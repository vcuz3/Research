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
- Confirmed (2026-08-16 full 1-minute audit): the Parquet contains 4,718,718
  unique, physically ordered bars from 2017-08-17 04:00 UTC through 2026-08-12
  23:59 UTC. All 120 raw ZIPs match their Binance SHA-256 files, and the
  Parquet hash matches `data/binance_spot_btcusdt_1m/BTCUSDT-1m-data-quality.json`.
- Confirmed: the 1-minute Parquet has no nulls, duplicate timestamps,
  out-of-order rows, non-finite/non-positive prices, OHLC inconsistencies,
  negative activity, or taker-volume-over-total-volume violations. Its 24,002
  zero-trade bars are flat and have zero volume fields.
- Confirmed: coverage is not continuous. There are 34 gaps totaling 8,561
  missing one-minute bars (2017: 496; 2018: 3,975; 2019: 1,764; 2020: 1,253;
  2021: 993; 2023: 80), plus the 240-minute pre-listing boundary on 2017-08-17.
- Confirmed: 21,602 early bars are not aligned to UTC minute boundaries:
  20,401 rows at +20.799 seconds in `raw/monthly/BTCUSDT-1m-2017-12.zip` and
  1,201 rows at +14.789 seconds in `raw/monthly/BTCUSDT-1m-2018-02.zip`.
  Seventeen retained bars have nonstandard durations. One impossible raw row
  (`close_time < open_time`) in `raw/monthly/BTCUSDT-1m-2020-12.zip` was
  correctly rejected during conversion.

## Known risks and open questions

- Provisional: archive coverage and gap counts remain unknown until the full downloader run completes.
- Binance archive revisions can change checksums; rerun the downloader to verify cached inputs against current official checksums.
- The 1-minute dataset is suitable only with explicit gap handling. Do not
  forward-fill missing OHLCV bars. Strategies using UTC minute slots should
  rebuild or explicitly exclude the two off-grid early blocks; ideally rebuild
  them from trades/aggTrades if exact UTC-minute bars are required.
- The 1-minute dataset currently ends on 2026-08-12 and must be refreshed for
  current-date use.

## Next actions

1. Run each desired full download and inspect its interval-specific
   `BTCUSDT-<interval>-data-quality.json` before using the data in research.

## Promotion candidates

- None.
