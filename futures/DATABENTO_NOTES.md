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
