# Project Memory: Trading Research Ingestion

## Scope

- Objective: Download public trading-related academic papers and institutional reports daily for local reading and future systematic-research intake.
- Markets: All asset classes and trading-research themes.
- Data coverage: Daily forward collection; operator-selected manual date ranges; no default backfill.
- Current phase: MVP implemented; OmniRoute, Gmail, and Google Drive connected.

## Current status

- Verdict: provisional
- Last verified: 2026-08-21
- Lifecycle phase: implementation
- Reproduction command: `python -m research_ingestion.cli run --date 2026-08-13 --no-email`
- Primary evidence: `tests/`, `reports/SMOKE_TEST_2026-08-13.md`, and smoke-test output under `data/runs/`.

## Confirmed findings

- Thirty-one local tests pass for configuration loading, classification, fail-closed AI routing, structured responses, RSS/paywall parsing, arXiv pacing, thematic/Crossref/SSRN/ScienceDirect metadata discovery, acceptance-gated OpenAlex/Unpaywall lookup, historical PDF repair, public-PDF fallback resolution, manual PDF inbox matching/import, credential redaction, email formatting, SMTP app-password delivery, delivery-only retry, Google Drive API and desktop-sync dated-library deduplication, manifests, and abstract reconstruction.
- The corrected 2026-08-13 live smoke run discovered 3 candidates, accepted 2 by deterministic fallback, rejected 1, and downloaded/extracted 1 public PDF.
- Page-level access checking excluded the premium Aligrithm RSS item found by the first run.
- Project `.env` values load automatically without overriding explicit process environment variables.
- A live OmniRoute classification through `free-research` returned valid structured JSON and accepted the trading-research fixture with relevance 0.90.
- OmniRoute authentication and local-only binding were verified after restart: unauthenticated `/v1/models` returned HTTP 401, the listener was `127.0.0.1:20128`, and an authenticated pipeline classification succeeded with relevance 0.90.
- Gmail OAuth with the narrow `gmail.send` scope is configured for the operator-selected sender. A live test message was accepted by Gmail for both configured recipients: `vd373094@gmail.com` and `antrading37@gmail.com`.
- Google Drive upload is authorized with a separate `drive.file` OAuth token for `antrading37@gmail.com`, enabled for daily runs, and uses a `Trading Research Library/YYYY/YYYY-MM-DD/` hierarchy.
- The final 2026-08-14 thematic/SSRN smoke run completed in 243 seconds: 140 deduplicated candidates, 40 free-only AI reviews, 12 accepted at threshold 0.75, and no paid/quota stop. Evidence: `reports/SMOKE_TEST_2026-08-14.md` and `data/runs/2026-08-14.json`.
- SSRN direct pages and its Delivery endpoint return HTTP 403 to the automated client. The compliant connector uses public Crossref prefix `10.2139`, Crossref creation dates, `ssrn.*` DOI validation, and finance anchors. PDFs remain title/link-only unless public metadata exposes a PDF.
- Deep review and AI calls are each capped at 120; the independent 180,000 estimated input-token ceiling remains fail-closed. PDF and permanent 4xx failures are not retried. API keys and bearer credentials are redacted from user-facing errors.
- Daily email entries contain title, abstract when available, and canonical link; source and relevance score remain omitted.
- Daily email is multipart plain text/HTML: HTML titles are bold and both formats label `abstract:` and `link:`. Every rejected candidate is now retained in `data/rejected/YYYY-MM-DD.json` with stage, reason, metadata, and available deterministic/AI scoring details.
- Drive OAuth was verified as `antrading37@gmail.com` on 2026-08-15. One accepted public PDF was uploaded successfully to `Trading Research Library/2026/2026-08-13`; automatic sync is enabled.
- The Windows task `Trading Research Ingestion` is installed and verified: daily at 22:00 Australia/Sydney, `StartWhenAvailable=True`, `--catch-up`, correct project virtual environment/working directory, overlapping runs disabled, and a four-hour execution limit. Its next scheduled run after installation is 2026-08-16 22:00.
- The full manual 2026-08-15 run completed in 483 seconds: 149 deduplicated candidates, 80 free-only AI calls (46,392 estimated input tokens), 12 accepted, 1 public PDF, successful Gmail delivery, and 1 Drive upload to `Trading Research Library/2026/2026-08-15`. The only warning was the known Elsevier Article Metadata HTTP 401. Evidence: `data/runs/2026-08-15.json`.
- ScienceDirect was disabled in `config/config.json` on 2026-08-19 after persistent Article Metadata HTTP 401 responses on every run from 2026-08-15 through 2026-08-19. Its connector is retained but will not be called unless explicitly re-enabled.
- The 2026-08-19 run exposed two separate operational failures: arXiv returned HTTP 429 for nine thematic requests, and local OmniRoute at `127.0.0.1:20128` refused connections after one attempted call. The run completed via deterministic fallback, accepting 25 items; treat that day's selection quality as provisional. Evidence: `data/runs/2026-08-19.json`.
- Consecutive arXiv requests are now paced three seconds apart, including after failures, matching official arXiv API guidance. The scheduled task now runs `scripts/run_scheduled.ps1`, which starts OmniRoute when port 20128 is down and waits up to 90 seconds before ingestion. Live verification on 2026-08-19 started OmniRoute successfully and authenticated `/v1/models` returned HTTP 200.
- Public-PDF discovery now handles relative and `property=` citation metadata, standard public PDF links, fallback after a failed direct URL, and auditable no-PDF reasons. The initial missing-PDF set for 2026-08-15 through 2026-08-19 comprised 61 accepted metadata/title-link records: 57 SSRN, 3 Crossref, and 1 Aligrithm item.
- The user explicitly approved sending accepted-paper DOIs to OpenAlex and Unpaywall with `vd373094@gmail.com` as the Unpaywall contact. Resolution is enabled only after acceptance; an executable privacy regression test confirms rejected DOI records do not reach the resolvers.
- Historical resolution for 2026-08-15 through 2026-08-19 attempted 61 missing accepted records and recovered 4 verified public PDFs: 2 arXiv copies, 1 Zenodo copy, and 1 publisher-hosted copy. All 4 were saved locally, hashed, added to the dated manifests, uploaded to the matching Drive folders, and independently verified in Drive as owned by `antrading37@gmail.com`. The remaining 57 had no verified public copy through OpenAlex, Unpaywall, or public landing metadata; most are SSRN records whose automated pages return HTTP 403. Evidence: `data/pdf_resolution/2026-08-15.json` through `2026-08-19.json`.
- The 2026-08-20 run completed with 15 accepted email entries but only 3 verified public PDFs; all 3 downloaded and uploaded successfully. The other 12 were SSRN metadata records with no OpenAlex/Unpaywall public copy, confirmed again by a same-night accepted-only repair run. This was not a Drive failure. Evidence: `data/runs/2026-08-20.json` and `data/pdf_resolution/2026-08-20.json`.
- Email now labels each entry `pdf: saved to Google Drive` or `pdf: no verified public copy available`. Scheduled resolver-only retries run at ages 1, 3, 7, and 14 days to accommodate OA-index lag without repeatedly accessing blocked SSRN/publisher landing pages.
- The scheduled pipeline now scans `pdf_downloads/` after daily ingestion. It validates each PDF, requires a unique accepted-item identifier plus exact normalized title (or a unique exact normalized title), preserves the inbox file, stores and hashes a byte-identical dated library copy, updates the catalogue/accepted/reading manifests, and uploads to the corresponding dated Drive folder. Ambiguous and invalid files fail closed and every scan is audited under `data/pdf_imports/`.
- Four manually downloaded SSRN PDFs were matched to the 2026-08-20 accepted manifest, copied into `data/raw/2026/08/20/ssrn/`, and uploaded successfully to `Trading Research Library/2026/2026-08-20`. Evidence: `data/pdf_imports/2026-08-20T141030-0000.json`.
- Scheduled discovery continued through 2026-08-24, but Gmail delivery failed for 2026-08-22 through 2026-08-24 with Google OAuth `invalid_grant` (expired or revoked refresh token); Drive failed for the same reason on 2026-08-24. The Windows task itself remained healthy and advanced `last_successful_date.txt` because delivery failures are currently warnings rather than run failures. Accepted counts awaiting email recovery are 6, 2, and 6 respectively. Evidence: `data/runs/2026-08-22.json` through `2026-08-24.json` and Windows Scheduled Task history checked 2026-08-25.
- Superseding the prior delivery failure: Gmail now uses SMTP/TLS with a dedicated app password, and Drive uses the signed-in Google Drive for desktop mount at `G:\My Drive`. Delivery-only recovery resent all three August 22-24 digests successfully without AI calls and copied the August 24 PDF into the desktop-synced library. Run reports now record `smtp_sent`; scheduled delivery retries cover the prior 30 days and return a task failure if still incomplete. Verified 2026-08-25.

## Provisional hypotheses

- Public APIs and feeds provide enough daily candidates for a useful top-25 reading email.
  - Kill test: one-day smoke run yields no relevant accepted items or excessive false positives.
  - Evidence needed: inspected daily reading JSON and source/run counts.

## Decisions and constraints

- Schedule: 22:00 Australia/Sydney with catch-up after missed runs.
- Accepted items only in the main manifest; a second compact JSON is optimized for skimming.
- Download only public PDFs. Public pages without PDFs are represented by title and canonical link.
- Gmail delivery uses SMTP/TLS with a dedicated app password and sends at most 25 accepted items.
- AI calls go only to a self-hosted OmniRoute free-only route. Quota, payment, or token-limit conditions stop AI and emit warnings; there is no paid fallback.
- Retention is indefinite and manually managed.

## Known risks and open questions

- Feed-only sources may not expose all items after a long offline interval.
- ScienceDirect is disabled because its metadata-only Article Metadata endpoint consistently returned HTTP 401 `AUTHORIZATION_ERROR`; Crossref/OpenAlex may still supply overlapping metadata.
- arXiv may still rate-limit requests despite the configured three-second pacing; HTTP 429 remains non-fatal and reduces that run's coverage.
- Google app passwords can be revoked by an account-password change or manually; Drive for desktop must be running and its `G:` mount available for prompt cloud synchronization. Delivery retries preserve failed work without rerunning AI.

## Next actions

1. Confirm the next scheduled arXiv run completes without HTTP 429 after pacing and that OmniRoute preflight succeeds unattended.
2. Inspect the first few scheduled daily digests and tune quality/source filters if needed.

## Promotion candidates

- None.
