# Low-volatility false-breakout reversion Project Guide

## Objective and scope

- Question: do range breakouts during unusually low ATR regimes revert?
- Markets: EURUSD, GBPUSD, AUDUSD, NZDUSD.
- Source: user-supplied rules dated 2026-09-19; no external paper.
- Data: `../data/clean/{asset}_1m_clean.parquet`, midpoint 1-minute OHLC,
  2011-07-19 to 2026-07-17 (NZDUSD begins 2011-12-06).

## Project map

| Concern | Location |
| --- | --- |
| Frozen rules | `paper/PAPER_SPEC.md` |
| Baseline config | `baseline_replication/configs/baseline.json` |
| Execution/accounting | `backtest_engine/engine.py` |
| Features/signals | `strategy/signals.py` |
| Registered runs | `experiments/ledger.csv`, `artifacts/runs/` |
| Current findings | `reports/FINDINGS.md` |

## Data and session conventions

- Naive source timestamps are interpreted as UTC minute starts.
- Spot FX uses the archive's available continuous-week calendar; no synthetic
  missing bars are created.
- Decision bars are left-labelled, left-closed fixed-minute UTC buckets.
- Incomplete decision bars are reported and dropped. Rolling windows operate on
  the compact series of complete tradable bars.
- There are no futures rolls or corporate-action adjustments.
- SHA-256 fingerprints and coverage diagnostics are saved per run.

## Commands

```powershell
python -m pytest -q
python run_backtest.py --config baseline_replication/configs/baseline.json --output artifacts/runs/EXP-0001
python run_walk_forward.py --config experiments/configs/walk_forward_grid.json --output artifacts/runs/EXP-0002
python ..\..\tools\research_admin.py check --project .
```

## Acceptance gates

- Engine: all deterministic tests pass.
- Hypothesis: pooled gross mean R > 0, clustered 95% CI excludes zero, and at
  least 3/4 pairs have positive gross mean R.
- Confirmation: path-preserving null, same-slot/matched-rate clock control,
  neighbouring parameters, measured spread, and independent review.
- Holdout: timestamps from 2024-07-18 onward are reserved from optimisation and
  remain untested by EXP-0002. EXP-0001 already inspected them, so only future
  data is a clean thesis-level holdout.
