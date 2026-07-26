# EXP-0006 Results Discussion

- Hypothesis: `HYP-0003` — repairing the Wilder ATR warm-up (textbook SMA seed) and
  re-selecting the estimator at matched effective memory changes the VEI studies A–F
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: EXP-0005's count-weighted within-slot high-vs-rest momentum contrast,
  both markets
- Data scope: NQ + ES clean Databento RTH 1-min, 2011–2026, 3710 sessions — identical
  sample to EXP-0001..0005. No new data.
- Tests: `python -m futures.nq.vei_exploration.tests.run_tests` → **11/11 pass** (was
  8/8; 4 new, incl. `test_wilder_seed_matches_reference_loop`, which pins the closed-form
  seeded recursion to a literal textbook loop, and
  `test_wilder_alpha_equals_ema_span_2n_minus_1`).

## Result versus hypothesis

**Kill test 1 FIRED on NQ. Study D is downgraded from `confirmed` to
`qualified / inconclusive`.** The momentum-regime contrast survived the repair in sign,
shape and cross-market direction, but lost significance on NQ at the preregistered cut.
Study A's attribution is replaced. Studies B, C and E are unchanged in verdict. One
EXP-0005 corollary is **reversed**.

### Rule 23 — reproduction before interpretation

Every legacy-seed row reproduced its published number before any repaired number was read:

| statistic | published | legacy row this run |
|---|---|---|
| Study A `wilder_10_50` NQ (mean/AC1/whipsaw/IC) | 0.893 / 0.549 / 0.229 / +0.1572 | identical |
| Study A `wilder_10_50` ES | 0.924 / 0.506 / 0.257 / +0.1950 | identical |
| Study D high-regime corr NQ / ES | +0.104 / +0.096 | +0.1041 / +0.0957 |
| Study F within-slot contrast NQ | +0.1098 [+0.0251,+0.1715] | +0.1098 [+0.0253,+0.1719] |
| Study F within-slot contrast ES | +0.1033 [+0.0208,+0.1681] | +0.1033 [+0.0239,+0.1676] |
| EXP-0004 primary cell NQ / ES (Sharpe) | +0.015 (t 0.06) / −0.073 | +0.015 (t 0.06) / −0.073 |

CI endpoints differ only in bootstrap jitter (same seed, different draw order). **PASS.**

### PRIMARY METRIC (D / F)

`F_term_structure_threshold_control_{NQ,ES}.csv`:

| cut | NQ n_high | NQ diff [90% CI] | ES n_high | ES diff [90% CI] |
|---|---|---|---|---|
| LEGACY seed, absolute >1.10 | 2674 | +0.1098 [+0.0253,+0.1719] | 3168 | +0.1033 [+0.0239,+0.1676] |
| **repaired, absolute >1.10** | 2854 | **+0.0690 [−0.0068,+0.1339]** | 3356 | **+0.0857 [+0.0092,+0.1465]** |
| repaired, matched-rate | 2674 | +0.0872 [+0.0090,+0.1444] | 3168 | +0.0839 [+0.0050,+0.1534] |

- **Kill test 1** ("if the within-slot contrast loses significance on EITHER market, D is
  downgraded to inconclusive"): NQ repaired absolute is **+0.0690 [−0.0068, +0.1339] — CI
  includes 0** → **FIRED.**
- **Kill test 3** (threshold confound): on NQ the result is significant at the
  matched-rate cut but not at the absolute cut → must be reported as
  **threshold-sensitive**. ES is significant at both.
- Pooled Study D (`D_regime_dynamics_regime_*.txt`) agrees: NQ +0.104→+0.0673 (CI now
  includes 0), ES +0.096→+0.0749 (CI just excludes 0).

**Honest characterisation.** The effect did not vanish — same sign on both markets, point
estimate 63% (NQ) / 83% (ES) of legacy, and every *shape* result replicates. What changed
is that the better-measured feature yields a **smaller** contrast, i.e. part of Study D's
original size was riding on the warm-up artefact. HYP-0003's stated prior was that a
better-measured feature should give an equal or larger effect, so this is evidence
against the finding, and the preregistered downgrade stands.

## Gross, net, baseline, and null comparison

### A — corrected: memory dominates; the warm-up repair is worth ~+0.05 IC

Full table in `A_smoothing_smoothing_{NQ,ES}.txt`. Forward-30m-vol IC:

| variant | defined | mean | AC1 | whipsaw | IC NQ | IC ES |
|---|---|---|---|---|---|---|
| SMA 10/50 | 44516 | 0.973 | −0.011 | 0.456 | +0.060 | +0.069 |
| Wilder 10/50 **legacy seed** | 44516 | 0.893 | 0.549 | 0.229 | +0.157 | +0.195 |
| Wilder 10/50 **repaired seed** | 44516 | 0.917 | 0.441 | 0.245 | **+0.202** | **+0.207** |
| SMA 19/99 (com-matched to Wilder) | 37099 | 0.956 | 0.330 | 0.334 | +0.186 | +0.188 |
| Wilder 5/25 (com-matched to SMA 10/50) | 48226 | 0.947 | 0.145 | 0.365 | **+0.035** | **+0.060** |
| EMA 19/99 (α-identical to Wilder 10/50) | 37099 | 0.921 | 0.470 | 0.270 | +0.242 | +0.249 |
| Wilder 20/100 | 37099 | 0.860 | 0.685 | 0.150 | **+0.396** | **+0.353** |

1. **Memory, not estimator form.** At matched centre-of-mass a plain SMA (19/99) reaches
   +0.186/+0.188, level with Wilder 10/50. Matched the other way, Wilder 5/25 falls to
   +0.035/+0.060 — *below* the SMA it nominally beat. EXP-0001's attribution is withdrawn.
2. **The warm-up repair is real and free**: same 44516 decisions, IC +0.157→+0.202 (NQ),
   +0.195→+0.207 (ES). Note AC1 *falls* (0.549→0.441): the legacy series was partly
   autocorrelated because consecutive bars shared a common contaminating seed, so the old
   "persistence" headline was itself inflated by the defect.
3. **Open lead, flagged not adopted.** `wilder_20_100` is far ahead on IC (+0.396/+0.353
   at the same 37099 decisions as the 19/99 cells, so not a sample effect), and IC rises
   monotonically with memory across every cell. **Caveat that stops adoption:** Study B
   shows the vol LEVEL predicts forward vol at IC +0.86, so lengthening the numerator's
   memory makes VEI progressively more level-like — `IC_fwdvol` may be rewarding "less of
   a ratio" rather than a better ratio. That makes `IC_fwdvol` a poor selection metric for
   a ratio feature and puts Study A's original metric choice in question too. Canonical
   **stays Wilder(10/50)** so this run remains a single-variable change (warm-up only).

### B — verdict unchanged, increment smaller

`IC(level)` +0.860/+0.848. VEI's own IC rises with the repair, but its **incremental** ΔR²
over the level FALLS: NQ +0.004→**+0.0017**, ES +0.002→**+0.0006**. Conclusion unchanged
and slightly strengthened: for vol forecasting/sizing use the level; the ratio adds a
sliver, now thinner.

### C — verdict unchanged, sub-claim withdrawn

Still **no intraday coiled spring**. But the legacy sub-claim ("expansion ratio is LOWEST
at low VEI and RISES with VEI") does not survive: repaired quintile expansion ratios are
flat and non-monotone (NQ H=30: 0.958 / 0.944 / 0.952 / 0.968 / 0.960; ES: 0.988 / 0.960
/ 0.967 / 0.985 / 0.977). Cleaner repaired statement: the expansion ratio is essentially
**independent of VEI** (~0.94–0.99 everywhere — intraday vol decays regardless of regime),
while forward vol *level* still rises monotonically with VEI (persistence). The legacy
monotonic rise was itself partly the warm-up artefact.

### E / EXP-0004 — verdict UNCHANGED (REJECT)

| cell | NQ Sharpe (day t) | ES Sharpe (day t) |
|---|---|---|
| legacy, high>1.10, H=30 | +0.015 (0.06) | −0.073 (−0.28) |
| repaired, high>1.10, H=30 | +0.134 (0.52) | −0.050 (−0.19) |
| repaired, matched-rate | +0.232 (0.89) | +0.030 (0.12) |

Better, but nowhere near the preregistered `day_t ≥ 2.0` gate. **KILL-TEST 1 REJECT on
both markets**, so no nulls were spent (standing rule) — the matched-count random null and
Null C remain **unspent**. The gross dose-response is if anything *sharper* under the
repair (NQ high gross/trade +0.96 → +1.39 pt; low regime still ≈0/negative), so the
mechanism reads cleanly while the edge still does not monetize. Per HYP-0003's
multiple-testing note these improved numbers are post-hoc on consumed history and are
**not** evidence for the edge.

## Regimes, sensitivity, and alternative explanations

Surviving from F, unchanged:

- **The time-of-day audit is untouched and slightly stronger**: within-slot retains
  **111% (NQ) / 117% (ES)** of the pooled contrast. Whatever D is, it is still not a
  clock effect.
- **Front-loading replicates**: high-regime corr peaks at H=5 (+0.148 NQ / +0.146 ES),
  decaying to ~+0.07 by H=120/close (constant-sample view). EXP-0004's "strengthens with
  hold" stays corrected.
- **VR(q) within-slot difference ≈0** (NQ +0.009/+0.022/−0.001/−0.015 at q=2/5/10/30) —
  a drift tilt, not a smoother path. Replicates.
- **The 13:30 slot is the standout and now more extreme**: corr_high +0.3768 (NQ, n=246) /
  +0.4245 (ES, n=269), rest-corr also elevated (+0.047/+0.043). Unexplained; both markets.
- **F4**: with memory identified as the axis, `10_100` + past_win=30/60 is now the best
  cell on both markets (NQ +0.0727/+0.0751, ES +0.0883/+0.0636), edging out `10_50`.
  `past_win=10` still kills the effect in every variant — past_win remains load-bearing.

### REVERSAL — EXP-0005 corollary (a) does not survive

Legacy F3d concluded "de-seasonalising DESTROYS information; VEI's info is in its ABSOLUTE
level; do NOT fix its intraday drift." Under the repaired feature that inverts:

| | NQ raw level | NQ slot percentile | ES raw level | ES slot percentile |
|---|---|---|---|---|
| legacy | +0.100 | +0.069 | +0.086 | +0.068 |
| repaired | +0.0682 [−0.0143,+0.1493] | **+0.0798 [+0.0087,+0.1482]** | +0.0642 [−0.0155,+0.1423] | +0.0711 [−0.0021,+0.1486] |

The causal same-slot percentile is now **equal or better** than the raw level on both
markets, and on NQ it is the only one of the two whose CI excludes 0. Mechanism: the
legacy warm-up bias was itself time-of-day dependent (worst early in the session, where
the long ATR is least populated), which artificially advantaged the raw level over a
de-seasonalised one. **The "do not de-seasonalise" instruction is withdrawn** — it was an
artefact of the bug it was measured through.

### Alternative explanations considered

- *Is the downgrade just the threshold shifting?* Addressed by kill test 3's matched-rate
  cut, which holds selection count fixed at the legacy value. The contrast is still below
  legacy at matched count (+0.0872 vs +0.1098 NQ), so the **shrinkage** is a feature
  effect, not a threshold effect. The **significance** of the NQ cell, however, IS
  threshold-sensitive — hence "qualified" rather than "dead".
- *Is the repair itself wrong?* `test_wilder_seed_matches_reference_loop` pins the closed
  form to a literal textbook loop, per session, on both exponential methods, including a
  ragged session shorter than the window. The legacy path is retained and reproduces all
  five prior experiments to 4 decimals.
- *Is this a power problem?* Partly — the high-VEI cell is 2854/3356 decisions and the
  per-slot detail swings from +0.26 to −0.22 on n≈57 cells; the aggregate is dominated by
  the large late slots. But power is unchanged from EXP-0005; only the feature changed.

## Artifact and implementation risks

**Artifact immutability was broken.** The re-run wrote into `A_smoothing/`,
`BC_vol_forecast/`, `D_regime_dynamics/`, `F_term_structure/` and `EXP-0004/`,
overwriting the EXP-0001..0005 outputs. The project is untracked by git, so the originals
are not recoverable. Mitigation: (a) every legacy number is reproduced by the
`seed='first'` rows inside this run and is recorded in the ledger and
`reports/FINDINGS.md`; (b) this run's outputs are snapshotted in this directory. Going
forward, re-runs must write to a new `EXP-XXXX/` directory rather than the study
directory, and this project should be committed to git.

Other: `IC_fwdvol` is retained as Study A's metric but is now known to be biased toward
level-like (long-memory) variants — see the `wilder_20_100` caveat above. Any future
estimator selection needs a metric that is not monotone in "how much this ratio resembles
the vol level".

## Builder interpretation

The reviewer's objection was correct on all three checkable points, and the repair
mattered more than expected: it did not merely tidy the feature, it removed a chunk of the
project's headline finding. Net position after EXP-0006 — VEI's role as a **momentum
regime selector is qualified, not confirmed**: real and same-signed on both markets, but
NQ's CI straddles zero at the preregistered cut and the whole effect is smaller than
published. Everything already negative (B's marginal increment, C's no-spring, E's
REJECT) is unchanged or slightly more negative. The one genuinely new positive finding is
that **effective memory is the operative axis** of the estimator choice, with
`wilder_20_100` a strong but confounded-looking lead that needs a better selection metric
than `IC_fwdvol` before anyone acts on it.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: **updated** — section A replaced (A-corrected/A-corrected(b) now
  backed by this run); B/C/D/F amended; the EXP-0005 de-seasonalisation corollary marked
  REVERSED; Study D status changed to qualified.
- `MEMORY.md`: **updated** — Study D downgraded, canonical-VEI note, next actions.
- Shared `LEARNINGS.md`: the estimator-memory / `ewm` warm-up entry added 2026-07-26 is
  now additionally supported by this run's downstream effect (a headline finding shrank
  when the warm-up was repaired), which strengthens rather than changes it.
