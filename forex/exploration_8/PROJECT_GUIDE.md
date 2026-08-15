# AUD triangular pricing exploration Project Guide

## Objective and scope

- Research question: do causal extremes in AUDUSD relative to AUDJPY/USDJPY predict a tradable reversion after realistic controls?
- Instruments/markets: AUDUSD, AUDJPY, USDJPY spot FX.
- Source paper: user-supplied idea; transcribed in `paper/PAPER_SPEC.md`.
- Data source and coverage: shared `forex/data` one-minute midpoint OHLC archives; exact coverage is emitted by the notebook for the selected window.

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

- Timestamp source and timezone: source timestamp normalized to UTC-naive pandas timestamps.
- Trading calendar/session: 24-hour spot-FX week; AUDUSD is the canonical observed calendar.
- Instrument/roll convention: spot FX, no roll.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: no fill; require complete constituent minutes and exact three-pair timestamp intersection.
- Data fingerprint command: add content hashes before any registered material experiment.

## Commands

```powershell
# Build the notebook
python _build_notebook.py
python _build_pine_translation_notebook.py

# Run deterministic feature/engine fixtures
python -m pytest test_triangle.py -q
python -m pytest test_pine_translation.py -q

# Validate project structure
python ..\..\tools\research_admin.py check --project .

# Run one registered experiment
python run_decay.py --config experiments/configs/exp_0001_decay.json --output-dir artifacts/runs/EXP-0001
```

## Acceptance gates

- Baseline tolerance: constructed identity fixture within 1e-12; timing/cost fixtures exact within floating tolerance.
- Engine tests required: `python -m pytest test_triangle.py test_pine_translation.py test_decay.py -q`.
- Minimum validation suite: raw/aligned data quality, two-bar embargo, three-leg cost stress, neighboring parameters, date-block circular re-pairing null, and frozen OOS.
- Holdout protocol: 2024 onward locked in the notebook until method and parameters are frozen; dates already inspected elsewhere in the workspace are not relabeled as pristine evidence.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
