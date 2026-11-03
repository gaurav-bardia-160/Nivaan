from __future__ import annotations

import re
from collections.abc import Generator
from typing import Any

from datetime import datetime, timezone

from backend.config import DEFAULT_DISCLAIMER, WEB_SEARCH_ENABLED, WEB_SEARCH_CONFIDENCE_THRESHOLD
from backend.modules.agent import route
from backend.modules.bandit_policy import bandit_policy
from backend.modules.domain_router import Domain, classify_domain, entry_matches_domain
from backend.modules.unresolved_queue import log_unresolved_query
from backend.modules.explainer import (
    NOT_FOUND_LAST_VERIFIED,
    NOT_FOUND_SOURCE_URL,
    explain_entry,
    explain_rag_result,
    greeting_answer,
    not_found_answer,
)
from backend.modules.guardrails import find_flags, mask_text
from backend.modules.llm import (
    LocalLLMClient,
    apply_rewrite_to_answer,
    enhance_grounded_answer,
)
from backend.modules.memory import conversation_memory
from backend.modules.retrieval import find_entry, find_entry_by_id, find_entry_with_score
from backend.modules.translate_voice import apply_language_policy
from backend.modules.translator import extract_language_and_clean_query
from backend.rag.runtime import retrieve_if_enabled
from backend.schemas import Answer, AskRequest, Step, Warning



_GREETING_WORDS = {
    "hi", "hello", "hey", "heya", "hiya", "namaste", "namaskar", "pranam",
    "kem cho", "kemcho", "good morning", "good afternoon", "good evening", "good day",
    "greetings", "help", "who are you", "what can you do", "intro", "welcome",
}


def _is_pure_greeting(text: str) -> bool:
    import re
    cleaned = re.sub(r"[^\w\s]", "", text.strip().lower())
    return cleaned in _GREETING_WORDS

_FOLLOW_UP_MARKERS = {
    "that", "this", "it", "its", "same", "above", "these", "those", "here", "there",
    # Hindi/Hinglish pronouns
    "iska", "iski", "iske", "uska", "uski", "uske", "yeh", "ye", "woh", "wo", "isme", "usme",
    # Gujarati pronouns
    "ana", "ama", "te", "tenu",
}

_FOLLOW_UP_INTENTS = {
    "document", "documents", "doc", "docs", "proof", "proofs", "paper", "papers", "paperwork",
    "step", "steps", "procedure", "process", "apply", "requirement", "requirements",
    "fee", "fees", "cost", "charge", "charges", "price", "penalty", "free", "pay",
    "time", "days", "duration", "tat", "deadline", "how long",
    "status", "track", "tracking", "check", "verify",
    "eligibility", "eligible", "criteria", "who can",
    # Troubleshooting, error, exception & failure intents
    "failed", "fail", "failure", "stuck", "pending", "rejected", "rejection", "error",
    "cancelled", "cancel", "mismatch", "refund", "reissue", "delay", "delayed",
    "not working", "issue", "problem", "dispute", "ombudsman", "grievance", "escalate",
    "escalation", "complaint", "deducted", "deduct", "money", "srn", "arn", "adverse", "reversal",
    # Hindi/Gujarati intents
    "dastavej", "kagaj", "paisa", "shulk", "samay", "kya", "kaise",
    "atki", "atke", "radd", "khata", "shikayat", "kat", "kata", "kaat",
}

_TROUBLESHOOTING_TOKENS = {
    "failed", "fail", "failure", "fails", "stuck", "pending", "rejected", "rejection", "error",
    "cancelled", "cancel", "mismatch", "refund", "reissue", "delay", "delayed", "delays",
    "issue", "problem", "dispute", "ombudsman", "grievance", "escalate", "escalation",
    "deducted", "deduct", "debited", "debit", "srn", "arn", "adverse", "reversal",
    "exhausted", "limit", "crossed", "unpaid", "unvalidated", "correction", "defective",
    "tat", "overdue", "exceeded", "atki", "atke", "radd", "shikayat", "kat", "kata", "kaat",
    "unsolicited", "foreclosure", "prepayment", "cibil", "experian", "crif",
    "joint declaration", "cheque", "passbook", "fvr", "blo", "aero", "ero",
    "nalsa", "edaakhil", "dcdrc", "scdrc", "ncdrc", "mbu", "baal aadhaar",
    "condonation", "119", "139", "330",
}


def _has_anaphoric_reference(text: str) -> bool:
    tokens = {t.lower().strip("?,.!:;'\"") for t in text.split()}
    return bool(tokens & _FOLLOW_UP_MARKERS)


_STANDALONE_TOPIC_TERMS = {
    # Civic & Identity
    "passport", "pasport", "paspot", "passsport", "psk", "popsk", "tatkaal",
    "pan", "pancard", "e-pan", "epan", "nsdl", "utiitsl", "form 49a",
    "aadhaar", "aadhar", "adhar", "uidai", "eaadhaar", "biometric", "biometrics",
    "voter", "voters", "voterid", "voter-id", "epic", "nvsp", "eci",
    "dl", "rc", "driving", "licence", "license", "parivahan", "rto",
    "fastag", "toll", "nhai", "ihmcl", "vahan", "sarathi", "chassis", "challan", "echallan", "cbse", "marksheet",
    "tax", "itr", "itr-4", "itr-1", "itr-v", "income tax", "incometax",
    "pf", "epf", "epfo", "uan", "provident",
    "ration", "pds", "nfsa",
    "kisan", "pmkisan", "pm-kisan",
    "apaar", "digilocker", "udyam", "msme", "gst",
    "fir", "police fir", "police complaint", "consumer court",
    "cybercrime", "1930",
    "savings account", "bank account", "fixed deposit", "rbi", "loan", "foreclosure", "cibil", "atm", "cibil", "experian", "crif", "edaakhil", "nalsa",
    # Hindi/Gujarati terms
    "आधार", "આધાર", "पैन", "પૅન", "पासपोर्ट", "પાસપોર્ટ", "मतदाता", "ચૂંટણી", "ટેક્સ", "कर", "आयकर",
}


def _has_standalone_topic(text: str) -> bool:
    lowered = text.lower()
    _UNSUPPORTED_NON_CIVIC_TERMS = {
        "cake", "bake", "baking", "recipe", "cook", "cooking", "chocolate",
        "movie", "song", "songs", "lyrics", "cricket", "football", "weather", "joke", "jokes",
    }
    lowered_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", lowered))
    if lowered_tokens & _UNSUPPORTED_NON_CIVIC_TERMS:
        return False
    tokens = {t.strip("?,.!:;'\"") for t in lowered.split()}
    if tokens & _STANDALONE_TOPIC_TERMS:
        return True
    for phrase in (
        "income tax", "driving license", "driving licence", "ration card",
        "savings account", "bank account", "consumer court", "pm kisan",
        "police fir", "pan card", "voter id", "aadhar card", "aadhaar card", "police verification", "joint declaration", "cross limit", "auto reversal", "credit card", "legal aid", "upi transaction", "upi payment failed", "failed upi", "upi compensation", "rbi compensation",
        "fastag", "toll refund", "nhai", "ihmcl", "vahan", "chassis mismatch", "chassis number", "rc correction", "digilocker", "cbse marksheet",
    ):
        if phrase in lowered:
            return True
    return False


def _is_follow_up_query(text: str) -> bool:
    tokens = {t.lower().strip("?,.!:;'\"") for t in text.split()}
    has_pronoun = bool(tokens & _FOLLOW_UP_MARKERS)
    if has_pronoun:
        return True

    # Check for troubleshooting / error tokens: citizens often describe procedural failures in full sentences
    # If the user explicitly mentions a standalone civic topic, it has its own domain/procedure.
    # It must NOT be treated as a follow-up to a different domain from a previous turn.
    if _has_standalone_topic(text):
        return False

    has_troubleshooting = bool(tokens & _TROUBLESHOOTING_TOKENS)
    if has_troubleshooting and len(tokens) <= 35:
        return True

    entry, score = find_entry_with_score(text)
    if entry is not None and score >= 55 and _verified_entry_covers_request(entry.get("id", ""), text):
        return False

    has_intent = bool(tokens & _FOLLOW_UP_INTENTS)
    if has_intent and len(tokens) <= 20:
        return True
    return False


def reformulate_follow_up_query(
    search_text: str,
    context_topic: str | None,
    previous_entry_title: str | None = None,
) -> str:
    """Reformulate pronoun-heavy, ambiguous, or error follow-up queries using prior context."""
    topic = (context_topic or previous_entry_title or "").strip()
    if not topic:
        return search_text

    clean_topic = re.sub(r"^(Relevant official material:\s*)", "", topic).strip()
    lowered_search = search_text.lower()
    lowered_topic = clean_topic.lower()

    topic_words = set(re.findall(r"\b[a-z0-9_-]+\b", lowered_topic)) - {"the", "a", "an", "for", "to", "in", "of", "and"}
    search_words = set(re.findall(r"\b[a-z0-9_-]+\b", lowered_search))
    if len(topic_words & search_words) >= 2:
        return search_text

    tokens = {t.lower().strip("?,.!:;'\"") for t in search_text.split()}
    is_trouble = bool(tokens & _TROUBLESHOOTING_TOKENS)
    has_pronoun = bool(tokens & _FOLLOW_UP_MARKERS)
    has_intent = bool(tokens & _FOLLOW_UP_INTENTS)

    if is_trouble or has_pronoun or has_intent or len(tokens) <= 6:
        return f"{clean_topic} {search_text}"

    return search_text


def _request_text(request: AskRequest) -> str:
    parts = [request.question or "", request.document_text or ""]
    return "\n\n".join(part.strip() for part in parts if part and part.strip())


def _verified_entry_covers_request(entry_id: str, text: str) -> bool:
    """Reject broad router matches when the verified guide does not cover the requested subtask."""
    import re
    query_domain = classify_domain(text)
    if not entry_matches_domain(entry_id, None, query_domain):
        return False
    lowered = text.lower()
    _UNSUPPORTED_NON_CIVIC_TERMS = {
        "cake", "bake", "baking", "recipe", "cook", "cooking", "chocolate",
        "movie", "song", "songs", "lyrics", "cricket", "football", "weather", "joke", "jokes",
    }
    lowered_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", lowered))
    if lowered_tokens & _UNSUPPORTED_NON_CIVIC_TERMS:
        return False
    if entry_id == "pan_card_new":
        lowered_tokens = set(re.findall(r"\b[a-z0-9_-]+\b", lowered))
        if not (lowered_tokens & {"pan", "pancard", "epan"} or "form 49a" in lowered or "form 49aa" in lowered or "पैन" in lowered or "પૅન" in lowered):
            return False
        out_of_scope_intents = ("download", "reprint", "correction", "correct", "link aadhaar", "status")
        if any(intent in lowered for intent in out_of_scope_intents):
            return False
    if entry_id == "passport_application_new":
        passport_tokens = ("passport", "paspot", "pasport", "passsport", "psk", "popsk", "tatkaal")
        if not any(token in lowered for token in passport_tokens):
            return False
        renewal_tokens = ("renewal", "renew", "re-issue", "reissue", "expired", "expire")
        if any(token in lowered for token in renewal_tokens):
            return False
    if entry_id == "passport_renewal_reissue":
        renewal_tokens = ("renewal", "renew", "re-issue", "reissue", "expired", "expire")
        if not any(token in lowered for token in renewal_tokens):
            return False
    if entry_id == "voter_id_new_registration":
        voter_tokens = ("voter", "voters", "voterid", "voter-id", "epic", "nvsp", "eci", "electoral", "voting")
        if not any(token in lowered for token in voter_tokens):
            return False
    if entry_id == "aadhaar_enrolment_basics":
        out_of_scope = ("photo", "photograph", "picture", "mobile", "phone", "email", "address", "update", "correction", "change", "baal", "mbu", "biometric update")
        if any(intent in lowered for intent in out_of_scope):
            return False
    if entry_id in ("itr_filing_basics", "file_itr_basics"):
        tax_tokens = ("itr", "tax", "incometax", "income tax", "tax return", "form 16", "ay", "assessment year")
        if not any(token in lowered for token in tax_tokens):
            return False
        out_of_scope = ("defective", "139(9)", "139", "condonation", "119", "refund unpaid", "bank validation", "reissue", "notice")
        if any(intent in lowered for intent in out_of_scope):
            return False
    if entry_id == "epf_withdrawal_basics":
        out_of_scope = ("joint declaration", "closed company", "closed establishment", "untraceable", "cheque", "passbook", "name not printed", "stamp")
        if any(intent in lowered for intent in out_of_scope):
            return False
    if entry_id == "savings_account_kyc":
        out_of_scope = ("unsolicited", "cibil", "experian", "crif", "credit report", "credit card", "tat", "reversal")
        if any(intent in lowered for intent in out_of_scope):
            return False
    if entry_id == "loan_agreement_explainer":
        out_of_scope = ("unsolicited", "cibil", "experian", "crif", "credit report", "credit card")
        if any(intent in lowered for intent in out_of_scope):
            return False
    if entry_id == "aadhaar_photo_biometric_update":
        photo_tokens = ("photo", "photograph", "picture", "image", "biometric", "biometrics", "fingerprint", "iris", "face")
        if not any(token in lowered for token in photo_tokens):
            return False
    if entry_id == "pm_kisan_scheme":
        kisan_tokens = ("kisan", "pmkisan", "farmer", "agriculture", "crop", "landholding")
        if not any(token in lowered for token in kisan_tokens):
            return False
    if entry_id in ("loan_agreement_review", "loan_agreement_explainer"):
        loan_tokens = ("loan", "emi", "borrower", "lender", "foreclosure", "prepayment")
        if not any(token in lowered for token in loan_tokens):
            return False
    if entry_id in ("consumer_complaint_basics", "consumer_court_complaint"):
        if any(token in lowered for token in ("tax", "itr", "return", "139")):
            return False
        # Specific jurisdictional or self-representation questions must be answered dynamically by statutory RAG
        specific_legal_intents = ("represent myself", "represent himself", "without a lawyer", "hire a lawyer", "need a lawyer", "district court", "district commission", "pecuniary", "jurisdiction", "50 lakh", "limit")
        if any(intent in lowered for intent in specific_legal_intents):
            return False
        consumer_tokens = ("consumer", "edaakhil", "unfair trade", "deficiency", "dcdrc", "district commission")
        if not any(token in lowered for token in consumer_tokens) and not ("defective" in lowered and any(t in lowered for t in ("goods", "product", "item", "service", "phone", "appliance"))):
            return False
    if entry_id == "aadhaar_pvc_payment_failed":
        if not any(token in lowered for token in ("aadhaar", "aadhar", "pvc", "uidai")):
            return False
        trouble_tokens = ("failed", "deducted", "deduct", "debit", "debited", "srn", "stuck", "cut", "kata", "error", "money", "refund", "pending", "paisa", "transaction", "reversal")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "itr_bank_validation_failed":
        if not any(token in lowered for token in ("itr", "incometax", "income tax", "tax return", "form 16")) and not ("tax" in lowered and "refund" in lowered):
            return False
        trouble_tokens = ("validation", "failed", "unpaid", "reissue", "refund", "mismatch", "ifsc", "re-issue", "reject", "rejected")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "passport_police_verification_delayed":
        if not any(token in lowered for token in ("passport", "paspot", "pasport")):
            return False
        trouble_tokens = ("police", "verification", "delay", "delayed", "pending", "adverse", "days", "tat", "clearance")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "epf_joint_declaration_correction":
        if not any(token in lowered for token in ("epf", "epfo", "pf", "uan")):
            return False
        trouble_tokens = ("joint declaration", "correction", "mismatch", "wrong", "exit", "father", "employer", "rejected", "claim")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "rbi_failed_upi_atm_penalty":
        if not any(token in lowered for token in ("upi", "atm", "rbi", "penalty", "compensation", "cash")):
            return False
        trouble_tokens = ("failed", "fail", "deducted", "debit", "debited", "reversal", "penalty", "100", "tat", "dispute", "ombudsman", "stuck")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "aadhaar_cross_limit_exception":
        if not any(token in lowered for token in ("aadhaar", "aadhar", "uidai")):
            return False
        trouble_tokens = ("limit", "exhausted", "cross", "exception", "third time", "twice", "maximum", "cannot update", "blocked", "rejected")
        if not any(token in lowered for token in trouble_tokens):
            return False
    if entry_id == "fastag_toll_dispute_refund":
        if not any(token in lowered for token in ("fastag", "toll", "nhai", "ihmcl", "plaza")):
            return False
    if entry_id == "parivahan_vahan_rc_correction":
        if not any(token in lowered for token in ("rc", "vahan", "parivahan", "chassis", "challan", "echallan", "rto")):
            return False
    if entry_id == "digilocker_cbse_name_mismatch":
        if not any(token in lowered for token in ("cbse", "digilocker", "marksheet")):
            return False
    return True


def _finalize_answer(answer: Answer, *, request: AskRequest, safe_question: str, target_lang: str, rl_arm: str | None = None) -> Answer:
    translated = apply_language_policy(answer, target_lang, query_text=safe_question)
    if rl_arm:
        translated = translated.model_copy(update={"rl_arm": rl_arm})
    conversation_memory.remember(
        request.conversation_id,
        user_text=safe_question,
        answer=translated,
    )
    return translated


def run(request: AskRequest | dict[str, Any]) -> Answer:
    """Run the safe backend workflow for typed text and supported uploads.

    Current production boundary:
    - Supports typed questions, pasted document_text, .txt uploads, and text-based PDF uploads.
    - Masks obvious sensitive values server-side before retrieval/explanation.
    - Routes the request with deterministic agent rules.
    - Adds conservative rule-based warnings for document text.
    - Returns English answers only and warns honestly for non-English answer requests.
    - Never guesses outside the local knowledge base.
    """
    parsed_request = request if isinstance(request, AskRequest) else AskRequest(**request)
    if parsed_request.conversation_id and getattr(parsed_request, "history", None):
        conversation_memory.sync_history(parsed_request.conversation_id, parsed_request.history)

    masked_question = mask_text(parsed_request.question)
    masked_document = mask_text(parsed_request.document_text)
    masked_items = list({item.item_type: item for item in [*masked_question.masked_items, *masked_document.masked_items]}.values())
    safe_request = parsed_request.model_copy(
        update={
            "question": masked_question.text or None,
            "document_text": masked_document.text or None,
        }
    )
    safe_text = _request_text(safe_request)

    search_question, target_lang = extract_language_and_clean_query(masked_question.text, parsed_request.language)
    search_document, _ = extract_language_and_clean_query(masked_document.text, parsed_request.language)
    routing_request = parsed_request.model_copy(
        update={
            "question": search_question or None,
            "document_text": search_document or None,
        }
    )
    search_text = _request_text(routing_request) or safe_text
    query_domain = classify_domain(search_text, safe_request.document_text)

    # Reinforcement Learning: Select optimal retrieval and LLM hyperparameters via LinUCB Contextual Bandit
    is_followup = _is_follow_up_query(search_text)
    bandit_action = bandit_policy.select_action(search_text, is_followup=is_followup)
    bandit_policy.record_action(parsed_request.conversation_id, search_text, bandit_action)

    if (
        parsed_request.input_type == "question"
        and not parsed_request.document_text
        and _is_pure_greeting(search_text)
    ):
        base_greeting = greeting_answer(safe_text, masked_items=masked_items)
        greeting = enhance_grounded_answer(
            base_greeting,
            question=safe_text,
            memory=conversation_memory.recent(parsed_request.conversation_id),
            temperature=bandit_action.temperature,
        )
        return _finalize_answer(
            greeting,
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
            rl_arm=bandit_action.name,
        )

    memory_turns = conversation_memory.recent(parsed_request.conversation_id, limit=25)
    effective_context_topic = parsed_request.context_topic
    context_entry_id = parsed_request.previous_entry_id or conversation_memory.latest_entry_id(
        parsed_request.conversation_id
    )

    # Domain boundary protection: if current query introduces a standalone topic or switches domain,
    # reset any inherited context topic to eliminate cross-domain bleed (the "punting trap" & template paralysis)
    if _has_standalone_topic(search_text):
        effective_context_topic = None
        context_entry_id = None
    elif memory_turns:
        prev_text = memory_turns[-1].user_text or ""
        prev_domain = classify_domain(prev_text)
        if query_domain != Domain.UNKNOWN and prev_domain != Domain.UNKNOWN and query_domain != prev_domain:
            effective_context_topic = None
            context_entry_id = None

    if not effective_context_topic and memory_turns:
        for mt in reversed(memory_turns):
            t = mt.answer_title or ""
            if t and "welcome" not in t.lower() and "not found" not in t.lower():
                clean_t = re.sub(r"^(Relevant official material:\s*)", "", t).strip()
                if clean_t.lower() not in ("frequently asked questions", "faq", "faqs", "official civic procedure", "home", "user manual", "overview"):
                    effective_context_topic = clean_t
                    break
        if not effective_context_topic and memory_turns:
            effective_context_topic = memory_turns[-1].user_text

    # Multi-turn conversational context expansion & query reformulation:
    if effective_context_topic and (_is_follow_up_query(search_text) or _has_anaphoric_reference(search_text)):
        reformulated_text = reformulate_follow_up_query(search_text, effective_context_topic)
        if reformulated_text != search_text:
            search_text = reformulated_text
            routing_request = routing_request.model_copy(update={"question": search_text})

    route_result = route(routing_request)

    entry = None
    if route_result.matched_entry_id:
        entry = find_entry_by_id(route_result.matched_entry_id)
    if not entry:
        entry, _ = find_entry_with_score(search_text)

    # Multi-turn conversational context resolution:
    # If no standalone entry matched (or entry matched incidentally while the user explicitly
    # used an anaphoric pronoun like 'for that' / 'for this' pointing to the previous topic),
    # resolve against previous_entry_id or context_topic.
    is_clarification = any(search_text.lower().startswith(p) for p in ("what is this ", "what are these ", "what is a ", "what does ", "explain this ", "meaning of "))
    if context_entry_id and _is_follow_up_query(search_text) and not is_clarification:
        if entry is None or _has_anaphoric_reference(search_text):
            candidate = find_entry_by_id(context_entry_id)
            if candidate:
                entry = candidate
                if not effective_context_topic:
                    effective_context_topic = candidate.get("title", "")

    entry_coverage_text = search_text
    if effective_context_topic and _is_follow_up_query(search_text):
        entry_coverage_text = f"{effective_context_topic} {search_text}"

    if entry is None and effective_context_topic and _is_follow_up_query(search_text):
        candidate, _ = find_entry_with_score(effective_context_topic)
        if candidate:
            entry = candidate

    # 1. Document Analysis Path: For uploaded or pasted agreements/notices, analyze document text directly
    if parsed_request.input_type == "document" and parsed_request.document_text:
        if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
            doc_answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
            existing_titles = {warning.title for warning in doc_answer.warnings}
            extra_warnings = [warning for warning in find_flags(masked_document.text) if warning.title not in existing_titles]
            doc_answer = doc_answer.model_copy(update={"warnings": [*doc_answer.warnings, *extra_warnings], "citations": []})
            doc_answer = enhance_grounded_answer(
                doc_answer,
                question=safe_text,
                memory=memory_turns,
                temperature=bandit_action.temperature,
            )
            return _finalize_answer(
                doc_answer,
                request=parsed_request,
                safe_question=masked_question.text or safe_text,
                target_lang=target_lang,
                rl_arm=bandit_action.name,
            )

    # 2. Pure Dynamic RAG Search Path: Retrieve official evidence across canonical 1,353 corpus documents
    rag_query = search_text
    if effective_context_topic and (_is_follow_up_query(search_text) or _has_anaphoric_reference(search_text)):
        rag_query = f"{effective_context_topic} {search_text}"
    rag_result = retrieve_if_enabled(rag_query, domain=query_domain, top_k=bandit_action.top_k)
    MIN_RRF_CONFIDENCE_THRESHOLD = 0.010

    # Web Search Confidence Gate (Phase 1 - ephemeral, read-only to Qdrant)
    if WEB_SEARCH_ENABLED:
        from backend.web_search.confidence import compute_rag_confidence
        rag_confidence = compute_rag_confidence(rag_result)
        if rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:
            from backend.web_search.allowlist import build_allowlist_query
            from backend.web_search.audit_log import log_pending_ingestion
            from backend.web_search.fetcher import fetch_page_text, is_navigation_or_boilerplate_text
            from backend.web_search.searcher import search_duckduckgo
            from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE
            web_query = build_allowlist_query(search_text, query_domain)
            web_results = search_duckduckgo(web_query, max_results=3)
            fallback_candidate = None
            for res in web_results:
                page_text = fetch_page_text(res.url)
                if not page_text or len(page_text.strip()) < 30:
                    continue
                if is_navigation_or_boilerplate_text(page_text):
                    continue
                web_answer = synthesize_from_web(
                    safe_text, page_text, res.url,
                    memory=memory_turns,
                )
                is_rejected = (
                    DISCRIMINATOR_FAILURE_PHRASE.lower() in web_answer.summary.lower()
                    or any(rp in web_answer.summary.lower() for rp in (
                        "does not contain", "could not find", "cannot find", "no specific instructions",
                        "not found", "does not provide", "not mention", "no information", "unable to find",
                        "failed to extract", "read more",
                    ))
                )
                if is_rejected:
                    if fallback_candidate is None:
                        fallback_candidate = web_answer
                    continue

                log_pending_ingestion({
                    "query": safe_text,
                    "url": res.url,
                    "domain": query_domain.value if hasattr(query_domain, "value") else str(query_domain),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "snippet": res.snippet,
                })
                return _finalize_answer(
                    web_answer,
                    request=parsed_request,
                    safe_question=masked_question.text or safe_text,
                    target_lang=target_lang,
                    rl_arm=bandit_action.name,
                )

            if fallback_candidate is not None:
                return _finalize_answer(
                    fallback_candidate,
                    request=parsed_request,
                    safe_question=masked_question.text or safe_text,
                    target_lang=target_lang,
                    rl_arm=bandit_action.name,
                )

    if rag_result is not None and rag_result.hits:
        top_hit = rag_result.hits[0]
        # Strict Grounding Gate: If top chunk is below confidence threshold, refuse to guess
        if top_hit.score < MIN_RRF_CONFIDENCE_THRESHOLD:
            log_unresolved_query(
                safe_text,
                reason="low_retrieval_confidence",
                domain=supported_category(search_text) if 'supported_category' in globals() else None,
                top_score=top_hit.score,
                conversation_id=parsed_request.conversation_id,
            )
            return _finalize_answer(
                not_found_answer(safe_text, masked_items=masked_items),
                request=parsed_request,
                safe_question=masked_question.text or safe_text,
                target_lang=target_lang,
                rl_arm=bandit_action.name,
            )
        rag_answer = explain_rag_result(rag_result, safe_text, masked_items=masked_items)
        if rag_answer is not None:
            # If the user asked a supported general procedure query covering a verified catalog topic,
            # bind canonical metadata (entry_id, canonical title, official portal), while keeping all content dynamically synthesized
            if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
                verified_warnings = [
                    w if isinstance(w, Warning) else Warning(**w)
                    for w in entry.get("warnings", [])
                ]
                verified_steps = [
                    s if isinstance(s, Step) else Step(**s)
                    for s in entry.get("steps", [])
                ]
                entry_title_lower = entry.get("title", "").lower()
                clean_citations = [
                    c for c in rag_answer.citations
                    if not any(conflict in c.title.lower() for conflict in (
                        ("139(9)", "defective") if "bank" in entry_title_lower else ()
                    ))
                ]
                from backend.web_search.confidence import compute_rag_confidence
                score_conf = compute_rag_confidence(rag_result)
                dynamic_conf = "high" if score_conf >= 0.75 else ("medium" if score_conf >= 0.35 else "low")
                rag_answer = rag_answer.model_copy(update={
                    "entry_id": entry.get("id"),
                    "title": entry.get("title", rag_answer.title),
                    "summary": entry.get("summary") or rag_answer.summary,
                    "steps": verified_steps if verified_steps else rag_answer.steps,
                    "confidence": "medium" if entry.get("status") == "verified" else dynamic_conf,
                    "source_url": entry.get("source", {}).get("url") or rag_answer.source_url,
                    "documents_needed": entry.get("documents_needed") or rag_answer.documents_needed,
                    "warnings": verified_warnings if verified_warnings else rag_answer.warnings,
                    "citations": clean_citations if clean_citations else rag_answer.citations,
                })
            # Dynamically synthesize grounded summary, actionable steps, and documents needed using LLM
            rag_answer = enhance_grounded_answer(
                rag_answer,
                question=safe_text,
                memory=memory_turns,
                temperature=bandit_action.temperature,
            )
            return _finalize_answer(
                rag_answer,
                request=parsed_request,
                safe_question=masked_question.text or safe_text,
                target_lang=target_lang,
                rl_arm=bandit_action.name,
            )

    # 3. Fallback when RAG is disabled via feature flag but verified entry covers request
    if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
        answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
        answer = answer.model_copy(update={"citations": []})
        answer = enhance_grounded_answer(
            answer,
            question=safe_text,
            memory=memory_turns,
            temperature=bandit_action.temperature,
        )
        return _finalize_answer(
            answer,
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
            rl_arm=bandit_action.name,
        )

    log_unresolved_query(
        safe_text,
        reason="no_verified_guide_or_rag_match",
        domain=None,
        top_score=0.0,
        conversation_id=parsed_request.conversation_id,
    )
    return _finalize_answer(
        not_found_answer(safe_text, masked_items=masked_items),
        request=parsed_request,
        safe_question=masked_question.text or safe_text,
        target_lang=target_lang,
        rl_arm=bandit_action.name,
    )


def run_stream(request: AskRequest | dict[str, Any]) -> Generator[dict[str, object], None, None]:
    """Runs grounded RAG synthesis and yields Server-Sent Events (SSE) in real time.

    Events yielded:
    - status: Dynamic backend status messages ("Searching portals...", "Generating...")
    - meta: Metadata payload (title, confidence, source_url, citations, masked_items, rl_arm)
    - token: Plain language summary tokens as generated by the LLM
    - done: Complete finalized Answer object for persistence and structured section rendering
    """
    yield {"event": "status", "data": {"message": "Validating request & securing privacy..."}}

    parsed_request = request if isinstance(request, AskRequest) else AskRequest(**request)
    if parsed_request.conversation_id and getattr(parsed_request, "history", None):
        conversation_memory.sync_history(parsed_request.conversation_id, parsed_request.history)

    masked_question = mask_text(parsed_request.question)
    masked_document = mask_text(parsed_request.document_text)
    masked_items = list({item.item_type: item for item in [*masked_question.masked_items, *masked_document.masked_items]}.values())
    safe_request = parsed_request.model_copy(
        update={
            "question": masked_question.text or None,
            "document_text": masked_document.text or None,
        }
    )
    safe_text = _request_text(safe_request)

    search_question, target_lang = extract_language_and_clean_query(masked_question.text, parsed_request.language)
    search_document, _ = extract_language_and_clean_query(masked_document.text, parsed_request.language)
    routing_request = parsed_request.model_copy(
        update={
            "question": search_question or None,
            "document_text": search_document or None,
        }
    )
    search_text = _request_text(routing_request) or safe_text
    query_domain = classify_domain(search_text, safe_request.document_text)

    is_followup = _is_follow_up_query(search_text)
    bandit_action = bandit_policy.select_action(search_text, is_followup=is_followup)
    bandit_policy.record_action(parsed_request.conversation_id, search_text, bandit_action)

    # 1. Pure Greeting Path
    if (
        parsed_request.input_type == "question"
        and not parsed_request.document_text
        and _is_pure_greeting(search_text)
    ):
        base_greeting = greeting_answer(safe_text, masked_items=masked_items)
        yield {
            "event": "meta",
            "data": {
                "title": base_greeting.title,
                "confidence": base_greeting.confidence,
                "source_url": str(base_greeting.source_url),
                "citations": [],
                "masked_items": [m.model_dump(mode="json") for m in masked_items],
                "rl_arm": bandit_action.name,
            },
        }
        client = LocalLLMClient()
        final_rewrite = None
        token_count = 0
        if client.config.enabled:
            for kind, payload in client.stream_grounded_answer(
                question=safe_text,
                answer=base_greeting,
                memory=conversation_memory.recent(parsed_request.conversation_id),
                temperature=bandit_action.temperature,
            ):
                if kind == "token" and payload:
                    token_count += 1
                    yield {"event": "token", "data": {"delta": str(payload)}}
                elif kind == "final":
                    final_rewrite = payload

        if token_count == 0:
            words = base_greeting.summary.split(" ")
            for i, w in enumerate(words):
                yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}

        greeting = apply_rewrite_to_answer(base_greeting, final_rewrite, safe_text)
        final_ans = _finalize_answer(
            greeting,
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
            rl_arm=bandit_action.name,
        )
        yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
        return

    yield {"event": "status", "data": {"message": "Searching official portals & statutory guidelines..."}}

    memory_turns = conversation_memory.recent(parsed_request.conversation_id, limit=25)
    effective_context_topic = parsed_request.context_topic
    context_entry_id = parsed_request.previous_entry_id or conversation_memory.latest_entry_id(
        parsed_request.conversation_id
    )

    if _has_standalone_topic(search_text):
        effective_context_topic = None
        context_entry_id = None
    elif memory_turns:
        prev_text = memory_turns[-1].user_text or ""
        prev_domain = classify_domain(prev_text)
        if query_domain != Domain.UNKNOWN and prev_domain != Domain.UNKNOWN and query_domain != prev_domain:
            effective_context_topic = None
            context_entry_id = None

    if not effective_context_topic and memory_turns:
        for mt in reversed(memory_turns):
            t = mt.answer_title or ""
            if t and "welcome" not in t.lower() and "not found" not in t.lower():
                clean_t = re.sub(r"^(Relevant official material:\s*)", "", t).strip()
                if clean_t.lower() not in ("frequently asked questions", "faq", "faqs", "official civic procedure", "home", "user manual", "overview"):
                    effective_context_topic = clean_t
                    break
        if not effective_context_topic and memory_turns:
            effective_context_topic = memory_turns[-1].user_text

    if effective_context_topic and (_is_follow_up_query(search_text) or _has_anaphoric_reference(search_text)):
        reformulated_text = reformulate_follow_up_query(search_text, effective_context_topic)
        if reformulated_text != search_text:
            search_text = reformulated_text
            routing_request = routing_request.model_copy(update={"question": search_text})

    route_result = route(routing_request)

    entry = None
    if route_result.matched_entry_id:
        entry = find_entry_by_id(route_result.matched_entry_id)
    if not entry:
        entry, _ = find_entry_with_score(search_text)

    is_clarification = any(search_text.lower().startswith(p) for p in ("what is this ", "what are these ", "what is a ", "what does ", "explain this ", "meaning of "))
    if context_entry_id and _is_follow_up_query(search_text) and not is_clarification:
        if entry is None or _has_anaphoric_reference(search_text):
            candidate = find_entry_by_id(context_entry_id)
            if candidate:
                entry = candidate
                if not effective_context_topic:
                    effective_context_topic = candidate.get("title", "")

    entry_coverage_text = search_text
    if effective_context_topic and _is_follow_up_query(search_text):
        entry_coverage_text = f"{effective_context_topic} {search_text}"

    if entry is None and effective_context_topic and _is_follow_up_query(search_text):
        candidate, _ = find_entry_with_score(effective_context_topic)
        if candidate:
            entry = candidate

    # 2. Document Analysis Path
    if parsed_request.input_type == "document" and parsed_request.document_text:
        if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
            doc_answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
            existing_titles = {warning.title for warning in doc_answer.warnings}
            extra_warnings = [warning for warning in find_flags(masked_document.text) if warning.title not in existing_titles]
            doc_answer = doc_answer.model_copy(update={"warnings": [*doc_answer.warnings, *extra_warnings], "citations": []})

            yield {
                "event": "meta",
                "data": {
                    "title": doc_answer.title,
                    "confidence": doc_answer.confidence,
                    "source_url": str(doc_answer.source_url),
                    "citations": [],
                    "masked_items": [m.model_dump(mode="json") for m in masked_items],
                    "rl_arm": bandit_action.name,
                },
            }
            yield {"event": "status", "data": {"message": "Formulating document guidance..."}}

            client = LocalLLMClient()
            final_rewrite = None
            token_count = 0
            if client.config.enabled:
                for kind, payload in client.stream_grounded_answer(
                    question=safe_text,
                    answer=doc_answer,
                    memory=memory_turns,
                    temperature=bandit_action.temperature,
                ):
                    if kind == "token" and payload:
                        token_count += 1
                        yield {"event": "token", "data": {"delta": str(payload)}}
                    elif kind == "final":
                        final_rewrite = payload

            if token_count == 0:
                words = doc_answer.summary.split(" ")
                for i, w in enumerate(words):
                    yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}

            enhanced = apply_rewrite_to_answer(doc_answer, final_rewrite, safe_text)
            final_ans = _finalize_answer(
                enhanced,
                request=parsed_request,
                safe_question=masked_question.text or safe_text,
                target_lang=target_lang,
                rl_arm=bandit_action.name,
            )
            yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
            return

    # 3. Dynamic RAG Search Path
    rag_query = search_text
    if effective_context_topic and (_is_follow_up_query(search_text) or _has_anaphoric_reference(search_text)):
        rag_query = f"{effective_context_topic} {search_text}"
    rag_result = retrieve_if_enabled(rag_query, domain=query_domain, top_k=bandit_action.top_k)
    MIN_RRF_CONFIDENCE_THRESHOLD = 0.010

    # Web Search Confidence Gate for streaming (Phase 1 - ephemeral, read-only to Qdrant)
    if WEB_SEARCH_ENABLED:
        from backend.web_search.confidence import compute_rag_confidence
        rag_confidence = compute_rag_confidence(rag_result)
        if rag_confidence < WEB_SEARCH_CONFIDENCE_THRESHOLD:
            yield {"event": "status", "data": {"message": "Searching official government portals online..."}}
            from backend.web_search.allowlist import build_allowlist_query
            from backend.web_search.audit_log import log_pending_ingestion
            from backend.web_search.fetcher import fetch_page_text, is_navigation_or_boilerplate_text
            from backend.web_search.searcher import search_duckduckgo
            from backend.web_search.synthesizer import synthesize_from_web, DISCRIMINATOR_FAILURE_PHRASE
            web_query = build_allowlist_query(search_text, query_domain)
            web_results = search_duckduckgo(web_query, max_results=3)
            fallback_candidate = None
            for res in web_results:
                page_text = fetch_page_text(res.url)
                if not page_text or len(page_text.strip()) < 30:
                    continue
                if is_navigation_or_boilerplate_text(page_text):
                    continue
                web_answer = synthesize_from_web(
                    safe_text, page_text, res.url,
                    memory=memory_turns,
                )
                is_rejected = (
                    DISCRIMINATOR_FAILURE_PHRASE.lower() in web_answer.summary.lower()
                    or any(rp in web_answer.summary.lower() for rp in (
                        "does not contain", "could not find", "cannot find", "no specific instructions",
                        "not found", "does not provide", "not mention", "no information", "unable to find",
                        "failed to extract", "read more",
                    ))
                )
                if is_rejected:
                    if fallback_candidate is None:
                        fallback_candidate = web_answer
                    continue

                log_pending_ingestion({
                    "query": safe_text,
                    "url": res.url,
                    "domain": query_domain.value if hasattr(query_domain, "value") else str(query_domain),
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "snippet": res.snippet,
                })
                yield {
                    "event": "meta",
                    "data": {
                        "title": web_answer.title,
                        "confidence": web_answer.confidence,
                        "source_url": str(web_answer.source_url) if web_answer.source_url else "",
                        "citations": [c.model_dump(mode="json") for c in web_answer.citations],
                        "masked_items": [m.model_dump(mode="json") for m in masked_items],
                        "rl_arm": bandit_action.name,
                    },
                }
                yield {"event": "status", "data": {"message": "Synthesizing answer from official portal..."}}
                # Stream the summary tokens word-by-word (no LLM re-synthesis — already done in synthesize_from_web)
                words = web_answer.summary.split(" ")
                for i, w in enumerate(words):
                    yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}
                final_ans = _finalize_answer(
                    web_answer,
                    request=parsed_request,
                    safe_question=masked_question.text or safe_text,
                    target_lang=target_lang,
                    rl_arm=bandit_action.name,
                )
                yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
                return

            if fallback_candidate is not None:
                yield {
                    "event": "meta",
                    "data": {
                        "title": fallback_candidate.title,
                        "confidence": fallback_candidate.confidence,
                        "source_url": str(fallback_candidate.source_url) if fallback_candidate.source_url else "",
                        "citations": [c.model_dump(mode="json") for c in fallback_candidate.citations],
                        "masked_items": [m.model_dump(mode="json") for m in masked_items],
                        "rl_arm": bandit_action.name,
                    },
                }
                words = fallback_candidate.summary.split(" ")
                for i, w in enumerate(words):
                    yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}
                final_ans = _finalize_answer(
                    fallback_candidate,
                    request=parsed_request,
                    safe_question=masked_question.text or safe_text,
                    target_lang=target_lang,
                    rl_arm=bandit_action.name,
                )
                yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
                return

    if rag_result is not None and rag_result.hits:
        top_hit = rag_result.hits[0]
        if top_hit.score >= MIN_RRF_CONFIDENCE_THRESHOLD:
            rag_answer = explain_rag_result(rag_result, safe_text, masked_items=masked_items)
            if rag_answer is not None:
                if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
                    verified_warnings = [
                        w if isinstance(w, Warning) else Warning(**w)
                        for w in entry.get("warnings", [])
                    ]
                    verified_steps = [
                        s if isinstance(s, Step) else Step(**s)
                        for s in entry.get("steps", [])
                    ]
                    entry_title_lower = entry.get("title", "").lower()
                    clean_citations = [
                        c for c in rag_answer.citations
                        if not any(conflict in c.title.lower() for conflict in (
                            ("139(9)", "defective") if "bank" in entry_title_lower else ()
                        ))
                    ]
                    from backend.web_search.confidence import compute_rag_confidence
                    score_conf = compute_rag_confidence(rag_result)
                    dynamic_conf = "high" if score_conf >= 0.75 else ("medium" if score_conf >= 0.35 else "low")
                    rag_answer = rag_answer.model_copy(update={
                        "entry_id": entry.get("id"),
                        "title": entry.get("title", rag_answer.title),
                        "summary": entry.get("summary") or rag_answer.summary,
                        "steps": verified_steps if verified_steps else rag_answer.steps,
                        "confidence": "medium" if entry.get("status") == "verified" else dynamic_conf,
                        "source_url": entry.get("source", {}).get("url") or rag_answer.source_url,
                        "documents_needed": entry.get("documents_needed") or rag_answer.documents_needed,
                        "warnings": verified_warnings if verified_warnings else rag_answer.warnings,
                        "citations": clean_citations if clean_citations else rag_answer.citations,
                    })

                yield {
                    "event": "meta",
                    "data": {
                        "title": rag_answer.title,
                        "confidence": rag_answer.confidence,
                        "source_url": str(rag_answer.source_url),
                        "citations": [c.model_dump(mode="json") for c in rag_answer.citations],
                        "masked_items": [m.model_dump(mode="json") for m in masked_items],
                        "rl_arm": bandit_action.name,
                    },
                }
                yield {"event": "status", "data": {"message": "Formulating verified guidance..."}}

                client = LocalLLMClient()
                final_rewrite = None
                token_count = 0
                if client.config.enabled:
                    for kind, payload in client.stream_grounded_answer(
                        question=safe_text,
                        answer=rag_answer,
                        memory=memory_turns,
                        temperature=bandit_action.temperature,
                    ):
                        if kind == "token" and payload:
                            token_count += 1
                            yield {"event": "token", "data": {"delta": str(payload)}}
                        elif kind == "final":
                            final_rewrite = payload

                if token_count == 0:
                    words = rag_answer.summary.split(" ")
                    for i, w in enumerate(words):
                        yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}

                enhanced = apply_rewrite_to_answer(rag_answer, final_rewrite, safe_text)
                final_ans = _finalize_answer(
                    enhanced,
                    request=parsed_request,
                    safe_question=masked_question.text or safe_text,
                    target_lang=target_lang,
                    rl_arm=bandit_action.name,
                )
                yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
                return

    # 4. Verified Entry Fallback
    if entry is not None and _verified_entry_covers_request(entry.get("id", ""), entry_coverage_text):
        answer = explain_entry(entry, user_question=safe_text, masked_items=masked_items)
        answer = answer.model_copy(update={"citations": []})
        yield {
            "event": "meta",
            "data": {
                "title": answer.title,
                "confidence": answer.confidence,
                "source_url": str(answer.source_url),
                "citations": [],
                "masked_items": [m.model_dump(mode="json") for m in masked_items],
                "rl_arm": bandit_action.name,
            },
        }
        yield {"event": "status", "data": {"message": "Formulating verified guidance..."}}

        client = LocalLLMClient()
        final_rewrite = None
        token_count = 0
        if client.config.enabled:
            for kind, payload in client.stream_grounded_answer(
                question=safe_text,
                answer=answer,
                memory=memory_turns,
                temperature=bandit_action.temperature,
            ):
                if kind == "token" and payload:
                    token_count += 1
                    yield {"event": "token", "data": {"delta": str(payload)}}
                elif kind == "final":
                    final_rewrite = payload

        if token_count == 0:
            words = answer.summary.split(" ")
            for i, w in enumerate(words):
                yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}

        enhanced = apply_rewrite_to_answer(answer, final_rewrite, safe_text)
        final_ans = _finalize_answer(
            enhanced,
            request=parsed_request,
            safe_question=masked_question.text or safe_text,
            target_lang=target_lang,
            rl_arm=bandit_action.name,
        )
        yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}
        return

    # 5. Unsupported / No Verified Guide Found
    log_unresolved_query(
        safe_text,
        reason="no_verified_guide_or_rag_match",
        domain=None,
        top_score=0.0,
        conversation_id=parsed_request.conversation_id,
    )
    not_found = not_found_answer(safe_text, masked_items=masked_items)
    yield {
        "event": "meta",
        "data": {
            "title": not_found.title,
            "confidence": not_found.confidence,
            "source_url": str(not_found.source_url),
            "citations": [],
            "masked_items": [m.model_dump(mode="json") for m in masked_items],
            "rl_arm": bandit_action.name,
        },
    }
    words = not_found.summary.split(" ")
    for i, w in enumerate(words):
        yield {"event": "token", "data": {"delta": w + (" " if i < len(words) - 1 else "")}}

    final_ans = _finalize_answer(
        not_found,
        request=parsed_request,
        safe_question=masked_question.text or safe_text,
        target_lang=target_lang,
        rl_arm=bandit_action.name,
    )
    yield {"event": "done", "data": {"answer": final_ans.model_dump(mode="json")}}


__all__ = ["run", "run_stream"]
