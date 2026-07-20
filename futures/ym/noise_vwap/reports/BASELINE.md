# YM Noise-Area + VWAP — Baseline Replication

Faithful port of the audited NQ/ES/GC `noise_vwap` baseline to **YM (E-mini Dow,
CBOT)**. Only the data path and contract economics differ; `core/engine.py`,
`core/metrics.py`, `core/nulls.py`, `core/session.py`, `core/engine2*.py` are
verbatim copies of the audited NQ code (kept in parity per project convention).

Reproduce:

```
python -m futures.ym.noise_vwap.core.build_clean          # build YM_1m_clean.parquet
python -m futures.ym.noise_vwap.scripts.data_quality YM 90 # rule-9a gate
python -m futures.ym.noise_vwap.scripts.run_baseline YM 90 # baseline
```

Raw captured output: `reports/BASELINE.txt`, `reports/DATA_QUALITY.txt`.

## Contract economics

- E-mini Dow (YM): **$5 × index**, min tick **1.0 index point = $5**, 1 point = $5.
- Fees modeled at $2.25/side (= 0.45 pt). Slippage grid in ticks (1 tick = 1.0 pt).

## Data

- Databento RAW continuous `YM.v.0` 1-min, built to `futures/ym/data/YM_1m_clean.parquet`.
- Timeline **clean**: 0 duplicate minutes, 0 out-of-order bars, 0 sessions span a roll.
- RTH sessions (09:30–16:00 ET, ≥350 bars): **4015**, 2010-06-07 → 2026-07-17.
- Completeness: median 390/390 RTH minutes; only 1.3% of sessions miss ≥1 minute.
- Rule-9a band coverage: relaxed `BAND_MIN_FRAC=0.9` (ported from GC) holds uniform
  ~98% across all 13 decision minutes; the strict all-90 rule would have silently
  dropped up to 8% at 12:59 (492 decision points total). No time-of-day skew on YM
  (liquid); the fix is precautionary here.

## Baseline result (1 contract, per-day clustered, before sizing)

| cost      | gross pt | net pt | hit  | day$net | net t | net Sharpe |
|-----------|---------:|-------:|-----:|--------:|------:|-----------:|
| gross     | +3.244   | +3.244 | .343 | +23.7   | +1.55 | 0.51       |
| 0.25 tick | +3.244   | +1.844 | .338 | +13.5   | +0.88 | 0.29       |
| 0.50 tick | +3.244   | +1.344 | .338 | +9.8    | +0.64 | 0.21       |
| 1.0 tick  | +3.244   | +0.344 | .329 | +2.5    | +0.16 | 0.05       |

- 3337 trades (1.46/day); fills honest — **0 same-bar fills** (all at a later bar open).
- Both legs positive gross: long +3.59 pt (1709), short +2.88 pt (1628).
- Naive always-long drift control is ~flat (net +0.089 pt, Sharpe 0.01): the edge is
  the timing signal, not intraday Dow drift.

## Verdict

The method **transfers to YM with a positive gross edge but is weak and
cost-fragile** — the same profile as GC, materially weaker than NQ. YM's $5 tick is
a large fraction of the per-trade move, so net degrades fast: net Sharpe 0.21 at
0.50 tick, ~0 by 1.0 tick, net t never clears 1. This is a **replication PASS but a
NO-GO for deployment** on the standalone per-trade edge (no Null-C or sizing study
run yet — gross is only marginally positive so the deployment case is already
weak). Treat as a paper/replication baseline; any further work must use the audited
engine and compare against this frozen baseline.
