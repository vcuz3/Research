# Project Memory: RTY Noise Area VWAP

Concise handoff. Detailed evidence lives in the linked reports and code. This
project is a port of `futures/nq/noise_vwap` (via the GC port) to RTY (E-mini
Russell 2000).

## Scope

- Objective: replicate the NQ/ES Noise-Area + VWAP intraday-momentum baseline on
  RTY, then decide whether a robust, cost-surviving edge exists.
- Instrument: RTY (E-mini Russell 2000, CME). $50 × index, tick 0.10 pt = $5,
  point = $50.
- Data: Databento `RTY.v.0` raw continuous 1m, **2017-07-14** → 2026-07-17
  (`futures/rty/data/RTY_1m_clean.parquet`; 2242 RTH sessions, 0 span a roll).
  Sample is shorter than NQ/ES/YM — RTY migrated to CME in July 2017.
- Current phase: **baseline replicated; verdict NO-GO.**

## Current status

- Verdict: **replication PASS, but a clear NO-GO — the method does NOT transfer to
  RTY.** There is **no positive gross edge**: gross −0.253 pt/trade (Sharpe −0.44,
  t=−1.00) BEFORE any cost, net worsens monotonically with cost (net Sharpe −0.76
  @0.50 tick, −0.94 @1.0 tick).
- Naive always-long drift is also **negative** (net −0.566 pt, Sharpe −0.45): RTY
  small-caps had no positive intraday drift over 2017–2026, so there is no
  favorable backdrop for a breakout-momentum system to ride.
- 1980 trades over 2242 sessions; both legs negative gross. Fills honest (0 same-bar).
- Reproduce: `python -m futures.rty.noise_vwap.scripts.run_baseline RTY 90`.
- Evidence: `reports/BASELINE.md`, `reports/BASELINE.txt`.
- **Data-quality gate (rule 9a):** `python -m futures.rty.noise_vwap.scripts.data_quality RTY 90`;
  `reports/DATA_QUALITY.txt`. Timeline clean; relaxed `BAND_MIN_FRAC=0.9` gives
  uniform ~96% decision-minute band coverage (strict all-90 would drop a uniform
  ~8–10% = 1370 points, NOT time-of-day-skewed — consistent with the shorter
  post-2017 window under-filling the trailing-90 requirement).

## Machinery / parity

- `core/engine.py`, `core/metrics.py`, `core/nulls.py`, `core/nulls_session.py`,
  `core/session.py`, `core/engine2.py`, `core/engine2_nb.py` are **verbatim copies
  of the audited NQ/GC code**. Only `core/data.py` (paths + economics) and
  `core/build_clean.py` (source path + OUT) are instrument-specific. Keep in parity.
- Fast path (`engine2_nb`) imported OK but **bit-exact parity vs `core.engine` NOT
  re-verified on RTY** — verify before using the grid/fast path.

## Not yet done

- Nothing to size or null-test: the real pass fails the primary metric at the GROSS
  level, which is already a REJECT. Preserve as negative evidence (rule 25).
- Caveat: result is for the post-2017, small-cap-specific window only. If ever
  re-opened, the only clean new evidence is future/out-of-sample data (rule 26).
- All historical data here is now consumed research data, not a sealed holdout.
