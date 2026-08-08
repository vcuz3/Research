# EXP-0002 review — Stage A, multi-scale market characterization

- **Hypothesis / pre-spec:** `experiments/hypotheses/HYP-0002.md`, frozen before the run.
- **Config:** `baseline_replication/configs/stage_a.json`
- **Command:** `python -u forex/exploration_4/_run_stage_a.py`
- **Tests:** `python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider` — 22 passed.
- **Builder:** Claude. **Reviewer:** unassigned. **Review status:** pending.
- **Data scope:** EURUSD, GBPUSD, AUDUSD, NZDUSD 1-minute midpoint OHLC, 2012-01-01
  onward. Consumed history 2012–2023 drives every selection number; 2024+ opened once
  as a descriptive check only.
- **Result:** rule resolves to **τ\* = 5 min, H\* = 240 min**, and the shared-endpoint
  control independently resolves to the same pair. But the exit gate passes only in
  the "documented disagreement" sense — see §3.

---

## 1. What the run found

**View 1 (variance ratio).** Every rung reverts, and reversion *deepens with the
timescale*: pooled consumed `VR` = 0.9483 (5m), 0.9060 (15m), 0.8885 (30m), 0.8757
(60m), 0.8689 (120m), Lo–MacKinlay robust `z` between −12.4 and −15.2. `VR < 1` holds
in all five session cells and all four pairs. This is a real, well-powered ambient
reversion signature.

**View 2 (conditional extreme→anchor).** Reversion *conditional on an extreme* runs
the opposite way across the ladder: pooled consumed gross mean R at `k = 2.0`, best
over H, is 0.190 (τ=5, H=240), 0.100 (τ=15), 0.058 (τ=30), 0.021 (τ=60), −0.0001
(τ=120). The same ordering holds on the maximal sample (0.158 / 0.082 / 0.059 / 0.026
/ 0.005), so the ordering is not a coverage artifact of the common-sample rule.

**View 3 (bounded double barrier).** Profit factor is **below 1 at every rung, both
caps, both entry arms** — best 0.934 at τ=30. Its ranking (30 > 15 > 60 > 5 > 120)
agrees with neither of the other views. §4 shows why that ranking cannot be taken at
face value.

**Costs.** The best breakeven round-trip is **0.79 pips** (k=2.5, τ=5, H=240,
undelayed) and **0.64 pips** at the k=2.0 headline. The modelled base round trip is
**1.21 pips**, of which **0.70 pips is commission alone**. Net expectancy is negative
in every cell of the surface.

---

## 2. The shared-endpoint control (added; not in the frozen spec)

In this archive `open[i] == close[i-1]` for **99.99998%** of contiguous minutes
(measured directly on EURUSD: 5,532,683 contiguous minutes). The undelayed entry price
is therefore *the same number* that terminates the displacement window, so any
transient pricing error at that instant enters the displacement with `+1` and the
forward return with `−1`. That is the manufactured-reversion mechanism recorded in
`ai_shared_memory/LEARNINGS.md` §6.

A one-bar entry delay was added as a **paired** control on the identical signal set —
same rows, complete under both arms, so the comparison is coverage-matched rather than
sample-shifted. Pooled consumed, k=2.0:

| τ | H | n | gross R (d0) | gross R (d1) | Δ | Δ t |
| --- | --- | --- | --- | --- | --- | --- |
| 5 | 240 | 111,695 | 0.1527 | 0.0666 | −0.0862 | −12.2 |
| 5 | 480 | 79,303 | 0.1627 | 0.0665 | −0.0963 | −12.2 |
| 15 | 120 | 39,711 | 0.0810 | 0.0398 | −0.0412 | −3.6 |
| 30 | 120 | 21,954 | 0.0588 | 0.0083 | −0.0504 | −3.3 |
| 60 | 60 | 11,256 | −0.0072 | −0.0005 | +0.0067 | +0.3 |

**Roughly 56–78% of the measured conditional reversion is the shared endpoint.** What
survives is real, decisively non-zero at τ=5 (d1 = 0.067R, and the paired Δ is
t = −12, so the loss itself is not noise), and indistinguishable from zero at τ ≥ 60.
The control does **not** change the selection: applying the frozen rule to the delayed
arm also returns τ\* = 5, H\* = 240.

---

## 3. Where the views disagree, and what the rule did

Views 1 and 2 **rank the ladder in opposite directions**. This is not a defect in
either: `VR(τ)` is unconditional and linear, so it measures the serial dependence of
the *average* τ-minute move; view 2 measures what happens *after a τ-minute move is
extreme*. That the two invert is itself the finding — ambient reversion strengthens
with timescale while extreme-conditional reversion weakens with it.

The frozen rule anticipated this (HYP-0002 §6.3) and takes τ\* from view 2, the
conditional view, because the strategy monetizes the conditional object. Recorded in
`verdict.json` as `selection_basis`.

View 3 disagrees with both. Under the exit gate this is a **documented disagreement,
not agreement** — the gate's weaker branch. It is recorded as such rather than smoothed
over.

---

## 4. Why view 3's ranking cannot be read as a grain comparison

View 3 charges a **fixed 1-pip adverse stop slippage** against barriers set in **vol
units**. A fixed pip cost is a far larger fraction of σ at a fine grain than a coarse
one (Rule 19), so the comparison is mechanically biased against fine grains. The
arithmetic is exact:

| τ | median σ (pips) | 1 pip in R | implied mean loss (R) | excess over the 1.0R target |
| --- | --- | --- | --- | --- |
| 5 | 3.17 | 0.316 | 1.327 | 0.327 |
| 15 | 5.40 | 0.185 | 1.192 | 0.192 |
| 30 | 7.61 | 0.132 | 1.136 | 0.136 |
| 60 | 10.84 | 0.092 | 1.095 | 0.095 |
| 120 | 15.62 | 0.064 | 1.063 | 0.063 |

The excess loss over the nominal 1.0R stop matches the slippage-in-R column to within
0.011R at every rung. **The entire payoff asymmetry in view 3 is the fixed-pip
slippage**, not barrier behaviour. Note also that at τ=5 the win rate is 0.5385 —
*above* the algebraic break-even 0.5 for RR = 1 — so the entry does carry information;
the slippage charge is what turns it negative.

View 3 is therefore a valid *absolute* statement (with a 1-pip slippage this book
loses at every grain) and an **invalid cross-grain ranking**. Its disagreement with
view 2 is not evidence against τ\* = 5. Stage B should not reuse this configuration as
a grain comparator.

---

## 5. Alternative explanations considered

- **Coverage artifact.** The H=480 completeness rule removes 33–42% of signals, and
  not evenly — it strips windows spanning the weekend and the archive's daily
  ~21:00–22:00 UTC rollover hole, which are exactly the thin hours where the effect
  concentrates. Addressed by reporting the maximal-sample surface alongside; the τ
  ordering is unchanged, so the selection does not rest on the rule. Enumerated by
  UTC hour in `reports/DATA_QUALITY.md` §3.
- **Baseline drift.** Naive always-long drift is ~0 pooled at every horizon
  (H=240: −0.081 pips, CI [−0.384, +0.222]), so the fade is not harvesting a
  directional tilt. London alone carries a real −0.84 pip/240min tilt — and London is
  the one session where the fade measures **zero** (0.017R, t=0.30), which is the
  opposite of what a drift explanation predicts.
- **Thin-liquidity concentration.** The effect lives in `off` hours (0.525R, t=5.4)
  and Asia (0.307R, t=4.2), not London (0.017R, t=0.30). Those are precisely the hours
  the cost model prices most expensively (the 21:00 UTC rollover carries a 5× spread
  multiplier). This is a *deployment* problem, not a measurement error, but it means
  the R-unit result and the pip-cost result point in opposite directions by
  construction.
- **Pair breadth.** 3 of 4 pairs positive (NZD 0.252 t=5.7, EUR 0.227 t=3.0, AUD 0.208
  t=3.4); GBP is flat (0.043, t=0.54) and goes slightly negative under the delay
  control. With ≈2 effective independent pairs this is weak breadth.
- **Selection/search.** No parameter was tuned to PnL. The k grid shows a coherent
  dose-response (0.134 → 0.190 → 0.249 → 0.231 across k = 1.5/2.0/2.5/3.0) rather than
  a lone spike, which is what a searched artifact usually looks like.

---

## 6. Departures from the frozen spec, and one bug

All three are recorded here rather than by editing `HYP-0002.md`.

1. **σ window counted in market bars, not calendar bins.** The frozen text says a
   fixed 28,800-minute window = `28800/τ` bars. Counted over raw bins that floor is
   *unsatisfiable*: spot FX covers only ~71% of calendar minutes, so a 0.9 `min_periods`
   floor nulls σ everywhere and the first implementation produced zero signals. σ is
   computed over the compacted series of tradable returns, so the bar count per rung is
   exactly as frozen and the window spans the same **market** time at every rung.
   `min_periods` becomes a warm-up requirement and cannot act as a hidden
   time-of-day filter. Covered by `test_sigma_survives_market_closures`.
2. **Entry-delay diagnostic added** (`entry_delay_bars: [0, 1]`,
   `primary_entry_delay_bars: 0` in the config). This adds evidence; it changes no
   frozen parameter and the rule is still applied to the delay-0 arm as contracted.
   Reported side by side, never substituted.
3. **Bug found and fixed before the final run.** The naive-drift table originally
   called the cell-pooling helper *inside* the per-pair loop, so it emitted four
   different `POOLED` rows, each secretly one pair. Fixed by returning raw rows and
   pooling once after concatenation; guarded by
   `test_cell_frames_pool_exactly_once_across_pairs`. No other table was affected —
   views 2 and 3 always ran on the concatenated frame. The first full run's artifacts
   were overwritten by the corrected run; nothing downstream consumed them.

---

## 7. Sealed holdout (opened once, changed nothing)

τ=5, k=2.0 gross mean R on 2024+: 0.187R at H=240 (n=15,438) with a day-clustered CI
of [−0.020, +0.393] — same sign, **CI includes zero**. VR on the holdout stays below 1
at every rung. Directionally consistent, not confirmatory, and it did not and could
not influence τ\* or H\*.

---

## 8. Builder interpretation

Stage A did its job: it produced a map and a defensible grain, and it removed a large
piece of an apparent effect before Stage B could freeze it into a book.

The honest reading is that **spot FX majors do revert, at every timescale, but the
tradable version of that reversion is smaller than its own transaction cost.** After
the shared-endpoint control, the best cell on the ladder is ~0.067R ≈ 0.40 pips gross
per signal against a 1.21-pip modelled round trip whose commission component alone is
0.70 pips. The gap is not a cost-model quibble; it is a factor of three.

That is not a Stage-A verdict — Stage A does not issue one — but Stage B should be
specified knowing it. Two specific carry-forwards:

- The runbook's proposed Stage-B exit ("reversion to z = 0") is **near-degenerate at
  the selected grain**: `zcross` is 0.96 by H=15 and 1.00 by H=60 at τ=5. At this grain
  that exit is a time exit wearing a different name. Either move to the anchor-retrace
  definition (`touch100` is 0.22/0.36/0.51/0.63/0.73 at H=15/30/60/120/240 — an actual
  discriminator) or accept it as a time exit and say so.
- H\* = 240 minutes conflicts with the weekend-flat constraint more than it looks: the
  Friday-flat rule truncates ~8.5% of τ=5 signals at H=480 and the H=480 completeness
  rule strips a third of the sample. H\* = 240 is the shortest horizon within the
  frozen tolerance of the maximum, which is why the rule picked it.

**My recommendation for the Stage A→B gate:** pass it as *documented disagreement*,
adopt τ\* = 5 / H\* = 240, and require Stage B to report the delayed-entry arm as its
primary and the undelayed arm as a diagnostic — the reverse of this stage. The
shared-endpoint artifact is large enough here (56–78%) that a reference book built on
the undelayed arm would be a ruler with a bias in it.

## 9. Independent review checklist

1. Rerun the tests and the EXP-0002 command; confirm `verdict.json` reproduces.
2. Check the σ-window departure in §6.1 is the right call, not a silent weakening of
   the Rule 9a floor.
3. Check the view-3 slippage decomposition in §4 — it is the load-bearing reason the
   third view is discounted.
4. Inspect the H=480 coverage exclusion by UTC hour and judge whether the common-sample
   surface is safe to have driven the selection.
5. Confirm no number driving τ\*/H\* came from 2024+.
