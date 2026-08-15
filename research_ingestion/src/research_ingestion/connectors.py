from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from typing import Iterable

from .http import PublicHttpClient
from .models import Candidate


TRADING_QUERY = (
    'trading OR "market microstructure" OR "asset pricing" OR momentum OR '
    '"mean reversion" OR "statistical arbitrage" OR volatility OR derivatives OR '
    '"portfolio construction" OR "execution costs" OR liquidity OR "algorithmic trading"'
)

ARXIV_QUERY = " OR ".join((
    "all:trading", 'all:"market microstructure"', 'all:"asset pricing"',
    "all:momentum", 'all:"mean reversion"', 'all:"statistical arbitrage"',
    "all:volatility", "all:derivatives", 'all:"portfolio construction"',
    'all:"execution costs"', "all:liquidity", 'all:"algorithmic trading"',
))


@dataclass
class SourceResult:
    source: str
    candidates: list[Candidate]
    warnings: list[str]


def _text(node: ET.Element | None, default: str = "") -> str:
    return " ".join((node.text or default).split()) if node is not None else default


def _parse_date(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    try:
        from email.utils import parsedate_to_datetime
        return parsedate_to_datetime(value).isoformat()
    except (TypeError, ValueError, OverflowError):
        return value


def fetch_arxiv(client: PublicHttpClient, day: dt.date, limit: int) -> SourceResult:
    start = day.strftime("%Y%m%d0000")
    end = day.strftime("%Y%m%d2359")
    query = f"({ARXIV_QUERY}) AND submittedDate:[{start} TO {end}]"
    params = {
        "search_query": query,
        "start": 0,
        "max_results": min(limit, 200),
        "sortBy": "submittedDate",
        "sortOrder": "descending",
    }
    try:
        raw = client.get("https://export.arxiv.org/api/query", params=params).content
        root = ET.fromstring(raw)
        ns = {"a": "http://www.w3.org/2005/Atom"}
        out = []
        for entry in root.findall("a:entry", ns):
            page = _text(entry.find("a:id", ns))
            stable_id = page.rsplit("/", 1)[-1]
            pdf = next((x.attrib.get("href") for x in entry.findall("a:link", ns)
                        if x.attrib.get("type") == "application/pdf"), None)
            out.append(Candidate(
                source="arXiv",
                title=_text(entry.find("a:title", ns)),
                abstract=_text(entry.find("a:summary", ns)),
                canonical_url=page,
                pdf_url=pdf,
                stable_id=f"arxiv:{stable_id}",
                authors=[_text(a.find("a:name", ns)) for a in entry.findall("a:author", ns)],
                published_at=_text(entry.find("a:published", ns)) or None,
                updated_at=_text(entry.find("a:updated", ns)) or None,
                document_type="academic_paper",
                is_open_access=True,
            ))
        return SourceResult("arXiv", out, [])
    except Exception as exc:
        return SourceResult("arXiv", [], [f"arXiv failed: {exc}"])


def fetch_crossref(client: PublicHttpClient, day: dt.date, limit: int, mailto: str) -> SourceResult:
    params = {
        "query": TRADING_QUERY,
        "filter": f"from-pub-date:{day.isoformat()},until-pub-date:{day.isoformat()}",
        "rows": min(limit, 1000),
        "select": "DOI,title,abstract,author,published,URL,link,license,type",
        "mailto": mailto,
    }
    try:
        payload = json.loads(client.get("https://api.crossref.org/works", params=params).content)
        out = []
        for item in payload["message"]["items"]:
            title = " ".join(item.get("title") or [])
            abstract = re.sub(r"<[^>]+>", " ", item.get("abstract", ""))
            links = item.get("link") or []
            pdf = next((x.get("URL") for x in links if "pdf" in x.get("content-type", "").lower()), None)
            parts = (item.get("published") or {}).get("date-parts", [[None]])[0]
            published = "-".join(f"{n:02d}" if i else str(n) for i, n in enumerate(parts) if n is not None)
            doi = item.get("DOI")
            out.append(Candidate(
                source="Crossref",
                title=html.unescape(title),
                abstract=html.unescape(" ".join(abstract.split())),
                canonical_url=item.get("URL") or f"https://doi.org/{doi}",
                pdf_url=pdf,
                stable_id=f"doi:{doi}" if doi else None,
                doi=doi,
                authors=[" ".join(filter(None, [a.get("given"), a.get("family")])) for a in item.get("author", [])],
                published_at=published or None,
                document_type="academic_paper",
                license=(item.get("license") or [{}])[0].get("URL"),
            ))
        return SourceResult("Crossref", out, [])
    except Exception as exc:
        return SourceResult("Crossref", [], [f"Crossref failed: {exc}"])


def fetch_openalex(client: PublicHttpClient, day: dt.date, limit: int, api_key_env: str) -> SourceResult:
    api_key = os.getenv(api_key_env)
    if not api_key:
        return SourceResult("OpenAlex", [], [f"OpenAlex skipped: {api_key_env} is not set"])
    params = {
        "search": TRADING_QUERY,
        "filter": f"from_publication_date:{day.isoformat()},to_publication_date:{day.isoformat()}",
        "per_page": min(limit, 100),
        "api_key": api_key,
    }
    try:
        payload = json.loads(client.get("https://api.openalex.org/works", params=params).content)
        out = []
        for item in payload.get("results", []):
            primary = item.get("primary_location") or {}
            best = item.get("best_oa_location") or {}
            pdf = best.get("pdf_url") or (primary.get("pdf_url") if primary.get("is_oa") else None)
            doi_url = item.get("doi")
            doi = doi_url.removeprefix("https://doi.org/") if doi_url else None
            out.append(Candidate(
                source="OpenAlex",
                title=item.get("title") or "",
                abstract=_invert_abstract(item.get("abstract_inverted_index")),
                canonical_url=(primary.get("landing_page_url") or doi_url or item["id"]),
                pdf_url=pdf,
                stable_id=item.get("id"),
                doi=doi,
                authors=[x.get("author", {}).get("display_name", "") for x in item.get("authorships", [])],
                published_at=item.get("publication_date"),
                updated_at=item.get("updated_date"),
                document_type="academic_paper",
                is_open_access=(item.get("open_access") or {}).get("is_oa"),
                license=best.get("license"),
            ))
        return SourceResult("OpenAlex", out, [])
    except Exception as exc:
        return SourceResult("OpenAlex", [], [f"OpenAlex failed: {exc}"])


def _invert_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(words))


def fetch_sciencedirect(client: PublicHttpClient, day: dt.date, limit: int, api_key_env: str) -> SourceResult:
    api_key = os.getenv(api_key_env)
    if not api_key:
        return SourceResult("ScienceDirect", [], [f"ScienceDirect skipped: {api_key_env} is not set"])
    params = {
        "query": TRADING_QUERY,
        "date": day.isoformat(),
        "count": min(limit, 100),
        "apiKey": api_key,
        "httpAccept": "application/json",
    }
    try:
        payload = json.loads(client.get("https://api.elsevier.com/content/search/sciencedirect", params=params).content)
        out = []
        for item in payload.get("search-results", {}).get("entry", []):
            is_oa = str(item.get("openaccess", "0")).lower() in {"1", "true", "yes"}
            links = item.get("link") or []
            page = next((x.get("@href") for x in links if x.get("@ref") == "scidir"), None)
            doi = item.get("prism:doi")
            out.append(Candidate(
                source="ScienceDirect",
                title=item.get("dc:title") or "",
                abstract=item.get("dc:description") or "",
                canonical_url=page or item.get("prism:url") or f"https://doi.org/{doi}",
                pdf_url=None,
                stable_id=f"pii:{item.get('pii')}" if item.get("pii") else None,
                doi=doi,
                authors=[x.get("$", "") for x in item.get("authors", {}).get("author", [])] if isinstance(item.get("authors"), dict) else [],
                published_at=item.get("prism:coverDate"),
                document_type="academic_paper",
                is_open_access=is_oa,
                metadata={"science_direct_fulltext_api": item.get("prism:url") if is_oa else None},
            ))
        return SourceResult("ScienceDirect", out, [])
    except Exception as exc:
        return SourceResult("ScienceDirect", [], [f"ScienceDirect failed: {exc}"])


def fetch_feed(client: PublicHttpClient, day: dt.date, feed: dict, limit: int) -> SourceResult:
    name = feed["name"]
    try:
        root = ET.fromstring(client.get(feed["url"]).content)
        entries = root.findall(".//item")
        atom_ns = {"a": "http://www.w3.org/2005/Atom"}
        if not entries:
            entries = root.findall("a:entry", atom_ns)
        out = []
        for entry in entries[:limit]:
            title = _text(entry.find("title")) or _text(entry.find("a:title", atom_ns))
            link_node = entry.find("link")
            if link_node is None:
                link_node = entry.find("a:link", atom_ns)
            link = _text(link_node) or (link_node.attrib.get("href") if link_node is not None else "")
            description = (_text(entry.find("description")) or _text(entry.find("summary"))
                           or _text(entry.find("a:summary", atom_ns)))
            published = (_text(entry.find("pubDate")) or _text(entry.find("published"))
                         or _text(entry.find("a:published", atom_ns)) or _text(entry.find("a:updated", atom_ns)))
            parsed = _parse_date(published)
            if parsed:
                try:
                    if dt.datetime.fromisoformat(parsed.replace("Z", "+00:00")).date() != day:
                        continue
                except ValueError:
                    pass
            combined = f"{title} {description} {' '.join(entry.itertext())}".lower()
            if any(term.lower() in combined for term in feed.get("exclude_terms", [])):
                continue
            page_exclusions = [term.lower() for term in feed.get("exclude_page_terms", [])]
            if page_exclusions and link:
                try:
                    page = client.get(link, headers={"Accept": "text/html"}, max_bytes=2_000_000)
                    page_text = page.content.decode("utf-8", errors="ignore").lower()
                    if any(term in page_text for term in page_exclusions):
                        continue
                except Exception as exc:
                    return SourceResult(name, out, [f"{name} access check failed for {link}: {exc}"])
            out.append(Candidate(
                source=name,
                title=html.unescape(title),
                abstract=html.unescape(re.sub(r"<[^>]+>", " ", description)),
                canonical_url=link,
                stable_id=_text(entry.find("guid")) or link,
                published_at=parsed,
                document_type="institutional_report" if name in {
                    "BIS Research Papers", "Central Bank Research Hub", "NBER New Working Papers"
                } else "article",
                metadata={"discovery_only": bool(feed.get("discovery_only"))},
            ))
        return SourceResult(name, out, [])
    except Exception as exc:
        return SourceResult(name, [], [f"{name} failed: {exc}"])


def collect_all(client: PublicHttpClient, config: dict, day: dt.date) -> list[SourceResult]:
    sources = config["sources"]
    limit = config["candidate_limit_per_source"]
    results: list[SourceResult] = []
    if sources["arxiv"].get("enabled"):
        results.append(fetch_arxiv(client, day, limit))
    if sources["crossref"].get("enabled"):
        results.append(fetch_crossref(client, day, limit, sources["crossref"]["mailto"]))
    if sources["openalex"].get("enabled"):
        results.append(fetch_openalex(client, day, limit, sources["openalex"]["api_key_env"]))
    if sources["sciencedirect"].get("enabled"):
        results.append(fetch_sciencedirect(client, day, limit, sources["sciencedirect"]["api_key_env"]))
    for feed in sources.get("feeds", []):
        if feed.get("enabled"):
            results.append(fetch_feed(client, day, feed, limit))
    return results
