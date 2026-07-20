# GC VWAP Reversion Project Guide

Model-neutral operating manual for the GC (COMEX Gold) VWAP standard-deviation-band
mean-reversion (fade) baseline. Distinct from `futures/gc/noise_vwap` (a noise-area
momentum/breakout strategy); this project shares only the raw clean data, the RTH
convention, and the contract economics.

## Objective and scope

- Research question: does fading a ±2σ stretch of intraday gold around its session
  VWAP, with a fixed 2:1 bracket to VWAP, produce a net edge under honest fills?
- Instrument: GC (COMEX Gold); deployed on MGC micro (1/10 notional).
- Data: Databento `GC.v.0` raw continuous; 1-second RTH archive for accurate
  intrabar fills, 1-minute for comparison.

## Project map

| Concern | Location |
| --- | --- |
| Strategy spec / claims | `paper/PAPER_SPEC.md`, `paper/CLAIMS.md` |
| Frozen baseline config | `baseline_replication/configs/faithful_config.json` |
| 1s clean data build | `core/build_clean_1s.py` → `../data/GC_1s_rth.parquet` |
| Session, VWAP, σ bands | `core/data.py` (`load_rth`, `load_rth_1s`) |
| Fade engine (numba) | `core/engine.py` |
| Metrics (day-clustered) | `core/metrics.py` |
| Baseline runner | `scripts/run_baseline.py` |
| Baseline report | `reports/BASELINE_REPLICATION.md` |
| Run history | `experiments/ledger.csv` |
| Current state | `MEMORY.md` |

## Contract economics

GC: 100 troy oz, tick 0.10 = $10, 1 point = $100. Set in `core/data.py`.

## Commands

```powershell
# Build the shared GC 1s RTH clean file (once; ~40M rows, 479 MB)
python -m futures.gc.vwap_reversion.core.build_clean_1s

# Reproduce the baseline (1s = accurate fills; 1m for comparison)
python -m futures.gc.vwap_reversion.scripts.run_baseline GC 1s
python -m futures.gc.vwap_reversion.scripts.run_baseline GC 1m
```

## Data and session conventions

- Timestamps UTC in the parquet; converted to America/New_York (DST-correct).
- RTH cash 09:30–16:00 ET; entry window 10:00–15:00 ET.
- Raw unadjusted continuous (intraday ratios distorted by additive adjustment);
  0 RTH sessions span a roll.
- Shared GC source parquet lives in `futures/gc/data/`; project-local data
  folders should not duplicate the same instrument archive.
- Missing data: 1s sessions are sparsely populated (median ~9540 bars); sessions
  with < `MIN_BARS_1S` (3000) traded seconds are dropped.
- All inspected history is consumed research data, not a sealed holdout.

## Acceptance gates

- Fill feasibility asserted in code (`scripts/run_baseline.py::assert_fills`): every
  entry/exit fill attainable within its bar; gaps fill at the open (rule 5).
- Baseline must report gross AND net (rule 20) and a day-clustered risk unit
  (rule 13/22). A claimed edge must be sign-stable across the conservative vs
  path-optimistic fill and survive the strict trade-through entry.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
