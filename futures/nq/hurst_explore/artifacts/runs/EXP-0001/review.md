# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Measurement-error floor of an intraday Hurst estimate
- Status: completed (descriptive / measurement)
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned (independent review pending)
- Primary metric: std(Ĥ) vs window/estimator/frequency; real cross-estimator MAD vs the floor
- Kill test: synthetic floor negligible at n≈30, OR real estimator disagreement < own bias

## Result versus hypothesis

Confirmed. The synthetic floor is large at short windows (std 0.17–0.30 at n=30)
and only tightens to ≈0.04 (full 1m day) / ≈0.015 (full 1s day). Real
cross-estimator disagreement (ghe1≈0.46 vs R/S≈0.57) is explained by the
estimators' own measured biases; bias-corrected whole-session H≈0.49–0.50 on
NQ and ES. 1s cuts the floor ~2–3× vs the full 1m day.

## Gross, net, baseline, and null comparison

No trading. "Baseline" is synthetic fBm truth-recovery (validated in
`tests/test_hurst.py`): ghe1/ghe2 near-unbiased, DFA small +bias, R/S known +bias.
The bias table IS the reference used to correct the real levels.

## Regimes, sensitivity, and alternative explanations

- Estimator choice is the main sensitivity: R/S levels are not trustworthy
  without bias correction; ghe1 (low bias) or DFA (low variance) preferred.
- Rule 9a: 1s fill-rate is era-dependent (min 0.26 pre-2015) — handled by the
  fill/era filter used downstream (A2).

## Evidence

`a1_summary.txt`, `synthetic_floor.csv`, `real_1m_{NQ,ES}.parquet`,
`real_1s_NQ.parquet`, `meta.json`.

## Reviewer verdict

Independent review (Claude, 2026-07-22) of the user's correction run EXP-0003:
ACCEPT. The complete-grid estimator gate (exact slots 0..389; 7 NQ / 4 ES
sessions excluded), the executable inverse-calibration bias correction, and the
matched-session Part C all correct real defects in EXP-0001. The calibration
DISPROVED my original "collapses to ~0.50" overclaim: properly bias-corrected
whole-session levels span NQ 0.473-0.499 / ES 0.466-0.485 (cluster mildly BELOW
0.5), i.e. near-RW to mildly anti-persistent, not a universal 0.50. R/S calibrated
0.568->0.499 (NQ), confirming the calibration removes its known bias. Part C on
149 matched sessions (1m 0.471 vs 1s min+ 0.490) is honestly labeled a consistency
diagnostic, not agreement. No further correctness objections.
