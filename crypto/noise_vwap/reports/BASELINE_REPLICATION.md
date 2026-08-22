# Baseline Replication

- Baseline experiment ID: EXP-0001
- Source version: local audited NQ Noise-Area + VWAP project as inspected on
  2026-08-16.
- Data scope/fingerprint: Binance Spot BTCUSDT 1-minute Parquet, archive hash
  recorded in `../../data/binance_spot_btcusdt_1m/BTCUSDT-1m-data-quality.json`;
  loaded 2019-01-01 through 2026-08-12.
- Frozen config: weekday 09:30-15:59 ET, 30-minute decisions, 90-session band,
  90% history floor, 5 bps/side, fixed one-unit notional.
- Exact command: `python crypto/noise_vwap/backtest_engine/run_notebook.py`

## Claim results

| Claim ID | Published | Local | Tolerance | Status | Explanation/evidence |
| --- | ---: | ---: | ---: | --- | --- |
| CLM-001 | causal next-open fills | zero timing violations | zero | passed | notebook execution audit |
| CLM-002 | strictly prior same-slot history | manual parity error 0 | `1e-12` | passed | notebook feature audit |
| CLM-003 | no synthetic missing bars | 4,090 missing minutes reported; none filled | zero synthetic bars | passed | notebook data audit |
| CLM-004 | no published BTC value | IS Sharpe -0.223; OOS 0.230 | descriptive | provisional | EXP-0001 |

## Verdict

The frozen transfer cell narrowly survives its prespecified screen but is not a
GO. OOS gross expectancy is 11.835 bps/trade against a 10 bps assumed round
trip, while in-sample performance and 2025-2026 are negative. Independent
review, a valid path-preserving null, and intended-venue execution evidence are
required before interpreting this as an edge.
