# Opening Shock Continuation Project Guide

## Objective and scope

- Research question: does agreement between the overnight gap and the first
  cash-session half-hour isolate persistent price discovery that continues from
  10:00 to the 16:00 cash close?
- Instruments: full-size NQ primary, full-size ES sibling; one contract only.
- Literature baseline: Gao et al. (2018), DOI
  `10.1016/j.jfineco.2018.05.009`. This is a local futures rule transfer, not a
  reproduction of the paper's 1993-2013 SPY result.
- Data: local Databento raw-derived NQ/ES one-minute and one-second continuous
  OHLCV, through 2026-07-14 for the common analysis span.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` |
| Paper-rule futures transfer | `baseline_replication/` |
| Execution/accounting | `backtest_engine/` |
| Features/signals/sizing | `strategy/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- `ts_utc`/`ts_event` are timezone-aware UTC. ET dates and clocks are derived
  with `America/New_York`; never use a fixed UTC offset.
- A strict full RTH QA cohort has exactly 390 unique one-minute starts from
  09:30 through 15:59 ET, with no gaps longer than 60 seconds. It is not the
  primary sample selector.
- Primary eligibility is determined from the known exchange schedule and
  causal endpoints: the prior expected NYSE session's 15:59 endpoint, all 30
  opening minutes, the active entry record, and one unchanged instrument ID.
  Current/prior Databento condition must be `available`. A missing scheduled
  exit after an otherwise eligible entry fails the run instead of deleting the
  day.
- Signals use raw tradable prices. No adjusted price is used for PnL.
- The 09:59 bar is complete at 10:00:00. Primary entry order is active at
  10:00:01 and fills at the first subsequent one-second record plus slippage.
- Exit is scheduled at entry and active at 15:59:59; it is not based on the
  15:59 bar close.
- Flat eligible days remain explicit zeros in portfolio statistics.
- Fingerprints and the complete eligibility funnel are produced by the
  registered data-quality run.

## Commands

```powershell
python -m pytest -q futures/nq/opening_shock_continuation/tests
python -m futures.nq.opening_shock_continuation.scripts.data_quality --output-dir <registered-run-dir>
python -m futures.nq.opening_shock_continuation.scripts.run_baseline --output-dir <registered-run-dir>
python -m futures.nq.opening_shock_continuation.scripts.run_experiment --output-dir <registered-run-dir>
python -m futures.nq.opening_shock_continuation.scripts.run_validation --economic-result <registered-economic-result.json> --output-dir <registered-run-dir>
python -m futures.nq.opening_shock_continuation.scripts.run_power --economic-result <registered-economic-result.json> --validation-result <registered-validation-result.json> --output-dir <registered-run-dir>
```

## Acceptance gates

- Paper intake: distinguish the published SPY claim from the local futures
  transfer; do not claim published-value parity.
- Engine: all unit tests pass; one-second timestamps, same-contract identity,
  adverse fills, costs, no-trade zeros, and causal rolling features are audited.
- Innovation: enforce every HYP-0002 kill condition, 4,999-draw mechanism and
  family-search nulls, cost stress, era/year/side results, rate-matched controls,
  ES sibling, and delayed entry.
- Holdout: all historical observations are globally consumed. The 2019-2022
  and 2023-2026 splits are pseudo-OOS diagnostics; only future data can confirm.

A material experiment is complete only when its ledger row contains its frozen
config, data scope, command, metric, result, artifact path, builder, reviewer,
and review status.
