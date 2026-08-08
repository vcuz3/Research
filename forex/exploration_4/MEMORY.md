# exploration_4 — Project Memory

## What this project is
A single **frozen, naive mean-reversion baseline** for USD-major spot FX, built to
be the reference book that a *later* project holds regime overlays up against. It is
the middle step of: describe → **freeze naive baseline** → post-hoc regime overlays
→ promote survivors. **Not** a strategy to optimize.

## Status
**Planned, not built** (2026-08-08). Build spec: `PROJECT_PLAN.md`. Frozen
pre-registration: `KILL_TEST.md`. Builder/reviewer: unassigned.

## The frozen design (do not tune)
- Feature: standardized displacement `z = (close_t/close_{t-6} − 1)/(σ·√6)`, plain
  rolling σ over 100 bars with a fractional min_periods floor.
- Bars: 5-min (from `forex/data/clean/{PAIR}_1m_clean.parquet`).
- Entry: first crossing of `|z| ≥ 2`, fade, filled at next-bar open; one position
  per pair; no fixed time clock.
- Exit: reversion to `z=0` OR compulsory 1.5σ single-barrier stop (both frozen at
  entry). News-blackout veto on entries.
- Estimand: per-signal mean net R, day-clustered SE; gross/cost/net by era.

## Hard project constraints (inherited)
- Compulsory single-barrier stop on every trade (prop-firm challenge).
- No fixed time clock in decisions.
- High-impact-news blackout is a standing veto.
- Data is **midpoint** OHLC, `volume == -1` → spread unmeasured → report a
  **breakeven-pip curve**, never a single net number.

## Key reuse
Engine, cost model, and news table live in `forex/exploration_1/`
(`_rsi_stop_engine.py`, `_bracket_engine.py`, `_cost_model.py`,
`_run_rsi_axis6_calendar.high_impact_times`). Import; do not reimplement fills.

## Mandatory diagnostics (asymmetric target → required)
1. Entry-information: symmetric-bracket + fixed-horizon rerun (Rule 15).
2. Random-exit control at matched exit rate.

## Open decisions / notes
- Target geometry fixed to reversion-to-0 (user, 2026-08-08).
- 4 pairs are EUR/GBP/AUD/NZD (no USDJPY in archive); ~2 effective independent.

## Verdict
_pending build._
