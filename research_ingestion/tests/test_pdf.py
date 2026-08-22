from research_ingestion.http import Download
from research_ingestion.models import Candidate
from research_ingestion.pdf import download_public_pdf


def test_relative_property_pdf_metadata_is_downloaded():
    class Client:
        def get(self, url, **_kwargs):
            if url == "https://example.test/paper":
                return Download(
                    b'<html><meta property="citation_pdf_url" content="/files/paper.pdf"></html>',
                    "text/html",
                    url,
                )
            assert url == "https://example.test/files/paper.pdf"
            return Download(b"%PDF-1.7 public", "application/pdf", url)

    candidate = Candidate(source="test", title="Paper", canonical_url="https://example.test/paper")
    content, url, status = download_public_pdf(Client(), candidate, 1_000_000)

    assert content == b"%PDF-1.7 public"
    assert url == "https://example.test/files/paper.pdf"
    assert status == "downloaded"


def test_failed_direct_url_falls_back_to_public_landing_link():
    class Client:
        def get(self, url, **_kwargs):
            if url == "https://example.test/broken.pdf":
                raise RuntimeError("temporary direct-link failure")
            if url == "https://example.test/paper":
                return Download(
                    b'<html><a type="application/pdf" href="/working.pdf">PDF</a></html>',
                    "text/html",
                    url,
                )
            assert url == "https://example.test/working.pdf"
            return Download(b"%PDF-1.7 fallback", "application/pdf", url)

    candidate = Candidate(
        source="test",
        title="Paper",
        canonical_url="https://example.test/paper",
        pdf_url="https://example.test/broken.pdf",
    )
    content, url, status = download_public_pdf(Client(), candidate, 1_000_000)

    assert content == b"%PDF-1.7 fallback"
    assert url == "https://example.test/working.pdf"
    assert status == "downloaded"


def test_missing_pdf_records_auditable_reason():
    class Client:
        def get(self, url, **_kwargs):
            return Download(b"<html><title>No PDF</title></html>", "text/html", url)

    candidate = Candidate(source="test", title="Paper", canonical_url="https://example.test/paper")
    content, url, status = download_public_pdf(Client(), candidate, 1_000_000)

    assert content is None
    assert url is None
    assert status == "title_link_only: landing page exposed no public PDF link"
