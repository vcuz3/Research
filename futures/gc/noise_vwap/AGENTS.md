# GC Noise VWAP — agent operating notes

Port of `futures/nq/noise_vwap` to GC (COMEX Gold). Read the workspace
`AGENTS.md`/`RULES.md` and this project's `PROJECT_GUIDE.md` and `MEMORY.md`.

## Commands

```powershell
python -m futures.gc.noise_vwap.core.build_clean          # build data/GC_1m_clean.parquet
python -m futures.gc.noise_vwap.scripts.run_baseline GC 90 # faithful baseline
```

## Conventions

- `core/engine.py` and `core/metrics.py` are verbatim copies of the audited NQ
  engine. Keep them in parity; port fixes from NQ rather than diverging.
- Databento `GC.v.0` raw continuous 1m is the faithful data source.
- GC economics: tick 0.10 = $10, point = $100. Set in `core/data.py`.
- Register material runs in `experiments/ledger.csv`. Compare against the frozen
  baseline in `reports/BASELINE.md`; require a claim-matched Null C before any
  edge claim.
