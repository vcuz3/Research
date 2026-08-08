# Anchored TWAP/SMA Z-band Strategy Project Guide

## Objective and scope

- Research question: does the clarified close-reentry Z-band fade retain net value out of sample?
- Instruments/markets: AUDUSD, EURUSD, GBPUSD, NZDUSD spot-FX midpoint bars.
- Source: user-supplied Pine v6 script, transcribed in `paper/PAPER_SPEC.md`.
- Data source and coverage: `../data/clean/*_1m_clean.parquet`, 2011-07/12 through 2026-07-17.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` |
| Faithful replication | `baseline_replication/` |
| Execution/accounting | `backtest_engine/` |
| Features/signals/sizing | `strategy/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: timezone-naive UTC `ts_utc`; converted with IANA DST rules for session features.
- Trading calendar/session: continuous spot FX; TWAP sessions start 17:00 America/New_York.
- Instrument/roll convention: spot FX, no rolls.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: signals use only complete 15-minute bars; gaps remain visible and pending entries use the next observed complete-bar open.
- Data fingerprint: material-run `run_manifest.json` records SHA-256, row count, and coverage for every file.

## Commands

```powershell
# Build/validate data
python -m pytest backtest_engine/test_engine.py -q
python _build_single_pair_notebook.py
python _smoke_run_single_pair_notebook.py

# Reproduce faithful baseline
python run_research.py --output-dir artifacts/runs/EXP-0001

# Run engine tests and parity fixtures
python -m pytest backtest_engine/test_engine.py -q

# Run one registered experiment
python run_research.py --output-dir artifacts/runs/EXP-0001
```

## Acceptance gates

- Baseline tolerance: exact state/fill fixtures; deterministic reruns should match to 1e-10.
- Engine tests required: `python -m pytest backtest_engine/test_engine.py -q`.
- Minimum validation suite: gross/net, cost stress, pair/year splits, adverse ambiguity, and later path-preserving null before any edge claim.
- Holdout protocol: `single_pair_zband_workbench.ipynb` excludes 2024+ at the Parquet-load boundary unless the final-confirmation switch is set. EXP-0001 already consumed 2024-2026-07-17, so scientifically clean evidence is future-only even though the notebook now demonstrates the intended workflow.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
