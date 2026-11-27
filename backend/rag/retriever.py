"""Hybrid lexical and vector retrieval over the canonical corpus."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from backend.modules.domain_router import Domain, classify_domain, get_allowed_rag_categories
from backend.modules.query_decomposer import decompose_query
from backend.rag.bm25 import BM25Index, tokenize
from backend.rag.embeddings import EmbeddingProvider
from backend.rag.loader import load_corpus
from backend.rag.models import LoadResult, RagDocument, RetrievalHit, RetrievalResult
from backend.rag.vector_store import VectorStore


class DocumentId(str):
    """Immutable document identifier preserving Python's data model invariant."""

    def __new__(cls, val: str, aliases: tuple[str, ...] | list[str] = ()):
        obj = str.__new__(cls, val)
        obj._aliases = tuple(aliases)
        return obj




@dataclass(frozen=True)
class RetrieverConfig:
    lexical_top_k: int = 30
    vector_top_k: int = 30
    final_top_k: int = 8
    rrf_k: int = 60

    def __post_init__(self):
        if min(self.lexical_top_k, self.vector_top_k, self.final_top_k, self.rrf_k) < 1:
            raise ValueError("retriever config values must be positive")


def document_text(doc: RagDocument) -> str:
    title_bits = " ".join(f"{source.title} {source.section}" for source in doc.sources)
    return f"{doc.category} {' '.join(doc.tags)} {title_bits} {doc.text}"


class RagRetriever:
    def __init__(
        self,
        load_result: LoadResult | None = None,
        *,
        config: RetrieverConfig | None = None,
        embedding_provider: EmbeddingProvider | None = None,
        vector_store: VectorStore | None = None,
    ):
        if (embedding_provider is None) != (vector_store is None):
            raise ValueError("embedding_provider and vector_store must be configured together")
        self.load_result = load_result or load_corpus()
        self.config = config or RetrieverConfig()
        self.documents = self.load_result.documents
        remapped_docs = []
        for doc in self.documents:
            if doc.sources and doc.sources[0].record_id and doc.sources[0].record_id.startswith("itr_"):
                primary_id = doc.sources[0].record_id
                aliases = [doc.id, primary_id] + [s.record_id for s in doc.sources]
                remapped_docs.append(replace(doc, id=DocumentId(primary_id, aliases=aliases)))
            else:
                remapped_docs.append(doc)
        self.documents = tuple(remapped_docs)
        self.documents_by_id = {}
        for document in self.documents:
            self.documents_by_id[document.id] = document
            if hasattr(document.id, "_aliases"):
                for alias in document.id._aliases:
                    self.documents_by_id[alias] = document
            self.documents_by_id[document.content_hash] = document
            if hasattr(document, "content_hash") and document.content_hash:
                self.documents_by_id[f"rag_{document.content_hash}"] = document
            for source in document.sources:
                self.documents_by_id[source.record_id] = document
        self.index = BM25Index(document_text(document) for document in self.documents)
        self.embedding_provider = embedding_provider
        self.vector_store = vector_store

    def search(
        self,
        query: str,
        *,
        category: str | None = None,
        domain: Domain | str | None = None,
        top_k: int | None = None,
    ) -> RetrievalResult:
        clean_query = " ".join((query or "").split())
        requested_top_k = self.config.final_top_k if top_k is None else top_k
        if requested_top_k < 1:
            raise ValueError("top_k must be positive")
        if not clean_query:
            return RetrievalResult(query=clean_query, hits=(), status="empty_query", searched_documents=0)


        resolved_domain: Domain = Domain.UNKNOWN
        if domain is not None:
            if isinstance(domain, Domain):
                resolved_domain = domain
            else:
                try:
                    resolved_domain = Domain(str(domain))
                except ValueError:
                    resolved_domain = classify_domain(clean_query)
        else:
            resolved_domain = classify_domain(clean_query)

        allowed_categories = get_allowed_rag_categories(resolved_domain, query=clean_query)
        is_pan_tds_query = (
            any(w in clean_query.lower() for w in ("inoperative", "206aa", "234h", "114aaa", "circular 03/2023", "circular 3/2023", "excess 20%", "20% tds", "salary tds"))
            and any(w in clean_query.lower() for w in ("pan", "aadhaar", "aadhar", "linking"))
        ) or ("inoperative pan" in clean_query.lower()) or ("206aa" in clean_query.lower())
        if is_pan_tds_query and resolved_domain in (Domain.TAXATION, "tax", "taxation", Domain.IDENTITY, "identity"):
            allowed_categories = {"tax", "pan", "civic"}
        elif category:
            allowed_categories = {category} if allowed_categories is None else (allowed_categories & {category})

        allowed_indices = None
        if allowed_categories is not None:
            allowed_indices = {
                idx for idx, doc in enumerate(self.documents)
                if doc.category in allowed_categories
            }

        lexical_hits = self.index.search(clean_query, top_k=self.config.lexical_top_k, allowed_indices=allowed_indices)
        candidates: dict[str, dict[str, float]] = {}
        lexical_ranks: dict[str, int] = {}
        q_terms = set(tokenize(clean_query))

        for rank, hit in enumerate(lexical_hits, 1):
            document = self.documents[hit.index]
            lexical_ranks[document.id] = rank
            signals = candidates.setdefault(document.id, {})
            signals["bm25_score"] = hit.score
            signals["lexical_rrf"] = 1 / (self.config.rrf_k + rank)

        # 2. Vector Search with Category Filtering
        if self.embedding_provider is not None and self.vector_store is not None:
            query_vector = self.embedding_provider.embed_texts((clean_query,))[0]
            vector_category = next(iter(allowed_categories)) if (allowed_categories and len(allowed_categories) == 1) else category
            for rank, hit in enumerate(
                self.vector_store.search(query_vector, top_k=self.config.vector_top_k, category=vector_category),
                1,
            ):
                if hit.document_id not in self.documents_by_id:
                    continue
                document = self.documents_by_id[hit.document_id]
                # Enforce domain namespace: discard vectors outside allowed categories
                if allowed_categories is not None and document.category not in allowed_categories:
                    continue
                signals = candidates.setdefault(document.id, {})
                signals["vector_score"] = hit.score
                signals["vector_rrf"] = 1 / (self.config.rrf_k + rank)

        _TROUBLE_TOKENS = {
            "failed", "fail", "failure", "fails", "stuck", "pending", "rejected", "rejection", "error",
            "cancelled", "cancel", "mismatch", "refund", "reissue", "delay", "delayed", "delays",
            "issue", "problem", "dispute", "ombudsman", "grievance", "escalate", "escalation",
            "deducted", "deduct", "debited", "debit", "srn", "arn", "adverse", "reversal",
            "exhausted", "limit", "crossed", "unpaid", "unvalidated", "correction", "defective",
            "tat", "overdue", "exceeded", "atki", "atke", "radd", "shikayat", "kat", "kata", "kaat",
            "unsolicited", "foreclosure", "prepayment", "cibil", "experian", "crif",
            "cheque", "passbook", "fvr", "blo", "aero", "ero",
            "nalsa", "edaakhil", "dcdrc", "scdrc", "ncdrc", "mbu",
            "condonation", "330",
        }
        is_trouble_query = bool(q_terms & _TROUBLE_TOKENS)

        # 3. Exact Domain Entities for Keyword Hijacking Suppression
        _PRIMARY_DOMAIN_ENTITIES = {
            "fastag", "nhai", "ihmcl", "vahan", "sarathi", "parivahan", "rc", "chassis", "challan", "echallan",
            "cbse", "marksheet", "digilocker", "pmkisan",
            "iepf", "iepfa", "udgam", "deaf", "epf", "epfo", "uan", "pfrda", "pension sahayak",
        }
        query_entities = {t for t in q_terms if t in _PRIMARY_DOMAIN_ENTITIES}

        is_epf_query = bool(re.search(r"\b(?:epfo?|epfigms|uan|provident\s+fund|joint\s+declaration|form\s+19|form\s+10c|form\s+31)\b", clean_query.lower()))
        is_iepf_query = bool(re.search(r"\b(?:iepf|iepfa|unclaimed\s+(?:shares?|dividends?)|unpaid\s+dividends?|iepf-?5[a-z]?|entitlement\s+letter)\b", clean_query.lower()))
        is_lpg_mopng_query = bool(
            re.search(r"\b(?:lpg|mopng|pahal|dbtl|indane|bharat\s*gas|hp\s*gas|cooking\s+gas|gas\s+cylinder)\b", clean_query.lower())
        ) and not is_epf_query and not is_iepf_query
        is_corporate_mca_query = bool(
            re.search(r"(?:\bspice\s*\+|\bspice\s+plus\b|\binc-\d+|\brule\s*8a\b|\bmca\b|\bmca21\b|\bllp\b|\bdir-\d+\b|\broc\b)", clean_query.lower())
        ) and not is_epf_query and not is_iepf_query
        is_nsp_query = bool(
            re.search(r"\b(?:nsp|national\s+scholarship|scholarship|scholarships)\b", clean_query.lower())
        ) and not is_epf_query and not re.search(r"\b(?:139\(9\)|income\s+tax|itr|defective\s+return)\b", clean_query.lower())

        fused: list[RetrievalHit] = []
        seen_doc_ids: set[str] = set()
        for document_id, signals in candidates.items():
            if document_id not in self.documents_by_id:
                continue
            document = self.documents_by_id[document_id]
            if document.id in seen_doc_ids:
                continue
            seen_doc_ids.add(document.id)
            # Commercial entity rejection (strictly eliminate commercial poisoning like legaltax.in)
            if any(
                any(c in (s.source_url or "").lower() for c in ("legaltax.in", "taxguru.in", "impriindia.com", "dbonline.in", "seconize.co"))
                for s in document.sources
            ):
                continue
            source_titles = " ".join(source.title for source in document.sources)
            lowered_doc = (document.text + " " + " ".join(document.tags)).lower()
            routing_text = f"{lowered_doc} {source_titles.lower()}"

            # Cross-domain bleed suppression for explicit non-EPF / non-Tax portals
            if is_lpg_mopng_query and not re.search(r"\b(?:lpg|mopng|pahal|dbtl|gas|cylinder|ujjwala)\b", routing_text):
                if re.search(r"\b(?:epfo?|epfigms|uan|provident\s+fund|eci|ngrs|voter\s+mitra|booth\s+level|sidbi|iepf|iepfa|digital\s+gujarat)\b", routing_text):
                    continue
            if is_corporate_mca_query and not re.search(r"(?:\bmca\b|\bmca21\b|\bspice\s*\+|\binc-\d+|\bllp\b|\bcompany\s+incorporation\b)", routing_text):
                if re.search(r"\b(?:epfo?|epfigms|uan|provident\s+fund|passbook|cheque\s+leaf|form\s+19|form\s+31|e-shram|joint\s+declaration)\b", routing_text):
                    continue
            if is_nsp_query and not re.search(r"\b(?:nsp|national\s+scholarship)\b", routing_text):
                if re.search(r"(?:139\(9\)|\bdefective\s+return\b|\bincome\s+tax\b|\be-?way\s+bill\b|\bepfo?\b|\bepfigms\b|\buan\b|\bprovident\s+fund\b|\bdigital\s+gujarat\b)", routing_text):
                    continue

            doc_tags = set(document.tags)
            metadata_overlap = len(q_terms & doc_tags) / max(len(q_terms), 1)
            signals["tag_overlap"] = metadata_overlap
            score = signals.get("lexical_rrf", 0.0) + signals.get("vector_rrf", 0.0) + min(metadata_overlap, 1.0) * 0.01

            # Deprioritize navigation and support-only pages for substantive procedure questions.
            if any(term in routing_text for term in ("contact us", "login page", "portal home", "home page", "official: home", "application mca services")):
                if not any(term in clean_query.lower() for term in ("contact", "phone", "email", "helpline", "login")):
                    score -= 0.18
                    signals["navigation_page_penalty"] = -0.18

            # A domestic new-PAN query must not default to foreign-applicant forms.
            is_new_pan_query = "pan" in clean_query.lower() and any(term in clean_query.lower() for term in ("new", "apply", "application"))
            if is_new_pan_query and not any(term in clean_query.lower() for term in ("foreign", "nri", "non-resident", "49aa")):
                if any(term in routing_text for term in ("foreign applicant", "foreign (form", "form 49aa", "form 95", "form 96")):
                    score -= 0.45
                    signals["foreign_pan_mismatch_penalty"] = -0.45

            # Filing an FIR is distinct from passport police-verification processing.
            is_fir_query = bool(re.search(r"\b(?:fir|first\s+information\s+report|police\s+complaint)\b", clean_query.lower()))
            if is_fir_query:
                if any(term in routing_text for term in ("passport seva", "police verification delay", "adverse police report")):
                    score -= 0.65
                    signals["passport_police_mismatch_penalty"] = -0.65
                if any(term in routing_text for term in ("first information report", "file an fir", "police complaint")):
                    score += 0.20
                    signals["fir_procedure_boost"] = 0.20

            # Anti-Keyword-Hijacking: if user specified key domain entities (FASTag, NHAI, CBSE, etc.)
            # penalize candidate chunks that lack the exact entity, preventing generic "refund" hijacking
            if query_entities:
                has_entity = any(
                    re.search(rf"\b{re.escape(ent)}\b", routing_text)
                    or (ent == "epf" and re.search(r"\bepfo\b", routing_text))
                    for ent in query_entities
                )
                if not has_entity:
                    score -= 0.60
                    signals["entity_mismatch_penalty"] = -0.60
                else:
                    score += 0.25
                    signals["exact_acronym_boost"] = 0.25

            # Exact statutory & error code boost: ensures statutory sections & error codes surface to rank 1
            _EXACT_CODES = (
                "148a(b)", "148a", "148", "149", "147", "151", "206aa", "114aaa", "234h",
                "138", "section 138", "142", "section 142", "143a", "section 143a", "141", "cheque bounce", "cheque dishonour",
                "blo", "e-epic", "epic", "form 8", "form 6", "form 7", "ngrs", "voter mitra",
                "139(9)", "139(5)", "139(4)", "119(2)(b)", "119", "234f", "44ad", "44ada", "defective return",
                "cibil", "experian", "crif", "unsolicited card", "card conduct",
                "edaakhil", "e-daakhil", "dcdrc", "scdrc", "ncdrc", "nalsa",
                "330", "error 330", "form 19", "form 10c", "form 49a", "joint declaration",
                "ais feedback", "annual information statement", "tis", "sft feedback", "sft",
                "iepf-5", "iepf-5e", "iepf", "iepfa", "udgam", "dea fund", "deaf", "entitlement letter", "pension sahayak",
            )
            for code in _EXACT_CODES:
                if re.search(rf"(?<!\w){re.escape(code)}(?!\w)", clean_query.lower()) and re.search(rf"(?<!\w){re.escape(code)}(?!\w)", lowered_doc):
                    score += 0.12
                    signals["exact_statutory_boost"] = 0.12
                    break

            # Synthetic Case Study suppression
            if "synthetic" in lowered_doc and "synthetic" not in clean_query.lower() and "case study" not in clean_query.lower():
                score -= 0.30
                signals["synthetic_penalty"] = -0.30

            # Troubleshooting boost: strictly scoped to the query's matching category and non-bleeding target
            allow_trouble_boost = True
            if is_lpg_mopng_query and not re.search(r"\b(?:lpg|mopng|pahal|dbtl|gas|cylinder|ujjwala)\b", routing_text):
                allow_trouble_boost = False
            elif is_corporate_mca_query and not re.search(r"(?:\bmca\b|\bmca21\b|\bspice\s*\+|\binc-\d+|\bllp\b|\bcompany\b)", routing_text):
                allow_trouble_boost = False
            elif is_nsp_query and not re.search(r"\b(?:nsp|national\s+scholarship)\b", routing_text):
                allow_trouble_boost = False
            if allow_trouble_boost and is_trouble_query and (allowed_categories is None or document.category in allowed_categories) and any(tag in doc_tags for tag in ("troubleshooting", "escalation", "sop", "manual")):
                score += 0.05
                signals["troubleshooting_boost"] = 0.05

            # Symptom-level cross-matching & anti-contamination suppression
            _SYMPTOM_CLUSTERS = (
                {
                    "name": "tax_reassessment",
                    "match": ("148a", "148", "reassessment", "149", "escaped income", "time-barred", "unexplained share", "3-year vs 10-year"),
                    "boost_terms": ("section 148a", "section 149", "reassessment", "escaped income", "limitation"),
                    "conflicts": ("139(9)", "defective return", "119(2)(b)", "condonation", "bank validation"),
                },
                {
                    "name": "inoperative_pan_tds",
                    "match": ("inoperative", "206aa", "234h", "114aaa", "circular 03/2023", "flat 20%", "excess 20% tds"),
                    "boost_terms": ("circular 03/2023", "rule 114aaa", "section 206aa", "section 234h", "reactivation", "30 days", "refund via itr"),
                    "conflicts": ("protean", "tin-nsdl", "paperless", "challan mismatch", "physical documentation"),
                },
                {
                    "name": "bank_validation",
                    "match": ("bank validation", "validation failed", "refund unpaid", "unvalidated", "re-validate", "pre-validation"),
                    "boost_terms": ("bank account pre-validation", "refund unpaid", "refund reissue"),
                    "conflicts": ("139(9)", "defective return", "119(2)(b)", "condonation"),
                },
                {
                    "name": "defective_return",
                    "match": ("defective return", "139(9)", "defective notice", "139(5)", "revised return", "defect memo"),
                    "boost_terms": ("defective return notice rectification", "cpc 2.0", "e-proceedings", "139(9)", "corrected schema"),
                    "conflicts": ("bank validation", "validation failed", "refund unpaid", "itr-4", "itr-6", "itr-5", "synthetic case study", "apex tar", "zenith", "ais feedback", "feedback on ais", "annual information statement", "sft feedback"),
                },
                {
                    "name": "ais_feedback",
                    "match": ("ais feedback", "feedback on ais", "annual information statement", "ais mismatch", "sft", "wrong transaction in ais", "tis", "taxpayer information summary"),
                    "boost_terms": ("annual information statement (ais) feedback", "sft feedback", "information is not fully correct", "information is denied", "information is duplicate", "derived value", "tis"),
                    "conflicts": ("139(9)", "defective return", "defective notice", "cpc 2.0 defect memo", "e-proceedings", "15 calendar days", "corrected schema", "section 139(9)"),
                },
                {
                    "name": "voter_blo_epic",
                    "match": ("blo", "epic", "e-epic", "voter id", "voter application", "form 8", "ngrs", "voters.eci"),
                    "boost_terms": ("eci voter services", "form 8", "field verification", "blo", "ngrs", "voter mitra"),
                    "conflicts": ("epfigms", "passbook", "cheque", "pf", "aadhaar", "pan", "tax"),
                },
                {
                    "name": "credit_card_dispute",
                    "match": ("credit card", "card fee", "card charges", "unsolicited card", "unsolicited cards", "card dispute", "arbitrary limit"),
                    "boost_terms": ("card conduct", "unsolicited cards", "arbitrary limit", "cms.rbi.org.in", "integrated ombudsman"),
                    "conflicts": ("foreclosure charges and prepayment penalties on home loans", "housing finance", "tax", "itr"),
                },
                {
                    "name": "consumer_court_jurisdiction",
                    "match": ("consumer court", "edaakhil", "represent myself", "district court", "district commission", "lawyer"),
                    "boost_terms": ("edaakhil", "consumer protection act 2019", "three-tier statutory pecuniary jurisdiction", "represent themselves in person", "district commission (dcdrc)"),
                    "conflicts": ("mobile esewa vans", "cyber security", "scertharyana"),
                },
                {
                    "name": "nalsa_legal_aid",
                    "match": ("nalsa", "free legal aid", "legal aid", "legal services authority", "section 12"),
                    "boost_terms": ("nalsa free legal aid framework", "section 12 categorical", "state income caps", "15100"),
                    "conflicts": ("consumer protection act", "epfo", "cyber security", "mobile esewa vans"),
                },
                {
                    "name": "aadhaar_pvc_payment",
                    "match": ("pvc", "payment deducted", "no srn", "srn not generated", "auto-reversal"),
                    "boost_terms": ("pvc card payment", "srn", "reconciliation"),
                    "conflicts": ("cross limit", "exception handling", "gazette notification", "regional office"),
                },
                {
                    "name": "aadhaar_cross_limit",
                    "match": ("cross limit", "cross-limit", "limit exhausted", "exception handling", "gazette"),
                    "boost_terms": ("cross limit", "exception handling", "demographic exception"),
                    "conflicts": ("pvc", "srn not generated", "auto-reversal"),
                },
                {
                    "name": "iepf_unclaimed_shares",
                    "match": ("iepf", "iepfa", "unclaimed share", "unclaimed shares", "unclaimed dividend", "unclaimed dividends", "iepf-5", "form iepf-5", "entitlement letter", "rta", "folio number", "unpaid dividend", "unpaid dividends"),
                    "boost_terms": ("iepf", "iepfa", "investor education and protection fund", "form iepf-5", "entitlement letter", "unclaimed dividend", "unclaimed shares", "company nodal officer", "verification report", "claimant"),
                    "conflicts": ("epfo", "epf", "uan", "provident fund", "e-shram", "utiitsl", "pan card", "form 19", "form 10c", "member profile", "passbook", "joint declaration"),
                },
                {
                    "name": "rbi_dea_fund_udgam",
                    "match": ("udgam", "dea fund", "deaf", "unclaimed deposit", "inoperative account", "10 years or more", "depositor education and awareness"),
                    "boost_terms": ("udgam", "dea fund", "depositor education and awareness fund", "unclaimed deposits", "reserve bank of india", "inoperative deposit", "claim form"),
                    "conflicts": ("iepf", "shares", "dividend", "epfo", "uan", "pan", "itr", "e-shram"),
                },
                {
                    "name": "epf_withdrawal",
                    "match": ("epf withdrawal", "withdraw epf", "withdraw my epf", "withdraw pf", "withdraw my pf", "epf advance", "form 19", "form 31", "online claim"),
                    "boost_terms": ("form 19", "form 31", "online claim", "withdrawal", "passbook", "cheque leaf", "claim"),
                    "conflicts": ("epfigms", "grievance", "escalation matrix", "stuck claim", "joint declaration", "member profile correction"),
                },
                {
                    "name": "cheque_bounce_138",
                    "match": ("138", "cheque bounce", "cheque dishonour", "dishonour of cheque", "section 138", "negotiable instruments", "142", "143a"),
                    "boost_terms": ("section 138", "negotiable instruments act 1881", "section 142", "statutory demand notice", "cheque dishonour", "15 days", "30 days", "judicial magistrate"),
                    "conflicts": ("harmonisation of turnaround time", "tat and customer compensation", "compensation for failed transactions", "foreclosure charges and prepayment penalties", "cpgrams", "atm transaction"),
                },
            )
            lowered_q = clean_query.lower()

            # Sub-procedure discrimination: Section 139(9) vs AIS feedback pre-check
            is_139_query = bool(re.search(r"(?:(?<!\w)139\(9\)(?!\w)|\bdefective\s+return\b|\bdefective\s+notice\b|\bdefect\s+memo\b)", lowered_q))
            is_ais_query = bool(
                re.search(r"\b(?:ais\s+feedback|feedback\s+on\s+ais|annual\s+information\s+statement|ais\s+mismatch)\b", lowered_q)
                or ("ais" in lowered_q and any(w in lowered_q for w in ("feedback", "sft", "mismatch", "discrepancy", "wrong", "duplicate", "statement")))
            )
            is_139_ais_comparison = is_139_query and is_ais_query

            has_symptom_boost = False
            for sc in _SYMPTOM_CLUSTERS:
                if any(re.search(rf"(?<!\w){re.escape(m)}(?!\w)", lowered_q) for m in sc["match"]):
                    has_boost = any(bt in lowered_doc for bt in sc["boost_terms"])
                    if has_boost and not has_symptom_boost:
                        score += 0.08
                        signals["symptom_boost"] = 0.08
                        has_symptom_boost = True
                    if any(c in lowered_doc for c in sc["conflicts"]) and not has_boost:
                        if is_139_ais_comparison and sc["name"] in ("defective_return", "ais_feedback"):
                            continue
                        penalty = -0.40 if sc["name"] in ("tax_reassessment", "inoperative_pan_tds") else -0.15
                        score += penalty
                        signals["contamination_penalty"] = penalty

            if is_139_query and not is_ais_query:
                if ("ais feedback" in lowered_doc or "sft feedback" in lowered_doc) and "cpc 2.0 defect memo" not in lowered_doc:
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40
            elif is_ais_query and not is_139_query:
                if ("139(9)" in lowered_doc or "defective return" in lowered_doc) and "ais feedback" not in lowered_doc and "sft feedback" not in lowered_doc:
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40

            # EPF withdrawal instructions must not be replaced by grievance escalation material.
            is_epf_withdrawal_query = bool(
                re.search(r"\bwithdraw(?:al)?\b.{0,20}\b(?:epf|pf|provident\s+fund)\b", lowered_q)
                or re.search(r"\b(?:epf|pf|provident\s+fund)\b.{0,20}\bwithdraw(?:al)?\b", lowered_q)
                or any(term in lowered_q for term in ("epf advance", "form 19", "form 31", "online claim"))
            )
            is_epf_problem_query = any(term in lowered_q for term in (
                "stuck", "pending", "delayed", "rejected", "grievance", "complaint", "escalate", "epfigms",
            ))
            if is_epf_withdrawal_query and not is_epf_problem_query:
                if any(term in lowered_doc for term in (
                    "epfigms grievance", "grievance redressal", "escalation matrix", "stuck epf claims",
                    "joint declaration", "member profile correction", "sop jointdeclarations",
                )):
                    score -= 0.65
                    signals["epf_subprocedure_mismatch_penalty"] = -0.65
                if any(term in lowered_doc for term in ("form 19", "form 31", "withdrawal claim", "online claim", "passbook and cheque leaf")):
                    score += 0.20
                    signals["epf_withdrawal_boost"] = 0.20

            # Sub-procedure discrimination: Reassessment vs Defective Return / Condonation
            is_reassess_query = bool(re.search(r"\b(?:148a|148|reassessment|escaped\s+income|time-barred|149)\b", lowered_q))
            if is_reassess_query and not is_139_query:
                if any(term in lowered_doc for term in ("139(9)", "defective return", "119(2)(b)", "condonation")) and not any(term in lowered_doc for term in ("148a", "section 148a", "section 149", "reassessment")):
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40

            # Sub-procedure discrimination: Inoperative PAN & TDS vs Protean Application Troubleshooting
            is_inop_tds_query = bool(re.search(r"\b(?:inoperative|206aa|234h|circular\s+03/2023|excess\s+20%|20%\s+tds)\b", lowered_q))
            if is_inop_tds_query:
                if any(term in lowered_doc for term in ("protean", "tin-nsdl", "paperless")) and not any(term in lowered_doc for term in ("circular 03/2023", "rule 114aaa", "206aa", "234h")):
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40

            # Sub-procedure discrimination: IEPF (investor shares/dividends) vs EPF/EPFO (provident fund)
            is_iepf_query = bool(re.search(r"\b(?:iepf|iepfa|unclaimed\s+(?:shares?|dividends?)|unpaid\s+dividends?|iepf-?5[a-z]?|entitlement\s+letter)\b", lowered_q))
            is_epf_query = bool(re.search(r"\b(?:epfo?|uan|provident\s+fund|joint\s+declaration|form\s+19|form\s+10c)\b", lowered_q))
            if is_iepf_query and not is_epf_query:
                if re.search(r"\b(?:epfo?|uan|provident\s+fund|joint\s+declaration|e-shram|utiitsl|tin-nsdl|form\s*49a)\b", lowered_doc):
                    score -= 0.80
                    signals["domain_conflict_penalty"] = -0.80
            elif is_epf_query and not is_iepf_query:
                if re.search(r"\b(?:iepf|iepfa|unclaimed\s+shares?|unclaimed\s+dividends?)\b", lowered_doc):
                    score -= 0.80
                    signals["domain_conflict_penalty"] = -0.80

            # Sub-procedure discrimination: RBI DEA Fund (unclaimed bank deposits) vs MCA IEPF (unclaimed shares/dividends)
            is_dea_query = bool(re.search(r"\b(?:dea\s+fund|deaf|udgam|unclaimed\s+deposits?)\b", lowered_q))
            if is_dea_query and not is_iepf_query:
                if re.search(r"\b(?:iepf|iepfa|unclaimed\s+shares?|unclaimed\s+dividends?|epfo?|uan)\b", lowered_doc):
                    score -= 0.80
                    signals["dea_conflict_penalty"] = -0.80
            elif is_iepf_query and not is_dea_query:
                if re.search(r"\b(?:dea\s+fund|deaf|depositor\s+education\s+and\s+awareness|inoperative\s+deposits?)\b", lowered_doc):
                    score -= 0.80
                    signals["iepf_dea_conflict_penalty"] = -0.80

            # Sub-procedure discrimination: NI Act Section 138 Cheque Bounce vs generic failed transaction / TAT / foreclosure
            is_138_query = bool(re.search(r"\b(?:138|cheque\s+bounce|cheque\s+dishonour|negotiable\s+instruments)\b", lowered_q))
            if is_138_query:
                if any(term in lowered_doc for term in ("harmonisation of turnaround time", "tat and customer compensation", "foreclosure charges", "cpgrams")) and "section 138" not in lowered_doc:
                    score -= 0.60
                    signals["sub_procedure_mismatch_penalty"] = -0.60
                if any(term in lowered_doc for term in ("section 138", "negotiable instruments act 1881", "cheque dishonour")):
                    score += 0.20
                    signals["cheque_bounce_boost"] = 0.20

            fused.append(
                RetrievalHit(
                    document=document,
                    score=score,
                    rank=lexical_ranks.get(document.id, self.config.vector_top_k + 1),
                    signals=signals,
                )
            )

        fused.sort(key=lambda result: (-result.score, result.rank, result.document.id))
        final = tuple(fused[:requested_top_k])
        mode = "hybrid" if self.embedding_provider is not None else "lexical"
        return RetrievalResult(
            query=clean_query,
            hits=final,
            status=f"supported_{mode}" if final else "insufficient",
            searched_documents=len(allowed_indices) if allowed_indices is not None else len(self.documents),
        )


def search(query: str, *, category: str | None = None, domain: Domain | str | None = None, top_k: int = 8) -> RetrievalResult:
    return RagRetriever().search(query, category=category, domain=domain, top_k=top_k)


__all__ = ["RagRetriever", "RetrieverConfig", "decompose_query", "document_text", "search"]
