# Project Memory: VEI Exploration

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: characterise the Volatility Expansion Index (VEI = intraday
  ATR(short)/ATR(long)) as an indicator — where it carries real, causal information —
  before committing it to any strategy. Companion to `futures/nq/noise_vwap` EXP-0035,
  where VEI as a momentum-breakout entry gate was a NO-GO.
- Instruments or markets: NQ and ES futures (1-min RTH).
- Data coverage: shared clean Databento files `futures/nq/data/{NQ,ES}_1m_clean.parquet`,
  2011–2026, ~3710 sessions after degraded-day drops. No trading — measurement only.
- Current phase: descriptive exploration (like `hurst_explore`); no baseline/engine
  needed. Study D is the promotion candidate.

## Current status

- Verdict: VEI is NOT a direction predictor and (as a vol forecaster) is dominated by
  the vol level. Its best candidate role was as a **momentum REGIME SELECTOR** (Study D),
  which does NOT monetize standalone (EXP-0004: daily risk-adjusted Sharpe ≈0; positive
  high-cell gross exceeds modeled cost but is too weak/lumpy) and which **EXP-0006
  DOWNGRADED to qualified/inconclusive**: after
  repairing a per-session Wilder-ATR warm-up defect the contrast shrank to 63% (NQ) /
  83% (ES) of published and NQ's CI crossed zero at the preregistered cut. The time-of-day
  audit (EXP-0005) still holds — D is not a clock effect — but D is no longer established
  at the claimed significance. Net: **VEI's verified role is diagnostic/regime-labelling
  and (marginally) risk; there is no established directional edge, and the one descriptive
  finding that looked strongest is now qualified.** EXP-0007 then confirmed that the
  legacy seed accidentally encoded the opening bar, but **rejected that accidental
  component as predictive information**: no controlled CI, monotonic dose response,
  era stability, or both-market null survival, and one shared session is load-bearing.
  **EXP-0008 then established what VEI is FOR, by separating the two roles cleanly: at
  forecasting vol the LEVEL dominates and the ratio adds a sliver; at selecting the
  momentum regime the LEVEL contributes NOTHING (contrast ≈0, CI spans 0 on both
  markets) and only the RATIO carries anything.** So the ratio's reason to exist is
  vindicated on the momentum axis specifically — while Study D itself stays qualified.
- Last verified: 2026-07-27 (EXP-0001..0008; EXP-0006 supersedes parts of A/C/D/F;
  EXP-0007 closes the legacy-seed-as-predictor explanation; EXP-0008 retires
  `IC_fwdvol` as a selection metric and withdraws the `wilder_20_100` lead).
- Lifecycle phase: exploration / hypothesis generation.
- Holdout status: consumed research history; only future shadow is clean holdout.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction: `python -u -m futures.nq.vei_exploration.scripts.{s1_smoothing,
  s2_vol_forecast,s3_regime_dynamics,s4_term_structure} {NQ|ES}`.
- Tests: **no pytest in this environment** — run
  `python -m futures.nq.vei_exploration.tests.run_tests` (13/13 pass).
- Primary evidence: `reports/FINDINGS.md`.

## Confirmed findings (descriptive, cross-market NQ+ES)

- **A / EXP-0001 — ~~the ATR estimator dominates smoothing~~ → CORRECTED 2026-07-26:
  effective MEMORY dominates, and the shipped Wilder is mis-initialised.** The original
  observation holds (SMA(10/50) VEI is near-noise: AC1 ≈ 0, whipsaw 46%, fwd-vol IC
  +0.06; Wilder(10/50) → AC1 0.55, whipsaw 0.23, IC +0.157 NQ / +0.195 ES), but the
  *attribution* was wrong — the comparison changed estimator form and effective memory
  together (SMA(n) com = (n−1)/2, Wilder(n) com = n−1, so wilder_10_50 has ~2× the
  memory of sma_10_50). Missing controls, both directions: **SMA(19/99)** (com-matched)
  gets AC1 0.33, whipsaw 0.33, IC **+0.186 NQ / +0.188 ES** — matches-or-beats Wilder;
  **Wilder(5/25)** (com-matched down) collapses to IC **+0.001 NQ / +0.040 ES**, worse
  than the SMA. Memory alone (SMA 10/50→19/99) triples the IC on both markets. Also:
  Wilder α=1/n *is* `ewm(span=2n−1)`, so wilder_10_50 ≡ ema_19_99 as a recursion. And
  `ewm(adjust=False, min_periods=n)` in `core/vei.py::_roll` seeds at bar 0 rather than a
  textbook n-bar SMA, and `min_periods=n` on an α=1/n recursion admits 17% of decisions
  whose long ATR is seed-dominated: masking those (ema 19/99) lifts IC to +0.242/+0.249,
  a textbook seed to +0.202/+0.207 — the shipped variant is worse than **both** repairs,
  and the ATR resets per session so this recurs ~3710×. Ratio-smoothing spans 3/5/10 at
  1-min were also under-powered vs a 30-min clock (decayed by the next decision); a
  decision-clock (30–120m) smoother is untested. → Studies B–F all used the weaker
  implementation. Not invalidating (each is internally consistent + cross-market), but
  fix warm-up and re-select at matched memory before any re-run.
  Evidence: `scripts/s1b_estimator_controls.py` →
  `artifacts/runs/A_smoothing/estimator_controls_{NQ,ES}.txt`, `reports/FINDINGS.md`
  §A-corrected. NOTE unchanged: noise_vwap EXP-0035 used the jumpiest SMA variant.
- **A-corrected (b) — VEI=1 is a TIME-OF-DAY line, not a calm line.** Mean VEI 0.893 NQ
  / 0.924 ES; the mis-init explains only ~0.024 of it (SMA VEI has no seed and is also
  <1 at 0.973/0.986). The real cause is the session-reset ATR anchoring the long window
  on the high-vol open: mean VEI by slot runs 0.745→1.165 (NQ) / 0.788→1.216 (ES)
  monotonically through the day. So the stated reading ("≈1 calm, <1 contraction, >1
  expansion") does not hold for this implementation, A's whipsaw metric (crossings of
  1.0) is partly a time-of-day artefact, and `VEI>1.10` in D/E is largely a "late
  session" selector — which is exactly what EXP-0005 measured. **Does not overturn
  Study D** (EXP-0005's within-slot audit retained 106%/105% of pooled), and do NOT
  de-seasonalise (EXP-0005 showed that destroys the information).
- **B / EXP-0002 — VEI adds little to vol forecasting.** The vol LEVEL forecasts
  forward realized vol strongly (rank IC +0.86, R² 0.60); adding log(VEI) raises R² only
  +0.004 (NQ)/+0.002 (ES). **EXP-0006 (repaired): the increment is even smaller,
  +0.0017 NQ / +0.0006 ES** — verdict unchanged, slightly strengthened. For sizing/risk
  use the vol level; the ratio adds a sliver.
- **C / EXP-0002 — no intraday coiled spring.** Verdict holds; one sub-claim withdrawn by
  EXP-0006. Legacy: expansion ratio LOWEST at low VEI (~0.90), rising with VEI. Repaired:
  the expansion ratio is **flat/non-monotone at ~0.94–0.99 across every VEI quintile**
  (i.e. essentially independent of VEI — vol decays intraday regardless of regime); the
  forward vol LEVEL still rises monotonically with VEI (persistence). Either way there is
  no spring intraday. The squeeze→breakout idea, if real, is a daily/multi-day timescale
  (backlog item 4). Corrects the stated "VEI<1 = spring" intuition at the intraday horizon.
- **D / EXP-0003 — VEI as a momentum regime selector → DOWNGRADED to QUALIFIED /
  INCONCLUSIVE by EXP-0006.** Legacy (through the warm-up defect): corr(trailing 30m,
  next 30m) ~0 in low & calm, **+0.104 NQ [+0.023,+0.186] / +0.096 ES [+0.016,+0.171]**
  at VEI>1.10. Repaired: **+0.067 NQ [−0.010,+0.142] (CI includes 0) / +0.075 ES
  [+0.003,+0.144]**. Preregistered kill test 1 fired on NQ. Direction and cross-market
  agreement survive; size and significance do not. Also threshold-sensitive (NQ is
  significant at a selection-rate-matched cut, +0.087 [+0.009,+0.144], but not at the
  fixed 1.10 line — consistent with A-corrected(b): 1.10 is not a calibrated level).
  Still no significant 30m mean-reversion in any regime. Read as a real but weak,
  small-sample tilt that EXP-0004 already showed does not monetize — not the "vol plays a
  role in every strategy" payoff it was written up as. Not contradicted by EXP-0035
  (that measured continuation of ALREADY-extended breakouts; D is the unconditional tape).

- **E / EXP-0004 (HYP-0001) — momentum-in-high-VEI: mechanism CONFIRMED, edge
  REJECTED.** Preregistered promotion of Study D. Causal momentum (side=sign(trailing
  30m ret), next-open fill, 30m hold, flat at close, non-overlapping, conservative
  per-interval cost). Gross dose-response is clean, correct-signed, cross-market:
  `high>1.10` gross +0.96 pt/t (NQ) / +0.375 (ES); `low<=1.10` ≈0/neg; `all` in between
  → momentum's positive gross expectancy lives in the high-VEI regime (Study D confirmed
  at the strategy level). But NOT deployable: the preregistered `high>1.10, H=30` cell
  has daily Sharpe +0.015 (NQ, t=0.06) / −0.073 (ES) — per-trade tilt sub-cost and
  daily-lumpy. Kill-test 1 failed → matched-count random null and Null C not spent
  (standing rule). Sensitivity: net/t monotone in T and horizon (H=60 t≈1.7 NQ/1.4 ES,
  still <2, post-hoc); 2023+ positive (forward-watch only). The recurring project
  pattern: a real cross-market per-trade signal that does not monetize. Engine
  `core/strategy.py` (+ causality tests), Null C adapter `core/nulls.py` reusing the
  audited `noise_vwap.null_c_returns`.

- **F / EXP-0005 (HYP-0002) — Study D is NOT a time-of-day artefact; the horizon reading
  in E was wrong.** VEI drifts up all day (session-reset ATR anchored to the open), so
  `VEI>1.10` fires on ~1% of morning but 19–64% of late decisions and **88.9% NQ / 87.4%
  ES of high-VEI decisions sit after 14:00** (31% of the clock). Correlating *within*
  each slot then count-weighting: contrast **+0.1098 [+0.0251,+0.1715] NQ / +0.1033
  [+0.0208,+0.1681] ES = 106%/105% of pooled** → Study D stands *as a non-clock effect*.
  Robust to the thin-cell threshold; still +0.073/+0.068 using only the 4 largest late
  slots. **EXP-0006: the AUDIT holds and strengthens (within-slot retains 111%/117% of
  pooled) — D is definitively NOT a clock effect — but the audited contrast itself shrank
  to +0.069 NQ [CI includes 0] / +0.086 ES, which is what triggered D's downgrade.**
  Three corollaries: (a) ~~**de-seasonalising DESTROYS information**~~ → **REVERSED by
  EXP-0006. Do not cite this.** Legacy said the causal same-slot percentile was weaker
  than the raw level (NQ +0.069 vs +0.100; ES +0.068 vs +0.086); repaired it is
  equal-or-BETTER (NQ raw +0.068 [CI incl. 0] vs pct **+0.080 [+0.009,+0.148]**; ES
  +0.064 vs +0.071) — the legacy warm-up bias was itself time-of-day dependent (worst
  early, where the long ATR is least populated) and artificially favoured the raw level;
  (b) the momentum info is **front-loaded** — peaks at H=5–10
  (+0.177 NQ/+0.170 ES), holds to 30–60, ≈0 by 90–120/close, which **corrects E's "the
  effect strengthens with hold"** (the H=60 gain is cost amortisation, not signal — that
  axis is closed); (c) **VR(q) shows no within-slot regime difference**, so "momentum
  regime" = a drift tilt, not a smoother path (the pooled VR gap was pure composition).
  Also: a real VEI-INDEPENDENT momentum effect at the **13:30 slot** on both markets
  (+0.101/+0.108 vs ≈0 elsewhere). F4: (10,50) + past_win=30 is the best cell on both
  markets; past_win is load-bearing.
- **Erratum (rule 13), same run.** EXP-0004's published H=60 cell was a **2-unit book**
  (60-min hold on a 30-min clock) against a declared non-overlapping single-position
  estimand. Corrected 1-unit: NQ Sh +0.442 (t1.70) / ES +0.526 (t2.02); 60-min clock
  +0.288/+0.249. `core/strategy.py::simulate` now enforces non-overlap by default
  (`allow_overlap=True` opts in), guarded by `test_no_overlap_is_the_default`.
  **EXP-0004's verdict is unchanged** — the preregistered H=30 cell is untouched. Note
  `simulate` works in bar-index space, so on sessions with missing minutes a nominal
  30-min hold can genuinely overlap the next decision (this removed 2 NQ bets).
- **G / EXP-0007 (HYP-0004) — legacy seed is mechanically an opening-anchor feature,
  but carries NO robust incremental prediction.** Within-slot
  corr(`legacy_vei-repaired_vei`, quiet first bar relative to first 50m) is +0.551 NQ /
  +0.532 ES: the bug really does encode the opening transition. Predictive hypothesis
  REJECTED: controlled past×quiet coefficient +0.0171 NQ CI[−0.0304,+0.0210] / +0.0121
  ES CI[−0.0272,+0.0164]; re-pairing p=.045/.137 fails both-market gate; quietest-minus-
  loudest quintile spread +0.016/−0.022 is non-monotone/wrong-signed ES; eras alternate.
  The same zero-range opening on 2020-03-16 is maximum influence in both: leave-one-out
  flips to −0.0153/−0.0071, and dropping zero opens gives −0.0128/−0.0059. The 92.1%-
  overlapping common high set retains +0.087/+0.086, while the spectacular legacy-only
  fringe is only 23/40 consumed observations. Do not restore the bug or promote
  `quiet_open`. Evidence: `artifacts/runs/EXP-0007/review.md`.
- **H / EXP-0008 (HYP-0005) — `IC_fwdvol` measures LEVEL-LIKENESS, not ratio quality; and
  the LEVEL alone does NOT select momentum.** Ten variants on one common sample
  (n=33,389, so estimator is never confounded with time of day). Across variants
  `IC_fwdvol` = 0.89·corr_lvl + 0.01, **R² 0.992 on BOTH markets**; the decisive control
  `LEVEL: atr_10` (no denominator, zero ratio content) **tops that column** (+0.575 /
  +0.613 vs best ratio +0.396 / +0.353). Mechanism is algebraic: as the denominator's
  memory grows ATR(long) → a within-session constant, so the ratio degenerates into a
  rescaled ATR(short) = the level, which §B already showed beats every VEI variant at
  forecasting vol (+0.86). Worse, it is **anti-selective**: contrast-vs-corr_lvl r −0.915
  / −0.871, so it ranks variants opposite to the primary metric, and `wilder_20_100` is
  the worst ratio on contrast. `IC_partial` (new `analysis.partial_spearman`) is only a
  partial repair — pure-level controls still top it, because a differently-windowed level
  carries fwd-vol info `past_rv` lacks. **No forward-vol metric can select a ratio.**
  BONUS (the control's best output): pure LEVEL contrast ≈0 (−0.005 NQ / +0.023 ES, CIs
  span 0) vs every ratio +0.06..+0.12 → **high volatility alone does not select the
  momentum regime, the EXPANSION RATIO does** — first separation of VEI from the level on
  the momentum axis, and it sharpens D (D is NOT "momentum works when vol is high").
  Does NOT revive D; the contrast column is a 10-variant search on consumed history and
  the argmax `wilder_20_50` is NOT promoted — only the SLOPE is established.
  Evidence: `artifacts/runs/EXP-0008/review.md`, FINDINGS §H.

## Provisional hypotheses

- None promoted. The accidental-opening-feature lead is CLOSED by EXP-0007. The H=60
  lead is also CLOSED (F1 shows it was cost amortisation, not
  signal). Remaining leads (backlog): daily-timescale squeeze (item 4, now the biggest
  untouched dimension — full 24h data already present, needs only a loader), regime-
  persistence exit (item 10), expansion onset vs late-chase + volume participation
  (item 11), the unexplained 13:30 slot (item 12), and VEI as a gate on an existing
  momentum book rather than standalone (items 3/7).

## Decisions and constraints

- Canonical VEI = Wilder(10/50) **with the repaired warm-up** (`core/vei.py`
  `seed='sma'`, the default). `seed='first'` reproduces EXP-0001..0005 exactly and exists
  only for that. The (10,50) CHOICE is still **not validated-optimal** — it was originally
  selected on a memory-confounded comparison. **EXP-0008 withdrew the `wilder_20_100`
  lead**: its Study-A advantage was `IC_fwdvol` rewarding level-likeness, and on the
  project's primary metric it is the WORST ratio tested (contrast +0.059 NQ / +0.045 ES
  vs canonical +0.075 / +0.089). `IC_fwdvol` is **retired** as a selection metric — never
  select a ratio on a metric its own numerator maximises. Canonical (10,50) is retained
  by default rather than proven optimal; if the estimator is revisited, EXP-0008 says
  vary the SHORT leg (`wilder_5_25`/`5_50` are the least level-contaminated), not the
  long one, and score it on the momentum contrast at a matched selection rate — but note
  that column is a consumed-history search, so any change needs its own preregistered
  test.
- Descriptive only so far; no promotion to alpha without a preregistered kill test and
  claim-matched null (RULES 17/24/26).
- Prior: noise_vwap momentum is volatility-INDEPENDENT and every vol-selectivity screen
  there was a turnover lever; a VEI edge must monetize at the Sharpe/portfolio level.

## Known risks and open questions

- Study D is a screen on consumed history (EXP-0004 already showed it does not monetize
  standalone). The time-of-day confound is now RESOLVED (EXP-0005), but consumed-history
  status is unchanged — only a future shadow is clean holdout.
- Coverage: only the 09:59 decision slot drops (intraday long-ATR not yet populated).
  Confirmed uniform elsewhere by EXP-0005's rule-9a table; the 15:59 slot has a defined
  VEI but no forward window, so it is absent from every forward-looking statistic.
- Open: why is the 13:30 decision slot special on BOTH markets, independent of VEI?
- Open: the H=15 dip in the term structure reproduces on both markets and is unexplained.
- The first RTH bar has zero range on 2020-03-16 in both NQ and ES clean files. EXP-0007
  reports it explicitly; it must not be allowed to create an infinite log feature or
  count as independent cross-market confirmation.

## Next actions

0. **DONE (EXP-0006).** Warm-up repaired (`core/vei.py`, `seed='sma'` default, closed-form
   + pinned to a reference loop); A/B/C/D/E/F re-run on both markets. Outcome: Study D
   downgraded, C's slope sub-claim withdrawn, F's de-seasonalisation corollary reversed,
   B and E unchanged. Remaining from that item: the **decision-clock (30–120m) ratio
   smoother** is still untested.
0b. **DONE (EXP-0008), closed by REPLACEMENT.** The suspicion was confirmed decisively and
   identically on both markets: `IC_fwdvol` is a near-perfect linear function of how
   level-like a variant is (R² **0.992**, slope ≈0.90, intercept ≈0), and a control with
   NO denominator wins the column outright (+0.575 NQ / +0.613 ES vs best ratio +0.396 /
   +0.353). It is also **anti-selective** — it ranks variants OPPOSITE to the primary
   metric (contrast-vs-corr_lvl r −0.915 / −0.871). Metric retired, `wilder_20_100`
   withdrawn, canonical retained. Bonus result from the control: the pure vol LEVEL has
   momentum contrast ≈0 → **high vol alone does not select momentum, the ratio does**
   (FINDINGS §H). Note `10_100`'s F4 win was measured on this same discredited axis.
0c. **Repair `futures/nq/noise_vwap/core/vei.py:58`**, which has the identical
   `ewm(alpha=1/n, min_periods=n, adjust=False)` defect — EXP-0036's Wilder revisit ran the
   mis-initialised feature and should not be cited until re-run.
0d. **Commit this project to git** and stop re-running into study artifact directories —
   EXP-0006 overwrote the EXP-0001..0005 outputs irrecoverably (see its review.md).
0e. **DONE (EXP-0007):** test whether the legacy seed's accidental opening anchor was
   useful prediction. Mechanical channel confirmed; prediction rejected and path closed.
1. Backlog item 4 (daily/multi-day VEI + squeeze) — the largest untouched dimension, and
   a day-level regime label suits gating an existing book better than an intraday tilt.
2. Backlog item 11 (expansion onset vs late-chase + volume participation) — the "what
   kind of expansion" split, motivated by F3c showing rare expansions carry the most.
3. Do NOT re-run backlog item 5 (done in F) and do not pursue longer holds past ~60 min.

## Promotion candidates

- The Wilder-estimator lesson and "vol-expansion ratio is a momentum regime switch, not
  a vol forecaster" may become cross-project learnings after confirming in another
  project; project-specific for now.
