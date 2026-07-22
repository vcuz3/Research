# Baseline Replication - GC treated as XAU/USD

- Authoritative run: EXP-0003
- Config: `baseline_replication/configs/faithful_2024.json`
- Evidence: `artifacts/runs/EXP-0003/summary.json`, `trades_2024.parquet`, and
  `signal_funnel_2024.csv`
- Command: `python -m futures.gc.vwap_ema.scripts.run_baseline futures/gc/vwap_ema/artifacts/runs/EXP-0003`

## Verdict

**Stage 1: NO-GO.** The 2024 historical proxy has +0.1176R gross expectancy,
but the paper's required 0.24R cost makes it -0.1224R net. At 1% current-equity
risk, compounded return is -2.14%, Sharpe -0.525, and max drawdown 6.58%.

| Metric | Paper synthetic | Historical 2024 |
| --- | ---: | ---: |
| Trades | 247 | 17 |
| Win rate | 45.3% | 29.4% |
| Gross expectancy | not consistently stated | +0.1176R |
| Net expectancy | +0.414R | -0.1224R |
| Net profit factor | 1.76 | 0.743 |
| 1%-risk return | +102.2% | -2.14% |
| Sharpe | 3.99 | -0.525 |
| Max drawdown | 5.1% | 6.58% |

The paper's 247 trades are not a historical count. Section 6.1 samples 247
outcomes from assumed probabilities, and section 7.2 confirms that historical
bar validation remained outstanding. The local count must not be tuned to it.

## Signal-count audit

There are 18 raw signals in 2024: 15 long and 3 short. One occurs in the FOMC
entry blackout, leaving 17 executed trades. The cumulative funnel shows the
EMA50 touch/close and rejection-candle conjunction is the principal bottleneck;
the volume threshold reduces the final candidates further.

## Context and data quality

The 2011-2026 contextual run has 201 trades and fails before cost: -0.0292R
gross and -0.2692R net per trade, with -42.4% compounded return.

All 17 primary trade dates have usable 1-second streams. The 15m data has no
duplicate/out-of-order keys, no intraday contract rolls, and no 2024 feature
NaNs. Twelve of 259 2024 sessions are incomplete (69 missing 15m buckets); the
engine liquidates on the actual last bar. Detailed per-year and per-slot counts
are in `summary.json`.

## Source limitations

This is the closest deterministic historical test, not a literal reproduction
of the unpublished Monte Carlo sample. Section 4.3's VWAP partial is internally
inconsistent with entering already beyond VWAP, and the news-position stop is
manual and undefined. Neither was invented. The paper's NY-session and fixed-
UTC clocks also conflict; the frozen baseline uses NY-local time.
