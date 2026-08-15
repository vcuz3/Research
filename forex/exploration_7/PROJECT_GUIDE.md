# FX weekend gap reversion Project Guide

## Objective and scope

- Research question: <question>
- Instruments/markets: <universe>
- Source paper: `paper/source.pdf` or <source URL/citation>
- Data source and coverage: <source, version, dates>

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

- Timestamp source and timezone: <value>
- Trading calendar/session: <value>
- Instrument/roll convention: <value>
- Corporate actions or price adjustments: <value or not applicable>
- Missing data policy: <value>
- Data fingerprint command: <command>

## Commands

```powershell
# Build/validate data
<command>

# Reproduce faithful baseline
<command>

# Run engine tests and parity fixtures
<command>

# Run one registered experiment
<command>
```

## Acceptance gates

- Baseline tolerance: <claim-specific tolerances>
- Engine tests required: <commands/tests>
- Minimum validation suite: <nulls, costs, regimes, neighbours, cross-market>
- Holdout protocol: <sealed dates or future-only plan>

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
