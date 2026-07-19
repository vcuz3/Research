# Evaluation of `5095349_extracted.txt`

## Verdict

The paper is useful as an **idea source**, but its reported Sharpe ratios above
3 and annualized returns above 50% are not credible evidence that the same edge
will transfer to NQ or ES futures. The results are discovery-stage, in-sample
optimization on QQQ equities. They should not alter the project's current
qualified/watchlist verdict.

The highest-value previously untested claim was that very short, causal noise
lookbacks (2-8 prior sessions) adapt better than the 14/90-session baselines.
`EXP-0008` now rejects that claim on NQ and ES after full-family Null C selection
correction. Several other headline ideas have already been tested locally and
should not be reopened without new evidence.

## What the paper actually establishes

- It implements the Noise Area strategy on QQQ/SPY 1-second trade bars from
  2014-10-01 to 2024-10-01 and reports a weaker baseline than the source paper.
- It searches wide ranges for lookback, entry threshold, sizing, entry time,
  trade frequency, exit time, exit boundary, and ladder levels, optimizing
  Sharpe and alpha on the same ten-year period.
- The selected QQQ configurations report Sharpe 2.11-3.35, annualized return
  34%-60%, and maximum drawdown 11%-22%.
- All selected configurations use 2-8 day lookbacks. Selected VWAP-only exits
  use entry multipliers near or below 1.0; selected ladder variants use roughly
  1.28-1.33.
- Several optimized ladder targets are acknowledged to be practically
  unreachable, making those configurations close to stop-plus-time exits.

These are accurate summaries of the document, not independently verified
findings.

## Main evidentiary weaknesses

1. **No reported untouched holdout or walk-forward test.** A large continuous
   and discrete search is evaluated on the optimization period itself. The
   best Sharpe is therefore a selected maximum, not an unbiased performance
   estimate.
2. **No multiple-testing correction or full-pipeline null.** Optimizing two
   objectives over many interacting parameters can easily produce impressive
   survivors even when the machinery is exploiting drift or payoff geometry.
3. **Entry/exit sequencing is underspecified.** Signals use the favorable bar
   extreme (high for long entry, low for short entry) on 1-second bars, but the
   extract does not prove when an order becomes active, what price it receives,
   how gap-throughs fill, or how same-bar stop/target ambiguity is resolved.
4. **The exit search changes payoff geometry.** Ladder and asymmetric exits can
   raise Sharpe without proving better entry information. Symmetric or fixed-
   horizon diagnostics and claim-matched nulls are absent.
5. **Sizing drives headline returns.** Direction-specific equity margin,
   available-margin sizing, and target volatility differ materially from CME
   futures economics. Most selected trades use 100% of available margin.
6. **Daily statistics are preferable to per-trade statistics, but incomplete.**
   The paper reports daily Sharpe and drawdown, yet does not expose clustered
   inference, gross-versus-cost decomposition by era, capacity, turnover, or
   daily/weekly tail concentration.
7. **There is an internal ambiguity in the exit-boundary constraint.** The text
   says the exit boundary can be narrower and states
   `volatility_multiplier_exit < volatility_multiplier_enter`, while the
   differential formula is easy to misread and should be reconciled against
   source code before replication.
8. **Transport is nontrivial.** QQQ cash-session trading, equity commissions,
   dividends, margin, and a 15-minute early flat are not NQ/ES contract rules.

## Crosswalk to existing project evidence

| Paper theme | Local evidence | Disposition |
| --- | --- | --- |
| VWAP-only or alternate band/VWAP stop | `WFO.md` Design B: zero OOS Sharpe uplift; Null C identifies a machinery amplifier | Do not prioritize |
| Different decision frequencies | `STUDIES.md`: 30 minutes is the local sweet spot among 5/15/30/60 | Already tested |
| Partial profit-taking / runner | `STUDIES.md`: `tp0.75_67` is a qualified family-wise Null C survivor | Continue only in future shadow or as a preregistered ladder extension |
| Break-even stop | `STUDIES.md`: no material improvement | Closed absent new mechanism |
| Short 2-8 day lookback | `EXP-0008`: NQ ΔSharpe -0.065/p=0.8571; ES +0.026/p=0.1905 | Rejected |
| Exit before close | Not isolated under current working config | Small secondary ablation |
| Equity margin/target-vol sizing | Futures project uses causal contract-aware sizing | Risk study only; no alpha claim |

## Backlog and test artifacts

- Structured backlog: `experiments/IDEA_BACKLOG.md` (`IDEA-0001` through
  `IDEA-0006`).
- Promoted test: `experiments/hypotheses/HYP-0001.md`.
- Executable tester: `scripts/paper_5095349_hypothesis_test.py`.

All historical data in this project is already consumed. A survivor remains a
research screen and requires independent review plus future-only shadow evidence.
