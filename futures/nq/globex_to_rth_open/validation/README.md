# Validation Plan

No historical row is a sealed holdout. The next validation run should:

1. Preserve overnight return paths and all execution/accounting rules.
2. Destroy the association between causal MA/VIX state and the same trade date,
   using feature-date permutations within appropriate calendar/era blocks.
3. Rerun all six MA cells, all 27 VIX ranges, all four sizing modes, and the same
   maximum/selection rule on every draw.
4. Compare the observed best-cell improvement with the distribution of selected
   null improvements, not with a single shuffled result.
5. Add matched-trade-rate gates, filter complements, and 18:00 cost stress.
6. Reserve only future observations for a clean shadow test.

Until this exists, `reports/FINDINGS.md` is exploratory evidence only.

