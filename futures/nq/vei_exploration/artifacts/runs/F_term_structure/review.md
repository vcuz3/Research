# EXP-0005 — Study F: momentum term structure + time-of-day audit (HYP-0002)

- Builder: Claude (Opus 5), 2026-07-26
- Scripts: `scripts/s4_term_structure.py` (Study F), `scripts/hyp_0001_momentum_vei.py`
  (H=60 erratum). Descriptive — no trading claim in Study F, so no Null C (rule 17
  does not apply to a measurement with no P&L claim).
- **Verdict: Study D SURVIVES the time-of-day audit intact on both markets
  (HYP-0002 outcome 3, full survival). Study E's "the effect strengthens with hold"
  reading is CORRECTED — the predictive information decays with horizon; the H=60
  net-P&L gain was cost amortisation, not more signal. The published H=60 figure was
  also a 2-unit book; corrected below.**

## Reproduce

```
python -m futures.nq.vei_exploration.tests.run_tests
python -u -m futures.nq.vei_exploration.scripts.s4_term_structure {NQ|ES}
python -u -m futures.nq.vei_exploration.scripts.hyp_0001_momentum_vei real {NQ|ES}
```

Rule 23: EXP-0004 reproduced exactly (to the published 4 decimals) before any engine
change — `momo_all` netR −160.95, `low` −162.92, `high` +0.68, H60 netR +28.07 /
Sh +0.449 / t +1.72.

---

## F3c — THE AUDIT (primary metric): Study D is not a clock effect

The concern was real and large. Wilder VEI(10/50) is built from a session-reset ATR
whose long leg is anchored to the volatile open, so it drifts upward all day (NQ slot
mean 0.745 at 10:30 → 1.165 at 15:59) and the fixed cut `VEI>1.10` fires on ~1% of
morning decisions but 19–64% of late ones. **88.9% (NQ) / 87.4% (ES) of all high-VEI
decisions sit in the 14:00-and-later slots, which are only 31% of the clock.**

But the composition is not the cause. Correlating *inside* each of the 13 decision
slots and only then count-weighting:

| | pooled high | pooled rest | pooled diff | **within-slot diff [90% CI]** | retained |
|---|---|---|---|---|---|
| NQ | +0.1041 | +0.0001 | +0.1040 | **+0.1098 [+0.0251, +0.1715]** | 106% |
| ES | +0.0957 | −0.0022 | +0.0979 | **+0.1033 [+0.0208, +0.1681]** | 105% |

The contrast keeps its sign, its significance (CI excludes 0), and essentially all of
its magnitude on both markets. **HYP-0002 outcome 3: Study D stands as written.** If
anything the pooled figure slightly *understates* it.

Per-slot detail (`slot_contrast_*.csv`) shows the effect is present at nearly every
slot rather than concentrated: the morning cells, where high-VEI is genuinely rare, are
the strongest (NQ 10:30–12:30 diffs +0.23…+0.35 on n=37–78; ES +0.10…+0.24 on n=55–104),
and 13:30 is the single largest cell on both markets (+0.353 NQ / +0.373 ES). Two slots
go the other way on both or one market (13:00, and 14:30 on NQ). Small cells, so read
the weighted aggregate, not individual slots — but the pattern that a *rare* expansion
is more informative than a *routine* one is consistent across markets.

**Robustness of the primary statistic.** Cells thinner than `MIN_CELL` are dropped
before weighting, so the result was checked across that threshold. The within-slot
difference is flat from `MIN_CELL` 0 → 200 (NQ +0.094…+0.110; ES +0.097…+0.103) and
still clearly positive at `MIN_CELL`=300, which discards every morning slot and leaves
only the four largest late cells (NQ +0.073, ES +0.068). So the audit does not depend on
the small, high-correlation morning cells: it holds even when measured purely inside the
late slots where high-VEI is routine.

Independently, F3a/b finds a genuine time-of-day effect that has nothing to do with VEI:
unconditional corr(past30, fwd30) is ≈0 at every slot except **13:30 (+0.101 NQ /
+0.108 ES)** and **15:30 (+0.078 / +0.084)**, agreeing across markets. So both effects
are real and roughly additive — the more interesting of the possible outcomes.

## F3d — de-seasonalising VEI DESTROYS information (raw level wins)

At matched selection count (NQ K=2604 = 6.5%; ES K=3097 = 7.7%), raw level vs a causal
same-slot percentile rank (trailing 90 sessions, min 60):

| | raw level | slot percentile |
|---|---|---|
| NQ | **+0.1000 [+0.0180, +0.1863]** | +0.0687 [−0.0077, +0.1528] |
| ES | **+0.0861 [+0.0020, +0.1615]** | +0.0682 [−0.0037, +0.1417] |

The percentile is weaker on both markets and its CI includes 0 on both. The
selection-share table shows why the comparison had to be at matched count: the
percentile by construction spreads its picks evenly across slots (~9–10% each) while
the raw level concentrates them late. Conclusion: **VEI's information is in its
ABSOLUTE level, not in how unusual that level is for the hour.** Time of day is neither
the cause of the effect nor a useful normalisation of the feature — a genuinely
counter-intuitive result, and the practical reason not to "fix" VEI's intraday drift.

## F1 — term structure: the information is FRONT-LOADED and decays (corrects E)

Long horizons only exist for early decision slots, and high-VEI is rare early, so an
all-available decay curve confounds horizon with time of day. The constant sample
(decisions at 14:00 or earlier, which admit every horizon) is the composition-free read.
High regime, corr(past 30m, fwd H):

| H | 5 | 10 | 15 | 30 | 60 | 90 | 120 | close |
|---|---|---|---|---|---|---|---|---|
| NQ | **+0.177** | +0.168 | +0.095 | +0.161 | +0.131 | +0.070 | +0.068 | +0.029 |
| ES | **+0.170** | +0.128 | +0.073 | +0.150 | +0.150 | +0.060 | +0.054 | +0.025 |

Low and calm regimes are flat at ≈0 across every horizon on both markets.

This **corrects EXP-0004's interpretation**. That review read "the effect strengthens
with hold — H=60 gives Sharpe +0.449" as evidence that the high-VEI trend persists
beyond 30 minutes. In information terms it does not: predictability peaks at 5–10
minutes, holds through 30–60, and is gone by 90–120 and to-close. What improves with a
longer hold is the *cost ratio* — a fixed 0.35 pt (NQ) round trip amortised over a
bigger move — not the signal. Practical consequence: going longer buys cost efficiency,
not edge, and there is no basis for expecting further gains past ~60 minutes. (The dip
at H=15 on both markets is reproducible but unexplained; not over-read.)

## F2 — variance ratio: no regime difference once time of day is matched

VR(q) of the forward 60-min 1-min return path. Pooled figures look dramatic — NQ VR(30)
0.911 in high-VEI vs 0.959 in the rest — but a 60-min forward window excludes the late
slots where high-VEI concentrates, so that gap is composition. The within-slot paired
difference is ≈0 everywhere:

| q | 2 | 5 | 10 | 30 |
|---|---|---|---|---|
| NQ within-slot diff | +0.011 | +0.029 | +0.005 | +0.001 |
| ES within-slot diff | +0.016 | +0.039 | +0.020 | +0.020 |

So F2 does **not** corroborate F1 — it measures something different and finds nothing.
The honest synthesis: VEI predicts the *alignment of the aggregate forward move with the
aggregate past move*, and does **not** change the minute-to-minute character of the
forward path. All regimes are mildly anti-persistent (VR<1), consistent with
`hurst_explore`'s coarse-scale anti-persistence finding. "Momentum regime" means a
drift tilt, not a smoother trend.

## F4 — robustness: the canonical parameters sit at a local optimum

At matched selectivity (each variant takes its top 6.6% NQ / 7.8% ES), corr in the high
cell:

| VEI | past_win 10 | past_win 30 | past_win 60 |
|---|---|---|---|
| NQ (5,20) | +0.050 | +0.068 | +0.031 |
| NQ **(10,50)** | +0.031 | **+0.104** | +0.086 |
| NQ (10,100) | +0.057 | +0.087 | +0.051 |
| ES (5,20) | +0.039 | +0.075 | +0.054 |
| ES **(10,50)** | +0.003 | **+0.096** | +0.078 |
| ES (10,100) | +0.024 | +0.085 | +0.042 |

(10,50) with past_win=30 is the best cell on both markets, and past_win is clearly
load-bearing (a 10-min trailing return roughly kills the effect: +0.031 NQ / +0.003 ES).
The trailing-return window and the regime window being matched at 30/30 is a real
feature of the construct, not an arbitrary default. Rest-cell correlations are ≈0
throughout, so no variant is merely re-slicing a pooled effect.

## Erratum — the EXP-0004 H=60 estimand (rule 13)

A 60-minute hold on a 30-minute decision clock fills a second bet before the first
exits, so the published H=60 row described a book running **up to two concurrent
positions**, while HYP-0001 declares non-overlapping single-position bets and `score()`
sums per-bet R per day as one unit. `core/strategy.py::simulate` now enforces
non-overlap by default (`allow_overlap=True` to opt into concurrency), guarded by
`tests/test_strategy.py::test_no_overlap_is_the_default`.

| cell | NQ n | NQ netR | NQ Sharpe (t) | ES n | ES netR | ES Sharpe (t) |
|---|---|---|---|---|---|---|
| `H60_overlap2u` (as published) | 2636 | +28.07 | +0.449 (1.72) | 3102 | +26.43 | +0.357 (1.37) |
| **`H60_1unit`** (declared estimand) | 2229 | +22.83 | +0.442 (1.70) | 2604 | +32.67 | **+0.526 (2.02)** |
| `H60_clock60` (60-min clock) | 1628 | +12.01 | +0.288 (1.10) | 1940 | +12.85 | +0.249 (0.96) |

The correction does **not** change the EXP-0004 verdict. The preregistered primary cell
(`high>1.10`, H=30) is untouched — n=2636/3102, NQ Sharpe +0.015, ES −0.073 — so
kill-test 1 still fails and the nulls remain correctly unspent. H=60 remains a post-hoc
horizon (rule 26), so the ES `H60_1unit` t=2.02 is **not** a pass: it is a
sensitivity cell on consumed history, and F1 now shows the horizon gain is cost
amortisation rather than signal. `H60_clock60` is materially weaker than either, so the
apparent horizon benefit also depends on keeping the 30-min decision cadence.

Side effect worth recording: the guard also removed **2** NQ bets from the `all`/`low`
cells at H=30 (netR −160.95 → −161.19). `simulate` works in bar-index space, so on a
session with missing minutes a nominal 30-minute hold spans fewer than 30 index
positions and can genuinely overlap the next decision. ES was unaffected.

## Alternative explanations considered

- *"The whole thing is time of day."* Directly tested and rejected (F3c), on both
  markets, with the contrast retaining >100% of its pooled size.
- *"The morning cells are cherry-picked."* They are small (n=37–104), which is why the
  primary is the count-weighted aggregate over all slots, not a morning subset. The
  aggregate is dominated by the large late cells and is still +0.10.
- *"The percentile result is a lookback artefact."* Possible in principle; the
  lookback (90 sessions, min 60) is the workspace's standard band window, and the raw
  level wins on both markets by a similar margin.
- *F3c's within-slot conditioning uses full-sample slot membership (a two-sided
  statistic). That is legitimate here because it is an attribution control that never
  selects a trade; the causally-constructible analogue is F3d, which is strictly
  past-only.*

## Independent review

- Reviewer: unassigned
- Status: not-reviewed
- Open items: (1) confirm the within-slot count-weighting in
  `s4_term_structure.py::_slot_contrast` (the `MIN_CELL` sensitivity is reported above
  and the conclusion is stable, but the weighting scheme itself is worth a second read);
  (2) confirm the constant-sample construction in F1 (`mfo + 120 <= 389`);
  (3) confirm `allow_overlap=False` is a no-op at H<=30 on complete sessions (asserted
  in the test) and that the 2-bet NQ change is the missing-minute case described above.
