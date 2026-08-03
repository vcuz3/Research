# Project Memory: FX futures VWAP exploration (6E/6B)

## Scope

- Objective: open-ended exploration of VWAP on CME FX futures — does a session
  VWAP carry tradable information on EUR/USD and GBP/USD futures, and is its
  *volume* weighting load-bearing?
- Instruments: the full CME FX panel, all Databento `GLBX.MDP3` `ohlcv-1m`
  volume-ranked continuous front, UNADJUSTED. **6E** (EUR, $12.50/unit) and **6B**
  (GBP, $6.25/unit) are the original pair; **6J** (JPY, $12.50) added for EXP-0005;
  **6A/6C/6N** ($10.00) and **6S** ($12.50) added for EXP-0007. Databento `GLBX.MDP3` `ohlcv-1m` volume-ranked
  continuous front, UNADJUSTED, at `futures/data/databento/`.
- **Reporting units are PER PRODUCT.** 6E/6B use 1e-4 of quote; **6J uses 1e-6**,
  because it quotes dollars per YEN near 0.0091 and 12,500,000 x 1e-6 = $12.50,
  matching a 6E pip exactly. This is NOT the conventional USD/JPY pip (0.01 yen):
  the futures quote is the RECIPROCAL of the spot convention, so 0.01 yen maps to
  a price-level-dependent ~8.3e-8 and cannot be a fixed unit. Never place two
  products' native units side by side — use dollars or the risk-equalised
  (dispersion-normalised) statistic.
- **SIX OF SEVEN products changed tick mid-sample**, at six different dates, all
  verified against the price grid rather than assumed: 6J 2015 (1e-6 -> 5e-7),
  6C and 6E 2016, 6A 2020, 6N 2021, 6S 2022 (each 1e-4 -> 5e-5). 6B never changed.
  A cost quoted in ticks across this sample is wrong on six of seven.
- Data coverage: 2010-06-07 .. 2026-07-27 raw. **Explore = 2010-06-07 ..
  2023-12-29** (3,436 / 3,437 sessions). **Holdout = 2024/2025/2026, SEALED.**
- Current phase: exploration complete for the VWAP question; NO-GO recorded.

## Current status

- Verdict: **NO-GO** for a VWAP-based FX futures strategy. HYP-0002, HYP-0003 and
  HYP-0006 (RSI) rejected against preregistered kill tests; HYP-0005 inconclusive.
  HYP-0007 (home-market mechanism) rejected wrong-signed on fresh products.
  HYP-0001 (anatomy) and HYP-0004 (the volatility-matched control on finding C)
  not killed. **No survivor is tradable, now on SEVEN products**: each product's
  BEST block nets -$7 to -$12 per bet against the most optimistic possible round
  trip (6E -8.90, 6B -11.78, 6J -7.35, 6A -8.25, 6C -9.07, 6N -8.72, 6S -10.93).
- Last verified: 2026-08-03
- Lifecycle phase: hypothesis/experiment loop, seven experiments closed
- Baseline replication: **not applicable** — this is a measurement study, not a
  paper replication. `paper/` is intentionally empty.
- Engine audit: not applicable — no execution engine. All results are
  entry-information measurements (rule 15): entry `open(m+1)`, exit at a bar
  close, no stops/targets/barriers.
- Execution profile: decisions on a 30-minute **ET wall-clock** grid (`mfo`
  29, 59, …), 46 per session; session = CME trade date 18:00 ET → 16:59 ET.
- Holdout status: **sealed**, never loaded by an analysis script.
- Experiment ledger: `experiments/ledger.csv` (EXP-0001..0007, all completed)
- Reproduction commands:
  ```powershell
  .\.venv\Scripts\python.exe -m futures.forex.vwap_exploration.tests.test_core
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.data_quality
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0001_anatomy
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0002_entry_information
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0003_london_fix
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0004_vol_stratified_blocks
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0005_liquidity_vs_clock
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0006_rsi
  .\.venv\Scripts\python.exe -u -m futures.forex.vwap_exploration.scripts.hyp_0007_home_market
  ```
- Primary evidence: `reports/FINDINGS.md`, `reports/DATA_QUALITY.txt`,
  `artifacts/runs/EXP-000{1,2,3,4,5,6,7}/review.md`

## Authoritative artifacts

- Current findings: `reports/FINDINGS.md`
- Data-quality gate: `reports/DATA_QUALITY.txt`
- Hypotheses: `experiments/hypotheses/HYP-000{1,2,3,4,5,6,7}.md`
- Run reviews: `artifacts/runs/EXP-000{1,2,3,4,5,6,7}/review.md`
- Core (tested): `core/{data,vwap,frame,stats,fix,vol,rsi,home}.py`; `tests/test_core.py`
  (25 checks, all passing)

## Confirmed findings

- **A.** The volume weighting is a *real* operation on FX futures and is provably
  degenerate on FX spot. `R_sep` (median |VWAP−TWAP| / same-slot dispersion)
  0.259 (6E) / 0.249 (6B); the anchors put price on opposite sides of the market
  on **7.1%** of decisions on both. FX futures volume is *tilted*, not
  concentrated: top 30-min slot 6.2% of session volume vs 2.17% if flat, HHI only
  1.60x flat.
- **B.** Anchor displacement is a **worse** reversal signal than the bare trailing
  30-minute return. `past30` (no anchor at all) +0.197 pip t+3.92 (6E) / +0.384
  t+5.96 (6B) beats `vwap` (+0.131 t+2.66 / +0.048 t+0.72), and `vwap`/`twap`/
  `open`/`pclose` are mutually indistinguishable. Partialling `past_30` out halves
  the anchor's rank IC. **The VWAP framing is withdrawn.**
- **B1.** Non-tradable. Best gross +0.129 pip/bet against a 1.0 pip *optimistic*
  round trip. 6E's tick halved in 2016, so a single cost number is wrong by 2x
  across the sample (rule 19).
- **D1.** The shared-decision-bar artifact is worth **68% (6E) / 88% (6B)** of the
  naive estimate at a 30-minute horizon — worse than the 31-56% recorded on
  NQ/ES/GC at 5 minutes.
- **D2.** Session-averaging turns 6B's null (+0.048, t+0.72) into **+1.030,
  t+15.06**; `corr(session mean, session count)` = −0.46/−0.47. Note the
  correlation is **negative** here, opposite in sign to the FX-spot and NQ/ES
  cases, and still manufactures the same spurious result.
- **E/F.** The WM/Reuters 16:00 London fix leaves a footprint that beats **100%**
  of 21 placebo hours on both products and is **4x larger at month-end** on 6B
  (+5.05 pip, t+3.08) — and the *entire* footprint sits inside the benchmark's own
  averaging window. Entry at f+3 (16:03 London) instead of f+2 destroys it; a
  1-minute hold captures the whole 30-minute result at a higher t. Not tradable.
- **G.** 6B's Asia coverage (0.71-0.84 vs 6E's 0.89-0.96) made the conventional
  `lookback=60, min_periods=2/3` delete 35% of 6B's 18:00 ET decisions vs 1% of
  its London decisions. Project standard is **`lookback=90, min_periods=1/2`**
  (across-hour deletion spread 0.342 → 0.035).

- **C.** Anchor displacement REVERTS in the thin blocks (`asia`, `ny_pm`) and
  CONTINUES in the London/NY `overlap` (−0.282 / −0.300, both products), and this
  is **not** a volatility gradient. EXP-0004 re-ran the split within quintiles of
  a causal absolute realised volatility: `asia − overlap` went **+0.5300 →
  +0.5657 [+0.2302, +0.8952] on 6E** (106.7% retained) and +0.3776 → +0.2210
  [−0.4120, +0.8096] on 6B, while the cells' volatility ratio moved 0.453 → 0.904
  / 0.523 → 0.998 and the effective bet count held at 65.0% / 59.7% — so the
  split was matched, not weakened. Confirmed on 6E; **provisional on 6B**, whose
  CI spans zero. Invariant over 3 stratum counts, a non-overlapping volatility
  window and a looser coverage floor (18 cells each).
- **C1.** The MIRROR arm disagrees across products. Volatility contrast
  standardised within blocks: **6E −0.3455 → +0.1332** (volatility dies once block
  is fixed ⇒ block is the operative label) but **6B −0.3439 → −0.5370** and **6J
  +0.0116 → +0.0174** (volatility survives). All three agree the block contrast is
  not *caused* by volatility; they disagree on which label carries it, 2-1 against
  6E. Do not claim the inventory mechanism for GBP or JPY.
- **H (EXP-0005, 6J).** The *mechanism* behind finding C is **OPEN**. Adding 6J
  (asia/overlap liquidity ratio 0.314 vs 6E/6B's 0.129/0.132) was preregistered to
  separate "thin book" from "the ET clock". Verdict **inconclusive** on the
  declared metric — R(6J) = −0.0038 [−0.0331, +0.0255] against a gate of +0.0198 —
  because the benchmark was half-built from 6B, whose own contrast spans zero.
  That is a kill-test design fault, not a market fact. But two arms that DID have
  power weakened both accounts: **R(6E) − R(6J) = +0.0627 [+0.0103, +0.1107]**, CI
  excluding zero, and 6J's per-slot rank profile agrees with 6E/6B (+0.283/+0.489)
  less than they agree with each other (+0.646) — against H_clock; while 6J's
  `ny_pm` has **identical CME volume intensity** to 6E/6B's (0.82x vs 0.80x/0.82x)
  and 2-3x their reversion — against crude block-volume H_liquidity. **Total
  contract volume is not the operative liquidity measure.**

- **I (EXP-0006, RSI).** **RSI(14) is REJECTED and should not be re-proposed.**
  It is not a new quantity: `RSI(n) = 50 + 50*A_n(dp)/A_n(|dp|)` EXACTLY, and on
  this 30-minute grid the increments ARE `past_30` — so it is a re-NORMALISED
  sibling of finding B's incumbent. At matched ~11% selection rate the incumbent
  `dev_past30_z` beats it on **all three products** (+0.2306/+0.2462/+0.0332 vs
  +0.1099/−0.0526/−0.0173), and RSI fails to beat even its own bare numerator on
  6E and 6J. corr(RSI, its numerator) **+0.973**; corr(RSI, its denominator)
  **+0.014** — the ratio is barely a ratio.
- **I1.** The mechanism, and the transferable part: **a fixed 70/30 cut is a
  TIME-OF-DAY SELECTOR**, because RSI's denominator is a trailing window that lags
  volatility transitions. Per-slot selection-rate CV **0.364/0.333/0.223 vs the
  incumbent's 0.064/0.060/0.063 (3.5-5.7x worse)**, firing 6.40% in `asia` against
  16.07% in `overlap` on 6E while the incumbent is flat near 11%. Per finding C
  the `overlap` is where fading LOSES, so the conventional threshold concentrates
  bets in the worst block. What RSI *does* have is its smoothing: partial rank IC
  controlling for `past_30` retains 51-63% on all three.
- **J (construction constraint, applies to any future recursive feature).** A
  recursive feature's gap damage is **DISPLACED by its memory length**. Under a
  reset-on-gap policy, `asia`'s 5.78% missing bars collapsed **`ldn_am`'s** RSI
  coverage to 0.73 — despite `ldn_am` having 0.25% missing — because 14 periods is
  ~7 hours. **Per-block gap counts do not predict per-block coverage.** Always
  bridge increments across missing bars (`core/rsi.py::gap_policy="bridge"`):
  across-block spread 0.4010 → 0.0575 (6E), 0.7255 → 0.1835 (6B).

## Provisional hypotheses

- **C2 (corrected, was part of finding C).** The claim that `past30` has the
  OPPOSITE block profile to the anchor is **6B-only** and does NOT replicate on
  6E, where `past30`'s block contrast (+0.5336) is near-identical to `vwap`'s
  (+0.5657). FINDINGS §C's cross-product generalisation has been narrowed.
- **C3.** 6B's block contrast is directionally consistent but underpowered
  (CI [−0.41, +0.81]). Nothing should be built on the 6B half of finding C.
  Only future data can settle it; the holdout is the natural instrument and is
  not worth spending given finding B1.
(H2's post-hoc home-market candidate was tested as HYP-0007 and INVALIDATED —
see "Invalidated or superseded findings".)

## Invalidated or superseded findings

- **H2 (the counter-currency home-market account) — INVALIDATED 2026-08-03 by
  EXP-0007.** It fit 3/3 products it was read off, and was rejected WRONG-SIGNED
  on four never-loaded ones: pooled rho **+0.0526 (circular-shift p 0.710)** on
  the fresh four against **−0.2342** on the three that generated it. **6A is an
  outright counterexample** — Sydney is OPEN during `asia` and `asia` is 6A's
  strongest reversion block (block rho +0.9487, exact p 1.000, the maximum
  possible value in the wrong direction). The motivating 3/3 argmax was a
  **base-rate illusion**: `asia` is the best block for 5 of 7 products, so
  expected fresh hits = 1.00 against 1 observed. Do not revive this account.
- Note for cross-project readers: this does **not** invalidate anything in
  `forex/noise_vwap`. It sharpens it — that project could not tell "volume does
  not help" from "volume is not available"; finding A shows the volume exists and
  is non-degenerate on futures, and finding B shows it still does not help.

## Decisions and constraints

- Session = CME trade date, **18:00 ET → 16:59 ET** (1,380 minutes), verified
  against the archive (ET minute-of-day 1020-1079 is empty).
- Sessions spanning more than one `instrument_id` (~1.5%) are **dropped**: a
  session-anchored VWAP across a roll averages two contracts.
- Decision grid pinned to the **ET wall clock**, never to minutes-from-open.
- The London fix minute is derived from `Europe/London`, not hardcoded to 11:00
  ET — it is 12:00 ET on 6.1% of sessions, and the naive version understates the
  6B fix result by 35%.
- Costs are always built from `tick_size(product, year)`, never assumed.

## Known risks and open questions

- Everything rests on 1-minute OHLC. Finding F is precisely a case where that
  resolution cannot settle the question (the effect lives inside one minute).
  Any follow-up on the fix needs trades/L1 data, which is a paid Databento pull.
- Finding C's volatility confound is **closed** (EXP-0004, not a confound). What
  is open is the mechanism split between products: 6E says the block label
  carries it, 6B says the volatility label does.
- Only two products. 6A/6C/6J/6N/6S are downloaded and available at
  `futures/data/databento/` if a broader FX-futures panel is ever wanted.

## Next actions

1. If the fix direction is resumed: cost out Databento `trades`/`mbp-1` for 6E/6B
   around 16:00 London only, and re-test finding F at sub-minute resolution.
2. ~~Run IDEA-0004 before using finding C~~ — done (EXP-0004, 2026-08-03).
   Finding C is cleared for use on 6E; do not build on its 6B half.
3. ~~Run 6J (IDEA-0006)~~ — done (EXP-0005, 2026-08-03), inconclusive on its own
   metric but it replaced the leading mechanism candidate.
4. ~~Run IDEA-0008 (home-market panel test)~~ — done (EXP-0007, 2026-08-03),
   **REJECTED wrong-signed**. That was the last account on offer for finding C's
   mechanism, so the mechanism question now has NO live candidate. Do not open a
   new one without a prediction that is (a) derived from something exogenous and
   (b) testable on data this project has not already consumed — the panel is now
   fully spent, so the next such test would have to use the sealed holdout, which
   finding K does not justify.
5. **Recommended: close.** The VWAP question is answered NO-GO on seven products,
   the holdout is unspent, and every remaining idea is either blocked on paid data
   (IDEA-0005), weak-prior and cheap (IDEA-0007), or deliberately unrun because
   the family is already an order of magnitude under cost (IDEA-0010).

## Promotion candidates

- Promoted to `ai_shared_memory/LEARNINGS.md` on 2026-08-02: the degenerate
  no-anchor control, the estimand-contrast reproduction, and the
  measurement-window-overlaps-institutional-window failure mode.
- **Candidate, not yet promoted (EXP-0004, 2026-08-03).** The
  volatility-matched split of LEARNINGS 2026-07-31c *discriminates*: run here it
  did NOT collapse the contrast (+0.5300 → +0.5657 on 6E, vs +0.0496 → −0.0047
  in the entry that motivated it), which is what makes the control worth running
  rather than a formality that kills everything. Two sub-points worth carrying if
  a second project sees them: (a) the MIRROR arm can name a *different* winning
  label on two highly correlated products, so it is a per-market answer, not one
  answer; (b) a realised-volatility conditioner built from 1-minute changes has
  coverage equal to roughly the SQUARE of per-minute coverage, so it silently
  re-creates the finding-G hidden filter inside the control itself (29.7% of 6B
  Asia decisions deleted vs 0.1% of overlap) — and the deletion removes the
  quiet tail of the very variable being conditioned on. Needs a second project
  before it goes in `LEARNINGS.md`.
- **Candidate, not yet promoted (EXP-0005, 2026-08-03).** *Set a cross-product
  benchmark from a product whose OWN estimate is precise.* HYP-0005's gate was
  `0.60 x mean(R(6E), R(6B))`, and 6B's contrast turns out to span zero — so the
  benchmark carried 6B's noise into the gate and forced an inconclusive verdict on
  a point estimate that was −0.11x the benchmark. The better-powered arm (a
  bootstrap of the DIFFERENCE `R(6E) − R(6J)`) was decisive at
  [+0.0103, +0.1107] and had not been declared. Lesson: when a kill test compares
  a new market against a benchmark, bootstrap the DIFFERENCE and build the
  benchmark from the precise sibling, not the average of all of them.
- **Candidate, not yet promoted (EXP-0006, 2026-08-03), two items.** (a) *A fixed
  threshold on a TRAILING-WINDOW-normalised oscillator is a time-of-day selector,
  and the per-slot selection-rate CV measures it in one line.* This extends the
  2026-07-27 entry from session-RESET features to trailing-window ones, and RSI is
  the most widely used member of that family: its 70/30 cut had a per-slot CV
  3.5-5.7x the same-slot z-score's on 3/3 products, firing 2.5x more often in the
  overlap than in Asia. (b) *A recursive feature's gap damage is DISPLACED by its
  memory length*, so per-block gap counts do not predict per-block coverage — Asia's
  5.8% missing bars collapsed London's RSI coverage to 0.73. Both need a second
  project before promotion.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
