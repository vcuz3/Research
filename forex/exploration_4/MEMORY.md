# exploration_4 — Project Memory

## What this project is

A single frozen, naive standardized-displacement mean-reversion baseline for
four USD-major spot FX pairs. It is the reference book for possible later
overlay research, not a strategy to optimize.

## Status

**Completed — NO-GO (2026-08-08).** Material run: `EXP-0001`. The pre-run
specification, kill test, configuration, implementation, and planned ledger row
were frozen at Git commit `6658526` before any performance result was opened.
Independent review remains pending; builder: Codex, reviewer: unassigned.

## Confirmed findings

- Consumed-history primary base-cost net expectancy is **−0.3733 R/signal**
  (day-clustered 95% CI **[−0.3880, −0.3585]**, t=−49.58, n=55,958).
- Gross expectancy is already negative: **−0.0815 R** and **−0.244 pips** per
  signal. Mean modeled base round-trip cost is **1.081 pips**, so gross ≤ cost.
- The sealed 2024+ holdout is worse: base net **−0.5045 R** (95% CI
  [−0.5386, −0.4704], n=12,669); gross is −0.1775 R.
- Mandatory diagnostics fail with the compulsory stop: symmetric bracket
  **−0.0865 R** (CI [−0.0967, −0.0763]); fixed six-bar horizon **−0.0899 R**
  (CI [−0.1054, −0.0745]). The unstopped raw six-bar forward return is positive
  in consumed history (+0.0932 R) but is not deployable under the compulsory-stop
  constraint and fades to +0.0123 R with a zero-crossing CI in the holdout.
- Reversion timing beats the matched-duration random-exit null (observed
  −0.0815 R vs null 95th percentile −0.0859 R; p=0.002), but both are negative.
  This small exit-timing improvement cannot rescue the entry or costs.
- All four pairs are negative at base costs. EURUSD, GBPUSD, and AUDUSD remain
  strongly negative independently, so the verdict does not depend on NZDUSD.

## Post-closeout NZD data-repair sensitivity

- The 2026-08-08 hybrid NZD repair was evaluated separately at
  `artifacts/data_repair/NZDUSD_LSE_REPAIR_20260808/`; immutable `EXP-0001`
  artifacts and its ledger row were not rewritten.
- NZD path exclusions fell from 17,063 to 140. NZD consumed observations rose
  from 3,973 to 15,886, but gross expectancy became significantly negative at
  **−0.0617 R** (95% CI [−0.0854, −0.0379]) and base net was **−0.4826 R**.
- The pooled consumed result remains **NO-GO**: base net **−0.3937 R** (95% CI
  [−0.4077, −0.3797], n=67,871); holdout base net is **−0.5356 R**.
- The visualization notebook smoke-executes against either artifact directory
  via `FX_EXPLORATION4_ARTIFACT`.

## Data quality and implementation boundary

- Source Parquets contain midpoint OHLC only. Contrary to the planning wording,
  `volume` is absent rather than filled with −1; bid/ask is also unavailable.
- The exact 17:00 New York rollover bar is unavailable. Session-boundary exits
  use the last attainable 5-minute open before it (16:55), preventing an
  impossible 17:00 fill.
- The frozen `EXP-0001` input had material NZD holes and excluded 17,063 NZD
  candidates. The separately preserved repair sensitivity reduces this to 140;
  it does not relabel or overwrite the original consumed experiment.
- One position per pair is enforced statefully. The 30-minute news veto re-runs
  the state machine rather than post-filtering completed trades.

## Evidence and reproduction

- Current findings: `reports/FINDINGS.md`
- Rule 9a gate: `reports/DATA_QUALITY.md`
- Run artifacts and review: `artifacts/runs/EXP-0001/`
- Trade/metrics notebook: `notebooks/trade_visualizations.ipynb`
- Reproduce: `python -u forex/exploration_4/_run_baseline.py`
- Tests: `python -m pytest forex/exploration_4/test_baseline.py -q -p no:cacheprovider`

## Verdict and next action

**NO-GO. Close the baseline as negative evidence.** Do not tune this project or
leave a handoff implying a live edge. Any overlay research must be a separately
pre-registered follow-on project and must compare against this frozen negative
book. An independent reviewer should still rerun the tests and EXP-0001 command
and inspect the NZD coverage exclusion before the review status can pass.
