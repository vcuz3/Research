# Bitcoin Noise Area VWAP Project Guide

## Objective and scope

- Research question: does the audited NQ Noise-Area + VWAP intraday-momentum
  logic transfer to Bitcoin when the anchor and evaluation window are explicit?
- Instruments/markets: Binance Spot BTCUSDT as a reference series. Short-side
  deployment requires a separate executable vehicle.
- Source: the local NQ replication at `../../futures/nq/noise_vwap/`.
- Data source and coverage: official Binance Spot one-minute archives in
  `../data/binance_spot_btcusdt_1m/`, 2017-08-17 through 2026-08-12.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` |
| Faithful replication | `baseline_replication/` |
| Execution/accounting | `backtest_engine/` |
| Features/signals/sizing | `strategy/` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

## Data and session conventions

- Timestamp source and timezone: UTC `open_time`, converted directly to
  `America/New_York`; all notebook clocks are ET and DST-aware.
- Trading calendar/session: configurable anchor and session length; default is
  weekday 09:30-15:59 ET to match the NQ decision universe.
- Instrument/roll convention: continuous Binance Spot BTCUSDT; no rolls.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: report gaps/off-grid bars; never fill; exclude sessions
  that lack the anchor/final bar, duplicate a slot, or miss the coverage floor;
  skip an order if its exact next-minute fill bar is absent.
- Data fingerprint: inspect
  `../data/binance_spot_btcusdt_1m/BTCUSDT-1m-data-quality.json`.

## Commands

```powershell
# Refresh/validate shared data when required
python crypto/data/download_binance_btcusdt_1m.py

# Execute the transparent baseline without optional notebook packages
python crypto/noise_vwap/backtest_engine/run_notebook.py

# Validate project structure
python tools/research_admin.py check --project crypto/noise_vwap
```

## Acceptance gates

- Baseline tolerance: zero same-bar fills, zero synthetic bars, exact-next-minute
  fill delay, and one-cell causal rolling parity within `1e-12`.
- Engine tests required: execute all notebook code cells and retain the printed
  invariant table.
- Minimum validation suite before an edge claim: gross versus net, always-long
  drift control, anchor/clock neighbours, valid path-preserving Null C, cost
  stress, weekday/weekend and era splits, and intended-venue execution replay.
- Holdout protocol: notebook OOS dates are a temporal split, not a sealed
  holdout. Only future observations after specification freeze are clean.

A material experiment is complete only when its ledger row contains the config,
data scope, code reference, command, primary metric, result, artifact path,
builder, reviewer, and review status.
