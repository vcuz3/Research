from __future__ import annotations

import datetime as dt
import hashlib
import io
import json
import re
import unicodedata
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Any

from pypdf import PdfReader

from .drive import upload_accepted_pdfs
from .models import AcceptedItem, Candidate
from .redact import redact_sensitive
from .storage import Storage


SSRN_ID_RE = re.compile(r"(?:10\.2139/)?ssrn[.\s_-]?(\d{5,})", re.IGNORECASE)
DOI_RE = re.compile(r"10\.\d{4,9}/[-._;()/:a-z0-9]+", re.IGNORECASE)


@dataclass
class PdfInspection:
    content: bytes
    content_sha256: str
    metadata_title: str
    first_pages_text: str
    page_count: int
    identifiers: set[str]


def _normalise_title(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value).casefold()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", decomposed).split())


def _identifiers(value: str) -> set[str]:
    found = {match.group(0).rstrip(".,;)").casefold() for match in DOI_RE.finditer(value)}
    found.update(f"ssrn.{match.group(1)}" for match in SSRN_ID_RE.finditer(value))
    return found


def _item_identifiers(item: AcceptedItem) -> set[str]:
    values = " ".join(filter(None, (item.doi, item.stable_id, item.canonical_url)))
    return _identifiers(values)


def _inspect_pdf(path: Path, max_bytes: int, max_pages: int = 3) -> PdfInspection:
    size = path.stat().st_size
    if size <= 0:
        raise ValueError("empty file")
    if size > max_bytes:
        raise ValueError(f"file exceeds configured {max_bytes}-byte limit")
    content = path.read_bytes()
    if not content.startswith(b"%PDF"):
        raise ValueError("file does not have a PDF signature")
    reader = PdfReader(io.BytesIO(content))
    if reader.is_encrypted and reader.decrypt("") == 0:
        raise ValueError("encrypted PDF cannot be read")
    metadata_title = str((reader.metadata or {}).get("/Title") or "").strip()
    first_pages_text = "\n".join(
        page.extract_text() or "" for page in reader.pages[:max_pages]
    )
    if not reader.pages:
        raise ValueError("PDF contains no pages")
    identifier_text = f"{path.name}\n{metadata_title}\n{first_pages_text}"
    return PdfInspection(
        content=content,
        content_sha256=hashlib.sha256(content).hexdigest(),
        metadata_title=metadata_title,
        first_pages_text=first_pages_text,
        page_count=len(reader.pages),
        identifiers=_identifiers(identifier_text),
    )


def _match_pdf(
    inspection: PdfInspection,
    accepted: list[tuple[str, AcceptedItem]],
) -> tuple[str, AcceptedItem, str] | None:
    searchable = _normalise_title(
        f"{inspection.metadata_title} {inspection.first_pages_text}"
    )
    identifier_matches = [
        (day, item) for day, item in accepted
        if inspection.identifiers & _item_identifiers(item)
    ]
    if len(identifier_matches) == 1:
        day, item = identifier_matches[0]
        title = _normalise_title(item.title)
        if len(title) >= 20 and title in searchable:
            return day, item, "identifier_and_title"
        return None
    if len(identifier_matches) > 1:
        return None

    title_matches = [
        (day, item) for day, item in accepted
        if len(_normalise_title(item.title)) >= 20
        and _normalise_title(item.title) in searchable
    ]
    if len(title_matches) == 1:
        day, item = title_matches[0]
        return day, item, "title"
    return None


def _candidate(item: AcceptedItem) -> Candidate:
    return Candidate(
        source=item.source,
        title=item.title,
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


def import_pdf_inbox(
    project_root: Path,
    config: dict[str, Any],
    *,
    inbox: Path | None = None,
    sync_drive: bool = True,
) -> dict[str, Any]:
    started_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    import_config = config.get("pdf_import", {})
    if import_config.get("enabled", True) is False:
        return {
            "started_at": started_at,
            "status": "disabled",
            "pdf_files": 0,
            "imported": 0,
            "already_imported": 0,
            "unresolved": 0,
        }
    configured = inbox or Path(import_config.get("folder", "pdf_downloads"))
    inbox_path = configured if configured.is_absolute() else project_root / configured
    inbox_path.mkdir(parents=True, exist_ok=True)
    storage = Storage(project_root)
    results: list[dict[str, Any]] = []
    manifests: dict[str, tuple[Path, list[AcceptedItem]]] = {}
    accepted: list[tuple[str, AcceptedItem]] = []

    try:
        for manifest in sorted((storage.data / "accepted").glob("*.json")):
            payload = json.loads(manifest.read_text(encoding="utf-8"))
            day = str(payload.get("date") or manifest.stem)
            items = [AcceptedItem(**row) for row in payload.get("items", [])]
            manifests[day] = (manifest, items)
            accepted.extend((day, item) for item in items)

        changed: dict[str, list[AcceptedItem]] = {}
        drive_candidates: dict[str, list[AcceptedItem]] = {}
        max_bytes = int(config.get("download_max_bytes", 26_214_400))
        for path in sorted(inbox_path.iterdir(), key=lambda entry: entry.name.casefold()):
            if not path.is_file() or path.suffix.casefold() != ".pdf":
                continue
            row: dict[str, Any] = {"file": path.name}
            try:
                inspection = _inspect_pdf(path, max_bytes)
                row.update({
                    "sha256": inspection.content_sha256,
                    "metadata_title": inspection.metadata_title,
                    "page_count": inspection.page_count,
                })
                match = _match_pdf(inspection, accepted)
                if match is None:
                    row.update({
                        "status": "unmatched_or_ambiguous",
                        "reason": "No unique accepted-item identifier or exact normalized title match.",
                    })
                    results.append(row)
                    continue

                day, item, method = match
                row.update({"matched_date": day, "matched_title": item.title, "match_method": method})
                if item.content_sha256 == inspection.content_sha256 and item.local_pdf_path:
                    row["status"] = "already_imported"
                    drive_candidates.setdefault(day, []).append(item)
                    results.append(row)
                    continue
                if item.local_pdf_path:
                    row.update({
                        "status": "accepted_item_already_has_pdf",
                        "reason": "Existing accepted PDF was preserved; inbox file was not substituted.",
                    })
                    results.append(row)
                    continue

                local_path, content_hash = storage.save_pdf(day, _candidate(item), inspection.content)
                item.local_pdf_path = local_path
                item.content_sha256 = content_hash
                item.pdf_text_chars = len(inspection.first_pages_text)
                item.download_status = "imported_from_pdf_downloads"
                storage.persist_item(_candidate(item), item)
                changed.setdefault(day, []).append(item)
                drive_candidates.setdefault(day, []).append(item)
                row.update({"status": "imported", "local_pdf_path": local_path})
                results.append(row)
            except Exception as exc:
                row.update({"status": "invalid_pdf", "reason": redact_sensitive(exc)})
                results.append(row)

        drive_by_date: dict[str, Any] = {}
        for day in sorted(set(changed) | set(drive_candidates)):
            if day in changed:
                _, all_items = manifests[day]
                storage.write_manifests(day, all_items)
            if sync_drive and config.get("drive", {}).get("enabled"):
                try:
                    upload_items = [
                        replace(
                            item,
                            local_pdf_path=str(project_root / item.local_pdf_path)
                            if item.local_pdf_path and not Path(item.local_pdf_path).is_absolute()
                            else item.local_pdf_path,
                        )
                        for item in drive_candidates.get(day, [])
                    ]
                    drive_by_date[day] = upload_accepted_pdfs(day, upload_items, config["drive"])
                except Exception as exc:
                    drive_by_date[day] = {"status": "failed", "error": redact_sensitive(exc)}
            else:
                drive_by_date[day] = "disabled"

        report = {
            "started_at": started_at,
            "status": "completed",
            "inbox": str(inbox_path),
            "pdf_files": len(results),
            "imported": sum(row["status"] == "imported" for row in results),
            "already_imported": sum(row["status"] == "already_imported" for row in results),
            "unresolved": sum(
                row["status"] not in {"imported", "already_imported"} for row in results
            ),
            "drive_status_by_date": drive_by_date,
            "items": results,
        }
        report_path = storage.write_pdf_import_report(report)
        report["pdf_import_report"] = str(report_path)
        return report
    finally:
        storage.close()
