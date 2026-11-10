"""Adversarial Verification Suite for EPFO Corpus Remediation and Vector DB Integrity (Milestone 1, R1).

Executed by challenger_m1_2 to empirically stress-test:
1. Vector database configuration, point count, dimensionality, distance metric, and hash parity.
2. Retrieval accuracy and ranking of EPFO passbook and cheque validation standards.
3. Cross-domain bleed resistance against corporate (MCA / SPICe+) queries.
4. Parity and retrieval performance across all EPFO SOP documents in the civic corpus.
"""
import json
import pytest
from pathlib import Path
from qdrant_client import QdrantClient
from qdrant_client.http.models import Distance

from backend.config import DATA_DIR
from backend.offline.ensure_vector_db import inspect_vector_index
from backend.rag.loader import DEFAULT_MANIFEST, load_corpus
from backend.rag.retriever import RagRetriever
from backend.rag.runtime import get_retriever, rag_health
from backend.rag.vector_store import QdrantLocalVectorStore, read_index_metadata


EXPECTED_POINTS = 4046
EXPECTED_DIMENSIONS = 384
EXPECTED_DISTANCE = Distance.COSINE
EXPECTED_COLLECTION = "govbank_chunks"
EXPECTED_EPFO_CIRCULAR_URL = (
    "https://www.epfindia.gov.in/site_docs/PDFs/Circulars/Y2024-2025/WSU_IssueOfBKG_49885_16.pdf"
)
VECTOR_DIR = DATA_DIR / "vector_index" / "qdrant"


class TestVectorDatabaseIntegrity:
    """Adversarial stress-testing of Qdrant embedded collection parameters and metadata."""

    def test_qdrant_collection_parameters_and_distance_metric(self):
        """Verify directly with Qdrant client that collection geometry is exact."""
        retriever = get_retriever()
        client = None
        own_client = False
        if retriever.vector_store and hasattr(retriever.vector_store, "client"):
            client = retriever.vector_store.client
        elif retriever.vector_store and hasattr(retriever.vector_store, "_client"):
            client = retriever.vector_store._client
        else:
            client = QdrantClient(path=str(VECTOR_DIR), force_disable_check_same_thread=True)
            own_client = True
        try:
            info = client.get_collection(EXPECTED_COLLECTION)
            assert info.points_count == EXPECTED_POINTS, (
                f"Expected {EXPECTED_POINTS} points, found {info.points_count}"
            )
            assert info.config.params.vectors.size == EXPECTED_DIMENSIONS, (
                f"Expected vector dim {EXPECTED_DIMENSIONS}, found {info.config.params.vectors.size}"
            )
            assert info.config.params.vectors.distance == EXPECTED_DISTANCE, (
                f"Expected distance metric {EXPECTED_DISTANCE}, found {info.config.params.vectors.distance}"
            )
        finally:
            if own_client and client is not None:
                client.close()

    def test_vector_metadata_and_corpus_checksum_sync(self):
        """Verify that index metadata accurately reflects the current canonical corpus."""
        metadata = read_index_metadata(VECTOR_DIR)
        assert metadata is not None, "Metadata file meta.json or govbank_index.json missing"
        assert metadata["collection"] == EXPECTED_COLLECTION
        assert metadata["documents"] == EXPECTED_POINTS
        assert metadata["dimensions"] == EXPECTED_DIMENSIONS

        corpus = load_corpus(DEFAULT_MANIFEST)
        assert len(corpus.documents) == EXPECTED_POINTS
        assert metadata["corpus_sha256"] == corpus.report.corpus_sha256

    def test_ensure_vector_db_readiness_check(self):
        """Ensure inspect_vector_index returns ready=True without rebuilding."""
        report = inspect_vector_index(dest_dir=VECTOR_DIR)
        assert report["ready"] is True
        assert report["points"] == EXPECTED_POINTS
        assert report["dimensions"] == EXPECTED_DIMENSIONS
        assert report["reason"] == "ready"


@pytest.fixture(scope="module")
def civic_records():
    civic_path = DATA_DIR / "refined" / "troubleshooting" / "troubleshooting_civic.jsonl"
    records = {}
    with open(civic_path, "r", encoding="utf-8") as f:
        for line in f:
            if line.strip():
                item = json.loads(line)
                records[item["id"]] = item
    return records


@pytest.fixture(scope="module")
def hybrid_retriever():
    import os
    os.environ["RAG_ENABLED"] = "1"
    os.environ["RAG_VECTOR_ENABLED"] = "1"
    retriever = get_retriever()
    yield retriever
    if retriever.vector_store:
        retriever.vector_store.close()


class TestEpfoCorpusDocumentIntegrity:
    """Verify EPFO records in refined civic dataset are authentic official circulars."""

    def test_epfo_passbook_cheque_document_attributes(self, civic_records):
        """Verify epfo_claim_passbook_cheque_standards_01 has authentic official circular URL and tags."""
        doc = civic_records.get("epfo_claim_passbook_cheque_standards_01")
        assert doc is not None, "Record epfo_claim_passbook_cheque_standards_01 missing from civic JSONL"
        assert doc["source_url"] == EXPECTED_EPFO_CIRCULAR_URL
        assert "epfindia.gov.in" in doc["source_url"]
        assert "pmvbry-cdn" not in doc["source_url"]
        assert "Manual_for_Inspector" not in doc["source_url"]
        assert doc["status"] == "automated_verified"
        assert doc["source_confidence"] == "official"
        assert "sop" in doc["retrieval_tags"]
        assert "epf_claim_rejected" in doc["retrieval_tags"]
        assert "epf_bank_kyc" in doc["retrieval_tags"]
        assert "manual" not in doc["retrieval_tags"]

    def test_epfo_documents_manifest_host_allowlist(self):
        """Verify manifest allowlists www.epfindia.gov.in for troubleshooting_civic dataset."""
        with open(DEFAULT_MANIFEST, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        civic_spec = next((d for d in manifest["datasets"] if d["id"] == "troubleshooting_civic"), None)
        assert civic_spec is not None
        assert "www.epfindia.gov.in" in civic_spec["allowed_hosts"]
        assert "epfindia.gov.in" in civic_spec["allowed_hosts"]


class TestEpfoHybridRetrievalAndBleedResistance:
    """Stress-test hybrid vector and lexical retrieval on EPFO queries and bleed queries."""

    @pytest.mark.parametrize(
        "query,expected_record_id",
        [
            ("pre-printed name missing on cheque Form 19 rejection", "epfo_claim_passbook_cheque_standards_01"),
            ("EPFO Form 19 rejection cancelled cheque stamp", "epfo_claim_passbook_cheque_standards_01"),
            ("Why was my EPF claim rejected due to cancelled cheque leaf?", "epfo_claim_passbook_cheque_standards_01"),
            ("cancelled cheque leaf without pre-printed name EPF claim rejected", "epfo_claim_passbook_cheque_standards_01"),
            ("passbook not attested bank manager stamp EPFO Form 31", "epfo_claim_passbook_cheque_standards_01"),
            ("epfo cancelled cheque me naam nahi hai claim reject ho gaya", "epfo_claim_passbook_cheque_standards_01"),
            ("establishment closed company shut down employer untraceable Joint Declaration", "epfo_closed_establishment_attestation_01"),
            ("bank manager attestation closed establishment RPFC physical joint declaration", "epfo_closed_establishment_attestation_01"),
            ("EPFO Joint Declaration minor major modifications name date of birth correction Annexure-I", "epfo_joint_declaration_minor_major_sop_01"),
        ],
    )
    def test_epfo_queries_retrieve_expected_document_at_rank_1(self, hybrid_retriever, query, expected_record_id):
        """Adversarial Challenge: Cheque and passbook queries must retrieve the remediated SOP at Rank 1."""
        res = hybrid_retriever.search(query, top_k=5)
        assert res.hits, f"No hits retrieved for query: {query}"
        top_hit = res.hits[0]
        top_record_ids = [s.record_id for s in top_hit.document.sources]
        assert expected_record_id in top_record_ids, (
            f"Query '{query}' expected rank 1 '{expected_record_id}', got '{top_record_ids}' (score={top_hit.score})"
        )
        assert top_hit.score > 0.05, f"Score too low: {top_hit.score}"

    @pytest.mark.parametrize(
        "bleed_query",
        [
            "SPICe+ Part A Rule 8A corporate name reservation guidelines",
            "MCA SPICe+ company incorporation name approval criteria",
            "Ministry of Corporate Affairs name reservation objection Rule 8",
            "petroleum LPG subsidy direct benefit transfer DBTL ujjwala",
            "NSP national scholarship portal verification institute nodal officer",
        ],
    )
    def test_cross_domain_bleed_resistance(self, hybrid_retriever, bleed_query):
        """Adversarial Challenge: Unrelated corporate or subsidy queries must NOT retrieve epfo_claim_passbook_cheque_standards_01."""
        res = hybrid_retriever.search(bleed_query, top_k=5)
        for rank, hit in enumerate(res.hits):
            retrieved_records = [s.record_id for s in hit.document.sources]
            assert "epfo_claim_passbook_cheque_standards_01" not in retrieved_records, (
                f"Bleed detected! Record epfo_claim_passbook_cheque_standards_01 retrieved at rank {rank+1} for query '{bleed_query}'"
            )
