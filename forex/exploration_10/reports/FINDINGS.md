# Findings

## Current verdict

**NO-GO for parameter optimisation; WATCH only for the original gross effect.**

EXP-0001 found a small gross effect across all four pairs: 13,757 trades,
+0.0413 R and +0.479 pip per trade, with a date-cluster bootstrap 95% interval
of [+0.0234, +0.0592] R. It was cost-fragile: pooled expectancy became -0.0036 R
at a 0.5-pip round trip.

EXP-0002 searched 243 parameter combinations per asset using rolling five-year
training windows and forward validation at a 0.5-pip cost. It failed its frozen
kill test:

| Asset | WF trades | Mean net R | Selected Sharpe | Static baseline Sharpe | Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 1,599 | -0.0130 | -0.175 | -0.445 | +0.270 |
| GBPUSD | 1,246 | -0.0167 | -0.215 | +0.114 | -0.329 |
| AUDUSD | 865 | -0.0363 | -0.396 | -0.142 | -0.255 |
| NZDUSD | 1,114 | -0.0191 | -0.260 | -0.192 | -0.068 |
| **Pooled** | **4,824** | **-0.0195** | **-0.442** | **-0.292** | **-0.150** |

All four optimised forward books lost after the modeled cost. Training winners
looked strong (mean training Sharpe 0.72-0.94 by asset) but collapsed forward,
and 22 distinct configurations were selected across 32 asset-folds. This is
selection overfit, not stable adaptation.

## Reserved optimisation holdout

The interval from 2024-07-18 UTC through the archive end remains **untested by
the optimiser**. Predicate filtering loaded no timestamp later than 2024-07-17
23:59. The audit is in `artifacts/runs/EXP-0002/holdout_audit.json`.

Final pre-holdout fits were recorded but must not be scored yet:

| Asset | Locked configuration |
| --- | --- |
| EURUSD | 60min, ATR 28, percentile 0.15, stop 2.0 ATR, target 2.0 ATR |
| GBPUSD | 60min, ATR 28, percentile 0.20, stop 1.0 ATR, target 2.0 ATR |
| AUDUSD | 60min, ATR 14, percentile 0.15, stop 1.0 ATR, target 1.5 ATR |
| NZDUSD | 60min, ATR 14, percentile 0.15, stop 1.5 ATR, target 1.0 ATR |

Because the optimisation already failed walk-forward, these configurations do
not currently justify spending the reserved interval.

## Reporting correction

The EXP-0001 artifact used a business-day daily index, which omitted Sunday-UTC
FX exits from daily Sharpe only. Trade expectancy was unaffected. The corrected
calendar-day pooled Sharpes for costs 0.0/0.2/0.5/1.0 pip are respectively
1.126/0.636/-0.099/-1.314. Future code now uses calendar days and annualises by
sqrt(365).

## Remaining limitations

- Midpoint prices and fixed cost assumptions are not measured executable spreads.
- The ATR gate remains a strong time-of-day selector.
- No claim-matched path-preserving null or independent review is complete.
- EXP-0001 already inspected the reserved dates, so only future observations are
  genuinely clean for the original strategy thesis.
