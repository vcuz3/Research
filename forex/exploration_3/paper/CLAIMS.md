# Claims register

| ID | Claim | Metric / tolerance | Status |
| --- | --- | --- | --- |
| C-01 | State machine matches the clarified 2.5Z arm, re-entry, 2ATR stop, and 1R target. | Executable fixtures exact to `1e-10`. | Passed |
| C-02 | No bar-close signal trades before the next observed complete 15-minute open. | Every `entry_time >= signal_time`; exact fixture. | Passed |
| C-03 | The selected pre-2020 baseline has positive net value in 2021-2023. | Net mean pips > 0, daily net-pip Sharpe > 0, at least 3/4 pairs positive. | Failed EXP-0001 |
| C-04 | Any OOS survivor repeats in 2024-latest. | Same three thresholds as C-03. | Failed EXP-0001 |
| C-05 | A historical survivor is deployable. | Not claimed: requires measured spreads, a path-preserving null, and future shadow data. | Out of scope |
