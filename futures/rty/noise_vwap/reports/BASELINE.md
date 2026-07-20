# RTY Noise-Area + VWAP — Baseline Replication

Faithful port of the audited NQ/ES/GC `noise_vwap` baseline to **RTY (E-mini
Russell 2000, CME)**. Only the data path and contract economics differ;
`core/engine.py`, `core/metrics.py`, `core/nulls.py`, `core/session.py`,
`core/engine2*.py` are verbatim copies of the audited NQ code (kept in parity).

Reproduce:

```
python -m futures.rty.noise_vwap.core.build_clean            # build RTY_1m_clean.parquet
python -m futures.rty.noise_vwap.scripts.data_quality RTY 90 # rule-9a gate
python -m futures.rty.noise_vwap.scripts.run_baseline RTY 90 # baseline
```

Raw captured output: `reports/BASELINE.txt`, `reports/DATA_QUALITY.txt`.

## Contract economics

- E-mini Russell 2000 (RTY): **$50 × index**, min tick **0.10 index point = $5**,
  1 point = $50.
- Fees modeled at $2.25/side (= 0.045 pt). Slippage grid in ticks (1 tick = 0.10 pt).

## Data

- Databento RAW continuous `RTY.v.0` 1-min, built to `futures/rty/data/RTY_1m_clean.parquet`.
- **Sample begins 2017-07-14** — RTY migrated to CME in July 2017, so history is
  shorter than NQ/ES/YM (~9 years vs ~16).
- Timeline **clean**: 0 duplicate minutes, 0 out-of-order bars, 0 sessions span a roll.
- RTH sessions (09:30–16:00 ET, ≥350 bars): **2242**, 2017-07-14 → 2026-07-17.
- Completeness: median 390/390 RTH minutes; only 1.7% of sessions miss ≥1 minute.
- Rule-9a band coverage: relaxed `BAND_MIN_FRAC=0.9` holds uniform ~96% across all
  13 decision minutes; strict all-90 would drop a uniform ~8–10% (1370 decision
  points). The drop is **uniform across time-of-day** (not skewed to thin late
  hours as on GC), consistent with RTY's shorter window occasionally under-filling
  the trailing-90 requirement rather than a liquidity-hole pattern.

## Baseline result (1 contract, per-day clustered, before sizing)

| cost      | gross pt | net pt | hit  | day$net | net t | net Sharpe |
|-----------|---------:|-------:|-----:|--------:|------:|-----------:|
| gross     | −0.253   | −0.253 | .339 | −18.9   | −1.00 | −0.44      |
| 0.25 tick | −0.253   | −0.393 | .335 | −29.4   | −1.55 | −0.68      |
| 0.50 tick | −0.253   | −0.443 | .335 | −33.2   | −1.75 | −0.76      |
| 1.0 tick  | −0.253   | −0.543 | .330 | −40.7   | −2.14 | −0.94      |

- 1980 trades (1.50/day); fills honest — **0 same-bar fills**.
- Both legs negative gross: long −0.47 pt (964), short −0.05 pt (1016).
- Naive always-long drift control is also **negative** (net −0.566 pt, Sharpe −0.45):
  RTY small-caps had no positive intraday drift over 2017–2026.

## Verdict

**The method does NOT transfer to RTY.** Unlike NQ/ES/YM/GC, RTY has **no positive
gross edge at all** — gross is negative (Sharpe −0.44, t=−1.00) before any cost, and
net worsens monotonically with cost. The always-long drift is also negative, so
there is no favorable intraday backdrop for a breakout-momentum system to ride over
this sample. This is a **replication PASS (the pipeline is faithful and honest) but
a clear NO-GO** — there is nothing to size or null-test; the real pass fails the
primary metric at the gross level. Preserve as negative evidence. Caveat: the sample
is post-2017 only and small-cap-specific; the negative result is for THIS window.
