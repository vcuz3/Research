# EXP-0047 Results Discussion

- Hypothesis: `HYP-0035` — Exit-only fast-alpha overlay at a fixed short horizon
- Status: completed — **REJECT / NO-GO**. On the held-out TEST era the exit-timing
  uplift does NOT beat a blind fixed delay (NQ) or a random delay (NQ frac 0.100),
  and the fast sign carries no information on ES (inverted `same` ties the real arm).
  The capturable part is a generic exit-DELAY / looser-effective-stop (exposure
  amplifier), not fast-alpha reversion timing.
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: zero-trade-day daily net-ATR-R Sharpe uplift (dSharpe) of the
  exit-only overlay over the frozen baseline, NQ TEST era (primary), ES TEST transfer.
- Kill test: pick h* in {1,2,3} on NQ TRAIN only; freeze; REJECT unless on NQ TEST
  dSharpe>=+0.10 AND netR not fall; beats random-release null (frac<0.05) at matched
  trade count; beats fixed-delay; inverted `same` not as good; survives next_open.

## Result versus hypothesis

The 2026-08-16 exploration found the exit-only overlay positive at every 1–10 min
horizon on the FULL sample and read the EXP-0046 NQ +0.025 at h=5 as a local dip.
This confirmatory run split NQ into TRAIN (first 60%, 2011-12-08 → 2020-09-14, 2177
sessions) and TEST (last 40%, 2020-09-15 → 2026-07-14, 1451 sessions), selected the
horizon on TRAIN only, froze it, and ran the full control battery on TEST.

**Horizon selection (NQ TRAIN, exit-only dSharpe):** h1 +0.042, h2 +0.036, **h3
+0.077** → `h* = 3 min` frozen.

**NQ TEST-era arm grid (h*=3):**

| arm | n | gross pt/t | sumR | Sharpe | dSharpe |
|---|---|---|---|---|---|
| baseline | 1732 | 5.601 | — | 1.322 | 0.000 |
| **opposite (real)** | 1718 | 6.522 | +4.88 | 1.457 | **+0.135** |
| same (inverted) | 1726 | 5.650 | +0.03 | 1.311 | −0.012 |
| **fixed (blind delay)** | 1710 | 6.560 | +6.57 | 1.527 | **+0.204** |
| random (matched n) | 1716 | 6.105 | +2.93 | 1.403 | +0.081 |

- **Real gate PASSES in isolation** (dSharpe +0.135 ≥ +0.10, net R +4.88 up) — the
  overlay does lift TEST-era Sharpe. But that is not the deployable question.
- **It FAILS `beats_fixed`:** a *blind* fixed 4-bar exit delay scores **+0.204**,
  clearly ABOVE the real bounce-timing arm (+0.135). Waiting a fixed few bars beats
  waiting for a favourable fast bar.
- **It FAILS `beats_random`:** the random-release null (200 draws, matched trade
  count 1718 vs mean 1719) has mean +0.075, sd 0.048, and **frac(random ≥ real) =
  0.100** — the real arm is ~1.2 sd above a random delay, nowhere near the <0.05 bar.
- It PASSES `beats_same` (real +0.135 > inverted −0.012) and `survives_next_open`
  (next_open +0.135 ≈ signal_close +0.143 — not fill-sensitive on NQ).

**KILL TEST: `{real_gate:T, beats_random:F, beats_fixed:F, beats_same:T,
survives_next_open:T}` → REJECT** (the two decisive controls fail). Null C is
skipped per the standing gate rule.

## ES transfer (sibling-market mechanism test)

ES TEST era (1451 sessions, h*=3, arms only — the expensive 200-draw null was not
spent on an already-rejected candidate):

| arm | n | Sharpe | dSharpe |
|---|---|---|---|
| baseline | 1699 | 1.070 | 0.000 |
| opposite (real) | 1683 | 1.159 | +0.089 |
| **same (inverted)** | 1687 | 1.162 | **+0.092** |
| fixed | 1674 | 1.071 | +0.001 |
| random | 1681 | 1.133 | +0.063 |

**On ES the inverted `same` arm (+0.092) TIES/beats the real `opposite` arm
(+0.089), and both are below the +0.10 gate.** So the fast sign carries essentially
no exit-timing information on the recent ES era — waiting for an *adverse* bar to
exit is as good as waiting for a favourable bounce. This is the sharpest possible
statement of the mechanism failure: `opposite ≈ same` means direction is irrelevant;
only the *delay* matters.

## Gross, net, baseline, and null comparison

The two markets tell one story. The exit overlay's TEST-era Sharpe lift is real in
magnitude (NQ +0.135, ES +0.089) but **is not attributable to the fast-alpha
reversion timing**:

- a **blind fixed delay** reproduces (NQ) or exceeds it;
- a **random delay** matches it 10% of the time at matched exposure (NQ);
- the **inverted sign** ties it (ES).

The capturable effect is therefore a generic "don't liquidate instantly, hold a few
more bars" — i.e. a slightly **looser effective stop**. That is the same
variance/selectivity amplifier already documented for this book: EXP-0010 (base VWAP
stop, positive null-uplift mean on both markets), EXP-0046 (the bundled overlay's
quality-not-alpha exposure tradeoff), and the FX random-exit equivalence
(`fx-mandatory-stop-and-random-exit-control`). It raises per-trade gross (NQ 5.60 →
6.52 pt/t) with ~1% fewer trades, but that is a turnover/exposure lever, not exit
information.

## Regimes, sensitivity, and alternative explanations

- **Why EXP-0046 saw "beats random frac 0.000" and this run sees 0.100.** That
  earlier decisive result was the *bundled* overlay measured on the FULL sample at
  h=5. Here, on the *recent* TEST era, exit-only at h=3, the fast alpha no longer
  beats a blind/random wait. The reversion-timing information is concentrated in the
  earlier era (consistent with the known recent-era degradation of the ES exit leg in
  EXP-0046) and does not survive out-of-era. The full-sample exploration lead
  (+0.08–0.10 at short horizons) was a searched, era-pooled artifact of this.
- **Not a fill artifact** (LEARNINGS §6): NQ next_open +0.135 ≈ signal_close +0.143,
  ES next_open +0.089 ≈ signal_close +0.119 — the small gap is the wrong direction to
  rescue it.
- The TRAIN/TEST split behaved as designed: h* was chosen on 2011–2020 with no TEST
  leakage, and the controls — not a favorable slice — killed it.

## Artifact and implementation risks

- Default-off bit-exact parity asserted under both fill modes (rule 23).
- All fills next-open (rule 1/2); the fast bar's own close is never credited.
- Random-release control non-degenerate (sd 0.048, n ∈ [1709, 1725]) and matched to
  the real trade count — a real null, not an sd=0 pseudo-null.
- Coverage clean: exit-only drops are negligible (~1% fewer trades), mean exit delay
  4 bars.

## Builder interpretation

A clean, well-designed NO-GO that closes the EXP-0046 exit-only lead. The confirmatory
discipline earned its keep: the full-sample exploration made the exit overlay look
like a ~+0.10 edge at short horizons, but once the horizon was frozen on a train era
and the effect was measured out-of-era against its own controls, the reversion-timing
attribution collapsed — a blind fixed delay does it better on NQ, a random delay
matches it, and on ES the sign is irrelevant. The residual Sharpe lift is a looser
effective stop (an exposure/variance amplifier), which this project has repeatedly
ruled a turnover lever rather than alpha. Combined with EXP-0046, the fast-alpha
paper's exit overlay is fully retired on this book: the bundled overlay is a NO-GO
(entry leg harmful), and the exit leg — its one positive component — does not survive
its own controls out-of-era.

## Addendum (2026-08-16) — mechanism study REAFFIRMS this NO-GO

A post-review critique argued the conclusion over-reached: that "reversion is not
monetizable" was too strong, because the *structured* fixed 4-bar delay (+0.204)
sits ~2.7 sd above the random-delay null (+0.075), which looks like un-refuted
evidence for a real short-horizon post-stop reversion the memo dismissed. So I
measured the post-stop reversion directly and scale-free (R = ATR units), decoupled
from the overlay P&L — `reports/POST_STOP_REVERSION.md`,
`scripts/study_post_stop_reversion.py`, on NQ (3,414 stops) and ES (3,599).

Result (CORRECTED same day — the first pass over-stated this as "no reversion
exists," which contradicted the paper and `FAST_EXIT_REVERSION_EXPLORE.md`; fixed by
re-analyzing on the adverse-RUN-LENGTH axis instead of MAE depth): short-term mean
reversion IS real and monotone in run length on all bars (ES run≥5 +0.0039 R, t 6.2;
NQ runs 2–4 t 3–5.5), replicating the paper — but it is TINY in tradable R units
(the earlier "+0.180×med_move, t 12.7" = only 0.0018 R NQ / 0.0025 R ES; the huge t
was sample size + median-move units), so ~0.003 R gross is sub-cost standalone.
Critically, **at our stops the run-length monotonicity is GONE** (NQ run≥5 rev5 ≈ 0;
ES insignificant): a run strong enough to break the band+VWAP stop is a continuation-
selected case, so stop-conditioning strips out the reverting long-run *structure*. **The
paper's SIGN NO-GO stands** — but not because reversion is absent.

## Addendum 2 (2026-08-16) — the blind-wait uplift is MEAN/reversion, not exposure

The Addendum-1 parenthetical "the fixed>random gap is exposure/variance" is **retracted
— it was asserted, not measured, and it is wrong.** A Shapley decomposition of the
blind fixed 4-bar delay's +0.204 NQ-TEST dSharpe vs base (`POST_STOP_REVERSION.md`
§Decomposition) is **+117% MEAN effect / −17% variance** (daily std actually rises). The
blind wait captures a real, small, cost-surviving post-stop reversion — +0.0041 R/trade
net, +6.6 R over the TEST era — and *more* of it than the paper's sign-timed release
(+0.0030 R/trade). So the two claims must be separated:

1. **Paper's fast-alpha SIGN mechanism = NO-GO (this run's real result, stands):** a
   *blind* delay dominates the sign-timed arm (Sharpe +0.204 vs +0.135, and Sortino,
   netR, worst-day), and on ES `same`≈`opposite`. The trailing-return sign carries no
   exit-timing information.
2. **A blind fixed short stop-delay is a small REAL reversion capture, not exposure** —
   but it weakens the stop: win rate 26.8%→38.1%, yet maxDD +22% (4.70→5.73 R) and a
   fatter per-trade left tail (meanLoss −0.089→−0.111, p01 −0.326→−0.380). Sharpe/Sortino
   improve; a drawdown-constrained (prop) objective likely does not. Recent 2023+ the
   gain persists but is small (Sharpe 1.095→1.204).

**Consequence for this run's scope:** EXP-0047 correctly REJECTS the paper's sign
overlay, but it does NOT close the broader "delay the stop a few bars to capture
post-stop reversion" question — that is a small, real, drawdown-gated OPEN lead needing
its own preregistered test with a **drawdown-aware primary metric** (Calmar / prop
trailing-DD, not Sharpe). Method lesson (→ shared candidate): before labelling a Sharpe
uplift "exposure not signal," decompose it into mean vs variance rather than asserting
the mechanism; and read maxDD + the per-trade tail, not only Sharpe/Sortino, when a
change raises win rate by loosening a stop (rule 22).

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: add as a NO-GO closing the EXP-0046 exit-only lead; the
  key artifact is `beats_fixed=False` + `beats_random` frac 0.100 (NQ) and
  `opposite ≈ same` (ES) on the held-out era.
- `reports/FAST_EXIT_REVERSION_EXPLORE.md`: mark IDEA-0007 rejected by EXP-0047.
- `MEMORY.md`: append the NO-GO; retire the exit-only lead. IDEA-0008 (run-length
  conditioning) remains open but is now lower-prior given the exit-timing mechanism
  failed its controls.
- Shared `LEARNINGS.md`: not eligible without cross-project verification, but this is
  a second, independent instance (after EXP-0046) of "an exit-timing overlay's Sharpe
  lift is a blind-delay/exposure effect, not timing information" — strengthens the
  provisional candidate in `nq-fast-alpha-overlay-nogo`.
