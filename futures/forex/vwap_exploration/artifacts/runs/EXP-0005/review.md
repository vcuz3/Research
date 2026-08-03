# EXP-0005 Results Discussion

- Hypothesis: `HYP-0005` — The liquidity-block shape tracks LIQUIDITY, not the ET clock (6J dose test)
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review
- Primary metric: risk-equalised, volatility-matched `asia` − `overlap` contrast
  `R(6J)` against the 6E/6B benchmark `B`, session block-bootstrap 95% CI
- Command: `python -u -m futures.forex.vwap_exploration.scripts.hyp_0005_liquidity_vs_clock`
- Artifacts: `liqclock.txt`

## Result versus hypothesis

**Preregistered verdict: arm 3 — INCONCLUSIVE.** Nothing is claimed for either
account on the declared metric.

| | R_adj | boot95 CI |
|---|---|---|
| 6E | +0.0589 | [+0.0178, +0.0997] |
| 6B | +0.0073 | [−0.0677, +0.0712] |
| **6J** | **−0.0038** | **[−0.0331, +0.0255]** |

`B = +0.0331`, gate `0.60·B = +0.0198`. `R(6J)` is **−0.11×B** — the point
estimate is not merely attenuated but marginally *inverted* — yet its CI contains
both 0 and the gate, so arm 3 fires and pre-empts arm 1 exactly as written. I am
honouring that rule rather than reading the point estimate as a result.

**Rule 23**: 6E and 6B reproduce EXP-0004 to 4 dp (+0.5657 / +0.2210) after the
per-product-unit change; the artifact files are byte-identical on re-run.

**Rule 9a**, on a never-before-loaded archive: 6J has 3,437 sessions, 0 duplicate
or out-of-order timestamps, 0 OHLC violations, 0 zero-volume bars, an empty
17:00–18:00 ET halt, and the same 53 roll / 1 short session drops as 6B. Its Asia
`rv_60` coverage is **0.867 vs 6B's 0.703** — the premise check passes, and in the
declared direction.

## Gross, net, baseline, and null comparison

No null spent (project gate: a null is bought only once a real pass clears its
primary metric). Nothing here is tradable: the largest 6J cell is +0.0207 in
risk-equalised units, and the native `C_adj` of +0.0516 units is **$0.65/bet**
against a round trip of two 5e-7 ticks = **$12.50**. That is ~19x under cost,
worse than 6E's ~8x.

## Regimes, sensitivity, and alternative explanations

**The declared dose held.** Asia/overlap volume intensity: 6E 0.129, 6B 0.132,
**6J 0.314** — 6J's Asia is 2.40x less thin, matching the 2.4x quoted in the
hypothesis before the run.

**Robustness on 6J**: `R_adj` spans −0.0038..−0.0117 across 3 volatility measures
× 3 stratum counts, never positive, with `n_eff` retention of **90.4–92.4%** — far
better common support than 6E/6B got (65% / 60%), because 6J's blocks are less
volatility-separated. The volatility ratio moves 0.646 → 0.903..0.949. The control
worked well here; it is the *estimate* that is imprecise, not the machinery.

**Post-hoc (i): the better-powered comparison the kill test failed to declare.**
Arm 3 fired because `R(6J)`'s CI touches the gate, but the sharper question is
whether 6J differs from the benchmark. Bootstrapping the difference directly:

- `R(6E) − R(6J) = +0.0627` **[+0.0103, +0.1107] — CI excludes zero.**
- `R(6B) − R(6J) = +0.0111` [−0.0708, +0.0711] — not distinguishable.
- `B = +0.0331` lies **outside** `R(6J)`'s interval (upper bound +0.0255).

So 6J is measurably unlike 6E, and indistinguishable from 6B only because 6B is
itself weak. **This weakens H_clock**: a pure ET-clock account predicts 6J should
resemble the other two, and against the strongest benchmark it demonstrably does
not.

**The block-free arm agrees.** 6E and 6B share a liquidity clock, so their mutual
correlation is the benchmark for what "the clock explains it" looks like:
Spearman **+0.6458**. 6J against them: **+0.2825** (6E) and **+0.4889** (6B) —
below the benchmark on both. Pearson is flat across all three pairs
(+0.69..+0.76), so this separation is visible only in the rank view (LEARNINGS
2026-07-31a again; reported both ways). Per-slot P&L against each product's own
per-slot liquidity share is negative on all three (−0.38 / −0.23 / −0.23; pooled
within-product-demeaned −0.2514), which points the H_liquidity way.

**But the crude block-volume version of H_liquidity is not supported either, and
this is the run's sharpest negative.** 6J's `ny_pm` block has volume intensity
**0.82x — identical to 6E's 0.80x and 6B's 0.82x** — yet carries 6J's strongest
reversion (+0.0207, t +3.2) against their +0.0069 / +0.0104. Identical CME volume,
2–3x the effect. **Total contract volume is not the operative liquidity measure.**

**Post-hoc (ii): a pattern that fits all 12 cells.** Every product's strongest
reversion sits in the block where the **counter currency's own home market is
shut**, not in a fixed ET block:

| product | counter-ccy home | its night block | R there | overlap cell | argmax |
|---|---|---|---|---|---|
| 6E | Frankfurt/London | `asia` | +0.0522 (t +4.7) | −0.0153 (t −2.0) | `asia` ✓ |
| 6B | London | `asia` | +0.0202 (t +1.2) | −0.0159 (t −2.2) | `asia` ✓ |
| 6J | Tokyo | `ny_pm` | +0.0207 (t +3.2) | −0.0151 (t −1.8) | `ny_pm` ✓ |

ET 12:00–16:59 (`ny_pm`) is Tokyo 02:00–07:00; ET 18:00–02:59 (`asia`) is London
23:00–07:59. The two families are the same rule in different time zones. And the
`overlap` cell — the one block where *both* home markets are open — is
**near-identical on all three products** (−0.0153 / −0.0159 / −0.0151, t −2.0 /
−2.2 / −1.8), an invariance the block-volume account does not predict.

This reconciles everything: reversion appears to need the counter currency's home
dealers to be absent, and CME volume during Tokyo's night is high because of the
US close, not because JPY liquidity is present.

**It is post-hoc, read off 12 cells after seeing them, and is recorded as a
hypothesis rather than a finding.** It also has a cheap decisive test: the wider
panel is already downloaded and makes *differing* per-product predictions — 6A/6N
home markets fall inside `asia`, 6S inside `ldn_am`/`overlap`, 6C inside
`overlap`/`ny_pm`. Logged as IDEA-0008.

**Mirror arm** (volatility standardised within blocks): 6E +0.0068 (volatility
dies), 6B −0.0596 and 6J +0.0174 (volatility survives). 6E remains the odd one
out; the EXP-0004 cross-product mechanism disagreement is unresolved and now has a
third data point on the *other* side.

## Artifact and implementation risks

- **A per-product reporting unit was required and is a real trap.** 6J quotes
  dollars per YEN near 0.0091; the project's 1e-4 unit would have made every 6J
  number ~100x smaller and silently incomparable. Its unit is 1e-6, chosen so
  12,500,000 × 1e-6 = **$12.50**, exactly a 6E pip and exactly one pre-2015 tick.
  Pinned by `tests/test_core.py::6J's reporting unit is worth the same dollars`,
  which also asserts 6E/6B are unchanged.
- **This is NOT the conventional USD/JPY pip** (0.01 yen). The futures quote is
  the reciprocal of the spot convention, so 0.01 yen maps to a price-level-
  dependent ~8.3e-8 and cannot be a fixed reporting unit at all. Documented in
  `core/data.py`.
- **6J's tick halved mid-2015**, verified against the price grid rather than
  assumed (≥0.9998 of closes on the 1e-6 grid through 2015-05, 0.842 in 2015-06,
  ~0.51 from 2015-07). 2015 is a transition year assigned the finer tick — the
  *less* conservative choice for a cost floor, flagged wherever a 6J cost appears.
- **Cross-product magnitudes are never compared in native units.** The primary is
  risk-equalised (P&L over the decision's own same-slot displacement scale), the
  equal-risk estimand rule 12 names as the default.
- A definitional slip was caught and fixed mid-run: liquidity shares were first
  computed over the 46 decision minutes rather than all bars, shifting 6B's ratio
  ~7% from the premise table declared in the hypothesis. Now computed over all
  bars, matching the declaration.
- 21/21 core checks pass.

## Builder interpretation

The test I designed did not answer the question I asked, and it produced a better
question. Three things, kept separate:

1. **On the declared metric, nothing is established.** `R(6J)`'s interval is too
   wide. The gate at `0.60·B` was set against a benchmark half-built from 6B,
   whose own contrast is indistinguishable from zero — so `B` was a noisier
   reference than assumed when the hypothesis was written. That is a design fault
   in my kill test, not a property of the market, and it is the main thing to fix
   before the panel run: **benchmark against a product whose estimate is actually
   precise, or against a pooled estimate carrying its own CI.**
2. **H_clock is nonetheless weakened** by two arms that did have power: 6J differs
   from 6E with a CI excluding zero, and 6J's per-slot rank profile agrees with the
   others less than they agree with each other.
3. **The crude block-volume H_liquidity is also weakened**, by 6J's `ny_pm` cell
   having identical CME volume intensity to 6E/6B's and 2–3x the reversion. What
   survives both is a *refinement*: the relevant liquidity is the counter
   currency's home-market liquidity, which CME contract volume does not measure.

Nothing here changes the project verdict. 6J is ~19x under its cost floor, worse
than 6E. Finding C's status is unchanged — confirmed on 6E, provisional on 6B —
but its *mechanism* note must now read "open", because the leading candidate is no
longer the one written in `MEMORY.md`.

## Independent review

- Review status: reviewed by the builder; no second model was available this
  session, so this is self-review and is labelled as such.
- Objections raised and resolved:
  - *"Arm 3 pre-empting arm 1 discards a clearly-signed point estimate."* Yes, and
    deliberately. The rule was written before the data was loaded; overriding it
    after seeing −0.0038 would be exactly the goalpost move preregistration exists
    to prevent. The point estimate is reported prominently and the better-powered
    difference test is labelled post-hoc.
  - *"The home-market pattern is 12 cells and three products — is it anything?"*
    Unknown, which is why it is filed as IDEA-0008 with a preregisterable panel
    test rather than written into FINDINGS as a result. Its one non-trivial
    feature is that it predicts the `overlap` invariance, which is not what it was
    constructed to explain.
  - *"Could 6J's `ny_pm` result be the CME close rather than Tokyo's night?"* Not
    separable here — they are the same hours. The panel test separates them: 6A
    and 6N share 6J's Asia-region home market but not its ET profile.
- Verdict: **INCONCLUSIVE on the primary metric; H_clock weakened; block-volume
  H_liquidity weakened; a refined mechanism logged for test.**

## Promotion decision

- `reports/FINDINGS.md`: **yes** — new §H recording the three-product block table,
  the inconclusive verdict, and both weakened accounts. Finding C's status
  unchanged; its mechanism note updated to "open".
- `MEMORY.md`: **yes** — the inventory reading for 6E downgraded from "supported"
  to "open, leading candidate replaced"; IDEA-0008 added.
- `experiments/IDEA_BACKLOG.md`: **yes** — IDEA-0008 (counter-currency home-market
  panel test), and IDEA-0006 upgraded with the sharpened prediction.
- Shared `LEARNINGS.md`: **not yet.** The transferable methodological point — *set
  a cross-product benchmark from a product whose own estimate is precise; a
  benchmark averaged with a null-result sibling silently halves your power and can
  force an inconclusive verdict* — is real and cost this run its conclusion, but it
  is single-project. Recorded in `MEMORY.md` promotion candidates.
