# Project Memory: YM Noise Area VWAP

Concise handoff. Detailed evidence lives in the linked reports and code. This
project is a port of `futures/nq/noise_vwap` (via the GC port) to YM (E-mini Dow).

## Scope

- Objective: replicate the NQ/ES Noise-Area + VWAP intraday-momentum baseline on
  YM, then decide whether a robust, cost-surviving edge exists.
- Instrument: YM (E-mini Dow, CBOT). $5 × index, tick 1.0 pt = $5, point = $5.
- Data: Databento `YM.v.0` raw continuous 1m, 2010-06-07 → 2026-07-17
  (`futures/ym/data/YM_1m_clean.parquet`; 4015 RTH sessions, 0 span a roll).
- Current phase: **baseline replicated; verdict NO-GO for deployment.**

## Current status

- Verdict: **replication PASS, deployment NO-GO.** The method transfers with a
  positive gross edge but it is weak and cost-fragile (gross Sharpe 0.51, net
  Sharpe 0.21 @0.50 tick, net t=0.64 — never clears 1). YM's $5 tick eats a large
  fraction of the per-trade move.
- Baseline (0.50 tick, 1 contract, per-day clustered, before sizing): gross
  +3.244 pt/trade, net +1.344, day$net +9.8, net t=+0.64, net Sharpe 0.21; gross
  Sharpe 0.51 (t=1.55). 3337 trades over 4015 sessions. Fills honest (0 same-bar).
- Both legs positive gross; naive always-long drift ~flat (Sharpe 0.01) → the edge
  is timing, not Dow intraday drift.
- Reproduce: `python -m futures.ym.noise_vwap.scripts.run_baseline YM 90`.
- Evidence: `reports/BASELINE.md`, `reports/BASELINE.txt`.
- **Data-quality gate (rule 9a):** `python -m futures.ym.noise_vwap.scripts.data_quality YM 90`;
  `reports/DATA_QUALITY.txt`. Timeline clean; relaxed `BAND_MIN_FRAC=0.9` gives
  uniform ~98% decision-minute band coverage (strict all-90 would drop up to 8% at
  12:59 = 492 points). Precautionary here — YM is liquid, no time-of-day skew.

## Machinery / parity

- `core/engine.py`, `core/metrics.py`, `core/nulls.py`, `core/nulls_session.py`,
  `core/session.py`, `core/engine2.py`, `core/engine2_nb.py` are **verbatim copies
  of the audited NQ/GC code**. Only `core/data.py` (paths + economics) and
  `core/build_clean.py` (source path + OUT) are instrument-specific. Keep in parity
  — port fixes from NQ rather than diverging.
- Fast path (`engine2_nb`, numba) imported OK but its **bit-exact parity vs
  `core.engine` has NOT been re-verified on YM** (only the pandas engine runs the
  baseline). Verify parity before using the grid/fast path here.

## Not yet done (edge is already weak/NO-GO)

- No Null-C, sizing, or era-stability study run — gross is only marginally positive
  and net t<1, so the deployment case is already weak (gate: don't spend Null-C
  unless the real pass clears the primary metric).
- Cross-market comparison: YM sits between NQ (strong) and RTY (negative) —
  strongest un-consumed direction is a portfolio-leg study (NQ+ES+GC+YM book), not
  YM standalone tuning.
- All historical data here is now consumed research data, not a sealed holdout.
