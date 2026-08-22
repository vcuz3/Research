import json
import hashlib

from research_ingestion.models import AcceptedItem
from research_ingestion.pdf_import import PdfInspection, import_pdf_inbox
from research_ingestion.storage import Storage


def _accepted():
    return AcceptedItem(
        source="SSRN", title="Screening for Mean Reversion in Statistical Arbitrage",
        abstract_or_title="Abstract", document_type="academic_paper",
        canonical_url="https://doi.org/10.2139/ssrn.7313738", pdf_url=None,
        local_pdf_path=None, doi="10.2139/ssrn.7313738",
        stable_id="doi:10.2139/ssrn.7313738", authors=[], published_at="2026-08-20",
        updated_at=None, retrieved_at="2026-08-20T00:00:00Z", is_open_access=True,
        license=None, topics=["mean_reversion"], relevance_score=0.9,
        relevance_reason="Relevant", ai_status="classified", content_sha256=None,
        pdf_text_chars=0, download_status="title_link_only",
    )


def test_pdf_inbox_import_matches_identifier_updates_manifests_and_uploads(monkeypatch, tmp_path):
    storage = Storage(tmp_path)
    storage.write_manifests("2026-08-20", [_accepted()])
    storage.close()
    inbox = tmp_path / "pdf_downloads"
    inbox.mkdir()
    source = inbox / "ssrn-7313738.pdf"
    source.write_bytes(b"%PDF fixture")
    content_hash = hashlib.sha256(b"%PDF fixture").hexdigest()
    monkeypatch.setattr(
        "research_ingestion.pdf_import._inspect_pdf",
        lambda *_args: PdfInspection(
            content=b"%PDF fixture", content_sha256=content_hash, metadata_title="",
            first_pages_text="Screening for Mean Reversion in Statistical Arbitrage",
            page_count=12, identifiers={"ssrn.7313738"},
        ),
    )
    uploads = []
    monkeypatch.setattr(
        "research_ingestion.pdf_import.upload_accepted_pdfs",
        lambda day, items, _config: uploads.append((day, items[0].title)) or {"status": "completed"},
    )

    report = import_pdf_inbox(
        tmp_path,
        {"download_max_bytes": 1000, "drive": {"enabled": True}},
        sync_drive=True,
    )

    assert report["imported"] == 1
    assert report["items"][0]["match_method"] == "identifier_and_title"
    assert uploads == [("2026-08-20", "Screening for Mean Reversion in Statistical Arbitrage")]
    manifest = json.loads((tmp_path / "data/accepted/2026-08-20.json").read_text(encoding="utf-8"))
    assert manifest["items"][0]["content_sha256"] == content_hash
    assert manifest["items"][0]["download_status"] == "imported_from_pdf_downloads"
    assert source.read_bytes() == b"%PDF fixture"


def test_pdf_inbox_leaves_unmatched_file_untouched(monkeypatch, tmp_path):
    storage = Storage(tmp_path)
    storage.write_manifests("2026-08-20", [_accepted()])
    storage.close()
    inbox = tmp_path / "pdf_downloads"
    inbox.mkdir()
    source = inbox / "unknown.pdf"
    source.write_bytes(b"%PDF unknown")
    monkeypatch.setattr(
        "research_ingestion.pdf_import._inspect_pdf",
        lambda *_args: PdfInspection(
            content=b"%PDF unknown", content_sha256="b" * 64, metadata_title="Other paper",
            first_pages_text="Completely unrelated", page_count=1, identifiers=set(),
        ),
    )

    report = import_pdf_inbox(tmp_path, {"drive": {"enabled": False}}, sync_drive=False)

    assert report["imported"] == 0
    assert report["items"][0]["status"] == "unmatched_or_ambiguous"
    assert source.exists()
