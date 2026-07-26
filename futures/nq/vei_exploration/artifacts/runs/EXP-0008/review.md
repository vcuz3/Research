# EXP-0008 Results Discussion

- Hypothesis: `HYP-0005` — IC_fwdvol scores level-likeness, so it cannot select a VEI variant
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: cross-variant R² of `IC_fwdvol` on `corr_lvl`, plus the rank of the
  no-denominator `LEVEL:` control in the `IC_fwdvol` column, on both markets
- Kill test: see `experiments/hypotheses/HYP-0005.md`

## Result versus hypothesis

**KILL TEST 1 CONFIRMED, and KILL TEST 3 fired as well, on both markets.** `IC_fwdvol`
is not merely a poor selection metric for a VEI variant — it ranks variants in the
*opposite* order to the property the project cares about.

| | NQ | ES |
| --- | --- | --- |
| `IC_fwdvol` = a + b·`corr_lvl` | +0.0130 + **0.891**·corr_lvl, **R² 0.992** | +0.0100 + **0.903**·corr_lvl, **R² 0.992** |
| `IC_partial` = a + b·`corr_lvl` | +0.0158 + 0.116·corr_lvl, R² 0.301 | +0.0049 + 0.175·corr_lvl, R² 0.496 |
| `contrast` = a + b·`corr_lvl` | +0.1391 **− 0.216**·corr_lvl, **R² 0.838** | +0.1254 **− 0.160**·corr_lvl, **R² 0.759** |

Across ten variants, `IC_fwdvol` is a near-perfect straight line in how level-like the
variant is: R² 0.992 on **both** markets, slope ≈0.9, intercept ≈0. A variant's score on
the incumbent metric is, to three significant figures, its correlation with the vol
level. There is essentially no residual for "ratio quality" to live in.

The degenerate-limit control settles it. `LEVEL: atr_10` has **no denominator at all** —
zero ratio content by construction — and it **tops the `IC_fwdvol` column on both
markets** by a wide margin (+0.5745 NQ / +0.6130 ES) against the best ratio's +0.3958 /
+0.3530. A metric that a non-ratio wins cannot be used to select among ratios.

**Kill test 3 (the harmful case) also fired.** `contrast` — the project's actual primary
metric — is *negatively* related to `corr_lvl` (r −0.915 NQ / −0.871 ES). The two
metrics rank variants oppositely, so selection on `IC_fwdvol` does not merely fail to
help, it actively degrades the momentum-regime property. Concretely, the EXP-0006 lead
`wilder_20_100` — the highest-scoring ratio on `IC_fwdvol` — has the **lowest** momentum
contrast of any ratio tested (+0.0587 NQ / +0.0453 ES, both CIs including 0), below the
canonical `wilder_10_50` (+0.0751 / +0.0894). **The EXP-0006 decision not to adopt it
was correct, and adopting it would have been an active mistake.**

Per-variant results (common sample n=33,389, 9 of 13 slots, both markets):
`artifacts/runs/EXP-0008/selection_metric_{NQ,ES}.txt`.

## Gross, net, baseline, and null comparison

Not applicable — descriptive measurement of an estimator-selection metric, no trading,
no fills, no costs. No Null C is in scope and none was spent (HYP-0005 states this).

The relevant comparison is against the incumbent selection rule, and it is a rejection:
the incumbent's ranking is anti-correlated with the primary metric's ranking.

## Regimes, sensitivity, and alternative explanations

- **Cross-market.** Every number reproduces on ES: same R² to three decimals (0.992),
  same slope to ~0.01, same `LEVEL:`-wins verdict, same negative `contrast` slope, same
  worst-ratio identity (`wilder_20_100`). This is a machinery claim, so agreement is the
  expected outcome and *dis*agreement would have indicated a tape artefact rather than a
  metric defect. Agreement this exact is consistent with an algebraic property of the
  construction rather than an empirical regularity.
- **Sample confound controlled.** All variants are scored on one common sample (the
  intersection where every variant is defined), so the ranking cannot be an artefact of
  `long=100` being measured at later, different slots than `long=25` — the project's
  standing hazard (FINDINGS §A-corrected (b)).
- **Selection-rate confound controlled.** The `contrast` column uses a matched selection
  rate (each variant's own top 8.21% NQ / 9.46% ES quantile), so no variant can win by
  relabelling more decisions "high".
- **Alternative explanation considered: is `contrast`'s negative slope just the
  small-sample noise of a search?** Partly — the individual contrast CIs are wide and
  overlapping, and no single variant is significantly better than another. But the
  *slope* is estimated across ten variants and is strong on both markets, and it has an
  independent mechanical reading (below), so the direction is credible even though the
  argmax is not.
- **`IC_partial` is a partial repair, not a fix.** Partialling the level out of both
  sides breaks the near-perfect fit (R² 0.992 → 0.301 / 0.496) but the pure-level
  controls still top that column too (+0.1171 / +0.1494). The reason is that
  `LEVEL: atr_10` is a *differently windowed* level than the `past_rv` being partialled
  out, so it retains genuine forward-vol information that `past_rv` does not carry. So
  `IC_partial` measures "any vol information beyond `past_rv`", which a rescaled level
  still supplies in quantity. **No forward-vol-based metric is the right selector for a
  ratio.** `IC_partial` is worth reporting as a diagnostic but should not replace
  `IC_fwdvol` as the selection rule.

## Artifact and implementation risks

- `analysis.partial_spearman` / `block_boot_partial_ic` are new; both are covered by
  `tests/test_core.py::test_partial_spearman_removes_the_conditioning_variable` (which
  pins the degenerate case the metric exists to catch) and
  `::test_partial_spearman_matches_manual_rank_residual_correlation` (closed-form
  agreement to 1e-10). Suite 13/13.
- The `contrast` column reuses `s4_term_structure`'s audited `slot_contrast_arrays` /
  `weighted_slot_contrast` / `boot_slot_contrast` unchanged, so it is the same estimator
  as EXP-0005/EXP-0006's primary metric. Its `MIN_CELL=30` thin-cell rule is inherited.
- Bootstraps are 500 draws (ICs) and 400 draws (contrast), fewer than the 1000 used
  elsewhere, for runtime. CIs are correspondingly coarser; no conclusion here turns on a
  CI edge.
- The common sample drops the three morning decision slots (mfo 29/59/89) because
  `long=100` is undefined there. The `contrast` column is a within-slot statistic so
  slot composition is removed, but the result is nonetheless established on the 119–359
  window only. The canonical variant's contrast on this window (+0.0751 NQ / +0.0894 ES)
  sits close to EXP-0006's full-sample +0.0690 / +0.0857, so the restriction does not
  appear to be load-bearing.
- **This run wrote only to its own `artifacts/runs/EXP-0008/` directory** — the EXP-0006
  process defect is not repeated. The project is still untracked by git (next action 0d,
  still open).

## Builder interpretation

**Next action 0b is closed by replacement, not by adoption.** `IC_fwdvol` is retired as
an estimator-selection metric for VEI on both markets. The canonical `wilder_10_50` is
retained, and `wilder_20_100` is withdrawn as a lead.

The mechanism is now explicit and, in hindsight, algebraic. As the denominator's memory
grows, ATR(long) approaches a within-session constant; dividing by a constant does not
form a ratio, it rescales the numerator. So the "better" variants on `IC_fwdvol` were
better *because they had stopped being ratios* — they were converging on the vol level,
which Study B already showed beats every VEI variant at forecasting vol (+0.86). The
metric was rewarding the feature for abandoning the quantity the project is studying.

**The more valuable result is the one the controls produced for free.** The pure vol
level has a momentum contrast of essentially **zero** (−0.0047 NQ / +0.0225 ES, both CIs
spanning 0), while every genuine ratio is positive (+0.06 to +0.12). High volatility on
its own does **not** select the momentum regime; the *expansion ratio* does. That is a
direct, independent vindication of the ratio's reason to exist, and it is the first
result in this project that separates VEI from the level on the momentum axis rather
than the vol-forecasting axis. It also sharpens Study D's meaning: whatever D is
measuring, it is not "momentum works when vol is high".

Read together with EXP-0006, the project now has a coherent picture of the two axes:
on the **vol-forecasting** axis the ratio is dominated by the level and is nearly
worthless (Study B, ΔR² +0.0017); on the **momentum-regime** axis the level is worthless
and only the ratio carries anything (this run). They are not competing measurements of
one thing — they are different things, and VEI's only distinctive role is the second.

**What this does NOT do.** It does not revive Study D. D remains qualified/inconclusive
after EXP-0006, its CI still crosses zero on NQ at the canonical variant, and every
contrast CI in this table is wide. The `contrast` column is a ten-variant search on
consumed history (HYP-0005 multiple-testing note); the argmax `wilder_20_50` (+0.1075 NQ
/ +0.1181 ES) is **not** promoted and should not be cited as a better estimator. What is
established here is the *slope* — the direction of the relationship between
level-likeness and momentum-selectivity — not any individual cell.

Two secondary observations, both flagged rather than claimed:

- The short-window variants `wilder_5_25` and `wilder_5_50` have by far the highest
  `IC_partial` among ratios (+0.069/+0.067 NQ, +0.070/+0.068 ES) *and* healthy contrasts,
  i.e. they are the least level-contaminated cells. If the estimator is ever revisited,
  the short leg is where to look, not the long one.
- `sma_19_99` has `IC_partial` ≈ 0 on both markets (−0.006 / +0.002) despite a
  respectable `IC_fwdvol` of +0.19 — its entire forward-vol score is level content.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: new §G (selection-metric validity); §A-corrected's
  `wilder_20_100` lead marked withdrawn.
- `MEMORY.md`: next action 0b closed; canonical-estimator constraint updated.
- Shared `LEARNINGS.md`: **eligible** — the failure mode (scoring a RATIO on a metric its
  own numerator maximises) is construction-level, not NQ-specific, and the pure-numerator
  degenerate control is a reusable test. Recorded 2026-07-27.
