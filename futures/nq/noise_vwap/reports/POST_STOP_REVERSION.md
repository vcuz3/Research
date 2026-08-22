# Post-stop reversion — is there anything for a release rule to time? (EXPLORATION)

**Status: EXPLORATION / discovery (rule 26); verdict feeds a NO-GO.** Driver
`scripts/study_post_stop_reversion.py`; artifacts
`artifacts/explore/post_stop_reversion/{stops,curve}_{NQ,ES}.csv`.

> **CORRECTION (2026-08-16).** The first version of this report concluded "there is
> no exploitable post-stop reversion; the target does not exist." **That was an
> overstatement and it contradicted both the paper and this project's own confirmed
> `FAST_EXIT_REVERSION_EXPLORE.md` finding.** The short-term mean-reversion signal is
> REAL (see §Run-length reconciliation). Two errors caused the overstatement: (1) the
> study bucketed reversion by MAE *depth*, never by adverse-*run length* — the paper's
> actual axis — and pooled the run-length structure away; (2) the "negligible" reading
> confused *economically small in R units* with *nonexistent*. The corrected verdict:
> the reversion exists but is (a) tiny in tradable R units — the paper's own effect is
> ~0.002–0.004 R, its large t-stats are median-move-unit / large-N artifacts — and (b)
> its run-length *monotonicity* is **selected against at our stop location** (a run
> strong enough to break our band+VWAP stop is a continuation case; the reverting long
> runs revert before reaching the stop). **SECOND CORRECTION (same day):** a later
> claim in the earlier draft — that the blind fixed-delay Sharpe uplift over the base
> is an "exposure/variance amplifier" — is ALSO wrong. A Shapley decomposition of the
> +0.204 blind-wait dSharpe (§Decomposition) is **+117% MEAN effect** (better average
> exit P&L = captured reversion) and **−17% variance** (a small drag). So a blind
> ~4-bar stop-delay DOES harvest a small, real, cost-surviving post-stop reversion; the
> paper's *sign*-timed release does not beat it. The overlay NO-GO applies to the
> paper's SIGN mechanism, not to "reversion is unharvestable" — see the rewritten
> Verdict.

## Why this study exists

The EXP-0047 critique (2026-08-16) argued that "release the pending stop-exit when
the trailing-3m return flips sign" is too crude an instrument, and that the release
rule should be **derived from the post-stop reversion itself**. It also raised the
right structural point: **hitting a stop mechanically means price has just travelled
against us**, so some reversion is inherent to conditioning on an adverse extreme —
we must measure *how price reached the stop* and *what happened after*, and check it
against a same-size move that did **not** hit a stop.

So this decouples from the overlay P&L and measures the mechanism directly.

## Method

- Deployed baseline (continuous every-bar band/VWAP stop, next-open fills); keep only
  `reason=="stop"` exits (NQ 3,414; ES 3,599 over 3,628 sessions each).
- For each stop, reconstruct from 1-min RTH bars, **within the session only**:
  - **post-exit reversion** `rev[τ] = side·(close[i_det+τ] − open[i_det+1]) / ATR`.
    Anchored at the exit *fill* (open of the bar after detection), which is the
    LEARNINGS §6 paired one-bar embargo for free — the detection close is never the
    measurement anchor. Positive = price came back our way = we exited early.
  - **pre-stop path**: adverse-run length ending at detection, MAE over the hold, the
    trailing-h return (the "fast alpha") at detection for h∈{3,5}.
  - **sign-flip timing** `τ_flip`: bars after detection until `sgn(ret_h)==side` (the
    opposite-release trigger) and the reversion realized there.
- **Everything in R = ATR units.** (First pass in raw points was contaminated by NQ's
  ~10× multi-year scale drift — Rule 19 — which faked large means and near-zero
  t-stats. Normalising each trade by its session ATR fixed it.)
- **Magnitude+time-matched placebo**: over ALL RTH bars, the mean reversion (R) after a
  same-size adverse 3-bar move that did **not** trigger a stop, keyed by
  (time-of-day bin, `|trail3|/ATR` quintile). `excess = stop − placebo` isolates
  reversion *conditional on the stop event* from generic regression-to-the-mean.

## Result (MAE-depth view — see banner: this axis is why the first draft over-reached)

**Post-exit reversion is economically negligible and below a matched placebo.**

| | NQ | ES |
|---|---|---|
| peak reversion | **0.0042 R** (τ=30, curve ~flat) | **0.0042 R** (τ=9) |
| reversion at τ=5 | 0.0028 R | 0.0033 R |
| per-trade t (τ=3–6) | ~2.0–2.2 | ~2.1–2.8 |
| **session-clustered t** | **−0.6 to −4.5** | **−0.3 to −4.0** |
| median reversion (τ≤6) | ~0.003 R | **0.000 R** |
| frac reverting (>0) | 0.50–0.52 | 0.47–0.50 |
| **excess over placebo** | **negative every τ** (t −1.0 to −4.5) | **negative every τ** (t −1.2 to −4.2) |

Peak reversion is **≈0.004 R — under half a percent of a day's ATR**, i.e. a fraction
of a tick, gone in costs. Four independent reasons it is not a harvestable edge:

1. **It is near-symmetric.** Median reversion ≈ 0 and only ~50% of stops revert at all
   — a coin flip whether price comes back. The weakly-positive per-trade *mean* (t≈2)
   is a thin right tail, not a body.
2. **It is not robust to session clustering.** Per-trade the mean is weakly positive;
   equal-weighted **per session it is negative** (t up to −4.5). The sign flips with the
   weighting (LEARNINGS §4) — the positive average is concentrated in choppy multi-stop
   days; single-stop (trend) days *continue* after the stop. A deployable per-stop rule
   cannot rely on it.
3. **It is below a matched placebo — with a negative excess.** A same-size adverse move
   at the same time of day that did *not* hit our stop reverts **more** than one that
   did. So the stop event carries *negative* reversion information: our stop is
   (weakly, correctly) selecting genuine continuation/breakout moves — exactly what a
   breakout system's stop should do. There is no reversion-specific signal to exploit,
   and what little generic mean-reversion exists is better sampled *away* from our stops.
4. **It does not scale with the overshoot.** Bucketing by MAE, reversion is flat-to-
   *decreasing* in adverse-move size: NQ's largest-overshoot quintile (0.20 R) *continues*
   (−0.0006 R); ES's is flat (+0.0020 R, t −0.2). The one positive cell (ES quintile 2,
   +0.0124 R t 2.5) is a single searched cell of ten and not robust. **This kills a
   magnitude-triggered release** — bigger overshoots are real breakouts, not springs.

**Pre-stop path.** Stops are hit by *short, shallow* pokes, not long grinds: adverse-run
at the stop median **2 bars** (p90 4), MAE median **0.08 R** (p90 0.21). Consistent with
a well-placed noise-band stop being clipped by ordinary wiggles, after which the move is
as likely to continue as revert.

## Answers to the three specific questions

- **"Derive the release rule from the reversion, the 3m sign is too crude."** The
  reversion, measured directly and scale-free, is ~0.004 R, symmetric, and *below*
  placebo. No release rule — sign, magnitude, or a fixed peak-matched delay — can harvest
  it, because the target barely exists and is worse than a generic move. The crudeness of
  the sign was never the binding constraint; the **absence of exploitable post-stop
  reversion** is.
- **"`same≈opposite` on ES means price already reversed, recovering the loss."** Not
  supported. ES median reversion is **0.000 R** and only ~48–50% of stops revert.
  `same≈opposite` because the fast **sign carries no information** at a stop — the fast
  bar is noise, so inverting it changes nothing. The ~+0.09 Sharpe both arms showed in
  EXP-0047 is the generic delay/placebo-level wobble, not directional loss-recovery.
- **"ES has a different reversion half-life than NQ."** True in *shape*, immaterial in
  *size*. NQ's curve is essentially flat noise (~0.002–0.004 R, per-session negative);
  ES has a weak hump peaking ~6–9 min, decaying below half by ~25 min. Both peak at the
  same ≈0.004 R and both sit below placebo. The half-life differs; the magnitude is
  negligible on both.
- **The right-tail hypothesis (opposite-sign waits past a 2-min peak, p90=8).** The wait
  distribution is as described (τ_flip median 3 / p90 8 at h=3). But it is *not* the
  binding problem: on NQ there is no peak to overshoot (flat curve); on ES the peak is at
  τ=9 and the flip fires *before* it 94% of the time (P(τ_flip>9)=5.6% at h=3). The
  overlay does not fail because it waits too long past a reversion — it fails because
  **there is no material reversion to wait for.**

## What this resolves about EXP-0047

This **reaffirms the EXP-0047 NO-GO and corrects the mid-course critique of it.** The
critique worried that "structured fixed-delay (+0.204) ≫ random-delay (+0.075)" was
un-refuted reversion evidence the memo had dismissed. It is now refuted: there is no
material post-stop reversion on either market, so the structured-delay gain is **not**
reversion timing — it is the variance/exposure/path effect of a deterministic vs random
wait that the original memo named. The original call stands; my critique of it was the
thing that needed correcting. Checking was still correct — the user was right to demand
it — and the mechanism study, not the overlay P&L, is what settled it.

## Run-length reconciliation (added 2026-08-16, the correct axis)

Re-analysis of the stored per-trade data, bucketing reversion by adverse-**run length**
(the paper's axis) instead of MAE depth, and a matched all-bars measurement in the same
R units:

**All bars (the paper's population), R units — reversion is REAL and monotone in run:**

| run len | NQ r3 (t) | ES r3 (t) | ES r5 (t) |
|---|---|---|---|
| 1 | +0.0001 (0.8) | +0.0006 (6.0) | +0.0008 (6.3) |
| 2 | +0.0005 (3.6) | +0.0012 (7.2) | +0.0014 (6.3) |
| 3 | +0.0013 (5.5) | +0.0017 (6.1) | +0.0020 (5.4) |
| 4 | +0.0013 (3.7) | +0.0016 (3.5) | +0.0021 (3.5) |
| **≥5** | +0.0008 (1.8) | **+0.0039 (6.2)** | **+0.0036 (4.6)** |

This replicates the paper and `FAST_EXIT_REVERSION_EXPLORE.md`. The earlier report's
"+0.180 × median move, t 12.7" is, converted to R, only **0.0018 R (NQ) / 0.0025 R (ES)**
— the same order as everything here. **The impressive t-stats were sample size
(~600k bars) and median-move units, not a large per-event edge.** In tradable R units
the signal is ~0.002–0.004 R gross ≈ well under half a percent of daily ATR — sub-cost
as a standalone entry, which is exactly why the paper uses it only as a zero-cost
fill-timing overlay and calls it "unprofitable standalone."

**At our stops (the overlay's population) — the run-length monotonicity is GONE:**

| run len | NQ rev5 (t) | ES rev5 (t) | n(NQ) |
|---|---|---|---|
| 1 | +0.0066 (2.8) | +0.0019 (0.9) | 1117 |
| 2 | +0.0017 (0.7) | +0.0028 (1.1) | 1022 |
| 3 | +0.0022 (0.7) | +0.0026 (0.8) | 639 |
| 4 | −0.0025 (−0.5) | +0.0117 (2.5) | 323 |
| **≥5** | **−0.0009 (−0.2)** | **+0.0068 (1.0)** | 313 |

On NQ the long-run cells are flat-to-negative; ES has a noisy run-4 bump but run≥5 is
insignificant. **The trailing-move magnitude also fails to predict short-horizon
reversion at the stop:** `corr(|trail3|/ATR, rev5) ≈ 0` (NQ −0.03, ES +0.03). It weakly
predicts the *peak* 10-bar bounce (+0.15 NQ / +0.21 ES) — bigger displacement, bigger
available bounce — but that bounce is slower/noisier, so it washes out at a fixed short
horizon. Reversion in R is vol-neutral (`corr(ATR, rev5) ≈ 0`), confirming it is not a
volatility artifact; the weak ES trailing→rev5 tilt is partly a vol confound (it inverts
in the high-vol tercile). So there is no per-trade conditioner (run length, MAE depth, or
trailing size) that isolates which stops will bounce — the harvestable effect is a flat
pooled average, consistent with §Decomposition. **Selection is the mechanism:** the all-bars reverting long runs revert
*before* reaching a band+VWAP stop, so a run that actually breaks our stop is a
continuation-selected sample. Stop-conditioning strips out precisely the reverting tail
the paper's effect lives in. This is the correct, precise reason the exit overlay fails
— replacing the earlier draft's incorrect "no reversion exists."

## Decomposition — is the blind-wait Sharpe uplift reversion or exposure? (added 2026-08-16)

The EXP-0047 kill test showed a **blind fixed 4-bar stop-delay** scoring dSharpe +0.204
on NQ TEST, *above* the paper's sign-timed release (+0.135). The earlier draft dismissed
this gap as an exposure/variance amplifier (a "looser effective stop"). To test that
directly I decomposed each arm's daily-Sharpe change vs the baseline into a MEAN effect
(daily-mean P&L change) and a VARIANCE effect (daily-std change), Shapley-symmetric so
the two sum to the exact dSharpe. NQ TEST (2020-2026), 1732 baseline stops:

| arm | net R | meanR/trade | Sharpe | dSharpe | = MEAN | + VAR |
|---|---|---|---|---|---|---|
| baseline | +35.78 | +0.02066 | 1.3224 | 0.000 | — | — |
| paper sign-timed | +40.67 | +0.02367 | 1.4571 | +0.135 | +0.178 (+132%) | −0.043 (−32%) |
| **blind fixed 4-bar** | **+42.35** | **+0.02477** | **1.5268** | **+0.204** | **+0.240 (+117%)** | −0.035 (−17%) |

**The uplift is overwhelmingly a MEAN effect** — the daily-std actually *rises* slightly
(variance is a drag, not the source). The blind wait lifts net P&L by +6.57 R over the
~6-year TEST era (+0.0041 R/trade after costs), matching the ~0.003–0.004 R pooled
post-stop reversion measured scale-free above. So "it's exposure, not reversion" was
wrong: **waiting a few bars captures real reversion**, and it captures *more* of it than
the paper's sign rule (+0.0041 vs +0.0030 R/trade). The reconciliation with the flat
run-length table: the pooled post-stop reversion is small-positive and dominated by the
*short*-run stops (NQ run=1, n=1117, rev5 +0.0066) — there is no run-length *structure*
to key on (that is selected out), but there is a flat pooled bounce a dumb delay harvests.

**But the mean gain is partly paid in tail risk.** The blind wait converts many small
losses into small wins (win rate 26.8% → 38.1%), yet when price does *not* bounce the
loss is larger, and drawdown worsens:

| | maxDD (R) | worst trade p01 | p05 | meanLoss/trade | Sortino |
|---|---|---|---|---|---|
| baseline | 4.70 | −0.326 | −0.220 | −0.0885 | 1.669 |
| blind fixed 4-bar | **5.73** | −0.380 | −0.255 | −0.1111 | 1.870 |

At delay 4 max drawdown rises +22% and the per-trade left tail fattens. **But a
delay sweep (1–8 bars, `scripts/sweep_fixed_delay.py`) shows the +22% maxDD is
DELAY-4-SPECIFIC, not intrinsic** — NQ maxDD is non-monotone across delays and is
actually *better* than baseline at delay 6 (4.20 vs 4.70). So the drawdown cost is noisy,
not a law of delaying; the durable tail cost is the fatter per-trade left loss from
holding losers longer.

**The delay sweep also corrects two earlier claims:**
- **The P&L-optimal delay is NOT ~2 bars.** On NQ dSharpe rises to a plateau at **5–6
  bars** (delay 6 +0.249; delays 3–8 all +0.16…+0.25, all far above the random-null mean
  +0.075). The earlier "reversion done by minute 2" was about reversion *magnitude*
  front-loading (`FAST_EXIT_REVERSION_EXPLORE.md` Study 1) — a different object from the
  optimal exit delay, which trades bounce-capture against continuation risk and peaks
  later. NQ delay robustness *strengthens* the real-reversion reading on NQ.
- **NQ and ES disagree on the optimal delay.** ES peaks early (delay 1–3, +0.08…+0.09)
  and *decays* (delay 4 +0.001, delay 8 −0.04). So EXP-0047's calibrated `fixed_delay=4`
  is near-NQ-optimal but ES's WORST delay — part of why the ES fixed arm looked dead. The
  markets wanting different delays is the same sibling-disagreement signature that killed
  the overlay, and it caps confidence in a single robust rule.

**By-year the gain is fading in the recent era.** NQ delay-4 beats baseline clearly in
2020/2022/2023/2024 but HURTS in 2025 (0.44 vs 0.59) and 2026 (−1.16 vs −0.87); ES
similar. The "recent 2023+ positive" (Sharpe 1.095→1.204) was carried by 2023–2024; the
two most recent years are negative. A genuine degradation warning, not a clean recent
confirmation.

## Verdict

**Two distinct claims, do not conflate them:**

1. **The paper's fast-alpha SIGN mechanism for the stop-exit: NO-GO (stands).** A *blind*
   fixed ~4-bar delay dominates the sign-timed release on Sharpe (+0.204 vs +0.135),
   Sortino, net R and worst-day, and on ES the inverted `same` arm ties the real arm.
   The fast trailing-return *sign* carries no useful exit-timing information — "just wait
   a few bars" beats "wait for a favourable fast bar." This is the correct, precise
   EXP-0047 NO-GO.

2. **A blind fixed short stop-delay is a small, real, cost-surviving reversion capture —
   NOT nothing, and NOT exposure.** The decomposition proves it is ~100% a mean/reversion
   effect (+0.0041 R/trade net, +6.6 R over TEST, +0.20 Sharpe/Sortino, stable in the
   recent era). It is marginal (per-trade t≈2, not session-cluster-robust) and it works
   by *weakening the stop*, so it buys a higher win rate with a fatter left tail and +22%
   max drawdown. On a pure Sharpe/Sortino objective it is a small positive; on a
   drawdown-constrained objective it is likely net-negative. Its status is therefore
   **an honest OPEN question, not a closed NO-GO** — it needs its own preregistered test
   (primary metric = drawdown-aware, e.g. Calmar or the prop trailing-DD, not Sharpe)
   before any claim.

Earlier over-compressions now retracted: "no reversion exists" (§banner), and "the
blind-wait gap is exposure/variance" (this §). Preserve as negative + partial-positive
evidence (rule 25). IDEA-0008 (run-length-*conditioned* exit) is weak on the STOP
population — the run-length structure is selected out — but the flat pooled bounce that
a blind delay harvests is the live, drawdown-gated lead worth a narrow preregistered
follow-up.
