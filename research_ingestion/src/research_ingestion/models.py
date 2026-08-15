from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class Candidate:
    source: str
    title: str
    canonical_url: str
    document_type: str = "article"
    abstract: str = ""
    pdf_url: str | None = None
    stable_id: str | None = None
    doi: str | None = None
    authors: list[str] = field(default_factory=list)
    published_at: str | None = None
    updated_at: str | None = None
    is_open_access: bool | None = None
    license: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def identity(self) -> str:
        return (self.doi or self.stable_id or self.canonical_url).strip().lower()


@dataclass
class AcceptedItem:
    source: str
    title: str
    abstract_or_title: str
    document_type: str
    canonical_url: str
    pdf_url: str | None
    local_pdf_path: str | None
    doi: str | None
    stable_id: str | None
    authors: list[str]
    published_at: str | None
    updated_at: str | None
    retrieved_at: str
    is_open_access: bool | None
    license: str | None
    topics: list[str]
    relevance_score: float
    relevance_reason: str
    ai_status: str
    content_sha256: str | None
    pdf_text_chars: int
    download_status: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

