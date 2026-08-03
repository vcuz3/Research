# EXP-0002 Results Discussion

- Hypothesis: `HYP-0002` — London first-trade bounded-RSI midpoint fade
- Status: completed; locked-era kill test failed
- Builder: Codex
- Reviewer: not independently reviewed
- Scope: 2021-2023 only; frozen before run

## Result versus hypothesis

The revised strategy improves gross expectancy but fails the declared 0.5-pip
pair-and-direction gate.

| Slice | Trades | Gross pips/trade | Net at 0.5 pip |
|---|---:|---:|---:|
| EURUSD all | 618 | +0.476 | -0.024 |
| GBPUSD all | 624 | +0.808 | +0.308 |
| EURUSD long | 315 | +0.586 | +0.086 |
| EURUSD short | 303 | +0.361 | -0.139 |
| GBPUSD long | 338 | +0.287 | -0.213 |
| GBPUSD short | 286 | +1.423 | +0.923 |

Every gross slice is positive and every directional slice has at least 100
trades, but two required net slices and EURUSD pooled are negative.

## Risk, uncertainty, and stability

- Twenty-day moving-block 95% intervals include zero for every pair and side.
- Equal-risk sizing is weaker: net mean at 0.5 pip is -0.053R EURUSD and -0.010R
  GBPUSD. Only GBPUSD shorts remain positive (+0.024R).
- A one-unit two-pair portfolio has net daily Sharpe 0.18 and approximately
  -450 pips maximum drawdown.
- Annual signs are unstable. GBPUSD shorts are -1.54 net pips/trade in 2021 but
  +2.22/+2.08 in 2022/2023. EURUSD longs are -1.50/+2.92/-1.04. This is not a
  stable validation result.

## Execution and state audit

- Exactly one or zero trades per pair/day; 618/624 trades over 768 eligible days.
- The cap suppressed 2,158/2,272 later qualifying signals.
- Entry bars are in London only; no target was already marketable at entry.
- Target rates are 29-32%; stops are 68-71%; only six total EOD exits.
- No one-minute stop/target ambiguity occurred in this run.

## Interpretation

The London/bounded-RSI/first-trade revision transformed a negative discovery
baseline into positive gross expectancy across all four pair/direction slices.
That is encouraging mechanistically, but it is not robust after costs, sizing,
uncertainty, or annual stability. The strict verdict is FAIL/NO-GO.

Do not rescue the result by selecting GBPUSD shorts after seeing this table; that
would consume the validation interval and require future-only evidence. Further
historical parameter adjustment would be a new discovery cycle, not validation.

## Independent review

- Review status: pending
- Verdict: not independently reviewed

## Promotion decision

- Not approved for deployment or another claim on historical validation.
- Preserve as a possible future shadow hypothesis only if executable costs are
  demonstrated below the observed break-even and the exact rule remains frozen.
