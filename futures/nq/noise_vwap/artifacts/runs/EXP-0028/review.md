# EXP-0028 Results Discussion

- Hypothesis: `HYP-0019` — Fixed causal Hurst weights monetize EXP-0026 per-trade quality without deleting exposure.
- Status: completed — REJECT
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Matched-exposure equal-risk NQ/ES daily net-ATR-R Sharpe uplift; net R and maxDD co-primary
- Kill test: Reject unless both instruments improve Sharpe, neither loses more than 1% net R, pooled equal-weight Sharpe rises at least 0.10, and drawdown does not worsen; run 200-draw allocation-label null only after passing.

## Result versus hypothesis

The fixed Hurst allocation fails the frozen cross-market gate. It increases total
net R but does not improve risk-adjusted performance and makes the loss path more
severe.

| market | baseline Sh | sized Sh | dSh | baseline net R | sized net R | baseline maxDD | sized maxDD |
|---|---:|---:|---:|---:|---:|---:|---:|
| NQ | 1.288 | 1.265 | -0.022 | 91.20 | 95.30 | 4.70R | 5.15R |
| ES | 0.698 | 0.702 | +0.004 | 51.47 | 56.68 | 7.45R | 8.65R |
| equal-risk pool | 1.082 | 1.085 | **+0.002** | 71.33 | 75.99 | 4.36R | 5.16R |

The required pooled uplift was +0.10; observed uplift was +0.002. NQ's sign is
negative and drawdown worsens on both instruments, so three parts of the kill
test fail. No allocation-label null was spent.

## Gross, net, baseline, and null comparison

Trade population is identical (4,209 NQ; 4,326 ES) and H is defined on every
entry. The causal expanding-prior normalizer produced realized mean weights of
1.007 NQ and 1.025 ES, close to the target one risk unit without using the final
trade count. Net R rises by +4.11R NQ and +5.21R ES, confirming that high-H trades
have higher unconditional expectancy. The increased weight also concentrates
losses: worst day worsens from -1.17R to -1.25R NQ and -1.59R to -2.04R ES.

The inverted control is worse on net R and Sharpe in both markets, confirming the
EXP-0026 direction: high H is the better-quality side. But the correct-direction
allocation merely buys more return with more tail risk; it is leverage placement,
not a Sharpe improvement.

## Regimes, sensitivity, and alternative explanations

There was one frozen schedule and no parameter sweep. Because the real gate
failed widely, parameter sensitivity and a permutation null would only encourage
post-hoc optimization on consumed history. The result is consistent across the
most important distinction: both instruments gain net R, neither gains meaningful
Sharpe, and both suffer worse drawdown.

## Artifact and implementation risks

- H is computed causally from session-to-date closes at the signal bar; fills and
  exits are unchanged from the audited continuous-stop engine.
- Weight and its expanding normalizer are known at entry. No final trade count or
  same-day future signals are used.
- Complete-trade P&L and proportional costs are scaled by entry-frozen fractional
  risk units. This is implementable via micros or a sufficiently granular account;
  discrete contract rounding was deliberately outside this alpha test.
- Engine validation reproduced 2,923 baseline trades exactly; the full pandas vs
  numba parity suite passed, including every-bar stop and partial-TP cases.
- `pytest` was unavailable in the active Python environment; executable script
  assertions and the project's built-in validation commands passed.

## Builder interpretation

Hurst carries genuine return-ranking information but not diversifying information:
overweighting high-H trades raises expected return and simultaneously enlarges
loss concentration. Together with EXP-0026 (hard gate fails) and EXP-0027 (exit
conditioning fails), all three distinct monetization routes — selection,
management, and sizing — are exhausted on consumed history. Retain equal sizing
and do not optimize the 0.75/1.25 schedule.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: pending
- `MEMORY.md`: updated; Hurst sizing rejected and historical Hurst branch closed
- Shared `LEARNINGS.md`: not eligible without cross-project verification
