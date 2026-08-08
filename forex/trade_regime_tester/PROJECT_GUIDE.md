# Reusable Trade Regime Tester Project Guide

## Objective and scope

- Research question: Under which causally observable market regimes does a
  frozen strategy's trade-level expectancy remain stable from training to test?
- Instruments/markets: One configurable FX pair per notebook run, with an
  optional independent benchmark and cross-asset/macro inputs.
- Source paper: Not applicable; this is a reusable validation utility rather
  than a paper replication.
- Data source and coverage: Strategy-supplied completed trades; clean FX minute
  parquet under `forex/data/clean`; optional point-in-time macro and archived
  market-level files. Every run declares exact paths and split dates.

## Project map

| Concern | Location |
| --- | --- |
| Notebook and input contract | `trade_regime_tester.ipynb`, `README.md` |
| Feature and causal-join notes | `strategy/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: timezone-naive UTC after parsing; zoned inputs
  are converted to UTC.
- Trading calendar/session: continuous FX timestamps; descriptive UTC sessions
  are Asia 00:00-06:59, London 07:00-12:59, overlap 13:00-16:59, New York
  17:00-21:59, and rollover 22:00-23:59.
- Instrument/roll convention: spot FX pair selected in the configuration cell;
  no futures roll.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: source observation coverage is retained as a feature;
  feature eligibility requires configured train/test coverage and regime cells
  below the minimum count are flagged.
- Data fingerprint: the notebook emits a configuration fingerprint; material
  exports store source paths, split dates, thresholds, and learned parameters.

## Commands

```powershell
# Build the notebook from the reviewed source
python forex/trade_regime_tester/_build_notebook.py

# Execute every code cell with a shortened sealed-holdout sample
python forex/trade_regime_tester/_smoke_run_notebook.py

# Execute every code cell with the notebook's full default dates
python forex/trade_regime_tester/_smoke_run_notebook.py --full

# Validate project hygiene
python tools/research_admin.py check --project forex/trade_regime_tester

# Full analysis is interactive after registering an experiment
jupyter lab forex/trade_regime_tester/trade_regime_tester.ipynb
```

## Acceptance gates

- Baseline tolerance: unconditional split metrics must reproduce the supplied
  completed-trades table exactly.
- Engine tests required: every notebook code cell passes the smoke runner;
  holdout assertions remain active; feature timestamps do not exceed decisions.
- Minimum validation suite: coverage/thin-cell audit, fixed train/test contrasts,
  circular-shift null, FDR control, cross-market dependence, persistence, and
  explicit interaction limits. Any promoted gate must return to the
  authoritative stateful portfolio engine for exact costs/accounting.
- Holdout protocol: default 2024-01-01 onward is sealed and excluded by parquet
  read predicates. Open once only after a single rule/configuration is frozen,
  using the exact notebook confirmation phrase.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
