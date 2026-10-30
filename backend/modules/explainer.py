from __future__ import annotations



from typing import Any



from backend.config import DEFAULT_DISCLAIMER

from backend.rag.models import RetrievalResult

from backend.schemas import Answer, Citation, KnowledgeEntry, MaskedItem, Step, Warning



NOT_FOUND_SOURCE_URL = "https://www.india.gov.in/"

NOT_FOUND_LAST_VERIFIED = "2026-10-03"





def _to_entry(entry: KnowledgeEntry | dict[str, Any]) -> KnowledgeEntry:

    if isinstance(entry, KnowledgeEntry):

        return entry

    return KnowledgeEntry(**entry)





def explain_entry(

    entry: KnowledgeEntry | dict[str, Any],

    user_question: str,

    masked_items: list[MaskedItem] | None = None,

) -> Answer:

    """Build a source-grounded answer from one verified/curated knowledge entry.



    This first production-safe explainer is deterministic on purpose. It does not call

    an external AI model yet, so it cannot invent facts. Later, an LLM can rewrite the

    summary, but the source URL, date, checklist, warnings, and disclaimer should still

    be copied from trusted data in code.

    """

    clean_question = " ".join(user_question.strip().split())

    if len(clean_question) > 240:

        clean_question = f"{clean_question[:237]}..."

    knowledge = _to_entry(entry)



    summary = knowledge.summary

    if knowledge.status != "verified":

        summary = (

            f"{summary} Note: this guide is currently marked unverified in the project data, "

            "so re-check the official source before using it for a real task."

        )







    return Answer(

        entry_id=knowledge.id,

        title=knowledge.title,

        summary=summary,

        documents_needed=knowledge.documents_needed,

        steps=[Step(title=step.title, detail=step.detail) for step in knowledge.steps],

        warnings=[

            Warning(title=warning.title, message=warning.message, severity=warning.severity)

            for warning in knowledge.warnings

        ],

        source_url=knowledge.source.url,

        last_verified=knowledge.source.last_verified,

        confidence="medium" if knowledge.status == "verified" else "low",

        masked_items=masked_items or [],

        disclaimer=DEFAULT_DISCLAIMER,

    )





import re





def clean_rag_text(text: str) -> str:

    """Clean markdown links, images, headings, and formatting noise from excerpts."""

    if not text:

        return ""

    # Strip markdown image syntax ![alt](url) -> alt

    cleaned = re.sub(r"!\[([^\]]*)\]\([^)]+\)", r"\1", text)

    # Strip markdown link syntax [text](url) -> text

    cleaned = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", cleaned)

    # Strip heading symbols (#, ##, etc.)

    cleaned = re.sub(r"#+\s*", "", cleaned)

    # Clean breadcrumb junk like "* ) *" or "* *" or list numbers like "1. 2."

    cleaned = re.sub(r"\*\s*\)?\s*\*?", " ", cleaned)

    cleaned = re.sub(r"\b\d+\.\s*", "", cleaned)

    # Normalize whitespaces

    return " ".join(cleaned.split())





def _passage_quality_score(raw_text: str) -> float:

    """Measure whether a chunk contains real sentences vs pure navigation links."""

    cleaned = clean_rag_text(raw_text)

    words = cleaned.split()

    if len(words) < 5:

        return -10.0

    sentence_punct = sum(1 for c in cleaned if c in ".!?;")

    links = re.findall(r"\[([^\]]+)\]\([^)]+\)", raw_text)

    link_words = sum(len(l.split()) for l in links)

    link_ratio = link_words / max(len(raw_text.split()), 1)

    return (sentence_punct * 4.0) - (link_ratio * 15.0) + min(len(words), 80) * 0.1





def explain_rag_result(

    result: RetrievalResult,

    user_question: str,

    masked_items: list[MaskedItem] | None = None,

) -> Answer | None:

    """Return a conservative extractive answer from candidate official passages.



    The corpus has source provenance but has not been independently fact-checked.

    Therefore this function quotes short passages, exposes that limitation, and

    never turns candidate text into invented procedures or recommendations.

    """

    if not result.hits:

        return None



    citations: list[Citation] = []

    seen_urls: set[str] = set()

    scored_hits: list[tuple[float, Citation]] = []



    for hit in result.hits:

        for source in hit.document.sources:

            if source.source_url in seen_urls:

                continue

            seen_urls.add(source.source_url)

            clean_title_str = clean_rag_text(source.title) or "Official civic procedure"

            clean_excerpt_str = clean_rag_text(hit.document.text)[:697]

            q_score = _passage_quality_score(hit.document.text)

            citation = Citation(

                title=clean_title_str[:300],

                url=source.source_url,

                excerpt=clean_excerpt_str,

                reported_last_verified=source.reported_last_verified,

                factual_verification="unverified",

            )

            citations.append(citation)

            scored_hits.append((q_score, citation))

            break

        if len(citations) >= 3:

            break



    if not citations:

        return None



    # Prioritize the most descriptive, informational passage for the primary step

    scored_hits.sort(key=lambda x: x[0], reverse=True)
    first = scored_hits[0][1]

    question = " ".join(user_question.split())[:240]
    excerpt_clean = first.excerpt.strip()
    summary_candidate = (
        f"{excerpt_clean[:220].strip()} Note: this candidate evidence from official sources "
        "has not been independently fact-checked. Confirm time-sensitive rules on the linked official portal."
    )

    dynamic_steps: list[Step] = []
    for idx, (score, c) in enumerate(scored_hits[:2], 1):
        clean_name = re.sub(r"[|\-].*$", "", c.title).strip() or f"Official guideline {idx}"
        dynamic_steps.append(Step(title=f"Review {clean_name}"[:80], detail=c.excerpt[:280].strip()))
    dynamic_steps.append(
        Step(
            title="Verify Official Portal and Apply",
            detail=f"Visit {first.url} to review current deadlines, official eligibility, and submit applications directly.",
        )
    )

    return Answer(
        title=f"Relevant official material: {first.title}"[:180],
        summary=summary_candidate,
        documents_needed=[],
        steps=dynamic_steps,
        warnings=[

            Warning(

                title="Candidate evidence, not verified advice",

                message="Retrieval found related official-source text, but the project has not independently validated every factual statement.",

                severity="warning",

            )

        ],

        source_url=first.url,

        last_verified=first.reported_last_verified,

        confidence="low",

        masked_items=masked_items or [],

        citations=citations,

        disclaimer=DEFAULT_DISCLAIMER,

    )







def not_found_answer(user_question: str, masked_items: list[MaskedItem] | None = None) -> Answer:

    clean_question = " ".join(user_question.strip().split()) or "your request"

    if len(clean_question) > 240:

        clean_question = f"{clean_question[:237]}..."

    return Answer(

        title="No verified guide found",

        summary=(

            f"I could not find a close enough verified guide for '{clean_question}'. "

            "To avoid guessing, this assistant will not invent steps. Please check the relevant "

            "official portal or add a verified guide to the knowledge base first."

        ),

        documents_needed=[],

        steps=[],
        warnings=[
            Warning(
                title="Answer not grounded",
                message="No matching local guide was found, so the system is intentionally refusing to guess.",
                severity="warning",
            )
        ],
        source_url=None,

        last_verified=NOT_FOUND_LAST_VERIFIED,

        confidence="low",

        masked_items=masked_items or [],

        disclaimer=DEFAULT_DISCLAIMER,

    )









def greeting_answer(user_question: str, masked_items: list[MaskedItem] | None = None) -> Answer:
    return Answer(
        title="Welcome to Nivaan",
        summary=(
            "Hello! I am Nivaan, your AI civic and banking assistant. How can I help you today? "
            "You can ask me about official Indian government procedures (such as PAN card, Passport, Aadhaar, Voter ID, ITR, or EPF) "
            "or upload/paste document text to review legal notices and loan agreements."
        ),
        documents_needed=[],
        steps=[],
        warnings=[],
        source_url=None,
        last_verified=NOT_FOUND_LAST_VERIFIED,
        confidence="high",
        masked_items=masked_items or [],
        disclaimer=DEFAULT_DISCLAIMER,
    )



__all__ = ["DEFAULT_DISCLAIMER", "explain_entry", "explain_rag_result", "greeting_answer", "not_found_answer"]



