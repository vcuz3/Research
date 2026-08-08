# Conviction score (item 21) and supervised model (item 22) — both NO-GO

**Date:** 2026-08-07 · consumed history only, 2024+ sealed · screen (rule 26)

**Question.** The per-axis conviction search is exhausted: signal strength (axis 1),
volatility regime (axis 2) and cross-pair divergence (axis 3) all proved redundant
with `|z_twap|` depth, and the two orthogonal external axes (calendar proximity,
VIX regime) live in too small a tail to beat depth. Two moves remained that the
per-axis tests could not settle, because they exploit *joint* structure the single
gates cannot:

- **Item 21** — combine several mutually-orthogonal conditioners into one ranked
  conviction score, keep the top decile.
- **Item 22** — reframe as supervised prediction: label each fade "did it revert
  profitably" and let a model weight the axes jointly under leakage-safe CV.

**Both fail.** Neither a hand-built orthogonal conviction score nor a purged/embargoed
supervised model beats simply ranking by `|z_twap|` at the same trade rate. Depth
remains the single conviction lever.

## Setup

Baseline = the promoted session-TWAP fade: first crossing of `|z_twap| >= 1.5`
(event clock, non-overlap), 240-min time exit, horizon-scaled 3R stop, 1-pip
slippage, delay 0 and 1, four USD majors (~23,834 trades). Outcome R produced only
by the audited `_rsi_stop_engine`. Shared per-trade table:
`_build_conviction_table.py -> rsi_conviction_trades.parquet` + the per-pair
`|z_twap|` depth frontier `rsi_conviction_frontier.json`.

**The honest bar is a DIRECT matched-count depth benchmark, not the frontier.** A
top-decile book fires at ~270–285 signals/yr/pair, which is *sparser than deepening
z alone can reach* (the frontier bottoms out at ~285–305/yr at `k=4.0`). Scoring
"excess over the frontier" then makes `np.interp` **clamp** to the `k=4.0` endpoint
and flatters the score (the LEARNINGS-2026-08-05 trap). So the primary metric is
`vs_depth_topq`: mean R minus the mean R of the **top-q trades ranked by `|z_twap|`**
on the identical book — exactly matched count, no extrapolation.

## Item 21 — conviction score (`_run_rsi_conviction_score.py`)

**Correlation audit reproduces the redundancy finding.** Spearman `|rho|` with depth:
`decel5` 0.44, `rv5_pct` 0.38, `zvel5` 0.37, `vei_atr_z` 0.26, `rv30_pct` 0.24
(all the strength/vol axes — redundant); orthogonal: `abs_sigma_pips` 0.01,
`vix_z` 0.02, `xdiv` 0.03, `prox_hi` 0.05. One representative per axis: depth
`absz_twap`, abs-vol `abs_sigma_pips`, cross-pair `xdiv`, calendar `prox_hi`, risk
`vix_z`. Orientation signs learned on the **early era only** (sign of
Spearman(feature, R)); percentile-rank each oriented feature within pair, average.

| set | top-decile meanR | **vs depth-top-q (d0 / d1)** | vs frontier (clamped) |
|---|---|---|---|
| all axes | +0.049 | **−0.040 / −0.021 (1/4)** | +0.008 |
| depth-free (no `|z|`) | +0.029 | **−0.051 / −0.029 (1/4)** | −0.032 |

Against the honest matched-count depth benchmark the conviction score is **worse**
than just ranking by `|z_twap|` (1/4 pairs beat it). The `+0.008` "excess over the
frontier" is entirely the clamping artifact. Dropping depth from the score
(depth-free) is worse still — the orthogonal external axes select a *worse* book
than depth.

## Item 22 — supervised model (`_run_rsi_supervised.py`)

11 decision-time features; label `R_d0 > 0` (base reversion rate 0.511); **6 purged +
embargoed contiguous time folds**, embargo 1680 min (240-min hold + 1 day), so no
training outcome window overlaps the test period; standardiser/imputer fit on train
folds only; out-of-fold predictions ranked into a conviction score.

**Decision-time features carry no predictive skill: OOF AUC ≈ 0.51 for every model.**

| model | AUC | top-decile **vs depth-top-q (d0 / d1)** |
|---|---|---|
| logit · all axes | 0.513 | −0.016 / −0.009 (1/4) → NO-GO |
| logit · depth only | 0.511 | −0.002 / −0.001 (1/4) → NO-GO (≈0, sanity: logit-on-depth ≈ depth rank) |
| hgbt · all axes | 0.507 | +0.021 / +0.022 (3/4) → *flagged SUPPORTED* |
| hgbt · depth only | 0.509 | −0.021 / −0.017 (1/4) → NO-GO |

The one positive flag (hgbt top-decile) is a **top-bucket fluke**: it is non-monotone
(drops to −0.009 at keep-20, −0.014 at keep-40) on an AUC-0.507 model, and a
seed sweep confirms it is noise — `vs_depth_topq` swings **−0.038 → +0.072** across
6 random seeds (seed 0 happened to land +0.021/3-4; seed 1 gives −0.038/1-4). A
real conviction edge would degrade gracefully with keep and be seed-stable; this
does neither. The linear model, which cannot overfit the tail, is cleanly negative.

## Verdict

**Both items NO-GO.** Combining the orthogonal axes into a ranked conviction score,
or letting a properly-cross-validated model weight all axes jointly, does **not**
beat ranking by `|z_twap|` at matched trade count. The joint/interaction question
the per-axis tests left open is now closed: there is no cross-axis structure to
harvest — the reversion outcome is near-unpredictable from decision-time state
(AUC 0.51), and depth is a near-sufficient statistic for conviction. The remaining
live lever is unchanged: the **estimand** (prop-firm account simulation), not a
better per-bet selection signal.

**Method notes (reusable).** (1) For a top-decile selection, compare against a
direct matched-COUNT depth benchmark, never `np.interp` over a frontier whose
sparsest cell is denser than the selection — the interpolation clamps and flatters.
(2) Any tree-model top-bucket result must be seed-swept and checked for
keep-monotonicity before it is believed; an AUC ≈ 0.5 model can still throw a
spurious +0.02 top decile on one seed.

**Reproduce:**
`python -u _build_conviction_table.py` then
`python -u _run_rsi_conviction_score.py` and `python -u _run_rsi_supervised.py`.
