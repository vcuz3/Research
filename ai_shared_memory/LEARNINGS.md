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
