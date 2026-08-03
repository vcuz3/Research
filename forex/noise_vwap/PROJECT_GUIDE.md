# Forex Noise Area TWAP Project Guide

Model-neutral operating manual. Current state and verdict live in `MEMORY.md`.

## Objective and scope

- Research question: does the Zarattini / Quantitativo Noise-Area + VWAP
  intraday momentum strategy port to spot FX majors, and — since IBKR cash FX
  publishes no size — what replaces the VWAP in its two roles (entry gate and
  trailing-stop reference)?
- Universe: EURUSD, GBPUSD, AUDUSD, NZDUSD spot, 1-minute IBKR midpoint bars.
- Source specification: `paper/PAPER_SPEC.md`. The source PDFs and the reference
  implementation live in `futures/nq/noise_vwap/`.
- Data coverage: 2011-07-20 → 2026-07-17 (NZDUSD from 2011-12-07).

## Project map

| Concern | Location |
| --- | --- |
| Adaptation contract | `paper/PAPER_SPEC.md` |
| Sessions, TWAP anchor, bands, ATR | `core/session.py` |
| Cleaning | `core/build_clean.py` |
| Execution and accounting | `core/engine.py` (reference), `core/engine_nb.py` (kernel), `core/metrics.py` |
| Null model | `core/nulls.py` |
| Hypotheses and run ledger | `experiments/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamps: tz-aware UTC in the source, converted directly to
  America/New_York. No intermediate zone.
- Sessions (ET wall clock, DST-safe — US DST switches inside the closed FX
  weekend):
  - `fxday` 17:15 ET → 16:59 ET (1,425 minutes)
  - `active` 03:00 ET → 16:59 ET (840 minutes)
  The `fxday` anchor is 17:15 rather than the nominal 17:00 roll because of a
  measured archive defect; see `reports/DATA_QUALITY.md`.
- Decision clock: pinned to the ET wall clock at `:29` and `:59`, never derived
  from minutes-from-open. This keeps decisions out of the `:00–:14` archive
  gaps and is asserted in `tests/test_core.py`.
- Volume: **none exists.** `volume == -1` on 100% of source rows;
  `core/build_clean.py` drops the column rather than carrying a constant that a
  downstream feature could silently weight by. The VWAP is replaced by the
  session TWAP, which is the VWAP formula under constant weights.
- Missing data: sessions below 90% of expected bars are dropped; the band uses
  the rule-9a fractional `min_periods` (0.9 × lookback), not the strict rule.
- Units: pips (1e-4), $10/pip/standard lot, and R = net pips / causal
  prior-session ATR(14) pips.

## Commands

```powershell
# Build clean parquet from the CSV archives
python -u -m forex.noise_vwap.core.build_clean

# Rule-9a data-quality gate (writes reports/DATA_QUALITY.md)
python -u -m forex.noise_vwap.scripts.data_quality

# Core invariants (22 checks) and engine parity (400 configurations)
python -u -m forex.noise_vwap.tests.test_core
python -u -m forex.noise_vwap.tests.test_parity

# EXP-0001: the declared port grid plus drift controls
python -u -m forex.noise_vwap.scripts.run_grid

# EXP-0002: exit-neutral entry information, re-executed mirror, futures reference
python -u -m forex.noise_vwap.scripts.entry_information
```

## Acceptance gates

- **Data:** `scripts/data_quality.py` must report band coverage at decision
  slots ≥ 0.99 with a per-slot spread ≈ 0, session-anchor stability ≥ 0.98, and
  every low-coverage window accounted for.
- **Engine:** `tests/test_core.py` and `tests/test_parity.py` must pass before
  any result is interpreted. `core/engine.py` is the definition of the rules;
  `core/engine_nb.py` must never diverge from it.
- **Result:** gross is read before net (a negative gross is a NO-GO no exit or
  cost change rescues). Effects are reported per-signal with session
  cluster-robust inference, never session-averaged — see `reports/FINDINGS.md`
  §D for why that matters here.
- **Null C** is spent only after a real pass clears its primary metric.
- **Holdout:** consumed. Only future observations are clean holdout evidence.

A material experiment is complete only when its ledger row carries the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer and review status.
