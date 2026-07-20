# RTY Noise VWAP — agent operating notes

Port of `futures/nq/noise_vwap` (via the GC port) to RTY (E-mini Russell 2000).
Read the workspace `AGENTS.md`/`RULES.md` and this project's `PROJECT_GUIDE.md` and
`MEMORY.md`.

## Commands

```powershell
python -m futures.rty.noise_vwap.core.build_clean            # build ../data/RTY_1m_clean.parquet
python -m futures.rty.noise_vwap.scripts.data_quality RTY 90 # rule-9a gate
python -m futures.rty.noise_vwap.scripts.run_baseline RTY 90 # faithful baseline
```

## Conventions

- `core/engine.py` and `core/metrics.py` are verbatim copies of the audited NQ
  engine. Keep them in parity; port fixes from NQ rather than diverging.
- Databento `RTY.v.0` raw continuous 1m is the faithful data source (post-2017).
- RTY economics: tick 0.10 = $5, point = $50. Set in `core/data.py`.
- Register material runs in `experiments/ledger.csv`. Compare against the frozen
  baseline in `reports/BASELINE.md`; require a claim-matched Null C before any
  edge claim.
