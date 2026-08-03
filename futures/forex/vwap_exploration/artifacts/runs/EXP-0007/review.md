# EXP-0007 Results Discussion

- Hypothesis: `HYP-0007` — Reversion tracks the COUNTER CURRENCY's home-market hours, not the ET clock
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review
- Primary metric: pooled within-product-demeaned Spearman(home-market openness,
  per-bet risk-equalised reversion) across the 46 decision slots of the **four
  fresh products**, against a circular-shift null
- Command: `python -u -m futures.forex.vwap_exploration.scripts.hyp_0007_home_market`
- Artifacts: `homemkt.txt`

## Result versus hypothesis

**REJECTED, decisively and in the wrong direction.**

| arm | result |
|---|---|
| 1. `rho_fresh < 0` | **FAIL** — `rho_fresh = +0.0526`, the opposite sign |
| 2. circular-shift null p < 0.05 | **FAIL** — p = 0.7103 |

**The single most telling number in the run:**

| sample | pooled rho |
|---|---|
| consumed three (6E/6B/6J) — the sample that generated the hypothesis | **−0.2342** |
| **fresh four (6A/6C/6N/6S)** | **+0.0526** |

The pattern exists only where it was found. That is the textbook signature of a
post-hoc regularity, and separating fresh from consumed products is exactly what
was supposed to detect it (rule 26). It did.

**Observed block profiles, risk-equalised** (fresh products in bold):

| product | `asia` | `ldn_am` | `overlap` | `ny_pm` | best | predicted best | hit |
|---|---|---|---|---|---|---|---|
| 6E | +0.0522 | +0.0119 | −0.0153 | +0.0069 | asia | ny_pm | no |
| 6B | +0.0202 | +0.0002 | −0.0159 | +0.0104 | asia | asia | YES |
| 6J | −0.0024 | −0.0021 | −0.0151 | +0.0207 | ny_pm | overlap | no |
| **6A** | **+0.0423** | −0.0024 | −0.0046 | +0.0137 | **asia** | **ldn_am** | **no** |
| **6C** | +0.0259 | +0.0133 | +0.0075 | +0.0169 | asia | asia | YES |
| **6N** | −0.0040 | −0.0059 | −0.0021 | +0.0073 | ny_pm | ldn_am | no |
| **6S** | +0.0258 | +0.0147 | +0.0053 | +0.0084 | asia | ny_pm | no |

**6A is the decisive counterexample.** Sydney is *open* during the `asia` block
(openness 0.842 — the second highest in the panel), and `asia` is 6A's
**strongest** reversion block (+0.0423). Its block-level Spearman against openness
is **+0.9487, exact-permutation p = 1.000** — the maximum possible score in the
wrong direction. If the home-market account were right, 6A should have looked like
6J. It looks like 6E.

## Gross, net, baseline, and null comparison

No null spent beyond the declared label nulls (nothing cleared a primary metric).

**Not tradable on any of the seven.** Each product's *best* block, in native units
against the most optimistic post-2016 round trip (1-tick market, fill at the touch
both sides):

| | 6E | 6B | 6J | 6A | 6C | 6N | 6S |
|---|---|---|---|---|---|---|---|
| net $/bet | −8.90 | −11.78 | −7.35 | −8.25 | −9.07 | −8.72 | −10.93 |

Seven of seven, $7-12 under cost per bet, in the single most favourable cell each.

## Regimes, sensitivity, and alternative explanations

**The argmax arm looked like weak support and is worth nothing — a base-rate trap
I built the control for and am glad I did.** Fresh argmax agreement is 1/4, which
against the declared uniform 1/4 null reads as "exactly chance". But it is worse
than that: **`asia` is the best block for 5 of 7 products (71%)**, so "predicting
`asia`" is nearly free. Scored against that observed marginal, the *expected*
number of fresh hits is **1.00 against 1 observed** — literally zero information.
The original 3/3 argmax agreement that generated IDEA-0008 was inflated by the
same base rate and should never have been read as p ≈ 1/64.

**Per-product detail, block level** (exact 24-permutation null):

| | 6E | 6B | 6J | **6A** | **6C** | **6N** | **6S** |
|---|---|---|---|---|---|---|---|
| rho | 0.0000 | −1.0000 | −0.1054 | **+0.9487** | **−0.6325** | **+0.2108** | **0.0000** |
| p | 0.542 | 0.042 | 0.500 | 1.000 | 0.250 | 0.667 | 0.542 |

Two of four fresh products point the wrong way, one is flat, one is directionally
right but not significant. At slot level the fresh four give +0.2908 / +0.0176 /
−0.1529 / +0.0561, none with a circular-shift p below 0.26.

**The volatility control does not rescue it.** Partialling per-slot `rv_60` out:
fresh +0.0211 → +0.0055; all seven −0.0819 → −0.0992. The confound is not hiding a
real effect in either direction.

**What the data actually says, and it partially walks back EXP-0005's reading.**
`asia` is the best block for 5 of 7 products *regardless of home time zone*, which
is closer to the ET-clock account than to anything about the counter currency.
EXP-0005's finding that products genuinely *differ* still stands — 6J and 6N are
the two exceptions and their `asia` cells are actually negative — but they do not
differ in the way home-market hours predict. **Finding C's mechanism is not merely
still open; the leading candidate is now eliminated and the field is emptier than
it was.** Honest current state: the block profile is mostly common across products
(clock-like), with two genuine exceptions that nothing on offer explains.

**Rule 9a, four never-loaded archives.** All seven share the CME FX session with an
empty 17:00-18:00 ET halt and the same loader drops. Coverage is materially worse
on two of the fresh products — 6N bar coverage 0.758 / `rv_60` 0.645 and 6S 0.798 /
0.673, against 6E's 0.971 / 0.941 — so 6N and 6S are the least powered cells and
their flat results carry correspondingly less weight. 6A and 6C, the two that
matter most for the prediction (opposite ends of the openness range), are well
covered at 0.955 / 0.891 bar coverage.

**Rule 23.** 6E/6B/6J reproduce their EXP-0005 risk-equalised block profiles to
4 dp after the four-product code additions.

**Tick eras.** All four new products halved mid-sample, at four different dates —
6C 2016, 6A 2020, 6N 2021, 6S 2022 — verified against the price grid rather than
assumed. **Six of the seven products change tick somewhere in the sample**, so a
cost quoted in ticks is wrong on six of seven.

## Artifact and implementation risks

- **The fresh/consumed split is the whole design** and was declared before the
  four archives were opened. Had all seven been pooled, the headline would have
  been rho = −0.0722 (p = 0.176) — a weak-but-suggestive number that would
  probably have been written up as "directionally consistent, needs more data".
  The split turns that into a clean rejection.
- **The circular-shift null is the right one and it mattered less than expected**:
  both nulls centred near zero (+0.0009 and −0.0004) with the circular one wider
  (sd 0.0935 vs 0.0756), as anticipated. With a real effect the choice would have
  been load-bearing; here both give the same answer.
- **A stated flaw of the hypothesis was confirmed rather than repaired.** HYP-0007
  recorded before the run that the openness definition already mispredicted 6E
  (ranking `ny_pm` above `asia`). I did not adjust the definition to fix that, and
  the fresh data went on to reject it. Adjusting first would have produced a
  fitted definition and a meaningless test.
- **Bug found and fixed mid-run**: `stats.spearman` has an `n >= 10` guard, so
  every block-level (n=4) per-product cell silently returned NaN — and the
  permutation comparison then scored `NaN <= NaN` as False throughout, printing
  p = 0.0000 for all seven, which reads as seven significant results. Replaced
  with an explicit small-n Spearman. A guard that returns NaN into a comparison
  that treats NaN as a *pass* is a dangerous combination and is worth remembering.
- Uniform 08:00-17:00 local home-market hours with real per-currency DST, no
  per-product tuning — so the definition has zero free parameters and cannot have
  been fitted.
- 25/25 core checks pass.

## Builder interpretation

The idea was good enough to be worth the run and is now dead. Three things to
carry:

1. **H_home is rejected on fresh products, wrong-signed, with 6A as an outright
   counterexample.** The mechanism behind finding C is open, and one plausible
   candidate is now removed rather than merely untested.
2. **The generating sample gave −0.2342 and the fresh sample +0.0526.** This is
   the clearest demonstration in this project of why a pattern read off inspected
   data needs uninspected data — and the panel supplied a usable substitute for a
   holdout without spending the sealed 2024-2026 years.
3. **The argmax evidence that motivated the idea was a base-rate illusion.** 3/3
   agreement looked like p ≈ 1/64 under a uniform null; with `asia` winning 71% of
   products, the expected agreement was ~1 of 4 fresh products and exactly 1 was
   observed. **Score an argmax hit rate against the modal-category base rate, not
   a uniform null.**

Nothing changes the project verdict, which is now supported on seven products
rather than two: $7-12 under cost per bet in every product's best cell.

## Independent review

- Review status: reviewed by the builder; no second model was available this
  session, so this is self-review and is labelled as such.
- Objections raised and resolved:
  - *"Four fresh products is a small test — is this underpowered rather than
    negative?"* Partly, and the hypothesis said so in advance. But the result is
    not a weak null: it is the **wrong sign**, with the strongest fresh product
    (6A, well covered, at the extreme of the openness range) scoring the maximum
    possible value in the wrong direction. Underpowered tests give noisy zeros,
    not confident inversions.
  - *"6A and 6N are correlated, so this is closer to three products."* Declared in
    advance and true. It does not rescue the hypothesis: 6A and 6N disagree with
    each other here (block-level +0.9487 vs +0.2108; `asia` strongly positive on
    6A and negative on 6N), so they are not behaving as one observation.
  - *"6N and 6S have poor coverage — should they be excluded?"* Reported rather
    than excluded, because dropping the two weakest cells after seeing the result
    is a selection. Note the two best-covered fresh products (6A, 6C) are also the
    two with the sharpest predictions, and they split 1-1.
  - *"Does this resurrect H_clock, which EXP-0005 weakened?"* Partially, and the
    review says so. Products still differ (EXP-0005's `R(6E)−R(6J)` CI excluding
    zero is reproduced here), but `asia` wins for 5 of 7 regardless of time zone.
    The two accounts are not exhaustive and neither is now adequate.
- Verdict: **REJECTED.** H_home does not survive on fresh products.

## Promotion decision

- `reports/FINDINGS.md`: **yes** — §H1 rewritten from "post-hoc hypothesis" to
  **rejected**, with the fresh-vs-consumed table and the base-rate correction;
  new §K for the seven-product cost floor.
- `MEMORY.md`: **yes** — H2 moves from "leading candidate" to invalidated;
  IDEA-0008 closed; the mechanism recorded as open with the field narrowed.
- `experiments/IDEA_BACKLOG.md`: **yes** — IDEA-0008 closed as tested and
  rejected.
- Shared `LEARNINGS.md`: **yes, as provisional.** Two general, executable lessons:
  (a) *a cross-sectional panel gives you a usable holdout for a pattern read off
  inspected data — score fresh members separately; here the generating sample gave
  −0.23 while the fresh one gave +0.05*; (b) *an argmax agreement rate must be
  scored against the modal-category base rate, not a uniform null* — 3/3 looked
  like p ≈ 1/64 and was worth nothing once `asia` was seen to win 71% of products.
  Both are supported by this run's code and artifacts.
