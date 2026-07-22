# EXP-0003 Results Discussion

- Hypothesis: `HYP-0001` — The quantified paper strategy has positive historical expectancy on the 2024 GC-as-XAU/USD proxy
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: 2024 gross and net expectancy R
- Kill test: NO-GO if 2024 gross expectancy <=0R or net expectancy <=0R at 0.24R after engine and data-quality gates pass

## Result versus hypothesis

The hypothesis is rejected. The primary 2024 run produced 17 trades with gross
expectancy +0.1176R but net expectancy -0.1224R after the frozen 0.24R cost.
At 1% current-equity risk it returned -2.14%, Sharpe -0.525, and max drawdown
6.58%. This crosses the prespecified net-expectancy kill threshold.

## Gross, net, baseline, and null comparison

The paper's 247 observations are a chosen Monte Carlo sample, not historical
qualifying signals. Historical 2024 has 18 raw signals; one entry is removed by
the FOMC blackout, leaving 17 trades. Net profit factor is 0.743. Full-history
context is harder negative: 201 trades, gross -0.0292R and net -0.2692R per
trade, with a -42.4% compounded result. Because the real pass fails, no Null C
is warranted.

## Regimes, sensitivity, and alternative explanations

The 2024 sample is small and long-heavy (14 long, 3 short), so its positive gross
estimate is imprecise. The contextual sample removes the apparent gross edge.
No parameter search was performed. All inspected history is consumed.

## Artifact and implementation risks

Data checks: no duplicate/out-of-order 15m keys, no session spanning multiple
symbols, no 2024 feature NaNs, and all 17 trade dates have usable 1s data. Twelve
of 259 2024 sessions are incomplete (69 missing 15m buckets); the engine exits
on the actual last available bar. Remaining source risks are the GC proxy, the
NY-local/fixed-UTC contradiction, the unimplementable VWAP partial protocol,
and the discretionary news stop override.

## Builder interpretation

Stage 1 is NO-GO under the user-directed 1% risk and 0.24R cost. The historical
entry mechanism does not produce anything close to the synthetic frequency,
and its small 2024 gross edge is less than half the stated cost.

## Independent review

- Review status: pending independent second-model review
- Objections: none beyond the disclosed source ambiguities
- Verdict: builder-audited NO-GO

## Promotion decision

- `reports/FINDINGS.md`: promoted
- `MEMORY.md`: promoted
- Shared `LEARNINGS.md`: not eligible without cross-project verification
