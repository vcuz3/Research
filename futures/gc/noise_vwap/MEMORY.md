# Project Memory: GC Noise Area VWAP

Concise handoff. Detailed evidence lives in the linked reports, code, and run
artifacts. This project is a port of `futures/nq/noise_vwap` to GC (COMEX Gold).

## Scope

- Objective: replicate the NQ/ES Noise Area + VWAP intraday-momentum baseline on
  GC, then decide whether a robust, cost-surviving gold edge exists.
- Instrument: GC (COMEX Gold) futures. 100 oz, tick 0.10 = $10, point = $100.
- Data: Databento `GC.v.0` raw continuous 1m, 2011-08-01 → 2026-07-16 (built to
  `data/GC_1m_clean.parquet`; 3844 RTH sessions, 0 span a roll).
- Current phase: baseline validated; verdict is NO-GO for deployment.

## Current status

- Verdict: **NO-GO for deployment.** The method replicates and the per-trade
  timing signal is genuine-but-tiny (beats Null-C), but it is economically inert
  (vol-target Sharpe 0.07) and cost-fragile. Keep as a paper/replication result.
- Last verified: 2026-07-19 from EXP-0000 (baseline), EXP-0001 (Null-C + sizing),
  EXP-0002 (HYP-0001 COMEX hours), EXP-0003 (HYP-0002 anchor×k×lookback grid).
- The strategy machinery (`core/engine.py`, `core/metrics.py`, `core/nulls.py`) is
  a verbatim copy of the audited NQ code; only data path and contract economics
  differ. **Fast path (EXP-0003):** `core/engine2.py` + `core/engine2_nb.py`
  (numba) + `core/session.py` ported from NQ — bit-exact vs `core.engine` (2641
  trades, gross +0.3586 pt), ~13x faster (0.39s vs 5.1s/config). `core/session.py`
  adds the `load_rth_both` dual-anchor loader (rth/eth VWAP) + k-scalable bands;
  `core/nulls_session.py` is the sdate/mfo return-shuffle rebuilding both anchors'
  VWAP (diffusivity real=null=0.1000 pt).
- Baseline (0.50 tick/side, 1 contract, per-day clustered, before sizing): gross
  +0.359 pt/trade, net +0.214, day$ net +30.2, net t=+1.25, net Sharpe 0.46;
  gross Sharpe 0.77. 2641 trades over 3647 sessions.
- Reproduce: `python -m futures.gc.noise_vwap.scripts.run_baseline GC 90`.
- Evidence: `reports/BASELINE.md`, `artifacts/runs/EXP-0001/`, `.../EXP-0002/`.

## Confirmed findings

- The method transfers to gold with a positive gross edge but is **materially
  weaker than NQ** (gross Sharpe 0.77 vs 1.22) and **much more cost-fragile**
  (net/gross ~60% at 0.50 tick vs ~90% on NQ; net Sharpe 0.24 by 1.0 tick).
- Gold has **no positive intraday long drift** (always-long control net −0.084
  pt, Sharpe −0.10), unlike equities. Both long and short legs contribute.
- **Null-C (EXP-0001):** the timing signal is genuine-but-tiny — real day-$net
  beats its path-preserving noise (z=+2.26, p=0.065 at 0.25 tick / z=+2.66,
  p=0.048 at 0.50 tick; only 15% machinery capture). Diffusivity gate passes
  (real=null=0.1000 pt = 1 gold tick). NOT purely machinery, unlike several NQ
  exit-study rejects.
- **Vol-target sizing (EXP-0001) kills tradability:** 3%/8x sizing over 2011-2026
  gives CAGR 0.1%, Sharpe 0.07, maxDD −45.7%, no year persistence. The marginal
  per-bet edge does not compound; gold's ~$190k notional floors sizing to 1-2
  contracts at $100k equity. The per-trade Sharpe 0.46 badly overstates the sized
  0.07.
- **HYP-0001 REJECTED / inverted (EXP-0002):** gold-native COMEX pit hours
  (08:20-13:30 ET) are *worse* than the equity window (net Sharpe 0.21 vs 0.46)
  AND fail their own Null-C (z=+0.04, p=0.476, 96% capture). The real timing trace
  lives only in the equity 09:30-16:00 window — the gold edge is tied to the
  equity cash session, not gold's floor hours. Do NOT sweep window times on
  consumed history.
- **HYP-0002 REJECTED (EXP-0003):** a 50-cell grid — VWAP anchor {rth, eth} × band
  vol-mult k {0.5,1.0,1.25,1.5,2.0} × noise lookback {5,14,30,60,90}, decision-clock
  exits, scored era-neutrally (daily Sharpe on net return = net_pt/price) with
  expanding WFO + a consumed 2023-26 holdout — finds NO config that beats the frozen
  baseline out-of-sample. In-sample best-of-50 = Sharpe 0.487 (t=1.83, n.s.,
  uncorrected); short lookbacks (5-14) win in-sample. WFO-selected stream is
  NEGATIVE (Sharpe -0.45) and WORSE than the static baseline (-0.15); the untuned
  baseline BEATS the best-IS cell on the holdout (0.841 vs 0.686). The **ETH
  (Globex 18:00-anchored) VWAP is INERT** — rth/eth cells interleave the whole
  ranking; the VWAP anchor is not a lever. Era-unstable: 2013-2023 net-negative, the
  positive full-sample number is carried by the 2011-13 and 2023-26 endpoints.
  Verdict rests on the OOS failure alone (complete evidence). The max-stat Null-C was
  STOPPED at 76/200 draws (the failing real pass is already a REJECT — do not run
  Null-C unless the real pass is positive AND the user confirms). Partial null
  (directional only): real best-of-50 0.487 vs null best-of-50 mean 0.520, z=−0.26,
  62% of noise draws beat it. Do NOT tune band-k/lookback/anchor on consumed history.
  Exit spec confirmed: stop = max(band,vwap) long / min(band,vwap) short, checked on
  the 30-min decision clock (NOT continuous; continuous = `exit_check=every_bar`).

## Not yet done (optional; edge is already NO-GO)

1. Era stability (2011–2026), cost stress, neighbouring lookbacks — lower priority
   given the sizing result.
2. Independent review of EXP-0001/EXP-0002 configs and interpretation.
3. If continued at all, the only clean evidence now is a future-only shadow; all
   history here is consumed.

## Decisions and constraints

- Engine/metrics are copies of the audited NQ code; keep them in parity — port
  fixes from NQ rather than diverging.
- All historical data here is now consumed research data, not a sealed holdout.
- New variants must use the audited engine and compare against this frozen
  baseline; register material runs in `experiments/ledger.csv`.
