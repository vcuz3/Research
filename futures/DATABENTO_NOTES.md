# Databento 1-minute futures data

Use Databento's CME Globex dataset (`GLBX.MDP3`) with schema `ohlcv-1m`.

For a TradingView-like continuous front contract, start with volume-ranked continuous symbology:

- `NQ.v.0`
- `ES.v.0`
- `GC.v.0`

Run a cost estimate first:

```powershell
.\.venv\Scripts\python.exe futures\scripts\download_databento_ohlcv.py --start 2011-08-01 --end 2026-07-15 --estimate-only
```

Download Parquet:

```powershell
.\.venv\Scripts\python.exe futures\scripts\download_databento_ohlcv.py --start 2011-08-01 --end 2026-07-15
```

Download gold only:

```powershell
.\.venv\Scripts\python.exe futures\scripts\download_databento_ohlcv.py --symbols GC --start 2011-08-01 --end 2026-07-17
```

Outputs go to `futures\data\databento`.

The script also writes a `*_roll_map.csv` file that resolves the continuous instrument IDs to raw contract symbols, e.g. `NQU6`, `ESU6`, or `GCQ6`.

## Back-adjust rolls

Databento returns unadjusted continuous futures. To remove visible rollover jumps while keeping the latest prices unchanged, run additive backwards adjustment after downloading:

```powershell
.\.venv\Scripts\python.exe futures\scripts\adjust_continuous_rolls.py futures\data\databento\NQ_ohlcv-1m_NQv0_20110801_20260715.parquet
.\.venv\Scripts\python.exe futures\scripts\adjust_continuous_rolls.py futures\data\databento\ES_ohlcv-1m_ESv0_20110801_20260715.parquet
.\.venv\Scripts\python.exe futures\scripts\adjust_continuous_rolls.py futures\data\databento\GC_ohlcv-1m_GCv0_20110801_20260717.parquet
```

This writes `*_back_adjusted_additive.parquet` plus `*_roll_adjustments.csv`.

Use `--method additive` for chart-style continuous point prices. Use `--method ratio` only if you want the older history scaled to preserve percentage returns.

The default roll gap estimate is `new contract open - old contract previous close` at each `instrument_id` change. This is a practical approximation using only the downloaded continuous file.

Important: Databento continuous futures are not back-adjusted. The `v` roll rule ranks contracts by trading volume, and `.0` selects the most active/front contract for that rule. This is usually the right starting point for chart-style continuous ES/NQ, but roll gaps remain real price gaps.

As of the smoke test on 2026-07-16 Sydney time, `GLBX.MDP3` was available through `2026-07-15 14:40:00 UTC`. A 2011-08-01 to 2026-07-15 estimate for both NQ and ES was about `$37.67`.

## GC download completed

Gold futures were downloaded on 2026-07-18 Sydney time:

- Raw: `futures\data\databento\GC_ohlcv-1m_GCv0_20110801_20260717.parquet`
- Back-adjusted: `futures\data\databento\GC_ohlcv-1m_GCv0_20110801_20260717_back_adjusted_additive.parquet`
- Roll adjustments: `futures\data\databento\GC_ohlcv-1m_GCv0_20110801_20260717_back_adjusted_additive_roll_adjustments.csv`
- Roll map: `futures\data\databento\GC_ohlcv-1m_GCv0_20110801_20260717_roll_map.csv`
- Dataset condition calendar: `futures\data\databento\GLBX_MDP3_dataset_condition_20110801_20260717.csv`

The GC file contains 5,186,870 one-minute bars from `2011-08-01 00:00:00 UTC` through `2026-07-16 23:59:00 UTC`, with 75 raw contract segments and 74 additive roll adjustments. The Databento cost estimate returned `$0.0000`.

For `GLBX.MDP3` over this range, the dataset condition calendar has 4,666 available days, 28 degraded days, and 13 missing days.

## ES and YM 1-second downloads completed

ES and YM 1-second OHLCV futures were downloaded on 2026-07-25 Sydney time:

- ES raw: `futures\data\databento\ES_ohlcv-1s_ESv0_20100606_20260724.parquet`
- ES roll map: `futures\data\databento\ES_ohlcv-1s_ESv0_20100606_20260724_roll_map.csv`
- YM raw: `futures\data\databento\YM_ohlcv-1s_YMv0_20100606_20260724.parquet`
- YM roll map: `futures\data\databento\YM_ohlcv-1s_YMv0_20100606_20260724_roll_map.csv`

Before download, no existing `ES_ohlcv-1s*` or `YM_ohlcv-1s*` file was present in
`futures\data\databento`. The Databento estimate for `GLBX.MDP3`, schema
`ohlcv-1s`, symbols `ES.v.0` and `YM.v.0`, from `2010-06-06` through exclusive
`2026-07-24`, returned `$0.0000` for each symbol and `$0.0000` total. The
download command used `--require-zero-cost`.

Verified outputs:

- ES: 148,538,728 rows, 1,532,409,672 bytes.
- YM: 98,540,418 rows, 1,128,780,196 bytes.

Databento emitted reduced-quality warnings for some degraded or missing dates
inside the requested range. Treat those as data-quality findings to quantify
before relying on affected periods.

## Additional 1-minute futures download completed

On 2026-07-30 Sydney time, 25 additional volume-ranked continuous futures were
downloaded with schema `ohlcv-1m`, request range `[2010-06-06, 2026-07-28)`, and
Databento cost estimate `$0.0000` for every symbol:

- Energy: `CL.v.0`, `MCL.v.0`, `NG.v.0`, `RB.v.0`, `HO.v.0`, `BZ.v.0`.
- Additional metals: `SI.v.0`, `HG.v.0`, `MGC.v.0`, `PL.v.0`, `PA.v.0`.
- Interest rates: `ZN.v.0`, `ZB.v.0`, `ZF.v.0`, `ZT.v.0`, `UB.v.0`,
  `SR3.v.0`, `ZQ.v.0`.
- Exchange-traded FX: `6E.v.0`, `6B.v.0`, `6J.v.0`, `6A.v.0`, `6C.v.0`,
  `6S.v.0`, `6N.v.0`.

Verified outputs under `futures/data/databento/` contain 102,408,470 rows and
1.307 GiB of Parquet data in total. Every file has a readable Parquet footer,
its row count matches its metadata JSON, timestamps are ordered, and its roll
map is present. Most contracts begin on 2010-06-07 and end on 2026-07-27; MGC
begins 2010-10-03, MCL begins 2021-07-11, and SR3 begins 2018-05-06 because of
their available contract histories.

The downloader now retries each failed chunk up to four times with exponential
backoff. This was added after Databento terminated one long response early with
`Response ended prematurely`. The downloads also emitted Databento warnings for
degraded dates; run the workspace data-quality gate before interpreting a
backtest over affected periods.
