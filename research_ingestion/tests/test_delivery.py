import datetime as dt
import json

from research_ingestion.delivery import retry_failed_deliveries
from research_ingestion.models import AcceptedItem
from research_ingestion.storage import Storage


def test_retry_delivery_uses_saved_manifest_and_updates_run_report(monkeypatch, tmp_path):
    day = dt.date.today().isoformat()
    item = AcceptedItem(
        source="SSRN", title="Paper", abstract_or_title="Abstract",
        document_type="academic_paper", canonical_url="https://example.test",
        pdf_url=None, local_pdf_path=None, doi=None, stable_id="paper", authors=[],
        published_at=day, updated_at=None, retrieved_at=f"{day}T00:00:00Z",
        is_open_access=None, license=None, topics=[], relevance_score=0.9,
        relevance_reason="Relevant", ai_status="classified", content_sha256=None,
        pdf_text_chars=0, download_status="title_link_only",
    )
    storage = Storage(tmp_path)
    storage.write_manifests(day, [item])
    storage.write_run_report(day, {
        "date": day, "status": "completed", "email_status": "failed: expired",
        "drive_status": {"status": "failed", "error": "expired"}, "warnings": [],
    })
    storage.close()
    calls = []
    monkeypatch.setattr(
        "research_ingestion.delivery.send_digest",
        lambda *_args, **_kwargs: calls.append("email") or "smtp_sent",
    )
    monkeypatch.setattr(
        "research_ingestion.delivery.upload_accepted_pdfs",
        lambda *_args, **_kwargs: calls.append("drive") or {"status": "completed"},
    )
    config = {
        "email_recipients": ["reader@example.test"], "email_top_n": 25,
        "email": {}, "drive": {},
    }

    result = retry_failed_deliveries(tmp_path, config)

    assert result["status"] == "completed"
    assert calls == ["drive", "email"]
    report = json.loads((tmp_path / "data/runs" / f"{day}.json").read_text(encoding="utf-8"))
    assert report["email_status"] == "smtp_sent"
    assert report["drive_status"]["status"] == "completed"
