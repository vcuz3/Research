# Validation Index

| Validation concern | Current evidence | State |
| --- | --- | --- |
| Implementation forensic review | `../FORENSIC.md` | completed |
| Pipeline and edge review | `../REVIEW.md` | qualified / paper-only |
| Data quality and migration | `../DATA_AUDIT.md` | completed |
| Kill tests and Null C | `../KILL_TEST.md`, `../core/nulls.py` | faithful rerun outstanding |
| Era and regime behaviour | commands/results indexed in `../REVIEW.md` | regime dependent |
| Walk-forward tests | `../WFO.md` | historical research evidence |
| Cross-market/portfolio | `../FORENSIC.md`, `../REVIEW.md` | completed historically |
| Sealed holdout | `../MEMORY.md` | none; historical data consumed |

Validation code must use identical clocks, costs, universe, data scope, and metric
units for strategy and controls. Any future shadow protocol should be dated and
frozen here before observations arrive.
