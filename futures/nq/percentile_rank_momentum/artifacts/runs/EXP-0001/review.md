# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Self-rank momentum plus expected-value readout as a single-instrument NQ signal
- Status: completed — Rule-9a gate passed after the pre-P&L user amendment
- Builder: codex
- Reviewer: unassigned
- Primary metric: Per-trade net expectancy in NQ ticks with session-cluster-robust t-statistic, after reading gross expectancy first; also report zero-day, trade-day-only, and causal vol-targeted daily Sharpes.
- Kill test: Stop before P&L if the Rule-9a feature gate is not evaluable; otherwise apply the gross, matched-count ML-value, full-pipeline Null-C, and ES sign-transfer gates below.

## Result versus hypothesis

The amended 40%-of-W same-sign floor is feasible. Depending on W, 228,754 to
240,767 of 267,694 decision rows are eligible (85.5% to 89.9%), and 15,741 to
17,105 cross the 0.85 entry threshold. This authorizes the P&L ladder.

## Gross, net, baseline, and null comparison

Not applicable at this gate. No P&L, fills, model, or null was executed.

## Regimes, sensitivity, and alternative explanations

The all-slot per-era firing-rate CV is 0.36 because the 60-minute RTH horizon is
structurally unavailable from 10:00 through 10:25. Those rows are dropped and
counted. On coverage-matched eligible slots, the maximum era CV is 0.18–0.19
across W, with most eras near 0.09–0.15. Full slot/era counts are in the CSVs.

## Artifact and implementation risks

The legacy `nq_5m_clean.parquet` timestamp is timezone-naive despite the original
spec calling it UTC. The pre-run amendment uses five-minute RTH bars resampled
from the audited timezone-aware `NQ_1m_clean.parquet`. Seven expected five-minute
slots are missing across 3,718 eligible sessions; they remain missing and are
counted rather than filled.

## Builder interpretation

The coverage gate passes, but says nothing about profitability. Continue to the
B0–B4 ladder on eligible decisions and read gross expectancy first.

## Independent review

- Review status: not reviewed
- Objections: pending
- Verdict: coverage gate passed; P&L evidence pending

## Promotion decision

- `reports/FINDINGS.md`: update after the P&L ladder
- `MEMORY.md`: update after the P&L ladder
- Shared `LEARNINGS.md`: not eligible without cross-project verification
