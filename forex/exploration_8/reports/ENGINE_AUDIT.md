# Engine Audit

- Engine version/code reference: `backtest_engine/engine.py`, initial workbench implementation.
- Test command: `python -m pytest test_triangle.py -q`.
- Reviewer: independent review pending.

## Results

Five deterministic fixtures pass. They cover cross-rate algebra, strict feature
lagging, signal direction, next-bar timing, exact one-leg/three-leg cost deduction,
and rejection of events crossing a missing bar. See
`../backtest_engine/TEST_MATRIX.md`.

## Exceptions and risks

- The engine prices midpoint event returns, not executable orders.
- Portfolio capital, leverage, margin, financing, and concurrent three-leg fills
  are outside the current exploratory scope.
- No independent implementation parity review has occurred.

## Verdict

Passed for the limited fixed-horizon event-study scope. Not approved for an
executable arbitrage or portfolio-performance claim.
