import datetime as dt
import json

from research_ingestion.connectors import (
    THEME_QUERIES,
    ARXIV_THEME_QUERIES,
    _invert_abstract,
    fetch_arxiv,
    fetch_crossref,
    fetch_feed,
    fetch_sciencedirect,
    fetch_ssrn,
)
from research_ingestion.http import Download


def test_openalex_abstract_reconstruction():
    assert _invert_abstract({"Trading": [0], "works": [1]}) == "Trading works"


def test_arxiv_paces_consecutive_theme_requests(monkeypatch):
    class Client:
        def __init__(self):
            self.calls = 0

        def get(self, url, **_kwargs):
            self.calls += 1
            return Download(
                b'<feed xmlns="http://www.w3.org/2005/Atom"></feed>',
                "application/atom+xml",
                url,
            )

    sleeps = []
    monkeypatch.setattr("research_ingestion.connectors.time.sleep", sleeps.append)
    client = Client()

    result = fetch_arxiv(client, dt.date(2026, 8, 19), 100)

    assert result.warnings == []
    assert client.calls == len(ARXIV_THEME_QUERIES)
    assert sleeps == [3.0] * (len(ARXIV_THEME_QUERIES) - 1)


def test_rss_link_and_exclusion_are_parsed():
    class Client:
        def get(self, *_args, **_kwargs):
            return Download(b"""<rss><channel>
              <item><title>Free trading study</title><link>https://example.test/free</link>
                <description>market microstructure</description><pubDate>Thu, 13 Aug 2026 10:00:00 GMT</pubDate></item>
              <item><title>Premium strategy</title><link>https://example.test/paid</link>
                <category>Premium</category><pubDate>Thu, 13 Aug 2026 10:00:00 GMT</pubDate></item>
            </channel></rss>""", "application/rss+xml", "https://example.test/feed")

    result = fetch_feed(Client(), dt.date(2026, 8, 13), {
        "name": "test", "url": "https://example.test/feed", "exclude_terms": ["premium"]
    }, 10)
    assert len(result.candidates) == 1
    assert result.candidates[0].canonical_url == "https://example.test/free"


def test_page_paywall_marker_is_excluded():
    class Client:
        def get(self, url, **_kwargs):
            if url.endswith("/feed"):
                return Download(b"""<rss><channel><item><title>Trading study</title>
                  <link>https://example.test/paid</link><description>market liquidity</description>
                  <pubDate>Thu, 13 Aug 2026 10:00:00 GMT</pubDate></item></channel></rss>""",
                                "application/rss+xml", url)
            return Download(b"This post is for paying subscribers only", "text/html", url)

    result = fetch_feed(Client(), dt.date(2026, 8, 13), {
        "name": "test", "url": "https://example.test/feed",
        "exclude_page_terms": ["paying subscribers only"]
    }, 10)
    assert result.candidates == []


def test_crossref_uses_separate_theme_queries_and_deduplicates():
    class Client:
        def __init__(self):
            self.queries = []

        def get(self, _url, *, params, **_kwargs):
            self.queries.append(params["query"])
            payload = {"message": {"items": [{
                "DOI": "10.1234/trading",
                "title": ["Market microstructure study"],
                "abstract": "Order book liquidity and execution",
                "URL": "https://doi.org/10.1234/trading",
                "published": {"date-parts": [[2026, 8, 13]]},
            }]}}
            return Download(json.dumps(payload).encode(), "application/json", _url)

    client = Client()
    result = fetch_crossref(client, dt.date(2026, 8, 13), 100, "reader@example.test")

    assert len(client.queries) == len(THEME_QUERIES)
    assert all(" OR " not in query for query in client.queries)
    assert len(result.candidates) == 1
    assert set(result.candidates[0].metadata["discovery_themes"]) == set(THEME_QUERIES)


def test_ssrn_uses_doi_prefix_endpoint_and_finance_filter():
    class Client:
        def __init__(self):
            self.urls = []
            self.filters = []

        def get(self, url, *, params, **_kwargs):
            self.urls.append(url)
            self.filters.append(params["filter"])
            payload = {"message": {"items": [
                {
                    "DOI": "10.2139/ssrn.12345",
                    "title": ["<p>Liquidity and asset returns</p>"],
                    "abstract": "Evidence from financial markets",
                    "URL": "https://doi.org/10.2139/ssrn.12345",
                    "published": {"date-parts": [[2026, 8, 13]]},
                },
                {
                    "DOI": "10.2139/ssrn.99999",
                    "title": ["Clinical protein response"],
                    "abstract": "A medical study",
                    "URL": "https://doi.org/10.2139/ssrn.99999",
                    "published": {"date-parts": [[2026, 8, 13]]},
                },
                {
                    "DOI": "10.2139/ssrn.88888",
                    "title": ["International trade law and market access"],
                    "abstract": "A legal study of trade agreements",
                    "URL": "https://doi.org/10.2139/ssrn.88888",
                    "published": {"date-parts": [[2026, 8, 13]]},
                },
            ]}}
            return Download(json.dumps(payload).encode(), "application/json", url)

    client = Client()
    result = fetch_ssrn(client, dt.date(2026, 8, 13), 100, "reader@example.test")

    assert client.urls and set(client.urls) == {"https://api.crossref.org/prefixes/10.2139/works"}
    assert all(value.startswith("from-created-date:") for value in client.filters)
    assert [item.doi for item in result.candidates] == ["10.2139/ssrn.12345"]
    assert result.candidates[0].source == "SSRN"
    assert result.candidates[0].title == "Liquidity and asset returns"


def test_sciencedirect_keeps_paywalled_metadata_without_pdf():
    class Client:
        def __init__(self):
            self.calls = []

        def get(self, url, *, params, headers):
            self.calls.append((url, params, headers))
            payload = {"search-results": {"entry": [{
                "dc:title": "Execution costs in fragmented markets",
                "dc:description": "We study liquidity and price impact.",
                "prism:doi": "10.1016/j.example.2026.1",
                "prism:url": "https://api.elsevier.test/article/pii/S1",
                "prism:coverDate": "2026-08-15",
                "pii": "S1",
                "openaccess": "0",
                "link": [{"@ref": "scidir", "@href": "https://sciencedirect.test/article/S1"}],
            }]}}
            return Download(json.dumps(payload).encode(), "application/json", url)

    import os
    os.environ["TEST_ELSEVIER_KEY"] = "test-key"
    try:
        client = Client()
        result = fetch_sciencedirect(client, dt.date(2026, 8, 15), 100, "TEST_ELSEVIER_KEY")
    finally:
        os.environ.pop("TEST_ELSEVIER_KEY", None)

    assert client.calls
    assert {call[0] for call in client.calls} == {"https://api.elsevier.com/content/metadata/article"}
    assert all(call[1]["view"] == "STANDARD" for call in client.calls)
    assert all("pub-date IS 20260815" in call[1]["query"] for call in client.calls)
    assert len(result.candidates) == 1
    item = result.candidates[0]
    assert item.abstract == "We study liquidity and price impact."
    assert item.pdf_url is None
    assert item.is_open_access is False
    assert item.metadata["metadata_only"] is True
