from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .drive import upload_accepted_pdfs
from .http import PublicHttpClient
from .models import AcceptedItem, Candidate
from .pdf import download_public_pdf, extract_pdf_text
from .redact import redact_sensitive
from .storage import Storage


def _candidate_from_accepted(item: AcceptedItem) -> Candidate:
    return Candidate(
        source=item.source,
        title=item.title,
        abstract=item.abstract_or_title if item.document_type == "academic_paper" else "",
        canonical_url=item.canonical_url,
        document_type=item.document_type,
        pdf_url=item.pdf_url,
        stable_id=item.stable_id,
        doi=item.doi,
        authors=item.authors,
        published_at=item.published_at,
        updated_at=item.updated_at,
        is_open_access=item.is_open_access,
        license=item.license,
    )


def resolve_accepted_pdfs(
    project_root: Path,
    config: dict[str, Any],
    day: str,
    *,
    sync_drive: bool = True,
    resolver_only: bool = False,
) -> dict[str, Any]:
    storage = Storage(project_root)
    client = PublicHttpClient()
    manifest = storage.data / "accepted" / f"{day}.json"
    try:
        if not manifest.exists():
            return {"date": day, "status": "accepted_manifest_not_found"}
        payload = json.loads(manifest.read_text(encoding="utf-8"))
        items = [AcceptedItem(**row) for row in payload.get("items", [])]
        missing = [item for item in items if not item.local_pdf_path]
        recovered: list[AcceptedItem] = []
        results: list[dict[str, Any]] = []

        for item in missing:
            candidate = _candidate_from_accepted(item)
            try:
                content, resolved_url, status = download_public_pdf(
                    client,
                    candidate,
                    config["download_max_bytes"],
                    oa_config=config.get("public_pdf_resolution"),
                    resolver_only=resolver_only,
                )
                item.download_status = status
                if content:
                    try:
                        extracted = extract_pdf_text(content)
                    except Exception as exc:
                        extracted = ""
                        item.download_status = f"downloaded_text_extraction_failed: {redact_sensitive(exc)}"
                    local_path, content_hash = storage.save_pdf(day, candidate, content)
                    item.pdf_url = resolved_url or item.pdf_url
                    item.local_pdf_path = local_path
                    item.content_sha256 = content_hash
                    item.pdf_text_chars = len(extracted)
                    storage.persist_item(candidate, item)
                    recovered.append(item)
                else:
                    storage.persist_item(candidate, item)
                results.append({
                    "title": item.title,
                    "doi": item.doi,
                    "status": item.download_status,
                    "pdf_url": item.pdf_url,
                    "local_pdf_path": item.local_pdf_path,
                })
            except Exception as exc:
                results.append({
                    "title": item.title,
                    "doi": item.doi,
                    "status": f"resolution_error: {redact_sensitive(exc)}",
                    "pdf_url": item.pdf_url,
                    "local_pdf_path": None,
                })

        accepted_path, reading_path = storage.write_manifests(day, items)
        drive_status: dict[str, Any] | str = "disabled"
        if sync_drive and config.get("drive", {}).get("enabled") and recovered:
            try:
                drive_status = upload_accepted_pdfs(day, recovered, config["drive"])
            except Exception as exc:
                drive_status = {"status": "failed", "error": redact_sensitive(exc)}

        report = {
            "date": day,
            "status": "completed",
            "attempted": len(missing),
            "recovered": len(recovered),
            "still_unavailable": len(missing) - len(recovered),
            "resolver_only": resolver_only,
            "drive_status": drive_status,
            "accepted_manifest": str(accepted_path),
            "reading_manifest": str(reading_path),
            "items": results,
        }
        report_path = storage.write_pdf_resolution_report(day, report)
        report["pdf_resolution_report"] = str(report_path)
        return report
    finally:
        client.close()
        storage.close()
