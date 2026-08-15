# One-day smoke test: 2026-08-13

## Outcome

- Status: provisional pass for discovery, filtering, PDF extraction, storage, and JSON output.
- Candidates after source collection: 3.
- Accepted by deterministic fallback: 2.
- Rejected by deterministic threshold: 1.
- Public PDFs downloaded and text-extracted: 1 (44,527 extracted characters).
- OmniRoute calls: 0; the client failed closed because no free-only route was configured.
- Email: deliberately disabled for the smoke run.
- Digest delivery is configured to include pipeline warnings, including any AI token/quota stop.

The compact reading output is `data/reading/2026-08-13.json`; the complete
accepted-item manifest is `data/accepted/2026-08-13.json`; source warnings and
counts are in `data/runs/2026-08-13.json`.

## Source observations

- Crossref returned one accepted academic paper with a public CC BY 4.0 PDF.
- Quantocracy returned one accepted title/link roundup.
- A premium Aligrithm item appeared in its RSS feed. A page-level public-access
  check now excludes it, and the corrected smoke run returned zero Aligrithm
  candidates for the date.
- Concretum returned one candidate that failed the trading-quality threshold.
- arXiv returned HTTP 429 despite bounded retries and polite delay; this remains
  a live-source warning rather than a silent zero.
- OpenAlex and ScienceDirect were skipped because their free API keys were not set.
- The official BIS research feeds responded successfully but had no items dated
  2026-08-13.

## Interpretation

The pipeline mechanics work, but the two accepted items are not evidence that
the final quality threshold is calibrated. The academic paper is topically
relevant but should be judged by OmniRoute once the free-only route is running.
The next operational smoke test should enable OpenAlex, ScienceDirect,
OmniRoute, and Gmail OAuth, then inspect the top-25 email and false-positive rate.
