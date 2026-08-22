# Claims Register

| Claim ID | Claim and source | Published value | Tolerance | Local result | Status | Evidence |
| --- | --- | ---: | ---: | ---: | --- | --- |
| CLM-001 | Causal parity with the NQ logic: completed decision bar, exact next-minute open fill | required behavior | zero violations | 0 non-exact entries; 0 non-exact non-EOD exits | passed | `artifacts/runs/EXP-0001/review.md` |
| CLM-002 | Same-slot noise estimates use only prior sessions | required behavior | numerical parity within `1e-12` on an audited cell | absolute error 0 | passed | `artifacts/runs/EXP-0001/review.md` |
| CLM-003 | Missing/off-grid BTC bars are reported and never forward-filled | required behavior | zero filled synthetic bars | 4,090 loaded-slice missing minutes reported; 0 orders used a delayed fill | passed | `artifacts/runs/EXP-0001/review.md` |
| CLM-004 | BTC transfer performance | no published BTC value | descriptive only | OOS net Sharpe 0.230; IS -0.223 | provisional | `reports/BASELINE_REPLICATION.md` |
