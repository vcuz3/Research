# Project Memory: Asian Range RSI Reversal

## Scope

- Objective: test stateful five-minute RSI fades outside the observed Asian range.
- Markets: EURUSD and GBPUSD midpoint OHLC.
- Data: `forex/data/*usd_intraday_1min.csv`.
- Current phase: post-hoc discovery after initial baseline rejection.

## Current status

- Verdict: initial specification and frozen locked-era revision both rejected.
- Last verified: 2026-08-03.
- Lifecycle phase: experiment loop.
- Engine audit: deterministic causality/ambiguity tests pass; independent review pending.
- Execution: completed 5m signal, next-5m-open entry, frozen 2x ATR stop,
  one-minute adverse barrier resolution, 16:59 ET timeout, stateful non-overlap.
- Discovery consumed: 2012-2020.
- Validation consumed: 2021-2023 was scored once by frozen HYP-0002. It was not a
  pristine market holdout because related exploration previously exposed it.
- Reproduction: `python forex/asian_range_reversal/scripts/run_hyp_0001.py --experiment-id EXP-0001`.
- Evidence: `artifacts/runs/EXP-0001/`.

## Confirmed findings

- EXP-0001 midpoint: -0.095/-0.078 gross pips/trade EURUSD/GBPUSD over
  9,402/9,797 trades. At 0.5 pip: -0.595/-0.578; daily Sharpe -1.01/-0.78.
- Opposite target is worse: -0.177/-0.114 gross pips/trade.
- Long midpoint gross is -0.247/-0.248. Short gross is +0.064/+0.104 but below cost.
- Equal-risk net mean at 0.5 pip is also negative: -0.035R/-0.041R.
- About 4.1-4.3 trades occur per eligible day; 21k-22k qualifying midpoint
  signals are discarded per pair because a position is open.

## Provisional post-hoc findings

- London midpoint shorts are +0.66/+0.72 gross and +0.16/+0.22 after 0.5 pip.
- Mild RSI exceedances outperform severe extremes in both pairs; the most
  extreme RSI quintile loses heavily, consistent with continuation.
- Highest-ATR quintile loses about 1.5 pips gross across both pairs and sides.
- Later repeat entries tend to degrade, but sequence behavior is not stable enough
  across pair/direction to freeze a cap without further judgment.

## EXP-0002 locked-era result

- Frozen revision: London only, midpoint target, RSI 70-75/25-30, first executed
  trade per pair/day, otherwise identical execution.
- 618 EURUSD and 624 GBPUSD trades over 768 eligible days. Gross is +0.476/+0.808
  pips/trade; at 0.5 pip it is -0.024/+0.308.
- Directional net: EUR long +0.086, EUR short -0.139, GBP long -0.213, GBP short
  +0.923. It fails the predeclared requirement that both pairs and directions pass.
- All 20-day block intervals include zero. Equal-risk net is -0.053R/-0.010R by
  pair. Two-pair one-unit daily Sharpe is 0.18 with about -450 pips drawdown.
- Annual signs are unstable; do not promote the strong GBPUSD-short cell post hoc.

## Decisions and constraints

- 2012-2020 and 2021-2023 are now consumed for this family. Further historical
  filtering is discovery, not validation; only future data can provide a clean test.
- Do not infer a revised stateful result by filtering completed EXP-0001 trades;
  skipped trades change which later signals are eligible, so rerun the engine.
- Complete observed Asian range is unavailable due systematic rollover gaps.

## Next actions

1. Close the historical strategy as NO-GO or freeze it unchanged for future shadow only.
2. Obtain independent engine/result review before relying on mechanics.
3. Calibrate executable bid/ask costs if considering a future shadow test.
