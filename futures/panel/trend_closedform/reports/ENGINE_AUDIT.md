# Engine Audit

The engine is `core/engine.py`, ~150 lines, not `backtest_engine/`. It is a
vol-targeted continuously-held linear position with **no stop, target or
barrier**, so there is no intrabar path to adjudicate (rule 3) and no queue to
model (rule 4). What it must get right is causality, execution timing, the roll
and the accounting, and those are what it asserts.

If this project ever acquires a barrier rule it needs a real engine and an
explicit rule-3 intrabar policy, and this file must be rewritten first.

## What is tested

`tests/test_core.py`, **30/30 passing**. Run:

```powershell
.\.venv\Scripts\python.exe -m futures.panel.trend_closedform.tests.test_core
```

| Area | Checks |
| --- | --- |
| Causality (rule 7) | perturbing `x` at T leaves every signal before T unchanged; the vol scale at row t ignores the price at row t; engine positions do not respond to a future shock |
| Execution (rules 1-2) | `lag=0` (article's own, unattainable) and `lag=1` (executable) are separate code paths; the lag-1 prediction provably drops the lag-1 autocorrelation |
| Closed-form identity | exact at both lags, through injected rolls, and for the EWMA crossover; the PHI decomposition is an exact partition |
| Kernel algebra | `w[0]` multiplies `x_t` (an off-by-one there shifts every lag in the formula); crossover return-form == price-form on a random path; crossover has no level term |
| Rolls (rule 11) | roll returns are dropped, not zeroed, in the risk units |
| Coverage (rule 9a) | a strict `min_periods` deletes a series with scattered roll gaps while the fractional floor survives it |
| Units (rule 19) | measured tick recovers decimal and binary grids and a mid-sample change; contract turnover is not the risk-unit turnover |
| Turnover claim | the closed form's `(2/sqrt(pi))sqrt(1-nu)` matches the engine's measured risk-unit turnover on noise |
| Intraday construction | slot scaling equalises per-slot variance; a per-slot MEAN profile inflates pooled AC1 and slot-demeaning fixes it; a per-slot SCALE profile does not inflate it |
| Statistics | Spearman matches scipy including ties; the cluster bootstrap is wider than a naive one under duplicates; the re-pairing null centres at zero |

## Known limitations

- The percentile bootstrap for the pooled OOS **difference** re-groups resampled
  clusters, which biases it: on the intraday arm the interval does not bracket
  its own point estimate. Read that arm as "no evidence", never as a signed
  result. The daily arm's interval does bracket its point.
- `x` is standardised by a causal 63-session (daily) or 90-session same-slot
  (intraday) scale. `sd(x)` lands at 1.02-1.21 across products, so the risk units
  are comparable but not exactly unit-variance.
