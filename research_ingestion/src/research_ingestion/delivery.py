from __future__ import annotations

import datetime as dt
import json
from pathlib import Path
from typing import Any

from .drive import upload_accepted_pdfs
from .emailer import send_digest
from .models import AcceptedItem
from .redact import redact_sensitive


def _failed(value: Any) -> bool:
    if isinstance(value, str):
        return value.casefold().startswith("failed")
    return isinstance(value, dict) and value.get("status") == "failed"


def retry_failed_deliveries(
    project_root: Path,
    config: dict[str, Any],
    *,
    days: int = 30,
) -> dict[str, Any]:
    cutoff = dt.date.today() - dt.timedelta(days=max(1, days))
    results: list[dict[str, Any]] = []
    run_dir = project_root / "data" / "runs"
    for run_path in sorted(run_dir.glob("*.json")):
        try:
            day = dt.date.fromisoformat(run_path.stem)
        except ValueError:
            continue
        if day < cutoff:
            continue
        report = json.loads(run_path.read_text(encoding="utf-8"))
        email_failed = _failed(report.get("email_status"))
        drive_failed = _failed(report.get("drive_status"))
        if not email_failed and not drive_failed:
            continue
        manifest_path = project_root / "data" / "accepted" / f"{day.isoformat()}.json"
        row: dict[str, Any] = {
            "date": day.isoformat(),
            "email_attempted": email_failed,
            "drive_attempted": drive_failed,
        }
        if not manifest_path.exists():
            row["status"] = "accepted_manifest_not_found"
            results.append(row)
            continue
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        items = [AcceptedItem(**item) for item in manifest.get("items", [])]
        warnings = [
            warning for warning in report.get("warnings", [])
            if not warning.startswith(("Email delivery failed:", "Google Drive upload failed:"))
        ]
        if drive_failed:
            try:
                report["drive_status"] = upload_accepted_pdfs(day.isoformat(), items, config["drive"])
                row["drive_status"] = report["drive_status"]
            except Exception as exc:
                row["drive_status"] = {"status": "failed", "error": redact_sensitive(exc)}
                report["drive_status"] = row["drive_status"]
        if email_failed:
            try:
                report["email_status"] = send_digest(
                    day.isoformat(), items, config["email_recipients"],
                    config["email_top_n"], warnings, config.get("email"),
                )
                row["email_status"] = report["email_status"]
            except Exception as exc:
                row["email_status"] = f"failed: {redact_sensitive(exc)}"
                report["email_status"] = row["email_status"]
        report["delivery_retry_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        run_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        row["status"] = "completed" if not _failed(row.get("email_status")) and not _failed(row.get("drive_status")) else "failed"
        results.append(row)
    return {
        "status": "completed" if all(row.get("status") == "completed" for row in results) else "failed",
        "attempted_dates": len(results),
        "items": results,
    }
