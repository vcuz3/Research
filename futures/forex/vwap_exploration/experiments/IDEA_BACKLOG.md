# Idea Backlog

Uncommitted brainstorming belongs here. An idea is not a finding or approved
experiment. Use `python tools/research_admin.py new-idea` to add entries.

## Ideas

## IDEA-0001 — Is the VOLUME weighting in VWAP load-bearing on FX futures?

- Created: 2026-08-02
- Status: **promoted to HYP-0001, tested, not killed** (EXP-0001)
- Note: FX spot archives carry no size, so every spot "VWAP" is a TWAP. Futures
  are the only venue in this workspace where the question is well posed.

## IDEA-0002 — Does displacement from a session anchor predict forward return?

- Created: 2026-08-02
- Status: **promoted to HYP-0002, tested, REJECTED** (EXP-0002)

## IDEA-0003 — The WM/Reuters 16:00 London fix

- Created: 2026-08-02
- Status: **promoted to HYP-0003, tested, REJECTED** (EXP-0003)

## IDEA-0004 — Volatility-stratified re-run of the liquidity-block split

- Created: 2026-08-02
- Status: **promoted to HYP-0004, tested, NOT REJECTED** (EXP-0004, 2026-08-03).
  Finding C survives: `asia − overlap` +0.5300 → +0.5657 on 6E at a matched
  volatility ratio of 0.904, +0.3776 → +0.2210 (CI spans zero) on 6B. The
  blocker on finding C is cleared for 6E. Two by-products: the `past30`
  dissociation is 6B-only (FINDINGS §C corrected), and the mirror arm names a
  different operative label on each product.
- Idea: finding C (anchor displacement reverts in the thin blocks, continues in
  the London/NY overlap) is a split matched on time of day only. LEARNINGS
  2026-07-31c showed a time-of-day-matched split can still inherit a volatility
  gradient, and collapsed a comparable contrast from +0.0496 to −0.0047 when the
  split was also taken within volatility quintiles. Re-run the block contrast
  within same-slot volatility quintiles, and report the volatility ratio between
  the cells before and after, to show the split was not merely weakened.
- Cost: cheap; reuses `core/frame.py` and the existing panel.

## IDEA-0005 — Sub-minute resolution around the London fix

- Created: 2026-08-02
- Status: open; **blocked on paid data**
- Idea: finding F localises the entire fix footprint to the single minute
  16:02-16:03 London, i.e. the last minute of the post-2015 benchmark window.
  1-minute OHLC cannot resolve what happens inside that minute, so it cannot
  establish whether any of it was ever attainable. A Databento `trades` or
  `mbp-1` pull for 6E/6B restricted to 15:50-16:10 London would settle it.
- Cost: paid Databento pull; `DATABENTO_NOTES.md` records that trades/L1 schemas
  are not free. Scope it to the 20-minute window before pricing it.

## IDEA-0006 — Widen the FX-futures panel beyond 6E/6B

- Created: 2026-08-02
- Status: **partly consumed** — 6J was run as HYP-0005/EXP-0005 (2026-08-03) to
  test liquidity-vs-clock. Verdict inconclusive on the declared metric, but it
  weakened both accounts and generated **IDEA-0008**, which is now the sharper
  version of this idea and should be run instead of a generic panel sweep.
- Idea: 6A, 6C, 6J, 6N, 6S are already downloaded at `futures/data/databento/`
  with the same 2010-2026 span. The `past30`-beats-every-anchor result (finding B)
  is the one worth checking on a wider panel, since it is a claim about the
  *family* of session anchors rather than about EUR or GBP. 6J (JPY) is the most
  informative addition: its liquidity profile peaks in the Asia block, which is
  where 6E/6B are thinnest, so it tests finding C's shape against a market whose
  liquidity clock is different.

## IDEA-0007 — Does the anchor matter more for a GATE than for a signal?

- Created: 2026-08-02
- Status: open
- Idea: EXP-0002 tested the anchor as a continuous *signal*. Its industry use is
  usually as a binary *gate* ("only go long above VWAP"). EXP-0001 measured that
  a VWAP gate and a TWAP gate disagree on 7.1% of decisions, which is the only
  place the volume weighting could possibly show up. A gate study would put that
  7% directly under test rather than diluting it across the whole distribution.
  Weak prior given finding B, but it is the one framing EXP-0002 did not cover,
  and it is cheap.

## IDEA-0008 — Does reversion follow the COUNTER CURRENCY's home-market night? (panel test)

- Created: 2026-08-03
- Status: **promoted to HYP-0007, tested, REJECTED** (EXP-0007, 2026-08-03).
  Tested on 6A/6C/6N/6S — four never-loaded products, predictions derived from
  each currency's own tz with no free parameters. Pooled rho on the FRESH four
  **+0.0526 (wrong sign), circular-shift p 0.710**, against **−0.2342** on the
  three products that generated it. **6A is an outright counterexample**: Sydney
  is OPEN during `asia` and `asia` is 6A's strongest reversion block (block-level
  rho +0.9487, exact p 1.000 — the maximum possible value in the wrong
  direction). The motivating 3/3 argmax was a BASE-RATE ILLUSION: `asia` is the
  best block for 5 of 7 products, so expected fresh hits = 1.00 against 1
  observed. Mechanism behind finding C is open with this candidate eliminated.
- Observation (POST-HOC, EXP-0005) — retained as the record of what generated it: across 3 products x 4 blocks, every product's
  strongest reversion sits in the block where the **counter currency's own home
  market is shut** — 6E/6B in `asia` (London 23:00-07:59), 6J in `ny_pm` (Tokyo
  02:00-07:00). And the `overlap` block, where both home markets are open, is
  near-identical on all three (−0.0153 / −0.0159 / −0.0151, t −2.0 / −2.2 / −1.8).
- Proposed mechanism: transitory order flow reverts when the dealers who warehouse
  that currency are absent. CME contract volume does NOT measure this — 6J's
  `ny_pm` has the same volume intensity as 6E/6B's (0.82x vs 0.80x/0.82x) and 2-3x
  the reversion, because that volume is the US close, not JPY liquidity.
- Why it is worth running: it is the only account left standing after EXP-0005
  weakened both H_clock and crude block-volume H_liquidity, and it predicts the
  `overlap` invariance, which is not what it was constructed to explain.
- The test: the panel is already downloaded and makes **differing** per-product
  predictions, which is what makes it a real test rather than a re-description —
  6A (Sydney) and 6N (Wellington) home markets fall INSIDE `asia`, so they should
  look like 6J (no Asia reversion), not like 6E/6B; 6S (Zurich) sits in
  `ldn_am`/`overlap` like 6E; 6C (Toronto) sits in `overlap`/`ny_pm`. Preregister
  the argmax block per product BEFORE loading, and score 5-7 products at once.
- Main artifact risk: with 4 blocks the argmax is a 1-in-4 guess, so 3/3 is not
  strong evidence (p≈0.016 under a uniform null but the blocks are not equally
  likely a priori). Score the full predicted ORDERING, not the argmax, and use a
  per-product null that shuffles the block labels. Also fix the EXP-0005 design
  fault: benchmark against a product whose own estimate is precise, not against a
  mean that includes a null-result sibling.
- Cost: cheap; reuses `core/` unchanged plus one `pip_size` entry per product, and
  each new product needs its price grid checked for a mid-sample tick change.
- Motivating evidence: `artifacts/runs/EXP-0005/review.md`, `reports/FINDINGS.md`
  §H1.

## IDEA-0009 — RSI(14) on the decision grid

- Created: 2026-08-03
- Status: **promoted to HYP-0006** (EXP-0006)
- Observation: RSI(n) is not a new quantity. With `U-D = dp` and `U+D = |dp|` and
  a linear smoother, `RSI = 50 + 50*A_n(dp)/A_n(|dp|)` EXACTLY (verified to 3e-14
  in `tests/test_core.py`). It is a smoothed trailing return over a trailing
  absolute-return volatility. On this project's 30-minute decision grid the
  increments ARE `past_30` — so RSI(14) is a differently-NORMALISED sibling of
  finding B's best signal, not a new idea.
- Question worth asking: is RSI's **trailing-window** normaliser better or worse
  than this project's **causal same-slot** one? That is a real methodological
  question with transferable value, and it is the only interesting thing here.
- Expected improvement: **none in tradability**, and this should be said up front.
  Finding B1 puts the trailing-return family ~8x under the most optimistic cost
  floor; a re-normalisation of it cannot cross that gap. This is a measurement
  question, not a strategy search.
- Main artifact risk: RSI's denominator LAGS volatility transitions (it is a
  trailing window, not a same-slot statistic), so after a quiet stretch gives way
  to a busy one the denominator is still small and RSI reaches 70/30 more easily.
  A fixed 70/30 cut may therefore be partly a TIME-OF-DAY selector — the exact
  LEARNINGS 2026-07-27 failure, on a new feature. Also the `ewm(adjust=False)`
  seeding trap (LEARNINGS 2026-07-26): `wilder_rma` uses the textbook SMA seed and
  the tests pin the difference.
- Motivating evidence: `core/rsi.py`, `reports/FINDINGS.md` §B.

## IDEA-0010 — Smoothed past_30 with the project's same-slot normaliser (the RSI that RSI should be)

- Created: 2026-08-03
- Status: open; **logged deliberately UNRUN.** EXP-0006 says what the better
  feature would be, but the family is already ~8x under cost (finding B1), so
  building it would be a measurement and not a strategy. Do not run this without
  being asked; it is recorded so the reasoning is not lost, not as a queue item.
- Observation (EXP-0006): RSI has two dimensions and they failed differently. Its
  14-period SMOOTHING is real — partial rank IC controlling for `past_30` retains
  51-63% on all three products. Its NORMALISATION is wrong for this market — the
  trailing-window denominator makes a fixed 70/30 cut fire 2.3-4.1x more often in
  some slots than others (per-slot CV 3.5-5.7x the incumbent's), concentrated in
  the `overlap`, which is the one block where finding C says fading loses.
- The idea: keep the smoothing, swap the normaliser. Wilder-smooth `past_30` over
  n periods, then z-score by the project's CAUSAL SAME-SLOT scale rather than by a
  trailing `A_n(|dp|)`. That is "the RSI that RSI should be" on a market with a
  strong intraday liquidity clock.
- Kill test if it is ever run: it must beat `dev_past30_z` at matched selection
  rate on 6E, 6B AND 6J, and its per-slot selection-rate CV must stay near the
  incumbent's ~0.06. Sweep n with matched rates — EXP-0006's n=7/n=28 cells looked
  better than n=14 but at wildly different selection rates on consumed history, so
  they are a shape, not a result.
- Main artifact risk: this is a THIRD pass over the same signal family on data
  already fully inspected. Any winner is a searched survivor and would need the
  sealed 2024-2026 holdout or a forward period, which finding B1 does not justify
  spending.
- Motivating evidence: `artifacts/runs/EXP-0006/review.md`, `reports/FINDINGS.md`
  §I/§I1.
