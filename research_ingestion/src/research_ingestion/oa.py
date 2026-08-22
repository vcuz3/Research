from __future__ import annotations

import json
import os
from urllib.parse import quote, urlparse

from .http import PublicHttpClient
from .redact import redact_sensitive


def _http_url(value: object) -> str | None:
    if not isinstance(value, str):
        return None
    parsed = urlparse(value)
    return value if parsed.scheme in {"http", "https"} and parsed.netloc else None


def _deduplicate(values: list[str]) -> list[str]:
    return list(dict.fromkeys(values))


def resolve_open_access_locations(
    client: PublicHttpClient, doi: str | None, config: dict | None
) -> tuple[list[str], list[str], list[str]]:
    """Return verified OA PDF/landing URLs from explicitly enabled resolvers."""
    if not doi or not config or not config.get("enabled"):
        return [], [], []

    pdf_urls: list[str] = []
    landing_urls: list[str] = []
    errors: list[str] = []
    encoded_doi = quote(doi, safe="")

    if config.get("openalex_enabled", True):
        params: dict[str, str] = {}
        key_env = config.get("openalex_api_key_env", "OPENALEX_API_KEY")
        if os.getenv(key_env):
            params["api_key"] = os.environ[key_env]
        try:
            payload = json.loads(client.get(
                f"https://api.openalex.org/works/https://doi.org/{encoded_doi}",
                params=params,
            ).content)
            locations = [payload.get("best_oa_location") or {}, *(payload.get("locations") or [])]
            for location in locations:
                if not location or not location.get("is_oa"):
                    continue
                pdf = _http_url(location.get("pdf_url"))
                landing = _http_url(location.get("landing_page_url"))
                if pdf:
                    pdf_urls.append(pdf)
                if landing:
                    landing_urls.append(landing)
        except Exception as exc:
            errors.append(f"OpenAlex DOI lookup failed: {redact_sensitive(exc)}")

    if config.get("unpaywall_enabled", True):
        email = str(config.get("unpaywall_email") or "").strip()
        if not email:
            errors.append("Unpaywall DOI lookup skipped: contact email is not configured")
        else:
            try:
                payload = json.loads(client.get(
                    f"https://api.unpaywall.org/v2/{encoded_doi}",
                    params={"email": email},
                ).content)
                if payload.get("is_oa"):
                    locations = [payload.get("best_oa_location") or {}, *(payload.get("oa_locations") or [])]
                    for location in locations:
                        if not location:
                            continue
                        pdf = _http_url(location.get("url_for_pdf"))
                        landing = _http_url(location.get("url_for_landing_page"))
                        if pdf:
                            pdf_urls.append(pdf)
                        if landing:
                            landing_urls.append(landing)
            except Exception as exc:
                errors.append(f"Unpaywall DOI lookup failed: {redact_sensitive(exc)}")

    return _deduplicate(pdf_urls), _deduplicate(landing_urls), errors
