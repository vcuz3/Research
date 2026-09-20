# NQ/ES Percentile-Rank Momentum + Bimodal Expected-Value Project Guide

## Objective and scope

- Research question: Can same-slot self-ranked momentum plus hysteresis and a causal expected-value classifier produce a robust NQ edge?
- Instruments/markets: NQ primary; ES untuned sibling transfer.
- Source papers: see `paper/PAPER_SPEC.md`.
- Data source and coverage: audited `../data/NQ_1m_clean.parquet` and `ES_1m_clean.parquet`, 2011-08-01 to 2026-07-14 eligible RTH sessions.

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

- Timestamp source and timezone: timezone-aware UTC source converted DST-correctly to America/New_York.
- Trading calendar/session: RTH 09:30–16:00 ET; 5-minute bars; feature decisions nominally from 10:00.
- Instrument/roll convention: cleaned continuous front contract; no RTH multi-symbol sessions or roll rows.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: no fill-forward; sessions below 350 one-minute bars excluded; remaining missing slots counted.
- Data fingerprints: `artifacts/runs/EXP-0001/data_audit.json`.

## Commands

```powershell
# Build/validate data
python -m futures.nq.percentile_rank_momentum.validation.coverage_report --experiment-id EXP-0001

# Reproduce faithful baseline
not applicable — two-source synthesis

# Run engine tests and parity fixtures
python -m pytest futures/nq/percentile_rank_momentum/tests -q
python -m futures.nq.noise_vwap.scripts.studies validate

# Run one registered experiment
python -m futures.nq.percentile_rank_momentum.experiments.run_hyp0001 --experiment-id EXP-0002
```

## Acceptance gates

- Baseline tolerance: exact engine-replayed trade counts; matched B1 uses nearest discrete threshold without interpolation.
- Engine tests required: commands above plus project hygiene check.
- Minimum validation suite: gross/net, B0-B4, matched count, alpha × W surface, eras, ES sign transfer; Null C only after real-data gates.
- Holdout protocol: full archive consumed; future-only.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
