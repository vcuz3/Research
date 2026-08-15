import datetime as dt

from research_ingestion.connectors import _invert_abstract, fetch_feed
from research_ingestion.http import Download


def test_openalex_abstract_reconstruction():
    assert _invert_abstract({"Trading": [0], "works": [1]}) == "Trading works"


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
