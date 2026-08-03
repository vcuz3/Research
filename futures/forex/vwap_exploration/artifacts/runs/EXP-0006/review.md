# EXP-0006 Results Discussion

- Hypothesis: `HYP-0006` — RSI(14) carries reversal information beyond the trailing return it is built from
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review
- Primary metric: per-bet mean of fading the RSI(14) extreme vs the bare numerator
  and vs the project incumbent, all at matched selection rate on a common sample
- Command: `python -u -m futures.forex.vwap_exploration.scripts.hyp_0006_rsi`
- Artifacts: `rsi_6E.txt`, `rsi_6B.txt`, `rsi_6J.txt`

## Result versus hypothesis

**REJECTED on all three products.** Arms 1 and 3 fail everywhere; arm 2 fails on
two of three and "passes" on 6B only in a way that is not a win (see below).

| arm | 6E | 6B | 6J |
|---|---|---|---|
| 1. sign/signif — M>0, CI excludes 0 | FAIL | FAIL | FAIL |
| 2. beats its own bare numerator | FAIL | *"PASS"* | FAIL |
| 3. beats the project incumbent | FAIL | FAIL | FAIL |
| 4. partial IC ≥ 50% of raw | PASS | PASS | PASS |

Per-bet means at a matched ~11% selection rate on a common sample (all four
signals and `fwd_30` defined on identical rows):

| signal | 6E | 6B | 6J |
|---|---|---|---|
| `rsi_14` (70/30) | +0.1099 (t +1.13) | −0.0526 (t −0.38) | −0.0173 (t −0.21) |
| `rsi_num_14` — bare NUMERATOR | +0.1148 | −0.1515 | +0.1235 |
| **`dev_past30_z` — INCUMBENT** | **+0.2306 (t +2.03)** | **+0.2462 (t +1.54)** | **+0.0332** |
| `past_30` raw — no normaliser | +0.0415 | +0.4621 (t +2.98) | +0.0561 |

**Arm 2 on 6B is not a win.** RSI (−0.0526) "beats" its numerator (−0.1515) only
by being less negative; both are losses. The arm was written to detect a
denominator that adds value, and a comparison between two negative cells does not
demonstrate that. Recorded as a technical pass and a substantive failure.

**Arm 4 passes everywhere and is the one real thing RSI has.** The partial rank IC
controlling for `past_30` retains 62.6% / 51.2% / 50.9% of the raw IC — so RSI's
14-period *smoothing* genuinely carries information beyond one 30-minute
increment. That dimension is real. It is the *normalisation* that fails.

## Gross, net, baseline, and null comparison

No null spent (project gate — a null is bought only once a real pass clears its
primary metric; nothing cleared). Not tradable by a wide margin: on 6E, gross
+0.1349 units in 2010-2015 against a 2.0-unit optimistic round trip = **−$23.31
per bet**, and +0.0941 against 1.0 unit post-2016 = **−$11.32 per bet**.

## Regimes, sensitivity, and alternative explanations

**The decomposition, on real bars, explains the whole result.** RSI is
algebraically `50 + 50·A_n(dp)/A_n(|dp|)` (verified to 3e-14 in the tests). On
these bars:

| | 6E | 6J |
|---|---|---|
| corr(RSI, its own numerator) | **+0.9732** | +0.9693 |
| corr(RSI, its own denominator) | **+0.0144** | +0.0908 |
| corr(RSI, `past_30`) — one increment | +0.3039 | +0.3028 |

RSI is its numerator to a rank correlation of 0.97. **The denominator separates
essentially nothing**, which is the LEARNINGS 2026-07-27 degenerate-numerator
result reproduced on a new feature: score the bare numerator, and if it matches
the ratio, the ratio is a rescaling. Here it matches on 6E (+0.1148 vs +0.1099)
and beats it on 6J (+0.1235 vs −0.0173).

**Why the normaliser matters, and it is the most transferable part of the run.**
At a matched selection rate the ranking is consistent on all three products:
**incumbent > RSI**. The mechanism is calibration:

| | 6E | 6B | 6J |
|---|---|---|---|
| per-slot selection-rate CV, RSI 70/30 | 0.3637 | 0.3331 | 0.2226 |
| per-slot selection-rate CV, incumbent | 0.0639 | 0.0600 | 0.0632 |
| **ratio** | **5.69x** | **5.55x** | **3.52x** |
| worst/best slot rate, RSI | 4.1x | 4.0x | 2.3x |
| worst/best slot rate, incumbent | 1.3x | 1.3x | 1.3x |

The fixed 70/30 cut fires **6.40% of the time in `asia` and 16.07% in `overlap`**
on 6E (6B 6.83% / 15.06%; 6J 9.30% / 15.06%), while the incumbent is flat near 11%
in every block. RSI's denominator is a *trailing window*, so it lags volatility
transitions and reaches its extremes far more easily once activity picks up. The
minimum slot is `mfo` 479 (ET 01:59, deep Asia) on both 6E and 6B and the maximum
is 989/1019 (ET 10:29/10:59, the overlap) — exactly the prediction written into
the hypothesis before the run.

**And that is precisely the wrong way round for this market.** Finding C
establishes that displacement *continues* in the `overlap` (fading loses there:
−0.0153 / −0.0159 / −0.0151 risk-equalised) and *reverts* in the thin blocks. So a
fixed 70/30 threshold concentrates its bets in the one block where the trade does
not work. RSI is not a weak signal here so much as a **badly calibrated selector**
applied to a signal the project already has a well-calibrated selector for.

Internal consistency worth noting: 6J has the *mildest* miscalibration (CV ratio
3.52x, worst/best 2.3x), and 6J is the product with the flattest Asia liquidity
profile (EXP-0005). The calibration defect tracks the liquidity gradient causing
it.

**A wrinkle reported rather than smoothed over.** The incumbent beats raw
`past_30` on 6E (+0.2306 vs +0.0415) and roughly ties it on 6J (+0.0332 vs
+0.0561) but **loses to it on 6B** (+0.2462 vs +0.4621, t +2.98). So "the
same-slot z-score is always the best normaliser" is *not* supported; what is
supported on all three is the narrower claim that **the incumbent beats RSI**.
Note also these cells sit at a ~11% selection rate, not finding B's `|z| >= 1`, so
they are not directly comparable to §B's headline numbers.

**Neighbouring windows** (rule 18, 6E): n=7 fires 21.8% and gives +0.1533
(t +2.40); n=28 fires 2.5% and gives +0.5276 (t +2.56). These look better than
n=14 — but they are two cells of a three-point sweep on consumed data, at wildly
different selection rates, and the n=28 cell is 2.5% of decisions. Read as a
shape, not an argmax; no claim is made and none should be.

**Standard project controls.** Estimand contrast on 6E: per-bet versus
session-averaged **+2.8929 (t +18.14)** with `corr(session mean, count)` =
−0.4479 — finding D2 reproducing on a new signal. Era stability on 6E: **7 of 14
years positive**, i.e. a coin flip. The shared-decision-bar variant is reported in
the artifact per finding D1.

## Artifact and implementation risks

**The material rule-9a finding: for a RECURSIVE feature, a data gap's damage is
DISPLACED in time, so per-block gap counts do not predict per-block coverage.**
Under a `reset` policy a missing bar does not cost one decision — it costs `n`
more while the Wilder run rebuilds, and on a 30-minute grid `n=14` is ~7 hours.

| 6E block | missing bars | RSI coverage, `bridge` | RSI coverage, `reset` |
|---|---|---|---|
| `asia` | 5.78% | 0.9418 | **0.5773** |
| `ldn_am` | **0.25%** | 0.9975 | **0.7305** |
| `overlap` | 0.07% | 0.9993 | 0.9782 |
| `ny_pm` | 2.83% | 0.9717 | 0.9544 |

`ldn_am` has almost no gaps of its own and the second-worst coverage, because
Asia's gaps are still rebuilding when London opens. Across-block coverage spread
**0.4010 → 0.0575** (6E) and **0.7255 → 0.1835** (6B) when increments are bridged
across missing bars instead of resetting. This is finding G with a lag, and it
generalises to any recursive feature — EMA, Wilder ATR, Kalman filters — on a grid
with holes. Pinned by `tests/test_core.py::a single missing bar costs 1 decision
under 'bridge' but n+1 under 'reset'`, which also asserts the damage is displaced.

Other risks handled:

- **Wilder seeding** (LEARNINGS 2026-07-26): `wilder_rma` uses the textbook n-bar
  SMA seed, not `ewm(adjust=False)` whose `min_periods` masks rather than seeds.
  The tests assert the two differ, so the trap cannot return silently.
- **Common sample.** A first pass compared arms on different denominators because
  each signal had its own NaN pattern; the "matched" rates then matched on
  different bases. Fixed — every arm is now scored on rows where `fwd_30` and all
  four signals are defined (87.82% of 6E decisions), and the arms have identical n.
- **Structurally impossible slots** (`mfo` 29 has no `past_30`, `mfo` 1379 has no
  `fwd_30`) were entering the selection-rate CV as spurious zeros and inflating it
  for both signals. Now excluded by a ≥100-common-decision floor per slot.
- Causality of RSI under truncation, and reset placement, are both pinned by tests.
- 25/25 core checks pass.

## Builder interpretation

The hypothesis was expected to fail and it did, but the run is worth more than the
verdict because it says *which* of RSI's two dimensions failed:

1. **The smoothing is real.** A 14-period Wilder average of the increments carries
   information beyond one increment — partial IC retains 51-63% on all three
   products. Arm 4 is the only arm RSI passes and it passes cleanly.
2. **The normalisation is wrong for this market, and measurably so.** Dividing by
   a trailing-window volatility instead of a causal same-slot dispersion makes a
   fixed 70/30 threshold fire 2.3-4.1x more often in some slots than others
   (CV 3.5-5.7x the incumbent's), concentrated in the `overlap` — the one block
   where finding C says fading loses.
3. **And the ratio is barely a ratio.** corr(RSI, numerator) = 0.97;
   corr(RSI, denominator) = 0.01. Whatever the denominator does to the
   *threshold*, it does almost nothing to the *ranking*.

The constructive reading, and the only thing worth carrying forward: an RSI whose
denominator were the project's causal same-slot scale would be a smoothed
`past_30` with a calibrated threshold, and points 1 and 2 together say that is the
version worth testing. It is still ~8x under cost, so it would be a measurement
rather than a strategy — logged as IDEA-0010 and deliberately **not run**, because
the project verdict does not change and continuing to search a family already
established as non-tradable is not something to do unprompted.

## Independent review

- Review status: reviewed by the builder; no second model was available this
  session, so this is self-review and is labelled as such.
- Objections raised and resolved:
  - *"Arm 2 passed on 6B — is the rejection over-stated?"* No: both cells are
    negative there, so the arm is technically satisfied and substantively empty.
    Called out in the results table rather than counted as support.
  - *"n=7 and n=28 both look better than n=14 — is 14 just a bad choice?"* They
    are two cells of a three-point sweep at very different selection rates on
    consumed history. Reported, explicitly not claimed. Testing them properly needs
    matched rates and a fresh preregistration.
  - *"The incumbent loses to raw `past_30` on 6B — doesn't that undercut the
    same-slot story?"* It undercuts the strong version, and the review says so.
    The claim retained is only that the incumbent beats RSI, which holds 3/3.
  - *"Is the gap-policy choice a researcher degree of freedom that flatters the
    result?"* It is one, which is why both policies are computed and reported.
    `bridge` was chosen because it deletes less and more uniformly, not because it
    scored better; the primary conclusion is a matched-rate comparison unaffected
    by the choice.
- Verdict: **REJECTED.** RSI(14) adds nothing over the signal it is built from;
  its normalisation is measurably worse-calibrated than the project's.

## Promotion decision

- `reports/FINDINGS.md`: **yes** — new §I (the identity, the matched-rate table,
  the calibration result) and §J (the recursive-feature coverage displacement,
  which extends finding G).
- `MEMORY.md`: **yes** — RSI recorded as tested and rejected so it is not
  re-proposed; the recursive-gap lesson recorded as a construction constraint.
- `experiments/IDEA_BACKLOG.md`: **yes** — IDEA-0010, the same-slot-normalised
  smoothed `past_30`, logged and explicitly not run.
- Shared `LEARNINGS.md`: **candidate, not yet promoted.** Two transferable items,
  both single-project so far: (a) *a fixed threshold on a trailing-window-
  normalised oscillator is a time-of-day selector, and the per-slot selection-rate
  CV measures it in one line* — the 2026-07-27 entry extended from session-reset
  features to trailing-window ones, and RSI is the most widely used member of that
  family; (b) *a recursive feature's gap damage is displaced by its memory length,
  so per-block gap counts do not predict per-block coverage*. Recorded in
  `MEMORY.md` promotion candidates.
