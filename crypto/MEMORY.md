# Project Memory: Crypto shared market data

## Scope

- Objective: Maintain reusable cryptocurrency market data and ingestion tooling.
- Instruments or markets: Binance Spot BTCUSDT, 1-minute and 1-second klines.
- Data coverage: 1-minute downloader supports 2017-08-17 onward; 1-second
  downloader supports 2020-01-01 onward, both through the last complete UTC day.
- Current phase: data acquisition.

## Current status

- Verdict: provisional
- Last verified: 2026-08-13
- Lifecycle phase: baseline
- Holdout status: consumed (historical market data intended for research)
- Reproduction command: `python crypto/data/download_binance_btcusdt_1m.py`
- Primary evidence: `data/download_binance_btcusdt_1m.py`, `data/test_download_binance_btcusdt_1m.py`

## Confirmed findings

- Confirmed: a live 2017-08-17 through 2017-08-18 smoke test verified the
  official monthly checksum and produced 2,640 valid bars with no internal
  gaps or duplicates; the first available bar was 2017-08-17 04:00 UTC.
- The full archive has not yet been downloaded or quality-audited.

## Decisions and constraints

- Confirmed: use official Binance Spot public archives for BTCUSDT 1-minute klines.
- Confirmed: retain checksummed raw archives and normalize mixed
  millisecond/microsecond source timestamps to UTC `timestamp[ms]` values in a
  typed, Zstandard-compressed Parquet output.
- Confirmed: report gaps and invalid rows; never silently fill missing bars.
- Confirmed: official Binance checksummed BTCUSDT 1-second monthly archives
  exist for 2020-01 and current-era months; store 1-second data separately.
- Confirmed: a live 2026-08-12 1-second smoke test verified the official daily
  checksum and produced exactly 86,400 bars from 00:00:00 through 23:59:59 UTC
  with no gaps or duplicates; Zstandard Parquet read-back passed.

## Known risks and open questions

- Provisional: archive coverage and gap counts remain unknown until the full downloader run completes.
- Binance archive revisions can change checksums; rerun the downloader to verify cached inputs against current official checksums.

## Next actions

1. Run each desired full download and inspect its interval-specific
   `BTCUSDT-<interval>-data-quality.json` before using the data in research.

## Promotion candidates

- None.
