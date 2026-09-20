# Claims Register

No performance claim was supplied. The requested strategy is a discovery-stage
hypothesis, not a paper replication.

| Claim ID | Claim | Decision rule | Status | Evidence |
| --- | --- | --- | --- | --- |
| CLM-001 | The requested rules can be implemented causally on all four pairs. | All engine tests pass and all pairs have valid feature coverage. | passed | `reports/ENGINE_AUDIT.md` |
| CLM-002 | Low-volatility false breakouts have positive gross expectancy. | GO only if pooled gross mean R > 0, a date-cluster bootstrap 95% CI excludes 0, and at least 3/4 pairs have positive mean gross R. | passed, exploratory and cost-fragile | `artifacts/runs/EXP-0001/summary.json` |
