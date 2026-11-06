"""Hybrid lexical and vector retrieval over the canonical corpus."""
from __future__ import annotations

import re
from dataclasses import dataclass, replace

from backend.modules.domain_router import Domain, classify_domain, get_allowed_rag_categories
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

        # 1. Hard Domain Routing Short-Circuit for Uncovered Domains
        # Evaluate unconditionally on the query text to prevent caller-passed domain argument bypass.
        if classify_domain(clean_query) == Domain.UNCOVERED or domain in (Domain.UNCOVERED, "uncovered"):
            return RetrievalResult(
                query=clean_query,
                hits=(),
                status="uncovered_domain",
                searched_documents=0,
            )

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

        allowed_categories = get_allowed_rag_categories(resolved_domain)
        if category:
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
            "cbse", "marksheet", "digilocker", "pmkisan"
        }
        query_entities = {t for t in q_terms if t in _PRIMARY_DOMAIN_ENTITIES}

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
            doc_tags = set(document.tags)
            metadata_overlap = len(q_terms & doc_tags) / max(len(q_terms), 1)
            signals["tag_overlap"] = metadata_overlap
            score = signals.get("lexical_rrf", 0.0) + signals.get("vector_rrf", 0.0) + min(metadata_overlap, 1.0) * 0.01

            lowered_doc = (document.text + " " + " ".join(document.tags)).lower()

            # Anti-Keyword-Hijacking: if user specified key domain entities (FASTag, NHAI, CBSE, etc.)
            # penalize candidate chunks that lack the exact entity, preventing generic "refund" hijacking
            if query_entities:
                has_entity = any(re.search(rf"\b{re.escape(ent)}\b", lowered_doc) for ent in query_entities)
                if not has_entity:
                    score -= 0.60
                    signals["entity_mismatch_penalty"] = -0.60
                else:
                    score += 0.25
                    signals["exact_acronym_boost"] = 0.25

            # Exact statutory & error code boost: ensures statutory sections & error codes surface to rank 1
            _EXACT_CODES = (
                "blo", "e-epic", "epic", "form 8", "form 6", "form 7", "ngrs", "voter mitra",
                "139(9)", "139(5)", "139(4)", "119(2)(b)", "119", "234f", "44ad", "44ada",
                "cibil", "experian", "crif", "unsolicited card", "card conduct",
                "edaakhil", "e-daakhil", "dcdrc", "scdrc", "ncdrc", "nalsa",
                "330", "error 330", "form 19", "form 10c", "form 49a", "joint declaration",
                "ais feedback", "annual information statement", "tis", "sft feedback", "sft",
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

            # Troubleshooting boost: strictly scoped to the query's matching category
            if is_trouble_query and (allowed_categories is None or document.category in allowed_categories) and any(tag in doc_tags for tag in ("troubleshooting", "escalation", "sop", "manual")):
                score += 0.05
                signals["troubleshooting_boost"] = 0.05

            # Symptom-level cross-matching & anti-contamination suppression
            _SYMPTOM_CLUSTERS = (
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
                    "match": ("credit card", "card fee", "card charges", "unsolicited card", "card dispute", "arbitrary limit"),
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
                    "match": ("cross limit", "limit exhausted", "exception handling", "gazette"),
                    "boost_terms": ("cross limit", "exception handling", "demographic exception"),
                    "conflicts": ("pvc", "srn not generated", "auto-reversal"),
                },
            )
            lowered_q = clean_query.lower()
            for sc in _SYMPTOM_CLUSTERS:
                if any(m in lowered_q for m in sc["match"]):
                    has_boost = any(bt in lowered_doc for bt in sc["boost_terms"])
                    if has_boost:
                        score += 0.08
                        signals["symptom_boost"] = 0.08
                    if any(c in lowered_doc for c in sc["conflicts"]) and not has_boost:
                        score -= 0.15
                        signals["contamination_penalty"] = -0.15

            # Sub-procedure discrimination: Section 139(9) vs AIS feedback
            is_139_query = bool(re.search(r"\b(?:139\(9\)|defective\s+return|defective\s+notice|defect\s+memo)\b", lowered_q))
            is_ais_query = bool(
                re.search(r"\b(?:ais\s+feedback|feedback\s+on\s+ais|annual\s+information\s+statement|ais\s+mismatch)\b", lowered_q)
                or ("ais" in lowered_q and any(w in lowered_q for w in ("feedback", "sft", "mismatch", "discrepancy", "wrong", "duplicate", "statement")))
            )

            if is_139_query and not is_ais_query:
                if ("ais feedback" in lowered_doc or "sft feedback" in lowered_doc) and "cpc 2.0 defect memo" not in lowered_doc:
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40
            elif is_ais_query and not is_139_query:
                if ("139(9)" in lowered_doc or "defective return" in lowered_doc) and "ais feedback" not in lowered_doc and "sft feedback" not in lowered_doc:
                    score -= 0.40
                    signals["sub_procedure_mismatch_penalty"] = -0.40

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


__all__ = ["RagRetriever", "RetrieverConfig", "document_text", "search"]
