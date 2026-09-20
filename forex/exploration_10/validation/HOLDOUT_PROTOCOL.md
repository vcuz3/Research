# Optimisation Holdout Protocol

Frozen before EXP-0002 on 2026-09-19.

## Reserved interval

For every asset, timestamps from **2024-07-18 00:00:00 UTC onward** are excluded
from parameter construction, training, selection, walk-forward validation, and
reporting. The final available timestamp is 2026-07-17 20:59 UTC, so this reserves
approximately 24 months per pair.

The optimiser uses Parquet predicate filtering and asserts that every loaded
timestamp is strictly earlier than the asset cutoff. Its audit artifact records
the cutoff and maximum loaded timestamp, but no holdout prices or outcomes.

## Important limitation

EXP-0001 previously tested the baseline configuration over the full archive,
including this interval. Therefore the interval is untouched by **optimisation**
but is not a genuinely unseen historical holdout for the strategy family. It may
test optimisation overfit operationally, but only future observations can provide
a clean new holdout for the original thesis.

## Walk-forward design

- Candidate grid: 243 combinations across timeframe, ATR period, ATR percentile,
  stop ATR, and target ATR.
- Per-asset selection; no cross-asset pooling during parameter choice.
- Rolling five-year training window, followed by one-year forward validation.
- Annual steps from 2012-01-01, plus a final partial validation ending at the
  holdout boundary.
- Selection objective: training daily Sharpe of R after 0.5 pip round-trip cost,
  requiring at least 200 training trades. Ties prefer higher mean net R, then the
  deterministic configuration ID.
- Validation outputs are computed only for each fold's training-selected
  candidate. Unselected candidates' validation results are not written.
- Final per-asset parameters are selected using the last five pre-holdout years
  and locked without evaluating the reserved interval.

## Kill test

The optimisation family is a NO-GO if the stitched walk-forward validation has
non-positive pooled daily Sharpe, fails to improve the baseline by at least 0.10
Sharpe, or fewer than three of four assets have positive mean net R at 0.5 pip.
