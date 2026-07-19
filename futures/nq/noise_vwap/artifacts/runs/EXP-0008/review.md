# EXP-0008 Results Discussion

- Hypothesis: `HYP-0001` — A short causal noise lookback improves NQ risk-adjusted returns
- Status: completed — hypothesis rejected
- Builder: Codex
- Reviewer: unassigned
- Primary metric: full-family maximum zero-trade-day daily net-ATR Sharpe uplift over lookback 90
- Kill test: Reject if max Sharpe uplift is below +0.10, selected net R is below lookback 90, or family-wise p exceeds 0.05

## Result versus hypothesis

Rejected on both the primary NQ test and the ES sibling control.

| Instrument | Selected lookback | Sharpe uplift | Net-R delta | Null max mean | Family-wise p | Verdict |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| NQ | 30 | -0.065 | -3.8 | +0.026 | 0.8571 | Reject |
| ES | 2 | +0.026 | +2.3 | -0.046 | 0.1905 | Reject |

Neither instrument reached the prespecified `+0.10` Sharpe uplift or corrected
`p <= 0.05` gates. NQ also lost aggregate net R.

## Gross, net, baseline, and null comparison

NQ lookback 90 retained the strongest full-sample Sharpe (1.29) and net R
(+91.2). The best nonbaseline NQ candidate, lookback 30, had Sharpe 1.22 and net
R +87.4. ES lookback 2 marginally improved Sharpe from 0.70 to 0.72 and net R
from +51.5 to +53.7, but the effect was small and not family-wise significant.

## Regimes, sensitivity, and alternative explanations

Short lookbacks looked better in 2023+ on both markets: NQ lookback 2 had recent
Sharpe 1.81 versus 1.10 for lookback 90; ES lookback 2 had 1.39 versus 0.80.
This is post-hoc regime evidence on consumed data and conflicts with the
full-sample primary test. It may motivate future-only monitoring, not another
historical optimization.

Fill sensitivity was negligible for selected NQ lookback 30 (Sharpe -0.002,
net R -0.1) but adverse for ES lookback 2 (Sharpe -0.091, net R -6.6), further
weakening transportability.

## Artifact and implementation risks

The corrected path-preserving null matched diffusivity exactly (NQ 0.25 point,
ES 0.00 point median). Each of 20 draws reran all eight band constructions,
engine execution, costs, scoring, and maximum selection on the common
post-lookback-90 sample. Twenty draws provide coarse p-value resolution, but
the observed p-values are far from the decision boundary.

## Builder interpretation

The paper's 2-8 day lookbacks do not improve this NQ futures strategy when
isolated from its other optimized parameters. The result is a useful NO-GO.
Retain lookback 90; do not promote short lookbacks from this historical screen.

## Independent review

- Reviewer: Claude (Opus 4.8)
- Review date: 2026-07-18
- Review status: completed
- Verdict: REJECT confirmed — concur with the builder.
- Basis: Read the hypothesis, frozen config, `paper_5095349_hypothesis_test.py`,
  and all four raw outputs. Every number in this review is backed by the
  artifacts, including the ES fill-sensitivity line (`real_es.txt:14`).
- Methodology checks passed: single-variable isolation of the noise lookback;
  fair common lb90-eligible sample so short windows get no extra history;
  selection priced correctly via the family maximum-statistic against 20
  full-pipeline Null C draws (band construction + engine + costs + winner
  selection all rerun); valid path-preserving null with matched diffusivity
  (NQ 0.25, ES 0.00); honest zero-trade-day Sharpe; explicit gross and net costs.
- Objections: none blocking.
  1. The 2023+ short-lookback strength (NQ lb2 recent Sharpe 1.81 vs 1.10; ES
     lb2 1.39 vs 0.80) is the live risk. The builder correctly treated it as
     post-hoc on consumed data and refused to re-optimize (Rule 26). It must
     remain a future-shadow monitoring question only, never a new historical
     screen.
  2. 20 draws is adequate for a reject (p=0.857 NQ, 0.19 ES, both far from
     0.05); require >=100 draws before ever accepting anything from this harness.
  3. Causality of `S.noise_bands(lookback)` (strictly-prior sessions) is
     inherited from the audited core, not re-proven in this artifact.

## Promotion decision

- `reports/5095349_EVALUATION.md`: updated
- `MEMORY.md`: updated with the rejected hypothesis
- Shared `LEARNINGS.md`: not eligible without cross-project verification
