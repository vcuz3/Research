from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from pathlib import Path

from .models import AcceptedItem, Candidate


SCHEMA = """
CREATE TABLE IF NOT EXISTS items (
    identity TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    source TEXT NOT NULL,
    canonical_url TEXT NOT NULL,
    doi TEXT,
    published_at TEXT,
    retrieved_at TEXT NOT NULL,
    local_pdf_path TEXT,
    content_sha256 TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at);
"""


class Storage:
    def __init__(self, root: Path) -> None:
        self.root = root
        self.data = root / "data"
        for part in (
            "accepted", "reading", "rejected", "runs", "pdf_resolution",
            "pdf_imports", "raw", "state", "catalogue",
        ):
            (self.data / part).mkdir(parents=True, exist_ok=True)
        self.db = sqlite3.connect(self.data / "catalogue" / "research.sqlite")
        self.db.executescript(SCHEMA)

    def close(self) -> None:
        self.db.close()

    def contains(self, candidate: Candidate) -> bool:
        row = self.db.execute("SELECT 1 FROM items WHERE identity = ?", (candidate.identity(),)).fetchone()
        return row is not None

    def save_pdf(self, day: str, candidate: Candidate, content: bytes) -> tuple[str, str]:
        digest = hashlib.sha256(content).hexdigest()
        source = re.sub(r"[^a-z0-9]+", "-", candidate.source.lower()).strip("-")
        identifier = re.sub(r"[^a-zA-Z0-9._-]+", "-", candidate.identity())[-100:].strip("-") or digest[:16]
        directory = self.data / "raw" / day.replace("-", "/") / source / identifier
        directory.mkdir(parents=True, exist_ok=True)
        target = directory / f"document-{digest[:12]}.pdf"
        if not target.exists():
            target.write_bytes(content)
        return str(target.relative_to(self.root)), digest

    def persist_item(self, candidate: Candidate, item: AcceptedItem) -> None:
        payload = json.dumps(item.to_dict(), ensure_ascii=False, sort_keys=True)
        self.db.execute(
            "INSERT OR REPLACE INTO items VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (candidate.identity(), item.title, item.source, item.canonical_url, item.doi,
             item.published_at, item.retrieved_at, item.local_pdf_path, item.content_sha256, payload),
        )
        self.db.commit()

    def write_manifests(self, day: str, items: list[AcceptedItem]) -> tuple[Path, Path]:
        accepted_path = self.data / "accepted" / f"{day}.json"
        reading_path = self.data / "reading" / f"{day}.json"
        accepted_payload = {
            "date": day,
            "accepted_count": len(items),
            "items": [item.to_dict() for item in items],
        }
        reading_payload = {
            "date": day,
            "item_count": len(items),
            "items": [
                {
                    "title": item.title,
                    "abstract_or_title": item.abstract_or_title,
                    "canonical_url": item.canonical_url,
                    "local_pdf_path": item.local_pdf_path,
                    "source": item.source,
                    "topics": item.topics,
                    "relevance_score": item.relevance_score,
                }
                for item in sorted(items, key=lambda x: x.relevance_score, reverse=True)
            ],
        }
        accepted_path.write_text(json.dumps(accepted_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        reading_path.write_text(json.dumps(reading_payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return accepted_path, reading_path

    def write_rejected_manifest(self, day: str, items: list[dict]) -> Path:
        path = self.data / "rejected" / f"{day}.json"
        payload = {
            "date": day,
            "rejected_count": len(items),
            "items": items,
        }
        path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_run_report(self, day: str, report: dict) -> Path:
        path = self.data / "runs" / f"{day}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_pdf_resolution_report(self, day: str, report: dict) -> Path:
        path = self.data / "pdf_resolution" / f"{day}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    def write_pdf_import_report(self, report: dict) -> Path:
        stamp = report["started_at"].replace(":", "").replace("+", "-")
        path = self.data / "pdf_imports" / f"{stamp}.json"
        path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
        return path

    @property
    def state_path(self) -> Path:
        return self.data / "state" / "last_successful_date.txt"
