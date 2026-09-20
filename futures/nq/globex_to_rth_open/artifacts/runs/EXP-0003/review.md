# EXP-0003 Results Discussion

- Hypothesis: `HYP-0001`.
- Status: completed.
- Builder: Codex.
- Reviewer: unassigned.
- Primary metrics: net ATR14 units/trade, dollars, Sharpe, HAC(5) t by full
  sample and era.

## Result versus hypothesis

The baseline positive-mean kill test did not fire. SMA200 and high-VIX ranges
are exploratory leads. None can be accepted because full-family nulls and
independent review are pending.

## Gross, net, baseline, and controls

Baseline gross/net is $75.61/$60.61 per trade after $15 cost. Exact clocks,
roll exclusions, lagged features, hand accounting, era splits, and ATR
normalization passed. No selection-aware null was run.

## Regimes and alternative explanations

The baseline is positive in all four eras but dollar P&L is concentrated after
2023. VIX >=25 remains positive after ATR normalization, yet its era counts are
uneven and crisis regimes dominate. SMA200 is positive in each era but is one of
six searched clocks and changes trade frequency.

## Builder interpretation

WATCH. Preserve the positive baseline and MA/VIX leads for validation. Treat the
failure of all three inverse-vol rules to dominate equal sizing as meaningful
negative evidence.

## Independent review

- Review status: pending.
- Verdict: pending.

## Promotion decision

- Promoted to `reports/FINDINGS.md` and `MEMORY.md` as provisional only.
- Not eligible for shared learnings.

