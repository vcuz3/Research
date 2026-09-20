# NQ Globex to RTH Open Project Guide

## Objective and scope

- Research question: what has been the gross and cost-adjusted performance of a
  long NQ position from 18:00 to 09:30 New York time, and how do causal MA/VIX
  gates and four sizing rules change that performance?
- Instrument: NQ continuous front contract, one position at a time.
- Source specification: `paper/PAPER_SPEC.md`.
- Data: common NQ minute and daily VIX sources; data is referenced, not copied.

## Project map

| Concern | Location |
| --- | --- |
| Frozen strategy contract | `paper/` |
| Baseline config | `baseline_replication/configs/baseline.json` |
| Execution/accounting | `backtest_engine/engine.py` |
| Features and joins | `strategy/features.py` |
| Study CLI/config | `scripts/run_study.py`, `experiments/configs/` |
| Immutable outputs | `artifacts/runs/` |
| Tests | `tests/test_study.py` |
| Current reports | `reports/` |

## Data and session conventions

- Source timestamps are UTC-aware; decision clocks are converted with the IANA
  `America/New_York` timezone, so DST is not hard-coded.
- Entry/exit fills require the exact 18:00 and 09:30 bar opens.
- Daily NQ features use completed 09:30-15:59 RTH data available before entry.
- VIX is a bounded backward date join with a maximum age of four calendar days.
- Unadjusted prices and contract IDs protect overnight P&L from synthetic rolls.
- Source fingerprints are written into every run manifest.

## Commands

```powershell
python -m pytest futures\nq\globex_to_rth_open\tests -q -p no:cacheprovider
python futures\nq\globex_to_rth_open\scripts\run_study.py
python futures\nq\globex_to_rth_open\scripts\run_vol_target_figure.py
python futures\nq\globex_to_rth_open\scripts\run_lse_sma200_figure.py
python tools\research_admin.py check --project futures\nq\globex_to_rth_open
```

## Acceptance gates

- Execution: exact anchors, 15.5-hour holding time, same contract, no roll inside.
- Causality: every feature/VIX date is no later than entry date; sizing reference
  is shifted before rolling.
- Accounting: hand fixture exactly reconciles gross, $15 cost, and net.
- Data quality: source, RTH, VIX, anchor, window, staleness, and minute-of-day
  coverage reports are material outputs.
- Interpretation: the entire history and parameter sweep are discovery data.
  No best row is confirmatory; a survivor needs selection-aware validation and
  a future shadow period.
