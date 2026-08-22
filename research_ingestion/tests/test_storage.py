import json

from research_ingestion.models import AcceptedItem, Candidate
from research_ingestion.storage import Storage


def test_storage_deduplicates_and_writes_reading_manifest(tmp_path):
    storage = Storage(tmp_path)
    candidate = Candidate(source="arXiv", title="A paper", canonical_url="https://x", doi="10.1/test")
    item = AcceptedItem(
        source="arXiv", title="A paper", abstract_or_title="Abstract", document_type="academic_paper",
        canonical_url="https://x", pdf_url=None, local_pdf_path=None, doi="10.1/test", stable_id=None,
        authors=[], published_at="2026-08-13", updated_at=None, retrieved_at="2026-08-14T00:00:00Z",
        is_open_access=True, license=None, topics=["market_microstructure"], relevance_score=0.9,
        relevance_reason="relevant", ai_status="classified", content_sha256=None, pdf_text_chars=0,
        download_status="title_link_only",
    )
    storage.persist_item(candidate, item)
    assert storage.contains(candidate)
    _, reading = storage.write_manifests("2026-08-13", [item])
    payload = json.loads(reading.read_text(encoding="utf-8"))
    assert payload["items"][0]["abstract_or_title"] == "Abstract"
    rejected = storage.write_rejected_manifest("2026-08-13", [{
        "rejection_stage": "deterministic_quality",
        "title": "Rejected paper",
        "rejection_reason": "Score below minimum.",
    }])
    rejected_payload = json.loads(rejected.read_text(encoding="utf-8"))
    assert rejected_payload["rejected_count"] == 1
    assert rejected_payload["items"][0]["rejection_stage"] == "deterministic_quality"
    storage.close()
