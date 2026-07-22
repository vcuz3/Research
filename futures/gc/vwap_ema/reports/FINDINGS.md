# Findings

## EXP-0003 - Stage 1 NO-GO

- Paper frequency is synthetic: 247 Monte Carlo draws, not historical setups.
- Historical 2024: 18 signals, one news-blocked, 17 trades.
- +0.1176R gross becomes -0.1224R net at the specified 0.24R cost.
- 1%-risk result: -2.14%, Sharpe -0.525, maxDD 6.58%.
- Full history fails gross at -0.0292R/trade and net at -0.2692R/trade.
- No null is run because the real baseline fails the preregistered gate.
