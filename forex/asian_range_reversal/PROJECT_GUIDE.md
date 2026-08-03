# Asian Range RSI Reversal Project Guide

## Objective and scope

- Test whether five-minute RSI extremes make outside observed Asian-range states
  fadeable with a frozen ATR stop and range-derived target.
- EURUSD and GBPUSD; EXP-0001 opens 2012-2020 only. Keep 2021-2023 locked until
  one post-hoc revision is frozen.
- Source: chronological IBKR one-minute midpoint files in `forex/data/`.

## Data conventions

- Timestamps are UTC; session labels use `America/New_York` with DST.
- Trading day rolls at 17:00 ET. The systematic rollover gap is reported and the
  Asian level is called `observed_asian_range`.
- Five-minute features require five exact constituent minutes and restart after gaps.
- Data fingerprint: file byte length, modification time, first/last retained time,
  row count, duplicate/order/OHLC checks in every run artifact.

## Commands

```powershell
python -m pytest forex/asian_range_reversal/tests -q
python forex/asian_range_reversal/scripts/run_hyp_0001.py --experiment-id EXP-0001
python tools/research_admin.py check --project forex/asian_range_reversal
```

## Acceptance gates

- Deterministic engine fixtures and feature fixtures pass.
- HYP-0001 kill test is applied without changing the frozen config.
- EXP-0001 must not load 2021+. The 2021-2023 strategy-specific validation era is
  locked but not pristine because related exploratory work has viewed those years.
- A survivor requires independent review, calibrated bid/ask costs, and a future
  shadow sample before any deployment interpretation.
