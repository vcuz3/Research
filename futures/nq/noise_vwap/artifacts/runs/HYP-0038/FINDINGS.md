# HYP-0038 — Post-adverse-spike passive-fill scheduler (execution alpha) → NO-GO

Execution-layer experiment (not a signal/accounting change). Re-prices the
deployed clock book's ALREADY-DECIDED fills against the 1s tape to ask whether a
passive limit that leans into the post-stop retrace beats crossing at
`next_open`. Script: `scripts/hyp_0038_passive_fill.py`. NQ 1s
(`../data/NQ_1s_clean.parquet`, roll-stitched). TRAIN first 60% / TEST last 40%
of common sessions (2011-12-08 → 2026-07-14). Per-DAY cluster-robust SE.
Confirmatory a priori δ=0.25σ, g=0.10σ, K=5 (sweeps are discovery, rule 26).

## Verdict: NO-GO — the passive-exit saving is entirely touch-vs-fill

Kill test 1 and 2 FAIL, kill test 3 PASS. The apparent exit saving lives ONLY at
the non-capturable touch ceiling (g=0) and inverts to a **significant loss** once
a deployable vol-scaled trade-through guard is required. This is a fresh, clean
reproduction of LEARNINGS §6 (a passive level-retrace exit whose entire edge is
the touch-vs-fill assumption when the retrace target is also the reversal point).

## Coverage (not the cause)

1s tape coverage on TEST is excellent — median 299 sec per 5-min window,
frac≥30s = 1.000, frac==0 = 0.000 (TRAIN median 248 sec, same fracs). The NO-GO
is a genuine fill-economics result, not a fine-bar coverage artifact
(LEARNINGS §6 coverage caveat checked and cleared).

## Confirmatory triad (δ=0.25σ, g=0.10σ, K=5), TEST

Reported per LEARNINGS §6: **touch ceiling** (g=0, non-capturable upper bound) /
**guarded book** (deployable g=0.10σ) / **time-exit floor** (always chase, pure
timing, no spread). Improvement is side-signed `fs·(exec − ref)`, positive = a
better fill than crossing at `next_open`.

| arm | policy | mean tick | mean R | day-t | fill-rate |
|---|---|---|---|---|---|
| **EXIT** | touch (g=0) | +1.091 | +0.00021 | −0.35 | — |
| **EXIT** | **guard (g=0.10σ)** | **−2.869** | **−0.00346** | **−3.02** | 0.815 |
| **EXIT** | floor (chase) | +5.163 | +0.00506 | +0.06 | — |
| ENTRY (placebo) | touch (g=0) | −4.763 | −0.00455 | −3.60 | — |
| ENTRY (placebo) | guard (g=0.10σ) | −9.006 | −0.00850 | −5.50 | 0.743 |
| ENTRY (placebo) | floor (chase) | −6.265 | −0.00715 | −3.08 | — |

TRAIN shows the same shape (exit touch +0.282 → guard −0.656 tick, day-t −2.33).

## Kill tests (NQ TEST)

1. **Guarded EXIT improvement > 0 with day-t > 1.96 — FAIL.** −2.869 tick,
   day-t = −3.02. The deployable passive exit LOSES ~2.9 ticks/trade vs crossing,
   significantly.
2. **Effect persists at a deployable guard, not only g≈0 — FAIL.** Touch ceiling
   +1.091 tick (and even that is not significant, day-t −0.35) collapses to
   −2.869 tick under g=0.10σ. Textbook touch-vs-fill: the retrace level is where
   price reverses, so a touch is not a fill; requiring price to trade THROUGH the
   limit selects exactly the fills where it kept going (we'd have done better
   crossing). LEARNINGS §6 confirmed on a new instrument/context.
3. **Entry placebo does NOT beat the exit arm — PASS.** Entry guard −9.006 tick
   is worse than exit guard −2.869 tick, so the (negative) exit result is not
   generic spread capture. The entry arm's larger loss is the expected adverse
   selection (passive entries miss the deep breaks that run away, which ARE the
   edge — LEARNINGS §1/§4). Both arms lose net of chase; the exit merely loses
   less.

**VERDICT: FAIL → NO-GO.** Per the gated execution plan (rule 25 / gate-nullc),
the ES 1s clean build (kill test 5, transfer) was NOT spent — NQ failed kill
tests 1–3, so ES is moot.

## Discovery sweep confirms the artifact is uniform (TRAIN)

`discovery_NQ.csv`, all (δ,g,K) combos. The NO-GO is not a confirmatory-point
fluke — it holds across the whole searched space:

- **Every guarded (g>0) EXIT config is ≤ +0.276 tick** and all but one are
  negative; the single non-negative one (K=3, δ=0.50, g=0.10) is +0.276 tick at
  day-t = +0.03 — indistinguishable from zero.
- **Touch-ceiling (g=0) EXIT configs are small positives** (best +0.842 tick,
  K=3 δ=0.50, day-t +2.04) that all vanish or invert under any guard. The entire
  "saving" is the touch assumption.

## Interpretation

This is the third and cleanest death of the fast-alpha post-stop reversion
(DIAG EXP-0046/0047 → HYP-0038): (i) as a directional exit overlay it failed the
Sharpe bar (EXP-0047); (ii) re-cast as an execution saving that carries no
position risk — explicitly to sidestep that bar — it fails the more basic
touch-vs-fill test. The reversion is real, tiny, and untimeable: you cannot
harvest it passively (the guard kills it) and harvesting it by waiting (the floor
arm, +5.163 tick but day-t +0.06) just adds enormous variance AND reintroduces
the position risk the whole framing was meant to avoid. The retrace level is a
reversal point, so leaning a limit into it adversely selects its own fills.

Lever exhausted. No look-ahead: the limit price and fill decision use only the 1s
path strictly AFTER the exit-trigger bar; chase is an actually-traded 1s price at
window end (kill test 4 holds by construction).
