# Engine audit

Status: **passed for the implemented scope** on 2026-08-07.

Command: `python -m pytest backtest_engine/test_engine.py -q`

Eight fixtures pass:

1. 2.5Z arming, close-back-inside trigger, next-open entry, 2ATR stop, and 1R target.
2. Same one-minute bar touching stop and target resolves to the stop.
3. Gap through a stop fills at the first observed open.
4. The Pine timeout uses strict `age > max_arm_bars`.
5. Wilder ATR is seeded by an SMA, not the common first-value EWM shortcut.
6. Session TWAP/running dispersion is causal under a future-data mutation.
7. Round-trip cost is deducted exactly once and inference clusters by session.
8. Positions do not overlap within a pair.

Material trade-table assertions also pass: entry is never before signal information,
exit is never before entry, net equals gross minus cost, and per-pair positions do
not overlap. Data-quality outputs are in `artifacts/runs/EXP-0001/`.

Limits: midpoint one-minute OHLC is not quote data. Adverse resolution bounds
same-minute ambiguity but does not reconstruct the within-minute path or spread.
