# Backtest Engine Boundary

The reusable engine remains under `../core/` to preserve imports:

- `engine.py`: paper-faithful reference execution.
- `engine2.py` and `engine2_nb.py`: generalized/optimized implementations.
- `metrics.py`: metric definitions and units.
- `nulls.py`: session-valid null construction.
- `session.py`, `data.py`, `build_clean.py`: data/session contracts.

Strategy and experiment scripts may supply signals and configuration but must not
reimplement fills, costs, accounting, sizing, or metrics. New engine behaviour
requires a fixture or test, faithful parity where applicable, and an engine-phase
ledger row.

Validation commands:

```powershell
python -m futures.nq.noise_vwap.scripts.studies validate
python -m futures.nq.noise_vwap.scripts.bench_engine parity
```
