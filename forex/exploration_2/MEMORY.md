# Project Memory: Forex Exploration 2

## Scope

- Objective: Explore a five-minute Bollinger breakout with a ratcheting band stop and causal volatility/trend regime gates.
- Instruments or markets: EURUSD, GBPUSD, AUDUSD, NZDUSD spot-FX midpoint OHLC.
- Data coverage: clean one-minute archives begin in 2011; the notebook loads only rows before 2024 by default.
- Current phase: Bollinger-window repair implemented and smoke-validated; corrected full pre-holdout breakout run is pending.

## Current status

- Verdict: **NO-GO for the superseded late-session momentum implementation; corrected continuous 200-observed-bar strategy not yet fully rerun.**
- Last verified: 2026-08-09
- Lifecycle phase: corrected engine audit passed; full research run pending
- Baseline replication: not applicable (user-specified strategy)
- Engine audit: five synthetic timing/fill/window invariants pass. Corrected smoke execution gives BB(200) coverage 99.73% in the shortened pre-2021 slice and effectively 100% in 2021-2023; only initial warm-up and rare invalid/partial bars are missing.
- Execution profile: five-minute close signal, next-open entry, one position per pair, entry-bar stop active, adverse gap-through fill, ratcheting stop from completed bars, Friday 17:00 New-York close.
- Holdout status: 2024+ sealed by the default loader and asserted after trade generation.
- Reproduction command: `python _build_bollinger_notebook.py`; smoke with `python _smoke_run_bollinger_notebook.py` from this directory.
- Primary evidence: `bollinger_breakout_regime_sweep.ipynb`, `_bollinger_engine.py`, `_test_bollinger_engine.py`.
- Mean-reversion candidate: `bollinger_reentry_mean_reversion.ipynb`, `_bollinger_mean_reversion_engine.py`, `_test_bollinger_mean_reversion_engine.py`.

## Confirmed findings

- The superseded segmented-BB four-pair baseline lost gross before costs in both samples: pooled average R -0.0390 / active-session Sharpe -0.599 before 2021, and -0.0212 / -0.281 in 2021-2023. Pre-2021 average R was negative on 4/4 pairs; 2021-2023 was positive only on EURUSD/GBPUSD and negative on AUDUSD/NZDUSD. These figures describe only the old late-session implementation; notebook outputs were cleared when the corrected notebook was regenerated.
- None of the neighbouring Bollinger length, entry-depth, or stop-width rows shown in the geometry table is positive in both samples. A hypothetical 0.5-pip round trip worsens 2021-2023 pooled average R from -0.0212 to -0.0665; 1.0 pip gives -0.1118.
- Critical scope correction: the old engine reset BB at every non-five-minute link. The archives have about 3,200 such gaps per pair, almost one per trading day. Consequently BB(200) was defined on only 30.1% of rows and, for EURUSD/GBPUSD/AUDUSD, on session slots 202-287 only (about 09:50-17:00 New York). BB(300)'s very small sample was a coverage artefact. The old run does **not** support a whole-day verdict.
- The breakout engine now rolls Bollinger means and population standard deviations over valid observed closes across scheduled rollover/weekend closures. Execution still blocks next-open entries across a gap, while RV30/ATR/VEI remain segmented to preserve their stated short horizons. Baseline trades carry causal before/after-gap distances for post-hoc diagnostics. Evidence: `_bollinger_engine.py`, `_test_bollinger_engine.py`, regenerated `bollinger_breakout_regime_sweep.ipynb`.
- The breakout notebook forcibly reloads `_bollinger_engine.py` and prints engine version `2026-08-04-continuous-observed-bb-v2`, preventing a long-lived Jupyter kernel from silently retaining the old segmented construction. BB(200) coverage is displayed separately from the all-feature minimum, which can be low because causal regime features require long history.
- A separate causal same-slot area-fade test now lives in
  `area_mean_reversion_entry_variants.ipynb` with execution logic in
  `_area_mean_reversion_engine.py`. It compares the first inside-to-outside
  crossing per FX session with a non-overlapping 30-minute checkpoint policy;
  both enter at the next open and exit open-to-open after exactly 60 minutes.
  Four synthetic causality/timing invariants and a full pre-2024 EURUSD smoke
  execution pass. The smoke is diagnostic, not a registered experiment.

## Provisional hypotheses

- High volatility acceleration or stronger higher-timeframe trends may condition breakout performance.
  - Kill test: positive net average R in both pre-2021 and 2021-2023, at least 3/4 pair agreement, one-pip cost survival, and neighbouring-parameter stability.
  - Evidence needed: full four-pair run, matched-selectivity controls, claim-matched null, then a frozen 2024+ test.
- Same-slot 90th/10th percentile session-return breaches show a positive but
  small provisional gross fade before 2024. The unchanged four-pair verification
  measures 15/30/60/120-minute direction-adjusted returns, separates upper/lower
  breaches, and compares the one-per-session primary rule with a symmetric
  same-slot large-move control matched exactly on trade count for 3/4 pairs and
  within three trades on GBPUSD. Gross first-cross means are positive on both
  sides at 60 minutes for 4/4 pairs, but all cells remain negative after the
  explicit pair-level ECN spread anchor, 0.10-pip-per-side slippage, and
  0.70-pip round-trip commission assumptions. Those costs are imported rather
  than measured in the midpoint archive. Evidence:
  `area_mean_reversion_entry_variants.ipynb`; EURUSD smoke reproduction:
  `python _smoke_run_area_mean_reversion_notebook.py`.
- Incremental validation is implemented in
  `area_mean_reversion_incremental_validation.ipynb` with paired session panels,
  20-session moving-block bootstrap inference, common-date cross-pair alignment,
  and a volatility-scaled signal-state spread proxy. At 60 minutes, gross
  primary-minus-control differences per eligible session were EUR +0.247
  [0.005, 0.487], GBP +0.064 [-0.300, 0.464], AUD +0.411 [0.019, 0.803], and
  NZD -0.124 [-0.504, 0.266] pips; the equal-weight common-date result was
  +0.131 [-0.050, 0.318]. Thus the preregistered-style incremental kill rule
  fails: the portfolio interval includes zero and pair signs are not stable.
  All eight pair/side primary cells remain negative after the ECN-anchor
  signal-state cost proxy. This is a research-level NO-GO for incremental area
  information and an economic NO-GO under the proxy, not measured-spread fill
  evidence. Evidence helpers: `_area_validation.py`, `_test_area_validation.py`.

## Decisions and constraints

- “Trailing 0.75σ band” means a ratchet: long stops never fall and short stops never rise.
- Population standard deviation (`ddof=0`) is used for the Bollinger band.
- 2021-2023 is an already-exposed internal temporal evaluation, not pristine out-of-sample evidence.
- Midpoint data have no measured bid/ask spread; notebook outputs are gross plus hypothetical cost stress.
- “Calgar” is interpreted as Calmar (CAGR divided by maximum drawdown).
- The new re-entry notebook defines BB(200) over the last 200 valid observed closes and deliberately carries it across scheduled rollover/weekend closures. In contrast, RV30 retains a true consecutive-six-bar clock and restarts after gaps.
- Re-entry candidate: arm after a close beyond ±1.5σ, require a later close back inside within six bars, enter next open toward the mean, freeze the signal-bar mean target and ±2.5σ catastrophic stop, and time out open-to-open after 120 minutes.
- Causal RV gates include shifted prior-same-slot medians, ratios, and percentiles at both 90- and 252-session memories. Minimum observation fraction is 2/3.
- Equity and headline account metrics in the re-entry notebook use one user-selected pair only. Other pairs are robustness diagnostics and are never pooled into the account.
- Position sizing rejects entries whose next-open-to-sizing-stop distance is below 0.5 signal-bar σ, preventing accidental extreme leverage from a near-stop gap.

## Known risks and open questions

- The four USD-quoted pairs are correlated tests.
- Full regime/parameter selection is a multiple search and must be compared with deeper-entry matched-rate controls.
- Portfolio equity is realised-only between exits, allows concurrent 1%-risk positions, and has no leverage cap or mark-to-market margin model.
- A calibrated spread/slippage series is required before economic interpretation.
- A stop-free first-crossing diagnostic run during review found only tiny gross Bollinger-fade endpoint returns: median across pairs about +0.075/+0.037 pip at 30 minutes in pre-2021/2021-2023, both negative after a 0.5-pip cost. This is provisional ad-hoc evidence, not a registered experiment, but it rejects simply mirroring every breakout as the next default.

## Next actions

1. Run the corrected full `bollinger_breakout_regime_sweep.ipynb` across all four pairs before making a whole-day breakout verdict; inspect BB coverage and post-hoc gap-proximity rows first.
2. Run the full `bollinger_reentry_mean_reversion.ipynb` across all four pairs and inspect BB/RV/time-of-day coverage before interpreting strategy rows.
3. Read the fixed-horizon entry-information table before the bracket result; reject the mean-reversion candidate if gross re-entry expectancy does not clear plausible costs.
4. Compare any RV-gated survivor with a deeper outer-band entry at matched selection rate; inspect but do not filter post-hoc rollover-proximity rows.
5. Resolve any surviving target/stop configuration on one-minute paths, then freeze it and add a claim-matched path-preserving null before opening 2024+.
6. For the area-fade notebook, inspect gross direction-adjusted returns before
   costs, require upper/lower agreement, compare both entry variants with a
   matched-rate generic large-move control, and register a hypothesis before a
   material cross-pair or parameter run.
7. Do not tune the area fade around EUR/AUD survivors: the paired common-date
   portfolio failed its 60-minute kill rule and NZD was wrong-signed. Any future
   revisit needs genuinely new information (measured bid/ask, a prespecified
   mechanism, or unconsumed future data), not another threshold search.

## Promotion candidates

- None.
