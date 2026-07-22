# Claims Register

| ID | Published claim | Value | Tolerance | Local result | Status |
| --- | --- | ---: | ---: | ---: | --- |
| CLM-001 | 2024 trade count | 247 | +/-5% | 17 | fail |
| CLM-002 | Win rate | 45.3% | +/-5 pp | 29.4% | fail |
| CLM-003 | Net expectancy | +0.414R | +/-0.05R | -0.122R | fail |
| CLM-004 | Profit factor | 1.76 | +/-0.20 | 0.743 net | fail |
| CLM-005 | Total return at 1% risk | +102.2% | +/-2 pp | -2.14% | fail |
| CLM-006 | Annualised Sharpe | 3.99 | +/-0.25 | -0.525 | fail |
| CLM-007 | Maximum drawdown | 5.1% | +/-2 pp | 6.58% | pass numerically, strategy loses |

Published values are synthetic simulation outputs. Failure to match them with
historical data is evidence against external validity, not a coding tolerance
failure that should be optimized away.

Local evidence: `../artifacts/runs/EXP-0003/summary.json`.
