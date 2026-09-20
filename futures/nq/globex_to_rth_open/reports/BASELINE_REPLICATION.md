# Baseline Replication

- Authoritative experiment: `EXP-0003` (supersedes EXP-0001/0002 reporting).
- Source version: user-defined strategy v1, frozen in `paper/PAPER_SPEC.md`.
- Data scope: 2011-08-02 through 2026-07-14 trade dates.
- Frozen config: `experiments/configs/study_v3.json`.
- Command: `python futures\nq\globex_to_rth_open\scripts\run_study.py`.
- Costs: one tick slippage and $2.50 commission per side, or $15 round trip.

## Equal-contract baseline

| Measure | Result |
| --- | ---: |
| Valid trades | 3,761 |
| Gross points/trade | 3.7805 |
| Gross dollars/trade | $75.61 |
| Net dollars/trade | $60.61 |
| Mean net / prior ATR14 | 0.01708 |
| Total gross / costs / net | $284,370 / $56,415 / $227,955 |
| Net daily Sharpe | 0.531 |
| HAC(5) t-statistic | 2.244 |
| Net hit rate | 54.91% |
| Maximum drawdown | -$97,010 |

The maximum drawdown is for one continuously available NQ contract and is not a
percentage return because no account capital was specified.

## Era results, equal contract

| Era | Trades | Net $/trade | Net ATR14 units | Sharpe | HAC(5) t |
| --- | ---: | ---: | ---: | ---: | ---: |
| 2011-2015 | 1,091 | $16.53 | 0.01632 | 0.657 | 1.604 |
| 2016-2019 | 1,013 | $31.22 | 0.01649 | 0.720 | 1.486 |
| 2020-2022 | 762 | $28.49 | 0.00754 | 0.193 | 0.375 |
| 2023-2026 | 895 | $174.96 | 0.02680 | 0.959 | 1.973 |

The dollar result is heavily concentrated in 2023-2026. ATR normalization
reduces, but does not eliminate, the era difference.

## Verdict

The baseline is reproduced and positive under the frozen cost model, so its
predeclared nonpositive-mean kill test does not fire. It remains provisional:
the large drawdown, cost simplification, full-sample reuse, and lack of an
independent review prevent a deployment claim.

