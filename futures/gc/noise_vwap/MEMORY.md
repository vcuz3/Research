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
  EXP-0002 (HYP-0001 COMEX hours), EXP-0003 (HYP-0002 anchor×k×lookback grid),
  EXP-0004 (HYP-0003 continuous stop), EXP-0005 (data-quality band-coverage fix →
  revised baseline), EXP-0006 (HYP-0004 exit system: partial-TP + looser clock),
  EXP-0007 (HYP-0005 cross-asset ES direction-conditioning).
- The strategy machinery (`core/engine.py`, `core/metrics.py`, `core/nulls.py`) is
  a verbatim copy of the audited NQ code; only data path and contract economics
  differ. **Fast path (EXP-0003):** `core/engine2.py` + `core/engine2_nb.py`
  (numba) + `core/session.py` ported from NQ — bit-exact vs `core.engine` (2692
  trades, gross 974.60 pt / +0.362 pt), ~13x faster (0.39s vs 5.1s/config).
  `core/session.py` adds the `load_rth_both` dual-anchor loader (rth/eth VWAP) +
  k-scalable bands; `core/nulls_session.py` is the sdate/mfo return-shuffle
  rebuilding both anchors' VWAP (diffusivity real=null=0.1000 pt).
- Baseline (REVISED, EXP-0005; 0.50 tick/side, 1 contract, per-day clustered,
  before sizing): gross +0.362 pt/trade, net +0.217, day$ net +31.0, net t=+1.30,
  net Sharpe 0.48; gross Sharpe 0.79. 2692 trades over 3647 sessions. *(Superseded
  EXP-0000: +0.359 / +0.214 / +30.2 / t+1.25 / Sh 0.46 / 2641 trades.)*
- Reproduce: `python -m futures.gc.noise_vwap.scripts.run_baseline GC 90`.
- Evidence: `reports/BASELINE.md`, `artifacts/runs/EXP-0001/`, `.../EXP-0002/`.
- **Data-quality gate (rule 9a):** run `python -m futures.gc.noise_vwap.scripts.data_quality GC 90`
  at every data/feature change; report is `reports/DATA_QUALITY.md`. Timeline is
  clean (0 dup / 0 out-of-order / 0 intra-session rolls); 13.1% of sessions miss
  ≥1 minute (thin GC afternoon, genuine no-trade minutes).

## Confirmed findings

- **DATA-QUALITY FIX (EXP-0005), revised baseline.** The noise band used
  `rolling(90, min_periods=90)` (verbatim NQ port): it required ALL 90 prior
  sessions to have a bar at a given minute, so ONE missing minute in the trailing
  window nulled the band, and the engine skips a band-less decision bar. On GC's
  thin post-floor-close afternoon this silently deleted up to **28% of the 15:29
  decisions** (2149 decision points total), time-of-day-dependent, invisible on
  liquid NQ. Fixed to `min_periods = ceil(0.9×90) = 81` (`BAND_MIN_FRAC`, in BOTH
  `core/data.py` and `core/session.py` for parity); band coverage now uniform
  ~97.8% across decision minutes. Causal (still `move.shift(1)`, prior-only),
  parity re-verified bit-exact (2692 trades / 974.60 pt). Baseline nudged UP
  (2641→2692 trades, net Sharpe 0.46→0.48, gross t 2.11→2.17) — the defect was
  CONSERVATIVE (deleted signals; no lookahead/fill artifact), so **verdict is
  UNCHANGED NO-GO** (EXP-0001 vol-target Sharpe 0.07 is still binding). Caveat:
  **EXP-0001..EXP-0004 all ran on the STRICT bands** — their REJECT/NO-GO verdicts
  are directionally safe (small change, wide margins) but any FUTURE re-open of
  those questions must rebuild on the relaxed bands. Evidence:
  `artifacts/runs/EXP-0005/review.md`, `reports/DATA_QUALITY.md`. Added workspace
  RULES.md rule 9a (mandatory data-quality gate at every data/feature stage).

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

- **HYP-0003 REJECTED (EXP-0004): continuous (every-bar) stop INVERTS on GC.** The
  NQ GO variant — check the band/VWAP stop every 1-min bar instead of on the 30-min
  decision clock, entries/flips unchanged — is an *adopted* uplift on NQ (Sharpe
  1.16→1.30 at SAME gross, Null-C z5.20). On GC it does the opposite: gross
  COLLAPSES +0.359→+0.127 pt/trade (−65%), net Sharpe +0.46→−0.06 (Δ−0.52, t
  +1.25→−0.17), trades 2641→3806; net-negative from 0.50 tick. The loser tail DID
  shrink (loser mean −$330→−$197, stop_frac 0.67→0.82) exactly as on NQ, but it
  clipped the winners (short-leg gross →0) because GC has NO intraday drift and is
  noise-dominated at the minute scale — tightening the exit check is whipsaw, not
  variance reduction. The 30-min clock's looseness is load-bearing on gold. Single-
  variable change (`core.engine` `exit_check=every_bar`); fills honest (0 same-bar
  in both). Null-C NOT run (real pass fails the primary metric = already a REJECT,
  per gate-nullc-on-success-metric). Keep the decision-clock stop; do NOT re-open on
  consumed history. Evidence: `artifacts/runs/EXP-0004/review.md`.

- **HYP-0004 REJECTED (EXP-0006): partial-TP exit is BENIGN but sub-threshold; the
  looser (60-min) clock is HARMFUL.** Ported the NQ exit survivor (partial-TP +
  runner: bank `tp_frac` at `tp_atr` ATR favourable, runner keeps the decision-clock
  stop) to GC's decision-clock baseline, plus a 60-min clock. Best variant
  (tp1.0_67 / tp1.5_50) lifts net daily Sharpe only **+0.023 / +0.021** @0.50tick —
  below the +0.05 gate → REJECT, Null-C not run (gate-nullc-on-success-metric).
  KEY CONTRAST with EXP-0004: partial-TP does **not** invert like the continuous
  stop — gross is **held/nudged up** (+0.362→+0.375 pt at tp1.5_50), win% 33.6→34.0,
  because it BANKS the extension instead of tightening the runner's stop. So the
  drift/noise-ratio learning holds on the take-profit side too, just weakly. The tp
  ordering **inverts vs NQ**: tighter tp0.75 HURTS (−0.014), value only at tp≥1.0
  rising to tp1.5 — gold needs more room before banking (same theme as the
  continuous-stop and 60-clock results). 60-min clock halves net Sharpe
  (0.475→0.258, bigger losers) — "30-min looseness is load-bearing" does NOT mean
  looser is better; 30 is near a local optimum. Parity vs core.engine asserted.
  Also fixed a pre-existing broken data path (parquet relocated to shared
  `futures/gc/data/`; repointed `core/data.py`+`core/session.py` to `parents[2]`).
  Evidence: `artifacts/runs/EXP-0006/review.md`.

- **HYP-0005 REJECTED (EXP-0007): conditioning GC direction on the contemporaneous ES
  noise-VWAP state DESTROYS the edge; the "equity momentum bleeds into gold" thesis is
  disproven at the direction level.** At each GC decision bar, ES's own noise-VWAP state
  (long/short/flat, built by the SAME audited `core.data`/`noise_bands` on ES) overlays
  GC's `want` (engine `cond_mode`, no-op off → parity bit-exact 2692/974.60). Common
  GC∩ES set 3550 sessions; ES states 14% long / 12% short / 74% flat. Common-set
  baseline net Sharpe 0.49 (2681 trades, gross +0.371 pt). Three pre-specified overlays,
  ALL worse: `agree` (take GC signal only if ES agrees) HALVES gross +0.371→+0.162 and
  flattens net Sharpe→0.03 (t+0.04) on 582 trades (−78%) — a rarity filter that selects
  the WORSE GC trades (if ES-agreement carried signal it would CONCENTRATE gross, not
  dilute it); `gate` (ES in any breakout) net Sharpe −0.11; `es_dir` (trade GC in ES's
  direction, the strongest thesis form) net NEGATIVE Sharpe −0.56 (hit 46% but no
  payoff = high-win/low-payoff loser). Best uplift −0.466 << +0.05 gate → re-pairing
  null (Rule 18) NOT spent for these three (real pass fails primary metric = already
  REJECT, gate-nullc-on-success-metric; a null only adjudicates a POSITIVE uplift).
  RECONCILES with EXP-0002: the edge needs equity HOURS (a regime/liquidity backdrop =
  "when"), but does NOT follow ES's instantaneous sign ("which direction") — separable,
  and the direction reading is dead. **FOLLOW-UP (user asked re opposite-ES + continuous
  stop):** two more overlays — `es_opp` (trade GC OPPOSITE ES) net Sharpe −1.03, WORSE
  not better = Rule-16 mirror trap (es_dir loses on COSTS: gross +0.039≈0, net −0.106 =
  0.039−0.145 round-trip; flipping gives gross −0.047 and still pays 0.145 → −0.192 — the
  negative of a cost-dominated loser is a bigger loser); continuous stop harmful on GC
  (re-confirms EXP-0004, baseline 0.49→0.01, worst cell es_opp+continuous −2.82). The ONE
  positive overlay is `disagree` (GC's own signal only when ES DISAGREES = skip the
  ES-agreement trades): net Sharpe 0.49→**0.67** (gross +0.371→+0.439, t 1.35→1.74, −13%
  trades), clears +0.05 gate → EARNED the re-pairing null. Null (300 yr-stratified draws):
  real uplift +0.177 vs null mean −0.013/sd 0.125, **z=+1.53, frac(null≥real)=0.073**.
  Null centered at ~0 (NOT +0.177) ⇒ NOT a pure rarity filter (random-ES-day skipping
  doesn't lift Sharpe) — ES-agreement genuinely marks lower-quality GC trades = weak-real
  cross-info. BUT z=1.53 (p≈0.073) misses the z>2/<5% bar AND is the MAX over ~6 post-hoc
  configs on consumed history ⇒ QUALIFIED screen, NOT validated; needs future/shadow
  holdout (Rule 26). Does NOT touch the sizing NO-GO (Sharpe 0.07). Tradable reading:
  "ES agreement is a mild NEGATIVE quality tag" (skip those trades), not "trade with ES"
  (dead) or "trade opposite ES" (dead). ES added to `core/data.py` PATHS (state only, no
  ES economics/P&L); engine `cond_mode` ∈ {agree,gate,es_dir,es_opp,disagree} (no-op off).
  Evidence: `artifacts/runs/EXP-0007/review.md`, `.../disagree_repairing_null.txt`.

## Not yet done (optional; edge is already NO-GO)

1. **Portfolio-leg study (strongest un-consumed direction; see IDEA_BACKLOG).**
   GC standalone is NO-GO, but the same small-but-real timing edge exists on NQ/ES/GC
   and GC's low equity correlation is a book-level ASSET. Question: does adding GC to
   an NQ+ES noise-VWAP book raise book Sharpe / cut drawdown? Un-consumed (about the
   COMBINATION, not GC's parameters); likely a new cross-project experiment. Deploy on
   MGC (micro gold, 1/10 notional) — fixes sizing granularity, NOT the per-instrument
   Sharpe. **All GC strategies here are traded on MGC.**
2. ~~Cross-asset conditioning (condition GC direction on ES noise-VWAP state)~~ — DONE,
   REJECTED (HYP-0005/EXP-0007): direction-conditioning DESTROYS the edge (best uplift
   −0.466). Only a same-window vol/regime conditioner (NOT direction) remains open, and
   it is lower-priority than the portfolio-leg study.
3. Era stability (2011–2026), cost stress, neighbouring lookbacks — lower priority
   given the sizing result.
4. Independent review of EXP-0001/EXP-0002/EXP-0004 configs and interpretation.
5. If continued at all, the only clean evidence now is a future-only shadow; all
   history here is consumed.

## Decisions and constraints

- Engine/metrics are copies of the audited NQ code; keep them in parity — port
  fixes from NQ rather than diverging.
- All historical data here is now consumed research data, not a sealed holdout.
- New variants must use the audited engine and compare against this frozen
  baseline; register material runs in `experiments/ledger.csv`.
