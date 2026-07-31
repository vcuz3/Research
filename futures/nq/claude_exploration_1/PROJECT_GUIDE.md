# Cross-Asset Macro Exploration (DXY / GC / ES) Project Guide

## Objective and scope

- Research question: does an explicit macro factor — the **dollar** — carry usable
  information about gold and the equity indices? Tested four ways: as a decomposition of
  their own moves (HYP-0001), as a lead (HYP-0002), as a regime label (HYP-0003), and
  across the overnight boundary (HYP-0004).
- Instruments/markets: GC, ES, NQ 1-minute RTH, plus a synthetic causal DXY from CME FX
  futures 6E (EUR), 6J (JPY), 6B (GBP), 6C (CAD).
- Source paper: none. This is an original exploration, so `paper/` and
  `baseline_replication/` are **not applicable** and remain template stubs.
- Data source and coverage: Databento v0 continuous 1-minute files in
  `futures/data/databento/`; 2011-08-01 → 2026-07-15; **3,710** near-complete
  non-degraded ES sessions.
- **Answer: no.** All four hypotheses rejected. See `reports/FINDINGS.md`.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` — **not applicable** (no source paper) |
| Faithful replication | `baseline_replication/` — **not applicable** |
| Execution/accounting | `backtest_engine/` — **not applicable** (nothing trades) |
| Data layer, features, inference | `core/data.py`, `core/features.py`, `core/stats.py` |
| Study scripts | `scripts/` |
| Invariant tests | `tests/test_core.py` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls | `core/stats.py` (re-pairing null) + each study script |
| Immutable outputs | `artifacts/runs/EXP-XXXX/` |
| Current reports | `reports/FINDINGS.md`, `reports/DATA_QUALITY.md` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: Databento `ts_event`, tz-aware **UTC**, converted to
  `America/New_York` for the session clock. No lossy local round-trip.
- Trading calendar/session: equity RTH **09:30-16:00 ET**, anchored on the **ES** calendar.
  Sessions with fewer than 350 bars, and the shared Databento degraded-day list, are
  dropped. The equity clock anchors the whole project — gold and the dollar trade around
  it, but every decision here is made at an equity RTH minute.
- Instrument/roll convention: **v0 (volume-rank-0) continuous, unadjusted.** The v0 series
  splices contracts, so the bar at a contract change carries a fake jump (measured: median
  |r| at a 6E roll is 3.6e-3 versus 7.3e-5 off-roll, ~49x). Every return in this project is
  **NaN on a roll bar**, and prices are carried as a roll-adjusted cumulative log level.
- Corporate actions or price adjustments: not applicable to futures.
- Missing data policy: each series is reindexed onto the common RTH minute grid and
  forward-filled at most **5 minutes**; a minute where any dollar leg is still missing
  yields NaN for the index, so the basket never mixes staleness policies across legs. Every
  filled minute is counted per leg, per era and per time of day in
  `reports/DATA_QUALITY.md`. Forward-filling manufactures autocorrelation and lead-lag —
  exactly the effects measured here — hence the mandatory EUR-only control arm.
- Dollar index definition: ICE's geometric basket rebuilt from CME legs. Because every CME
  FX contract is quoted as USD per unit of foreign currency, **every leg enters `log DXY`
  with a negative coefficient**; weights are the published ICE weights renormalised over
  the available legs. Never a fitted PCA — that would be a two-sided statistic (rule 8).
- Data fingerprint command: `python -u -m futures.nq.claude_exploration_1.scripts.build_panel`

## Commands

```powershell
# Build/validate data (writes artifacts/panel_*.parquet + reports/DATA_QUALITY.md)
python -u -m futures.nq.claude_exploration_1.scripts.build_panel

# Run the invariant tests (30 checks)
python -m futures.nq.claude_exploration_1.tests.test_core

# Reproduce each registered experiment
python -u -m futures.nq.claude_exploration_1.scripts.s1_residual_momentum      # EXP-0001
python -u -m futures.nq.claude_exploration_1.scripts.s2_lead_lag               # EXP-0002
python -u -m futures.nq.claude_exploration_1.scripts.s3_factor_coherence 30    # EXP-0003
python -u -m futures.nq.claude_exploration_1.scripts.s4_overnight_impulse      # EXP-0004
python -u -m futures.nq.claude_exploration_1.scripts.s3b_gold_coherence 100    # EXP-0005
```

Approximate runtimes on this machine: panel build ~2 min (three baskets), s1 ~4 min,
s2 ~25 min (289k rows x partial ICs x 200 bootstrap draws), s3 ~8 min, s3b ~12 min,
s4 ~1 min.

## Acceptance gates

- **Baseline tolerance:** not applicable — there is no paper to replicate. In its place,
  every study asserts its own algebraic identities in-run and prints them in the artifact:
  `beta=0` reproduces raw momentum exactly (max|diff| 0.0), and
  `resid + factor == past` to 1.7e-18 on all three markets.
- **Engine tests required:** `tests/test_core.py` must be 30/30 before any study is
  interpreted. It pins: roll bars never enter a return; the roll-adjusted level has no
  splice jump but keeps the real move; minute returns never span a session; the causal β is
  blind to its own session and the future; the rolling correlation is causal, matches a
  direct window computation, and never spans a session; the same-slot z-score removes both
  per-slot level **and** scale (while the ratio-to-mean sibling removes only level); the
  matched split has identical cell sizes and identical slot composition; the regime
  contrast finds a planted regime and reads ~0 on noise; the re-pairing null is a
  year-stratified derangement that destroys pairing while preserving the donor series;
  forward windows are strictly forward and non-overlapping with past ones.
- **Minimum validation suite** for any claim in this project:
  1. the **degenerate or reversed control** — the factor leg, the reverse lead-lag
     direction, or the volatility-matched split, whichever is the construction's
     degenerate limit;
  2. the **EUR-only** dollar arm (staleness);
  3. the **lagged-endpoint** arm for any reversal claim;
  4. **both** rank IC and mean quintile spread;
  5. the **rule-18 re-pairing null**, gated on the real pass first clearing its primary
     metric;
  6. an era split, and the economic size in **ticks and dollars against a round trip**.
- **Holdout protocol:** all history through 2026-07-15 is **consumed**. Only future
  observations are clean. Nothing in this project earned a forward test.

A material experiment is complete only when its ledger row contains the config, data
scope, code reference, command, primary metric, result, artifact path, builder, reviewer,
and review status.
