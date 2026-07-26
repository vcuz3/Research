# EXP-0009 Results Discussion

- Hypothesis: `HYP-0006` — Normalising VEI by its trailing same-slot mean gives a
  threshold that means what it says, at no information cost
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: two co-primary — (1) per-slot selection-rate spread at a matched global
  rate; (2) the count-weighted within-slot momentum contrast, plus the pooled contrast,
  both markets
- Kill test: see `experiments/hypotheses/HYP-0006.md`

## Result versus hypothesis

**Kill test 1 did NOT fire. Kill test 2 is the outcome: calibration is fixed at no
information cost.** The normalisation is adopted as the regime label.

### Co-primary 1 — CALIBRATION (per-slot selection rate at matched global rate)

| feature | spread NQ / ES | CV NQ / ES |
| --- | --- | --- |
| `raw` | **0.1690 / 0.1981** | **0.933 / 0.882** |
| `rel` = VEI / mu_slot | 0.0293 / 0.0307 | 0.135 / 0.105 |
| `z` = (VEI − mu)/sd | **0.0115 / 0.0121** | **0.050 / 0.041** |
| `pct` (ordinal) | 0.0093 / 0.0088 | 0.039 / 0.031 |

The defect is confirmed at full size and is identical on both markets: at `VEI > 1.10`
the raw feature selects **1.5% of the 10:30 slot and 18.4% of the 15:30 slot** (NQ; ES
2.6% → 22.4%). It is a time-of-day selector, not a volatility selector. Every
normalisation collapses that to near-uniform. This half of the result is mechanical by
construction, as HYP-0006 stated in advance — it is reported to size the fix, not as a
discriminating test.

The informative detail is that **`rel` is ~2.5× worse-calibrated than `z`** on both
markets. That is the location-vs-scale distinction the unit test predicted: dividing by
the trailing same-slot mean removes the per-slot LEVEL but not the per-slot DISPERSION,
so a residual imbalance survives. Empirically, then, **VEI's per-slot dispersion is not
proportional to its per-slot level** — worth knowing, and the reason both variants were
carried rather than one.

### Co-primary 2 — INFORMATION (momentum contrast at matched selection rate)

| feature | within-slot NQ | within-slot ES | pooled NQ | pooled ES |
| --- | --- | --- | --- | --- |
| `raw` | +0.0748 [−0.0002, +0.1352] | +0.0781 [−0.0040, +0.1442] | +0.0647 [−0.0097, +0.1443] | +0.0633 [−0.0119, +0.1405] |
| `rel` | +0.0659 [−0.0154, +0.1277] | +0.0722 [−0.0019, +0.1368] | +0.0711 [−0.0042, +0.1452] | +0.0754 [+0.0017, +0.1556] |
| **`z`** | **+0.0959 [+0.0187, +0.1544]** | **+0.0784 [+0.0052, +0.1377]** | **+0.0930 [+0.0096, +0.1680]** | **+0.0869 [+0.0046, +0.1638]** |
| `pct` | +0.0805 [+0.0037, +0.1294] | +0.0626 [−0.0235, +0.1198] | +0.0795 [−0.0018, +0.1507] | +0.0699 [−0.0026, +0.1432] |

**Kill test 1 (the real risk) does not fire.** `rel` retains 88.1% NQ / 92.5% ES of raw's
within-slot contrast, comfortably above the pre-declared 75% gate, on both markets.
Normalising VEI by its own same-slot history does **not** destroy its information. That
settles the EXP-0005 / EXP-0006 flip-flop: the original "de-seasonalising destroys
information" claim was an artefact of the warm-up bug, and the reversal now has a second,
independent, magnitude-preserving confirmation.

**`z` is the standout, and it is the only feature of the four whose CI excludes zero on
both markets in both metrics** — four cells out of four. `raw` excludes zero in none of
its four. Note carefully *how* it gets there, because the two markets differ: on NQ the
point estimate rises (+0.0748 → +0.0959, +28%) at essentially unchanged CI width (0.1354
→ 0.1357); on ES the point estimate is flat (+0.0781 → +0.0784) with a slightly narrower
interval (0.1482 → 0.1325). So this is **not** "the effect is 28% bigger" — it is a
better-conditioned measurement whose significance pattern happens to be consistent across
both markets and both metrics.

### Sensitivity and coverage

Lookback {30, 90, 180} on `rel`: within-slot +0.0672 / +0.0659 / +0.0590 (NQ) and
+0.0661 / +0.0722 / +0.0553 (ES). No cliff and no sharp optimum; 180 is worst on both,
consistent with a stale trailing window tracking the regime poorly. The default 90 was
inherited from `causal_slot_percentile` for single-variable comparability and was **not**
selected on this sweep.

Rule 9a: the trailing window costs 60 of 3710 sessions, **uniformly across every slot**
(kept fraction 0.9838 at all 11 slots). That uniformity is the pass signal — a coverage
loss that tracked time-of-day liquidity would be the tell. The 09:59 slot (no long ATR
yet) and the 15:59 slot (no forward window) are absent as in every prior forward-looking
statistic in this project.

## Gross, net, baseline, and null comparison

Not applicable — descriptive measurement of a feature normalisation. No trading, fills,
or costs, and therefore no Null C (HYP-0006 states this in advance; the standing rule is
also that a failing real pass does not buy a null, and EXP-0004's REJECT stands).

The baseline comparison is `raw` in the same table on the same common sample, which is
the single-variable control.

## Regimes, sensitivity, and alternative explanations

- **Cross-market.** The calibration result is essentially identical on NQ and ES
  (spread 0.169/0.198 → 0.012/0.012 for `z`), as is the ordering `pct ≈ z ≪ rel ≪ raw`.
  Kill test 1's non-firing reproduces on both. The `z` significance pattern reproduces on
  both. What does *not* reproduce is the *size* of `z`'s gain (+28% NQ, flat ES) — so the
  construction transfers but the magnitude of the improvement does not, and it must be
  described as a measurement improvement rather than a larger effect.
- **Alternative explanation: is `z` just selecting fewer late-day decisions and thereby
  dodging a bad regime?** No — every feature is compared at a matched global selection
  rate, and the within-slot metric removes slot composition entirely. `z` and `pct` have
  nearly identical per-slot selection profiles (CV 0.050 vs 0.039) but materially
  different contrasts (+0.096 vs +0.081 NQ; +0.078 vs +0.063 ES), so the difference is
  not the slot profile — it is that `z` keeps the magnitude information `pct` discards.
- **Alternative explanation: is this just noise across four correlated features?** Partly.
  The CIs are wide and heavily overlapping and no feature is significantly different from
  another. The claim being made is about the *significance pattern being consistent across
  two markets and two metrics*, not about any pairwise gap.
- **Why `rel` underperforms `z`.** Two candidate reasons, not separated here: the residual
  calibration imbalance (it leaves per-slot scale uncorrected), or per-slot scale itself
  carrying information. Distinguishing them would need a fifth measurement on the same
  data and was not attempted.

## Artifact and implementation risks

- `analysis.causal_slot_stats` is new, covered by
  `tests/test_core.py::test_causal_slot_stats_is_causal_and_matches_definition`
  (literal trailing-window agreement plus a future-perturbation causality check) and
  `::test_slot_normalisation_removes_a_per_slot_level_shift` (which pins the
  location-vs-scale distinction). Suite 15/15.
- **A bug was caught by running:** the sensitivity sweep initially held `min_obs=60`
  fixed while varying the lookback, making it unreachable at `lookback=30` — the feature
  silently defined nothing and the block crashed. Fixed by holding the *fraction* constant
  (`_min_obs_for`). Worth recording because a quieter version of the same bug would have
  produced an empty-sample number instead of an error.
- The contrast machinery is `s4_term_structure`'s audited `slot_contrast_arrays` /
  `weighted_slot_contrast` / `boot_slot_contrast`, unchanged, so it is the same estimator
  as EXP-0005/0006/0008. `pooled_contrast` is new and simple (difference of two Pearson
  correlations, session-block bootstrapped).
- Bootstraps are 400 draws for runtime, so CIs are coarse. Two significance calls sit near
  a CI edge (`z` ES within-slot lower bound +0.0052, pooled +0.0046) and should not be
  leaned on individually — the cross-market, cross-metric *pattern* is the claim.
- Wrote only to `artifacts/runs/EXP-0009/`.

## Builder interpretation

**The calibration defect is real, large, cross-market, and fully fixable at no cost to the
feature's information.** `VEI > 1.10` was never a volatility threshold — it selected 1.5%
of late-morning decisions and 18–22% of late-afternoon ones. Any VEI regime label built on
a fixed cut of the raw ratio was substantially a clock. Normalising against the trailing
same-slot distribution removes that entirely, and the pre-declared risk that it would
normalise the signal away did not materialise.

**Recommendation: adopt `z` = (VEI − mu_slot)/sd_slot as the project's regime label,** with
`rel` retained as the interpretable sibling — its "1.0 = normal for this time of day"
reading is easier to reason about, at a modest calibration cost. This is a
**measurement/calibration improvement and explicitly not new evidence for an edge**, exactly
as kill test 2 specifies.

**On Study D — stated precisely, because this is the tempting over-read.** D was downgraded
to qualified/inconclusive by EXP-0006 specifically because NQ's CI crossed zero. Under `z`
it does not cross zero, on either market, in either metric. That is a real and
cross-market-consistent observation. It is **not** a restoration of D's status, for a reason
that has nothing to do with the numbers: this is the fifth measurement of D on the same
consumed history, and `z` was chosen from four candidates *after* seeing D fail under the
canonical one. That is precisely the search rule 26 exists to catch. The honest position is
that **`z` makes Study D worth exactly one clean forward test** — it does not retroactively
pass a test D already failed.

What this does add: combined with EXP-0008 (the momentum information lives in the ratio,
not the level) and EXP-0005 (it is not a clock effect), VEI's regime-labelling role now has
a properly calibrated feature to be expressed in. The three known defects of the original
construct — a mis-initialised warm-up (EXP-0006), a selection metric that rewarded
degeneracy (EXP-0008), and an uncalibrated threshold (this run) — are all now repaired. If
the feature is tested again, it should be tested in this form.

**What has not changed:** EXP-0004's REJECT stands, no null was spent, and there is still no
established directional edge. Better measurement of a weak effect is still a weak effect.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: new §I (slot-normalised VEI); §A-corrected (b)'s calibration
  defect now has its fix; §F corollary (a)'s reversal independently confirmed.
- `MEMORY.md`: canonical regime label updated to `z`; Study D's status unchanged, with the
  forward-test note added.
- Shared `LEARNINGS.md`: **eligible for the method** — a session-reset feature's fixed
  threshold is a time-of-day selector, and the trailing same-slot z-score fixes it while
  the ratio-to-mean only half-fixes it. The contrast improvement is holdout-pending and is
  recorded as provisional.
