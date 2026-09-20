# Engine Audit

- Code: `strategy/signals.py`, `backtest_engine/engine.py`.
- Test command: `python -m pytest -q`.
- Result: 11 passed on 2026-09-19.
- Reviewer: independent review pending.

## Verified invariants

- Wilder ATR has an SMA seed and recursive updates.
- ATR percentile and breakout levels exclude the current candle.
- Completed-bar signals enter at the first available later minute open.
- Brackets are active on the entry minute and frozen from signal ATR.
- Gap-through stops fill at the first tradable open.
- Nondeterministic stop/target ordering within a minute resolves to the stop;
  19 such exits are labelled `stop_ambiguous` in EXP-0001.
- Opposite signals exit at their executable open without same-time reversal.
- Round-trip costs are deducted exactly once and positions do not overlap per pair.
- Optimisation input is predicate-filtered before the reserved cutoff and guarded
  by fail-closed timestamp assertions.
- Daily FX accounting retains Sunday-UTC exits on a calendar-day index. This
  corrects the EXP-0001 artifact's business-day Sharpe report; trade P&L was unaffected.

## Exceptions and risks

- One-minute OHLC cannot order events within a minute; the adverse rule bounds,
  but does not reconstruct, those paths.
- The source is midpoint data. Spread, latency, financing, and market impact are
  sensitivities rather than measured fills.
- No independent parity implementation or reviewer has signed off yet.

## Verdict

Mechanically fit for exploratory baseline use; not yet validated for deployment.
