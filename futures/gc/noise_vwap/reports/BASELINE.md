# GC Noise Area + VWAP — Baseline Replication

Faithful port of the NQ/ES `noise_vwap` baseline to GC (COMEX Gold). Same
strategy machinery, same Concretum :59/:29 decision clock, same VWAP entry gate,
same next-open honest fills, same 90-session noise lookback. Only the data and
contract economics differ.

- Code: `core/build_clean.py`, `core/data.py`, `core/engine.py` (copied verbatim
  from the audited NQ engine), `core/metrics.py`, `scripts/run_baseline.py`.
- Data: Databento `GC.v.0` raw continuous 1-minute, 2011-08-01 → 2026-07-16,
  built to `data/GC_1m_clean.parquet`. 3844 RTH sessions, median 390 bars,
  0 sessions span a contract roll.
- Contract economics: 100 troy oz, tick 0.10 = $10, 1 point = $100.
- Reproduce: `python -m futures.gc.noise_vwap.scripts.run_baseline GC 90`

> **Revised 2026-07-19 (EXP-0005), data-quality fix.** The noise band originally
> used `rolling(90, min_periods=90)`, requiring all 90 prior sessions to have a
> bar at a given minute; a single missing minute nulled the band and the engine
> skips a band-less decision, silently deleting up to 28% of the 15:29 decisions
> on GC's thin afternoon (invisible on liquid NQ). Fixed to
> `min_periods = ceil(0.9 × 90) = 81` (`BAND_MIN_FRAC`, `core/data.py` +
> `core/session.py`). Numbers below are the **revised** baseline; the old figures
> are noted inline as *(was …)* and fully superseded. See `reports/DATA_QUALITY.md`
> and `artifacts/runs/EXP-0005/`. Verdict is unchanged (NO-GO).

## Per-trade / per-day baseline (before vol-target sizing, rule 12/21)

Honest fills (next-bar open), 1 contract, day-clustered inference. GC 3647 usable
sessions, **2692 trades** (1.43/day, *was 2641*), hit 0.34. NQ shown for a direct
comparison (reproduce: `python -m futures.nq.noise_vwap.scripts.run_baseline NQ 90`).

| Metric (0.50 tick/side) | GC (revised) | GC (was) | NQ |
| --- | ---: | ---: | ---: |
| gross pt/trade | +0.362 | +0.359 | +4.945 |
| net pt/trade | +0.217 | +0.214 | +4.470 |
| day $ net (1 contract) | +31.0 | +30.2 | +127.5 |
| day-net t-stat | +1.30 | +1.25 | +3.15 |
| net daily Sharpe | 0.48 | 0.46 | 1.10 |
| gross daily Sharpe | 0.79 | 0.77 | 1.22 |
| gross day-$ t-stat | +2.17 | +2.11 | +3.49 |

Cost sensitivity (net pt/trade → net Sharpe), revised GC:

| cost/side | GC net pt | GC Sharpe | NQ net pt | NQ Sharpe |
| --- | ---: | ---: | ---: | ---: |
| 0.25 tick | +0.267 | 0.58 | +4.595 | 1.14 |
| 0.50 tick | +0.217 | 0.48 | +4.470 | 1.10 |
| 1.00 tick | +0.117 | 0.26 | +4.220 | 1.04 |

Long/short split (net pt/trade, 0.50 tick): GC L +0.326 (1382) / S +0.102 (1310);
NQ L +4.210 / S +4.740. Both sides positive on GC at low cost; the short side goes
to ~0 by 1.0 tick. The recovered decisions (EXP-0005) are afternoon/short-heavy,
so the short leg improves (+0.088 → +0.102).

## Findings

1. **The method transfers to gold with a positive gross edge** (gross day-$
   t=+2.11, Sharpe 0.77), but it is **materially weaker than NQ** — roughly half
   the daily Sharpe and marginal net significance (net t≈1.2–1.6 at realistic
   cost).
2. **The edge is much more cost-fragile on gold.** Net/gross retention at 0.50
   tick/side is ~60% on GC versus ~90% on NQ; by 1.0 tick/side GC's net Sharpe
   falls to 0.24 and the short side turns negative. The gross-per-trade edge is
   small relative to the tick.
3. **Gold has no positive intraday long drift.** The naive always-long control is
   *negative* (−0.084 net pt, Sharpe −0.10), unlike equities where it is a
   positive tailwind. So the GC edge is not riding an underlying long drift — both
   the long and short legs are doing work — but it also does not inherit the
   equity-index intraday momentum tailwind.
4. **Fill feasibility:** 0 same-bar fills; every entry/exit fills at a later bar
   open by construction (rule A1/2).

## Status — validated, verdict NO-GO for deployment

Follow-on validation (`artifacts/runs/EXP-0001`, `EXP-0002`) is complete:

- **Null C (EXP-0001):** the timing signal is genuine-but-tiny — real day-$net
  beats its path-preserving return-shuffle noise (z=+2.26/p=0.065 at 0.25 tick,
  z=+2.66/p=0.048 at 0.50 tick; only ~15% machinery capture). Diffusivity gate
  passes (real=null=0.1000 pt = 1 gold tick). So it is NOT purely machinery.
- **Vol-target sizing (EXP-0001):** 3%-target / 8x-cap over 2011–2026 gives CAGR
  0.1%, Sharpe 0.07, maxDD −45.7%, no year-to-year persistence. The marginal
  per-bet edge does not compound into a tradable portfolio, and gold's ~$190k
  contract notional floors sizing to 1–2 contracts at $100k equity.
- **Session window (HYP-0001 / EXP-0002):** REJECTED — see below. The equity
  09:30–16:00 window is confirmed as the better of the two, not a defect.

Net: a real but economically inert intraday-momentum trace in gold. Keep as a
replication/paper result; **not deployment evidence.**

## Session hours — tested (HYP-0001 / EXP-0002): equity window wins

The NQ/ES replication uses the equity cash session 09:30–16:00 ET; gold's liquid
COMEX floor hours are 08:20–13:30 ET. HYP-0001 tested the gold-native window with
identical machinery re-anchored to its open. Result: **REJECTED, hypothesis
inverted.** COMEX hours are *worse* (net Sharpe 0.21 vs 0.46) and fail their own
Null C (z=+0.04, p=0.476, 96% machinery capture), whereas the real timing trace
survives Null C only in the equity window (z=+2.66, p=0.048). Gold's small edge is
tied to the equity cash session, not its own floor hours. Evidence:
`artifacts/runs/EXP-0002/review.md`. Do not sweep window times on consumed history.
