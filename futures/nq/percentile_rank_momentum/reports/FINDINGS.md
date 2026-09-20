# Findings

## HYP-0001 — rejected / NO-GO

`EXP-0001` passed the P&L-blind Rule-9a gate after the user amended the infeasible
90% same-sign minimum to 40%. Coverage is 85.5%–89.9% across W=60/90/120/252.
The first six nominal decision slots are unavailable to the 60-minute RTH horizon
and are explicitly dropped and counted. Evidence:
`../artifacts/runs/EXP-0001/DATA_QUALITY.md`.

`EXP-0002` rejects the trading hypothesis on the common 3,275-session sample:

| Arm | Trades | Gross ticks/trade | Net ticks/trade | Cluster t | Zero-day Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: |
| B1 direct, q=.85 | 7,830 | +0.782 | -1.118 | -1.03 | -0.286 |
| B2 hysteresis | 7,059 | +1.640 | -0.260 | -0.19 | -0.053 |
| B3 classifier argmax | 18,359 | +0.915 | -0.985 | -1.13 | -0.314 |
| B4 classifier E[r] | 9,428 | **-0.122** | **-2.022** | -1.62 | -0.450 |
| B1 matched count, q=.82 | 9,511 | +0.278 | -1.622 | -1.69 | -0.469 |

Confirmed within this experiment:

- **Gross gate failed:** B4 is negative before costs.
- **ML-value gate failed:** B4 trails matched-count B1 by 0.400 net tick/trade.
- **Sibling-sign gate failed:** ES B4 gross is +0.331 tick/trade, opposite NQ,
  and remains -1.029 ticks/trade net.
- **No parameter rescue:** all 24 alpha × W × {B1,B2} cells are net-negative.
  Hysteresis improves the direct feature, but best center gross (+1.640 ticks)
  remains below the modeled 1.9-tick NQ round-trip cost.
- **Era instability:** B4 gross is negative in 2011-2014 and 2023+, weakly
  positive in the middle eras, and net-negative in all four.
- **Risk:** B4 total net is -$95,306 per NQ contract; start-zero max drawdown
  -$99,700, worst day -$13,954, and worst week -$18,504.

Null C was not spent because the pre-registered real-data gross and ML gates
failed. Detailed evidence: `../artifacts/runs/EXP-0002/review.md`,
`ladder_NQ.csv`, `stability_surface_nq.csv`, `era_metrics_*.csv`,
`matched_count_grid_*.csv`, and `risk_reconciliation.csv`.

Verdict: **reject HYP-0001 and do not deploy or continue tuning this historical
sample.** A materially new feature requires a new hypothesis. All inspected
history is consumed, so only future observations are a clean holdout.
