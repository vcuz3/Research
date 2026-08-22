import json

from research_ingestion.backfill import resolve_accepted_pdfs
from research_ingestion.models import AcceptedItem
from research_ingestion.storage import Storage


def test_pdf_backfill_updates_manifest_and_writes_separate_report(monkeypatch, tmp_path):
    storage = Storage(tmp_path)
    item = AcceptedItem(
        source="Crossref", title="Paper", abstract_or_title="Abstract", document_type="academic_paper",
        canonical_url="https://doi.org/10.1/test", pdf_url=None, local_pdf_path=None, doi="10.1/test",
        stable_id=None, authors=[], published_at="2026-08-15", updated_at=None,
        retrieved_at="2026-08-16T00:00:00Z", is_open_access=None, license=None,
        topics=["strategy"], relevance_score=0.9, relevance_reason="Relevant", ai_status="classified",
        content_sha256=None, pdf_text_chars=0, download_status="title_link_only",
    )
    storage.write_manifests("2026-08-15", [item])
    storage.close()
    monkeypatch.setattr(
        "research_ingestion.backfill.download_public_pdf",
        lambda *_args, **_kwargs: (b"%PDF-1.7 fixture", "https://repository.test/paper.pdf", "downloaded_open_access_resolver"),
    )
    monkeypatch.setattr("research_ingestion.backfill.extract_pdf_text", lambda _content: "extracted text")

    report = resolve_accepted_pdfs(
        tmp_path,
        {"download_max_bytes": 1_000_000, "public_pdf_resolution": {"enabled": True}, "drive": {"enabled": False}},
        "2026-08-15",
        sync_drive=False,
        resolver_only=True,
    )

    assert report["attempted"] == 1
    assert report["recovered"] == 1
    assert report["resolver_only"] is True
    manifest = json.loads((tmp_path / "data" / "accepted" / "2026-08-15.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["local_pdf_path"]
    assert manifest["items"][0]["download_status"] == "downloaded_open_access_resolver"
    audit = json.loads((tmp_path / "data" / "pdf_resolution" / "2026-08-15.json").read_text(encoding="utf-8"))
    assert audit["recovered"] == 1
