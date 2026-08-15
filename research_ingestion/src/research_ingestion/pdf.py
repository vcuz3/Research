from __future__ import annotations

import io

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .http import PublicHttpClient
from .models import Candidate


def extract_pdf_text(content: bytes, max_pages: int = 80) -> str:
    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page in reader.pages[:max_pages]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def download_public_pdf(client: PublicHttpClient, candidate: Candidate, max_bytes: int) -> tuple[bytes | None, str | None, str]:
    urls: list[str] = []
    if candidate.pdf_url:
        urls.append(candidate.pdf_url)
    api_url = candidate.metadata.get("science_direct_fulltext_api")
    if api_url and candidate.is_open_access:
        urls.append(api_url)
    for url in urls:
        try:
            result = client.get(url, headers={"Accept": "application/pdf"}, max_bytes=max_bytes)
            if result.content.startswith(b"%PDF") or "application/pdf" in result.content_type:
                return result.content, result.final_url, "downloaded"
        except Exception as exc:
            return None, None, f"download_failed: {exc}"

    if candidate.metadata.get("discovery_only") or not candidate.canonical_url:
        return None, None, "title_link_only"
    try:
        page = client.get(candidate.canonical_url, headers={"Accept": "text/html"}, max_bytes=2_000_000)
        if "html" not in page.content_type:
            return None, None, "title_link_only"
        soup = BeautifulSoup(page.content, "html.parser")
        meta = soup.find("meta", attrs={"name": "citation_pdf_url"})
        href = meta.get("content") if meta else None
        if href:
            result = client.get(href, headers={"Accept": "application/pdf"}, max_bytes=max_bytes)
            if result.content.startswith(b"%PDF"):
                return result.content, result.final_url, "downloaded"
    except Exception:
        pass
    return None, None, "title_link_only"

