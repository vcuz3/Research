# GC Noise Area VWAP Project Guide

Model-neutral operating manual for the GC (COMEX Gold) port of the Noise Area +
VWAP intraday-momentum baseline. The parent project is `futures/nq/noise_vwap`;
this project reuses its audited engine and method verbatim and swaps only the
data and contract economics.

## Project map

| Concern | Location |
| --- | --- |
| Faithful baseline config | `baseline_replication/configs/faithful_config.json` |
| Baseline result | `reports/BASELINE.md` |
| Clean data build | `core/build_clean.py` → `data/GC_1m_clean.parquet` |
| Session, VWAP, noise bands | `core/data.py` |
| Execution / accounting | `core/engine.py`, `core/metrics.py` (copies of NQ) |
| Baseline runner | `scripts/run_baseline.py` |
| Run history | `experiments/ledger.csv` |
| Current state | `MEMORY.md` |
| New immutable outputs | `artifacts/runs/<experiment_id>/` |

## Contract economics

GC (COMEX Gold): 100 troy oz, tick 0.10 = $10, 1 point = $100. Set in
`core/data.py` (`TICK`, `TICK_VALUE`, `POINT_VALUE`).

## Core commands

```powershell
python -m futures.gc.noise_vwap.core.build_clean
python -m futures.gc.noise_vwap.scripts.run_baseline GC 90
```

## Data conventions

- Databento `GC.v.0` raw (unadjusted) continuous 1m is the faithful source.
  Raw, not back-adjusted: the strategy is built on intraday ratios (close/open−1),
  which additive adjustment distorts. No RTH session spans a roll (verified).
- Session = equity RTH 09:30–16:00 ET, inherited from NQ/ES for a like-for-like
  method replication. A gold-native session window is an open research question.
- All inspected history is consumed research data, not a sealed holdout.

## Definition of done

A material experiment is complete only when its ledger row has a frozen config or
documented exception, data scope, code reference, command, primary metric,
result, evidence path, and review status. A claimed improvement must beat the
frozen baseline in `reports/BASELINE.md` and survive a claim-matched Null C.
