# Findings

## EXP-0001 — NO-GO

Pre-2020 model selection compared session TWAP with SMA(10/20/40/80), keeping
the user-confirmed 2.5Z/2ATR rules fixed. Every candidate was negative net at a
1-pip round trip. SMA(80) ranked first only because its daily Sharpe was least
negative.

| Period | Trades | Gross pips/trade | Net pips/trade | Daily net Sharpe | Clustered net-R t |
| --- | ---: | ---: | ---: | ---: | ---: |
| Train before 2020 | 13,262 | -0.442 | -1.442 | -2.292 | -8.32 |
| OOS 2021-2023 | 4,756 | +0.350 | -0.650 | -0.929 | -2.48 |
| Holdout 2024-2026-07-17 | 3,929 | +0.357 | -0.643 | -1.220 | -2.89 |

All four pairs were negative net in OOS and holdout. The gross later-period
effect becomes negative after only 0.5 pip of round-trip cost. The prespecified
kill test fails and the historical holdout confirms the failure.

Detailed evidence: `artifacts/runs/EXP-0001/review.md` and the notebook.
