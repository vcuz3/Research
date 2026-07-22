# Hurst Exploration (NQ/ES) Project Guide

## Objective and scope

- Research question: characterize the Hurst exponent of intraday NQ/ES price
  paths as its own object — how well it can be measured, and how it varies across
  timescale — before asking whether it can trade. Motivated by the noise_vwap
  finding that intraday H is a real per-trade quality signal that monetizes as
  neither selection, exit, nor sizing on a drift-riding momentum breakout.
- Instruments/markets: NQ and ES index futures, RTH 09:30–16:00 ET.
- Source paper: none (own exploratory/statistical study).
- Data source and coverage: NQ/ES 1-minute clean Databento (`../data/{NQ,ES}_1m_clean.parquet`,
  2011-08→2026-07, 3710 RTH sessions each); NQ 1-second Databento OHLCV
  (`futures/data/databento/NQ_ohlcv-1s_NQv0_...parquet`, 2010→2026). ES 1s is not
  in the archive → every 1s result is NQ-only; ES is the 1m cross-market check.

## Project map

| Concern | Location |
| --- | --- |
| Estimator panel + fBm generator | `core/hurst.py` |
| Data loaders (1m + streaming 1s) | `core/loaders.py` |
| Estimator validation | `tests/test_hurst.py` |
| Analyses (A1, A2, …) | `scripts/a*.py` |
| Hypotheses and run ledger | `experiments/` |
| Immutable outputs | `artifacts/runs/EXP-*/` |
| Reviewed synthesis | `reports/FINDINGS.md` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: UTC in parquet; converted to America/New_York.
- Trading calendar/session: RTH 09:30–16:00 ET. Data-quality intake retains
  near-complete sessions, but estimator paths require every slot 0..389 exactly
  once. `mfo` = minutes from 09:30; 1s grid = seconds from 09:30:00 in [0, 23400).
- Instrument/roll convention: continuous front (`.v.0`), raw (not back-adjusted);
  0 RTH sessions span a roll.
- Missing data policy: 16 Databento-flagged degraded days excluded
  (`loaders.DEGRADED`). 1s bars are sparse (only traded seconds); the regular
  grid is forward-filled and the fill-rate reported per Rule 9a. Incomplete 1m
  paths are reported and excluded rather than time-compressed. Sub-minute /
  micro claims restricted to fill ≥ 0.90 and era ≥ 2015.
- Data fingerprint: raw eligible 1m input has 3710 sessions per market; exact-grid
  estimator input has 3703 NQ / 3706 ES sessions. Material-run manifests record
  Parquet metadata plus code and output hashes.

## Commands

```powershell
# Validate the estimator panel against synthetic fBm of known H
python -m futures.nq.hurst_explore.tests.test_hurst

# A1: measurement-error floor (synthetic floor + real cross-estimator agreement)
python -u -m futures.nq.hurst_explore.scripts.a1_measurement_floor   # --quick for a fast pass

# A2: Hurst term structure across timescale H(tau), with matched RW control
python -u -m futures.nq.hurst_explore.scripts.a2_timescale           # --quick for a fast pass

# Review-driven calibration/bootstrap regressions
python -m futures.nq.hurst_explore.tests.test_analysis
```

## Acceptance gates

- Estimator gate: the panel must recover known synthetic H at a long window
  (ghe1/ghe2/dfa within 0.05, R/S within 0.11 given its known +bias) — enforced
  by `tests/test_hurst.py`.
- Measurement studies (A-series) are descriptive: no trading claim, no Null-C.
  Any predictive (B-series) or strategy (C-series) claim MUST add a claim-matched
  null, fill feasibility, and — for any 1s bracket/fade — 1s intrabar resolution
  (per the GC coarse-bar-fill learning), before it is presented as an edge.
- A structural claim must be shown to survive its matched control (e.g. the RW
  saturation control in A2) and, where the mechanism predicts it, to transfer to
  the ES sibling.
- Structural descriptions must report dependence-aware uncertainty, band-endpoint
  sensitivity, and era stability. Cross-frequency and NQ/ES agreement are
  corroboration, not statistically independent samples.

A material experiment is complete only when its ledger row and manifest contain
the config, data scope, code reference, command, primary metric, result,
artifact path, builder, and review status.
