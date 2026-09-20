# Engine Audit

- Engine version/code reference: `futures.nq.noise_vwap.core.engine` via `backtest_engine/adapter.py`
- Test command: `python -m pytest futures/nq/percentile_rank_momentum/tests -q`
- Reviewer: unassigned

## Results

Eight project tests pass. The adapter's fixture proves a close decision at 10:00
fills at the 10:05 open and a flat decision at 10:10 exits at the 10:15 open.
Costs reconcile exactly to 0.2375 NQ point per side and 1.9 ticks round trip.

The inherited validation command also passes exact faithful parity:
`python -m futures.nq.noise_vwap.scripts.studies validate` returns 2,923 trades
and +4.945 gross points/trade on both `core.engine` and `engine2`.

## Exceptions and risks

- `bench_engine parity` fails before numerical comparison because the numba output
  lacks `hard_risk`, `mae`, and `mfe` columns present in pandas output. This is an
  inherited generalized-engine harness issue; EXP-0002 uses faithful `core.engine`.
- Inherited `test_vei.py` fails collection when invoked by filesystem path because
  its relative import has no package parent. The remaining combined suite passes
  76/76. Neither exception affects the experiment path.
- Independent review remains pending.

## Verdict

Passed for the faithful next-open path used by EXP-0002, with the two inherited
harness exceptions above.
