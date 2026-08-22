import datetime as dt

import pytest

from research_ingestion.classify import AIResult
from research_ingestion.connectors import SourceResult
from research_ingestion.models import Candidate
from research_ingestion.pipeline import run_day


@pytest.mark.parametrize("accepted,expected_resolver_calls", [(False, 0), (True, 1)])
def test_doi_resolver_is_called_only_after_acceptance(monkeypatch, tmp_path, accepted, expected_resolver_calls):
    candidate = Candidate(
        source="Crossref",
        title="Trading paper",
        abstract="A systematic trading strategy.",
        canonical_url="https://doi.org/10.1/test",
        doi="10.1/test",
        document_type="academic_paper",
    )

    class Client:
        def close(self):
            pass

    class AI:
        calls = 1
        estimated_input_tokens = 10
        stopped_reason = None

        def classify(self, *_args):
            return AIResult(
                "classified",
                accepted=accepted,
                relevance_score=0.9 if accepted else 0.1,
                topics=["strategy"],
                reason="test verdict",
            )

    resolver_calls = []

    def fake_download(*_args, **kwargs):
        if kwargs.get("resolver_only"):
            resolver_calls.append(True)
        return None, None, "title_link_only: fixture"

    monkeypatch.setattr("research_ingestion.pipeline.PublicHttpClient", Client)
    monkeypatch.setattr("research_ingestion.pipeline.ZeroCostOmniRoute", lambda _config: AI())
    monkeypatch.setattr(
        "research_ingestion.pipeline.collect_all",
        lambda *_args: [SourceResult("Crossref", [candidate], [])],
    )
    monkeypatch.setattr("research_ingestion.pipeline.deterministic_classify", lambda _candidate: (2, ["strategy"]))
    monkeypatch.setattr("research_ingestion.pipeline.download_public_pdf", fake_download)

    config = {
        "ai": {"max_calls_per_run": 120},
        "deterministic_min_score": 2,
        "max_candidates_for_deep_review": 120,
        "quality_threshold": 0.75,
        "download_max_bytes": 1_000_000,
        "public_pdf_resolution": {"enabled": True},
        "drive": {"enabled": False},
        "email_recipients": ["reader@example.test"],
        "email_top_n": 25,
    }
    report = run_day(
        tmp_path, config, dt.date(2026, 8, 20), send_email=False, sync_drive=False
    )

    assert report["status"] == "completed"
    assert len(resolver_calls) == expected_resolver_calls
