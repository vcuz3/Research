# Noise Area VWAP Project Guide

This is the model-neutral operating manual for the NQ/ES Noise Area replication
and follow-on research. The project predates the standard workspace layout, so
the current code and reports remain in place and the new folders index them.

## Project map

| Research concern | Authoritative location |
| --- | --- |
| Paper specification and claims | `paper/`, `REPLICATION_PLAN.md` |
| Faithful baseline | `baseline_replication/`, `scripts/forensic.py`, `scripts/run_baseline.py` |
| Execution and accounting | `core/engine.py`, `core/engine2.py`, `core/metrics.py` |
| Null models | `core/nulls.py` |
| Strategy research | `core/vol_bands.py`, `scripts/`, `STUDIES.md`, `WFO.md` |
| Run history | `experiments/ledger.csv` |
| Validation status | `validation/`, `REVIEW.md`, `FORENSIC.md`, `KILL_TEST.md` |
| Current project state | `MEMORY.md` |
| New immutable outputs | `artifacts/runs/<experiment_id>/` |

Existing `outputs/` and root reports are legacy evidence and must not be moved
without updating every reference and reproduction command.

## Data conventions

- Shared parquet datasets live in `futures/nq/data/`. The clean Databento files
  built by `core.build_clean` are the faithful datasets:
  `../data/NQ_1m_clean.parquet` and `../data/ES_1m_clean.parquet`.
- Old vendor comparison files are archived under
  `../data/archive/old_vendor_backup/`; do not recreate project-local parquet
  copies.
- Session dates, exchange calendars, time zones, and decision clocks must remain
  explicit. A same-bar signal fill is not a faithful production assumption.
- All historical periods already inspected are consumed research data. They are
  not a sealed holdout; only future shadow observations can provide clean new
  holdout evidence.

## Core commands

Build the clean data and reproduce the baseline:

```powershell
python -m futures.nq.noise_vwap.core.build_clean
python -m futures.nq.noise_vwap.scripts.forensic
python -m futures.nq.noise_vwap.scripts.run_baseline NQ 90
```

Validate engine behaviour and faithful/generalized parity:

```powershell
python -m futures.nq.noise_vwap.scripts.studies validate
python -m futures.nq.noise_vwap.scripts.bench_engine parity
```

Run further analyses only after adding or updating the matching ledger row.
Commands for historical null, era, fill, and portfolio studies remain indexed in
`REVIEW.md`.

Routine administration:

```powershell
python tools/research_admin.py new-idea --project futures/nq/noise_vwap --title "<title>"
python tools/research_admin.py new-hypothesis --project futures/nq/noise_vwap --title "<testable claim>"
python tools/research_admin.py check --project futures/nq/noise_vwap
```

## Definition of done

A material experiment is complete only when its ledger row has a frozen config
or documented legacy exception, data scope, code reference, command, primary
metric, result, evidence path, and review status. A claimed improvement must be
measured against the clean, honest baseline and survive its declared kill test.
