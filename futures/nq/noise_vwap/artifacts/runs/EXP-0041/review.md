# EXP-0041 — Causal rolling-percentile regime calibration sweep

- Hypothesis: `HYP-0029` — Causal rolling-percentile volatility and trend regimes are better calibrated than full-sample fixed buckets without relying on strategy P&L
- Status: completed — QUALIFIED
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Frozen calibration score plus hard gates; annual occupancy, singleton rate, dwell, coverage and 12-cell counts; strategy P&L descriptive only
- Kill test: Reject any candidate with max annual vol share >60%, median vol dwell <3 sessions, post-warmup label loss >15%, or failed causality. Rank passers only by frozen calibration score; P&L descriptive.

## Result versus hypothesis

The fixed EXP-0038 buckets are materially nonstationary as labels: on the common
2013-10-08..2026-07-14 sample their worst calendar year has 98.0% of sessions in one
volatility bucket and their frozen calibration score is 0.619. The causal sweep improves
this substantially, but only one candidate clears every registered volatility gate.

`10-session indicator × 504-session calibration` is the P&L-blind winner: score 0.403,
maximum annual volatility-bucket share 55.2%, median volatility dwell 3 sessions, zero
post-warm-up loss, smooth threshold movement (99th-percentile relative daily jump 1.21%),
and causal prefix parity. It also raises the minimum full-sample 12-cell coverage from
138 days under the fixed control to 163.

The preregistered primary `20×504` ranks second but narrowly FAILS the hard annual-
concentration gate: 60.8% high-vol days in 2022 versus the <=60% requirement. Its score
is 0.422 and median vol dwell is a steadier 5 sessions. The result answers the user's
question: 20 sessions is slightly too slow for the frozen occupancy criterion, while
three years is not optimal — the two-year/504-session calibrator dominates both 252 and
756 in the relevant neighbourhood.

Qualification: `10×504` trend labels still churn (median dwell 2 sessions, singleton
rate 17.1%). The exact experiment gate was volatility-dwell based, so the candidate
passes as a VOLATILITY calibration. It does not establish a fully stationary joint
vol×trend state model.

## Gross, net, baseline, and null comparison

Strategy P&L was excluded from calibration selection and evaluated only afterward.
On the common sample, baseline marginal daily-$ Sharpe by relative-vol bucket is:

| rule | low | normal | elevated | high |
|---|---:|---:|---:|---:|
| `10×504` selected | 1.18 | 1.47 | 1.14 | 0.73 |
| `20×504` primary | 1.38 | 0.47 | 1.27 | 1.04 |

The full-sample-qcut claim that high volatility carries the edge does NOT transfer to a
causal relative-vol definition: high is the weakest marginal band under the selected
calibration, and none of the causal profiles is monotonic. This is descriptive consumed-
history evidence, not a new rejection test of EXP-0039; it does reinforce EXP-0040's
NO-GO on volatility sizing.

No Null C was run because this experiment makes a calibration claim, not a P&L or alpha
claim. Any later search across these nine definitions must repeat the full selection in
each null draw.

## Regimes, sensitivity, and alternative explanations

- The 504-session calibration is the local sweet spot. Short 252-day histories overreact
  to a single unusual year; 756-day histories adapt too slowly. All 252/756 neighbours
  breach the 60% annual-concentration gate.
- A 10-session indicator improves annual occupancy but pays for it with more switching:
  volatility singleton rate 4.7% versus 2.1% for `20×504`; trend singleton rate 17.1%
  versus 11.1%.
- Relative regimes cannot force every calendar year to contain every state. Selected
  `10×504` still has zero high-vol days in 2023 and zero low-vol days in 2022; it is much
  better calibrated than 98% concentration, not perfectly stationary.
- Recent P&L remains unstable after relabelling. Under `10×504`, high-relative-vol Sharpe
  is -0.74 in 2024, +0.41 in 2025, and -2.71 in 2026 YTD. Normal is +3.91, -1.49, -3.38.
  Labels are more stationary; conditional returns are not.
- A possible future calibration-only hypothesis is to decouple horizons (volatility 10,
  trend 40) or add trend hysteresis. That combination was not preregistered and is not
  promoted from this result.

## Artifact and implementation risks

- All nine candidates use the same common 3,173-session ranking sample; natural first-
  label dates and zero post-warm-up loss are reported separately.
- The calibration window accepts two-thirds minimum observations (`168/336/504` for
  `252/504/756`), as frozen in config. This permits a 504-day maximum window to begin
  after 336 valid indicator observations.
- Full daily label/threshold history is saved for the primary, but not for all nine;
  all candidates' annual occupancy and aggregate diagnostics are retained.
- Full history is consumed. The result can choose a descriptive labelling convention,
  not validate future regime-conditioned alpha.
- Eleven focused causal/null invariant tests passed. Pytest emitted only the existing
  cache-permission and dateutil deprecation warnings.

## Builder interpretation

Adopt `10×504` only when a causal RELATIVE-volatility reporting label is needed. Keep
raw RV20/absolute volatility for risk limits and sizing. Do not use the selected label
as an entry gate or size multiplier: its P&L ordering is nonmonotonic and EXP-0040 has
already rejected causal volatility sizing.

Do not yet adopt the joint trend axis as “stationary.” Its two-session median dwell is
too noisy for a stable operational state without a separately preregistered hysteresis
or decoupled-horizon calibration.

## Independent review

- Review status: not reviewed
- Objections: independent review remains required; builder identified the trend-churn
  qualification and the fixed-control reporting omission, then reran deterministically.
- Verdict: pending independent review

## Promotion decision

- `reports/FINDINGS.md`: no project findings file exists; evidence stays in run artifact.
- `MEMORY.md`: update with the qualified calibration result.
- Shared `LEARNINGS.md`: not eligible without cross-project verification
