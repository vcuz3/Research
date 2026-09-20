# Data Quality

EXP-0001 loaded 5.44-5.54 million minute rows per pair. All four sources have
zero duplicate timestamps, zero out-of-order timestamps, and zero invalid OHLC
rows. EURUSD/GBPUSD/AUDUSD begin 2011-07-19; NZDUSD begins 2011-12-06; all end
2026-07-17 20:59 UTC. SHA-256 fingerprints are recorded in the run artifact.

At 30 minutes, 180,868-182,632 complete decision candles remain per asset.
EURUSD/GBPUSD/AUDUSD have 3,849-3,850 incomplete nonempty buckets; NZDUSD has
751. These are reported then dropped. Rolling windows use complete tradable
candles: 13 ATR warm-up rows, 113 percentile warm-up rows, and 10 breakout
warm-up rows per pair are null by construction.

Detailed global, yearly, and UTC-hour coverage and gap counts are in:

- `artifacts/runs/EXP-0001/data_quality.csv`
- `artifacts/runs/EXP-0001/data_quality_by_year.csv`
- `artifacts/runs/EXP-0001/data_quality_by_utc_hour.csv`

The low-volatility selection rate varies from 0.5% to 66.1% across asset-hour
cells. This is not missing-data leakage, but it is a material time-of-day
selector that needs a matched-rate control.
