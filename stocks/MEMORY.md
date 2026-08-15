# Project Memory: Nasdaq-100 historical stocks

## Scope

- Objective: Download point-in-time Nasdaq-100 constituent 1-minute data without silently excluding former or delisted constituents.
- Instruments or markets: Nasdaq-100 equity securities and historical component changes.
- Data coverage: 2016-08-11 through 2026-08-11, London Strategic Edge 1-minute bars.
- Current phase: data-source qualification.

## Current status

- Verdict: blocked by incomplete multi-provider coverage.
- Last verified: 2026-08-11.
- Lifecycle phase: data intake.
- Reproduction command: `python stocks/download_nasdaq100_1m.py prepare`
- Primary evidence: `universe/provider_coverage_audit.csv` and `manifest.json`.

## Confirmed findings

- The historical universe is reconstructed causally from a current snapshot and component changes; former constituents are retained in `universe/membership_periods.csv`.
- LSE's visible stock catalog and candle endpoint omit multiple acquired/delisted historical constituents, so LSE alone cannot currently supply the complete requested universe.
- The downloader fails closed when this coverage gate is not satisfied.
- Databento `XNAS.ITCH` has `ohlcv-1m` only from 2018-05-01. It can provide 8,119,260 useful records for 29 LSE-gap tickers at an estimated USD 5.0814, fully repairing 7 gaps but leaving 30 tickers incomplete. Evidence: `DATABENTO_GAP_CHECK.md`.
- QuantConnect's AlgoSeek US Equities cloud dataset is a viable complete source: SIP-consolidated, minute resolution, explicitly survivorship-bias-free, with approximately 27,500 securities and coverage from January 1998. Its Security Master tracks delistings and ticker changes. Local download is a separate paid license and data must remain in LEAN format.

## Decisions and constraints

- Do not describe an LSE-only subset as survivorship-bias-free.
- Do not use `--allow-provider-gaps` for a backtest intended to make universe-wide claims.
- The workspace-root `.env` supplies `londonstrategicedge_api`; no secret is copied here.

## Known risks and open questions

- A second historical vendor or restored LSE symbols are required to fill missing names and ticker-history gaps.
- Even an LSE+Databento merge needs a pre-2018 delisted-stock source; Databento's Nasdaq-only bars also introduce a venue-definition mismatch versus consolidated bars.
- QuantConnect Cloud can avoid the mixed-vendor panel, but the cloud workflow must replace the requested generic local-Parquet archive. Current documented Quant Researcher local bulk cost is USD 11,760 for minute US Equities plus USD 600/year for the required Security Master.
- Same ticker symbols can represent different corporate identities; membership events are retained for audit.

## Next actions

1. Prefer a QuantConnect Cloud/LEAN implementation if platform-hosted data is acceptable.
2. If local files are mandatory, decide whether the QuantConnect LEAN-only download license and cost are acceptable; do not convert licensed files to Parquet.
3. Otherwise ask LSE to restore missing symbols or identify another pre-2018 delisted one-minute source.
