# EXP-0002 Walk-forward optimisation

## Verdict

**NO-GO under the frozen walk-forward kill test.**
Across stitched validation windows, the selected policy has pooled daily Sharpe
-0.442 versus -0.292
for the static baseline (delta -0.150); 0/4
assets have positive mean net R after 0.5 pip round-trip cost.

| Asset | Validation trades | Mean net R | Selected Sharpe | Baseline Sharpe | Delta |
| --- | ---: | ---: | ---: | ---: | ---: |
| EURUSD | 1599 | -0.0130 | -0.175 | -0.445 | +0.270 |
| GBPUSD | 1246 | -0.0167 | -0.215 | +0.114 | -0.329 |
| AUDUSD | 865 | -0.0363 | -0.396 | -0.142 | -0.255 |
| NZDUSD | 1114 | -0.0191 | -0.260 | -0.192 | -0.068 |
| POOLED | 4824 | -0.0195 | -0.442 | -0.292 | -0.150 |

## Locked parameters for the untested optimisation holdout

- EURUSD: `tf60min_a28_p0.15_s2.0_t2.0`
- GBPUSD: `tf60min_a28_p0.20_s1.0_t2.0`
- AUDUSD: `tf60min_a14_p0.15_s1.0_t1.5`
- NZDUSD: `tf60min_a14_p0.15_s1.5_t1.0`

The reserved interval begins 2024-07-18 UTC for every pair. It was not loaded,
scored, or used in parameter selection by this run. `holdout_audit.json` records
the fail-closed timestamp assertions. Do not add holdout results to this run.

## Interpretation

- The search covered 243 configurations per asset. Each validation fold was
  evaluated only after selection on its preceding rolling five-year training window.
- Training winners averaged Sharpe 0.72-0.94 by asset, but their mean fold-level
  validation Sharpe was negative for EURUSD (-0.14), GBPUSD (-0.27), and AUDUSD
  (-0.43), and only +0.08 for NZDUSD. This train/forward collapse is direct
  evidence of selection overfit.
- Parameter choices were unstable: 20/32 folds selected 60-minute candles, but
  22 distinct configurations were chosen across 32 asset-folds. No configuration
  dominated the walk-forward path.
- The final partial validation ends at the holdout boundary; it is labelled in
  `walk_forward_selections.csv`.
- The baseline had already inspected the reserved dates in EXP-0001, so this is
  an optimisation holdout, not a clean thesis-level historical holdout.
- Midpoint execution and a fixed 0.5-pip charge remain approximations. The clock
  selector and claim-matched null remain unresolved.
- Independent review is pending.
