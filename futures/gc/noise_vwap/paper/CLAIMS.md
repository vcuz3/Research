# Claims Register (GC)

GC is a method port, not a published-value replication (the source paper covers
equity indices, not gold). The "claim" here is that the audited NQ/ES machinery
transfers to gold, measured against the strategy's own honest baseline and nulls.

| Claim | Target | Current GC result | Status | Evidence |
| --- | --- | ---: | --- | --- |
| Positive gross per-trade edge | > 0, significant | gross Sharpe 0.77, day-$ t=+2.11 | provisional | `../reports/BASELINE.md` |
| Positive net edge at realistic cost | > 0, significant | net Sharpe 0.46, t=+1.25 @0.50 tick | marginal / provisional | `../reports/BASELINE.md` |
| Edge exceeds a valid session null | beat Null C | not yet run | open | `../MEMORY.md` |
| Robust, persistent post-cost edge | qualitative | cost-fragile; not validated | not deployment-ready | `../reports/BASELINE.md` |

Values are headline approximations before vol-target sizing. See the cited report
for exact definitions and full precision.
