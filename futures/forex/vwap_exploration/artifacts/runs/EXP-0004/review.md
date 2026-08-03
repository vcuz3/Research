# EXP-0004 Results Discussion

- Hypothesis: `HYP-0004` — Finding C's liquidity-block shape survives a volatility-matched split
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review
- Primary metric: volatility-stratified `asia` − `overlap` per-bet contrast (pips)
  for the `vwap` anchor at H=30, session block-bootstrap 95% CI, both products
- Kill test: REJECT if `C_adj <= 0` or `C_adj < 0.50·C_raw` on either product;
  UPGRADE to confirmed only if the CI also excludes zero on at least one product
  and the cells' volatility ratio moved materially toward 1 on both
- Command: `python -u -m futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks`
- Artifacts: `volstrat_6E.txt`, `volstrat_6B.txt`

## Result versus hypothesis

**Finding C is NOT a volatility artifact.** The reject gate is cleared on both
products; on 6E the contrast is essentially *unchanged* by the control.

| arm | 6E | 6B |
|---|---|---|
| 1. sign `C_adj > 0` | **PASS** +0.5657 | **PASS** +0.2210 |
| 2. magnitude `C_adj >= 0.50·C_raw` | **PASS** (107% retained) | **PASS** (58.5%) |
| 3. significance, CI excludes 0 | **PASS** [+0.2302, +0.8952] | FAIL [−0.4120, +0.8096] |
| 4. control worked (vol ratio → 1, `n_eff` ≥ 50%) | **PASS** | **PASS** |

Arm 3 required a CI excluding zero on *at least one* product, so by the
preregistered rule the finding is upgraded. The honest scope of that upgrade is
narrower than the arm table suggests and is set out under "Builder
interpretation".

This is the opposite outcome to the run that motivated it. LEARNINGS 2026-07-31c
collapsed a comparable slot-matched contrast from +0.0496 to −0.0047 under
exactly this control. Here the analogous number goes **+0.5300 → +0.5657**.

**Rule 23 reproduction.** The unadjusted block table reproduces finding C
exactly: 6E `vwap` `asia` +0.2883 (t +5.18) and `overlap` −0.2823 (t −1.88)
against FINDINGS §C's +0.288 / −0.282 (t +5.18 / −1.88); 6B `overlap` −0.2998
(t −1.81) against −0.300 (t −1.81). Four-decimal agreement, so the adjusted arm
is being compared against the right baseline.

## Gross, net, baseline, and null comparison

No null was spent, per the project gate (a null is bought only once a real pass
clears its primary metric; this run can only remove a claim, never create one).

The confound is real and large before it is removed — mean `rv_60` runs
0.86 → 1.89 pip/min across the blocks on 6E (2.21x) and 1.11 → 2.21 on 6B
(1.99x) — so the control had something substantial to remove and demonstrably
removed it (asia/overlap volatility ratio 0.453 → 0.904 on 6E, 0.523 → 0.998 on
6B) while retaining 65.0% / 59.7% of the effective bet count. That pairing is the
evidence that the split was matched, not merely weakened; without it the
non-collapse would be uninterpretable in the same way a collapse would be.

**This does not disturb the NO-GO (finding B1), and arguably reinforces it.** The
largest cell in the whole run is 6E `asia` at the top volatility quintile,
+0.7797 pip/bet against `overlap`'s −0.7555. `asia` is also the block with the
*worst* liquidity and therefore the widest quoted spread, so the gross edge is
biggest exactly where the cost floor is highest. Pooled `asia` gross of +0.2883
pip/bet still sits ~3.5x under the most optimistic post-2016 6E round trip of
1.0 pip, before any Asia-hours spread widening is priced.

## Regimes, sensitivity, and alternative explanations

**Robustness surface (18 declared cells per product, none selected on).** `adj/raw`
across 3 volatility measures × 3 stratum counts × 2 anchors:

- 6E: **+0.97 to +1.16** in all 9 `vwap`+`past30` × `rv_60`/`rv_lag_60` cells and
  all 9 loose-floor cells. The contrast is invariant to the control.
- 6B: **+0.55 to +0.95** for `vwap`. The point estimate erodes but never inverts
  and never falls below the 0.50 gate.

The volatility ratio moves monotonically toward 1 as strata refine (3 → 10 bins:
0.831 → 0.957 on 6E), and `C_adj` is flat over that range, which is the signature
of a contrast that does not live in the confounder.

**The mirror arm is the most informative result, and the two products disagree.**
Volatility contrast (q5 − q1), raw versus standardised within blocks:

| | raw | within-block | reading |
|---|---|---|---|
| 6E | −0.3455 | **+0.1332** | volatility dies (and flips) once block is fixed |
| 6B | −0.3439 | **−0.5370** | volatility *strengthens* once block is fixed |

On 6E the declared reading "block survives and volatility dies ⇒ H_micro
supported" fires cleanly. On 6B the opposite label survives: within three of four
blocks, high-volatility decisions are markedly worse (`asia` −1.5723 vs +0.0813;
`overlap` −0.7636 vs +0.0946; `ny_pm` −0.1856 vs +0.1810), and it is the *block*
contrast that is insignificant there. So the two products agree that the block
contrast is not *caused* by volatility, and disagree about which label carries
the information. Cross-product agreement holds at the level of the kill test and
fails at the level of the mechanism.

**Block-free view.** Across the 43 decision slots with ≥100 bets, Spearman(mean
`rv_60`, mean per-bet pip) = **−0.4305 (6E) / −0.1711 (6B)**. The unconditional
cross-slot gradient does point the way H_vol predicts on both products — which is
precisely why the pooled block table on its own could not settle the question,
and why the within-stratum arm was needed.

**The `past30` dissociation is 6B-only and does not replicate on 6E.** This is a
correction to finding C's second half, which is currently stated in FINDINGS §C
without a product qualifier ("Anchor displacement and short-horizon reversal have
opposite time-of-day profiles on FX futures"):

| | `vwap` C_adj | `past30` C_adj | opposite? |
|---|---|---|---|
| 6E | +0.5657 | **+0.5336** | **no** — near-identical |
| 6B | +0.2210 | −0.1352 | yes |

On 6E the no-anchor arm has the *same* block profile as the anchor, both raw
(`asia` +0.3181 / `overlap` −0.1841) and adjusted. The generalising sentence in
FINDINGS §C is not supported and must be narrowed to 6B.

**Rule-9a defect found inside the control itself, sized, and shown not to
matter.** `rv_60` requires both minutes of each one-minute change, so pairwise
coverage is roughly the square of per-minute coverage; on 6B's thin Asia hours
that lands near the 0.5 floor and deletes **29.7% of `asia` decisions against
0.1% of `overlap`** (across-block spread 0.296). This is finding G reappearing on
a new statistic, and it is *selective in the worst possible way* — it removes the
quietest decisions of the thinnest block, i.e. one tail of the very variable
being conditioned on. The sensitivity arm (`rv_60_loose`, identical statistic at
a 0.25 floor, spread 0.296 → 0.150) moves 6B's `C_adj` only +0.2210 → +0.2491 and
6E's +0.5657 → +0.5751. The coverage rule is not driving the answer. Coverage
cannot be made uniform on 6B — ~12% of Asia decisions have too few traded minutes
in the trailing hour at any floor — which is genuine illiquidity, consistent with
finding G's conclusion that 6B's Asia gaps are not a download artifact.

## Artifact and implementation risks

- **Full-sample quantile strata.** The bins are two-sided. Declared and accepted
  before the run: the estimand is a descriptive contrast and no position is taken
  on the basis of a bin, so rule 8 (which governs what was *tradable*) is not
  engaged. A causal expanding quantile would make bin membership era-dependent
  and is the wrong instrument for a stratification.
- **Bootstrap holds the bin edges fixed** so that resampling perturbs the data and
  not the stratification; pinned by
  `tests/test_core.py::quantile_bins reuses supplied edges`.
- **Common support is enforced, not assumed.** The harmonic weight is zero
  wherever either cell has fewer than 30 bets, so no stratum is extrapolated
  into; `n_eff` reports the shortfall (65.0% / 59.7%). The three new
  `stratified_contrast` invariants pin that the helper kills a pure confound,
  preserves a real within-stratum effect, and collapses `n_eff` to zero under
  disjoint support.
- **No shared print.** `rv_60` ends at `close(m)`; the entry price is `open(m+1)`.
  `rv_lag_60` additionally shares no minute with the `past_30` signal window, and
  gives the same answer, so the `past30` arm is not attenuated by conditioning on
  its own inputs.
- **Off-by-one in the `diff` window slices** is the main implementation risk and
  is pinned against a hand-computed ramp in
  `tests/test_core.py::realized_vol windows are causal`.
- 20/20 core checks pass (15 prior + 5 new).

## Builder interpretation

The control that was supposed to be able to kill finding C did not kill it, and
on 6E did not even dent it. Three separate things follow, and they should not be
run together:

1. **The narrow claim is confirmed on 6E and directionally supported on 6B:** the
   `asia` − `overlap` contrast in anchor-displacement reversion is not a
   restatement of the intraday volatility profile. On 6E it is *stronger* after
   matching, with a CI excluding zero and invariance across every robustness cell.
2. **The mechanism attribution is confirmed on 6E only.** 6E's mirror arm says
   block carries the information and volatility does not; 6B's says the reverse,
   and 6B's block contrast is underpowered (CI [−0.41, +0.81]). The transitory
   inventory account earns 6E; it has not earned GBP.
3. **Finding C's dissociation half is withdrawn as a general claim** and narrowed
   to 6B, where the run confirms it. On 6E `past30` and `vwap` have the same block
   profile before and after the control.

Nothing here changes the project verdict. The VWAP framing is still withdrawn
(finding B: the no-anchor arm beats every anchor pooled on both products, and on
6E it also matches the anchor block-by-block), and the effect is still an order
of magnitude below cost in the block where it is largest.

The residual worth recording is that this is the first time in this workspace the
volatility-matched split has been run and the contrast has *survived*. That is
what makes the LEARNINGS 2026-07-31c entry more useful, not less: the control
discriminates, rather than collapsing everything it touches.

## Independent review

- Review status: reviewed by the builder; no second model was available this
  session, so this is self-review and is labelled as such rather than presented
  as independent.
- Objections raised and resolved:
  - *"The kill test's arm 3 needed only one product — isn't the upgrade
    over-claimed?"* Partly, which is why the verdict is split by product above
    rather than stated once. The arm as written is met; the interpretation is
    restricted to what each product's evidence supports.
  - *"The rule-9a coverage flag on 6B could be manufacturing the non-collapse."*
    Tested rather than argued: the loose-floor arm moves `C_adj` by +0.03 pip.
  - *"Both products' cross-slot correlations are negative, which is the H_vol
    direction."* Recorded above. It is the unconditional view and is exactly what
    the within-stratum arm was built to condition on; it is reported because it
    is the strongest single piece of evidence *against* the run's conclusion.
- Verdict: **NOT REJECTED.** Finding C upgraded to confirmed on 6E, held
  provisional on 6B; its dissociation half narrowed to 6B.

## Promotion decision

- `reports/FINDINGS.md`: **yes** — §C rewritten (status, product scope, the
  dissociation correction, the mirror-arm disagreement); status table updated.
- `MEMORY.md`: **yes** — finding C moves out of "Provisional hypotheses"; the
  IDEA-0004 blocker is cleared.
- Shared `LEARNINGS.md`: **not yet.** The reusable observation ("the
  volatility-matched split discriminates — it does not always collapse the
  contrast, and the mirror arm can name a *different* winner on two correlated
  products") is single-project and belongs in the existing 2026-07-31c entry as a
  counter-example only after it is seen once more elsewhere. Recorded here and in
  `MEMORY.md` under promotion candidates.
