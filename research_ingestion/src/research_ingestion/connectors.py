from __future__ import annotations

import datetime as dt
import html
import json
import os
import re
import time
import urllib.parse
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from math import ceil
from typing import Iterable

from .http import PublicHttpClient
from .models import Candidate
from .redact import redact_sensitive


THEME_QUERIES: dict[str, str] = {
    "market_microstructure": "market microstructure order book market impact trade execution liquidity",
    "momentum_trend": "momentum trend following time series momentum breakout asset returns",
    "mean_reversion": "mean reversion pairs trading statistical arbitrage cointegration",
    "volatility_derivatives": "volatility options derivatives implied volatility variance risk premium",
    "portfolio_risk": "portfolio construction asset allocation risk parity drawdown position sizing",
    "machine_learning": "machine learning financial markets algorithmic trading return forecasting",
    "asset_pricing_factors": "asset pricing factor premia cross sectional returns value carry",
    "macro_trading": "macro trading monetary policy interest rates currencies bonds inflation",
    "digital_assets": "bitcoin crypto digital assets blockchain defi trading",
    "research_methods": "backtesting transaction costs data snooping overfitting systematic trading",
    "event_driven": "event driven trading earnings announcements mergers market reaction",
    "alternative_data": "alternative data sentiment news analytics trading financial markets",
}

ARXIV_THEME_QUERIES: dict[str, str] = {
    "market_microstructure": '(all:"market microstructure" OR all:"order book" OR all:"market impact" OR all:"trade execution")',
    "momentum_trend": '(all:"trend following" OR all:"time series momentum" OR all:"financial momentum")',
    "mean_reversion": '(all:"mean reversion" OR all:"pairs trading" OR all:"statistical arbitrage")',
    "volatility_derivatives": '(all:"implied volatility" OR all:"option pricing" OR all:"variance risk premium")',
    "portfolio_risk": '(all:"portfolio construction" OR all:"asset allocation" OR all:"risk parity")',
    "machine_learning": '(all:"algorithmic trading" OR all:"financial markets" AND all:"machine learning")',
    "asset_pricing_factors": '(all:"asset pricing" OR all:"factor premia" OR all:"cross sectional returns")',
    "macro_trading": '(all:"macro trading" OR all:"monetary policy" AND (all:currency OR all:bond OR all:market))',
    "digital_assets": '(all:bitcoin OR all:"crypto trading" OR all:"digital asset market")',
    "research_methods": '(all:backtesting OR all:"transaction costs" AND all:trading OR all:"data snooping")',
    "event_driven": '(all:"event driven trading" OR all:"earnings announcement" AND all:market)',
    "alternative_data": '(all:"alternative data" AND all:trading OR all:"news sentiment" AND all:market)',
}

SSRN_FINANCE_ANCHORS = (
    "trading", "financial", "finance", "portfolio", "stock", "equity", "bond", "option", "derivative",
    "volatility", "liquidity", "currency", "forex", "arbitrage", "investment", "bitcoin", "crypto",
    "monetary policy", "interest rate", "factor premia", "risk premium", "execution", "order book",
    "market making", "asset pricing", "asset returns", "commodity market", "systematic strategy",
)

ARXIV_REQUEST_INTERVAL_SECONDS = 3.0


@dataclass
class SourceResult:
    source: str
    candidates: list[Candidate]
    warnings: list[str]


def _theme_limit(total_limit: int) -> int:
    return max(1, ceil(total_limit / len(THEME_QUERIES)))


def _merge_theme_candidates(candidates: Iterable[Candidate], limit: int) -> list[Candidate]:
    merged: dict[str, Candidate] = {}
    for candidate in candidates:
        key = candidate.identity()
        theme = candidate.metadata.get("discovery_theme")
        if key in merged:
            themes = merged[key].metadata.setdefault("discovery_themes", [])
            if theme and theme not in themes:
                themes.append(theme)
            continue
        if theme:
            candidate.metadata["discovery_themes"] = [theme]
        merged[key] = candidate
        if len(merged) >= limit:
            break
    return list(merged.values())


def _published_date(item: dict) -> str | None:
    parts = (item.get("published") or item.get("posted") or {}).get("date-parts", [[None]])[0]
    value = "-".join(f"{n:02d}" if i else str(n) for i, n in enumerate(parts) if n is not None)
    return value or None


def _clean_markup(value: str) -> str:
    # Some Crossref/SSRN titles are HTML-escaped more than once.
    text = value
    for _ in range(2):
        text = html.unescape(text)
    return " ".join(re.sub(r"<[^>]+>", " ", text).replace("\xa0", " ").split())


def _is_auth_error(exc: Exception) -> bool:
    return getattr(getattr(exc, "response", None), "status_code", None) in {401, 403}


def _crossref_candidate(item: dict, source: str, theme: str) -> Candidate:
    title = _clean_markup(" ".join(item.get("title") or []))
    abstract = _clean_markup(item.get("abstract", ""))
    links = item.get("link") or []
    pdf = next((x.get("URL") for x in links if "pdf" in x.get("content-type", "").lower()), None)
    doi = item.get("DOI")
    return Candidate(
        source=source,
        title=title,
        abstract=abstract,
        canonical_url=item.get("URL") or f"https://doi.org/{doi}",
        pdf_url=pdf,
        stable_id=f"doi:{doi}" if doi else None,
        doi=doi,
        authors=[" ".join(filter(None, [a.get("given"), a.get("family")])) for a in item.get("author", [])],
        published_at=_published_date(item),
        document_type="academic_paper",
        license=(item.get("license") or [{}])[0].get("URL"),
        metadata={"discovery_theme": theme},
    )


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
    out: list[Candidate] = []
    warnings: list[str] = []
    ns = {"a": "http://www.w3.org/2005/Atom"}
    for request_index, (theme, theme_query) in enumerate(ARXIV_THEME_QUERIES.items()):
        # arXiv asks clients making consecutive API calls to wait three seconds.
        # Pace even after a failed request so a 429 does not trigger another
        # immediate call and worsen source coverage.
        if request_index:
            time.sleep(ARXIV_REQUEST_INTERVAL_SECONDS)
        params = {
            "search_query": f"{theme_query} AND submittedDate:[{start} TO {end}]",
            "start": 0,
            "max_results": min(_theme_limit(limit), 200),
            "sortBy": "submittedDate",
            "sortOrder": "descending",
        }
        try:
            raw = client.get("https://export.arxiv.org/api/query", params=params).content
            root = ET.fromstring(raw)
        except Exception as exc:
            warnings.append(f"arXiv theme {theme} failed: {redact_sensitive(exc)}")
            continue
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
                metadata={"discovery_theme": theme},
            ))
    return SourceResult("arXiv", _merge_theme_candidates(out, limit), warnings)


def fetch_crossref(client: PublicHttpClient, day: dt.date, limit: int, mailto: str) -> SourceResult:
    out: list[Candidate] = []
    warnings: list[str] = []
    for theme, query in THEME_QUERIES.items():
        params = {
            "query": query,
            "filter": f"from-pub-date:{day.isoformat()},until-pub-date:{day.isoformat()}",
            "rows": min(_theme_limit(limit), 1000),
            "select": "DOI,title,abstract,author,published,URL,link,license,type",
            "mailto": mailto,
        }
        try:
            payload = json.loads(client.get("https://api.crossref.org/works", params=params).content)
        except Exception as exc:
            warnings.append(f"Crossref theme {theme} failed: {redact_sensitive(exc)}")
            continue
        for item in payload["message"]["items"]:
            if (item.get("DOI") or "").lower().startswith("10.2139/ssrn."):
                continue
            out.append(_crossref_candidate(item, "Crossref", theme))
    return SourceResult("Crossref", _merge_theme_candidates(out, limit), warnings)


def fetch_ssrn(client: PublicHttpClient, day: dt.date, limit: int, mailto: str) -> SourceResult:
    """Discover SSRN papers through its public Crossref DOI-prefix metadata."""
    out: list[Candidate] = []
    warnings: list[str] = []
    for theme, query in THEME_QUERIES.items():
        params = {
            "query": query,
            # SSRN often deposits only a publication year. Crossref's created
            # timestamp is the reliable day on which a new SSRN DOI appeared.
            "filter": f"from-created-date:{day.isoformat()},until-created-date:{day.isoformat()}",
            "rows": min(_theme_limit(limit), 1000),
            "select": "DOI,title,abstract,author,created,published,posted,URL,link,license,type,publisher",
            "mailto": mailto,
        }
        try:
            payload = json.loads(client.get("https://api.crossref.org/prefixes/10.2139/works", params=params).content)
        except Exception as exc:
            warnings.append(f"SSRN theme {theme} failed: {redact_sensitive(exc)}")
            continue
        for item in payload.get("message", {}).get("items", []):
            doi = (item.get("DOI") or "").lower()
            candidate = _crossref_candidate(item, "SSRN", theme)
            created_at = (item.get("created") or {}).get("date-time")
            if created_at:
                candidate.published_at = created_at[:10]
                candidate.metadata["ssrn_deposited_at"] = created_at
            searchable = f"{candidate.title} {candidate.abstract}".lower()
            if doi.startswith("10.2139/ssrn.") and any(anchor in searchable for anchor in SSRN_FINANCE_ANCHORS):
                candidate.metadata["ssrn_finance_filtered"] = True
                out.append(candidate)
    return SourceResult("SSRN", _merge_theme_candidates(out, limit), warnings)


def fetch_openalex(client: PublicHttpClient, day: dt.date, limit: int, api_key_env: str) -> SourceResult:
    api_key = os.getenv(api_key_env)
    if not api_key:
        return SourceResult("OpenAlex", [], [f"OpenAlex skipped: {api_key_env} is not set"])
    out: list[Candidate] = []
    warnings: list[str] = []
    for theme, query in THEME_QUERIES.items():
        params = {
            "search": query,
            "filter": f"from_publication_date:{day.isoformat()},to_publication_date:{day.isoformat()}",
            "per_page": min(_theme_limit(limit), 100),
            "api_key": api_key,
        }
        try:
            payload = json.loads(client.get("https://api.openalex.org/works", params=params).content)
        except Exception as exc:
            warnings.append(f"OpenAlex theme {theme} failed: {redact_sensitive(exc)}")
            if _is_auth_error(exc):
                break
            continue
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
                metadata={"discovery_theme": theme},
            ))
    return SourceResult("OpenAlex", _merge_theme_candidates(out, limit), warnings)


def _invert_abstract(index: dict | None) -> str:
    if not index:
        return ""
    words = [(position, word) for word, positions in index.items() for position in positions]
    return " ".join(word for _, word in sorted(words))


def fetch_sciencedirect(client: PublicHttpClient, day: dt.date, limit: int, api_key_env: str) -> SourceResult:
    api_key = os.getenv(api_key_env)
    if not api_key:
        return SourceResult("ScienceDirect", [], [f"ScienceDirect skipped: {api_key_env} is not set"])
    out: list[Candidate] = []
    warnings: list[str] = []
    for theme, query in THEME_QUERIES.items():
        params = {
            "query": f"title-abstr-key({query}) AND pub-date IS {day.strftime('%Y%m%d')}",
            "count": min(_theme_limit(limit), 100),
            "view": "STANDARD",
            "httpAccept": "application/json",
        }
        try:
            payload = json.loads(client.get(
                "https://api.elsevier.com/content/metadata/article",
                params=params,
                headers={"X-ELS-APIKey": api_key, "Accept": "application/json"},
            ).content)
        except Exception as exc:
            warnings.append(f"ScienceDirect theme {theme} failed: {redact_sensitive(exc)}")
            if _is_auth_error(exc):
                break
            continue
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
                metadata={
                    "science_direct_fulltext_api": None,
                    "metadata_only": True,
                    "discovery_theme": theme,
                },
            ))
    return SourceResult("ScienceDirect", _merge_theme_candidates(out, limit), warnings)


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
                    return SourceResult(name, out, [f"{name} access check failed for {link}: {redact_sensitive(exc)}"])
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
        return SourceResult(name, [], [f"{name} failed: {redact_sensitive(exc)}"])


def collect_all(client: PublicHttpClient, config: dict, day: dt.date) -> list[SourceResult]:
    sources = config["sources"]
    limit = config["candidate_limit_per_source"]
    results: list[SourceResult] = []
    if sources["arxiv"].get("enabled"):
        results.append(fetch_arxiv(client, day, limit))
    if sources["crossref"].get("enabled"):
        results.append(fetch_crossref(client, day, limit, sources["crossref"]["mailto"]))
    if sources.get("ssrn", {}).get("enabled"):
        results.append(fetch_ssrn(client, day, limit, sources["ssrn"].get("mailto", sources["crossref"]["mailto"])))
    if sources["openalex"].get("enabled"):
        results.append(fetch_openalex(client, day, limit, sources["openalex"]["api_key_env"]))
    if sources["sciencedirect"].get("enabled"):
        results.append(fetch_sciencedirect(client, day, limit, sources["sciencedirect"]["api_key_env"]))
    for feed in sources.get("feeds", []):
        if feed.get("enabled"):
            results.append(fetch_feed(client, day, feed, limit))
    return results
