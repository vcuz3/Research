# RSI canonical RV regime by signal clock

## Verdict

Both canonical volatility regimes pass the frozen directional survival rule.
The result is not confined to scheduled `:29`/`:59` observations: higher
same-slot RV(5) and RV(30) percentile is associated with stronger RSI
mean-reversion P&L for scheduled states and for first crossings, and the
Q5-minus-Q1 gradient remains mostly positive after shifting the entire holding
window one minute later.

The clock comparison changes the economic interpretation. All-phase first
crossings have substantially lower gross P&L per signal than scheduled states,
but that comparison mixes minute-of-half-hour phases. Once phase is held fixed,
phase-29 first crossings are not weaker than scheduled states at the base
execution. Their very large base P&L largely disappears after a one-minute
delay, converging toward delayed scheduled results. Therefore:

- the **relative volatility-regime gradient survives** the clock and delay kill
  tests;
- much of the **absolute base-execution P&L level is boundary sensitive**; and
- the current midpoint results do **not** establish a deployable net edge.

This is consumed-history evidence on 2012-2023. The 2024+ holdout remains
sealed.

## Frozen design

The test follows `RSI_RV_CLOCK_REGIME_SPEC.md`: four USD-quoted FX pairs,
SMA-seeded Wilder RSI(14), New York time, and the canonical causal 90-session
same-slot percentiles `rv_5m_pct_90d` and `rv_30m_pct_90d`. Quintile cutpoints
are fitted on 2012-2020 scheduled observations and applied unchanged to all
clocks and to 2021-2023.

Clocks are:

- `scheduled_state`: RSI is extreme at New York `:29` or `:59`;
- `first_crossing_all`: the first minute RSI enters an extreme, with a 30-minute
  cooldown;
- `first_crossing_phase29`: accepted crossings restricted to phase `:29`;
- `scheduled_fresh`: scheduled states with extreme age zero.

Base execution enters at open `t+1` and exits at open `t+31`. Delayed execution
enters at `t+2` and exits at `t+32`, preserving a 30-minute hold. All P&L is
midpoint gross; "net" below only subtracts a hypothetical 0.5-pip round trip.

## Primary results

Values are medians across eight pair-era cells. `Votes` counts cells with a
positive Q5-minus-Q1 gross-P&L uplift.

| Regime | Clock | Delay | Q5-Q1 gross uplift (pip) | Votes | Q5 gross (pip) | Q5 after 0.5 pip | Hit rate | Gross session Sharpe |
|---|---|---:|---:|---:|---:|---:|---:|---:|
| RV(5) percentile | Scheduled state | 0 | 0.6738 | 8/8 | 0.9510 | 0.4510 | 57.72% | 1.543 |
| RV(5) percentile | Scheduled state | 1 | 0.3409 | 8/8 | 0.4518 | -0.0482 | 54.81% | 0.853 |
| RV(5) percentile | First crossing, all phases | 0 | 0.3233 | 8/8 | 0.4498 | -0.0502 | 54.59% | 1.855 |
| RV(5) percentile | First crossing, all phases | 1 | 0.1588 | 6/8 | 0.3204 | -0.1796 | 53.59% | 1.374 |
| RV(30) percentile | Scheduled state | 0 | 0.6507 | 8/8 | 1.1843 | 0.6843 | 57.72% | 1.453 |
| RV(30) percentile | Scheduled state | 1 | 0.4613 | 7/8 | 0.5723 | 0.0723 | 55.38% | 0.743 |
| RV(30) percentile | First crossing, all phases | 0 | 0.3382 | 7/8 | 0.4276 | -0.0724 | 54.41% | 1.093 |
| RV(30) percentile | First crossing, all phases | 1 | 0.2361 | 5/8 | 0.3164 | -0.1836 | 53.39% | 0.862 |

Both regimes satisfy every frozen sign criterion. Scheduled/all-crossing base
votes are at least 7/8, delayed votes are at least 5/8, and the phase-controlled
crossing coefficient is positive in at least 7/8 cells.

## Phase-matched clock diagnosis

| Regime | Phase-matched clock | Delay | Q5-Q1 uplift (pip) | Votes | Q5 gross (pip) | Q5 after 0.5 pip |
|---|---|---:|---:|---:|---:|---:|
| RV(5) | Phase-29 first crossing | 0 | 1.3525 | 6/8 | 1.8819 | 1.3819 |
| RV(5) | Phase-29 first crossing | 1 | 0.5538 | 5/8 | 0.4858 | -0.0142 |
| RV(5) | Scheduled fresh | 0 | 1.1842 | 7/8 | 1.5176 | 1.0176 |
| RV(5) | Scheduled fresh | 1 | 0.6642 | 6/8 | 0.6297 | 0.1297 |
| RV(30) | Phase-29 first crossing | 0 | 1.7171 | 8/8 | 2.5902 | 2.0902 |
| RV(30) | Phase-29 first crossing | 1 | 0.2302 | 6/8 | 0.6133 | 0.1133 |
| RV(30) | Scheduled fresh | 0 | 1.3343 | 8/8 | 1.7679 | 1.2679 |
| RV(30) | Scheduled fresh | 1 | 0.4974 | 7/8 | 0.7921 | 0.2921 |

At zero delay, fresh scheduled states and phase-29 crossings have much larger
Q5 gross P&L than the full scheduled sample. After the one-minute shift, the
phase-matched Q5 means converge sharply: RV(5) is 0.452 scheduled versus 0.486
phase-29 crossing; RV(30) is 0.572 versus 0.613. This supports a real relative
RV gradient, but it also shows that the first tradable minute carries a large
share of the apparent level edge.

The all-phase crossing regression controls for minute-of-half-hour and year and
clusters by New York session. Median regime coefficients are positive for both
features:

| Regime | Delay | Median regime beta (pip) | Positive cells | Median cluster t | t > 1.96 |
|---|---:|---:|---:|---:|---:|
| RV(5) percentile | 0 | 0.5409 | 8/8 | 2.26 | 5/8 |
| RV(5) percentile | 1 | 0.3260 | 7/8 | 1.33 | 3/8 |
| RV(30) percentile | 0 | 0.4982 | 8/8 | 2.51 | 5/8 |
| RV(30) percentile | 1 | 0.3464 | 8/8 | 1.73 | 4/8 |

Delay weakens both magnitude and inference, but does not reverse the pooled
direction.

## IC bridge and robustness

For scheduled full-range observations, the median within-slot RSI IC becomes
more negative from RV Q1 to Q5. The median Q1-minus-Q5 IC strength is 0.0512
(8/8 cells) for RV(5) and 0.0354 (7/8) for RV(30). With the one-minute delayed
target it remains 0.0278 (8/8) and 0.0264 (7/8), respectively. This agrees with
the event-P&L result and bridges exactly to the broad-sweep estimand.

As a reproduction check, scheduled RV(30) Q5 gross means match the prior broad
sweep to machine precision in all eight pair-era cells. Counts differ only
because this run reports target-valid signals, while the earlier helper counted
signals before target validity; conditional means are identical.

## Economics and data quality

The relative gradient is robust; the absolute edge is not yet economic. Median
Q5 all-phase first-crossing P&L is below the hypothetical 0.5-pip cost in every
base/delayed feature combination. Delayed scheduled RV(5) is also slightly
negative after that cost, while delayed scheduled RV(30) is only +0.072 pip per
signal. These are midpoint cost stresses, not spread-calibrated backtests.

Scheduled signals number 13,881-15,959 by pair. All-phase accepted first
crossings number 61,283-64,853; phase-29 crossings number 2,418-2,660. RV(5)
coverage is about 97.5%-97.7% and RV(30) coverage about 94.9%-96.0%. Input
timestamps remain ordered and unique; known NZDUSD gaps are preserved.

## Decision

Carry both `rv_5m_pct_90d` and `rv_30m_pct_90d` as distinct, provisional
volatility-regime variables. Do not restore the superseded "surprise" or
"acceleration synergy" labels. For every future RSI regime test, report:

1. scheduled state;
2. all-phase first crossing with phase controls;
3. a phase-matched crossing/fresh-state comparison; and
4. identical base and delayed execution windows.

No holdout opening or trading promotion is authorized by this test.

## Evidence

- Specification: `RSI_RV_CLOCK_REGIME_SPEC.md`
- Reproduction: `_run_rsi_rv_clock_regime.py`
- Machine-readable output: `rsi_rv_clock_regime_results.json`
- Tables: `rsi_rv_clock_regime_metrics.csv`,
  `rsi_rv_clock_regime_summary.csv`,
  `rsi_rv_clock_regime_phase_regressions.csv`, and
  `rsi_rv_clock_regime_scheduled_ic.csv`
- Charts: `charts/rsi_rv_clock_regime/scheduled_vs_crossing_regime_curves.png`,
  `charts/rsi_rv_clock_regime/regime_uplift_and_stability.png`, and
  `charts/rsi_rv_clock_regime/phase_matched_q5_and_delay.png`
