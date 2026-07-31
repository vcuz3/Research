# EXP-0042 — Causal trend hysteresis calibration

- Hypothesis: `HYP-0030` — Trend-percentile hysteresis reduces one-day regime flips without making the causal 10x504 state model too sticky
- Status: completed — PASS for label calibration
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Smallest h clearing all frozen label-quality gates; P&L descriptive only
- Kill test: NO-GO if no h clears median trend dwell>=3, singleton<=10%, max annual trend share<=60%, min 12-cell days>=150 and causality. Choose smallest passing h; never select on P&L.

## Result versus hypothesis

The experiment passes. A 7.5-percentage-point buffer (`h=0.075`) is the smallest
setting that clears every rule fixed before the run.

In simple language, the trend score must now move 7.5 percentile points beyond a
boundary before the label changes. Small moves near a boundary are ignored. Large moves
can still cross more than one state immediately.

| buffer | median state length | one-day labels | changes | smallest cell | verdict |
|---|---:|---:|---:|---:|---|
| 0% | 2 days | 17.1% | 1,201 | 163 | too noisy |
| 2.5% | 2 | 13.5% | 1,085 | 156 | too noisy |
| 5.0% | 2 | 10.34% | 975 | 158 | just misses |
| **7.5%** | **3** | **7.4%** | **872** | **152** | **pass** |
| 10.0% | 3 | 5.5% | 772 | 143 | too sticky |

“Smallest cell” means the least-populated one of the 12 volatility×trend combinations.
The minimum requirement was 150 days.

## Gross, net, baseline, and null comparison

Profit was deliberately excluded from selection. The strategy and total P&L do not
change; hysteresis only moves days between descriptive labels.

Full-sample daily-$ Sharpe by trend label:

| labels | chop | weak | trend |
|---|---:|---:|---:|
| raw | 0.88 | 1.48 | 0.76 |
| selected hysteresis | 0.46 | 1.79 | 0.83 |

The selected labels separate the weaker chop group from the stronger weak/trend groups
more clearly. This is descriptive evidence on already-used historical data. It is not
permission to skip chop days or change position size. No Null C was run because the
experiment tested label quality, not trading performance.

## Regimes, sensitivity, and alternative explanations

- The result is locally bounded: 5% is slightly too weak; 10% is too sticky. The 7.5%
  survivor is not an edge-of-grid accident.
- The selected label changes 12.9% of raw labels, but disagreement never lasts more than
  four sessions in a row. It smooths boundaries without rewriting long market periods.
- Annual occupancy remains balanced: no trend label exceeds 43.5% of a complete year.
- Recent results are not perfectly stable. Under hysteresis, chop is profitable in 2023,
  near zero in 2024, and sharply negative in 2025–2026. Hysteresis fixes label flicker;
  it does not guarantee that a regime's future profit has the same sign every year.
- The weak and trend groups remain positive in 2025 and 2026 YTD, but this was observed
  after selection and cannot justify a gate on consumed history.

## Artifact and implementation risks

- The first execution stopped before producing results because pandas/Arrow could not
  cumulatively sum a Boolean reporting column. The helper was replaced with an equivalent
  NumPy loop; label construction and selection logic were unchanged. The deterministic
  material run then completed.
- `h=0` is asserted to reproduce EXP-0041 labels exactly.
- Causal prefix parity passes for every buffer. Future observations cannot change an
  earlier state.
- Fourteen focused causal and Null-C invariant tests pass.
- Historical data are consumed. Only label calibration is accepted.

## Builder interpretation

Adopt `h=0.075` for the trend reporting labels paired with the EXP-0041 `10×504`
relative-volatility labels. Continue using the raw continuous percentile for charts and
diagnostics, so the smoothing is transparent.

Do not add an entry filter or sizing rule. A separate preregistered full-engine test and
Null C would be required for that materially different claim.

## Independent review

- Review status: not reviewed
- Objections: independent review remains required.
- Verdict: pending independent review

## Promotion decision

- `reports/FINDINGS.md`: no project findings file exists; evidence stays in run artifact.
- `MEMORY.md`: update with the calibrated label rule and non-alpha limitation.
- Shared `LEARNINGS.md`: not eligible without cross-project verification
