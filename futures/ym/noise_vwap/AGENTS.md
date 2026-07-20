# YM Noise VWAP — agent operating notes

Port of `futures/nq/noise_vwap` (via the GC port) to YM (E-mini Dow). Read the
workspace `AGENTS.md`/`RULES.md` and this project's `PROJECT_GUIDE.md` and
`MEMORY.md`.

## Commands

```powershell
python -m futures.ym.noise_vwap.core.build_clean           # build ../data/YM_1m_clean.parquet
python -m futures.ym.noise_vwap.scripts.data_quality YM 90 # rule-9a gate
python -m futures.ym.noise_vwap.scripts.run_baseline YM 90 # faithful baseline
```

## Conventions

- `core/engine.py` and `core/metrics.py` are verbatim copies of the audited NQ
  engine. Keep them in parity; port fixes from NQ rather than diverging.
- Databento `YM.v.0` raw continuous 1m is the faithful data source.
- YM economics: tick 1.0 = $5, point = $5. Set in `core/data.py`.
- Register material runs in `experiments/ledger.csv`. Compare against the frozen
  baseline in `reports/BASELINE.md`; require a claim-matched Null C before any
  edge claim.
