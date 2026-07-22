# Engine Audit

- Engine: `core/engine.py`
- Command: `python -m unittest futures.gc.vwap_ema.tests.test_engine -v`
- Result: 9/9 deterministic fixtures passed on 2026-07-22.

Covered invariants: next-bar entry, fill-bar processing, stop-first 1s path,
target-first path, adverse gap fill, frozen stop/3R geometry, wick-immune
close-only EMA50 trail, EMA20 switch after 2.5R, actual session-last-bar exit,
news entry blackout, and three-loss daily halt.

Every primary trade date has a usable 1s stream. Trail/EOD exits execute at a
completed 15m close by definition; the sole 2024 intrabar stop was 1s-resolved.

Known exceptions are source-specification limitations, not hidden engine rules:
the contradictory VWAP partial and discretionary news swing-stop override are
excluded and disclosed in `paper/PAPER_SPEC.md`.

## Verdict

Passed for the frozen deterministic subset. Independent second-model review is
still pending.
