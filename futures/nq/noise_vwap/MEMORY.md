# Project Memory: Noise Area VWAP

This file is the concise handoff for the project. Detailed evidence remains in
the linked reports, code, and run artifacts.

## Scope

- Objective: faithfully reproduce the published Noise Area VWAP strategy, audit
  its implementation, and test whether robust NQ/ES improvements exist.
- Instruments or markets: NQ and ES futures.
- Data coverage: 2011-2026 clean Databento research history. Shared parquet
  lives in `../data/` (`NQ_1m_clean.parquet`, `ES_1m_clean.parquet`); old vendor
  comparison files live in `../data/archive/old_vendor_backup/`.
- Current phase: final validation / future-shadow planning.

## Current status

- Verdict: qualified paper replication; research watchlist, not deployment-ready.
- Last verified: 2026-07-19 from the current forensic and review reports plus
  the corrected faithful Null C run `EXP-0007`, 1-second execution run
  `EXP-0009`, the rejected exit/lookback studies `EXP-0008`/`EXP-0010`, and
  the rejected gap/RVOL veto and sizing studies `EXP-0016`/`EXP-0017`.
- Lifecycle phase: final validation.
- Baseline replication: passed after correcting decision-clock and VWAP-gate
  discrepancies.
- Baseline tolerance and result: clean faithful headline is approximately NQ
  28.3% return / 1.31 Sharpe, ES 15.5% / 0.81, and equal-weight portfolio 23.8%
  / 1.52; compare published NQ 24.3% / 1.67, ES 16.8% / 1.25, portfolio 22.4%
  / 1.57.
- Engine audit: next-open faithful path and parity tooling exist. The Null C
  opening-sentinel defect is fixed and its anchor, net-move, atom, diffusivity,
  and pairing invariants are tested. The clean post-fix faithful run passed:
  NQ z=2.81/p=0.0323/49% capture; ES z=5.63/p=0.0323 with negative null net P&L.
- Execution profile: signal after the decision bar, fill at the next available
  bar open with explicit costs; `signal_close` is an ablation only.
- Holdout status: consumed. Only future shadow data can be clean holdout evidence.
- Experiment ledger: `experiments/ledger.csv` (legacy rows are reconstructed).
- Reproduction command: `python -m futures.nq.noise_vwap.scripts.forensic`.
- Primary evidence: `FORENSIC.md` and `REVIEW.md`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline evidence: `FORENSIC.md`
- Engine and pipeline review: `REVIEW.md`
- Data audit: `DATA_AUDIT.md`
- Kill tests: `KILL_TEST.md`
- Experiment history: `experiments/ledger.csv`

## Confirmed findings

- The original large replication gap was primarily caused by an off-by-one
  decision clock and a missing VWAP gate; the corrected clean run is broadly
  consistent with the paper's headline return claims.
- Faithful execution is next-open. Same-close execution is useful only as a
  labelled diagnostic.
- Performance is regime dependent and 2025 was weak; aggregate Sharpe alone is
  insufficient evidence of a persistent edge.
- The corrected faithful strategy exceeds the session-drift-preserving Null C
  on both NQ and ES in `artifacts/runs/EXP-0007/`; NQ still has material null
  capture (49%), so this supports a qualified timing edge rather than deployment.
- The former Null C implementation could shuffle its artificial zero-link
  sentinel away from index 0 and omit one real inter-bar link. The core and
  legacy study implementations now pin the opening atom and pass multi-seed
  invariant tests in `tests/test_nulls.py`.
- `EXP-0009` confirms that the working continuous-stop edge survives a causal
  first-touch execution model on 68.3 million NQ RTH one-second bars. At 0.5
  tick/side, zero-day daily Sharpe changed from 0.923 (1m close/next-open) to
  0.883 (1s touch), within the predeclared -0.15 tolerance. The touch engine was
  not an improvement: turnover increased and vol-targeted Sharpe/CAGR/maxDD
  changed from 1.184/22.5%/-18.1% to 1.090/19.5%/-24.4%. Evidence:
  `artifacts/runs/EXP-0009/`.

## Provisional hypotheses

- None currently promoted.

## Invalidated or superseded findings

- `HYP-0014` is rejected (EXP-0022): recasting the noise area as an ASYMMETRIC
  (per-side) band — separate up/down half-widths from the causal semi-means
  (`up = mean(max(move,0))`, `dn = mean(max(-move,0))`, `up+dn == sigma` identically),
  blended by a tilt (sig_up = sigma+tilt·(2up−sigma), sig_dn = sigma+tilt·(2dn−sigma))
  — is a cross-market NO-GO. The construction CONSERVES total half-width for every
  tilt (sig_up+sig_dn == 2·sigma, proved in `tests/test_bands.py`), so it is a PURE
  up/down redistribution, NOT the width dial that killed EXP-0010/0012/0021, and no
  RAW/MATCHED split is needed. Every tilt fails the +0.10 gate: NQ monotonically
  WORSE in tilt (ΔSharpe −0.065/−0.095/−0.110 at tilt 0.5/1.0/1.5; best tilt 0.5 also
  −5.4R net); ES best tilt 1.0 ΔSharpe +0.023/+1.9R (far below gate), tilt 1.5
  collapses (maxDD 7.0→12.9R). No Null C spent (real pass fails primary on both).
  DECISIVE diagnostic: the per-side residual at tilt=1 IS a real, cross-market-
  transferring asymmetry but a SMALL one — up-edge ~2–5% wider than symmetric,
  down-edge ~2–5% narrower, consistent across ALL 13 slots, largest mid-day (up/dn
  ≈1.09–1.10), minimal at mfo 89 (≈1.00). That up-tilt is the index up-drift showing
  in the up semi-mean; acting on it HURTS on NQ because widening the up-threshold
  rejects the drift-driven up-breakouts the momentum system rides while narrowing the
  down-threshold admits counter-drift down-breaks. The symmetric band is actively
  BETTER — the up/down asymmetry is a DRIFT property the strategy already monetizes
  (VWAP gate + ride-to-close); re-sizing the band to it double-counts and mis-selects.
  SYNTHESIS (transforms 1–3 complete): neither a √t reshape (cone, EXP-0020), a
  distributional reshape (quantile, EXP-0021), nor an up/down redistribution
  (asymmetric, EXP-0022) adds risk-adjusted value → the noise-area band is fully
  summarized by its per-slot SYMMETRIC LEVEL/width. Recast programme exhausted; retain
  `core/session.py::noise_bands`. The asymmetric band stays in `core/bands.py` as the
  tested per-side benchmark. Evidence: `artifacts/runs/EXP-0022/` (`review.md`,
  `asym_nq.txt`, `asym_es.txt`); `experiments/hypotheses/HYP-0014.md`.
- `HYP-0013` is rejected (EXP-0021): recasting the per-slot dispersion as a QUANTILE
  (percentile) instead of the MEAN is a cross-market NO-GO. At MATCHED median width
  every quantile cell collapses onto the mean band — best matched q0.90 NQ ΔSharpe
  +0.032 / ΔnetR +1.4R, ES ΔSharpe +0.067 / ΔnetR +5.2R, both below the +0.10 gate
  → no Null C. DECISIVE diagnostic: the residual quant/mean by decision slot is ≈1.0
  everywhere (0.96–1.01) on both markets = the matched quantile is just the mean band
  RESCALED, no reshaping of the intraday profile → the per-slot |move| distribution
  SHAPE carries no info beyond its LEVEL; the mean is a sufficient statistic at fixed
  width. The only RAW-view "win" (q0.50, narrower than the mean → more trades, NQ
  netR 101.9 vs 91.2 / Sh 1.34) is the width/capacity dial (cf. k-multiplier WFO,
  EXP-0010/0012), not a quantile effect — it vanishes under matched width. SYNTHESIS
  with EXP-0020: neither a √t reshape (cone) nor a distributional reshape (quantile)
  adds risk-adjusted value → the noise-area dispersion is fully summarized by its
  per-slot LEVEL/width. Transform 2 of the recast programme; the remaining lever is
  transform 3 (anchor/symmetry, asymmetric). `core/bands.py::noise_bands_quantile`
  (tested). Evidence: `artifacts/runs/EXP-0021/` (`review.md`, `quant_nq.txt`,
  `quant_es.txt`); `experiments/hypotheses/HYP-0013.md`.
- `HYP-0012` is rejected (EXP-0020): recasting the noise area as an analytic √t
  DIFFUSION CONE (one causal per-session vol scalar × √(mfo/M), calibrated to the
  baseline's end-of-day width) is a cross-market NO-GO as a REPLACEMENT for the
  empirical per-slot mean-|move| band. It is WORSE, not equal: NQ ΔSharpe −0.101 /
  ΔnetR −1.4R / +705 trades / net pt-per-trade 3.159→2.530; ES ΔSharpe −0.125 /
  ΔnetR −7.5R / +436 trades. Real pass fails the primary metric → no Null C spent
  (standing rule). POSITIVE finding via the residual m(mfo)=emp/cone: on BOTH
  markets the empirical band is ~1.35–1.55× WIDER than √t in the first hour (mfo
  29–59), converging to 1.0 at the close → intraday displacement is SUPER-DIFFUSIVE
  in the morning (opening-vol bulge wider than a random walk); the end-of-day-
  calibrated cone is too narrow early, admits noisier morning breakouts and dilutes
  per-trade quality. The per-slot empirical SHAPE is load-bearing (specifically the
  morning) and transfers to the ES sibling = real tape structure, not machinery.
  Coverage: the cone recovers only 90 decision points (0.2%, mfo 209 ≈ 13:29 ET) on
  liquid NQ/ES — the Rule-9a `min_periods` deletion bites THIN markets
  (GC/YM/RTY), not indices. Retain `core/session.py::noise_bands`. The cone stays in
  `core/bands.py` as tested reusable machinery / the pure-diffusion benchmark; its
  super-diffusive-open residual shapes the next transforms (2 quantile, 3
  asymmetric). This is transform 1 of the user's 4-transform noise-area recast
  programme (cone → quantile → asymmetric; range/EWMA dropped by user). Evidence:
  `artifacts/runs/EXP-0020/` (`review.md`, `cone_nq.txt`, `cone_es.txt`);
  `experiments/hypotheses/HYP-0012.md`.
- `HYP-0011` is rejected (EXP-0019). Thesis (user): high vol -> checking the stop every
  bar causes whipsaw, so use an INTERVAL (15-min) check when volatile and the continuous
  (every-bar) stop when calm; on a prop account capped at 1-2 micro contracts you cannot
  size with vol, so the exit CADENCE is the substitute vol lever and the deployable metric
  is raw DOLLAR daily Sharpe at 1 contract (not ATR-R). Two parts: (1) FIXED cadence sweep
  filled the gap between the 30-min decision clock and every-bar and found a NON-MONOTONE
  interior optimum at ~15 min on the dollar metric (NQ Sh 1.14->1.29, ES 0.93->1.09), but
  the fixed-15 vs 30-min-decision Null C FAILED — ATR-R NQ +0.034 p=0.29 / ES +0.058 p=0.19,
  dollar NQ +0.113 p=0.064 / ES +0.120 p=0.097 (marginal, never <0.05); the entire dollar
  uplift is vol-era weighting (rule 19), it evaporates under ATR normalisation. (2) The
  CONDITIONAL cadence (causal intraday-to-date range vs trailing-14-session same-tod median;
  hi-vol->15m, lo-vol->1m) is DOMINATED by fixed cadences: NQ cond Sh$ 0.92 vs fixed everybar
  0.96 vs fixed cad15 0.97; ES 0.70 vs 0.69 vs 0.81. Null C cond-everybar (dollar): NQ real
  -0.042 vs null mean +0.032 p=0.7419 (22/30 beat real); ES real +0.017 vs null +0.082
  p=0.8387 (25/30). DECISIVE diagnostic: the null CENTERS POSITIVE and the real tape sits
  BELOW its own null on both markets = the EXP-0010/0012 variance-amplifier signature. The
  whipsaw mechanism is mechanically real but NOT information: whipsaw reduction is a
  volatility/path-geometry property the path-preserving Null C PRESERVES (diffusivity gate
  exact), so noise reproduces it and then some; the surviving NQ timing edge actually PREFERS
  the every-bar checks the conditioner removes in high vol. Retain the fixed continuous stop.
  Overlays added default-off: int-cadence exit_check in core/engine.py + engine2.py
  ("decision"/"every_bar" strings bit-exact preserved); cond_regime/hivol_cadence/
  lovol_cadence in core/engine2.py (cond_regime=None parity). Scripts: exit_cadence.py
  (screen), hyp_0011_exit_cadence.py (fixed null), hyp_0011_cond_cadence.py (conditional
  null). Evidence: `artifacts/runs/EXP-0019/` (cond_{nq,es}.txt, fixed_cadence_null_{nq,es}.txt).
- `HYP-0010` is rejected as deployable cross-market alpha (EXP-0018). Thesis: NQ and ES
  share the "noise area", so gate NQ entries on contemporaneous ES confirmation. On the
  common NQ∩ES set (3628 sessions) the PRIMARY `agree` variant (take the NQ signal only
  when ES has broken out of its own noise area the SAME direction) gives net daily Sharpe
  1.074 vs baseline 1.102 (uplift −0.029, fails the +0.05 gate) and cuts total net R
  ~25%. IMPORTANT contrast with GC EXP-0007: on NQ `agree` is NOT a rarity filter — it
  RAISES gross/trade (+5.302 vs +4.945), net/trade (+4.827 vs +4.470) and hit-rate
  (0.407 vs 0.380) while trading ~30% less, so ES confirmation genuinely concentrates
  per-trade quality (the user's "an NQ break with no ES break is noise" has real per-trade
  support). It just does not monetize: it is a turnover/capacity lever (day-net t 2.68 vs
  3.15, flat Sharpe), not risk-adjusted alpha. `gate` (ES in ANY breakout) ≈ `agree`
  because ES breakouts during an NQ signal are almost always same-direction (coupling).
  The softer `vwap` gate (user's "don't go long if ES is under its VWAP") is inert-to-
  harmful (gross/kept FELL) — the noise-area breakout, not ES's VWAP side, carries the
  info. `es_dir` (ES leads?) is worse (Sh 0.70) and `es_opp` genuinely negative (Sh
  −0.72, gross −0.51, no Rule-16 mirror-trap) so ES does not lead NQ. The only Sharpe-
  beater `disagree` (+0.105) fails its re-pairing null (200 draws, null center +0.0001,
  z=1.08, 14% of draws beat real) — null center ~0 rules out a pure rarity filter but the
  uplift is inside the null noise band and weaker than GC's already-marginal disagree
  (z=1.53); post-hoc family-of-6 on consumed history. Retain the unconditioned baseline.
  Overlay `ext_state`/`cond_mode` added default-off to `core/engine.py` (cond_mode=None
  parity verified: 2923 trades / 14454.25 gross). Evidence: `artifacts/runs/EXP-0018/`.
- `HYP-0009` is rejected as validated capital-allocation alpha, although it is
  a default-off future-shadow candidate. The frozen four-level gap/RVOL sizing
  schedule kept all 4,209 trades and improved real zero-day daily Sharpe from
  1.288 to 1.398, net R from 91.20 to 101.97, and max drawdown from 4.70R to
  4.42R at only 0.957x mean trade weight. Net-R uplift was positive pre-2023
  (+8.40R) and 2023+ (+2.38R). However, 30 paired full-pipeline Null C draws
  reproduced mean Sharpe uplift +0.074 (sd 0.045) versus real +0.111: z=0.81,
  with 30% of null draws at least as strong. Do not deploy or use this as an ML
  justification on consumed history; only future shadow can resolve the
  residual real-minus-null uplift. Evidence: `artifacts/runs/EXP-0017/`.
- `HYP-0008` is rejected: vetoing otherwise valid NQ breakouts when the
  overnight gap opposes the signal and signal-minute RVOL(90) is below 1.2
  raised real net R by +3.97R and daily Sharpe by +0.236, with positive deltas
  both pre-2023 and 2023+, but retained only 86.1% of trades and failed the
  paired full-pipeline Null C test. The null produced a larger mean uplift of
  +5.18R (sd 5.18; real-vs-null z=-0.23; 53.3% of draws beat real). The EXP-0015
  conditional bins therefore did not validate as predictive alpha; treat this
  fixed rule as selectivity/turnover and do not use it to justify XGBoost.
  Evidence: `artifacts/runs/EXP-0016/`.
- `HYP-0007` is rejected for unconditional ES production-default adoption, but
  confirms material execution utility for the frozen EXP-0012 `s0.5_y0.5` cell.
  At 0.25 tick/side, full-sample net R/Sharpe/maxDD improve from
  51.5/0.70/7.45R to 84.3/1.02/6.22R and trades fall 37%. The joint net-R and
  maxDD condition passes only 1 of 4 eras: drawdown worsens in 2020+ and 2023+,
  while both net R and drawdown worsen in 2025+. Full-sample cost resilience is
  strong (at 1 tick/side: +42.4R treatment versus -16.1R baseline), so retain the
  exit default-off as a forward-shadow/execution-cost lever, not alpha or an
  unconditional default. Evidence: `artifacts/runs/EXP-0014/`.
- The original local replication statistics are invalid as faithful-paper
  evidence because the decision clock and VWAP gate differed.
- Pre-fix Null C magnitude estimates are superseded for the current faithful
  configuration; preserve them as historical evidence, not the current verdict.
- `HYP-0001` is rejected: short lookbacks did not improve full-sample NQ
  performance (best nonbaseline ΔSharpe -0.065, p=0.8571) and ES's small uplift
  (+0.026) was not family-wise significant (p=0.1905). Evidence:
  `artifacts/runs/EXP-0008/`.
- `HYP-0006` is rejected for production adoption but is a qualified NQ-specific
  forward-shadow candidate. A fixed early-flat cutoff before the close: NQ best cutoff
  45 ΔSharpe +0.101 clears the Sharpe threshold but net R is −0.8 below baseline (fails
  the net-R gate) and maxDD is worse; ES all cutoffs hurt (net R +51.5→+43-44, best
  ΔSharpe −0.030) so the sign does not transfer. Unlike the looser-stop artifacts this
  is NOT tail truncation (top-decile winner-R preserved) — it reshapes late-session
  variance only, on NQ only. **Follow-up Null C (2026-07-20)**, run at user request under
  a variance-avoidance reframing (net-R PRESERVATION as control, not increase): NQ PASSED
  (real max ΔSharpe +0.101 vs null max mean −0.048, p=0.0323, 0/30 null draws beat real —
  the null centers NEGATIVE, so this is a real late-session-specific timing feature, NOT
  the "fewer trades → higher Sharpe" machinery that killed EXP-0010/0012). ES REJECTED
  (real −0.030 vs null +0.008, p=0.7419: noise beats the real tape). The user's pan-index
  structural thesis (3:45 MOC imbalance, passive-close rebalancing, 0DTE gamma — all ≥ as
  strong on the S&P) is FALSIFIED by ES: a pan-index cause would help ES as much or more,
  but ES inverts. So the surviving NQ effect is NQ-tape-specific, buys daily-dispersion
  Sharpe only (net R flat, maxDD WORSE), and concentrates in 2023+ (23+Sh 1.10→1.54) on
  consumed data. Forward-watch, do not bank historically, do not attribute to the
  MOC/rebalance/0DTE mechanism. `flat_before_close` default-off in `engine2` (parity
  verified). Evidence: `artifacts/runs/EXP-0013/` (`nullc_nq.txt`, `nullc_es.txt`).
- `HYP-0005` is rejected: a narrower noise exit band + looser (below-price)
  VWAP-sigma band does not validate. NQ best cell ΔSharpe +0.090 / ΔnetR +14.1
  MISSES the +0.10 gate (no null run per the standing rule); ES best +0.320 clears
  the gate but the family-max Null C reproduces +0.254 on noise (p=0.2903). The
  literal negative-y (tighter) grid was rejected on both markets first. This is the
  3rd looser-stop/fewer-trades "higher Sharpe" that Null C exposed as a
  variance/selectivity amplifier (after EXP-0010 VWAP-touch and the KAMA rarity
  filter): treat any "fewer trades → higher Sharpe" exit as machinery until Null C
  clears it. The looser exit is a turnover/capacity lever, not alpha. exit_band
  added default-off to `engine2` (s=1/y=0 parity verified). Evidence:
  `artifacts/runs/EXP-0012/`.
- `HYP-0004` is rejected: the paper's two-stage RR ladder exit (Table-2
  −1R/+2R → bank 50% → 0R/+5R, 1R = entry-frozen band distance) does not beat the
  `both` stop. NQ ΔSharpe −0.075 / ΔnetR −12.9 (fails +0.10 gate), loses to
  `tp1.0_50` by −0.131 Sharpe, Null C p=0.6129; ES ΔSharpe +0.014, Null C
  p=0.3226. The fixed −1R stop and +5R cap cut gross R (111→97), discarding the
  trailing stop's edge. Ladder added default-off to `engine2` (tests + parity
  verified). Retain `both`; keep `tp1.0_50`. Evidence: `artifacts/runs/EXP-0011/`.
- `HYP-0003` is rejected: the paper's flagship every-bar VWAP-touch exit
  (`stop_ref="vwap"`) does not beat the current `both` stop. NQ uplift ΔSharpe
  -0.031 (fails +0.10 gate), Null C p=0.8710; ES uplift +0.258 but Null C
  p=0.2903. The null-uplift mean is positive on both markets (+0.083 NQ, +0.178
  ES), so the looser stop is a variance/selectivity amplifier that lifts Sharpe
  as much on noise as on signal, not exit information. It does raise per-trade
  net R with ~27% fewer trades — a turnover/capacity lever only, never a Sharpe
  claim. Retain the `both` stop. Evidence: `artifacts/runs/EXP-0010/`.

## Decisions and constraints

- Preserve existing import paths and reports during migration to the standard
  project structure.
- No historical period may be relabelled as sealed holdout after inspection.
- New strategy variants must use the audited engine and compare with the frozen
  faithful baseline.
- Routine ideas, hypotheses, experiment records, closeout, and hygiene checks use
  the shared `tools/research_admin.py` workflow.

## Known risks and open questions

- Obtain independent review of `EXP-0007` configuration and interpretation.
- Obtain independent review of the causal stop activation and cost treatment in
  `EXP-0009`; one-second OHLC still cannot resolve within-second path order.
- Quantify robustness to neighbouring parameters, costs, and post-publication
  regimes without treating searched variants as confirmatory evidence.
- Define the forward shadow start date and immutable observation protocol.

## Next actions

1. Review `EXP-0007`, `EXP-0008`, and `EXP-0009` independently.
2. Decide whether the 2023+ short-lookback regime observation belongs only in
   future shadow monitoring; do not optimize it further on consumed history.
3. Decide whether to enter a future-only shadow period or close the project.

## Promotion candidates

The clock and gate failures may become cross-project learnings after confirming
the same failure modes in another project. They remain project-specific here.
