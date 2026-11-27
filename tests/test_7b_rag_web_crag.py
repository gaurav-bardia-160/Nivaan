from __future__ import annotations

from datetime import date
from unittest.mock import MagicMock, patch

import httpx

from backend.modules.llm import LocalLLMClient, LocalLLMConfig, SummaryStreamFilter
import backend.pipeline as pipeline_mod
from backend.schemas import Answer, AskRequest, Citation
from backend.web_search.searcher import WebSearchResult, rank_results_for_query


def test_rank_results_for_query_handles_dict_subclass():
    results = [
        WebSearchResult(url="https://rbi.org.in/", title="Home", snippet="Welcome"),
        WebSearchResult(
            url="https://rbi.org.in/Scripts/FAQView.aspx?Id=10",
            title="Foreclosure Charges Prepayment FAQ",
            snippet="Guidelines on floating rate loans and prepayment penalties",
        ),
    ]
    ranked = rank_results_for_query("loan prepayment foreclosure penalties", results)
    assert len(ranked) == 2
    assert ranked[0].url == "https://rbi.org.in/Scripts/FAQView.aspx?Id=10"


def test_summary_stream_filter_suppresses_search_web_sentinel_and_trailing_keys():
    flt = SummaryStreamFilter()
    assert flt.feed("SEARCH_WEB_") == []
    assert flt.feed("REQUIRED") == []
    assert flt.accumulated_summary == ""

    flt2 = SummaryStreamFilter()
    emitted = []
    for chunk in [
        "RBI has ",
        "prohibited ",
        "foreclosure fees ",
        "for individual floating-rate borrowers.\n",
        "\ndocuments_needed: []\nsteps: []",
    ]:
        emitted.extend(flt2.feed(chunk))
    joined = "".join(emitted)
    assert "RBI has prohibited foreclosure fees" in joined
    assert "documents_needed" not in joined


def test_understand_query_extracts_search_keywords(monkeypatch):
    class FakeResp:
        def raise_for_status(self):
            return None

        def json(self):
            return {"message": {"content": '{"search_query": "EPFO joint declaration correction", "is_civic": true}'}}

    monkeypatch.setattr(httpx, "post", lambda *args, **kwargs: FakeResp())
    client = LocalLLMClient(
        LocalLLMConfig(
            enabled=True,
            base_url="http://127.0.0.1:11434",
            model="qwen7b-4k:latest",
            timeout_seconds=None,
            allow_remote=False,
        )
    )
    sq, is_civic = client.understand_query("mera pf mein naam galat hai company band ho gayi")
    assert sq == "EPFO joint declaration correction"
    assert is_civic is True


def test_stream_grounded_answer_triggers_needs_web_search_on_sentinel(monkeypatch):
    class FakeStreamResp:
        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def raise_for_status(self):
            return None

        def iter_lines(self):
            yield '{"message":{"content":"SEARCH_WEB_"},"done":false}'
            yield '{"message":{"content":"REQUIRED"},"done":true}'

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            pass

        def stream(self, *args, **kwargs):
            return FakeStreamResp()

    monkeypatch.setattr(httpx, "Client", FakeClient)
    client = LocalLLMClient(
        LocalLLMConfig(
            enabled=True,
            base_url="http://127.0.0.1:11434",
            model="qwen7b-4k:latest",
            timeout_seconds=None,
            allow_remote=False,
        )
    )
    ans = Answer(
        title="Tax Manual",
        summary="Some tax rules.",
        source_url="https://www.incometax.gov.in/",
        last_verified=date.today(),
        confidence="medium",
        citations=[
            Citation(
                title="Tax Manual",
                url="https://www.incometax.gov.in/",
                excerpt="Unrelated section.",
                reported_last_verified=date.today(),
                factual_verification="unverified",
            )
        ],
    )
    events = list(client.stream_grounded_answer(question="How to apply for Udyam?", answer=ans))
    assert events == [("needs_web_search", None)]


def test_pipeline_stream_falls_back_to_web_when_7b_flags_insufficient_rag(monkeypatch):
    monkeypatch.setenv("LOCAL_LLM_ENABLED", "true")
    monkeypatch.setenv("LOCAL_LLM_MODEL", "qwen7b-4k:latest")
    monkeypatch.setenv("RAG_ENABLED", "true")

    mock_doc = MagicMock()
    mock_doc.id = "doc1"
    mock_doc.category = "civic"
    mock_doc.text = "RBI rules on card issuance and billing."
    mock_doc.tags = ("rbi",)
    src = MagicMock()
    src.title = "RBI Master Direction"
    src.section = "General"
    src.source_url = "https://www.rbi.org.in/guide"
    src.reported_last_verified = date.today()
    src.factual_verification = "unverified"
    mock_doc.sources = (src,)
    mock_hit = MagicMock()
    mock_hit.document = mock_doc
    mock_hit.score = 0.05
    mock_res = MagicMock()
    mock_res.hits = (mock_hit,)
    mock_res.query = "loan prepayment"

    web_ans = Answer(
        title="Official Civic Procedure (rbi.org.in)",
        summary="RBI bars foreclosure penalties on floating-rate loans to individual borrowers.",
        source_url="https://www.rbi.org.in/faq",
        last_verified=date.today(),
        confidence="medium",
    )

    with patch.object(pipeline_mod, "WEB_SEARCH_ENABLED", True):
        with patch.object(pipeline_mod, "retrieve_if_enabled", return_value=mock_res):
            with patch("backend.web_search.confidence.compute_rag_confidence", return_value=0.80):
                with patch.object(
                    LocalLLMClient,
                    "stream_grounded_answer",
                    return_value=iter([("needs_web_search", None)]),
                ):
                    with patch.object(
                        pipeline_mod,
                        "_run_web_search_fallback",
                        return_value=(web_ans, True),
                    ) as mock_web:
                        events = list(
                            pipeline_mod.run_stream(
                                AskRequest(
                                    question="What are the RBI rules on loan prepayment?",
                                    conversation_id="test-crag-7b-web",
                                )
                            )
                        )

    mock_web.assert_called_once()
    done_ev = next(ev for ev in events if ev["event"] == "done")
    assert "floating-rate loans" in done_ev["data"]["answer"]["summary"]
