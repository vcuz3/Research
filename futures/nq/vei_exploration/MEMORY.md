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
  2011–2026, ~3710 sessions after degraded-day drops. Primarily measurement, with
  preregistered causal strategy promotions for surviving mechanisms.
- Current phase: exploration / hypothesis testing; no established alpha.

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
  **EXP-0009 then repaired the last known defect of the construct — the threshold.**
  `VEI>1.10` was a TIME-OF-DAY selector (1.5% of the 10:30 slot vs 18.4% of 15:30 on NQ);
  normalising against the trailing same-slot distribution removes that at NO information
  cost, and the canonical regime label is now the **trailing same-slot z-score**.
  **EXP-0010 then separated fresh from mature expansion:** volume-confirmed first
  crossings have better pooled momentum alignment than unconfirmed crossings on NQ/ES,
  while mature observations are weak. But the frozen H=10 strategy fails on daily risk
  and the result is era-dependent (negative 2011–19, positive 2020+). Treat onset/volume
  as a possible veto or allocator, not standalone alpha. **EXP-0011 confirmed that
  multi-horizon volatility state adds a small, stable amount of forward-30m volatility
  information beyond a causal same-slot median plus `range_rv_15m` core.** The OOS gain
  is real but marginal (about +0.009 normalized IC and 0.18 bp lower raw MAE), so the
  six extra state variables are not adopted; the two-input range core is the operational
  specification and multi-horizon remains a shadow benchmark. **EXP-0012 then rejected
  the clock-composition objection decisively:** the core's within-slot IC is 0.878 NQ /
  0.871 ES versus 0.418/0.383 for the median, FWL residual log-vol R² is 0.733 on both,
  and log-MSE error falls about 74% versus the median. The range core is therefore a
  genuine conditional volatility forecast, not merely a calibration instrument. This
  still establishes no directional alpha or economic use case.
  **EXP-0013 then supplied the economic use case test, and it is a REJECT that resolves
  the project's central question.** On the frozen noise_vwap book the per-trade
  standardised edge (`net points / forecast points`) is FLAT in the causal same-slot
  forecast percentile: −0.005 [−0.145,+0.135] NQ and +0.048 [−0.082,+0.184] ES, CIs
  spanning zero with opposite signs. Expectancy is PROPORTIONAL to forecast volatility,
  so sizing at `1/forecast` is the complete and optimal use of the forecast and no tilt
  remains. **Net project position: a forecast can be genuinely skilful (EXP-0012) and
  still have no economic application to the strategy you own (EXP-0013).** Volatility
  sets *where* an edge lives; it does not tell you how to size or gate it.
  **EXP-0014 and EXP-0015 then finished the arc.** EXP-0014: the recipe transfers to
  DOWNSIDE semivariance at 92-93% of its total-RV skill (so the leg a stop calculation
  needs is free), but the up/down SPLIT is a constant near one half plus noise and is not
  forecastable at all - the symmetric level is a sufficient statistic for the FORECAST
  just as it is for the noise BAND. EXP-0015: measured against PERSISTENCE (trailing
  30-minute RV) rather than the same-slot median, the core's advantage in ranking LEVELS
  is only **+0.013** within-slot, not EXP-0012's +0.47 - persistence alone beats
  seasonality by log-MSE skill +0.69/+0.71 - but its call on the CHANGE is real
  (+0.377/+0.390), survives the preregistered expansion-only gate (+0.220/+0.238), and
  strengthens monotonically with the size of the disagreement.
- Last verified: 2026-07-31 (EXP-0001..0015; EXP-0006 supersedes parts of A/C/D/F;
  EXP-0007 closes the legacy-seed-as-predictor explanation; EXP-0008 retires
  `IC_fwdvol`; EXP-0009 calibrates the regime label; EXP-0010 closes standalone onset;
  EXP-0011 confirms but does not operationally adopt multi-horizon volatility state;
  EXP-0012 confirms the range core's information is conditional, not a clock effect;
  EXP-0013 closes the volatility-sizing channel and the overlay programme; EXP-0014
  closes the downside-asymmetry channel; EXP-0015 qualifies EXP-0012's benchmark and
  establishes the core as a genuine but smaller timing instrument).
- Lifecycle phase: exploration / hypothesis generation.
- Holdout status: consumed research history. EXP-0011 additionally consumed
  2024-01-01 through 2026-07-14 for the forward-volatility specification; only data
  after 2026-07-14 is clean future shadow evidence. EXP-0012's annual walk-forward
  2016-2026 conditional diagnostic is also consumed, not a new independent holdout.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction: `python -u -m futures.nq.vei_exploration.scripts.{s1_smoothing,
  s2_vol_forecast,s3_regime_dynamics,s4_term_structure} {NQ|ES}`; forecast-vs-book
  conditioning via `... .scripts.{hyp_0010_vol_scaling,hyp_0011_semivariance,
  hyp_0012_disagreement} {NQ|ES}`.
- **The canonical forward-vol forecast is now importable, tested code:**
  `core/forward_vol.py` (`build_decision_frame`, `walkforward_forecast`). It reproduces
  the EXP-0011 notebook to |ΔIC| <= 1.7e-04 at exact row counts (tolerance 5e-4, asserted
  at the top of every run that uses it), and its sealed-read invariant is bit-identical.
  Use this rather than re-executing or mutating the notebook, which stays the immutable
  EXP-0011 record.
- Tests: run `python -m futures.nq.vei_exploration.tests.run_tests` (29/29 pass).
  (Correction 2026-07-27: pytest 9.1.1 IS installed — the older "no pytest in this
  environment" claim was wrong. The runner is still the right path because the workspace
  uses implicit namespace packages, so pytest cannot collect these modules by file path.)
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
  Study D** (EXP-0005's within-slot audit retained 106%/105% of pooled). ~~Do NOT
  de-seasonalise~~ — **that instruction is DEAD**: reversed by EXP-0006 (warm-up artefact)
  and then settled by EXP-0009, which showed a magnitude-preserving same-slot
  normalisation retains 88–93% of the contrast and fixes the calibration. **The fix for
  this defect is finding I / EXP-0009: use the trailing same-slot z-score.**
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

- **I / EXP-0009 (HYP-0006) — the VEI THRESHOLD was a clock; the trailing same-slot
  z-score fixes it at NO information cost.** User's proposal: apply the noise-area
  construction (same-time-of-day statistic over a trailing session lookback) to VEI
  itself. Four features at matched selection rate, one common sample. **(a)** Defect
  sized: at `VEI>1.10` the raw feature selects **1.5% of the 10:30 slot vs 18.4% of
  15:30** (NQ; ES 2.6%→22.4%); per-slot rate spread 0.169/0.198, CV 0.93/0.88. **(b)**
  `rel`=VEI/mu_slot only HALF-fixes it (spread 0.029/0.031) because dividing by the mean
  removes per-slot LOCATION but not SCALE → **VEI's per-slot dispersion is not
  proportional to its per-slot level**; `z`=(VEI−mu)/sd is 2.5× better (0.0115/0.0121),
  ≈`pct`. **(c) Kill test 1 did NOT fire** — `rel` retains 88.1% NQ / 92.5% ES of raw's
  within-slot contrast (gate 75%), so **de-seasonalising does NOT destroy information**;
  together with EXP-0006 this SETTLES the EXP-0005 claim as a warm-up-bug artefact, now
  with a second magnitude-preserving confirmation. **(d)** `z` is the ONLY feature of four
  whose CI excludes 0 on both markets in BOTH metrics (4/4 cells; raw 0/4): within-slot
  +0.0959 [+0.0187,+0.1544] NQ / +0.0784 [+0.0052,+0.1377] ES; pooled +0.0930 / +0.0869.
  BUT the mechanism differs by market — NQ's point estimate rises +28% at unchanged CI
  width, ES's is FLAT with a slightly narrower interval ⇒ **a better-conditioned
  measurement, not a bigger effect**; the significance pattern transfers, the gain size
  does not. **DECISION: adopt `z` as the regime label**, `rel` retained as the
  interpretable sibling ("1.0 = normal for this time of day"). Measurement improvement,
  NOT edge evidence. **(e)** Sensitivity lb{30,90,180}: no cliff, 180 worst on both; 90
  inherited not selected. Rule 9a: trailing window costs 60/3710 sessions UNIFORMLY across
  all 11 slots (0.9838 everywhere) = pass signal. CIs wide/overlapping/400-draw; two ES
  calls sit near a CI edge, so the PATTERN is the claim, not any pairwise gap.
  **(f) Does NOT revive Study D** — see the risks section. Evidence:
  `artifacts/runs/EXP-0009/review.md`, FINDINGS §I.

- **J / EXP-0010 (HYP-0007) — onset + volume is descriptively useful; standalone alpha
  REJECTED.** First five-minute crossing of canonical same-slot `z>=1.5`; volume confirms
  when trailing five-minute volume is above its same-slot norm and strengthens from the
  prior block. H=10 aligned return confirmed vs unconfirmed: **+0.639 vs -1.317 bp NQ**,
  **+0.781 vs -0.958 bp ES**; differences +1.956 [+0.592,+3.149] / +1.740
  [+0.752,+2.694]. First mature-high confirmed observations are net negative on both,
  so onset vs late is a real descriptive distinction. But primary H=10 daily Sharpe/t
  is only +0.050/+0.19 NQ and -0.199/-0.76 ES; kill test fires, nulls unspent. Declared
  H=30 reaches +0.527/t2.02 NQ but only +0.364/t1.40 ES and cannot replace primary.
  Important instability: strategy negative 2011–19 and positive 2020+ on BOTH markets;
  NQ/ES are highly dependent (84% onset-date overlap; same-event return corr 0.90).
  Recent positive cells are forward-watch only. Evidence: `artifacts/runs/EXP-0010/`,
  FINDINGS §J.

- **K / EXP-0011 (HYP-0008) — multi-horizon volatility adds real but operationally
  marginal forward-30m forecast information.** Against the frozen range core (causal
  trailing 90-session same-slot target median + `range_rv_15m`), Part-B OOS normalized
  IC improved by **+0.0088 NQ** (90% CI [0.0055, 0.0124]) and **+0.0095 ES**
  ([0.0064, 0.0133]); all OOS yearly deltas were positive and normalized MAE/QLIKE both
  improved. Raw-target IC improved +0.0100/+0.0113 and raw MAE by 0.176/0.189 bp.
  Thus the incremental hypothesis is confirmed. **Operational decision: do not adopt**
  the six extra multi-horizon state variables for this marginal gain. Use the simpler
  range core in production and retain the candidate only as a shadow benchmark. The
  2024-01-01 through 2026-07-14 OOS interval is now consumed. Evidence:
  `artifacts/runs/EXP-0011/review.md`,
  `notebooks/range_multihorizon_vol_confirmation.ipynb`.

- **L / EXP-0012 (HYP-0009) — the two-feature range core is a genuine CONDITIONAL
  forward-volatility forecast, not a clock-composition artefact.** Annual expanding-
  window OOS predictions over 2016 through 2026-07-14: pooled raw IC 0.8875 NQ / 0.8761
  ES versus 0.4828/0.4271 for the causal same-slot median. More importantly, within-slot
  model IC is **0.8782/0.8711** versus median **0.4181/0.3825**, delta **+0.4601**
  (90% session-block CI [0.4365,0.4833]) / **+0.4886** ([0.4625,0.5158]). Same-slot ×
  weekday deltas are nearly identical. After residualising log actual and forecast vol
  on log median, residual corr is 0.856/0.856 and R² **0.733/0.733**. Log-MSE skill is
  **+73.6%/+74.2%** versus the median; raw MAE falls 9.01→4.78 NQ and 7.47→3.93 ES vol
  bp. Every year and all 11 slots are positive. Thus the only non-baseline feature,
  `range_rv_15m`, carries powerful current-state information (including nonlinear
  interaction with the median). This is forecast skill, NOT directional alpha or an
  economic strategy. History through 2026-07-14 is consumed; independent review is
  pending. Evidence: `artifacts/runs/EXP-0012/review.md`,
  `reports/CONDITIONAL_FORWARD_VOL_HANDOFF.md`,
  `notebooks/conditional_forward_vol_signal.py`.

- **M / EXP-0013 (HYP-0010) — the forecast is a risk SCALE for a real book, not a tilt;
  the intraday volatility-SIZING channel is CLOSED.** The cheapest possible economic test:
  no new strategy, one regression on trades that already exist. Every trade of the frozen
  `futures/nq/noise_vwap` book was tagged with the canonical forecast at its own decision
  slot, and the standardised edge `net_points / forecast_points` regressed on the CAUSAL
  trailing same-slot percentile of the forecast. **Preregistered kill test fired on both
  markets:** slope **-0.0047 [-0.1451,+0.1345] NQ** and **+0.0483 [-0.0822,+0.1838] ES**
  on the adopted `continuous_stop` config, CIs spanning zero with opposite signs;
  top-minus-bottom quintile +0.0062 / +0.0312 likewise; the `baseline` config agrees.
  The quintile table shows why, mechanically: q1 to q5 the forecast rises 18.3 to 41.2 pt,
  the mean winner 34.8 to 83.9, the mean loser -8.4 to -22.1 and the median -2.35 to
  -7.10, while `std_edge` stays trendless. **Expectancy is PROPORTIONAL to forecast
  volatility, so `1/forecast` sizing is complete and optimal and no tilt remains.** Two
  by-products worth more than the primary: (1) **the book already self-selects into
  high forecast-vol slots** (34.8% NQ / 37.3% ES of trades in the top quintile vs 20%
  uniform) because a same-slot noise-band breakout rule IS a volatility filter — the
  mechanical reason volatility overlays keep adding nothing to this family; (2) **a rank
  IC of a conditioning variable against per-trade P&L is misleading here** (-0.357 /
  -0.316, large and negative) because on a 74-75%-loser skewed P&L it tracks the MEDIAN
  trade, not expectancy. Denominator follow-on does NOT transfer: vol-normalised sizing
  beats unsized on NQ only, and the forecast is not distinguishable from the deployed
  trailing ATR14 on either market's primary config, so **do not switch the sizing
  denominator**. Sub-cells (hold<=30m negative, short-only positive) point opposite ways
  across 6x2x2 slices = a sliced null, not promoted. Evidence:
  `artifacts/runs/EXP-0013/review.md`, FINDINGS section M.

- **N / EXP-0014 (HYP-0011) - downside volatility is total volatility times ONE HALF;
  the recipe transfers, the SPLIT does not.** Two preregistered claims, both settled on
  both markets. **Claim A CONFIRMED:** the frozen recipe applied unchanged to
  `fwd_dsv_bp` gives a within-slot IC delta over its own same-slot median of **+0.4267
  [+0.4054,+0.4499] NQ / +0.4560 [+0.4337,+0.4791] ES = 92.3%/92.8% retention** of the
  total-RV reference (gate 75%), log-MSE skill +0.626/+0.648, MAE 6.85->4.25 bp NQ and
  5.55->3.36 bp ES, positive in all eleven tested years. The downside leg is the hardest
  of the three (expected: down-minutes are the sparser, jump-driven half) but only just.
  **Claim B REJECTED:** all four `fwd_down_share` cells span zero and the markets
  disagree on which candidate is better. **The degenerate control is the decisive
  evidence, not the CIs** - the realised down-share is mean 0.4950/0.4942, sd
  0.166/0.158, per-slot means spanning only 0.486-0.500, and subtracting its causal
  trailing same-slot median **INCREASES** the variance (removes -2.1%/-2.0%): a trailing
  statistic fitted to constant-plus-noise is worse than no statistic. The drift control
  (noise_vwap EXP-0022's trap) found no drift channel either. Identity
  rv^2==dsv^2+usv^2 verified in-run to 2.9e-11. Evidence:
  `artifacts/runs/EXP-0014/review.md`, FINDINGS section N.

- **O / EXP-0015 (HYP-0012) - PERSISTENCE is a far harder benchmark than seasonality;
  the core is a genuine but SMALLER timing instrument.** Benchmark `P` = trailing
  30-minute RV built as the strict backward twin of the target (tested:
  `past_rv30_bp[p] == fwd_rv_bp[p-31]`). **The reframing that qualifies EXP-0012:**
  within-slot IC vs realised RV is model +0.8808/+0.8740, persistence +0.8674/+0.8610,
  seasonality +0.4186/+0.3830 - so EXP-0012's ~+0.47 delta over the same-slot median is
  **+0.013** over persistence. Persistence alone scores log-MSE skill +0.686/+0.710 over
  seasonality; the model's skill over persistence is +0.187/+0.148. **The levels are
  nearly all persistence; the deltas are where the model lives - quote both numbers or
  neither.** **PRIMARY PASS both markets:** within-slot IC(predicted log-change, realised
  log-change) **+0.3766 [+0.3690,+0.3841] NQ / +0.3901 [+0.3819,+0.3984] ES**, and the
  preregistered EXPANSION-only gate (declared in advance because contraction calls after
  a spike are nearly free) clears at **+0.2201/+0.2380**; marginal value over the same
  call made by seasonality alone is +0.1363/+0.1383. Stable across all 11 years
  (0.350-0.436) and all 11 slots. **Skill rises MONOTONICALLY with disagreement size**
  (decile 1->10: IC +0.033->+0.643, skill vs P +0.001->+0.426) - most right exactly where
  it would be used, the opposite of overconfidence. **Honest caveat:** on expansion calls
  the RANKING works but log-MSE skill over persistence is only +0.008 NQ / +0.061 ES vs
  +0.300/+0.211 on contractions - the direction-of-change call transfers, the magnitude
  call largely does not. Evidence: `artifacts/runs/EXP-0015/review.md`, FINDINGS section O.

## Provisional hypotheses

- None promoted. The opening-seed lead is CLOSED by EXP-0007, H=60 by Study F, the
  standalone onset+volume lead by EXP-0010, and **the volatility sizing/allocator lead
  (old backlog item 7) by EXP-0013**. Remaining: daily-timescale squeeze (item 4),
  regime-persistence exit (item 10), the unexplained 13:30 slot (item 12), and the four
  scheduled-calendar residual (item 13, now a TARGETED step — EXP-0015 identifies the
  exact weak cell it must improve) and a decision-shaped barrier-probability target
  (item 15). Items 14 and 16 are DONE and closed by EXP-0014 / EXP-0015. The 2020+ onset improvement is
  forward-watch, not a hypothesis pass.

## Decisions and constraints

- **Canonical forward-30m volatility specification = causal trailing 90-session
  same-slot target median + `range_rv_15m`** (EXP-0011). The median supplies the normal
  volatility level for that exact decision slot using only earlier sessions; the range
  feature supplies the latest local volatility state. EXP-0012 confirms the range input
  materially improves both conditional ordering and numerical accuracy after removing
  the median; it is not merely reconstructing the intraday curve. Multi-horizon state is
  a shadow benchmark, not a production dependency. Do not tune features, lookbacks,
  slots, or model parameters on data through 2026-07-14.

- **Canonical REGIME LABEL = the trailing same-slot z-score of VEI** (EXP-0009):
  `mu, sd = analysis.causal_slot_stats(d, "vei", lookback=90, min_obs=60)`, then
  `z = (vei - mu) / sd`. Use `rel = vei / mu` when an interpretable reading is wanted
  ("1.0 = normal for this time of day"), accepting ~2.5× worse calibration because it
  corrects location but not scale. **Never threshold the raw ratio** — a fixed cut on it
  is a time-of-day selector (1.5% of the 10:30 slot vs 18.4% of 15:30). The `1.10` line
  in D/E is a legacy artefact retained only for reproduction.
- Canonical VEI *feature* = Wilder(10/50) **with the repaired warm-up** (`core/vei.py`
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

- EXP-0011 establishes forecast accuracy, not economic value. The OOS comparison is now
  consumed through 2026-07-14; only later data can independently revisit the production
  choice. NQ/ES agreement is not fully independent because the markets are correlated.
  **EXP-0013 has now supplied the missing economic-value test for one concrete book and
  the answer was a REJECT**, so "accuracy, not value" is no longer an open caveat on that
  path — it is a settled result.
- **EXP-0011's multi-horizon INCREMENT carries an unresolved objection** (this project's
  review, 2026-07-31): its Part-A shuffled-target placebo did NOT centre at zero — null
  mean +0.0101 NQ / +0.0042 ES against an observed Part-A delta of +0.0192 / +0.0160 —
  and the placebo was never rerun on Part B, where NQ's confirmed delta of +0.0088 sits
  INSIDE that Part-A null band [+0.0075,+0.0127]. Read the increment as
  "qualified-confirmed pending the OOS placebo" (backlog item 18). This does not touch the
  adopted two-input core, which never depended on the increment, nor EXP-0012, which
  compared the core against the same-slot median rather than against a richer model.
- EXP-0011's evidence base is an UNTRACKED, mutable notebook; the only anchor is the
  recorded sha256 (`ccb9f5e9..79606`, still matching on disk). `core/forward_vol.py`
  removes the dependency for future work, but the original run has no version history and
  its admin registration is retrospective (declared and closed two minutes apart).
- The `core/forward_vol.py` reproduction leaves an unexplained |ΔIC| <= 1.7e-04 against
  the notebook. Inputs are proved bit-identical, so the residual is inside the fitted
  learner. Carried as a limitation under a declared 5e-4 tolerance (rule 23).
- **EXP-0012's headline is benchmark-dependent and must not be quoted alone.** Its
  within-slot delta of ~+0.47 is over the causal same-slot MEDIAN; over trailing
  30-minute realised volatility the same delta is +0.013 (EXP-0015). Both numbers are
  correct; using only the first overstates the model by a wide margin.
- The canonical forward-vol forecast is UNDEFINED at the 15:29 and 15:59 decision slots
  (a 30-minute forward window does not fit in the session). Any study joining it to a
  13-slot book loses those entries — 253 of 4,209 noise_vwap trades in EXP-0013. This is
  structural, not a filter, but it must be counted every time.

- EXP-0012 strongly confirms conditional forecast skill but does not select an economic
  application. The feature set is simple, while histogram gradient boosting remains a
  nonlinear implementation. Any simpler-model comparison on consumed history is only
  descriptive until future evidence. Independent review of the very large conditional
  effect remains pending.

- **Study D under the EXP-0009 `z` label: CI no longer crosses zero on either market or
  metric** — the exact reason EXP-0006 downgraded D. This is NOT a restoration. It is the
  FIFTH measurement of D on the same consumed history, and `z` was chosen from four
  candidates AFTER seeing D fail under the canonical feature: precisely the search rule 26
  exists to catch. **`z` makes D worth exactly ONE clean FORWARD test; it does not
  retroactively pass a test D already failed.** D's status stays qualified/inconclusive.
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
0c. **DONE (2026-07-27): `futures/nq/noise_vwap/core/vei.py` repaired** — same
   `seed='sma'` default / `seed='first'` legacy split, closed form pinned to a textbook
   loop, 8/8 tests. EXP-0035 used `sma` and is unaffected; **EXP-0036's numbers are now
   flagged UNVERIFIED in that project's MEMORY pending a re-run** (its NO-GO verdict is
   not expected to flip — what needs re-measuring is the "estimator is load-bearing"
   claim and the +0.105 dSharpe cell). **Remaining: actually re-run EXP-0036.**
0d. **DONE (2026-07-27): project committed** (18fb6b0). Correction to the earlier note —
   the project WAS already tracked; the problem was that its only commit (913da8d)
   postdated the EXP-0006 overwrite, so the EXP-0001..0005 originals are confirmed
   unrecoverable. Also fixed a workspace-wide defect found on the way: `.gitignore`'s
   blanket `*.csv` under "data files" was excluding **every project's
   `experiments/ledger.csv`** — the mandated run-level audit trail — in all 9 projects;
   a `!**/experiments/ledger.csv` negation now keeps them tracked.
0f. **DONE (EXP-0009):** threshold calibration repaired; canonical regime label is now the
   trailing same-slot z-score. **Remaining from that run: `z` earns Study D exactly ONE
   clean FORWARD test** — do not re-measure D on this history again.
0g. **DONE (EXP-0010):** expansion onset vs late-chase + volume participation. Pooled
   mechanism separates cleanly, mature-high is weak, but primary H=10 strategy fails
   both-market daily-risk gate and the result breaks by era. Standalone path CLOSED;
   volume/onset may be tested only as an incremental veto/allocator on a validated book.
0h. **DONE (EXP-0011):** multi-horizon state passed every forward-volatility OOS gate,
   but the gain was operationally marginal. Deploy the causal same-slot median plus
   `range_rv_15m`; keep multi-horizon as a shadow benchmark. Do not re-tune on data
   through 2026-07-14.
0i. **DONE (EXP-0012):** clock-composition objection rejected; the two-feature core
   retains very strong same-slot, same-slot × weekday, residual-log-vol, and loss skill
   on both markets. Next: independent review, choose one operational use case and its
   decision loss, then begin future-only shadow logging after 2026-07-14. Do not infer
   directional alpha or tune the specification on consumed history.
0e. **DONE (EXP-0007):** test whether the legacy seed's accidental opening anchor was
   useful prediction. Mechanical channel confirmed; prediction rejected and path closed.
0j. **DONE (EXP-0013):** the forecast's economic value on a real book. Kill test fired on
   both markets; per-trade expectancy is proportional to forecast volatility, so
   `1/forecast` sizing is complete and optimal and the intraday volatility-SIZING channel
   is CLOSED. Old backlog item 7 (sizing/risk-targeting) is retired as an alpha lever.
   Also produced the importable, tested `core/forward_vol.py` and a rule-23 harness that
   pins any future use of the forecast to the EXP-0011 notebook.
1. Backlog item 13 — **the scheduled-calendar residual.** The highest-value untouched
   channel, and after EXP-0015 a TARGETED one with a specific number to beat: the
   expansion-call log-MSE skill over persistence is only +0.008 NQ / +0.061 ES, and
   scheduled events are the anticipatable source of volatility EXPANSION. EXP-0011 showed the realised-vol channel
   is near-saturated (six extra state variables bought +0.009 IC), so the missing
   information is the part of volatility that is SCHEDULED and knowable in advance.
   Diagnostic first: rank the two-input core's largest errors and measure how much of the
   residual is calendar-clustered, per era and per slot. Build a feature only if it is.
2. Backlog item 4 (daily/multi-day VEI + squeeze) — still the largest untouched dimension
   on the VEI side, and a day-level regime label suits gating an existing book better than
   an intraday tilt.
0k. **DONE (EXP-0014, backlog 14):** downside semivariance. The recipe transfers at
   92-93%; the up/down split is a constant near one half and is not forecastable at all.
   Channel closed.
0l. **DONE (EXP-0015, backlog 16):** the disagreement set. The core IS a timing
   instrument (change-IC +0.38, expansion gate passed) but PERSISTENCE, not seasonality,
   is the benchmark that matters, and against it the LEVEL advantage is only +0.013.
   EXP-0012's headline is qualified accordingly.
3. Backlog item 15 — a decision-shaped barrier/tail-probability target instead of a
   conditional mean. Cheap on the existing machinery and the last untested route from a
   forecast to a decision.
4. Backlog item 18 — rerun the EXP-0011 shuffled-target placebo on the frozen Part-B
   predictions. Evaluation-only, no refit, cannot be re-tuning; until it is run the
   multi-horizon INCREMENT should read "qualified-confirmed" (its Part-A null did not
   centre at zero and NQ's OOS delta sits inside that null band). Does not affect the
   adopted two-input core.
5. Do NOT re-run backlog item 5 (done in F), item 11 (done in EXP-0010), item 7 (done in
   EXP-0013), pursue holds past ~60 min, or open a sixth volatility-overlay experiment on
   the noise_vwap book.

## Promotion candidates

- The Wilder-estimator lesson and "vol-expansion ratio is a momentum regime switch, not
  a vol forecaster" may become cross-project learnings after confirming in another
  project; project-specific for now.
