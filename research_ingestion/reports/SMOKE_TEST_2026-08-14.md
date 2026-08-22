# Thematic + SSRN smoke test: 2026-08-14

## Outcome

- Status: pass for bounded discovery, thematic filtering, SSRN metadata,
  free-only AI classification, storage, and JSON output.
- Runtime: 243 seconds for the final complete run.
- Candidates: 93 Crossref + 47 SSRN = 140 deduplicated.
- Deterministic rejects: 48.
- Ranked survivors beyond the deep-review cap: 52.
- Free-only OmniRoute reviews: 40; estimated input tokens: 56,710.
- Accepted at the evidence-calibrated 0.75 threshold: 12.
- Public PDFs: 0. SSRN's Delivery endpoint returned HTTP 403 to the automated
  client, so SSRN items remained title/link-only rather than bypassing access
  controls.
- Email: deliberately disabled.

Outputs are `data/accepted/2026-08-14.json`,
`data/reading/2026-08-14.json`, and `data/runs/2026-08-14.json`.

## Quality observations

The accepted set covers cryptocurrency pricing, interest-rate/bond risk,
minimum-variance covariance estimation, intraday SPX options, portfolio
construction, cross-sectional asset pricing, intraday information clocks,
macro-announcement stock pricing, sentiment-driven risk premia, ML forecasting,
automated strategy pipelines, and stablecoin basis trading. Raising the quality
threshold from 0.62 to 0.75 removed generic banking, reserve-currency,
regulatory, and investor-survey items observed in the calibration run.

## Operational findings

- Crossref does not support Boolean operators in its general query field. The
  pipeline now performs twelve separate trading-theme queries.
- SSRN's direct search pages reject automated access. New SSRN deposits are
  discovered through the public Crossref `10.2139` DOI-prefix endpoint using
  Crossref creation dates, then restricted to `10.2139/ssrn.*` records with
  finance/trading language.
- Deep review is capped at the top 40 deterministic survivors. Permanent HTTP
  4xx responses and PDF failures are not retried. This reduced the formerly
  unbounded run to under five minutes.
- ScienceDirect returned HTTP 401. Its API key must be rotated/replaced before
  that source can contribute.
- Warning text now redacts API keys and bearer credentials before persistence or
  email delivery.
- Two model responses were truncated in the calibration run. Structured JSON
  output and a 750-token per-response ceiling were added; the subsequent live
  compatibility check succeeded.

