# Claims Register

Published values below are from Table 5 of the inspected October 2014 working
paper. They are not acceptance targets for the local futures transfer.

| Claim ID | Published claim | Published value | Local test | Status | Evidence |
| --- | --- | ---: | --- | --- | --- |
| CLM-001 | SPY `r1` sign times the last half-hour | annual return 6.67%; Sharpe 1.08; NW t=4.36; hit 54.37% | NQ/ES rule transfer, 2011-2026 | not reproducible with local universe | `reports/BASELINE_REPLICATION.md` |
| CLM-002 | Trade only when `r1` and `r12` signs agree | annual return 4.39%; Sharpe 0.98; NW t=3.96; hit 77.05% | NQ/ES joint-sign transfer | not reproducible with local universe | `reports/BASELINE_REPLICATION.md` |
| CLM-003 | Always-long SPY during last half-hour | annual return -1.11%; Sharpe -0.18; NW t=-0.73 | NQ/ES always-long control | not reproducible with local universe | `reports/BASELINE_REPLICATION.md` |
| CLM-004 | Intraday momentum is stronger with opening volume/volatility | high-volume `r1` regression R2 3.1%; high-volatility joint R2 3.3% | Context only; not used to tune the primary innovation | contextual | `paper/PAPER_SPEC.md` |

The local baseline passes only if the published rule's *post-2013 futures
persistence* survives its preregistered cost and era tests. It cannot confirm or
refute the published SPY claims.
