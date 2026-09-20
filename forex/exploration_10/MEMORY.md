# Project Memory: Low-volatility false-breakout reversion

## Scope

- Objective: test and tune contrarian 10-bar breakouts in low-ATR regimes.
- Instruments: EURUSD, GBPUSD, AUDUSD, NZDUSD.
- Data: clean 1-minute midpoint OHLC, 2011-07-19 to 2026-07-17; NZD starts 2011-12-06.
- Current phase: baseline and walk-forward optimisation complete; validation pending.

## Current status

- Verdict: NO-GO for optimisation; provisional WATCH for the gross baseline.
- Last verified: 2026-09-19.
- EXP-0001: baseline complete, independent review pending.
- EXP-0002: 243-configuration per-asset walk-forward rejected, review pending.
- Engine audit: 11 deterministic tests pass.
- Execution: completed-bar signal, next available 1-minute open, frozen brackets,
  adverse 1-minute collision rule, one position per pair.
- Optimisation holdout: 2024-07-18 onward was not loaded or scored by EXP-0002.
  It is not thesis-clean because EXP-0001 previously inspected it.
- Evidence: `reports/FINDINGS.md`, `artifacts/runs/EXP-0001/`, `artifacts/runs/EXP-0002/`.

## Provisional findings

- EXP-0001: 13,757 trades, +0.0413 R and +0.479 pip gross per trade; all four
  pairs positive; cluster-bootstrap 95% CI [+0.0234,+0.0592] R.
- Gross economics are fragile: pooled expectancy is -0.0036 R at 0.5 pip cost.
- EXP-0002 walk-forward: selected policy -0.0195 net R/trade, -0.442 daily
  Sharpe versus static baseline -0.292; all four selected asset books negative.
- Training winners (mean Sharpe 0.72-0.94) collapsed forward. Twenty-two distinct
  configs appeared across 32 selections: strong evidence of selection overfit.
- ATR gate remains a clock selector (asset-hour firing rates 0.5%-66.1%).

## Locked but untested optimisation-holdout parameters

- EURUSD: 60min / ATR28 / p15 / stop2.0 / target2.0.
- GBPUSD: 60min / ATR28 / p20 / stop1.0 / target2.0.
- AUDUSD: 60min / ATR14 / p15 / stop1.0 / target1.5.
- NZDUSD: 60min / ATR14 / p15 / stop1.5 / target1.0.

Do not evaluate these on data from 2024-07-18 onward without a new explicit
instruction and preregistered experiment. The failed walk-forward rule does not
currently justify spending that reserve.

## Decisions and corrections

- Selection objective is calendar-day Sharpe of net R at 0.5 pip; five-year
  rolling train, one-year validation, minimum 200 training trades.
- EXP-0001 daily Sharpe used a business-day index that omitted Sunday UTC exits.
  Trade P&L was unaffected; future code uses calendar days and sqrt(365).
- Opposite signals exit but do not reverse at the same timestamp.
- Midpoint results are not executable-cost evidence.

## Next actions

1. Do not test the reserved optimisation holdout yet.
2. Before any new tuning, test a same-UTC-slot/matched-rate volatility control.
3. Run a validated path-preserving return-shuffle null through the full engine.
4. Obtain independent code/result review and use future data for clean confirmation.

## Promotion candidates

- None. The apparent gross edge is cost-fragile and parameter optimisation failed.
