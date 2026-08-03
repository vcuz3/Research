# Shared Research Learnings

This file contains verified lessons that apply across more than one research
project. The mandatory backtesting rules live in `RULES.md`; project status and
project-only findings belong in each project's `MEMORY.md`.

## Entry criteria

Add a learning only when it is:

- supported by code, data, or a reproducible test;
- durable enough to matter in later sessions;
- useful beyond the project where it was discovered;
- linked to evidence in this workspace.

Use one of these statuses: `confirmed`, `provisional`, `invalidated`, or
`superseded`. Provisional items should include the test needed to confirm or
kill them.

## Learnings

### 2026-08-03 — Estimator bias is a THIRD route to a time-of-day selector: a persistence statistic on a GROWING window has a shrinking sampling SD, and a fixed threshold on it reads that as signal — while POOLING one across a deterministic profile inflates it in the opposite direction

- Status: provisional (single project, NQ+ES — a correlated pair, so cheap corroboration
  rather than replication; but the mechanism is arithmetic and the degenerate control is
  decisive). Confirm or kill by applying the same per-slot selection-rate-CV diagnostic to
  any other thresholded feature whose ESTIMATION WINDOW varies — the CME FX projects'
  46-slot clock is the obvious next host, and the arm is evaluation-only.
- Applies to: (a) any feature that is an ESTIMATE of memory/persistence (AR(1) φ, Hurst H,
  variance ratio, half-life, autocorrelation) computed on a window whose LENGTH varies —
  session-to-date/expanding, coverage-dependent, or era-dependent — and then compared
  against a FIXED threshold; (b) any pooled lag-1/persistence statistic computed across a
  feature that has a deterministic intraday (or seasonal) profile.
- **The headline: this workspace already knew that a fixed threshold on a session-RESET
  feature is a clock (2026-07-27) and that a fixed cut on a TRAILING-WINDOW-normalised
  oscillator is a clock (2026-08-03, RSI). Estimator bias is a third route to the same
  defect, and it is the one nobody looks at, because the estimate is usually REPORTED
  rather than THRESHOLDED.** `noise_vwap`'s Hurst gate computes
  `H = ghe1(logp[:i+1])` — 30 one-minute bars at the 10:00 decision, 390 at 15:59 — then
  applies a fixed `H_GRID` cut at every one. Per-slot selection-rate CV against a matched
  same-slot z-score of the SAME H: **NQ 2.88–45.59× (median 23.9×), ES 5.90–46.48×
  (median 21.8×), at all 7 published thresholds.** At the realistic operating point
  `H ≥ 0.55` the gate fires on **33.5% of 10:00 decisions and 8.4% of 15:59 decisions**
  (NQ; 31.7% → 5.2% ES), monotonically — 4–6× more likely in the morning, which on that
  project is exactly where super-diffusion and the strongest part of its own edge live.
- **The mechanism is the estimator's DISPERSION, not its LEVEL — and that is the
  non-obvious part.** Across the gate's 13 windows the mean H moves only 0.0225 (NQ) /
  0.0203 (ES), while the sampling **sd compresses 3.80× / 3.54×** (0.176 → 0.046). A fixed
  cut sitting in the tail of a distribution whose width collapses 3.8× must select a
  collapsing fraction of it. Confirming signature: the CV ratio is **smallest at the
  threshold nearest the distribution's centre** (2.88× at `H ≥ 0.50`) and worst in the
  tails — i.e. the defect is mildest where nobody operates and worst where a selective
  gate actually sits. **So when auditing this, look at the per-window SD, not the mean.**
- **The decisive control, and it is three lines: `signflip` — the session's REAL
  |returns| with iid random signs.** It preserves the real intraday volatility seasonality
  minute-by-minute and destroys all memory, so true H = 0.50 by construction. It
  reproduces the sd compression (3.64× / 3.70×) and **about half the real selection ramp
  on its own** (0.330 → 0.141 NQ), and even on that memoryless path a fixed cut is
  **9.8–10.6× worse calibrated than a same-slot z**. A constant-volatility fBm control
  agrees, which is what rules out volatility seasonality as the driver. Prefer `signflip`
  to a plain random walk for any intraday persistence question: it holds the one nuisance
  variable you cannot otherwise separate.
- **The opposite-signed sibling, and the one that actually bit a published number:
  POOLING a lag-1 statistic across a deterministic profile INFLATES it.**
  `vei_exploration`'s AC1 column pools consecutive decision pairs across 13 slots, and VEI
  has a documented per-slot level drift (0.745 → 1.165) — so two consecutive readings
  covary partly because both are late-session. Removing the per-slot mean first:
  `wilder_10_50` **+0.4411 → +0.2198 (NQ)** / +0.4036 → +0.2007 (ES), and `ema_10_50`
  **+0.1609 → +0.0048 / +0.1386 → +0.0002, i.e. entirely clock.** Roughly HALF of the
  persistence that justified adopting the Wilder estimator was the clock. The *ranking*
  (wilder > ema > sma) survived on both markets, so the estimator choice stood — read this
  as "check the magnitude, the ordering is usually safe".
- **Small-sample bias itself is a NON-ISSUE for this workspace's inference, and it is
  worth knowing that so nobody spends a week on it.** Kendall's `E[φ̂] − φ ≈ −(1+3φ)/T`,
  measured on 20,000 draws per cell: max |bias| is **0.00025 at T = 44,516** (a pooled
  AC1), 0.0009 at T = 3,710, 0.009 at T = 390 — versus **0.122 at T = 30** and **0.284 at
  T = 13**. Every headline IC/reversion statistic here pools 1e4–1e5 observations and is
  immune. The bias is a FEATURE-CONSTRUCTION problem, not an inference problem.
- **Method note worth pinning: the analytic corrector FAILS exactly where you need it.**
  `−(1+3φ)/T` is accurate for T ≥ 30 (measured vs predicted agree within 0.008) but at
  **T = 13** it mispredicts badly (at φ = −0.4 it predicts +0.0154 against a measured
  +0.0001), and the analytic and bootstrap correctors then disagree by **0.12** on real
  data (per-session VEI AC1: raw +0.5255, Kendall +0.7831, bootstrap +0.6595). **Below
  T ≈ 20 use a parametric bootstrap correction, not the closed form** — and always run two
  independent correctors, because their disagreement is the only thing that reveals this.
- Bottom line for the audited projects: `vei_exploration`'s AC1 magnitude is halved but
  its estimator choice stands; `noise_vwap`'s "Hurst LEVEL is a real per-trade quality
  signal (beats a matched random null, p=0.03)" is **confounded with time of day and not
  separately established**, because that null matched COUNT, not TIME OF DAY. Neither is
  overturned and nothing deployed is affected (the Hurst gate was already rejected as
  selection, exit and sizing). The repair in both cases is one line: slot-demean the
  statistic, or gate on a same-slot z.
- Evidence: `futures/nq/estimator_bias/reports/FINDINGS.md` §A/§B/§C,
  `artifacts/runs/EXP-0001/review.md` (+ `bias_table.txt`, `pooled_ac1_{NQ,ES}.txt`,
  `hurst_gate_{NQ,ES}.txt`), `experiments/hypotheses/HYP-0001.md`. New tested module
  `core/arbias.py` + `tests/test_core.py` (18 checks, including that OLS shrinks toward
  zero for BOTH signs at small T, that slot-demeaning kills a pure clock the pooled
  estimator reports as persistence, and a guard that re-reads the audited script and fails
  if its `LAGS`/`H_GRID` change). Rule-23 reproduction of all 8 published AC1 cells was
  exact to 1e-4. Reproduce via
  `python -u -m futures.nq.estimator_bias.scripts.{s1_bias_table,s2_pooled_ac1,s3_hurst_gate}`.
- Origin: user asked to run item H-A2 of an intake of aligrithm.com articles
  (`research_papers/ALIGRITHM_HYPOTHESES_2026-08.md`, 2026-08-03), derived from that
  site's *3.35 Trend and Reversion Are the Same, and OLS Understates Both* and *5.30
  Order-Flow Autocorrelation*. The source article's own claim (OLS understates memory)
  turned out to be the LEAST important of the three effects the audit found.

### 2026-08-03 — A cross-sectional PANEL is a usable holdout for a pattern read off inspected data; and an ARGMAX agreement rate must be scored against the MODAL-CATEGORY base rate, not a uniform null

- Status: provisional (single project, but the rejection is unambiguous — wrong sign,
  with an outright counterexample at the extreme of the predictor's range). Confirm or
  kill by applying the fresh-vs-consumed split to any other cross-sectional claim in
  this workspace: the NQ↔ES sibling checks and the `noise_vwap` transfer ladder both
  have panel members that were inspected at different times.
- Applies to: (a) any regularity noticed *while looking at* results and then written up
  as a mechanism — especially one that "fits every market we have"; (b) any evidence of
  the form "the best cell was the predicted one on k of k units".
- **The headline: a pattern that fit 3/3 markets died on 4 fresh ones, and the two
  samples disagreed in SIGN.** A post-hoc account (reversion sits where the counter
  currency's home market is shut) was read off 12 cells of 6E/6B/6J. It was
  preregistered from each currency's own time zone with real DST and a uniform
  08:00-17:00 local window — **zero free parameters** — then tested on 6A/6C/6N/6S,
  four CME FX contracts never previously loaded. Pooled within-product-demeaned
  Spearman(home-market openness, reversion), which the hypothesis requires to be
  NEGATIVE: **consumed three −0.2342, fresh four +0.0526** (circular-shift null
  p = 0.710). The effect existed only in the sample that generated it. **Had all seven
  been pooled the headline would have been −0.0722, p = 0.176 — a "directionally
  consistent, needs more data" result that would have survived into the next
  write-up.** The split is what turned a soft maybe into a clean rejection, and it cost
  nothing but declaring it in advance.
- **The single most useful diagnostic was a counterexample at the extreme of the
  predictor.** 6A (Sydney) has the second-highest home-market openness during the Asia
  block (0.842) and that block is its *strongest* reversion cell — block-level Spearman
  **+0.9487, exact-permutation p = 1.000**, the maximum possible score in the wrong
  direction. Underpowered tests give noisy zeros; they do not give confident
  inversions. So when choosing which panel members to add, **pick the ones at the ENDS
  of the proposed predictor's range**, not the ones most similar to the originals.
- **Sub-lesson, and the one most likely to bite elsewhere: "the argmax was the
  predicted cell on k of k units" is nearly worthless when one category is the modal
  winner.** The idea was motivated by 3/3 argmax agreement, read as p ≈ (1/4)³ ≈ 1/64
  under a uniform null over 4 blocks. But the Asia block is the best cell for **5 of 7
  products (71%)**, so "predict Asia" is close to free. Scored against that observed
  marginal, the expected number of fresh hits was **1.00 against 1 observed** — exactly
  zero information. **Compute the base rate of the modal category across units and use
  it as the null; a uniform null over categories is the wrong null whenever the
  categories are not equally likely a priori** — which, for anything indexed by time of
  day, sector, or regime, they never are.
- **Sub-lesson on nulls for two autocorrelated series on a cyclical index: use a
  CIRCULAR SHIFT, not a label shuffle.** Both the predictor and the per-slot P&L are
  strongly autocorrelated along a 46-slot intraday clock; a free permutation destroys
  that autocorrelation and is anti-conservative. Shifting each unit's labels round the
  cycle preserves the contiguity of both series and destroys only their alignment, and
  the shifts are exactly enumerable (46 per unit). Here both nulls centred at ~0 with
  the circular one wider (sd 0.094 vs 0.076), so the choice did not change the verdict
  — but it would have with a real effect, and it is one line either way.
- **A real bug worth pinning: a small-n guard that returns NaN, feeding a comparison
  that treats NaN as a pass.** `spearman()` had an `n >= 10` guard; the per-unit cells
  had n = 4, so every one returned NaN, and the permutation test then scored
  `NaN <= NaN` as False throughout and printed **p = 0.0000 for all seven units** —
  which reads as seven significant results. Guards that degrade to NaN are only safe if
  every downstream comparison treats NaN as a FAILURE; check that explicitly.
- Bottom line for the project: the mechanism behind the effect is now **open with no
  live candidate**, and the cost floor is confirmed on seven products rather than two
  (each product's best cell nets **−$7 to −$12 per bet** against the most optimistic
  possible round trip). Also worth carrying as a rule-19 calibration: **six of the
  seven contracts changed tick mid-sample, at six different dates** (6J 2015, 6C and 6E
  2016, 6A 2020, 6N 2021, 6S 2022), so a cost quoted in ticks across 2010-2023 is wrong
  on six of seven — verify the price grid per product per year rather than assuming.
- Evidence: `futures/forex/vwap_exploration/artifacts/runs/EXP-0007/{review.md,
  homemkt.txt}`, `.../reports/FINDINGS.md` §H1/§H2/§K,
  `.../experiments/hypotheses/HYP-0007.md`. New tested module `core/home.py`
  (per-currency DST, no free parameters). Reproduce via
  `python -u -m futures.forex.vwap_exploration.scripts.hyp_0007_home_market`.
- Origin: user asked to run the project's own backlog item IDEA-0008 (2026-08-03),
  which had been logged as "the highest-value open direction" after EXP-0005 generated
  the pattern. It was rejected on the first genuinely fresh sample.

### 2026-08-02 — Check your MEASUREMENT window against the INSTITUTIONAL window before believing an event study; and a preregistered arm that fails in the WRONG DIRECTION is more informative than the three that pass

- Status: provisional (single project, but the diagnosis is over-determined — four
  independent observations all resolve to one boundary, on both markets). Confirm or
  kill by repeating the entry-lag/holding-horizon boundary sweep on any other event
  study in this workspace whose event has a PUBLISHED duration (an auction, an
  auction-imbalance reveal, a settlement window, an index-rebalance window, an
  economic-release embargo lift).
- Applies to: any event study anchored on a benchmark, fixing, auction, settlement or
  release that has a **published window** rather than an instant — and to reading a
  preregistered arm that fails backwards.
- **The headline: an event study whose entry sits INSIDE the event's own averaging
  window measures the event, not a tradable reaction to it.** Testing the WM/Reuters
  16:00 London fix on 6E/6B futures, entry `open(f+2)` = 16:02:00 London, hold 30
  minutes, fading the 30-minute pre-fix drift: **+0.905 pip t+2.48 (6E) / +1.552 pip
  t+3.54 (6B)**, and it **beat 100% of 21 placebo hours on both products**, and it was
  **4x larger at month end** on 6B (+5.05, t+3.08) exactly where index-rebalancing flow
  concentrates, with the raw pre-fix drift itself 55%/85% larger on those days. Three
  of four preregistered arms passed. Every one of those is a real measurement and none
  of them is an edge: the WM fix window runs to **16:02:30**, so the entry was 30
  seconds inside it.
- **The two controls that diagnose it, and they are one line each.** (1) **Entry-lag
  sweep**: move the entry one minute later, to f+3 = 16:03, the first minute fully
  clear of the widest published window. The effect dies on both products (6E
  +0.905 → **−0.060**; 6B +1.552 → **+0.278**) and stays dead at f+5/f+10/f+30.
  (2) **Holding-horizon sweep at a FIXED entry**: shorten the exit instead. The
  **1-minute** bet captures the entire 30-minute result *at a higher t*
  (+0.847 t+4.43 / +1.320 t+7.02). A 30-minute result that is entirely its first
  minute is not a 30-minute result. Run both — the lag sweep says *where* it lives,
  the horizon sweep says *how much of it* is there.
- **The wrong-direction failure was the clue.** Arm 4 was preregistered from the FSB's
  2014 recommendation: WM widened the fix window from 1 minute to 5 minutes on
  **2015-02-15** explicitly to dilute the concentration of benchmark trading, so the
  effect should have SHRUNK. It **inverted** — the entire effect is post-2015 (6E
  −0.000 → +1.364; 6B −0.108 → +2.408) — because the widening is what moved the
  window's *end* past the entry point. Before 2015 the window closed at 16:00:30 and
  by 16:02 there was nothing left to capture. **A dated, externally-imposed structural
  break is the cheapest arm in an event study and it is worth more when it fails than
  when it passes**: had arm 4 merely come out flat, the honest reading would have been
  "mechanism uncertain, effect real" and the boundary controls would never have run.
  Generalisation: when a preregistered arm fails *backwards* rather than *weakly*, do
  not record it as a mechanism rejection — look for the thing that flips its sign, and
  check the measurement construction first.
- **Sub-lesson: derive an event clock from the event's OWN timezone.** The London 16:00
  fix is at 11:00 ET on 94% of sessions and **12:00 ET on 6.1%** — the ~3-week windows
  each spring and autumn when US and UK daylight-saving transitions are out of step.
  Hardcoding 11:00 ET files those sessions under a placebo hour and **understated the
  6B result by 35%** (+1.153 vs +1.552). Same family as the FX-spot wall-clock lesson
  below, reached from the calendar side rather than the archive side.
- **Sub-lesson, a real bug worth pinning: apply a subgroup MASK after computing a
  rolling feature, never before.** Masking the input series first (`np.where(mask, x,
  nan)`) and then taking a 90-session trailing window with `min_periods=45` leaves a
  1-in-21 scattered subgroup like *month-end* with an almost entirely NaN window, and
  the cell silently returns "too few events" instead of an answer. The month-end arm
  did not compute at all on the first pass and looked like a data limitation.
  Contiguous masks (eras) survive this; scattered ones do not — so the bug hides until
  the one subgroup you most care about.
- Evidence: `futures/forex/vwap_exploration/artifacts/runs/EXP-0003/review.md` (+
  `fix_6E.txt`, `fix_6B.txt`), `.../reports/FINDINGS.md` §E/§F,
  `.../experiments/hypotheses/HYP-0003.md`. Tested module `core/fix.py`. Reproduce via
  `python -u -m futures.forex.vwap_exploration.scripts.hyp_0003_london_fix {6E|6B}`.
- Origin: user asked for open-ended VWAP exploration on EUR/GBP futures (2026-08-02).
  The fix was chosen as the one moment in the FX day where a volume-weighted average
  price is a *contractual obligation* rather than an indicator.

### 2026-08-02 — On a market that HAS volume, VWAP is still beaten by the trailing return: run the NO-ANCHOR degenerate arm, not just the no-volume one

- Status: provisional (single project, but both products agree and it reversed the
  project's framing). Confirm or kill by adding the no-anchor arm to any other
  anchored-indicator study here — `futures/nq/noise_vwap`'s VWAP gate is the obvious
  target and the arm is evaluation-only.
- Applies to: any feature defined as a displacement from a session-anchored reference —
  VWAP, TWAP, opening range, prior close, anchored bands, pivot levels, developing
  value area.
- **The headline: the degenerate control for an ANCHOR study is not "a different
  anchor", it is NO ANCHOR.** On 6E/6B futures, fading `|dev_z| >= 1` at a 30-minute
  horizon (entry `open(m+1)`, per-signal mean, session cluster-robust t): `vwap`
  **+0.131 t+2.66 / +0.048 t+0.72**, `twap` +0.139/+0.075, `open` +0.082/+0.075,
  `pclose` +0.085/+0.049 — the four anchors are mutually indistinguishable and the two
  *degenerate* anchors sit inside VWAP's bootstrap CI on both products. Then the
  no-anchor arm — fade the trailing 30-minute return, z-scored by the identical causal
  same-slot construction, using no anchor, no averaging and no volume — returns
  **+0.197 t+3.92 (6E) / +0.384 t+5.96 (6B)**, i.e. **1.5x and 8x better than VWAP**.
  Partialling `past_30` out halves the anchor's rank IC (−0.0298 → −0.0146 /
  −0.0257 → −0.0114) while `past_30`'s own IC is the largest in the table. The anchor
  is a noisier proxy for short-horizon reversal.
- **This closes a gap the 2026-08-01 FX-spot entry could not close.** There, the
  volume-free variant matched the published rule on 8/8 cells — but on a venue with NO
  volume (`volume == -1` on 100% of 22.0M rows), which cannot distinguish *"volume does
  not help"* from *"volume is not available"*. CME FX futures publish real
  exchange-reported volume and separate the two: VWAP and TWAP genuinely differ there
  (median |VWAP−TWAP| **2.6 pip (6E) / 3.9 pip (6B)**, ~25% of the displacement scale,
  **putting price on opposite sides of the anchor 7.1% of the time**, correlation 0.957
  — nowhere near degenerate), and **it still does not help**. Volume was never the
  binding constraint on either venue.
- **Useful calibration, contrary to the usual framing: FX futures volume is TILTED, not
  CONCENTRATED.** Top 30-minute slot holds **6.2%** of session volume against 2.17%
  under a flat profile; top four slots 22.8%; HHI only **1.60x** flat. That is the
  quantitative reason |VWAP−TWAP| is ~25% of the displacement scale rather than ~100%,
  and it should temper any claim that an FX VWAP "is basically the London/NY overlap".
- **Sub-lesson (a), the shared-decision-bar artifact is WORSE than previously
  recorded.** Entering at `close(m)` (sharing a print with the feature) instead of
  `open(m+1)`: the honest estimate retains only **32.4% (6E) / 12.5% (6B)** of the
  naive one, at a **30-minute** horizon. The 2026-07-31 entry measured 31-56% retained
  at *5* minutes on NQ/ES/GC. On 6B seven-eighths of the measured reversal is one
  shared print. Do not assume the artifact shrinks with horizon.
- **Sub-lesson (b), the 2026-08-01 estimand trap reproduces on a third asset class —
  and the SIGN of `corr(block mean, block count)` does not matter.** Session-averaging
  instead of taking the per-signal mean turns 6B's null (**+0.048, t+0.72**) into
  **+1.030, t+15.06**, and 6E's +0.131/t+2.66 into +0.777/**t+15.92**. But
  `corr(session mean, session count)` here is **−0.46 / −0.47** — *negative*, the
  opposite sign from the FX-spot (+0.41) and NQ/ES (+0.23..+0.44) cases. Sessions with
  FEW signals had HIGH mean P&L, and the estimand still manufactured t≈16 from nothing.
  **Read the magnitude of that correlation, not its sign.** This is the second-project
  confirmation the 2026-08-01 entry asked for; that entry's estimand claim should now
  be read as confirmed.
- **Sub-lesson (c), rule 19 made concrete: a mid-sample TICK CHANGE silently doubles
  your cost model.** 6E's outright tick halved from 0.0001 ($12.50) to 0.00005 ($6.25)
  in **2016**; 6B's never changed. The same gross edge therefore went from 15x below
  cost to 8x below cost with no change in predictability. A cost quoted in *ticks*
  across 2010-2023 is wrong by 2x on one of the two contracts. Detect it in one line
  by checking the price grid (`round(px*1e5) % 10 == 0`) per year.
- Rule-9a note worth porting: 6B is materially thinner than 6E outside London/NY (Asia
  minute coverage **0.71-0.84** vs 0.89-0.96), and the conventional
  `lookback=60, min_periods=2/3` same-slot window deleted **35% of 6B's 18:00 ET
  decisions against 1% of its London decisions** — the GC hidden-liquidity-filter
  failure on a new instrument. `(90, 1/2)` keeps the same 45-session estimator floor
  and cuts the across-hour deletion spread from **0.342 to 0.035**. Also worth the
  check that paid off: the sub-95%-coverage minutes were NOT concentrated on any
  minute-of-hour (top counts 9/8/8 of 355; 12/12/12 of 662), so unlike the IBKR spot
  archives this was genuine illiquidity, not a download chunk artifact.
- Descriptive residual worth keeping (PROVISIONAL, volatility confound open): anchor
  displacement **reverts** in the thin blocks (Asia +0.288 t+5.18 on 6E) and
  **continues** in the London/NY overlap (−0.282 / −0.300, both products), while the
  no-anchor `past30` arm has the **opposite** time-of-day profile (strongest reversion
  in overlap/ny_pm, +0.700 t+5.04 on 6B). The split is matched on time of day but not
  on volatility, so per 2026-07-31(c) it is not yet safe to use.
- Bottom line for deployment: **non-tradable on either construction.** Best gross
  +0.129 pip/bet against a 1.0 pip *optimistic* round trip (1-tick-wide market, fill at
  the touch both sides) — about 8x below cost, and negative on 6B post-2016.
- Evidence: `futures/forex/vwap_exploration/reports/FINDINGS.md` §A/§B/§C/§D/§G,
  `artifacts/runs/EXP-0001/review.md`, `artifacts/runs/EXP-0002/review.md`,
  `experiments/hypotheses/HYP-0001.md` + `HYP-0002.md`. Code:
  `core/{data,vwap,frame,stats}.py`; tests `tests/test_core.py` (15 checks, including
  TWAP == VWAP-at-constant-volume AND != at varying volume, anchor causality under
  truncation, and a synthetic case where rank IC and mean spread disagree). Reproduce
  via `python -u -m futures.forex.vwap_exploration.scripts.{hyp_0001_anatomy,hyp_0002_entry_information}`.
- Origin: user asked for open-ended VWAP exploration on EUR/GBP futures with 2024-2026
  held out (2026-08-02). Both preregistered hypotheses rejected; the no-anchor arm was
  added mid-run after the partial-correlation control pointed at it, and it made the
  verdict more negative rather than less.

### 2026-08-01 — When SIGNAL COUNT is endogenous to the outcome, the per-signal and session-averaged estimands disagree in SIGN; and to test whether missing DATA is your binding constraint, score the variant that uses none of it

- Status: **confirmed for the estimand claim** (2026-08-02: reproduced in a second,
  independent project on a third asset class — CME 6E/6B FX futures — where
  session-averaging turned a null of +0.048 pip/t+0.72 into +1.030/**t+15.06**. Note
  `corr(block mean, block count)` was **negative** there (−0.46/−0.47), the opposite
  sign from this entry's cases, and manufactured the same spurious result: read the
  MAGNITUDE of that correlation, not its sign. See the 2026-08-02 entry above.)
  Sub-lessons (b), (c), (d) remain provisional.
- Applies to: (a) any statistic that averages per-signal outcomes within a session/day/
  block and then averages those blocks, whenever the NUMBER of signals in a block is
  itself an outcome of the same process — intraday breakout counts, threshold crossings,
  event triggers, any "take the trade whenever X" rule; (b) any port of a strategy to an
  instrument that is MISSING one of the strategy's input data series.
- **The headline: session-averaging a per-signal effect is not a conservative choice, it
  can invert the answer.** On GBPUSD, forward return to the session close after a
  noise-band breakout: **per-signal mean +0.010 pips (session cluster-robust t +0.01)
  versus session-averaged mean −9.655 pips (t −16.70)**. Opposite signs, three orders of
  magnitude apart in the point estimate. Every row of the diagnostic table came back at
  t ≈ −16 to −27 under session averaging, *including rows whose mean was positive*, which
  is the tell that the two are not measuring the same thing.
- **The mechanism, and how to detect it in one line: correlate each block's MEAN with its
  COUNT.** Here it was **+0.41**. Split by count quartile: sessions with 3.7 signals
  averaged **−22.3 pips each**, sessions with 32.7 signals averaged **+13.2**. A trending
  session generates both more breakouts *and* better ones, so weighting sessions equally
  implicitly requires knowing the session's FINAL signal count at allocation time — the
  exact non-causal estimand RULES.md rule 12 names. The deployable statistic for an
  equal-risk per-bet book is the **per-signal mean with a block cluster-robust SE**,
  `Var(mean) = (1/N²)·Σ_blocks (Σ_{i∈block}(xᵢ − x̄))²`, not the mean of block means.
- **This is NOT a quirk of the failing market — it is worse on the market where the
  strategy WORKS.** The same measurement on NQ/ES, identical code path: per-signal
  **+4.7 to +24.5 ticks (cluster-t +2.4 to +4.0)** versus session-averaged **−21.8 to
  −54.2 ticks (t −2.4 to −11.0)**, with corr(block mean, block count) +0.23 to +0.44. So
  the session-averaged estimand says the flagship strategy's own entry signal LOSES on
  NQ. Any conclusion in this workspace drawn from a session-averaged per-signal statistic
  is suspect until re-checked. Related but distinct from the earlier 2026-07-31 entry (a):
  there the disagreement was rank-vs-mean on the same weighting; here it is the WEIGHTING
  itself, and it is the more dangerous of the two because block-averaging looks like the
  conservative, dependence-aware choice.
- **Sub-lesson (b), the control that answers "is the missing data the problem?": build the
  variant that uses NONE of the missing input and score it against the faithful one.**
  Porting a VWAP-anchored strategy to spot FX, which publishes no size at all
  (`volume == -1` on 100% of 22.0M rows), the natural worry is that the VWAP substitute is
  too weak. Substituting the **TWAP** — not a new indicator, but literally the VWAP
  formula at constant weights, `Σtp·v/Σv → mean(tp)`, worth pinning in a test in BOTH
  directions — and then running a stop that uses no anchor at all settled it: the fully
  volume-free `band` stop **matched or beat** the published `max(band, anchor)` rule on
  **all eight** pair/session combinations (Sharpe +0.09..+0.41 better, per-trade P&L
  within ±0.13). The missing volume was not the binding constraint, and without that arm
  the obvious, plausible, completely wrong next step was to go build better volume
  proxies. Same family as the 2026-07-27 "score the bare numerator" lesson: the degenerate
  variant is the cheapest decisive control you can run.
- **Sub-lesson (c): a preregistered mirror control can be VACUOUS in the exit-neutral
  cell, which is where you most want it.** Rule 16 says re-run the mirror rather than
  negating P&L — correct, and this run did. But with the exit removed (hold to horizon) so
  as to isolate entry information per rule 15, the re-executed fade is the *exact*
  algebraic negation of the momentum version anyway (same entries, same fills: −0.668 vs
  +0.668 pips on identical 5,007 trades). The control can then only return "all pairs" or
  "no pairs" and adds nothing beyond the sign already in hand. **A re-executed mirror only
  carries information when the exit geometry is asymmetric.** Check that before declaring
  it as a criterion.
- **Sub-lesson (d), transfer-ladder extension:** the Noise-Area + VWAP intraday momentum
  family now fails at the GROSS level on EURUSD/GBPUSD/AUDUSD/NZDUSD — median **−0.55
  pips/trade** before any cost, 4/4 pairs, two independent session definitions, 88 of 96
  declared cells, best cell +0.24 pips against a 1.0 pip round trip. Ladder: NQ (strong
  intraday drift) works → ES weaker → GC/YM cost-fragile → RTY no gross edge → **FX
  negative gross**. Confirms on a new asset class that this family's transferability is
  governed by the target's own intraday continuation, not by the band machinery. Measured
  directly and unit-free (forward return per band half-width): NQ **+0.030..+0.103**,
  ES +0.026..+0.088, FX **−0.062..+0.061 with no reliable sign** — and the FX direction
  SIGN-FLIPS between the two session definitions on two of four pairs. What little signal
  exists is a weak short-horizon reversion in the two carry pairs (−0.09..−0.19 pips,
  t −2.4..−4.4), i.e. **5–11x smaller than the spread**: the Rule-16 mirror trap in its
  cost form again (GC 2026-07-19), since the negative of a sub-cost loser is a sub-cost
  loser.
- Rule-9a note worth porting: every sub-98%-coverage window in all four IBKR FX archives
  started **exactly on the hour** and ran 15 minutes — a download chunk-boundary artifact,
  not a liquidity effect (it is absent from the equally illiquid `:15–:59` minutes of the
  same hours, and identical across 15 years). It mattered twice: anchoring the FX day at
  the nominal 17:00 roll would have given NZDUSD a session-VARYING open (17:00 on 79% of
  sessions, 17:15 on the rest) and a different anchor from the other three pairs; and
  deriving the decision clock from minutes-from-open would have put the grid on `:14/:44`
  and silently deleted NZDUSD's 13:14/14:14/15:14 decisions. **Pin a decision clock to the
  WALL clock, not to minutes-from-open, when the archive has minute-of-hour structure**,
  and check whether a coverage gap has a fixed minute-of-hour signature before reading it
  as market microstructure.
- Evidence: `forex/noise_vwap/reports/FINDINGS.md` §B/§C/§D/§E,
  `.../reports/FINAL_REVIEW.md` ("What would have been concluded without the controls" —
  four of five controls each would have produced a confident wrong next step),
  `.../artifacts/runs/EXP-0001/review.md`, `.../artifacts/runs/EXP-0002/review.md`,
  `.../experiments/hypotheses/HYP-0001.md` + `HYP-0002.md`. Code: `core/session.py`,
  `core/engine.py` + `core/engine_nb.py` (trade-level parity on 400 configs),
  `scripts/entry_information.py::_cluster_t`; tests `tests/test_core.py` (22 checks,
  including TWAP == VWAP-at-constant-volume and TWAP != a real volume-weighted average)
  and `tests/test_parity.py`. Reproduce via
  `python -u -m forex.noise_vwap.scripts.{run_grid,entry_information}`.
- Origin: user asked to replicate `futures/nq/noise_vwap` on four FX majors and to adapt
  the trailing stop given that FX has no volume (2026-08-01). Both preregistered
  hypotheses were rejected; the estimand finding emerged from debugging a t-statistic that
  looked wrong and turned out to be a different, invalid estimand.

### 2026-07-31 — A forward-looking input can be an ANCHOR rather than an ANTICIPATOR: check WHERE it pays before crediting the mechanism you assumed

- Status: provisional (single project, but both markets of a correlated pair agree on every
  panel, and the mechanism reversal is monotone). Confirm or kill by repeating the
  conditional-cell split in a second project that adds any forward-looking or
  externally-sourced input to a past-price model.
- Applies to: adding an implied, surveyed, forecast, or otherwise forward-looking series
  (implied vol, analyst estimates, positioning surveys, weather forecasts, prediction-market
  prices) to a model built from an asset's own history — and to any claim that such an input
  helps because it "knows about scheduled events".
- **The headline: aggregate incremental metrics do not tell you WHY a feature helps, and the
  reason can be the opposite of the stated mechanism.** Adding intraday CBOE VIX to a
  two-input forward-30-minute realised-volatility model on NQ/ES gave a within-slot IC
  delta of **+0.0034 NQ / +0.0063 ES, positive in 11/11 years AND 11/11 slots on both
  markets**, CI excluding zero, robust to a further 15-minute quote lag. Every stability
  check a normal write-up runs, passed. The stated mechanism — implied volatility prices
  *scheduled* events that past price cannot see — was then tested directly and **reversed**.
  Splitting by the causal same-slot z-score of `log(implied/realised)`, the gain over the
  baseline was **monotone DECREASING** in the premium: q1 (implied unusually CHEAP)
  **+0.2220 NQ / +0.2746 ES**, q5 (richest) **+0.0189 / +0.0121**. The input pays right
  *after* a realised-volatility spike, where a past-price model over-extrapolates (its skill
  there was −0.187/−0.203, i.e. **worse than naive persistence**) and a slow, daily-scale
  level pulls the forecast back toward normal. It is an **anchor**, not an anticipator.
- **The single sharpest test is the one cell where the assumed mechanism must fire.** The
  13:59 decision forecasting 14:00–14:30 ET — the FOMC statement window, the most
  concentrated *scheduled* intraday volatility event in the US session — was the input's
  **WORST of eleven slots (+0.0004 NQ / +0.0237 ES)**, while its best were the
  *information-poor morning* slots (+0.1678/+0.2028), where the model's own state is
  thinnest. One conditional cell falsified the mechanism the aggregate number appeared to
  support. Pick that cell before the run and name it in the hypothesis.
- **Read the gain by decile of the BASELINE's own error too.** Here the new input made the
  EASY calls *worse* (deciles 1–5: −0.18..−0.05) and the hard ones better (deciles 7–10:
  +0.04..+0.13) on both markets. A net-positive average was a *redistribution* of accuracy,
  not a uniform improvement — which matters if the decision only consumes one end of that
  distribution.
- **Sub-lesson, and the arm that actually decided the run: benchmark a new EXTERNAL data
  source against the cheapest INTERNAL column you have not yet used.** The obvious
  degenerate control was "baseline + the naive benchmark the metric is scored against"
  (here trailing 30-minute realised vol: one column, already computed, containing zero
  implied-volatility information). It **beat** three engineered features off an external
  daily feed on both markets (+0.0717/+0.1061 vs +0.0656/+0.0972), as did three
  deliberately redundant windows of the same internal quantity (+0.1069/+0.1311). Before
  taking a production dependency on an outside feed, make it beat a column you already own.
- **Sub-lesson on ratios, confirming the 2026-07-27 entry below in a new domain:
  `log(implied) − log(realised)` is mostly its DENOMINATOR** when the numerator is a
  slower-moving quantity. Spot VIX is a 30-*day* number and barely moves across a
  30-*minute* clock, so the "variance risk premium" correlated **−0.857 NQ / −0.843 ES with
  realised volatility alone**, the bare denominator out-scored the ratio (|IC| 0.845 vs
  0.611), and residualising the premium on realised left the implied *level* plus noise —
  i.e. there was no separate premium dimension at all. Same disease, reached from the
  implied side. Its per-slot mean also ran −0.110 → +0.689 across the session (implied flat
  by construction, realised decaying), so a fixed threshold on it would have been a clock.
- **Watch for a shared term in the "does X precede Y" precondition test.** `vrp` is
  `log(implied) − log(past)` and the change target is `log(fwd) − log(past)`; both carry
  `−log(past)`, so their +0.32/+0.34 IC is mechanically inflated and is NOT evidence of
  anticipation. Same family as entry (d) immediately below.
- Useful positive note: the cross-market asymmetry predicted *in advance* did hold — VIX is
  an SPX measure, so ES (native) was predicted to gain more than NQ (proxy) and got roughly
  twice as much on both metrics. That is what confirms the input really is what you think it
  is, even when it is too small to use. **Prefer a mechanism prediction that is ASYMMETRIC
  across your markets over the usual "both markets agree" check** — the latter is nearly
  free on a correlated pair, the former can fail.
- Rule-9a note worth porting: joining a CASH index series to a FUTURES decision clock loses
  the US market holidays on which futures trade a shortened session and the cash index does
  not publish at all — 87 sessions here. It first looked like a time-of-day-selective join
  failure (morning slots 97.8%, afternoon 100%) and was not: holiday sessions only *have*
  morning rows. Check whether an apparent per-slot coverage gradient is really a per-session
  one before treating it as a hidden filter.
- Evidence: `futures/nq/vei_exploration/artifacts/runs/EXP-0017/review.md` (+
  `implied_vol_{NQ,ES}.txt`, `premium_cell_{NQ,ES}.txt`),
  `futures/nq/vei_exploration/reports/FINDINGS.md` §Q,
  `.../experiments/hypotheses/HYP-0014.md`. New tested module `core/vix.py` (causal as-of
  join asserted in code) + `tests/test_vix.py` (8 checks). Reproduce via
  `python -u -m futures.nq.vei_exploration.scripts.{hyp_0014_implied_vol,hyp_0014b_premium_cell} {NQ|ES}`.
- Origin: user asked to relate this project's volatility findings to VIX data held in the
  workspace (2026-07-31). The project's own backlog had recorded the direction as
  "data-blocked"; the data existed at `futures/data/vix/`.

### 2026-07-31 — Three cheap controls that each flipped a confident, correctly-signed, CI-excluding-zero result: the MEAN alongside the rank, the REVERSED direction, and a VOLATILITY-matched split

- Status: provisional (all three are single-project; each is supported by an executed
  control-bearing run and each CHANGED that run's verdict). Confirm or kill by re-running
  the named test in a second project — the first one is listed below and is
  evaluation-only.
- Applies to: (1) any rank IC reported against a return or a P&L; (2) any cross-asset or
  cross-instrument lead-lag claim; (3) any regime/conditioning split, including ones
  already matched on time of day.
- **(a) Rank IC and MEAN quintile spread can give OPPOSITE readings on the same rows, and
  in opposite directions across asset classes.** On NQ/ES/GC 1-min RTH, 30-min trailing
  return vs next 30-min return, 40k decisions each: **GC rank IC −0.0360 [CI excludes 0]
  with a mean q5−q1 spread of −0.15 ticks [CI spans 0]**; **ES/NQ rank IC ≈ 0 [CIs span 0]
  with mean spreads +1.09 / +3.34 ticks [CIs exclude 0]**. Gold has significant *rank*
  reversion with no expectancy; the indices have no *rank* momentum but real positive
  expectancy. The reconciliation is distributional: **equity intraday momentum lives in
  the TAILS** — large moves continue, typical moves do not — and a rank statistic weights
  the median observation, so it cannot see it. This is the mechanical reason a **breakout**
  rule works on NQ/ES while an unconditional momentum tilt does not, and it extends
  `vei_exploration` EXP-0013's "rank IC tracks the median trade" warning from *trade P&L*
  to *raw returns*, where it flips the sign of the conclusion rather than merely deflating
  it. **Report both, every time, and say which one the decision consumes** (equal-risk
  per-bet sizing consumes the mean; a barrier-truncated book may consume something closer
  to the median). Confirming test: recompute the headline ICs of `vei_exploration`
  EXP-0011/0012/0015 alongside their mean-based twins on the frozen predictions —
  evaluation-only, no refit, so it cannot be re-tuning.
- **(b) For any lead-lag claim, run the REVERSE direction before anything else — it is one
  line and it beats the staleness control, the horizon surface and the sibling split
  combined.** A genuine lead is ASYMMETRIC; a symmetric "each predicts the other" result
  is the signature of shared or non-synchronous contemporaneous information. Testing
  whether the dollar leads gold at a 5-minute non-overlapping clock, within-block partial
  Spearman IC controlling for own momentum: forward **−0.0049 [−0.0078,−0.0020]** —
  correctly signed, CI excluding zero, decaying with horizon exactly as a transmission lag
  should, and NOT a stale-price artifact (an EUR-only basket at 0.42% forward-filled
  minutes vs 4.70% retained the whole effect). But the **REVERSE was −0.0115, i.e. 2.36x
  LARGER** (ES 1.37x, NQ 2.72x): gold "leads" the dollar more than the dollar leads gold.
  Without the reverse arm this prints as a clean confirmed lead-lag. Read the
  contemporaneous link for scale too — here it was ~**75x** the 5-minute lagged one, which
  is what efficient transmission looks like.
- **(c) Matching a regime split on TIME OF DAY is not sufficient — match it on VOLATILITY
  as well.** Almost every intraday label is correlated with volatility, so cells selected
  by it inherit a volatility gradient even when slot composition is matched *exactly*. A
  cross-asset "factor coherence" label (trailing 60-min |corr| of the index with a
  synthetic DXY, same-slot z-scored, split at a matched 30% rate thresholded WITHIN each
  slot, so both cells had identical sizes and identical time-of-day mixes) gave a gold
  momentum contrast of **+0.0496 [+0.0069,+0.0853]** whose re-pairing null centred at zero.
  Re-running the split within **volatility quintiles** as well as within slots collapsed it
  to **−0.0047 [−0.0274,+0.0272]**, and the null's frac≥real went 0.067 → 0.600. The
  collapse was NOT a weakened split: the coherence spread between cells was unchanged
  (0.451/0.093 → 0.439/0.095) while the volatility ratio fell 1.46 → 1.11. Always run the
  MIRROR arm too (the other label conditioned on this one); here it was +0.0020, so neither
  label carried anything once the other was fixed. Sub-lesson, arriving from the SELECTION
  side of `vei_exploration` finding P: **a modest pairwise correlation between two labels
  does not imply the cells they select are matched.**
- **(d) Bonus control from the same runs — the shared decision-bar close manufactures
  reversion.** `past` ends and `fwd` starts at the same close, so pricing error there
  (bid-ask bounce, a stale or one-tick print) enters with +1 and −1 and induces mechanical
  negative correlation. Lagging the past window by one bar so the two share no price:
  **31-56% of measured reversion is artifact at a 5-minute horizon** (GC 0.69 / ES 0.59 /
  NQ 0.65 / synthetic DXY 0.44 retained) and **12-33% at 30 minutes**. Worst on a synthetic
  forward-filled index. The majority survives everywhere, so such reversions are real — but
  any short-horizon reversal quoted without this control is inflated by a third to a half.
- Meta-point worth as much as the three controls: across five runs, a normal exploratory
  pass would have reported **three** confident, correctly-signed, CI-excluding-zero results
  that a single extra control then destroyed. The controls cost a few lines each. Same
  family as `vei_exploration` findings H and P (score the degenerate limit; always run the
  redundant control), now confirmed from three new directions.
- Evidence: `futures/nq/claude_exploration_1/reports/FINDINGS.md` §B, §C, §E, §G and its
  closing section "What would have been concluded without the controls";
  `artifacts/runs/EXP-0001/`, `EXP-0002/`, `EXP-0005/`. Helpers + tests:
  `core/stats.py::within_slot_partial_ic`, `regime_contrast`, `_split_by_rate`,
  `repair_sessions`; `core/features.py` (`pastlag_*`, `slot_zscore`);
  `tests/test_core.py` (30 checks). Reproduce via
  `python -u -m futures.nq.claude_exploration_1.scripts.{s1_residual_momentum,s2_lead_lag,s3b_gold_coherence}`.
- Origin: user asked for hypotheses on DXY/gold/ES and a test of them (2026-07-31). All
  four preregistered hypotheses were rejected; these controls are what did the rejecting.

### 2026-07-27 — A fixed threshold on a SESSION-RESET feature is a time-of-day selector; fix it with a trailing same-slot Z-SCORE, not a ratio-to-mean

- Status: confirmed (calibration); provisional (the information gain — holdout-pending)
- Applies to: any feature whose window RESETS each session (intraday ATR, running VWAP
  distance, cumulative volume/RVOL, session-anchored ranges, opening-range extensions) and
  is then compared against a FIXED constant to define a regime, a gate, or a filter.
- Learning: a session-reset window is under-populated early and anchored on the opening's
  conditions, so the feature carries a deterministic intraday drift and a fixed cut on it
  selects wildly different fractions of the day at different times. On NQ/ES intraday
  VEI = ATR(10)/ATR(50), the canonical `VEI > 1.10` regime cut selected **1.5% of the
  10:30 decisions and 18.4% of the 15:30 decisions** (ES 2.6% → 22.4%); per-slot selection
  rate CV **0.93 / 0.88**. The "volatility regime" label was substantially a clock. Note
  this is NOT the same defect as a warm-up mis-initialisation — repairing the seed
  explained only ~20% of the drift; the session-reset anchoring is the dominant cause and
  survives any seeding fix.
- **The fix, and the non-obvious part: normalise against the trailing SAME-SLOT
  distribution (the noise-area construction applied to a feature), and use the Z-SCORE,
  not the ratio-to-mean.** Dividing by the trailing same-slot mean removes per-slot
  LOCATION but not per-slot SCALE, so it only half-works: selection-rate CV fell
  0.93 → 0.135 (NQ) / 0.88 → 0.105 (ES) for `x/mu`, but 0.93 → **0.050** / 0.88 →
  **0.041** for `(x-mu)/sd`. Empirically the feature's per-slot dispersion was not
  proportional to its per-slot level, so the two corrections are separable and both are
  needed. Keep `x/mu` only when an interpretable "1.0 = normal for this time of day"
  reading matters more than calibration.
- **Normalising did NOT destroy the feature's information** — the recurring fear, and here
  it was wrong. The magnitude-preserving `x/mu` retained 88.1% (NQ) / 92.5% (ES) of the
  raw feature's momentum contrast at matched selection rate, and the z-score was the only
  variant of four whose CI excluded zero on both markets in both a within-slot and a
  pooled metric. Caveat on reading that: the point estimate rose 28% on NQ but was FLAT on
  ES with a slightly narrower interval — so it is a **better-conditioned measurement, not
  a bigger effect**. The construction transfers; the size of the gain does not.
- Method notes: (1) use an ORDINAL percentile only if magnitude genuinely does not matter —
  it calibrates as well as the z-score but discards how far from normal a reading is, and
  it scored worse than the z-score on both markets here; (2) apply the rule-9a fractional
  `min_obs` (2/3 of the lookback, not the strict full window), and verify the coverage loss
  is UNIFORM ACROSS SLOTS — here it cost 60 of 3710 sessions at every slot equally, which
  is the pass signal; a loss that tracked time-of-day liquidity would be the tell; (3) when
  sweeping the lookback, scale `min_obs` with it — holding it fixed made it unreachable at
  the short end and silently defined nothing; (4) compare every candidate at a MATCHED
  global selection rate, or you are reading a selectivity dial.
- **Process caution learned alongside it:** changing a feature's normalisation *after*
  seeing a finding fail, and then finding a normalisation under which it passes, is a
  search — even when each step is individually principled. Here the repaired label removed
  the exact reason the project's headline finding had been downgraded, and the honest
  ruling was still that it earns **one clean forward test**, not a retroactive pass.
- Evidence: `futures/nq/vei_exploration/scripts/s5_slot_normalised.py` →
  `artifacts/runs/EXP-0009/`, `reports/FINDINGS.md` §I, `experiments/hypotheses/HYP-0006.md`.
  Helper + tests: `core/analysis.py::causal_slot_stats`,
  `tests/test_core.py::test_slot_normalisation_removes_a_per_slot_level_shift` (pins the
  location-vs-scale distinction). Reproduce via
  `python -u -m futures.nq.vei_exploration.scripts.s5_slot_normalised {NQ|ES}`.
- Origin: user proposal (2026-07-27) to apply the noise-area same-time-of-day construction
  to VEI itself rather than to displacement.

### 2026-07-27 — Never select a RATIO feature on a metric its own NUMERATOR maximises; test it with the degenerate no-denominator control

- Status: confirmed
- Applies to: any feature defined as a ratio, spread, or normalisation of one quantity by
  a slower/broader version of itself — ATR(short)/ATR(long), realised-vol ratios,
  volume-vs-average-volume, price-vs-moving-average, spread-vs-rolling-spread — whenever
  variants of it are ranked against each other by a predictive score.
- Learning: a ratio X/Y is only a ratio to the extent Y actually varies. As Y's effective
  memory grows it approaches a constant over the evaluation window, and X/Y degenerates
  into a **rescaled X**. If X's own level is a strong predictor of the target, the ranking
  metric will then reward variants *for ceasing to be ratios*. This is not a subtle
  contamination: on NQ/ES intraday VEI = ATR(short)/ATR(long), scoring ten variants by
  forward-vol IC gave `IC_fwdvol` = **0.89·corr(variant, vol level) + 0.01, R² 0.992 on
  BOTH markets** — the metric was, to three significant figures, nothing but
  level-likeness. The tempting "best" variant (`wilder_20_100`, IC +0.396/+0.353 vs
  canonical +0.202/+0.207) was simply the most degenerate one.
- **The decisive test is a one-line control: score the bare NUMERATOR, with no denominator
  at all.** It is not a candidate feature; it is the degenerate limit. If it *wins* the
  metric, the metric cannot select among ratios — no further argument is needed. Here the
  no-denominator ATR(10) topped the column outright (+0.575 NQ / +0.613 ES). Report it
  alongside the cross-variant regression of the metric on corr(variant, level); a high R²
  plus a winning numerator is conclusive.
- **Partialling the level out is only a PARTIAL repair.** A rank-partial IC (target and
  feature both residualised on the level) broke the fit (R² 0.992 → 0.30/0.50) but the
  bare-numerator controls still topped it, because a *differently windowed* level carries
  information the specific level being partialled out does not. Conclusion: when the
  target is the same quantity the numerator measures, **no metric built on that target can
  select the ratio** — change the target, don't patch the score.
- **Worse than uninformative — often anti-selective.** The metric ranked variants
  *opposite* to the property the ratio existed to provide: correlation between the
  momentum-regime contrast and level-likeness was **r −0.915 (NQ) / −0.871 (ES)**, and the
  `IC_fwdvol` winner had the *lowest* contrast of any ratio tested. So the score is not a
  weak signal to be used with caution; acting on it actively destroys the feature. Always
  check whether the convenient ranking metric and the metric you actually care about are
  correlated *at all* before selecting on the convenient one.
- **Corollary worth its own line — the control often answers the more interesting
  question.** Because the bare numerator is "the level with no ratio content", contrasting
  it against the ratios isolates what the ratio adds. Here the pure vol LEVEL had a
  momentum-regime contrast of essentially **zero** (−0.005 NQ / +0.023 ES, CIs spanning 0)
  while every genuine ratio was +0.06..+0.12: **high volatility alone does not select the
  momentum regime; the expansion RATIO does.** That vindicated the construct on one axis
  while the same run showed it near-worthless on the other (forecasting vol, where the
  level dominates). A ratio and its numerator can be measuring genuinely different things
  — run the degenerate control on *both* axes before concluding either way.
- Method notes that made the result clean: score every variant on ONE **common sample**
  (the intersection where all are defined) or a longer window silently changes which times
  of day are measured; and match the **selection rate** when threshold-based behaviour is
  compared, so no variant wins by relabelling more observations. Treat a multi-variant scan
  against the project's primary metric as a SEARCH — read the slope across variants, not
  the argmax.
- Evidence: `futures/nq/vei_exploration/scripts/s1c_selection_metric.py` →
  `artifacts/runs/EXP-0008/selection_metric_{NQ,ES}.txt`,
  `futures/nq/vei_exploration/reports/FINDINGS.md` §H, `experiments/hypotheses/HYP-0005.md`.
  Helper + tests: `core/analysis.py::partial_spearman`,
  `tests/test_core.py::test_partial_spearman_removes_the_conditioning_variable`.
  Reproduce via
  `python -u -m futures.nq.vei_exploration.scripts.s1c_selection_metric {NQ|ES}`.
- Origin: EXP-0006 flagged a suspiciously high-scoring long-memory variant and deliberately
  refused to adopt it; EXP-0008 (2026-07-27) tested the suspicion and upheld it.

### 2026-07-26 — Compare smoothers at matched effective MEMORY (centre-of-mass), not matched nominal n; and `ewm(adjust=False, min_periods=n)` is NOT textbook Wilder ATR

- Status: confirmed
- Applies to: any study that concludes one estimator/smoother "beats" another (SMA vs
  EMA vs Wilder RMA for ATR, and by extension any moving-average feature), and any
  Wilder/RMA ATR built with pandas `ewm` — especially one that RESETS per session.
- Learning, part 1 (the confound): `SMA(n)` has centre-of-mass `(n-1)/2`; an EMA with
  `alpha` has com `(1-alpha)/alpha`, so Wilder (`alpha=1/n`) has com `n-1` — **twice**
  the SMA of the same nominal `n`. Comparing `sma(10,50)` against `wilder(10,50)` therefore
  changes estimator FORM and effective MEMORY together, and the memory is usually the
  bigger lever. On NQ/ES intraday ATR ratios the confound fully reversed the conclusion:
  a com-matched plain `SMA(19/99)` reached forward-vol IC +0.186 NQ / +0.188 ES vs
  Wilder(10/50)'s +0.157 / +0.195 (a wash, one market each way), while the reverse control
  `Wilder(5/25)` — com-matched DOWN to SMA(10/50) — collapsed to IC **+0.001 / +0.040**,
  worse than the SMA it was supposed to beat. Changing memory alone (SMA 10/50 → 19/99)
  roughly tripled the IC on both markets. Related trap: Wilder `alpha=1/n` **is** exactly
  `ewm(span=2n-1)`, so a "Wilder vs EMA" row is not an estimator contrast at all — it is
  the same recursion at two alphas.
- Learning, part 2 (the initialisation): pandas `ewm(..., adjust=False)` seeds the
  recursion at the FIRST observation; `min_periods=n` only MASKS the first n-1 outputs, it
  does not seed with the first n-bar SMA the way textbook Wilder ATR does. Two separable
  costs, both material: (a) `min_periods=n` on an `alpha=1/n` recursion admits bars whose
  average has had well under one e-folding of data — on the NQ/ES VEI that was 17% of all
  decisions, and masking them lifted IC +0.157→+0.242 (NQ) / +0.195→+0.249 (ES); (b) the
  seed itself — a textbook SMA seed lifted IC to +0.202/+0.207. The shipped feature was
  worse than BOTH repairs. This is normally a one-off warm-up you can ignore on a
  continuous series, but **a feature that resets each session pays it every session**
  (~3710x here), so it becomes a permanent bias rather than a burn-in.
- Learning, part 3 (the calibration corollary): a ratio of a short to a long
  session-reset ATR is NOT centred on 1. The long window stays anchored on the high-vol
  open while the short window walks off it, so the ratio starts far below 1 and drifts up
  monotonically all day (mean by 30-min slot: 0.745→1.165 NQ, 0.788→1.216 ES). A fixed
  `ratio = 1` "calm/expansion" line is therefore a TIME-OF-DAY threshold, not a volatility
  threshold, and any metric defined as crossings of that line (e.g. a "whipsaw rate")
  partly measures the clock. Note the mis-initialisation explains only ~20% of the
  sub-1 mean — the session-reset anchoring is the dominant cause, and an SMA version with
  no recursion seed at all is also below 1.
- Consequence: (1) before crediting an estimator swap, run the com-matched control in
  BOTH directions (match the loser up, and the winner down) — one direction alone can be
  explained away; (2) for any per-session `ewm` ATR, either seed with the textbook n-bar
  SMA or set `min_periods` to the recursion's memory (~2n-1) rather than n, and report
  how many decision points the choice adds or removes; (3) never read a session-reset
  ratio against a fixed 1.0 line without first plotting its mean BY TIME OF DAY. Caveat
  from the same workspace: de-seasonalising such a ratio can DESTROY its information (the
  absolute level is what carries), so the fix is to re-label the threshold, not to
  normalise the drift away.
- Evidence: `futures/nq/vei_exploration/scripts/s1b_estimator_controls.py` →
  `artifacts/runs/A_smoothing/estimator_controls_{NQ,ES}.txt`,
  `futures/nq/vei_exploration/reports/FINDINGS.md` §A-corrected (+ the superseded §A).
  The same `ewm(alpha=1/n, min_periods=n, adjust=False)` warm-up defect is present at
  `futures/nq/noise_vwap/core/vei.py:58` (EXP-0036), so that revisit also ran the
  mis-initialised feature. Reproduce via
  `python -u -m futures.nq.vei_exploration.scripts.s1b_estimator_controls {NQ|ES}`.
- **Downstream consequence, added after EXP-0006 (the reason this is worth a shared
  entry):** repairing the warm-up was NOT cosmetic. Re-running the project's five prior
  experiments through the repaired feature (single-variable change, legacy path retained
  for a rule-23 reproduction that passed exactly) **shrank the project's headline finding
  until it failed its own preregistered kill test** — a momentum-regime contrast went from
  +0.110 [+0.025,+0.172] NQ / +0.103 [+0.021,+0.168] ES to +0.069 [−0.007,+0.134] /
  +0.086 [+0.009,+0.147], i.e. 63%/83% of published with NQ's CI crossing zero. Two
  further legacy conclusions inverted, both because the warm-up bias was itself TIME-OF-DAY
  dependent (worst early in the session, where the long window is least populated): a
  "de-seasonalising destroys information" corollary reversed (the causal same-slot
  percentile is now equal-or-better than the raw level), and a monotone dose-response
  slope flattened to noise. Note also that the defect **inflated the feature's apparent
  persistence** — lag-1 autocorrelation FELL 0.549→0.441 on repair, because consecutive
  bars shared one contaminating seed. General lesson: a per-reset warm-up bias is not a
  rounding error; it is a slowly-decaying common component injected into every window,
  and it can manufacture both autocorrelation and a time-of-day gradient that later
  studies then interpret as signal. Repair it BEFORE building findings on the feature.
- Origin: reviewer challenge to `futures/nq/vei_exploration` EXP-0001's "the ATR
  estimator dominates smoothing" headline (2026-07-26); the objection was upheld, the
  finding's attribution withdrawn, and the repair + full re-run registered as EXP-0006
  (`artifacts/runs/EXP-0006/review.md`, HYP-0003).

### 2026-07-20 — A same-time-of-day noise band is fully summarized by its per-slot SYMMETRIC LEVEL/width: none of a √t reshape (cone), a distributional reshape (quantile), or an up/down redistribution (asymmetric) adds value; the morning is super-diffusive

- Status: confirmed
- Applies to: any same-time-of-day "noise area" / displacement-envelope built as a
  per-slot empirical statistic anchored at the session open (the Zarattini/
  Quantitativo Noise-Area + VWAP family), and more generally to replacing a
  per-slot empirical intraday dispersion profile with an analytic diffusion model.
- Learning: it is tempting to collapse the 13-per-day per-slot empirical means
  (one thin same-slot sample each) into ONE causal per-session vol scalar times an
  analytic √(elapsed) profile — a driftless-random-walk "diffusion cone." This is
  parsimonious (90×13 params → ~1) and, on a THIN instrument, would also kill the
  Rule-9a strict-`min_periods` per-slot coverage deletion. It does NOT work as a
  replacement. Calibrated to match the empirical band's END-OF-DAY width (so the
  test isolates intraday SHAPE, not width), the cone was WORSE on both NQ (ΔSharpe
  −0.101, +705 trades, net pt/trade 3.159→2.530) and ES (ΔSharpe −0.125, +436
  trades). The diagnostic is the residual m(mfo)=empirical_sigma/cone_sigma: on
  BOTH markets the empirical band is ~1.35–1.55× WIDER than √t in the first hour
  and converges to 1.0 at the close. i.e. real intraday displacement is SUPER-
  DIFFUSIVE in the morning (an opening-volatility bulge / positive early
  autocorrelation wider than a random walk), so an end-of-day-calibrated cone is
  too narrow early, admits noisier morning breakouts, and dilutes per-trade
  quality. The per-slot empirical SHAPE — specifically the morning excess width —
  is the load-bearing part of the construct, and the effect transfers across the
  NQ↔ES sibling pair, so it is a real structural property of the index tape, not
  estimation machinery.
- Reusable sub-lessons: (1) before replacing an empirical intraday dispersion
  profile with any analytic model, plot the residual (empirical/model) BY TIME OF
  DAY; a monotone-from-the-open decay shape is the intraday-vol seasonality the
  model omits and is the real target for a parsimonious re-cast — a re-cast must
  REPRODUCE the morning excess, not assume √t. (2) The Rule-9a coverage win from a
  session-level (open+close) scalar is real but NEGLIGIBLE on liquid indices (cone
  recovered 0.2% of decisions, all near lunch); it only matters on the thin markets
  where the strict `min_periods` bug actually bites (GC/YM/RTY). (3) A "worse real
  pass" is a clean REJECT that spends no Null C — but its residual can still be the
  study's most valuable output. Sign discriminator held: the sibling reproduced
  both the sign and the residual shape, confirming structure over machinery.
- Quantile companion (transform 2, EXP-0021): recasting the per-slot dispersion as a
  qth PERCENTILE instead of the MEAN also adds nothing. The trap is that raising q
  just WIDENS the band (a capacity dial); so compare at MATCHED median width (rescale
  each q so its median sigma equals the mean band). At matched width every q cell
  collapsed onto the mean (best q0.90 NQ ΔSharpe +0.032, ES +0.067, both < a +0.10
  gate) and — the decisive tell — the residual quant/mean by slot was ≈1.0 EVERYWHERE
  (0.96–1.01): the matched quantile is just the mean band RESCALED, no reshaping. So
  the per-slot |move| distribution's SHAPE carries no info beyond its LEVEL; the MEAN
  is a sufficient statistic for the band at fixed width. The only "win" (median band
  q0.50, narrower than the mean → more trades, more NQ drift booked) is the same
  width/capacity dial, gone under matched width. Reusable method: always split a "new
  dispersion statistic" test into a RAW view (shows the width dial) and a MATCHED-WIDTH
  view (isolates shape), and read the residual-vs-baseline BY SLOT — a flat ≈1.0
  residual means you only changed width.
- Asymmetric companion (transform 3, EXP-0022): recasting the SYMMETRIC band as a
  per-side band — separate up/down half-widths from the causal semi-means
  (up = mean(max(move,0)), dn = mean(max(-move,0)), which sum to the baseline sigma
  identically), tilt-blended so the TOTAL half-width is conserved for every tilt
  (sig_up+sig_dn == 2·sigma) — also adds nothing, and this is the cleanest of the
  three tests because the conservation is EXACT BY CONSTRUCTION (proved in a test),
  so there is no width-dial confound and no RAW/MATCHED split is even needed; every
  tilt is already width-matched. Every tilt failed the +0.10 gate: NQ monotonically
  WORSE (ΔSharpe −0.065/−0.095/−0.110 at tilt 0.5/1.0/1.5); ES best +0.023, tilt 1.5
  collapses. The residual (sig_up/sigma, sig_dn/sigma by slot) IS a real, NQ↔ES-
  transferring asymmetry but a SMALL one — up-edge ~2–5% wider, down-edge ~2–5%
  narrower, across ALL slots, largest mid-day (up/dn ≈1.09–1.10). Crucially it points
  the SAME direction as the drift (index up-drift → larger up semi-mean), and acting
  on it HURTS on the strong-drift market: for a momentum breakout system, widening the
  up-threshold rejects the drift-driven up-breakouts it rides while narrowing the
  down-threshold admits counter-drift down-breaks. The symmetric band is not just
  adequate but actively BETTER — the up/down asymmetry is a DRIFT property the
  strategy ALREADY monetizes (VWAP gate + ride-to-close), so re-sizing the band to it
  double-counts and mis-selects. Reusable sub-lesson: a real, sibling-confirmed
  structural residual is NOT automatically a lever — if it merely restates a
  first-order feature (here drift) the strategy already captures downstream, exploiting
  it upstream double-counts and degrades selection. Build the redistribution to
  conserve the conserved quantity (total width) so the test is confounder-free.
- SYNTHESIS (transforms 1–3 complete, programme exhausted): the noise-area band is
  fully summarized by its per-slot SYMMETRIC LEVEL/WIDTH. A √t reshape is worse
  (empirical morning shape is load-bearing), a distributional reshape is inert (mean
  is a sufficient statistic at fixed width), and an up/down redistribution is
  inert-to-harmful (the asymmetry is drift already monetized). None of the dispersion
  statistic's time-profile SHAPE, per-slot distributional SHAPE, or up/down SYMMETRY
  carries information beyond the per-slot symmetric level. Retain the faithful mean
  band; do not spend further transforms on the band construction.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0020/review.md` (+ `cone_nq.txt`,
  `cone_es.txt`), `.../EXP-0021/review.md` (+ `quant_nq.txt`, `quant_es.txt`), and
  `.../EXP-0022/review.md` (+ `asym_nq.txt`, `asym_es.txt`),
  `futures/nq/noise_vwap/core/bands.py`, `futures/nq/noise_vwap/tests/test_bands.py`,
  `futures/nq/noise_vwap/experiments/hypotheses/HYP-0012.md` + `HYP-0013.md` +
  `HYP-0014.md`. Reproduce via
  `python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real {NQ|ES}`,
  `... .scripts.hyp_0013_quantile_band real {NQ|ES}`, and
  `... .scripts.hyp_0014_asymmetric_band real {NQ|ES}`.
- Origin: user asked to transform paper-4824172's noise-area concept "a different
  way to how it's currently calculated"; chosen staged programme
  (cone → quantile → asymmetric), completed 2026-07-20.

### 2026-07-20 — Cross-market same-signal confirmation concentrates per-trade quality on tightly-coupled siblings but yields NO deployable daily-Sharpe alpha

- Status: confirmed
- Applies to: gating instrument A's intraday breakout entries on the CONTEMPORANEOUS
  same-direction breakout of a correlated sibling B ("only take the trade if both broke
  out"). Now tested on both loosely-coupled (GC gated on ES, EXP-0007) and tightly-coupled
  (NQ gated on ES, EXP-0018) pairs in the Noise-Area + VWAP family.
- Learning: the "a real breakout shows on BOTH indices; a solo break is just noise" thesis
  is intuitive and its per-trade effect DEPENDS ON COUPLING, but in NEITHER case does it
  produce a risk-adjusted edge. The discriminator is what the confirm filter does to
  GROSS-PER-TRADE on the KEPT trades:
    - GC↔ES (loose): the `agree` filter HALVED gross/trade (+0.371→+0.162 pt) = selecting
      the WORSE trades = a rarity filter (wrong-signed selection).
    - NQ↔ES (tight): the `agree` filter RAISED gross/trade (+4.945→+5.302), net/trade
      (+4.470→+4.827) and hit-rate (0.380→0.407) while trading ~30% less — so the tighter
      coupling genuinely concentrates per-trade quality; ES confirmation carries REAL
      per-trade information, exactly where the thesis predicts.
  Yet on NQ this still did NOT monetize: it is a pure turnover/capacity trade — total net R
  fell ~25%, daily P&L got lumpier (day-net t 2.68 vs 3.15), and net daily Sharpe was flat-
  to-down (1.074 vs 1.102, uplift −0.029, below a +0.05 gate). "Two independent same-
  direction breakouts" is just a higher evidential bar that raises selection quality and
  cuts exposure; better selection + less exposure = no risk-adjusted gain. It is a
  capacity/cost lever ("trade less, per-trade-better"), never alpha.
- Reusable sub-lessons: (1) `gate` (B in ANY breakout) ≈ `agree` on a tightly-coupled pair
  because B's breakouts during an A-signal are almost always same-direction — so a "did B
  break out at all" filter is not meaningfully different from "did B agree". (2) The SOFTER
  gate (B merely on the correct side of its own VWAP) was inert-to-harmful on NQ (gross/kept
  FELL): the full noise-area BREAKOUT on B carries the per-trade info, B's VWAP sign does
  not — the noise-area construct is load-bearing. (3) B does NOT lead A: entering A in B's
  breakout direction (`es_dir`) was much worse (Sh 0.70 vs 1.10) and the mirror `es_opp` was
  genuinely negative (gross −0.51, not just cost — no Rule-16 rescue). (4) On BOTH pairs the
  only Sharpe-beater was the `disagree` filter (take A only when B does NOT confirm), and on
  BOTH it failed its Rule-18 re-pairing null with the null CENTERED AT ~0 (NQ z=1.08 frac
  0.14; GC z=1.53 p≈0.073): center-at-0 rules out a pure rarity filter but the real uplift
  sits inside the null band = consumed-history post-hoc screen, holdout-pending, not an edge.
- Consequence: when testing cross-market confirmation, read gross-per-trade on the KEPT
  trades FIRST (rising = real per-trade info on a tight pair; falling = rarity filter on a
  loose pair) AND read total net R + daily Sharpe (both can be flat/down even when per-trade
  quality rises). A confirm filter that improves per-trade metrics but cuts total net R and
  leaves Sharpe flat is a capacity/turnover lever — bank it as that (or default-off), never
  as alpha. Gate the re-pairing null on the primary clearing its metric; interpret the
  null's CENTER, not just its tail.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0018/review.md` (+ `es_confirm.txt`);
  contrast `futures/gc/noise_vwap/artifacts/runs/EXP-0007/review.md`. NQ reproduces via
  `python -m futures.nq.noise_vwap.scripts.hyp_0010_es_confirm NQ 90 0.50 200`.
- Origin: user's "if one index breaks the noise area the other should too, else it's noise"
  thesis on NQ↔ES (2026-07-20); direct sibling of the GC HYP-0005 conditioning study.

### 2026-07-20 — A single-market Null C pass does not validate a mechanism that predicts cross-market transfer; the sibling market is the mechanism test

- Status: confirmed
- Applies to: any edge whose proposed MECHANISM is a broad/structural force shared by
  sibling instruments (e.g. a pan-index close phenomenon: MOC imbalances, passive-fund
  rebalancing, 0DTE gamma). Found on the NQ noise-VWAP early-flat-before-close cutoff.
- Learning: passing a drift-preserving return-shuffle Null C on ONE instrument confirms
  the effect is a real feature of THAT tape (not machinery) — but it says NOTHING about
  whether the STATED mechanism is correct. If the mechanism is a shared structural force,
  it makes a falsifiable cross-market prediction. Test the sibling. On NQ the early-flat
  cutoff PASSED its Null C convincingly (real max ΔSharpe +0.101 vs null max mean −0.048,
  p=0.032, 0/30 draws beat real — and critically the null centered NEGATIVE, cleanly
  separating it from the "fewer-trades→higher-Sharpe" machinery whose null centers
  POSITIVE). Yet the user's structural rationale (3:45 MOC imbalance reveal, passive-close
  rebalancing, 0DTE gamma) bears at LEAST as heavily on the S&P/ES as on the Nasdaq-100
  (SPX 0DTE is the largest 0DTE market; S&P passive AUM exceeds NDX). A pan-index cause
  therefore predicts ES benefits as much or more. ES INVERTED: early-flat was worse than
  baseline AND worse than its own null (noise beat the real tape, p=0.74). So the NQ pass
  is real but the mechanism is FALSIFIED — the surviving effect is NQ-tape-specific, not
  the general structural close phenomenon claimed.
- Two reusable sub-lessons: (1) the SIGN of the null center is the machinery discriminator
  — a looser/fewer-trades "improvement" whose null center is POSITIVE is variance
  amplification (rejected in NQ EXP-0010/0012, GC continuous-stop); a null center that is
  NEGATIVE (noise does worse) means the real effect is genuinely tied to the specific thing
  being cut. (2) A single-market Null C pass is NECESSARY but not SUFFICIENT to credit a
  cross-market mechanism; run the sibling as the mechanism test, and read its sign, before
  attributing the edge to a shared structural cause. Also: an NQ pass that (a) preserves
  net R without increasing it, (b) WORSENS drawdown, and (c) concentrates in a recent
  regime on consumed data is a forward-shadow candidate, not a deployable edge — the null
  pass upgrades it from "machinery" to "real but unexplained/unbanked", nothing more.
- Evidence: `futures/nq/noise_vwap/artifacts/runs/EXP-0013/review.md` (Follow-up Null C),
  `nullc_nq.txt`, `nullc_es.txt`; reproduce via
  `python -m futures.nq.noise_vwap.scripts.hyp_0006_early_flat null {NQ|ES} 30`.
- Origin: user revisited EXP-0013/HYP-0006 with a structural late-session-noise thesis and
  asked to run the previously-gated Null C (2026-07-20).

### 2026-07-18 — Pin artificial opening sentinels in return-shuffle nulls

- Status: confirmed
- Applies to: session-level path reconstruction and path-preserving return
  shuffles
- Learning: when `link[0] = 0` is an artificial opening anchor, including it in
  the permutation and then re-anchoring the first open discards whichever real
  link lands at index 0. This changes the reconstructed session net move. Pin
  the complete opening atom, or use another construction whose claimed
  invariants are proved by tests.
- Evidence: `futures/nq/noise_vwap/tests/test_nulls.py` and
  `futures/vwap_mean_version/tests/test_nulls.py`
- Consequence: every path-reconstruction null must test its opening anchor,
  session net move, complete atom multiset, and path-continuity statistic across
  multiple seeds before its P&L distribution is interpreted.
- Origin: `futures/nq/noise_vwap/core/nulls.py` and
  `futures/vwap_mean_version/core/nulls.py`

### 2026-07-19 — Noise-Area + VWAP cross-instrument transfer: some indices fail at the GROSS level, not just on cost/sizing

- Status: confirmed
- Applies to: porting the Zarattini/Quantitativo Noise-Area + VWAP intraday-momentum
  baseline (equity RTH 09:30–16:00 ET, 30-min clock, VWAP gate) to a new instrument.
  Established across NQ, ES, GC, and now YM + RTY (all via the same audited engine,
  data path + contract economics the only swap).
- Learning: the method's transferability spans a full range, and the failure can be
  at the GROSS (pre-cost) level, which is a harder NO-GO than GC's cost/sizing death.
  Faithful baselines, honest fills (0 same-bar), 1-contract per-day-clustered:
    - NQ (strong intraday drift): gross Sharpe ~1.2, net edge survives → GO-ish.
    - GC / YM (weak): positive gross but cost-fragile — GC gross Sh 0.79 net Sh 0.48;
      YM gross Sh 0.51 (t1.55) net Sh 0.21 (t0.64) @0.50 tick, dies by 1.0 tick. YM's
      $5 tick is a large fraction of the per-trade move (Rule-19 cost-scaling bites).
    - RTY (E-mini Russell 2000, small caps, 2017–2026): **NO gross edge at all** —
      gross −0.253 pt/trade, Sharpe −0.44, t−1.00 BEFORE any cost, monotonically
      worse net. The naive always-long drift control is ALSO negative (Sh −0.45): the
      small-cap tape had no positive intraday drift over the sample, so a breakout-
      momentum system has no favorable backdrop to ride. This is not a cost or sizing
      artifact — there is nothing to size or null-test (real pass fails the primary
      metric at gross = REJECT, no Null-C spent).
- Consequence: when porting an intraday-momentum breakout to a new instrument, read
  the GROSS number and the naive always-long drift control FIRST. A negative gross +
  negative always-long drift is a clean NO-GO that no exit/sizing tweak rescues; do
  not proceed to Null-C or sizing. The equity-index label does NOT guarantee transfer
  — RTY (small caps) behaves oppositely to NQ (large-cap tech) despite both being CME
  equity index futures on the identical session/clock.
- Also (rule 9a, re-confirmed): the strict `min_periods=lookback` band bug ports too;
  the `BAND_MIN_FRAC=0.9` fix keeps YM ~98% / RTY ~96% uniform decision-minute band
  coverage. On RTY the strict-rule drop is UNIFORM across time-of-day (shorter post-
  2017 window under-filling the trailing-90 requirement), unlike GC's late-day skew.
- Evidence: `futures/ym/noise_vwap/reports/BASELINE.md` (+ `BASELINE.txt`,
  `DATA_QUALITY.txt`), `futures/rty/noise_vwap/reports/BASELINE.md`; both baselines
  reproduce via `python -m futures.{ym,rty}.noise_vwap.scripts.run_baseline`.
- Origin: user asked to replicate the noise_vwap baseline on YM and RTY (2026-07-19).

### 2026-07-19 — "Edge localised to a co-market's session hours" ≠ "edge follows that market's direction"

- Status: confirmed
- Applies to: any intraday edge on instrument A that is found to live only in a
  DIFFERENT market B's cash-session window (a cross-asset / shared-risk-factor
  suspicion). Found on GC noise-VWAP, whose edge lives only in equity RTH.
- Learning: showing an edge is CONFINED to another market's trading hours (a "when"
  fact) does NOT imply that market's CONTEMPORANEOUS direction conditions the edge (a
  "which-direction" fact). They are separable and must be tested separately. On GC the
  edge dies in gold's own COMEX pit hours and only works in equity RTH (EXP-0002),
  which strongly suggested "equity momentum bleeding into gold" — yet conditioning GC's
  trade direction on the contemporaneous ES noise-VWAP state DESTROYED the edge:
    - `agree` (take GC signal only when ES agrees) HALVED gross (+0.371→+0.162 pt) and
      flattened net Sharpe 0.49→0.03 on a 78% trade cut. Diagnostic: if the co-market's
      agreement carried signal it would CONCENTRATE gross on the kept trades; instead it
      DILUTED it → the filter selects the WORSE trades (wrong-signed selection), i.e. a
      rarity filter, not information.
    - `es_dir` (trade A in B's direction, the strongest thesis form) went net-NEGATIVE
      (Sharpe −0.56, hit-rate UP to 46% but per-trade payoff too small for the bracket
      = classic high-win/low-payoff loser).
  The equity session evidently sets a REGIME/liquidity backdrop in which A's OWN signal
  works ("when"), without B's instantaneous sign predicting A's ("which direction").
- Do NOT "just flip" a negative direction-conditioner (Rule-16 mirror trap, cost form):
  trading A in B's direction (`es_dir`) was net-negative, but its GROSS was ≈0 (+0.039
  pt) — the loss was the round-trip COST (0.145 pt), not direction. Flipping to trade A
  OPPOSITE B (`es_opp`) therefore did NOT turn positive: gross went to −0.047 while the
  same 0.145 cost stayed, so net got WORSE (Sharpe −1.03 vs −0.56). The negative of a
  cost-dominated loser is a bigger cost-dominated loser. Always read the GROSS before
  assuming a sign-flip rescues a losing conditioner; if gross≈0, B carries no directional
  content in EITHER sign and no flip helps.
- The one thing that CAN carry weak info is B's AGREEMENT as a negative QUALITY tag, not
  a direction: skipping A-trades where B agrees (`disagree` filter) lifted net Sharpe
  0.49→0.67 and — crucially — the Rule-18 re-pairing null was centered at ~0, so it is
  NOT a pure rarity filter (dropping a RANDOM 13% of trades via unrelated B-days did not
  lift Sharpe). But it was MARGINAL (z=+1.53, p≈0.073, and the MAX over ~6 post-hoc
  configs on consumed history) → a QUALIFIED screen needing a future/shadow holdout, not
  a validated edge. The re-pairing null being centered at 0 (not at the real uplift) is
  the discriminator between "real weak cross-info" and "rarity filter".
- Consequence: when an edge is confined to another market's hours, run the direction-
  conditioning test (agree-filter, trade-in-B's-direction, AND its flip) BEFORE
  concluding "cross-asset momentum". Read the gross-per-trade on the KEPT trades, not
  just the Sharpe: a Sharpe that holds only because trade count collapsed with gross
  per trade FALLING is a rarity filter selecting the worse trades; a flip that leaves
  gross≈0 is pure cost. Gate the (Rule-18) re-pairing null on a POSITIVE real uplift
  first; interpret the null's CENTER (≈0 = real info; ≈real uplift = rarity) and treat a
  post-hoc config survivor as consumed-history, holdout-pending.
- Evidence: `futures/gc/noise_vwap/artifacts/runs/EXP-0007/review.md` +
  `.../disagree_repairing_null.txt`,
  `futures/gc/noise_vwap/scripts/hyp_0005_es_conditioning.py`; contrast with EXP-0002
  (`.../artifacts/runs/EXP-0002/`).
- Origin: GC HYP-0005/EXP-0007 (condition GC direction on ES noise-VWAP state; user
  follow-up on opposite-ES + continuous stop surfaced the mirror-trap and disagree
  filter).

### 2026-07-19 — Exit-timing granularity value scales with intraday drift/noise ratio

- Status: confirmed
- Applies to: intraday breakout/momentum strategies with a periodic decision clock
  and a level-based (band/VWAP) stop; tested on the Noise-Area + VWAP family.
- Learning: tightening the stop CHECK from the entry decision clock (e.g. 30-min) to
  every bar ("continuous / every-bar stop") is NOT a universally good exit upgrade.
  It reliably shrinks the loser tail on every instrument (it cuts losers sooner), but
  it also clips winners before their intraday drift develops. The NET effect scales
  with the instrument's intraday drift-to-noise ratio, and gross per trade drops
  ~30% on ALL of them:
    - NQ (strong intraday drift): net Sharpe 1.14 -> 1.28 (+0.145), t 3.24->3.65 — GO.
    - ES (weaker drift): net Sharpe 0.93 -> 0.92 (-0.008), t 2.63->2.61 — WASH.
    - GC/gold (no positive intraday drift, noise-dominated): net Sharpe 0.46 -> -0.06
      (-0.52), gross +0.359 -> +0.127 pt/trade — INVERTS / NO-GO.
  The loser tail shrinks identically in all three (stop_frac ~0.64->0.82, loser mean
  roughly halves); only whether the winners can afford the tighter leash differs.
- Consequence: never transfer an every-bar/continuous stop across instruments on the
  strength of one market's result. Re-measure gross AND net Sharpe per instrument;
  a Sharpe gain that comes with a large gross drop is buying variance reduction, and
  whether that is net-positive depends on the market's drift. Gate a claim-matched
  Null-C on the real pass first clearing the primary metric (a wash/negative real
  pass needs no null). The looseness of a slow decision clock can be load-bearing.
- Take-profit side (added 2026-07-19, GC EXP-0006): the same drift/noise-ratio logic
  governs a partial-TP + runner exit (bank a fraction after a `tp_atr`-ATR favourable
  extension), but with a MILDER failure mode than stop-tightening. On NQ the partial-TP
  is the exit study's only Null-C survivor (reversion-after-extension, sign flips vs
  noise). Ported to GC it is BENIGN not harmful: gross is HELD/nudged up (+0.362→+0.375
  pt) and win% rises, because it BANKS the give-back instead of tightening the runner's
  stop — the opposite of the continuous stop, which inverted by clipping winners. But on
  GC the uplift is only +0.02 net Sharpe (below a +0.05 deployment gate) = REJECT. Two
  transferable sub-lessons: (1) on a no-drift/noise-dominated instrument, extension-
  BANKING exits are safe-but-weak while stop-TIGHTENING exits are actively harmful —
  distinguish the two before porting an "exit upgrade"; (2) the tp-width optimum SHIFTS
  WIDER on the noise-dominated instrument (NQ best at tp0.75; GC's tp0.75 hurts, value
  only at tp≥1.0→1.5) — gold's minute moves need more room before banking, the same
  "looseness is load-bearing" theme. Also: going LOOSER than the sweet-spot clock (GC
  60-min vs 30-min) is harmful too — the decision clock sits near a local optimum, both
  tighter (continuous) and looser (60m) are worse.
- Evidence: `futures/nq/noise_vwap/scripts/es_continuous_stop.py` (NQ+ES),
  `futures/nq/noise_vwap/reports/STUDIES.md` (NQ continuous-stop Null-C z5.20/28% + NQ
  partial-TP survivor), `futures/gc/noise_vwap/artifacts/runs/EXP-0004/review.md` (GC
  continuous stop), `futures/gc/noise_vwap/artifacts/runs/EXP-0006/review.md` (GC
  partial-TP + 60-min clock).
- Origin: NQ adopted continuous stop (`scripts/studies.py`, INST hardcoded to NQ);
  GC HYP-0003/EXP-0004 rejection prompted the ES + GC cross-check; GC HYP-0004/EXP-0006
  extended the cross-check to the take-profit side.

### 2026-07-19 — Strict `min_periods=lookback` on a same-time-of-day rolling feature is a hidden liquidity filter

- Status: confirmed
- Applies to: any same-time-of-day / same-slot rolling feature (noise bands,
  seasonal averages, time-of-day baselines) built from bar data, ported across
  instruments of different liquidity. Found on the Noise-Area + VWAP family.
- Learning: building a per-(date, slot) rolling statistic with
  `rolling(lookback, min_periods=lookback)` requires EVERY session in the trailing
  window to have a bar at that exact slot. One missing bar anywhere in the window
  nulls the feature for that (date, slot), and if the strategy skips a slot with a
  null feature, that decision is silently deleted. The deletion rate scales with
  how often that slot is empty, so it is TIME-OF-DAY-DEPENDENT and concentrated in
  the instrument's thin hours: negligible on a liquid market (every RTH minute
  present) but severe when the exact construction is ported to a thinner one. On
  GC it deleted up to 28% of the 15:29 ET decisions (2149 decision points; band
  coverage 72–97% by minute) despite ~100% raw per-minute coverage — because the
  ALL-of-N requirement compounds rare single-minute gaps. Fixing to
  `min_periods = ceil(0.9*lookback)` (average over present sessions; still causal,
  `move.shift(1)`) restored uniform ~97.8% coverage. The defect is CONSERVATIVE
  (deletes signals, no lookahead/fill artifact), so it does not inflate an edge —
  but it under-samples in a biased way and corrupts any time-of-day interpretation.
- Consequence: (1) never port a windowed feature's coverage rule across liquidity
  regimes without re-measuring per-slot coverage; prefer a fractional `min_periods`
  so one gap does not null the window. (2) Rule 9a: run an executable data-quality
  gate at every data/feature stage and REPORT per-slot coverage, missing-bar
  counts, and how often/why the feature nulls or drops rows — a silent null is a
  reportable finding. A uniform post-fix coverage across slots is the pass signal;
  a coverage that tracks time-of-day liquidity is the tell.
- Evidence: `futures/gc/noise_vwap/reports/DATA_QUALITY.md`,
  `futures/gc/noise_vwap/scripts/data_quality.py`,
  `futures/gc/noise_vwap/artifacts/runs/EXP-0005/review.md`; RULES.md rule 9a.
- Origin: `futures/gc/noise_vwap/MEMORY.md` (EXP-0005); user found no trade on
  2026-07-07 despite price below band+VWAP from 15:00. NQ port
  (`futures/nq/noise_vwap/core/data.py`) still uses strict min_periods but is
  liquid enough that it barely bites — re-check before relying on its late-day slots.

### 2026-07-19 — A 1-minute gross edge on a TP/SL bracket can be a coarse-bar fill artifact

- Status: confirmed
- Applies to: any bracket / barrier / fade strategy with intrabar stop and target
  simulated on OHLC bars (the stop-vs-target ordering inside a bar is unobservable).
  Found on the GC VWAP-band mean-reversion fade.
- Learning: with 1-minute OHLC, a bar that reaches the TARGET but whose intrabar path
  actually hit the STOP first is credited a win, because 1m high/low cannot order the
  two touches and the adverse rule (rule 3) only fires when a bar can reach BOTH
  levels — a bar whose 1m range spans the target but not the (further) stop looks like
  a clean win even though a finer path shows an earlier stop touch. Re-running the
  IDENTICAL strategy on 1-SECOND bars exposes those stop-first paths: on GC the fade's
  gross win rate fell 35.6% → 33.4% (right on the 2RR break-even of 1/3) and the gross
  edge collapsed from Sharpe +0.57 / t+2.16 to +0.08 / t+0.32 (≈0). The 1m "edge" was
  entirely coarse-bar over-crediting, not signal. Direction of the bias: 1m FLATTERS a
  bracket whose stop is nearer than its target (asymmetric brackets are the common
  case). Same-bar-target and queue-through fill assumptions were NOT load-bearing here
  (the honest killer was intrabar path resolution, not the entry model).
- Consequence: never trust a 1-minute gross number for a TP/SL bracket or fade before
  re-resolving the intrabar path at a materially finer resolution (1s here). Report the
  1m-vs-1s win rate and gross side by side; if the win rate sits at the bracket's
  algebraic break-even (1/(1+RR)), the barriers are efficient and there is no edge. An
  engine keyed on seconds-from-midnight runs both resolutions unchanged so the only
  variable is the path.
- Evidence: `futures/gc/vwap_reversion/reports/BASELINE_REPLICATION.md`,
  `futures/gc/vwap_reversion/artifacts/runs/EXP-0000/` (baseline_1s.txt shows 1m vs 1s).
- Consistency: same conclusion as the NQ VWAP σ-band NO-GO (VWAP bands are efficient).
- Origin: `futures/gc/vwap_reversion/MEMORY.md` (EXP-0000).

<!--
Suggested entry format:

### YYYY-MM-DD — Short title

- Status: confirmed
- Applies to: project types, instruments, or methods
- Learning: one concise, atomic statement
- Evidence: relative/path/to/report.md or relative/path/to/test.py
- Consequence: what future work must do differently
- Origin: relative/path/to/project/MEMORY.md
-->
