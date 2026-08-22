# Noise VWAP Idea Backlog

Uncommitted brainstorming belongs here and is not evidence. Add ideas with
`python tools/research_admin.py new-idea --project futures/nq/noise_vwap`.

## Resolved actions (from the EXP-0047 critique, 2026-08-16 — CLOSED)

The critique deferred two TODOs pending a direct mechanism study of post-stop
reversion. The study is done (`scripts/study_post_stop_reversion.py` →
`reports/POST_STOP_REVERSION.md`) and it resolved both — in the REAFFIRMING
direction, not the softening one first queued.

- **TODO-A — DONE; NO-GO stands for a SELECTION reason (a mid-course over-statement
  was caught and corrected).** The study's first pass wrongly concluded "no post-stop
  reversion exists," which contradicted the paper and `FAST_EXIT_REVERSION_EXPLORE.md`
  — it had bucketed reversion by MAE *depth* not adverse-*run length*, and read "small
  in R units" as "nonexistent." Corrected: short-term reversion IS real and run-length-
  monotone on all bars (ES run≥5 +0.0039 R, t 6.2), but tiny in tradable R units
  (~0.003 R gross; the paper's "+0.180×med_move, t 12.7" = 0.0018 R NQ / 0.0025 R ES —
  huge t is sample size + median-move units) and hence sub-cost standalone. At OUR stops
  the run-length monotonicity is GONE (NQ run≥5 rev5 ≈ 0; ES insignificant) because a
  run that breaks the band+VWAP stop is a continuation-selected case (no run-length
  STRUCTURE to key on). So the paper's SIGN-mechanism NO-GO stands. Records corrected:
  report, auto-memory, EXP-0047 review/HYP, project MEMORY.
- **SECOND CORRECTION (same day) — the blind-wait uplift is REVERSION, not exposure; a
  blind stop-delay is NOT fully closed.** The first draft of TODO-A (and EXP-0047's
  review) labelled the blind fixed 4-bar delay's +0.204 dSharpe an "exposure/variance"
  effect. A Shapley decomposition disproves it: **+117% MEAN / −17% variance**. The blind
  delay captures a small, real, cost-surviving post-stop reversion (+0.0041 R/trade net,
  +6.6 R over TEST) — more than the paper's sign rule. Two claims, kept separate:
  1. Paper's fast-alpha SIGN mechanism = **NO-GO** (a blind delay dominates it).
  2. A blind fixed short stop-delay = a small **REAL** reversion capture that weakens the
     stop (win rate 27%→38%, but maxDD +22% 4.70→5.73 R, fatter per-trade tail). Sharpe/
     Sortino positive; a drawdown-constrained prop objective likely negative. This is an
     **OPEN, drawdown-gated lead** — see new IDEA-0009.
- **TODO-B — narrowed.** A structured-delay-vs-Null-C release keyed on run-length is
  DROPPED (the structure is selected out). But the *flat pooled* bounce a blind delay
  harvests is real and is now IDEA-0009 (drawdown-aware, not a stop-event structure play).

This closes the paper's SIGN-mechanism release direction (rule 25) but leaves a small,
real, drawdown-gated blind-delay reversion capture OPEN. See
`reports/POST_STOP_REVERSION.md` §Decomposition for the reconciliation.

## Ideas

Priority order after the prerequisite faithful Null C rerun (`EXP-0007`):

1. `IDEA-0001` was rejected by `EXP-0008`; preserve it as negative evidence.
2. VWAP-touch exit (`stop_ref="vwap"`) vs the current `both` stop was REJECTED by
   `EXP-0010` (HYP-0003): NQ ΔSharpe -0.031, ES +0.258 but Null C p=0.29 with a
   positive null-uplift mean on both markets — a variance/selectivity amplifier,
   not exit information. Preserve as negative evidence; the paper's strongest
   exit family (4.2) does not transport.
3. `IDEA-0002` is a small, low-complexity exit ablation.
4. `IDEA-0003` and `IDEA-0004` promoted to active pursuit after the 2026-07-18
   review of paper 5095349: the paper's headline VWAP/ladder/asymmetric-exit
   results are in-sample-optimized (no holdout/WFO), so harvest them only as
   isolated single-variable changes each gated by its own full-pipeline Null C.
5. `IDEA-0005` is a portfolio-risk study, not an alpha improvement.
6. `IDEA-0006` is low priority because it imports a large in-sample search.
7. `IDEA-0007` / `IDEA-0008` are the two surviving leads from the EXP-0046
   fast-alpha exit-leg exploration (`reports/FAST_EXIT_REVERSION_EXPLORE.md`).
   The VWAP-stop institutional variant was killed (Study 3 inverted the
   hypothesis); do not pursue it.


## IDEA-0007 — Exit-only fast-alpha overlay at a fixed SHORT horizon

- Status: **REJECTED by EXP-0047 (HYP-0035), 2026-08-16.** Frozen h*=3 on TRAIN,
  evaluated on held-out TEST: real gate passes (NQ dSharpe +0.135) but fails
  `beats_fixed` (blind delay +0.204) and `beats_random` (frac 0.100); ES inverted
  arm ties the real arm. The residual lift is a generic exit-delay/looser-stop
  exposure amplifier, not reversion timing. Preserve as negative evidence.
- Created: 2026-08-16
- Observation: EXP-0046 reported the exit-only leg at only the paper's 5-min
  horizon (NQ +0.025, ES +0.176). The exploration horizon sweep
  (`explore_fast_exit_reversion.py`) shows the exit-only dSharpe is positive at
  EVERY horizon 1–10 min on both markets, and short horizons (1–3 min) are as
  good or better than 5 min (NQ ~+0.08–0.10 vs the +0.025 dip at h=5; ES peak
  +0.206 at h=2). The h=5 NQ number was a local dip, not the leg's strength.
- Proposed mechanism: the exit micro-reversion is front-loaded (Study 1: NQ
  reversion essentially complete by minute 2), so a shorter bounce-detection
  horizon catches it before it decays.
- Kill test (to preregister): fix ONE short horizon in advance (candidate h=2 or
  h=3); REJECT unless dSharpe ≥ +0.10 with net R not falling, beats the
  random-release null (frac<0.05) at matched trade count, beats fixed/inverted,
  survives a per-horizon signal_close-vs-next_open fill ablation (EXP-0046 showed
  the ES exit leg is partly fill-sensitive), and Null C. Searched (rule 26): the
  6-point sweep is discovery; the confirmatory run must fix the horizon a priori.

## IDEA-0008 — Run-length-conditioned exit bounce

- Created: 2026-08-16
- Observation: reversion is a TAIL-OF-RUN-LENGTH effect on both markets (Study 1):
  a single adverse candle CONTINUES (NQ −0.035×med-move, t −7.3), while a run of
  ≥5 same-direction candles reverts hard (NQ +0.180, t +12.7; ES +0.340, t +20.3),
  monotone in run length. The paper's "reversion strengthens with consecutive
  candles" claim replicates.
- Proposed mechanism: arm the exit-bounce wait only after a long adverse run,
  where a genuine micro-reversion is likely, and not after a single candle (which
  continues) — a quality gate on the exit-timing overlay.
- Traps to preregister against: the run-length conditioner is correlated with the
  size of the shared-close boundary error (LEARNINGS §6, the "conditioner
  correlated with boundary noise" family), so the paired one-bar embargo must be
  built into the RELEASE, not just the diagnostic; the run-length threshold is a
  searched selector (fixed-threshold-timeofday-selector family) and must be swept
  as a placebo at matched selection rate.
- **Prior WEAKENED (2026-08-16, `reports/POST_STOP_REVERSION.md`).** Study 1's
  run-length reversion is measured on ALL adverse runs; but conditioned on the
  STOP event specifically, adverse runs are SHORT (median 2 bars, p90 4) and
  reversion does NOT scale with overshoot (largest-MAE quintile continues) and is
  below a matched placebo. So the long-run population IDEA-0008 wants to arm on is
  rare at our stops, and the reversion there is placebo-dominated. Only worth
  pursuing as an exit overlay on NON-stop exits, if at all; the stop-exit version
  is effectively covered by the POST_STOP_REVERSION NO-GO.


## IDEA-0009 — Blind fixed stop-delay (drawdown-gated reversion capture)

- Created: 2026-08-16
- Observation: separated from the EXP-0047 sign-mechanism NO-GO by the decomposition
  in `reports/POST_STOP_REVERSION.md` §Decomposition. A *blind* fixed ~4-bar delay of
  the stop-exit lifts NQ TEST Sharpe +0.204 over baseline, and the lift is **+117%
  MEAN / −17% variance** (Shapley) — i.e. it captures a small, real, cost-surviving
  post-stop reversion (+0.0041 R/trade net, +6.6 R over TEST), MORE than the paper's
  sign-timed release (+0.0030). No run-length structure to key on (selected out); the
  effect is a flat pooled bounce dominated by short-run stops.
- The catch: it works by weakening the stop → fatter per-trade left tail (meanLoss
  −0.089→−0.111). Delay sweep (`scripts/sweep_fixed_delay.py`) added three cautions:
  (a) the P&L-optimal delay is **~5–6 bars on NQ** (not 2m; delay 6 +0.249), but **~2
  bars on ES** (delay 4+ decays) — the markets DISAGREE, the sibling-disagreement
  signature that killed the overlay; (b) the +22% maxDD was delay-4-specific and
  non-robust (NQ maxDD *better* than base at delay 6); (c) by-year the gain is fading —
  clearly positive 2020–2024 but NEGATIVE in 2025 and 2026 on both markets.
- Baseline edge erosion (`scripts/diag_by_year.py`): NQ's per-trade edge eroded
  2024->2026 (gross pt/trade 8.51->4.57->-4.09, win% 27.9->25.8->20.8); NQ-specific (ES
  gross/trade ROSE in 2025, 0.97->2.42), 2026 a partial choppy tape (negative gross both).
- Causal regime split (`scripts/regime_sharpe.py`, trailing-ATR vol tercile + trailing-20
  close efficiency-ratio trend tercile, both known at session open) — **corrects a
  verbal-mechanism error**: I hypothesized the delay hurts in "failing-breakout"
  (continuation) regimes. FALSE on NQ — the delay helps in EVERY NQ vol and trend cell
  (+0.20…+0.30, incl. hiVol and trend). So the NQ 2025–26 collapse is ORTHOGONAL to these
  regimes (2026 sits in hiVol, whose delay-dSharpe averages +0.21) — it is a
  time-localized NON-STATIONARITY, not a vol/trend regime, which is more concerning.
  ES *is* genuinely regime-conditional and in the OPPOSITE direction to the guess: the
  delay helps ES in midVol (+0.62, rescuing a −0.16 baseline) and trend (+0.22) but HURTS
  in hiVol (−0.18) and chop (−0.09…−0.18). Baselines also vary by regime (NQ best hiVol
  1.53/chop 1.49, worst trend 1.05; ES midVol dead zone −0.16, trend weak 0.21). Markets
  disagree on regime response too (NQ robust, ES conditional). Net: IDEA-0009's benefit is
  robust across measured regimes on NQ but fading in time (unexplained), and
  regime-conditional + hiVol/chop-negative on ES — still a cautious lead, not deployable.
- Kill test to preregister: primary metric MUST be drawdown-aware (Calmar or the prop
  trailing-DD from [[nq-noise-vwap-prop-challenge]]), NOT Sharpe — the whole question
  is whether the mean gain survives the drawdown cost. Sweep the delay (1–10 bars) as a
  searched selector; require the effect on a TRAIN/TEST split it was not tuned on;
  cluster-robust SE (per-trade t is only ≈2, not session-robust); and confirm it is not
  a fill/touch artifact (§6 embargo, next_open fills).
- Status: OPEN. Lower urgency — a small effect paid partly in drawdown; only promote if
  the drawdown-aware metric clears its gate.

## IDEA-0010 — Post-adverse-spike passive-fill scheduler (execution alpha) → HYP-0038

- Created: 2026-08-17
- Origin: transfer of the fast-alpha post-stop reversion (DIAG-fast-reversion) out
  of a directional overlay (dead — tiny, untimeable, drawdown-gated) into an
  EXECUTION decision. The retrace is real and path-informative; used to lean
  passive into the post-spike bounce it is monetised as basis-point fill savings
  that carry NO position risk and need not clear the standalone-alpha bar.
- Scope from DIAG Q1: entry=momentum (mean-in-the-tails) so a passive entry
  adversely selects; exit=reversion so passive-into-retrace is aligned. Scheduler
  is scoped to EXITS; the ENTRY arm is a built-in placebo (generic spread capture
  ⇒ artifact).
- Preregistered as **HYP-0038** with the touch-vs-fill guard, entry placebo, and
  fine-bar-coverage controls. Proof of concept on NQ/ES 1s; illiquid-instrument
  generalisation deferred (separate data pull).
- Status: PREREGISTERED, not run.

## IDEA-0011 — First-session noise-area velocity → day-ahead vol-target sizing → HYP-0039

- Created: 2026-08-17
- Origin: fast-scale info as an INPUT to a slower decision. The noise area is a
  validated dispersion object; its first-30-min expansion RATE is a causal read on
  the session vol regime, fed to SIZING (magnitude), never direction.
- Hard constraint ([[nq-post-lunch-opening-range-nogo]]): morning predicts RANGE
  not DIRECTION — sizing-only; a directional edge is a leak, made a preregistered
  kill condition.
- Preregistered as **HYP-0039**: mechanism gate first (OOS vol-forecast skill that
  ADDS over prior-session vol, LEARNINGS §3), then drawdown-aware Calmar at matched
  exposure. Cheapest to falsify (noise-area machinery + data already exist).
- Status: PREREGISTERED, not run.

## IDEA-0001 — Short causal noise lookbacks

- Created: 2026-07-18
- Observation: The paper's optimized winners all used 2-8 prior sessions rather than its 14/90-session baselines; this claim has not been isolated on NQ/ES.
- Proposed mechanism: A short strictly-prior same-time-of-day window may adapt the noise boundary faster to current intraday volatility and admit meaningful breaks sooner.
- Expected improvement: Higher zero-trade-day net-R Sharpe than the 90-session working baseline without reducing aggregate net R or relying on one lookback.
- Main artifact risk: High selection risk across lookbacks; short windows amplify estimation noise and regime dependence. Rerun the full family under Null C on a common sample.
- Motivating evidence: outputs/5095349_extracted.txt pp.10,16; paper Tables 9-11
- Status: rejected by `EXP-0008`; NQ ΔSharpe -0.065/p=0.8571, ES +0.026/p=0.1905

## IDEA-0002 — Fixed early-flat cutoff

- Created: 2026-07-18
- Observation: The paper exits 11-31 minutes before the equity close; successful ladder variants cluster at 30 minutes before close.
- Proposed mechanism: Avoiding thin or reversal-prone closing minutes may reduce giveback and gap-to-next-open exit risk.
- Expected improvement: Lower daily drawdown and non-negative net-R delta versus the same entries and stop logic.
- Main artifact risk: Likely market-specific to equity margin rules and may simply truncate NQ's winner tail; test a tiny prespecified cutoff family and report tail retention.
- Motivating evidence: outputs/5095349_extracted.txt pp.2,8,16
- Status: REJECTED by `EXP-0013` (HYP-0006). Cutoff family {15,30,45,60} min. NQ
  best cutoff 45 ΔSharpe +0.101 clears Sharpe but net R −0.8 (fails gate) and maxDD
  worse; ES sign opposite (all cutoffs hurt). NOT tail truncation (p90R preserved) —
  variance reshaping only. Forward-watch: recent-2023 NQ Sharpe 1.10→1.54. Preserve
  as negative evidence; retain ride-to-close.

## IDEA-0003 — Causal two-stage ATR ladder

- Created: 2026-07-18
- Observation: The paper reports its strongest in-sample QQQ results for two-stage partial-exit ladders, while this project has only tested a single partial TP plus runner.
- Proposed mechanism: Banking part of a mature move and ratcheting the remaining stop may reduce giveback while retaining the large-winner tail.
- Expected improvement: Sharpe and drawdown improvement beyond the validated tp0.75_67 operating point with at least 90% top-decile winner-R retention.
- Main artifact risk: Paper ladder levels are AUM-dependent, often unreachable, and path-sensitive; translate to entry-frozen ATR units, include the fill bar, and use adverse ambiguous-bar resolution or close-trigger/next-open fills.
- Motivating evidence: outputs/5095349_extracted.txt pp.5-8,13,16; STUDIES.md partial-TP section
- Review note (2026-07-18): the paper's own Table 8 shows the upper ladder TP is
  "not realistically reached" for 3 of 4 strategies, collapsing into a time exit,
  so the tested ladder must be genuinely reachable in ATR units. This project's
  one Null-C survivor so far is the single partial-TP `tp1.0_50` (bank 50% at
  +1 ATR, runner trails; real dSharpe +0.056 vs null -0.032, z+2.57); the
  two-stage ladder must beat that operating point, not just the baseline.
- Status: REJECTED by `EXP-0011` (HYP-0004). The paper Table-2 ladder (−1R/+2R →
  bank 50% → 0R/+5R, 1R = entry-frozen band distance) cut NQ gross R 111→97, lost
  −0.075 Sharpe vs `both` and −0.131 vs `tp1.0_50`, ES flat; Null C did not save
  it. The fixed levels discard the trailing stop's edge. Preserve as negative
  evidence; `tp1.0_50` remains the only validated partial-exit tweak.

## IDEA-0004 — Entry and exit band horizons separated

- Created: 2026-07-18
- Observation: The paper allows a narrower exit boundary than entry boundary, but its stated inequality and implementation parameterization are internally confusing.
- Proposed mechanism: A stable entry boundary paired with a faster exit boundary may respond sooner when continuation fails.
- Expected improvement: Higher net-R Sharpe with identical entries and no loss of aggregate net R.
- Main artifact risk: Substantial overlap with the project's failed stop-reference/buffer search; high machinery-amplifier and multiple-testing risk. Resolve the paper's sign convention before coding.
- Motivating evidence: outputs/5095349_extracted.txt pp.5,7-8; WFO.md Design B
- Review note (2026-07-18): paper 4.3/4.4 lets the exit boundary be NARROWER
  than the entry boundary (a faster give-up), parameterized as
  volatility_multiplier_exit = enter + exit_diff with exit_diff in [-1, 0]. The
  engine's `stop_ref="band"` + `stop_buf_atr` can approximate a tighter exit
  band; test a tiny prespecified exit-multiplier family, hold entries identical,
  and gate on a full-pipeline Null C (the earlier stop-buffer search failed this
  exact way, so expect a machinery amplifier).
- Status: REJECTED by `EXP-0012` (HYP-0005). Grid s∈{0.5,0.75} × y∈{0.5,1.0} of
  max(narrow noise band, VWAP−y·σ_vw) long / mirror short. Literal negative-y
  (tighter) rejected both markets; user-selected positive-y (looser): NQ best
  +0.090 Sharpe MISSED the +0.10 gate, ES best +0.320 but Null C mean +0.254
  (p=0.29). Same looser-stop/fewer-trades Sharpe artifact as EXP-0010. Preserve as
  negative evidence; the looser exit is a turnover/capacity lever only.

## IDEA-0005 — Futures-native causal sizing comparison

- Created: 2026-07-18
- Observation: The paper's returns rely on direction-specific equity margin and target-vol sizing that usually saturates available margin; those economics do not transfer to futures.
- Proposed mechanism: Causal strategy-vol or underlying-vol targeting with explicit contract floors may improve capital efficiency without changing signal alpha.
- Expected improvement: Lower daily/weekly tail risk and drawdown at matched long-run volatility; no alpha claim.
- Main artifact risk: Sizing can manufacture attractive CAGR or Sharpe through leverage, floors, or retrospective allocation. Preserve one-contract gross/net evidence and enforce causal portfolio accounting.
- Motivating evidence: outputs/5095349_extracted.txt pp.2,13-14; FORENSIC.md faithful sizing
- Status: untriaged

## IDEA-0006 — Paper bundle transport benchmark

- Created: 2026-07-18
- Observation: The paper publishes optimized QQQ parameter bundles but no untouched holdout or walk-forward evidence.
- Proposed mechanism: Treating each published bundle as externally chosen may provide a low-discretion transport test on NQ/ES, after translating equity-only sizing and exits.
- Expected improvement: At least one coherent strategy family transfers in sign across NQ and ES and beats its own full-pipeline Null C distribution.
- Main artifact risk: Not independent of the paper's in-sample search; cross-asset transport is exploratory, definitions differ, and exact ladder translation is ambiguous. Benchmark only, never confirmation.
- Motivating evidence: outputs/5095349_extracted.txt Tables 7,9-11
- Status: untriaged

## IDEA-0007 — Causal percentile-rank breakout strength with hysteresis

- Created: 2026-07-22
- Observation: TBD
- Proposed mechanism: TBD
- Expected improvement: TBD
- Main artifact risk: TBD
- Motivating evidence: None yet
- Status: untriaged
