# Noise Area + VWAP intraday momentum (Zarattini / Quantitativo) — NQ & ES

> **UPDATE (forensic review, see FORENSIC.md).** The hygiene numbers below were computed
> on a config with a **decision-clock off-by-one bug** (decided at `:00/:30` instead of the
> published `:59/:29`) and **no VWAP entry gate**. The corrected *faithful* config is
> materially stronger — NQ **28.1% / Sharpe 1.31 / −28%**, ES **17.2% / 0.87 / −30%**,
> portfolio **24.2% / 1.54 / −19%** (vs published 22.4%/1.57/−15%) — and CAGR + portfolio
> Sharpe reconcile with the paper. The structural caveats (≈42% drift under Null-C,
> regime-dependence, weak 2025) still hold and were confirmed on the faithful config's
> sample-period curve. A Null-C re-run on the faithful config is the outstanding follow-up.

**Verdict: QUALIFIED / PAPER-ONLY.** A *real but regime-dependent* intraday-momentum
edge on NQ. It is the first candidate in this workbench to survive both the
fill-feasibility gauntlet **and** Null-C — the fill convention is irrelevant here
(not a fill artifact, unlike every prior NQ corpse). But ~42% of its P&L is pure
drift capture, the timing edge lives almost entirely in high-volatility trending
years, and it is **absent in 2024 and negative in 2025** — the two most recent years.
ES does **not** replicate honestly. Do not give it capital; paper/watchlist with a
vol/trend regime filter.

## What was built
- `core/build_clean.py` — rebuilt `data/{NQ,ES}_1m_clean.parquet` from the source
  xlsx in `futures/{nq,es}/data/` (the old magic_hour parquets had gaps). Dedupes
  overlapping file boundaries, derives roll flags, validates. **Coverage is now
  essentially gap-free**: NQ 467 missing RTH minutes across 3,858 sessions (median
  390/session), ES 304; 0 duplicate minutes; timezone confirmed CT via the RTH
  volume profile. ES now spans **2011–2026** (old parquet started 2014).
- `core/data.py` — RTH placement, cumulative session VWAP, same-time-of-day Noise
  Area bands (strictly-prior lookback, no lookahead / no session-total feature).
- `core/engine.py` — trend-following engine, **honest next-bar-open fills**, exits
  on the semi-hourly clock, flat at RTH close. `fill_mode="signal_close"` provided
  only to measure the fill artifact.
- `core/nulls.py` — single-instrument path-preserving return shuffle (Null C),
  diffusivity-gated.
- `core/metrics.py` — per-trade equal-weighted effect size, per-day summed P&L,
  day-clustered t (rules 12/13/22).

## Honest replication vs the Quantitativo headline
Next-open fills, full calendar, vol-target 3% / 8x cap, 14-day vol lookback.

| | Quantitativo | Honest (0.25-tick) | Honest (0.50-tick) |
|---|---|---|---|
| NQ CAGR | 24.3% | 21.6% | 19.6% |
| NQ Sharpe | 1.67 | **1.08** | **1.00** |
| NQ maxDD | −24% | −27% | −32% |
| ES CAGR | 16.8% | — | 3.3% |
| ES Sharpe | 1.25 | — | **0.27** |
| ES maxDD | −21% | — | −50% |

NQ lands in the same CAGR ballpark but at Sharpe ~1.0, not 1.67 (and deeper DD).
The 1.0→1.67 gap is **not** a fill artifact (see below) — it is methodology/parameters
(continuous vs semi-hourly stop monitoring, cost model, contract rounding). **ES does
not replicate at all** under honest fills + realistic cost.

## Hygiene gauntlet

**A. Fill feasibility (rule 1/2) — PASS, and this is the headline finding.**
All fills are the next 1-min bar open; 0 same-bar fills. Crucially, re-running with
the aggressive same-bar-close fill changes per-trade net from +4.144 → +4.166 pt and
leaves Sharpe at 1.08. On this slow semi-hourly clock the close→next-open gap is one
tick (0.25 pt) against a +4.5 pt edge, so **the edge does not come from the fill** —
the exact failure mode that killed the magic-hour and VWAP-breakout studies is absent.

**B. Null C (rule 17) — PASS (partial).** Diffusivity gate holds (real 0.2500 =
null 0.2500). Real day-$net +117.6 vs null mean +49.6 (std 22.9, n=50) →
**real beats the drift/machinery null by z = +2.97**; the null captures **42.2%** of
the P&L. So ~58% is genuine intraday-continuation timing; ~42% is drift the strategy
would harvest just by being long/vol-targeted (Null C preserves each session's net move).

**C. Naive always-long drift control — PASS.** Buying at the first decision and
holding to close nets +0.82 pt, t=0.43, Sharpe 0.11 — flat. The strategy (+4.14 pt,
t=3.09) beats it decisively, so the edge is not the 10:00→close drift.

**D. Two-sided — PASS in aggregate, UNSTABLE yearly.** Aggregate short side (+4.65 pt)
> long (+3.65 pt). But yearly the sides flip contribution (2024 L −0.19/S +15.6;
2025 L −10.6/S +3.4) — "whichever way the big trend ran," not a stable two-sided signal.

**E. Sibling market (ES, rule 18) — WEAK.** Same sign, much weaker, cost-fragile:
net +0.54 pt (t=1.81) at 0.25-tick, washing to +0.17 (t=0.55) at 1.0-tick. Consistent
with the article's ES<NQ ranking, but ES clears neither t=2 nor an honest Sharpe.

## The killer: era stability & recent decay (rules 19/22)
Per-year real vs Null-C excess-over-drift (z):

- **Timing edge present (z>2):** 2012 (3.9), 2013 (3.8), 2018 (2.4), 2020 (3.1), 2022 (3.0)
  — the early recovery plus the high-vol/high-trend years.
- **No timing edge (real ≈ drift):** 2014, 2015, 2017, 2019, 2023, **2024 (z=0.2)**.
- **Timing hurts:** 2016, **2025 (excess −154/day)**.

The aggregate z=3 is carried by five trending years. In calm years the strategy is
pure drift; **in the two most recent full years the timing component vanished (2024)
then went negative (2025)**. This is a long-trend/vol harvester whose alpha is
non-stationary and currently dormant. Only 3–5 of 16 years reach |t|≥2 standalone.

## Bottom line
Not a NO-GO and not a clean edge. Honestly: a genuine, fill-robust, Null-C-surviving
intraday-momentum signal on NQ that is **regime-dependent (long trend/vol), ~half drift,
and decaying (dead in 2024–25)**; ES does not hold up. Per rule 26, paper/watchlist —
capital only after (a) a vol/trend regime filter that gates out the dead calm-year
regime, (b) an explanation for the 2024–25 decay, and (c) forward shadow confirmation.

## Reproduce
```
python -m futures.nq.noise_vwap.core.build_clean            # rebuild clean parquets
python -m futures.nq.noise_vwap.scripts.run_baseline NQ 90
python -m futures.nq.noise_vwap.scripts.run_nulls    NQ 90 50
python -m futures.nq.noise_vwap.scripts.run_eras     NQ 90
python -m futures.nq.noise_vwap.scripts.run_year_vs_null NQ 90 15
python -m futures.nq.noise_vwap.scripts.run_fillcompare  NQ 90
python -m futures.nq.noise_vwap.scripts.run_portfolio NQ 90 0.03 8
```
