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
from urllib.parse import urlparse

OFFICIAL_DOMAINS = {
    "uidai.gov.in", "myaadhaar.uidai.gov.in", "rbi.org.in", "incometax.gov.in",
    "www.incometax.gov.in", "tinpan.proteantech.in", "onlineservices.proteantech.in",
    "pan.utiitsl.com", "www.pan.utiitsl.com", "www.trackpan.utiitsl.com",
    "passportindia.gov.in", "www.passportindia.gov.in", "parivahan.gov.in",
    "epfindia.gov.in", "www.epfindia.gov.in", "epfigms.gov.in", "sebi.gov.in",
    "digilocker.gov.in", "pgportal.gov.in", "ncdrc.nic.in", "voters.eci.gov.in",
    "eci.gov.in", "nalsa.gov.in", "edaakhil.nic.in", "ecommitteesci.gov.in",
}


def is_allowed_official_source(url: str) -> bool:
    if not url:
        return False
    lowered = url.lower()
    if any(c in lowered for c in ("legaltax.in", "taxguru.in", "cleartax.in", "indiafilings.com", "impriindia.com", "dbonline.in", "seconize.co")):
        return False
    parsed = urlparse(url)
    domain = (parsed.netloc or "").lower().split(":")[0]
    is_gov = bool(re.search(r"\.(gov\.in|nic\.in)$", domain))
    is_whitelisted = any(domain == whitelisted or domain.endswith("." + whitelisted) for whitelisted in OFFICIAL_DOMAINS)
    return is_gov or is_whitelisted


def _is_direct_or_binary_question(query: str) -> bool:
    if not query:
        return False
    lowered = query.strip().lower()
    return any(lowered.startswith(p) for p in (
        "can i", "can we", "can a", "should i", "should we", "do i need", "does it",
        "will it", "is it", "is there", "are we", "am i", "whether", "do we need"
    ))





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

            if not is_allowed_official_source(source.source_url):

                continue

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

    # Preserve top retrieval ranking
    first = citations[0]
    top_hit_text = result.hits[0].document.text

    # 1. Summary: Extract introductory diagnostic / explanatory paragraph
    intro_match = re.split(r"(?:\n\n|\bDirect Resolution Steps:|\bStatutory Harmonised Turnaround Times:)", top_hit_text)
    intro_text = intro_match[0].strip() if intro_match else top_hit_text[:480].strip()
    if len(intro_text) > 480:
        intro_text = intro_text[:480].rsplit(".", 1)[0] + "."
    summary_candidate = (
        f"{intro_text} Note: this candidate evidence from official sources "
        "has not been independently fact-checked. Confirm time-sensitive rules on the linked official portal."
    )

    # 2. Steps: Check if chunk has explicit numbered resolution steps
    dynamic_steps: list[Step] = []
    numbered_parts = [
        p.strip() for p in re.split(r"(?=\b[1-9]\.\s+[A-Z])", top_hit_text)
        if re.match(r"^[1-9]\.\s+[A-Z]", p.strip())
    ]
    if numbered_parts:
        for p in numbered_parts[:5]:
            clean_p = re.sub(r"^[1-9]\.\s+", "", p).strip()
            if ":" in clean_p:
                st_title, st_detail = clean_p.split(":", 1)
                dynamic_steps.append(Step(title=st_title.strip()[:80], detail=st_detail.strip()[:650]))
            else:
                dynamic_steps.append(Step(title=clean_p[:60].strip(), detail=clean_p[:650]))

    extra_blocks = re.findall(
        r"((?:Statutory Penalty[^\n:]*|Escalation|Delivery TAT)):\s*([^\n]+(?:\n[^\n]+)?)",
        top_hit_text,
        flags=re.I,
    )
    for block_title, block_body in extra_blocks[:2]:
        dynamic_steps.append(Step(title=block_title.strip()[:80], detail=block_body.strip()[:600]))

    if not dynamic_steps and not _is_direct_or_binary_question(user_question):
        for idx, c in enumerate(citations[:2], 1):
            clean_name = re.sub(r"[|\-].*$", "", c.title).strip() or f"Official guideline {idx}"
            dynamic_steps.append(Step(title=f"Review {clean_name}"[:80], detail=c.excerpt[:350].strip()))
        dynamic_steps.append(
            Step(
                title="Verify Official Portal and Apply",
                detail=f"Visit {first.url} to review current deadlines, official eligibility, and submit applications directly.",
            )
        )

    # Dynamic confidence based on hybrid RRF retrieval score
    top_score = result.hits[0].score
    calc_conf = "high" if top_score >= 0.05 else ("medium" if top_score >= 0.02 else "low")
    
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
        confidence=calc_conf,

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



