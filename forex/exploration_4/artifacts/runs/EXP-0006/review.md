# EXP-0006 review — Stage C axis 2: volatility regime (compression vs expansion) overlay

- **Pre-spec:** `experiments/hypotheses/HYP-0006.md`, frozen before the run.
- **Config:** `baseline_replication/configs/stage_c_vol.json`
- **Command:** `python -u forex/exploration_4/_run_stage_c_vol.py` (~1 min)
- **Reuses** the frozen book via `_run_stage_b` (build_signals, simulate_book) and the depth
  benchmark via `_run_stage_c_depth` (`_pooled_stats`, `depth_frontier.csv`), so the overlay
  acts on exactly the EXP-0004 stateful guarded delay-1 trades and is scored against EXP-0005.
- **Builder:** Claude. **Reviewer:** unassigned. **Review status:** pending.
- **Caveat:** proceeds while EXP-0004 is pending re-verification; conditional on the ruler.

---

## 1. Result

**Volatility regime REJECTED as a rescue** (both arms).

- **The feature is largely depth-orthogonal:** `corr(vr_z, |z_slot|) = +0.134` on consumed
  eligible trades, and `vr_z` is available on 99.8% of the 160,040 book-eligible trades. So the
  central confound (a vol veto secretly selecting depth) is small — this is a genuinely
  different axis, not a depth restatement, which makes the null result informative.
- **Net never clears zero on either arm at any deployable count.** Compression best
  (keep=0.15, n=11,869) net **−0.526 R_slot** CI[−0.627,−0.425]; expansion best (keep=0.60,
  n=36,965) net **−0.547** CI[−0.626,−0.468]. Net sits ≈ −0.53 to −0.58 across both whole
  grids — the ~1.25-pip modelled cost dwarfs any gross ordering, exactly as in EXP-0004/0005.
- **Gross direction, such as it is, favours COMPRESSION and penalises EXPANSION.** At tight
  cuts the expansion arm's gross goes sharply negative (keep=0.10 gross **−0.381** R_slot,
  keep=0.15 −0.248, keep=0.20 −0.104), while the compression arm's tight cuts are ~flat-to-mildly
  positive (keep=0.15 gross +0.018). Buckets confirm: the top `vr_z` bucket (high ambient vol,
  vr_z̄=2.74) has the worst gross (−0.076) and the expansion tail also selects deeper |z_slot|
  (abs_z 3.25 at keep=0.10 vs 2.77 base), so **deep displacements in high ambient vol revert
  LESS** — the opposite of a rescue. Compression does not order gross enough to matter either.
- **Null correctly gated out** (`gate-nullc-on-success-metric`): the primary (net CI>0 AND beat
  depth at matched count) never cleared on either arm, so the permutation null was not spent.
- **Sealed holdout** (compression keep=0.15, n=2,794), opened once: net −0.787 R_slot, gross
  −0.279 pips — worse, consistent.

## 2. Interpretation

Expected outcome under the honest prior (run-book §7). The ambient-volatility regime does not
separate capturable from un-capturable reversion. If anything it says the reversion is *worse*
in expansion (high-vol overshoots continue rather than snap back within 240 min), but every
cell is deeply net-negative, so there is nothing to size or veto into. The one nominally
"positive" number — the expansion arm's +0.023 excess over the depth benchmark at keep=0.60 —
is a non-result: it is an excess of one −0.547 book over a −0.570 benchmark, both far below
zero, at a mild keep-fraction, and it does not (and cannot, under the frozen rule) count as a
pass because net CI>0 fails. Reading it as a "win" would be exactly the trap HYP-0006 §4 was
written to prevent.

## 3. Alternative explanations considered

- **Is the veto reproducible without re-non-overlap?** No — `book_after_regime` re-runs greedy
  non-overlap per pair after each cut (Stage-B F1), so freed occupancy is credited; counts fall
  smoothly with the keep-fraction rather than proportionally.
- **Is the null result just a weak/degenerate feature?** No: `vr_z` has a real, monotone
  dose-response in `sigma_abs` across buckets (2.95→4.23 pips) and 99.8% coverage; it simply
  does not predict *net* reversion. It is a live feature that fails on the outcome, not a dead
  one.
- **Could the expansion excess be real?** It is +0.023 R_slot on a −0.547 book, at keep=0.60,
  with net CI far below zero and worse on the holdout; it is not distinguishable from the
  matched-count noise floor and was not promoted.

## 4. Departures and limitations

- **No departures from HYP-0006.** Both arms swept and reported; decision = excess over depth at
  matched count read from the swept grid (nearest count, not interpolated); null gated on the
  primary; both risk units and holdout handled as frozen.
- `vr_z` is built on `sigma_abs` (the slow 28,800-min window). A regime on a shorter ambient
  window is a distinct, untested feature — but the honest prior does not motivate chasing it.
- Cost is modelled (no bid/ask); the guarded fill is a model; conditional on EXP-0004
  re-verification and the open Stage-A repairs.

## 5. Independent review checklist

1. Rerun; confirm keep=1.0-equivalent base parity (n≈66.8k, gross −0.0275, net −0.565).
2. Confirm `corr(vr_z, |z_slot|)` is small and that `book_after_regime` re-applies non-overlap.
3. Confirm net CI>0 fails at every deployable cut on BOTH arms, so the null is correctly gated
   out, and that the +0.023 expansion excess is not treated as a pass.
4. Sanity-check the expansion-tail gross going negative while abs_z rises (deep-in-high-vol).
5. Confirm 2024+ was read once on the decision-pointed cut and informed no decision.
