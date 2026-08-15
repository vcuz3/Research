# EXP-0005 review — Stage C axis 1: displacement depth (|z_slot|) overlay

- **Pre-spec:** `experiments/hypotheses/HYP-0005.md`, frozen before the run.
- **Config:** `baseline_replication/configs/stage_c_depth.json`
- **Command:** `python -u forex/exploration_4/_run_stage_c_depth.py` (~3 min)
- **Reuses** the frozen book via `_run_stage_b` (build_signals, simulate_book) so the overlay
  acts on exactly the EXP-0004 stateful guarded delay-1 trades.
- **Builder:** Claude. **Reviewer:** unassigned. **Review status:** pending.
- **Caveat:** proceeds while EXP-0004 is pending re-verification and Stage-A repairs are open
  (user directed Stage C to start); this result is conditional on the ruler holding.

---

## 1. Result

**Depth REJECTED as a rescue; retained as the Stage-C benchmark curve.**

- **Parity:** the t=2.0 point reproduces EXP-0004 exactly (n=66,912, gross −0.028 R_slot, net
  −0.565) — the overlay pipeline is the frozen book at the entry floor.
- **Depth orders gross:** slope **+0.057 R_slot per unit |z_slot|**. Gross crosses zero around
  |z|≈2.8 and reaches +0.13 pips at |z|≥3.8. So deeper displacements do revert more — depth is
  genuine reversion signal, consistent with the LEARNINGS "depth near-sufficient statistic".
  (Each individual deep-tail gross CI still includes zero; it is the *ordering* that is real.)
- **But net never clears zero at any deployable depth.** Best deployable (|z|≥3.8, n=10,286):
  net **−0.500 R_slot** CI [−0.707, −0.294]. Net sits ≈ −0.50 to −0.57 R_slot across the whole
  grid because the modelled cost (~1.25 pips) dwarfs the ≤0.13-pip gross the deep tail reaches.
- **Cost does not fall with depth:** σ_slot actually *decreases* slightly with |z| (buckets:
  2.93→2.73 pips — a large z often comes from a small σ, not a large one), so cost in pips is
  roughly flat and there is no σ-scaling that rescues net at depth.
- **Null correctly gated out** (my `gate-nullc-on-success-metric` rule): the primary metric
  never cleared, so the permutation null was not spent.
- **Sealed holdout** (deepest, |z|≥4.0, n=1,536), opened once: net −1.03 R_slot, gross −0.81
  pips — even worse; consistent.

## 2. Interpretation

This is the expected outcome (run-book §7): depth is a real but **insufficient** lever. It
orders gross reversion — the near-sufficient statistic reappears — but the ordering buys a few
hundredths of R while the round-trip cost is ~0.5 R_slot, so no depth threshold is net-viable.
The value of the run is the **benchmark curve** (`depth_frontier.csv`): every later overlay
(vol, cross-pair, session, exit-horizon) must beat this (count → gross-R) curve at matched
count, and if one "helps" the first suspicion is that it is just selecting deeper |z_slot|.

## 3. Alternative explanations considered

- **Is the veto reproducible without re-non-overlap?** No — and it is not filtered post-hoc:
  `book_after_veto` re-runs greedy non-overlap per pair after each depth cut (Stage-B F1), so
  freed occupancy is credited. This is why n falls smoothly (66,912 → 8,555) rather than in the
  proportion a naive filter would give.
- **Could a finer/deeper grid find a viable pocket?** The grid runs to |z|≥4.0 (n=8,555, mean
  |z| 5.3 in the deepest bucket) and net is monotonically ≈ −0.5 R_slot; deeper still only
  shrinks n below the deployable floor. The holdout at |z|≥4.0 is worse, not better.
- **Is gross ordering an artifact of the guarded fill?** The ordering is in gross R on the same
  fill model as the book; it is not claimed as net-positive, so no fill-model rescue is implied.

## 4. Departures and limitations

- **No departures from HYP-0005.** The decision rule (net CI>0 at deployable count, else reject
  and retain the benchmark; null gated on the primary) was applied as frozen.
- Depth is the entry variable itself, so this is a benchmark, not an independent conditioner —
  stated in the hypothesis.
- Cost is modelled (no bid/ask); the guarded fill is a model; conditional on EXP-0004
  re-verification and the open Stage-A repairs.

## 5. Independent review checklist

1. Rerun the command; confirm the t=2.0 frontier point equals the EXP-0004 primary (parity).
2. Confirm `book_after_veto` re-applies non-overlap (not a post-hoc filter) and that n falls
   accordingly.
3. Confirm the null was gated out because the primary never cleared, and that the gate is the
   argmax-net deployable row's CI (not a cherry-picked row).
4. Sanity-check the gross depth slope sign and that net stays ≈ −0.5 R_slot across the grid.
5. Confirm 2024+ was read once (deepest threshold) and informed no decision.
