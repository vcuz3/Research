import json

from research_ingestion.http import Download
from research_ingestion.models import Candidate
from research_ingestion.pdf import download_public_pdf


def test_unpaywall_resolver_downloads_only_declared_open_access_pdf(monkeypatch):
    monkeypatch.delenv("OPENALEX_API_KEY", raising=False)
    calls = []

    class Client:
        def get(self, url, **kwargs):
            calls.append((url, kwargs.get("params")))
            if "api.openalex.org" in url:
                payload = {"best_oa_location": None, "locations": [], "open_access": {"is_oa": False}}
                return Download(json.dumps(payload).encode(), "application/json", url)
            if "api.unpaywall.org" in url:
                payload = {
                    "is_oa": True,
                    "best_oa_location": {
                        "url_for_pdf": "https://repository.test/public.pdf",
                        "url_for_landing_page": "https://repository.test/item",
                    },
                    "oa_locations": [],
                }
                return Download(json.dumps(payload).encode(), "application/json", url)
            assert url == "https://repository.test/public.pdf"
            return Download(b"%PDF-1.7 repository copy", "application/pdf", url)

    candidate = Candidate(
        source="Crossref",
        title="Accepted paper",
        canonical_url="https://doi.org/10.1234/example",
        doi="10.1234/example",
    )
    content, url, status = download_public_pdf(
        Client(),
        candidate,
        1_000_000,
        oa_config={
            "enabled": True,
            "openalex_enabled": True,
            "unpaywall_enabled": True,
            "unpaywall_email": "reader@example.test",
        },
        resolver_only=True,
    )

    assert content == b"%PDF-1.7 repository copy"
    assert url == "https://repository.test/public.pdf"
    assert status == "downloaded_open_access_resolver"
    unpaywall_call = next(call for call in calls if "api.unpaywall.org" in call[0])
    assert unpaywall_call[1] == {"email": "reader@example.test"}


def test_disabled_resolver_makes_no_external_lookup():
    class Client:
        def get(self, *_args, **_kwargs):
            raise AssertionError("disabled resolver must not call an external service")

    candidate = Candidate(
        source="Crossref",
        title="Paper",
        canonical_url="https://doi.org/10.1234/example",
        doi="10.1234/example",
    )
    content, url, status = download_public_pdf(
        Client(), candidate, 1_000_000, oa_config={"enabled": False}, resolver_only=True
    )

    assert content is None
    assert url is None
    assert status == "title_link_only: no public PDF URL"
