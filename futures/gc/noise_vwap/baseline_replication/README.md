# GC Baseline Replication

Faithful port of the NQ/ES Noise Area + VWAP momentum baseline to GC (COMEX Gold).

## What was ported

The strategy machinery is identical to `futures/nq/noise_vwap`. `core/engine.py`
and `core/metrics.py` are byte-for-byte copies of the audited NQ engine. Only two
things are instrument-specific:

1. `core/build_clean.py` reads the Databento `GC.v.0` raw 1-minute file.
2. `core/data.py` sets GC contract economics: tick 0.10, tick value $10, point
   value $100.

## Reproduce

```powershell
python -m futures.gc.noise_vwap.core.build_clean
python -m futures.gc.noise_vwap.scripts.run_baseline GC 90
```

## Result

See `../reports/BASELINE.md`. Summary: the method transfers with a positive but
materially weaker and more cost-fragile gross edge than NQ (gross Sharpe 0.77 vs
1.22, net t≈1.2–1.6 at realistic cost). Gold has no positive intraday long drift.
This is a replication only — no null, sizing, or validation has been run.

## Faithful config

`configs/faithful_config.json`.
