# YM Noise Area VWAP Project Guide

Model-neutral operating manual for the YM (E-mini Dow) port of the Noise Area +
VWAP intraday-momentum baseline. The parent project is `futures/nq/noise_vwap`
(and the GC port `futures/gc/noise_vwap`); this project reuses the audited engine
and method verbatim and swaps only the data and contract economics.

## Project map

| Concern | Location |
| --- | --- |
| Baseline result | `reports/BASELINE.md` (+ raw `reports/BASELINE.txt`) |
| Data-quality gate (rule 9a) | `scripts/data_quality.py` → `reports/DATA_QUALITY.txt` |
| Clean data build | `core/build_clean.py` → `../data/YM_1m_clean.parquet` |
| Session, VWAP, noise bands | `core/data.py` |
| Execution / accounting | `core/engine.py`, `core/metrics.py` (copies of NQ) |
| Grid/fast path | `core/session.py`, `core/engine2.py`, `core/engine2_nb.py` (copies) |
| Baseline runner | `scripts/run_baseline.py` |
| Run history | `experiments/ledger.csv` |
| Current state | `MEMORY.md` |

## Contract economics

E-mini Dow (YM, CBOT): $5 × index, tick 1.0 pt = $5, 1 point = $5. Set in
`core/data.py` and `core/session.py` (`TICK`, `TICK_VALUE`, `POINT_VALUE`).

## Core commands

```powershell
python -m futures.ym.noise_vwap.core.build_clean
python -m futures.ym.noise_vwap.scripts.data_quality YM 90
python -m futures.ym.noise_vwap.scripts.run_baseline YM 90
```

## Data conventions

- Databento `YM.v.0` raw (unadjusted) continuous 1m is the faithful source. Raw,
  not back-adjusted: the strategy is built on intraday ratios (close/open−1), which
  additive adjustment distorts. No RTH session spans a roll (verified).
- Session = equity RTH 09:30–16:00 ET, YM's native cash session.
- All inspected history is consumed research data, not a sealed holdout.

## Definition of done

A material experiment is complete only when its ledger row has a frozen config or
documented exception, data scope, code reference, command, primary metric, result,
evidence path, and review status. A claimed improvement must beat the frozen
baseline in `reports/BASELINE.md` and survive a claim-matched Null C.
