# Findings

## Result

**GO (exploratory only).** The pooled gross mean is +0.0413 R per trade
(date-cluster bootstrap 95% CI +0.0234 to +0.0592);
4/4 pairs are positive. This is discovery evidence because all
available history was inspected and no claim-matched path-preserving null has
yet been run.

## Gross baseline by pair

| Asset | Trades | Mean R | Mean pips | Win rate | Profit factor |
| --- | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 3369 | +0.0424 | +0.497 | 52.7% | 1.090 |
| GBPUSD | 3355 | +0.0464 | +0.740 | 53.0% | 1.099 |
| AUDUSD | 3542 | +0.0408 | +0.326 | 52.6% | 1.087 |
| NZDUSD | 3491 | +0.0358 | +0.367 | 52.4% | 1.075 |

## Pooled cost sensitivity

| Round-trip cost (pip) | Mean R | Mean pips | Daily Sharpe |
| ---: | ---: | ---: | ---: |
| 0.0 | +0.0413 | +0.479 | +1.073 |
| 0.2 | +0.0233 | +0.279 | +0.596 |
| 0.5 | -0.0036 | -0.021 | -0.121 |
| 1.0 | -0.0485 | -0.521 | -1.306 |

Exit reasons: `{"opposite_signal": 412, "stop": 6442, "stop_ambiguous": 19, "stop_gap": 9, "target": 6754, "time": 121}`.

The 2020+ gross mean is +0.0265 R pooled, with all four
pairs still positive (EURUSD +0.0269, GBPUSD +0.0306, AUDUSD +0.0274, NZDUSD +0.0210).
This is an inspected stability slice, not a holdout.

The low-volatility gate fires on 0.5% to
66.1% of eligible bars across asset-by-UTC-hour cells. That
large clock profile means the gate is also a time-of-day selector and requires
a matched-rate or same-slot control before attributing the result to volatility.

## Interpretation limits

- Prices are midpoint OHLC; the cost grid is a sensitivity, not measured spread.
- Brackets are replayed at 1-minute grain. Any stop/target collision within one
  minute is assigned to the stop, but finer sequencing remains unknown.
- The four USD pairs are correlated and do not constitute four independent tests.
- Capacity, financing, live latency, and executable bid/ask spreads are not modeled.

## Configuration

```json
{
  "assets": [
    "EURUSD",
    "GBPUSD",
    "AUDUSD",
    "NZDUSD"
  ],
  "data_pattern": "../data/clean/{asset}_1m_clean.parquet",
  "timeframe": "30min",
  "atr_period": 14,
  "atr_percentile": 0.15,
  "percentile_lookback": 100,
  "breakout_lookback": 10,
  "stop_atr": 1.5,
  "target_atr": 1.5,
  "max_holding_hours": 12.0,
  "require_complete_candles": true,
  "round_trip_cost_pips": [
    0.0,
    0.2,
    0.5,
    1.0
  ],
  "pip_size": 0.0001
}
```
