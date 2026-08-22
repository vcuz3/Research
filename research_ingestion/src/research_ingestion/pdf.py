from __future__ import annotations

import io
from urllib.parse import urljoin, urlparse

from bs4 import BeautifulSoup
from pypdf import PdfReader

from .http import PublicHttpClient
from .models import Candidate
from .oa import resolve_open_access_locations
from .redact import redact_sensitive


def extract_pdf_text(content: bytes, max_pages: int = 80) -> str:
    reader = PdfReader(io.BytesIO(content))
    chunks = []
    for page in reader.pages[:max_pages]:
        chunks.append(page.extract_text() or "")
    return "\n".join(chunks).strip()


def _is_pdf(content: bytes, content_type: str) -> bool:
    return content.startswith(b"%PDF") or "application/pdf" in content_type


def _download_first_public_pdf(
    client: PublicHttpClient, urls: list[str], max_bytes: int
) -> tuple[bytes | None, str | None, list[str]]:
    errors: list[str] = []
    seen: set[str] = set()
    for url in urls:
        if not url or url in seen:
            continue
        seen.add(url)
        try:
            result = client.get(url, headers={"Accept": "application/pdf"}, max_bytes=max_bytes, retries=1)
            if _is_pdf(result.content, result.content_type):
                return result.content, result.final_url, errors
            errors.append(f"non-PDF response from {result.final_url}")
        except Exception as exc:
            errors.append(redact_sensitive(exc))
    return None, None, errors


def _public_pdf_links(page_content: bytes, page_url: str) -> list[str]:
    soup = BeautifulSoup(page_content, "html.parser")
    links: list[str] = []
    for meta in soup.find_all("meta"):
        key = str(meta.get("name") or meta.get("property") or "").casefold()
        if key in {"citation_pdf_url", "eprints.document_url", "pdf_url"} and meta.get("content"):
            links.append(urljoin(page_url, str(meta["content"])))
    for link in soup.find_all("link", href=True):
        if str(link.get("type") or "").casefold() == "application/pdf":
            links.append(urljoin(page_url, str(link["href"])))
    for anchor in soup.find_all("a", href=True):
        href = str(anchor["href"])
        path = urlparse(urljoin(page_url, href)).path.casefold()
        if path.endswith(".pdf") or str(anchor.get("type") or "").casefold() == "application/pdf":
            links.append(urljoin(page_url, href))
    return links


def download_public_pdf(
    client: PublicHttpClient,
    candidate: Candidate,
    max_bytes: int,
    *,
    oa_config: dict | None = None,
    resolver_only: bool = False,
) -> tuple[bytes | None, str | None, str]:
    urls: list[str] = []
    if candidate.pdf_url and not resolver_only:
        urls.append(candidate.pdf_url)
    api_url = candidate.metadata.get("science_direct_fulltext_api")
    if api_url and candidate.is_open_access and not resolver_only:
        urls.append(api_url)
    content, final_url, errors = _download_first_public_pdf(client, urls, max_bytes)
    if content:
        return content, final_url, "downloaded"

    resolver_pdfs, resolver_landings, resolver_errors = resolve_open_access_locations(
        client, candidate.doi, oa_config
    )
    errors.extend(resolver_errors)
    content, final_url, resolver_download_errors = _download_first_public_pdf(
        client, resolver_pdfs, max_bytes
    )
    if content:
        return content, final_url, "downloaded_open_access_resolver"
    errors.extend(resolver_download_errors)

    if resolver_only:
        page_urls = resolver_landings
    elif candidate.metadata.get("discovery_only"):
        page_urls = resolver_landings
    else:
        page_urls = [candidate.canonical_url, *resolver_landings] if candidate.canonical_url else resolver_landings

    if not page_urls:
        detail = errors[0] if errors else "no public PDF URL"
        return None, None, f"title_link_only: {detail}"

    seen_pages: set[str] = set()
    for page_url in page_urls:
        if not page_url or page_url in seen_pages:
            continue
        seen_pages.add(page_url)
        try:
            page = client.get(page_url, headers={"Accept": "text/html"}, max_bytes=2_000_000, retries=1)
            if _is_pdf(page.content, page.content_type):
                status = "downloaded_open_access_resolver" if page_url in resolver_landings else "downloaded"
                return page.content, page.final_url, status
            if "html" not in page.content_type:
                errors.append(f"non-HTML landing response from {page.final_url}")
                continue
            public_links = _public_pdf_links(page.content, page.final_url)
            content, final_url, link_errors = _download_first_public_pdf(client, public_links, max_bytes)
            if content:
                status = "downloaded_open_access_resolver" if page_url in resolver_landings else "downloaded"
                return content, final_url, status
            errors.extend(link_errors)
            if not public_links:
                errors.append("landing page exposed no public PDF link")
        except Exception as exc:
            errors.append(f"landing page failed: {redact_sensitive(exc)}")
    detail = errors[0] if errors else "no public PDF URL"
    return None, None, f"title_link_only: {detail}"
