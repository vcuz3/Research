# Trading Research Ingestion Project Guide

## Objective

Build an auditable local ingestion pipeline for public trading-related academic
papers and institutional reports. Outputs are reading aids and source records,
not validated trading evidence.

## Project map

| Concern | Location |
| --- | --- |
| Runtime configuration | `config/config.json` |
| Source adapters | `src/research_ingestion/connectors.py` |
| Filtering and AI classification | `src/research_ingestion/classify.py` |
| Storage and manifests | `src/research_ingestion/storage.py` |
| Gmail SMTP delivery | `src/research_ingestion/emailer.py` |
| Google Drive desktop-sync library | `src/research_ingestion/drive.py` |
| Scheduling | `scripts/install_scheduled_task.ps1` |
| Tests | `tests/` |
| Durable status | `MEMORY.md` |

## Commands

```powershell
python -m pip install -e .[email,test]
python -m pytest
python -m research_ingestion.cli run --date 2026-08-13 --no-email
python -m research_ingestion.cli run --from 2026-08-01 --to 2026-08-07 --no-email
python -m research_ingestion.cli run --catch-up
python -m research_ingestion.cli authorize-drive
python -m research_ingestion.cli resolve-pdfs --from 2026-08-15 --to 2026-08-19
python -m research_ingestion.cli import-pdfs
python -m research_ingestion.cli retry-delivery --days 30
```

## Operating conventions

- Calendar timezone: `Australia/Sydney`.
- The scheduled task runs daily at 22:00 and has `StartWhenAvailable` enabled.
- `--catch-up` processes every calendar date after the last successful scheduled
  date through today. API sources are date-queryable; RSS catch-up is limited by
  each feed's retained history.
- Raw PDFs are immutable and named by stable document ID plus content hash.
- The catalogue uses SQLite; per-day accepted and reading manifests are JSON.
- Every non-accepted candidate is retained in `data/rejected/YYYY-MM-DD.json`
  with its rejection stage/reason and the deterministic or AI scores available
  at that stage. This supports false-negative review and threshold tuning.
- Secrets are environment variables or ignored files under `secrets/`.
- Google Drive for desktop is signed into the library account. The pipeline
  copies accepted PDFs into its local `My Drive/Trading Research Library/YYYY/
  YYYY-MM-DD/` tree, verifies the copied hash, and deduplicates by content hash.
  Drive for desktop performs cloud synchronization; title/link-only items are
  not copied.
- Academic API discovery uses separate queries for market microstructure,
  momentum/trend, mean reversion, volatility/derivatives, portfolio/risk,
  financial machine learning, asset-pricing factors, macro trading, digital
  assets, research methods, event-driven trading, and alternative data.
- Consecutive arXiv API calls are separated by three seconds in accordance
  with arXiv's API guidance. A failed or rate-limited request does not bypass
  the delay before the next theme.
- SSRN discovery uses public Crossref metadata for DOI prefix `10.2139`, then
  requires an `ssrn.*` DOI and finance/trading language. Direct SSRN scraping is
  intentionally disabled because its search and abstract pages reject automated
  clients. Public PDFs are downloaded only when Crossref exposes a public PDF or
  the public landing page supplies one.
- Deterministic survivors are ranked and only the top 120 receive PDF resolution
  and free-model review. This bounds daily runtime and aligns deep review with
  the configured AI call cap. The current AI acceptance threshold is 0.75.
- ScienceDirect discovery is disabled in configuration after repeated Elsevier
  Article Metadata HTTP 401 responses. The connector remains available for a
  future explicit re-enable if Elsevier grants the required entitlement.
- Digest emails are multipart plain text/HTML. HTML titles are bold, followed
  by `abstract:` when available, an explicit `pdf:` availability line, and
  `link:` before the canonical URL.
- Gmail delivery uses SMTP over TLS with a dedicated Google app password stored
  only in the ignored project environment. This avoids Testing-mode OAuth's
  seven-day refresh-token expiry. Changing the Google account password or
  revoking the app password requires creating a replacement.
- The scheduled wrapper checks localhost port 20128, starts OmniRoute as a
  hidden background daemon when needed, waits up to 90 seconds for readiness,
  and then invokes catch-up. Failure preserves deterministic fallback.
- Public-PDF discovery follows source-provided URLs and standard PDF metadata
  or links exposed by public landing pages. Relative links are resolved, one
  failed PDF URL does not prevent trying alternatives, and unresolved items
  retain an auditable reason in `download_status`.
- After an item passes acceptance, its DOI may be sent to the explicitly
  configured OpenAlex and Unpaywall resolvers to locate verified open-access
  repository copies. Rejected-item DOIs are never sent. Unpaywall uses the
  configured contact email and neither resolver is a paywall bypass.
- `resolve-pdfs` repairs already-accepted date ranges without rerunning AI or
  resending email. It updates accepted/reading manifests, writes immutable-style
  audit detail under `data/pdf_resolution/`, and uploads only newly recovered
  files to the corresponding Drive folders.
- After each scheduled run, unresolved accepted records are retried at ages 1,
  3, 7, and 14 days using resolver-only mode. This accommodates repository
  indexing lag without repeatedly requesting blocked SSRN/publisher pages.
- `pdf_downloads/` is a non-destructive manual-download inbox. Each scheduled
  run validates PDFs, extracts metadata and first-page text, matches only a
  unique accepted identifier or exact normalized title, copies matched bytes
  into the dated raw library, updates both manifests and the catalogue, and
  uploads to that article date's Drive folder. Invalid, ambiguous, unmatched,
  and already-backed items remain untouched and are audited in
  `data/pdf_imports/`.
- Each scheduled run retries failed email and Drive deliveries from the prior
  30 days using saved accepted manifests. This does not rerun discovery, AI, or
  ranking. A still-failed retry makes the Windows task return a nonzero result.

## Zero-cost AI boundary

The pipeline calls exactly one local, OpenAI-compatible OmniRoute base URL and
one configured model/route. It does not possess paid-provider credentials and
does not retry through another model or endpoint. Configure that OmniRoute route
to contain only free providers/models and no billing-enabled fallback. Local
per-run call and token estimates are hard caps. HTTP 402/429 and quota-related
responses disable further AI calls for the run and create a warning.
