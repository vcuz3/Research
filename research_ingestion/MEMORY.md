# Project Memory: Trading Research Ingestion

## Scope

- Objective: Download public trading-related academic papers and institutional reports daily for local reading and future systematic-research intake.
- Markets: All asset classes and trading-research themes.
- Data coverage: Daily forward collection; operator-selected manual date ranges; no default backfill.
- Current phase: MVP implemented; external integrations pending.

## Current status

- Verdict: provisional
- Last verified: 2026-08-15
- Lifecycle phase: implementation
- Reproduction command: `python -m research_ingestion.cli run --date 2026-08-13 --no-email`
- Primary evidence: `tests/`, `reports/SMOKE_TEST_2026-08-13.md`, and smoke-test output under `data/runs/`.

## Confirmed findings

- Eight local tests pass for classification, fail-closed AI routing (including gateway outage), RSS/paywall parsing, deduplication, manifests, and abstract reconstruction.
- The corrected 2026-08-13 live smoke run discovered 3 candidates, accepted 2 by deterministic fallback, rejected 1, and downloaded/extracted 1 public PDF.
- Page-level access checking excluded the premium Aligrithm RSS item found by the first run.

## Provisional hypotheses

- Public APIs and feeds provide enough daily candidates for a useful top-25 reading email.
  - Kill test: one-day smoke run yields no relevant accepted items or excessive false positives.
  - Evidence needed: inspected daily reading JSON and source/run counts.

## Decisions and constraints

- Schedule: 22:00 Australia/Sydney with catch-up after missed runs.
- Accepted items only in the main manifest; a second compact JSON is optimized for skimming.
- Download only public PDFs. Public pages without PDFs are represented by title and canonical link.
- Gmail delivery uses OAuth and sends at most 25 titles/links.
- AI calls go only to a self-hosted OmniRoute free-only route. Quota, payment, or token-limit conditions stop AI and emit warnings; there is no paid fallback.
- Retention is indefinite and manually managed.

## Known risks and open questions

- OmniRoute is not installed or running in the workspace as of 2026-08-14.
- Gmail OAuth client credentials have not been provided.
- Feed-only sources may not expose all items after a long offline interval.
- ScienceDirect metadata requires a free API key; full PDF retrieval remains limited to explicitly open-access content.
- arXiv returned HTTP 429 during all 2026-08-13 live smoke attempts; the pipeline reports this explicitly and continues other sources.

## Next actions

1. Add free OpenAlex and Elsevier keys and repeat a one-day source smoke test.
2. Configure a verified free-only OmniRoute route and inspect classification quality.
3. Complete Gmail OAuth consent, install the scheduled task, and run a delivery test.

## Promotion candidates

- None.
