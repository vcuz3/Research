# Project Memory: Noise Area VWAP

This file is the concise handoff for the project. Detailed evidence remains in
the linked reports, code, and run artifacts.

## Scope

- Objective: faithfully reproduce the published Noise Area VWAP strategy, audit
  its implementation, and test whether robust NQ/ES improvements exist.
- Instruments or markets: NQ and ES futures.
- Data coverage: 2011-2026 clean Databento research history. Shared parquet
  lives in `../data/` (`NQ_1m_clean.parquet`, `ES_1m_clean.parquet`); old vendor
  comparison files live in `../data/archive/old_vendor_backup/`.
- Current phase: final validation / future-shadow planning.

## Current status

- Verdict: qualified paper replication; research watchlist, not deployment-ready.
- Last verified: 2026-07-28 from the current forensic and review reports plus
  the corrected faithful Null C run `EXP-0007`, 1-second execution run
  `EXP-0009`, the rejected exit/lookback studies `EXP-0008`/`EXP-0010`, and
  the rejected gap/RVOL veto and sizing studies `EXP-0016`/`EXP-0017`.
- Lifecycle phase: final validation.
- Baseline replication: passed after correcting decision-clock and VWAP-gate
  discrepancies.
- Baseline tolerance and result: clean faithful headline is approximately NQ
  28.3% return / 1.31 Sharpe, ES 15.5% / 0.81, and equal-weight portfolio 23.8%
  / 1.52; compare published NQ 24.3% / 1.67, ES 16.8% / 1.25, portfolio 22.4%
  / 1.57.
- Engine audit: next-open faithful path and parity tooling exist. The Null C
  opening-sentinel defect is fixed and its anchor, net-move, atom, diffusivity,
  and pairing invariants are tested. The clean post-fix faithful run passed:
  NQ z=2.81/p=0.0323/49% capture; ES z=5.63/p=0.0323 with negative null net P&L.
- Execution profile: signal after the decision bar, fill at the next available
  bar open with explicit costs; `signal_close` is an ablation only.
- Holdout status: consumed. Only future shadow data can be clean holdout evidence.
- Experiment ledger: `experiments/ledger.csv` (legacy rows are reconstructed).
- Reproduction command: `python -m futures.nq.noise_vwap.scripts.forensic`.
- Primary evidence: `FORENSIC.md` and `REVIEW.md`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline evidence: `FORENSIC.md`
- Engine and pipeline review: `REVIEW.md`
- Data audit: `DATA_AUDIT.md`
- Kill tests: `KILL_TEST.md`
- Experiment history: `experiments/ledger.csv`

## Confirmed findings

- The original large replication gap was primarily caused by an off-by-one
  decision clock and a missing VWAP gate; the corrected clean run is broadly
  consistent with the paper's headline return claims.
- Faithful execution is next-open. Same-close execution is useful only as a
  labelled diagnostic.
- Performance is regime dependent and 2025 was weak; aggregate Sharpe alone is
  insufficient evidence of a persistent edge.
- The corrected faithful strategy exceeds the session-drift-preserving Null C
  on both NQ and ES in `artifacts/runs/EXP-0007/`; NQ still has material null
  capture (49%), so this supports a qualified timing edge rather than deployment.
- The former Null C implementation could shuffle its artificial zero-link
  sentinel away from index 0 and omit one real inter-bar link. The core and
  legacy study implementations now pin the opening atom and pass multi-seed
  invariant tests in `tests/test_nulls.py`.
- `EXP-0009` confirms that the working continuous-stop edge survives a causal
  first-touch execution model on 68.3 million NQ RTH one-second bars. At 0.5
  tick/side, zero-day daily Sharpe changed from 0.923 (1m close/next-open) to
  0.883 (1s touch), within the predeclared -0.15 tolerance. The touch engine was
  not an improvement: turnover increased and vol-targeted Sharpe/CAGR/maxDD
  changed from 1.184/22.5%/-18.1% to 1.090/19.5%/-24.4%. Evidence:
  `artifacts/runs/EXP-0009/`. **Decomposed by `EXP-0031`** (corrected after a
  reviewer question — the first-pass "latency" framing was wrong): the 1m
  continuous stop is CLOSE-CONFIRMED (`engine.py:158`, `close<stop` then next-1m
  open) whereas the EXP-0009 1s engine is FIRST-TOUCH (`sec_low<=stop`, a resting
  stop). These are different exit RULES, not one rule at two resolutions. Adding a
  default-off `trigger=1` (close-confirmed on 1s) splits the gap three ways at 0.5
  tick/side: (1) RESOLUTION is neutral — 1s close-confirmed reproduces the 1m
  result EXACTLY (4209 trades, daily Sharpe 0.9235 vs 0.9226), so finer data alone
  changes nothing and the fill is the next-minute open; (2) the WICK/trigger switch
  to first-touch is the real cost — +504 stop exits / +454 trades, −0.447 gross
  pt/trade, −0.041 daily Sharpe (~478 gross pts, ~1 NQ pt per wick-out), because
  close-confirmation filters the 1m wicks a resting stop takes; (3) LATENCY is a
  further separate −0.115 daily Sharpe / −0.33 gross pt per second on the touch
  model only (touch zero-day Sharpe L0/1/2/3/5s = 0.883/0.768/0.713/0.676/0.634).
  Conclusion: executing on finer data does NOT degrade the strategy; close-
  confirmation is a beneficial WICK FILTER and the deployed stop is realistic if
  you wait for the bar close. First-touch (a live resting stop) is a different,
  mildly worse exit policy dominated by premature wick-outs, not latency, though it
  stays net-positive (+$48-67/day, t>2.4). Retain the 1m close-confirmed continuous
  stop. New default-off `latency`+`trigger` args on `core/first_touch.py` (parity +
  wick + latency proved in `tests/test_first_touch.py`). Evidence:
  `artifacts/runs/EXP-0031/`; reproduce with
  `python -u -m futures.nq.noise_vwap.scripts.first_touch_decompose` and
  `... .scripts.hyp_0002_latency`.

- `EXP-0034` (HYP-0024) — decision-clock robustness audit of the continuous-stop
  baseline (user request). Shifted the 30-min decision-clock phase by +/-5/10 min and
  tried a 15-min cadence, across three exit engines on the common 3628-session 1s
  sample: E1 1m continuous (deployed close-confirmed), E2 1s first-touch (k=0), E3
  ATR buffer band-1.5*ATR_20 (EXP-0032 cell). Bands exist at every minute, so a shift
  only moves entry timing. VERDICT: **directionally robust but magnitude phase-
  sensitive; the deployed :59/:29 clock is a LOCAL OPTIMUM.** Every phase shift and
  the 15m cadence stays net-positive and significant (daily t 2.5-3.5, all vol-tgt
  Sharpe > 0.81) so the edge's sign/significance does not depend on the exact clock —
  but base30 is the BEST of the six grids on every engine/metric (1m daily Sharpe base
  0.923 vs shifts 0.669-0.814, max dev 0.25; touch 0.883 vs 0.552-0.791; atr 1.052 vs
  0.765-0.980), the +5min shift is uniformly the worst, and gross AND net pt/trade FALL
  on every shift (not variance — per-trade entry quality is phase-dependent). The
  identical phase-quality profile transfers across all three independent exit engines
  (shared entries only) = a real ENTRY-timing/intraday-seasonality effect around the
  round hour (:59 close -> :00 liquid open), corroborating FORENSIC's :00/:30
  off-by-one clock costing ~0.2-0.4 Sharpe. The 15m cadence is DILUTIVE (+40-50%
  trades, gross/trade collapses, lower zero-day Sharpe; vol-tgt holds). Rule-9a band
  coverage 0.996-1.000 all clocks. Retain the deployed :59/:29 30-min clock; record
  as a caveat that part of the headline is clock-phase alignment. No Null C (no clock
  improved on base). No core engine change. Evidence: `artifacts/runs/EXP-0034/`
  (`review.md`, `clock_grid.csv`, `report.json`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0024_decision_clock`.

- `EXP-0038` (regime-coverage diagnostic, user request after reading
  aligrithm.com/regime-coverage). Stratified the three exit variants (deployed
  continuous-stop baseline, partial_tp tp1.0_50, atr_buffer N20_k1.5) by a CAUSAL
  volatility regime (trailing-20d annualised σ, 4 quartile bins) × a CAUSAL trend/chop
  regime (|t-stat| of the trailing-20d mean daily return, 3 terciles) = 12 cells, on one
  common 3628-session RTH sample at 0.25 tick/side. Per cell: zero-day daily-$ Sharpe
  @1c with a 5000-draw bootstrap 95% CI; article gate N_min=252 days & SR_min=0.
  **All three variants share ONE profile and the SAME coverage gaps:** (1) aggregate
  ~1.0 Sharpe is DOMINATED by the high-vol band (25% of days, $170-236/day) — the
  article's "one cell carries the edge"; (2) the genuine SOFT SPOT is ELEVATED vol
  (50-75th pct: Sharpe 0.1-0.45, ~$5-30/day), NOT high vol, matching the project's
  "regime-dependent / 2025 weak" note; (3) daily-TREND cells are weakest within every
  vol band (win-day 16-18%) — an intraday breakout underperforms on strongly daily-
  trending days; (4) **8/12 cells pass, the SAME 4 fail — all for THIN coverage
  (<252d: low×chop 157, low×weak 210, elevated×trend 208, high×trend 176), NONE for
  negative Sharpe.** Vol/trend are correlated (calm→trend, crisis→chop) so the thin
  corners are real market rarity, not a fixable data gap; every thin cell's CI spans
  zero. Vol regimes are era-clustered (2013 has 0 high-vol days, 2022 ~98%; no year
  samples >~2 of 4 vol states) — the reason the full 15y is needed and two corners stay
  thin. **Exit comparison:** partial_tp tilts to calm/chop robustness (normal×chop
  0.57→0.98), atr_buffer to high-vol/trend upside (high×chop 1.80→2.40, elevated×trend
  0.37→1.16) but hurts low/normal chop — near mirror-image tilts; the exit is a
  regime-tilt lever, not a coverage fix. Descriptive only — no null spent, no verdict
  change; frozen configs; labels are 2-sided descriptive stratification (full-sample
  quantiles) over causal measures. Evidence: `artifacts/runs/EXP-0038/` (`review.md`,
  `cells_*.csv`, `per_year_*.csv`, `summary.json`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.regime_coverage`.

- `EXP-0039` (HYP-0027, Null C for the EXP-0038 regime profile; user follow-up).
  Question: is the high-vol Sharpe concentration real exploitable structure or the
  null-preserved vol-geometry that killed the vol conditioners EXP-0017/0019? Ran the
  EXP-0038 vol×trend stratification through 40 drift-preserving Null-C draws
  (`core/nulls.py::null_c_returns` + `_null_c_frame`), 3 variants. The null preserves
  each session's opening anchor + net move → **daily closes and therefore the regime
  LABELS are identical real-vs-null** (agreement 1.0000, asserted), so the test cleanly
  isolates intraday-timing content within fixed cell membership. Diffusivity gate passed
  (0.2500=0.2500). **RESULT — CONTRADICTS the machinery prior: the high-vol
  concentration BEATS the null decisively.** Baseline marginal `vol:high` real 1.475 vs
  null 0.390, z **4.26**, frac(null≥real) **0.000**; replicated on atr_buffer (z4.44)
  and partial_tp (z4.12) → an entry/regime property, not an exit artifact. The timing
  edge (real−null) is >2× larger in high vol (**+1.085**) than any other band
  (~+0.49–0.53). Every band beats its null (edge is broadly real), but the EXCESS is
  concentrated in high vol. Mechanistically coherent with the super-diffusive-morning
  finding (intraday continuation, the thing the breakout monetizes, is stronger when vol
  is high). **The EXP-0038 elevated-vol "soft spot" is mostly a DRIFT effect, not a
  timing hole:** the null itself earns −0.255 in elevated vol (vs +0.192 low), so the
  raw-Sharpe dip is unfavorable preserved drift; the strategy's own timing edge there
  (+0.492) ≈ low/normal. The three `elevated×*` cells are the only ones sitting inside
  their null (frac 0.10–0.28). **Refines, does NOT overturn, the "vol-independent"
  prior:** you still cannot GATE on vol (elevated cells carry positive real edge →
  skipping = turnover lever, consistent with VEI/RVOL/gap/Hurst NO-GOs), but the
  risk-adjusted intraday edge is genuinely vol-DEPENDENT. Clears the preregistered gate
  for a CAUSAL vol-sizing test (HYP-0028) — **but not a green light**: EXP-0028 (a real
  per-unit Hurst signal) FAILED sizing by concentrating tail risk, and high vol IS the
  drawdown regime, so a naive up-size chases real Sharpe into the tail. Any sizing
  schedule needs its own Null C, specification against BOTH per-contract and vol-targeted
  frames (vol-targeting already sizes down in high vol), maxDD/tail gating, and a forward
  shadow (2nd look on consumed history, rule 26). No core engine change. Evidence:
  `artifacts/runs/EXP-0039/` (`review.md`, `regime_nullc_*.csv`, `summary.json`);
  reproduce `python -u -m futures.nq.noise_vwap.scripts.hyp_0027_regime_nullc null 40`.

- `EXP-0040` (HYP-0028, causal vol-regime SIZING; the EXP-0039 follow-up): **NO-GO.**
  Overlaid a causal vol-regime weight (expanding percentile of trailing-20d vol, shifted;
  prior-mean-1 normalised, EXP-0017 protocol) on the deployed continuous-stop baseline.
  Frame A (deployable per-contract overlay): PRIMARY `high_boost` (1.5x above the causal
  75th vol pct — matches EXP-0039's "only high vol stood out") dSharpe **−0.006 (FLAT)**;
  `vol_linear` −0.025; mirror `vol_down` −0.036. Direction is right (high_boost beats the
  mirror by +0.030 → boosting high vol IS better than deweighting, as EXP-0039 predicts)
  but the magnitude is inert: **levering the high-Sharpe/high-VARIANCE days raises std in
  step with mean, so aggregate Sharpe is unmoved** — the unconditioned 1x book is already
  ~Sharpe-optimal across vol. Only side effect: high_boost mildly shallows maxDD
  (+$2,440) at flat Sharpe/higher mean$ (partly mean_w 1.037>1), tail slightly worse.
  Frame B (vol-target book × tilt, descriptive) is CONFOUNDED — **every schedule
  including the MIRROR raises Sharpe (vol_down +0.239)** = a generic reweighting/flooring
  artifact of the integer-floored vol-target series; it fails its own mirror control and
  is NOT evidence. Real fails the primary metric → **Null C NOT spent** (gate-nullc rule;
  a real pass that misses the primary is already a REJECT). **Synthesis
  EXP-0038/0039/0040:** the intraday edge is genuinely vol-DEPENDENT & concentrated in
  high vol (null-confirmed, EXP-0039) but is neither GATEABLE (elevated cells still carry
  positive edge → skipping = turnover lever) nor SIZEABLE (Frame A flat) — the EXP-0028
  "real per-unit signal doesn't monetize" / quality-not-alpha pattern. Vol changes WHERE
  the edge is measured, not how to size or gate it. Retain the unconditioned 1x book;
  vol-targeting stays survival not alpha. No core engine change (overlay lives only in
  `scripts/hyp_0028_vol_sizing.py`). Evidence: `artifacts/runs/EXP-0040/` (`review.md`,
  `real.json`); reproduce `python -u -m futures.nq.noise_vwap.scripts.hyp_0028_vol_sizing real`.

- **Cross-project confirmation of the sizing NO-GO at the INTRADAY entry level**
  (`futures/nq/vei_exploration` EXP-0013 / HYP-0010, 2026-07-31). EXP-0040 tested
  DAY-level vol banding; that study tested the remaining slice — per-ENTRY conditioning
  on a genuinely skilful causal forward-30-minute volatility forecast (its EXP-0011/0012
  two-input core). On this book's trades the standardised edge `net/forecast` is FLAT in
  the causal same-slot forecast percentile: slope -0.005 [-0.145,+0.135] NQ and
  +0.048 [-0.082,+0.184] ES on `continuous_stop`, CIs spanning zero with opposite signs;
  `baseline` agrees. Expectancy is PROPORTIONAL to forecast volatility, so `1/forecast`
  sizing is complete and optimal and no tilt remains. Two things this book should keep:
  (1) **the noise-band entry rule is ITSELF a volatility filter** — 34.8% NQ / 37.3% ES of
  trades land in the top forecast-vol quintile against 20% uniform, which is the
  mechanical reason every overlay here re-spends information the entry already spent;
  (2) the EXP-0011 forecast is **not** a better sizing denominator than the trailing ATR14
  already in use (day-t difference +0.46 [-0.08,+1.01] NQ cont., -0.33 [-0.96,+0.28] ES
  cont.) — do not switch. With EXP-0019, EXP-0032, EXP-0035/0036 and EXP-0040 this is the
  fifth rejected volatility route; treat a sixth overlay proposal as needing a mechanism
  that is not volatility level, expansion, or scale. Evidence:
  `../vei_exploration/artifacts/runs/EXP-0013/review.md`.

- `EXP-0041` (HYP-0029, causal regime calibration sweep): **QUALIFIED calibration
  result; no alpha promotion.** Swept indicator horizon {10,20,40} × trailing empirical
  calibration {252,504,756} on a common 3,173-session sample, selecting without P&L.
  The fixed EXP-0038 full-sample buckets are strongly era-bound (worst annual vol-bucket
  share 98.0%, calibration score 0.619). `10×504` is the only registered volatility-gate
  survivor: score 0.403, max annual bucket share 55.2%, median vol dwell 3 sessions,
  zero post-warm-up loss, causal prefix parity, and minimum 12-cell coverage 163 days.
  Primary `20×504` ranks second but narrowly fails the <=60% concentration gate (60.8%
  high in 2022); 252 days overreacts and 756 adapts too slowly, so 504 is the local
  calibration sweet spot. **Caveat:** the selected trend axis is NOT operationally
  stationary (median dwell 2 sessions; singleton rate 17.1%); treat `10×504` as a causal
  RELATIVE-VOL reporting label only. Descriptive P&L did not select the winner and is
  nonmonotonic: selected low/normal/elevated/high Sharpe = 1.18/1.47/1.14/0.73, so the
  EXP-0038 absolute high-vol concentration does not transfer to causal relative-vol
  labels and supplies no gate/size rationale (consistent with EXP-0040 NO-GO). No Null C.
  New reusable default-off machinery: `core/causal_regimes.py`; 11 focused causal/null
  tests pass. Evidence: `artifacts/runs/EXP-0041/`; reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0029_causal_regimes`.

- `EXP-0042` (HYP-0030, causal trend-label hysteresis): **PASS for label calibration;
  no alpha promotion.** Froze EXP-0041 `10×504` causal percentiles and swept trend
  boundary buffers {0,2.5,5,7.5,10 percentage points}, selecting without P&L. `h=7.5%`
  is the only complete pass: median trend dwell 2→3 sessions, singleton labels
  17.1%→7.4%, transitions 1,201→872, maximum annual trend share 43.5%, minimum 12-cell
  coverage 152 days, and causal prefix parity. The 5% buffer just misses the singleton
  gate (10.34%>10%); 10% is too sticky (minimum cell 143<150), so the survivor is locally
  bracketed. It differs from raw labels on 12.9% of days, never >4 consecutive sessions.
  Descriptive P&L was downstream and cannot select/promote: raw chop/weak/trend Sharpe
  0.88/1.48/0.76 becomes 0.46/1.79/0.83, but chop still changes sign across recent years.
  Hysteresis fixes boundary flicker, not return stationarity. Adopt `h=0.075` only for
  causal trend REPORTING alongside `10×504` relative vol; no entry gate, sizing overlay,
  or Null C. Reusable default-off state machine: `core/causal_regimes.py::hysteresis_labels`;
  14 focused tests pass. Evidence: `artifacts/runs/EXP-0042/`; reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0030_trend_hysteresis`.

- `EXP-0043` (HYP-0031, `require_reset` same-side re-entry lock; user-supplied external
  rule from a friend's independent Noise-Area implementation, `Require reset rule.md`
  "run 18"). Rule: after a STOP exit on one side, block fresh same-side entries until
  price is observed back INSIDE the noise area; opposite-side entries and flips are
  never blocked. **SPLIT VERDICT — the splitting variable is the STOP-CHECK CADENCE,
  and the two mechanisms are SUBSTITUTES.** PRIMARY preregistered cell (this project's
  deployed every-bar continuous-stop book): **NO-GO on both markets** — NQ dSharpe
  −0.011 / netR −4.41, ES +0.003 / netR −2.45, both fail the gate so Null C was not
  spent; an exposure-matched random drop from the same candidate pool does at least as
  well (frac(random≥real) 0.655 NQ / 0.825 ES) and the trades the lock removes are
  PROFITABLE (+0.0103 R NQ, +0.0054 ES) = exposure trimming, no selection. SECONDARY
  cell (decision-clock stop = the source spec's own run-18 cadence; **SEARCHED, not
  preregistered**): PASSES — NQ dSharpe **+0.117** / netR +4.77, ES **+0.224** / netR
  +14.81, removed trades are LOSERS (−0.0121 NQ / −0.0355 ES R, gross −2.36 pt NQ),
  gross/trade +23% both markets, ES maxDD 8.64→6.83. **DECISIVE control (1b): same
  lock, RANDOM unlock** — keep the lock, its side-scoping, cadence and PERSISTENCE,
  replace only its trigger with a coin flip at hazard p bisected to match the trade
  count exactly (NQ p=0.177 → n 2528 vs rule 2528; ES p=0.173 → 2567 vs 2579): real
  +0.117 vs null −0.012 sd 0.054 **frac 0.005** (NQ); +0.224 vs +0.039 sd 0.054
  **frac 0.000** (ES). The null centres at ~0, so cooling off for the same duration at
  matched exposure is worth NOTHING — the entire effect is WHERE the lock releases
  (price back inside the band), i.e. the reset CONDITION carries the information, which
  is precisely the spec's claim. Null C (40 draws): ES real +0.224 vs null +0.023,
  z+2.24, frac **0.000** PASS; NQ real +0.117 vs null **−0.038**, z+1.75, frac **0.075**
  = MISS vs the preregistered 0.05 (null centre NEGATIVE ⇒ tied to the thing being cut,
  the EXP-0013 signature, NOT fewer-trades variance amplification — but a miss, recorded
  as a miss). Diffusivity gate preserved exactly on both (NQ 0.2500=0.2500, ES
  0.0000=0.0000). MECHANISM: a 12×/day stop lets price run far outside the band before
  exiting, so the breakout is usually still true at the next checkpoint and the engine
  immediately re-buys the move that just failed; the lock removes that churn. An
  every-minute stop exits before that state forms, so little churn remains and what the
  lock then removes is profitable. Consistent with EXP-0031 (close-confirmed continuous
  stop retained): **the continuous stop already captures this value by another route.**
  Rejected clock-artifact explanation (the winning cell shares reset+stop clocks):
  control 1b holds the cadence FIXED and randomises only the trigger, and the effect
  transfers to ES with the same sign and larger magnitude. Retain the deployed
  baseline; do NOT promote as alpha; `reentry`/`reset_check`/`random_reset` kept
  default-off on `core/engine2.py` (bit-exact parity asserted on both stop books;
  `tests/test_require_reset.py` 7/7, incl. the load-bearing spec evaluation order —
  the stop bar is itself usually INSIDE the band, so checking reset after the stop
  would make the rule a no-op). **Two controls were produced INVALID in-run and are
  preserved rather than discarded:** (1) the first matched-count control matched lock
  FIRINGS not exposure — one blocked key removes only 0.586 trades, so the random arm
  cut ~666 NQ trades vs the rule's 430 and was flattered; corrected numbers 0.655/0.825
  replace an earlier 0.740/0.955; (2) on the secondary cells that control went
  DEGENERATE at K==pool (every draw identical, sd 0.0000) and printed a FALSE
  frac=0.000 that would have read as the run's strongest confirmation — a one-shot
  blocklist cannot imitate a PERSISTENT lock (blocking 100% of the pool once removes
  only ~153–310 trades vs the rule's 395), now guarded in code. Also recorded:
  **58% of ES and 39% of NQ minutes open exactly at the prior close**, so the
  next-open fill convention is frequently the same NUMBER as the signal close — a
  pre-existing project-wide caveat, identical across treatment and baseline.
  Evidence: `artifacts/runs/EXP-0043/` (`review.md`, `cells_*.csv`,
  `decomposition_*.json`, `random_reset_null_*.csv`, `nullc_*.csv`, `verdict_*.json`);
  reproduce `python -u -m futures.nq.noise_vwap.scripts.hyp_0031_require_reset real NQ`
  and `... real NQ 40 decision decision`.

- `EXP-0046` (HYP-0034, fast-alpha EXECUTION OVERLAY; Zarattini & Pagani 2026,
  `research_papers/Improving-Performance-with-Fast-Alphas-*.pdf`). Paper's thesis: a
  fast-decaying 5-min mean-reversion alpha (unprofitable standalone) is *informational*
  alpha that improves the *execution* of the slow breakout — delay entry to a 5-min
  fast pullback, delay the stop-exit to a 5-min bounce; they report Sharpe 0.87→0.99.
  Implemented as a single default-off overlay on `core/engine2.py`
  (`fast_overlay`/`fast_release`/`fast_horizon`/`fast_entry`/`fast_exit`/
  `fast_fixed_delay`/`fast_hazard`/`fast_seed`; bit-exact parity asserted under both
  fill modes; all fills stay next-open). Four release policies share identical wait
  machinery, differing ONLY in the trigger (EXP-0043 discipline): `opposite` (the
  paper), `same` (inverted), `fixed` (blind delay = real mean delay 5 bars), `random`
  (coin-flip release, hazard bisected to the real trade count). **REJECT / NO-GO on the
  bundled overlay.** NQ (primary): dSharpe **−0.062**, netR −5.04 → **REAL GATE FAILS**
  (needs +0.10 & netR not fall), so Null C not spent. ES (transfer): dSharpe **+0.098**,
  netR +6.12 — a near-miss just under the gate, **and the sibling markets DISAGREE in
  sign** (the standing mechanism-failure signal, cf. `nq-early-flat-close-nullc`); ES
  recent-era Sharpe also degrades 0.799→0.497. **The mechanism is nonetheless REAL:** on
  both markets `opposite` decisively beats `same`/`fixed`/`random` (NQ frac(random≥real)
  **0.000**, random mean −0.259 sd 0.050; ES same pattern) and lifts gross pt/t +7–11%
  (NQ 3.509→3.884, ES 0.730→0.776). It is a **quality-not-alpha exposure tradeoff**:
  better fills per trade, ~2.5% fewer trades, nets to a Sharpe LOSS. **KEY finding — the
  leg decomposition is CONSISTENT across NQ+ES and the two legs pull OPPOSITE ways:**
  entry-delay uniformly HARMFUL (NQ −0.104 / ES −0.096; no gross-pt gain — waiting to
  enter a momentum breakout forfeits the move), exit-delay uniformly POSITIVE (NQ +0.025
  / ES **+0.176**, gate-clearing on ES). Bundling them (as the paper does) hides the
  harmful entry leg behind the useful exit leg and drags NQ under the gate. Not a fill
  artifact (NQ negative under both next_open −0.062 and signal_close −0.035) — BUT the ES
  exit-leg IS partly fill-sensitive (signal_close +0.282 vs next_open +0.098; touch-vs-
  fill caution). Likely why the paper wins and we don't: **baseline substitution** — the
  paper stops at the SESSION OPEN (distant fixed stop, room for an exit-timing overlay);
  our deployed every-bar continuous band/VWAP stop already occupies that room (same
  substitution logic as EXP-0043/EXP-0031). **OPEN LEAD (SEARCHED, rule 26):** the
  EXIT-ONLY overlay is positive on both markets and gate-clearing on ES — worth its own
  preregistered hypothesis with a random-release null, a fill-model/touch-vs-fill check,
  and Null C before any claim; the combined and entry-only overlays are dead. Overlay
  kept default-off on `core/engine2.py`. Evidence: `artifacts/runs/EXP-0046/`
  (`review.md`, `arms_*.csv`, `legs_*.json`, `fill_ablation_*.json`, `coverage_*.json`,
  `random_null_*.csv`, `verdict_*.json`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0034_fast_overlay real NQ` (and `real ES`).
- Fast-alpha exit-leg FOLLOW-UP exploration (2026-08-16, SEARCHED/discovery only,
  `reports/FAST_EXIT_REVERSION_EXPLORE.md`, `scripts/explore_fast_exit_reversion.py`,
  `artifacts/explore/fast_exit_reversion/`). Three probes of EXP-0046's exit-only lead:
  (1) reversion translates NQ↔ES and is a **tail-of-run-length** effect — single
  adverse candle CONTINUES, a run of ≥5 reverts hard (NQ +0.180×med-move t+12.7 / ES
  +0.340 t+20.3, monotone in run length; the paper's consecutive-candles claim
  replicates on both). NQ reversion is more front-loaded (done by min 2). Survives the
  §6 embargo. (2) exit-only dSharpe is positive at EVERY 1–10 min horizon on both
  markets, short (1–3 min) ≥ paper's 5 min; the EXP-0046 NQ +0.025 at h=5 was a local
  dip (real ~+0.08–0.10) → IDEA-0007. (3) institutional-VWAP hypothesis
  **REJECTED/inverted** — exit uplift smallest under a VWAP stop (NQ −0.068, ES +0.004),
  largest under the noise-BAND stop (NQ +0.038, ES +0.142); the VWAP stop already
  trades ~27% fewer (baseline substitution, cf. `EXP-0010`) → IDEA-0008. None of this
  changes the bundled-overlay NO-GO.
- `EXP-0047` (HYP-0035, exit-only fast-alpha overlay at a fixed short horizon) —
  **NO-GO**, closes the EXP-0046 exit-only lead. Preregistered TRAIN/TEST split
  (TRAIN 2011-2020 selects h*=3, TEST 2020-2026 evaluates). NQ TEST real gate PASSES
  (dSharpe +0.135, netR +4.88) but FAILS the two decisive controls: a blind fixed
  4-bar delay scores +0.204 (> real) and the random-release null (200 draws, matched
  n) gives frac(random≥real)=0.100 — the reversion-timing attribution is not there
  out-of-era. ES TEST: inverted `same` (+0.092) ties real `opposite` (+0.089), both
  below gate → the fast sign carries no exit-timing info. The residual Sharpe lift is
  a generic exit-DELAY / looser effective stop (exposure/variance amplifier, cf.
  `EXP-0010`, `EXP-0046`, FX random-exit equivalence), not alpha. The EXP-0046
  full-sample "beats random frac 0.000" was era-pooled and did not replicate on recent
  data. Null C correctly skipped (gate rule). Evidence: `artifacts/runs/EXP-0047/`
  (`review.md`, `arms_test_*.csv`, `fill_ablation_test_*.json`, `random_null_test_NQ.csv`,
  `horizon_select_NQ.csv`, `verdict_*.json`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0035_exit_overlay NQ`. IDEA-0008
  (run-length conditioning) remains open but lower-prior after this.
- **Post-stop reversion mechanism study (2026-08-16) — overlay NO-GO stands for a
  SELECTION reason; reversion is REAL (corrected same day).** `reports/POST_STOP_REVERSION.md`,
  `scripts/study_post_stop_reversion.py`, `artifacts/explore/post_stop_reversion/`.
  A critique argued EXP-0047 over-reached (structured fixed-delay +0.204 ≫ random +0.075
  looked like un-refuted post-stop reversion). First pass measured post-stop reversion in
  R units (scale-free — raw points were Rule-19-confounded by NQ's ~10× scale drift) and
  wrongly concluded "no material reversion / target does not exist." **That over-stated it
  and contradicted the paper AND `FAST_EXIT_REVERSION_EXPLORE.md`.** Two errors: bucketed
  reversion by MAE *depth* not adverse-*run length* (the paper's axis), and read "small in
  R" as "nonexistent." CORRECTED via run-length re-analysis + matched all-bars R measurement:
  (1) reversion is REAL and MONOTONE in run length on all bars (ES run≥5 +0.0039 R, t 6.2;
  NQ runs 2–4 t 3–5.5) — paper replicates; (2) but TINY in tradable units — the earlier
  "+0.180×med_move, t 12.7" is only 0.0018 R (NQ) / 0.0025 R (ES); the huge t was sample
  size + median-move units, and ~0.003 R gross is sub-cost standalone (hence a fill-timing
  overlay only); (3) at OUR stops the run-length monotonicity is GONE (NQ run≥5 rev5 ≈ 0;
  ES insignificant) — SELECTION strips out the run-length STRUCTURE (a run strong enough
  to break the band+VWAP stop is a continuation case). **SECOND CORRECTION (same day) —
  the blind-wait uplift is REVERSION (mean), NOT exposure.** The first draft here (and
  EXP-0047's review) called the blind fixed-delay +0.204 dSharpe an "exposure/variance
  amplifier." A Shapley decomposition DISPROVES that: **+117% MEAN / −17% variance** (std
  rises). The blind 4-bar delay captures a small, real, cost-surviving post-stop reversion
  (+0.0041 R/trade net, +6.6 R over TEST) — MORE than the paper's sign rule (+0.0030). The
  pooled bounce is flat (short-run stops dominate, NQ run=1 rev5 +0.0066) so no structure
  to key on, but a dumb delay harvests it. **Split into two claims:** (1) the paper's
  fast-alpha SIGN mechanism = NO-GO (a blind delay dominates it on Sharpe/Sortino/netR/
  worst-day; ES `same`≈`opposite`) — the real EXP-0047 result; (2) a blind fixed short
  stop-delay = a small REAL reversion capture, but it weakens the stop (win rate 27%→38%,
  maxDD +22% 4.70→5.73 R, fatter per-trade tail) — Sharpe/Sortino like it, a
  drawdown-constrained prop objective likely doesn't → an OPEN, drawdown-gated lead
  needing its own preregistered test with a DRAWDOWN-AWARE metric (Calmar/prop trailing-DD,
  not Sharpe), NOT a closed NO-GO. [[IDEA-0008]] run-length-*conditioned* exit is weak on
  the STOP population; the flat pooled bounce is the live lead. Method keepers: reversion
  from the exit fill = §6 paired embargo for free; express a reversion effect in tradable
  R units before judging it (a median-move-unit t on 600k bars looks decisive at ~0.002 R);
  condition on the axis the mechanism names (run length), not a proxy (depth); **before
  calling a Sharpe uplift "exposure not signal," DECOMPOSE mean vs variance — don't assert
  it**; and read maxDD + per-trade tail (not just Sharpe/Sortino) when a change lifts win
  rate by loosening a stop (rule 22).

- `EXP-0048` (HYP-0036, entry confirmation-depth gate) — **NO-GO both markets.** SEARCHED
  from `diag_nonstationarity.py` (NQ 2026 fade = a HIT-RATE / follow-through collapse to
  win% 20.8%, below the ~23% geometric break-even; NOT signal scarcity — trd/sess ROSE to
  1.35 — NOT winner shrinkage nor variance) + `sweep_entry_buffer.py` (anticipatory-entry
  sweep: per-trade net edge MONOTONE in break depth; entering EARLIER strictly destroys
  edge, market pays for confirmation not anticipation). Preregistered test: gate decision-bar
  signals on `ext_atr >= k` (causal signed break depth from `scripts/wfo.py::candidate_signals`,
  ATR units), via the audited `entry_gate` path, k=0 bit-exact baseline; TRAIN first 60% /
  TEST last 40%; select k* = argmax TRAIN dSharpe subject to a **retain>=0.50 exposure floor**
  (forbids the degenerate tiny-exposure cell). NQ TRAIN loved it — k*=0.10 dSharpe **+0.186**,
  retain 0.56, per-trade gross 2.05→3.29→3.80 monotone in k (real per-trade quality) — but the
  Sharpe uplift is IN-SAMPLE ONLY and collapses to −0.65 once the floor is breached (k>=0.20).
  **NQ TEST kill test FAILS:** dSharpe **−0.016** (below +0.10 gate), netR −3.84, and the
  decisive matched-count random-drop null (keep 9571/12811, 200 draws) gives **frac(random>=real)
  0.210** — depth filtering is indistinguishable from randomly thinning the book. **ES TEST worse:**
  dSharpe **−0.312**, frac 0.905 (siblings disagree = standing mechanism-failure signal). Null C
  NOT spent (gate rule). The classic quality-not-alpha turnover lever (Hurst/VEI/gap/RVOL/
  percentile-momentum). **Reconciles the earlier "buffer lifts recent-era Sharpe" read:** that
  came from `threshold` (first-crossing) entry scored against the threshold buf=0 arm (Sharpe
  +0.771), a book that over-fires (6807 TEST signals vs the clock's 1732); the buffer climbed
  out of that over-firing hole toward — but never reaching — the deployed 30-min clock book
  (+1.322). Against the correct deployed baseline, split TRAIN/TEST, depth adds nothing
  risk-adjusted; "deeper earns more per trade" is real & era-stable, "deeper lifts Sharpe
  recently" was the weaker-reference + in-sample artifact. Retain the unconditioned
  continuous-stop baseline; no core engine change. Evidence: `artifacts/runs/EXP-0048/`
  (`review.md`, `train_sweep_NQ.csv`, `random_null_test_{NQ,ES}.csv`, `verdict_NQ.json`);
  reproduce `python -u -m futures.nq.noise_vwap.scripts.hyp_0036_confirm_depth NQ` and `... ES 0.1`.
- `EXP-0049` (HYP-0037, smarter depth entry gate: side-asymmetric / always-fire / band-relative)
  — **NO-GO all three arms, both markets.** SEARCHED user refinements of EXP-0048; none clears
  the NQ TEST +0.10 gate so no null spent. (A) side-asymmetric `k_long`/`k_short`: TRAIN grids
  MILDLY support the proposed asymmetry (short break wants to be deeper than long) — NQ
  kl0.10/ks0.15 +0.217, ES kl0.05/ks0.20 +0.414 — but TEST fails (NQ −0.011 netR−4.03; ES −0.268
  netR−9.93); in-sample only. (B) always-fire deeper first-crossing threshold vs the DEPLOYED
  clock book: loses at every buffer & era on both markets (deeper buffer raises per-trade pts
  only by shedding ~4× churn); only a cherry-picked NQ recent-20% slice "wins". (C) band-relative
  per-slot depth `ext_sigma`: diagnostic CONFIRMS the fixed-ATR cut was a mild time-of-day
  selector (per-slot fire-rate CV NQ 0.088→0.036, ES 0.115→0.050, sigma flatter) but correcting
  it does NOT change the verdict (NQ k_sig0.2 −0.007 netR−3.57; ES −0.405 netR−12.24). **The depth
  entry gate is a turnover/capacity lever in ATR OR band units.** Confirmation-depth entry family
  now CLOSED (EXP-0048 symmetric + EXP-0049). Evidence: `artifacts/runs/EXP-0049/` (`review.md`,
  `armA_train_{NQ,ES}.csv`, `armB_{NQ,ES}.csv`, `armC_fire_cv_{NQ,ES}.csv`, `verdict_{NQ,ES}.json`);
  reproduce `python -u -m futures.nq.noise_vwap.scripts.hyp_0037_depth_variants NQ` / `... ES`.

- `EXP-0050` (HYP-0039, first-30-min realised vol → day-ahead vol-target SIZING) — **NO-GO for
  deployment; one CONFIRMED forecast sub-result.** Transfer of the fast-alpha concept as an INPUT to
  a slower decision (IDEA-0011). **Kill test 1 (forecast) PASS:** first-30-min realised vol (log
  returns, causal — known at close of mfo 29, before the mfo-30 first entry) forecasts rest-of-session
  realised vol, adding **+0.119 (NQ) / +0.111 (ES) OOS R² over prior-session vol** and **+0.087 /
  +0.087 over the best daily baseline (HAR)**, TRAIN Newey-West HAC t ≈ 24/25, and **no directional
  leak** (placebo: early_rv does not predict session sign — a magnitude read, honouring the
  sizing-only constraint). Baseline horse-race finding: **a single trailing average does NOT beat
  yesterday** (ma5/ma22/EWMA all worse than the naive 1-day); only the HAR {1d,5d,22d} mix beats it
  (+0.046/+0.036). **Kill test 2 (sizing) NO-GO:** vol-targeting (daily-HAR or intraday) **loses to
  flat 1-contract on TRAIN both markets** — flat wins Sharpe AND Calmar decisively (NQ 1.27/12.5 vs
  ≤1.03/9.7; ES 0.48/2.99 vs ≤0.20/0.94); on TEST intraday only *ties* flat Sharpe (NQ 1.335 vs
  1.322; ES 1.048 vs 1.070) while improving Calmar via lower maxDD. **Mechanism REAFFIRMS
  `nq-noise-vwap-regime-coverage` (3rd independent confirmation the vol edge is not SIZEABLE):** net-R
  already ÷ 14-day ATR so vol-target re-normalises what ATR handled, and it DOWN-sizes the high-vol
  expansion days where this breakout-momentum edge concentrates. Narrow confirmed: intraday > daily-HAR
  at matched exposure on TEST both markets (NQ Calmar +1.49/Sharpe +0.125; ES +2.07/+0.115) but flips
  negative on ES TRAIN = not era-consistent → forward-watch only. No null spent (fails TRAIN-selectability).
  Evidence: `artifacts/runs/HYP-0039-gate/`, `artifacts/runs/HYP-0039-sizing/`; reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0039_vol_gate NQ` / `hyp_0039_vol_baselines NQ` /
  `hyp_0039_sizing NQ` (+ ES).

- `EXP-0051` (HYP-0038, post-adverse-spike passive-fill SCHEDULER = EXECUTION alpha, not
  signal alpha) — **NO-GO.** Transfer of the fast-alpha post-stop reversion (EXP-0046/0047,
  DIAG-fast-reversion) OUT of a directional overlay and INTO a fill-scheduling decision: the
  retrace is real/tiny/untimeable-for-direction but informative about the local PATH, so feed
  it to a decision that consumes path (execution). A post-processing layer (NO core/engine2.py
  change) re-prices the deployed clock book's ALREADY-DECIDED fills against the 1s tape — post a
  passive limit at `ref ± δ·σ_slot` leaning into the retrace, credit a fill only if the 1s path
  trades THROUGH by a vol-scaled guard `g·σ_slot` (RULES A4), else CHASE at the window-end 1s
  price. σ_slot = trailing-20-session mean of the 1m (high−low) range at that mfo slot. Reported
  as the LEARNINGS §6 triad: touch ceiling (g=0, non-capturable) / guarded book (deployable
  g≥0.10σ) / time-exit floor (always chase). EXITS = the thesis (aligned with the post-spike
  reversion); ENTRIES = a built-in PLACEBO (a passive entry adversely selects — misses the deep
  breaks that run away, which ARE the edge). Confirmatory a priori δ=0.25σ, g=0.10σ, K=5;
  TRAIN first 60% / TEST last 40%; per-DAY cluster-robust SE. **Kill 1 FAIL:** guarded EXIT
  improvement **−2.869 tick / −0.00346 R, day-t −3.02** (significantly NEGATIVE) on TEST — the
  deployable passive exit LOSES ~2.9 ticks/trade vs crossing. **Kill 2 FAIL (the decisive one):**
  the apparent saving lives ONLY at the non-capturable touch ceiling (+1.091 tick, itself day-t
  −0.35 = not even significant) and INVERTS under any real trade-through guard — **textbook
  touch-vs-fill (LEARNINGS §6) reproduced on a fresh instrument/context.** The retrace level is a
  reversal point, so a touch is not a fill; requiring price to trade THROUGH selects exactly the
  fills where it kept going (we'd have done better crossing). **Kill 3 PASS:** entry placebo
  −9.006 tick is worse than the exit −2.869, so the (negative) exit result is not generic spread
  capture; the entry arm's larger loss is the expected adverse selection. **Discovery sweep
  confirms the artifact is UNIFORM (TRAIN):** every guarded (g>0) EXIT config is ≤ +0.276 tick
  (t≈0) across all δ/g/K, and the touch-ceiling (g=0) configs are small positives (best +0.842
  tick) that all vanish or invert under any guard. 1s coverage EXCELLENT (TEST median 299 sec per
  5-min window, frac≥30s 1.000, frac==0 0.000) → NOT a fine-bar coverage artifact. The floor arm
  (+5.163 tick but day-t +0.06) shows the reversion is real but untimeable and huge-variance, and
  waiting reintroduces the position risk the framing was meant to avoid. **Third and cleanest
  death of the fast-alpha post-stop reversion** (EXP-0046 bundled overlay Sharpe-fail; EXP-0047
  exit-only overlay; now execution scheduling) — the reversion monetizes as neither direction nor
  execution. VERDICT FAIL → per the gated plan the ES 1s clean build (kill test 5, transfer) was
  NOT spent (rule 25 / gate-nullc). No Null C (real fails primary). No look-ahead (limit/fill use
  only the 1s path AFTER the exit bar; chase is an actually-traded 1s price). No core engine
  change. Evidence: `artifacts/runs/HYP-0038/` (`FINDINGS.md`, `confirm_NQ.json`,
  `discovery_NQ.csv`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0038_passive_fill NQ`.

## Provisional hypotheses

- None currently promoted.

## Invalidated or superseded findings

- `HYP-0025` is rejected (EXP-0035 SMA + EXP-0036 Wilder revisit, NO-GO both markets):
  the user's Volatility Expansion Index (VEI = intraday ATR(short)/ATR(long), baseline
  10/50, causal within-session `core/vei.py`) carries no robust, cross-market,
  monetizable info.
  **EXP-0036's NUMBERS ARE UNVERIFIED pending a re-run (flagged 2026-07-27).** It ran a
  MIS-INITIALISED Wilder ATR: `core/vei.py` used
  `ewm(alpha=1/n, min_periods=n, adjust=False)`, which pandas seeds at the FIRST bar
  rather than at the first n-bar SMA, and since this ATR resets every session the bias is
  paid once per session and never washes out. **The defect is now repaired**
  (`core/vei.py`, `seed='sma'` is the default; `seed='first'` reproduces EXP-0036 exactly
  for rule 23; the closed form is pinned to a literal textbook loop by
  `tests/test_vei.py::test_wilder_seed_matches_reference_loop`, 8/8 pass). In the sibling
  `vei_exploration` project the identical repair was NOT cosmetic — it moved forward-vol
  IC +0.157→+0.202, CUT apparent persistence (AC1 0.549→0.441; the shared seed was a
  contaminating common component), carried a time-of-day gradient, and shrank that
  project's headline finding until it failed its own preregistered kill test (EXP-0006).
  **Do not cite EXP-0036's specific numbers until it is re-run under the default seed.**
  EXP-0035 used `method='sma'`, which has no recursion to seed and is UNAFFECTED. The
  HYP-0025 NO-GO verdict rests on EXP-0035 plus EXP-0036's Null-C failure and absent ES
  transfer, so the *verdict* is not expected to flip; what needs re-measuring is the
  "estimator is load-bearing" claim and the +0.105 dSharpe cell.
  **EXP-0036 (Wilder-RMA revisit, user request):** `vei_exploration` Study A showed the
  SMA ATR used in EXP-0035 is the jumpiest, least-informative VEI variant; the Wilder
  RMA is far more persistent. Re-running the exact gate sweep with `method="wilder"`
  (`core/vei.py` now supports sma|wilder|ema, default sma reproduces EXP-0035) SHARPENED
  the result but did not change the verdict. NQ real gate now PASSES: family-best
  VEI(5/20) `low`≤1.003 (keep low-VEI/coiled breakouts, drop highest-VEI ~15% late
  chases) dSharpe +0.105, net R flat +0.33, retain 0.855, AND beats the matched-count
  random-drop null decisively (frac 0.000) = real per-trade quality selection (not
  rarity; matches EXP-0035 Part-C low-VEI-continues-better). BUT fails the decisive
  drift-preserving Null C on the primary metric (dSharpe real +0.105 vs null mean −0.001,
  center ~0, z+0.90, frac(null≥real)=0.175; dNetR frac 0.400) — the low-VEI quality
  selection is largely reproduced once returns are shuffled = vol-geometry the null
  preserves (EXP-0032 pattern), not a unique timing edge — and does NOT transfer to ES
  (best cell cuts 62% of trades, net R −12.0 = turnover lever). Estimator is load-bearing
  (SMA clear-fail → Wilder gate-pass-but-null-fail), verdict unchanged: real weak
  per-trade tilt, not validated alpha. Evidence: `artifacts/runs/EXP-0036/`; reproduce
  `...hyp_0025_vei_filter {real|null} {NQ|ES} 40 wilder`.
  --- Original EXP-0035 (SMA) below still stands ---
  Two parts. PART 1 descriptive (`scripts/vei_explore.py`, session-block-bootstrap
  Spearman IC): VEI does NOT predict direction (signed IC ≈0 both markets); it weakly
  predicts forward |move| (IC +0.017…+0.025, vol clustering, ~14% Q1→Q5 spread, not
  tradable); and at the BREAKOUT signal it has a small but cross-VARIANT-consistent
  NEGATIVE continuation-to-close IC on NQ (all 5 variants negative; baseline −0.030,
  CI[−0.046,−0.015]) = breakouts out of a LOW-VEI compression/coil follow through
  BETTER than high-VEI late chases (INVERTS the naive "expansion=impulse" thesis,
  mechanism-plausible) — BUT this does NOT transfer: ES continuation IC is
  weak/insignificant (−0.011, CI incl 0) with a POSITIVE quintile Q5−Q1 (+0.010,
  opposite sign). PART 2 entry gate (`scripts/hyp_0025_vei_filter.py`, rule-18 engine
  rerun via `entry_gate`, 5 variants × 2 dirs × 7 thresholds = 70 cells/mkt): NQ EVERY
  cell negative dSharpe (family-best VEI5/20 high retain0.85 dSharpe −0.013 = just the
  least-exposure-cut cell; matched random-drop null real −0.013 vs random −0.058,
  frac0.245 = mild real per-trade tilt but noise-level and net-negative); ES
  family-best VEI5/20 high dSharpe +0.066 but netR FALLS −2.4 and frac(rand≥real)0.095
  = turnover/capacity lever indistinguishable from random dropping, and OPPOSITE
  direction to NQ. Real gate REJECT on both → no Null C (standing rule). The classic
  project signature (small real per-trade effect, no risk-adjusted monetization) and
  fully consistent with volatility-INDEPENDENCE + the rejected selectivity screens
  (RVOL EXP-0016, gap EXP-0024, Hurst EXP-0026/0027, ATR-buffer EXP-0032). Retain the
  unconditioned continuous-stop baseline; `core/vei.py` kept as tested causal feature
  machinery, gate overlays default-off (no core engine change). Rule-9a: only the
  09:59 slot drops (intraday long-ATR not yet populated); ~100% coverage elsewhere.
  Evidence: `artifacts/runs/EXP-0035/` (`review.md`, `explore_{NQ,ES}.txt`,
  `gate_{NQ,ES}.txt`, `sweep_{NQ,ES}.csv`, `{coverage,forward_ic,continuation_ic}_*`,
  `random_null_*`, `verdict_*`); reproduce
  `python -u -m futures.nq.noise_vwap.scripts.vei_explore {NQ|ES}` and
  `...hyp_0025_vei_filter real {NQ|ES}`.
- `HYP-0022` is rejected (EXP-0032, NO-GO): a causal intraday-ATR stop buffer as a
  systematic replacement for the arbitrary close-confirmation wick filter. Exit on
  the first 1s touch of `stop = max(upper,vwap) − k·ATR_N` (float, no ratchet;
  `ATR_N` = causal rolling 1-min True-Range mean, `N∈{5..30}`, available from mfo30;
  entries unchanged; `k=0` = EXP-0031 first-touch). Motivated by EXP-0031: close-
  confirmation is an arbitrary, sampling-grid-pinned wick tolerance, so replace it
  with an explicit volatility-scaled buffer. PHASE 1 beat it in-sample — best
  `N20_k1.5` daily Sharpe 1.052 vs 0.923 (+0.130), vol-tgt 1.331 vs 1.184, `k=1.5`
  best for every `N`; a matched-width fixed 6.375-pt buffer reached only 0.968, an
  apparent +0.085 vol-scaling uplift; calibration showed close-confirmation tolerates
  wicks to ~0.8–1.0 ATR (p90) but the monetized `k≈1.5` is wider (part trailing
  looseness). The uplift HELD/strengthened in recent eras (≥2024 +0.191, ≥2025
  +0.155, last-252d +0.286; only CY2025 soft −0.061) and TRANSFERRED to ES (+0.105
  vs-cc, +0.032 scaling). PHASE 2 Null C KILLED it, and EXP-0033 supersedes the
  original 30-draw fixed-cell statistics with a full 199-draw selection-corrected
  test: every null draw repeats the complete N-k family and Phase-1 maximum-Sharpe
  selection. BOTH real uplifts sit almost exactly at their null centers:
  `uplift_vs_cc` real +0.132 vs null +0.139 (z -0.08, p=0.510); decisive
  `uplift_scaling` real +0.085 vs null +0.088 (z -0.04, p=0.525). Exact one-second
  minute-block null replay validates the fast one-minute proxy (3 frozen draws,
  max uplift error 0.0046 Sharpe, mean 0.0024). The return shuffle preserves the
  opening anchor, complete bar/link/volume atom set, session NET move, and
  diffusivity — NOT session high-low range (prior wording corrected) — while
  destroying order. The vol-adaptive stop benefit is reproduced after order is
  destroyed. Same signature as
  EXP-0019 (vol-conditional cadence) and the EXP-0010/0012 looser-stop rejections:
  whipsaw/vol-geometry is a property Null C preserves. Better-motivated than the wick
  mechanic and beats it in-sample/recently/on ES, but the gain is machinery, not real
  intraday path structure. Retain the close-confirmed continuous stop; thread closed
  on consumed history (revisit only with future/shadow data). New isolated engine
  `core/atr_buffer.py` (+ 1m runner reusing the kernel on 1m bars; `first_touch.py`
  untouched); accelerated audited null machinery in `core/nulls_fast.py` is
  bit-exact and its 4-worker 199-draw family run completed in 124.4s. Evidence:
  `artifacts/runs/EXP-0032/` for Phase 1 and `artifacts/runs/EXP-0033/` for the
  corrected null/execution validation; reproduce
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0023_fast_exact_nullc validate`
  and `...hyp_0023_fast_exact_nullc null 199 --workers 4`.
  **EXP-0037 block-null follow-up (user request):** the concern that single-minute
  shuffling destroys the volatility clusters an ATR exit needs is now directly
  tested and does not change the verdict. A corrected block Null C pins only the
  opening atom and permutes intact 5m/10m/15m blocks, preserving most local
  volatility dependence (absolute-body lag1 real 0.464 vs null 0.437/0.450/0.452;
  lag5 under 10m/15m blocks 0.408/0.421 vs 0.454) while reducing the time-of-day
  volatility-profile correlation to 0.286/0.303/0.331. In 199 full-family draws
  per block, real scaling uplift +0.085 sits at every null center: 5m +0.0888
  (z-0.05,p.515), 10m +0.0917 (z-0.09,p.480), 15m +0.0795 (z+0.08,p.395).
  Uplift versus close-confirmed fails even more strongly (all null means above
  real). Thus EXP-0033 was not rejected merely because its atom shuffle destroyed
  local vol clustering; keep the ATR buffer NO-GO. Evidence: `artifacts/runs/EXP-0037/`;
  reproduce `python -m futures.nq.noise_vwap.scripts.hyp_0026_block_nullc validate`
  and `...hyp_0026_block_nullc null 199 --workers 4`.
- `HYP-0021` is rejected (EXP-0030): the paper-inspired causal multi-horizon
  percentile-rank momentum + hysteresis overlay is a strong NQ NO-GO; no Null C
  spent because the real family failed by a wide margin.  At every minute, causal
  ATR-normalized returns over {5,15,30,60} minutes were ranked against the
  strictly prior 252-session, same-minute, same-sign history; the four ranks were
  averaged per side.  Normal noise/VWAP entries were gated at
  `q_enter in {0.6,0.7,0.8}` and the ordinary continuous band/VWAP stop was armed
  only after active-side rank fell below `q_exit in {0.2,0.4,0.6}`; flips/EOD
  remained active.  EVERY cell was worse: baseline 4209 trades / 91.20R / Sharpe
  1.288 / gross 3.509 pt/trade / maxDD 4.70R; family-best `qe0.6/qx0.2` retained
  only 37% (1556 trades), raised gross/trade to 4.247 but collapsed netR to 39.42,
  Sharpe to 0.694 (delta -0.594), and worsened maxDD to 7.18R.  Hysteresis worked
  mechanically (mean hold 67.7->106.9 min; stop exits 3414->949) and modestly
  improved the same-entry rank-only arm, but could not offset lost exposure.
  Stronger ranks were non-monotone (`qe0.8` gross below baseline); the inverted
  weak-rank control also lost (Sharpe 1.138 / 63.11R), so this is neither clean
  strength alpha nor a reversed edge.  It repeats the Hurst/cross-confirmation
  pattern: modest per-trade quality/capacity information does not monetize at the
  portfolio level.  Feature coverage was 96.45%-100% by slot; default-off engine
  parity passed.  Retain the unconditioned continuous-stop baseline.  Evidence:
  `artifacts/runs/EXP-0030/`; reproduce with
  `python -u -m futures.nq.noise_vwap.scripts.hyp_0021_percentile_hysteresis NQ`.
- `HYP-0020` is rejected (EXP-0029): a LAPLACE recency-weighted noise band is a
  cross-market NO-GO; no Null C spent. User idea: the flat lb90 mean band beats
  shorter lookbacks (EXP-0025) but under-weights recent sessions, so keep a long
  window but tilt the trailing per-slot |move| mean toward recent sessions with a
  Laplace kernel `sigma[d,mfo] = Σ_k w_k·|move[d-k,mfo]| / Σ w_k`, `w_k =
  exp(-|k-mu|/b)`. Swept the two shape knobs the user named — center-of-mass
  `mu∈{1,5,15,30}` and decay half-life `h∈{5,15,40}` (`b=h/ln2`) — with the window
  DERIVED (`lookback=clip(mu+5b,90,250)`) so slower decay uses a longer lookback
  ("slow decay for long lookback"); `b→∞,lb90` reduces to the flat baseline bit-exact
  (`tests/test_bands.py::TestLaplaceBand`). RAW/MATCHED-width split (EXP-0021 control),
  common post-lb250 same-sample. GATE FAILS on both → no Null C. NQ: EVERY matched cell
  WORSE (best mu5 h15 dSharpe −0.019; grid −0.019…−0.219; recency tilt strictly
  degrades, maxDD 4.7→8.2R at mu1 h5). ES: best matched mu1 h5 dSharpe +0.065 (<+0.10
  gate) is a width/capacity artifact (gross/trade FALLS −0.081, 136 fewer trades) and
  does NOT transfer (same cell is one of NQ's WORST matched, −0.117). DECISIVE: residual
  `laplace/flat` by decision slot is FLAT across all 13 slots (NQ ≈1.005, ES ≈1.08) = a
  uniform rescale, no slot-dependent reshape = the EXP-0021 quantile signature. The
  per-slot LEVEL is a sufficient statistic and the every-bar continuous stop already
  supplies recency vol-adaptivity, so a cross-history tilt only adds estimator variance
  to a well-estimated quantity. Extends the recast programme (EXP-0020/0021/0022) +
  EXP-0025: the noise band is fully summarized by its per-slot flat symmetric
  level/width across time-profile, distribution, up/down symmetry, estimator
  bias/variance, AND cross-history weighting. Band construction axis exhausted. Retain
  `core/session.py::noise_bands` lb90; `noise_bands_laplace`/`laplace_weights` kept in
  `core/bands.py` as tested benchmark. Evidence: `artifacts/runs/EXP-0029/`
  (`review.md`, `laplace_nq.txt`, `laplace_es.txt`); `experiments/hypotheses/HYP-0020.md`.
  Reproduce: `python -m futures.nq.noise_vwap.scripts.hyp_0020_laplace_band real {NQ|ES}`.
- `HYP-0019` is rejected (EXP-0028): matched-exposure Hurst risk allocation is a
  cross-market NO-GO. A single frozen causal schedule weighted entry-H<0.5 at
  0.75x and H>=0.5 at 1.25x, divided by the expanding PRIOR mean raw weight after
  100 trades; entries/exits and trade population were unchanged. Net R increased
  on both markets (NQ 91.20->95.30R; ES 51.47->56.68R), confirming EXP-0026's
  return-ranking sign, but Sharpe did not: NQ 1.288->1.265, ES 0.698->0.702, and
  the equal-risk pool 1.082->1.085 (dSharpe +0.002 vs +0.10 gate). MaxDD worsened
  on both (NQ 4.70->5.15R; ES 7.45->8.65R), as did pooled maxDD 4.36->5.16R.
  The inverted control was worse on return/Sharpe, so H ranks expectancy but not
  diversification: overweighting the better-quality trades merely concentrates
  tail risk. Real gate failed; allocation-label null not spent. Synthesis:
  selection (EXP-0026), exit management (EXP-0027), and now sizing all fail to
  monetize Hurst. Historical Hurst branch exhausted; retain equal sizing and use
  only future shadow data for any revisit. Evidence: `artifacts/runs/EXP-0028/`.
- `HYP-0018` is rejected (EXP-0027): conditioning the `tp1.0_50` partial-take-profit
  on entry-bar Hurst is a cross-market NO-GO; no Null-C spent. Follow-on from
  EXP-0026 — apply the real Hurst continuation signal where it costs no exposure
  (the EXIT, not a selection gate). Entries/trade population UNCHANGED (4209 NQ /
  4326 ES every cell); only the partial fires conditionally: bank the +1ATR partial
  on trades with entry-H ≤ T ("bank chop"), hold the runner on H > T; sweep T over
  {0.35..0.65}; endpoints = no-tp (continuous-stop baseline) and all-tp
  (unconditional tp1.0_50); MIRROR control banks high-H. Implemented via a new
  default-off `tp_gate` on `core/engine2.py` (parity: tp_gate=None==all-tp, empty
  gate==no-tp, bit-exact). REJECT on both. DECISIVE reads: (1) conditioning adds
  ~nothing — best conditional uplift over unconditional tp1.0_50 is −0.012 Sharpe
  (NQ) / +0.023 (ES), noise-level and below the +0.10 gate; at useful thresholds it
  banks ~95% of trades = collapses to all-tp, i.e. the tp's post-+1ATR
  mean-reversion capture is NOT Hurst-selective. (2) INVERTED + transfers: the
  MIRROR (bank high-H) BEATS the conditional (bank low-H) on BOTH markets (NQ 1.354
  vs 1.332; ES 0.723 vs 0.710) — predicted asymmetry with the OPPOSITE sign, so a
  tiny real tape property not NQ noise; entry persistence does not predict whether a
  trade's give-back is worth banking. (3) the tp overlay itself helps NQ (all-tp
  1.344 vs no-tp 1.288, +0.056) but HURTS ES (0.687 vs 0.698), so no robust exit
  surface exists for H to improve. Synthesis with EXP-0026: the Hurst exponent is a
  real per-trade CONTINUATION/quality signal that monetizes NEITHER as selection
  (EXP-0026 gate = turnover lever) NOR as exit management (this run) — the Hurst
  lever is exhausted. Retain unconditioned baseline; keep `tp_gate` as tested
  default-off machinery. Evidence: `artifacts/runs/EXP-0027/` (`review.md`,
  `conditional_{NQ,ES}.csv`, `mirror_{NQ,ES}.csv`, `verdict_{NQ,ES}.json`);
  `experiments/hypotheses/HYP-0018.md`. Reproduce:
  `python -m futures.nq.noise_vwap.scripts.hyp_0018_hurst_exit real {NQ|ES}`.
- `HYP-0017` is rejected as deployable alpha (EXP-0026): a causal intraday
  Hurst-exponent trade filter is a cross-market NO-GO, but the LEVEL carries real
  per-trade QUALITY info. User idea: add the Hurst exponent as a trade filter,
  test the sensitivity of Sharpe/expected-R to it, and test the raw level H, its
  ROC (1st derivative dH) and 2nd derivative d2H. Implemented as a per-signal
  `entry_gate` (rule-18 engine rerun, not a trade drop): at each 30-min decision
  bar compute the order-1 generalized Hurst exponent (structure function
  `E|X(t+τ)-X(t)|∝τ^H`, log-log slope over lags {1,2,3,4,5,7,10,15,20}∩[≤n/2]) of
  the causal session-to-date log-close path (anchored at the same open the band
  uses; validated trend→0.99, random-walk→0.49); dH/d2H taken along the
  within-session decision sequence. Real gate FAILS on both → no Null-C.
  Family-best on BOTH NQ and ES is the SAME un-tuned natural cell **H ≥ 0.5**
  (random-walk boundary): NQ dSharpe +0.058 / dNetR −10.4R (Sh 1.288→1.346, netR
  91.2→80.8, retain 0.62, maxDD 4.70→4.17R); ES dSharpe +0.084 / dNetR −2.9R (Sh
  0.698→0.781, retain 0.56) — both below the +0.10 Sharpe gate AND net R falls.
  POSITIVE finding: the Hurst LEVEL is a real, cross-market, mechanism-consistent
  per-trade QUALITY signal — as H≥T rises, gross pts/trade and expected net-R/trade
  rise MONOTONICALLY (NQ gross/t 3.51→4.59, ES 0.73→1.01; exp netR/t NQ
  0.022→0.031→0.046), the chop-regime `low` (keep H≤T) direction is worse
  everywhere (sign confirmed: breakouts want a persistent tape), and H≥0.5 BEATS a
  200-draw matched-count random-signal-drop null on NQ (frac(rand≥real) Sharpe
  0.03; ES marginal 0.08) — so it is NOT a pure rarity filter. **⚠ THAT POSITIVE
  FINDING IS QUALIFIED 2026-08-03 by `futures/nq/estimator_bias` EXP-0001 (finding
  C): it is CONFOUNDED WITH TIME OF DAY and is no longer separately established.**
  H here is estimated on a session-to-date EXPANDING window (30 bars at the mfo=29
  decision, 390 at mfo=389) and compared against a FIXED `H_GRID` cut, so the
  gate's per-slot selection-rate CV runs **2.88–45.59× (NQ, median 23.9×) /
  5.90–46.48× (ES)** that of a matched same-slot z-score of the same H, at all 7
  thresholds. At `H≥0.55` it fires on **33.5% of 10:00 decisions vs 8.4% of 15:59
  decisions (NQ; 31.7%→5.2% ES)** — 4–6× more likely in the morning, where this
  project separately documents super-diffusion (EXP-0020) and its strongest edge.
  Mechanism is DISPERSION not level: mean H moves 0.02 across the session while
  sd compresses 3.8×, and a `signflip` null (real |returns|, random signs, true
  H=0.50) reproduces about HALF the ramp. The matched-count random null used here
  matched COUNT, not TIME OF DAY, so it cannot separate the two. **Repair if ever
  revisited: a slot-matched null, or gate on a same-slot z-scored H.** Nothing
  deployed is affected (the gate is already rejected as selection/exit/sizing).
  Evidence: `futures/nq/estimator_bias/reports/FINDINGS.md` §C. But it does NOT
  monetize: it raises per-trade quality (+30% NQ, +38% ES gross/t) while cutting
  exposure ~40%, so total net R FALLS and Sharpe stays below the gate = a
  turnover/capacity lever, the same [[nq-es-crossmarket-confirm]] pattern (better
  selection + less exposure = no risk-adjusted gain). The user's DERIVATIVES
  (dH ROC, d2H acceleration) are inert-to-harmful: EVERY dH/d2H cell, both
  directions, both markets, is worse than baseline. Consistent with the project's
  volatility-INDEPENDENCE and the string of selectivity screens (KAMA regime, gap
  veto EXP-0024, RVOL veto EXP-0016) that all resolved as levers, not alpha. Retain
  the unconditioned baseline. Evidence: `artifacts/runs/EXP-0026/` (`review.md`,
  `sweep_{NQ,ES}.csv`, `random_null_{NQ,ES}.csv`, `verdict_{NQ,ES}.json`);
  `experiments/hypotheses/HYP-0017.md`. Reproduce:
  `python -m futures.nq.noise_vwap.scripts.hyp_0017_hurst_filter real {NQ|ES}`.
- `HYP-0015` is rejected (EXP-0024): a symmetric overnight-gap MAGNITUDE
  whole-day veto (skip every entry on a day whose `|rth_open - prior_close|/atr`
  exceeds T, T∈{0.5..2.0} ATR) is a cross-market NO-GO that fails INVERTED. This
  is the user's "if there's an overnight gap, just don't trade" idea as a hard
  GATE — distinct from the rejected EXP-0017 gap/RVOL scaling and the EXP-0016
  directional gap-vs-signal + low-RVOL per-signal veto (this is symmetric, no
  RVOL, whole-day). Every T degrades BOTH net R and daily Sharpe on NQ AND ES,
  monotonically (skip more → lose more): NQ T=0.5 skips 26.8% of days, netR
  91.2→58.2 (−33R), Sh 1.72→1.47; family-best T=2.0 still −1.4R/−0.019 Sh. Real
  gate fails on both → NO Null-C spent (standing rule). DECISIVE: the removed
  trades are PROFITABLE (NQ removed meanR +0.206 vs kept +0.021; removed early
  ≤mfo149 +0.367R = the best slice) — a big overnight gap is a strong directional
  open the momentum breakout RIDES, not the mis-anchored band/VWAP noise the
  mechanism predicted; the anchor-contamination thesis is inverted. Matched-count
  random-day-drop null (200 draws): random dropping is ≈Sharpe-neutral but the
  real gap-gate sits at frac(random≥real)=0.805 NQ / 0.870 ES = random beats gap
  dropping ~80–87% of the time = ANTI-selection, worse than a rarity filter.
  Gross/trade stays flat (3.51→3.51–3.65) while net R collapses = the loss is
  purely deleting profitable days. Same theme as EXP-0022 (the up/down asymmetry
  is drift the strategy already monetizes; gating on it double-counts) and the
  volatility-independence finding. Whole-day skip == drop-day-trades verified
  trade-for-trade against the engine `entry_gate` path (`_verify_equivalence`),
  so sweeps/nulls filter the frozen baseline (no per-cell engine re-runs). Retain
  the unconditioned baseline. Only the gap gate was run (the volume-supported-
  breakout gate and the 15-min clock were dropped by the user). Evidence:
  `artifacts/runs/EXP-0024/` (`review.md`, `real_sweep_{NQ,ES}.csv`,
  `random_day_null_{NQ,ES}.csv`); `experiments/hypotheses/HYP-0015.md`.
- `HYP-0016` is rejected (EXP-0025): a SURROUND-SMOOTHED, SHORT-HISTORY noise band
  (user idea) is a cross-market NO-GO. Redefinition: `sigma[d,mfo] = mean over prior
  `hist` sessions AND a local minute window [mfo-w, mfo+w]` (center-included, `2w+1`
  min, edge-truncated so the OPEN averages FORWARD-only; forward minutes come only
  from strictly-prior completed sessions so CAUSAL, no lookahead) of `|move|`. Thesis:
  neighbour pooling cuts per-slot estimator variance so a short, recency-adaptive
  history becomes usable (the 90-day average is lagging). Grid w∈{5,14,30} × hist∈
  {5,14,30} + `plain(hist)` control (surround off ≡ `noise_bands(hist)`), continuous
  stop, common post-lb90 sample. GATE FAILS on both → no Null C. NQ: EVERY cell worse
  on Sharpe (baseline Sh 1.29 / net_pt/t 3.159; best surround h30 w30 Sh 1.20 dSharpe
  −0.083 / net_pt/t 3.152 / netR −4.9R); shortening history is the dominant loss
  (plain h30/h14/h5 = 1.22/1.04/1.07), surround doesn't recover it. ES: best h14 w30
  dSharpe +0.029 (≪+0.10) but gross/trade FALLS −0.081 with +179 trades at wRatio 0.93
  = width dial, doesn't transfer to NQ. DECISIVE: (1) per-trade quality (the user's
  headline metric) NEVER rises above baseline on either market — baseline net_pt/t
  3.159 is the grid max. (2) The variance-reduction mechanism IS real but only bites
  once history is crippled (NQ h5 plain 1.07→h5 w30 1.13; ES h30 plain 0.59→h30 w30
  0.67) and never climbs back to lb90 = the long history is already the better
  bias/variance point; the every-bar CONTINUOUS STOP already supplies current-session
  vol adaptivity, so the band only needs a stable long-run per-slot LEVEL (the "lag"
  is load-bearing). (3) wRatio 0.89–0.99 = mild capacity dial, not alpha. New AXIS vs
  the EXP-0020/0021/0022 recast programme: that changed the profile SHAPE, this
  changed the LEVEL ESTIMATOR (bias/variance via pooling + recency) — still inert.
  `w=0`-reduction + causality proved in `tests/test_bands.py`. Retain `noise_bands`
  lb90; `noise_bands_surround` kept as tested benchmark. Evidence:
  `artifacts/runs/EXP-0025/` (`review.md`, `surround_nq.txt`, `surround_es.txt`);
  `experiments/hypotheses/HYP-0016.md`.
- `HYP-0014` is rejected (EXP-0022): recasting the noise area as an ASYMMETRIC
  (per-side) band — separate up/down half-widths from the causal semi-means
  (`up = mean(max(move,0))`, `dn = mean(max(-move,0))`, `up+dn == sigma` identically),
  blended by a tilt (sig_up = sigma+tilt·(2up−sigma), sig_dn = sigma+tilt·(2dn−sigma))
  — is a cross-market NO-GO. The construction CONSERVES total half-width for every
  tilt (sig_up+sig_dn == 2·sigma, proved in `tests/test_bands.py`), so it is a PURE
  up/down redistribution, NOT the width dial that killed EXP-0010/0012/0021, and no
  RAW/MATCHED split is needed. Every tilt fails the +0.10 gate: NQ monotonically
  WORSE in tilt (ΔSharpe −0.065/−0.095/−0.110 at tilt 0.5/1.0/1.5; best tilt 0.5 also
  −5.4R net); ES best tilt 1.0 ΔSharpe +0.023/+1.9R (far below gate), tilt 1.5
  collapses (maxDD 7.0→12.9R). No Null C spent (real pass fails primary on both).
  DECISIVE diagnostic: the per-side residual at tilt=1 IS a real, cross-market-
  transferring asymmetry but a SMALL one — up-edge ~2–5% wider than symmetric,
  down-edge ~2–5% narrower, consistent across ALL 13 slots, largest mid-day (up/dn
  ≈1.09–1.10), minimal at mfo 89 (≈1.00). That up-tilt is the index up-drift showing
  in the up semi-mean; acting on it HURTS on NQ because widening the up-threshold
  rejects the drift-driven up-breakouts the momentum system rides while narrowing the
  down-threshold admits counter-drift down-breaks. The symmetric band is actively
  BETTER — the up/down asymmetry is a DRIFT property the strategy already monetizes
  (VWAP gate + ride-to-close); re-sizing the band to it double-counts and mis-selects.
  SYNTHESIS (transforms 1–3 complete): neither a √t reshape (cone, EXP-0020), a
  distributional reshape (quantile, EXP-0021), nor an up/down redistribution
  (asymmetric, EXP-0022) adds risk-adjusted value → the noise-area band is fully
  summarized by its per-slot SYMMETRIC LEVEL/width. Recast programme exhausted; retain
  `core/session.py::noise_bands`. The asymmetric band stays in `core/bands.py` as the
  tested per-side benchmark. Evidence: `artifacts/runs/EXP-0022/` (`review.md`,
  `asym_nq.txt`, `asym_es.txt`); `experiments/hypotheses/HYP-0014.md`.
- `HYP-0013` is rejected (EXP-0021): recasting the per-slot dispersion as a QUANTILE
  (percentile) instead of the MEAN is a cross-market NO-GO. At MATCHED median width
  every quantile cell collapses onto the mean band — best matched q0.90 NQ ΔSharpe
  +0.032 / ΔnetR +1.4R, ES ΔSharpe +0.067 / ΔnetR +5.2R, both below the +0.10 gate
  → no Null C. DECISIVE diagnostic: the residual quant/mean by decision slot is ≈1.0
  everywhere (0.96–1.01) on both markets = the matched quantile is just the mean band
  RESCALED, no reshaping of the intraday profile → the per-slot |move| distribution
  SHAPE carries no info beyond its LEVEL; the mean is a sufficient statistic at fixed
  width. The only RAW-view "win" (q0.50, narrower than the mean → more trades, NQ
  netR 101.9 vs 91.2 / Sh 1.34) is the width/capacity dial (cf. k-multiplier WFO,
  EXP-0010/0012), not a quantile effect — it vanishes under matched width. SYNTHESIS
  with EXP-0020: neither a √t reshape (cone) nor a distributional reshape (quantile)
  adds risk-adjusted value → the noise-area dispersion is fully summarized by its
  per-slot LEVEL/width. Transform 2 of the recast programme; the remaining lever is
  transform 3 (anchor/symmetry, asymmetric). `core/bands.py::noise_bands_quantile`
  (tested). Evidence: `artifacts/runs/EXP-0021/` (`review.md`, `quant_nq.txt`,
  `quant_es.txt`); `experiments/hypotheses/HYP-0013.md`.
- `HYP-0012` is rejected (EXP-0020): recasting the noise area as an analytic √t
  DIFFUSION CONE (one causal per-session vol scalar × √(mfo/M), calibrated to the
  baseline's end-of-day width) is a cross-market NO-GO as a REPLACEMENT for the
  empirical per-slot mean-|move| band. It is WORSE, not equal: NQ ΔSharpe −0.101 /
  ΔnetR −1.4R / +705 trades / net pt-per-trade 3.159→2.530; ES ΔSharpe −0.125 /
  ΔnetR −7.5R / +436 trades. Real pass fails the primary metric → no Null C spent
  (standing rule). POSITIVE finding via the residual m(mfo)=emp/cone: on BOTH
  markets the empirical band is ~1.35–1.55× WIDER than √t in the first hour (mfo
  29–59), converging to 1.0 at the close → intraday displacement is SUPER-DIFFUSIVE
  in the morning (opening-vol bulge wider than a random walk); the end-of-day-
  calibrated cone is too narrow early, admits noisier morning breakouts and dilutes
  per-trade quality. The per-slot empirical SHAPE is load-bearing (specifically the
  morning) and transfers to the ES sibling = real tape structure, not machinery.
  Coverage: the cone recovers only 90 decision points (0.2%, mfo 209 ≈ 13:29 ET) on
  liquid NQ/ES — the Rule-9a `min_periods` deletion bites THIN markets
  (GC/YM/RTY), not indices. Retain `core/session.py::noise_bands`. The cone stays in
  `core/bands.py` as tested reusable machinery / the pure-diffusion benchmark; its
  super-diffusive-open residual shapes the next transforms (2 quantile, 3
  asymmetric). This is transform 1 of the user's 4-transform noise-area recast
  programme (cone → quantile → asymmetric; range/EWMA dropped by user). Evidence:
  `artifacts/runs/EXP-0020/` (`review.md`, `cone_nq.txt`, `cone_es.txt`);
  `experiments/hypotheses/HYP-0012.md`.
- `HYP-0011` is rejected (EXP-0019). Thesis (user): high vol -> checking the stop every
  bar causes whipsaw, so use an INTERVAL (15-min) check when volatile and the continuous
  (every-bar) stop when calm; on a prop account capped at 1-2 micro contracts you cannot
  size with vol, so the exit CADENCE is the substitute vol lever and the deployable metric
  is raw DOLLAR daily Sharpe at 1 contract (not ATR-R). Two parts: (1) FIXED cadence sweep
  filled the gap between the 30-min decision clock and every-bar and found a NON-MONOTONE
  interior optimum at ~15 min on the dollar metric (NQ Sh 1.14->1.29, ES 0.93->1.09), but
  the fixed-15 vs 30-min-decision Null C FAILED — ATR-R NQ +0.034 p=0.29 / ES +0.058 p=0.19,
  dollar NQ +0.113 p=0.064 / ES +0.120 p=0.097 (marginal, never <0.05); the entire dollar
  uplift is vol-era weighting (rule 19), it evaporates under ATR normalisation. (2) The
  CONDITIONAL cadence (causal intraday-to-date range vs trailing-14-session same-tod median;
  hi-vol->15m, lo-vol->1m) is DOMINATED by fixed cadences: NQ cond Sh$ 0.92 vs fixed everybar
  0.96 vs fixed cad15 0.97; ES 0.70 vs 0.69 vs 0.81. Null C cond-everybar (dollar): NQ real
  -0.042 vs null mean +0.032 p=0.7419 (22/30 beat real); ES real +0.017 vs null +0.082
  p=0.8387 (25/30). DECISIVE diagnostic: the null CENTERS POSITIVE and the real tape sits
  BELOW its own null on both markets = the EXP-0010/0012 variance-amplifier signature. The
  whipsaw mechanism is mechanically real but NOT information: whipsaw reduction is a
  volatility/path-geometry property the path-preserving Null C PRESERVES (diffusivity gate
  exact), so noise reproduces it and then some; the surviving NQ timing edge actually PREFERS
  the every-bar checks the conditioner removes in high vol. Retain the fixed continuous stop.
  Overlays added default-off: int-cadence exit_check in core/engine.py + engine2.py
  ("decision"/"every_bar" strings bit-exact preserved); cond_regime/hivol_cadence/
  lovol_cadence in core/engine2.py (cond_regime=None parity). Scripts: exit_cadence.py
  (screen), hyp_0011_exit_cadence.py (fixed null), hyp_0011_cond_cadence.py (conditional
  null). Evidence: `artifacts/runs/EXP-0019/` (cond_{nq,es}.txt, fixed_cadence_null_{nq,es}.txt).
- `HYP-0010` is rejected as deployable cross-market alpha (EXP-0018). Thesis: NQ and ES
  share the "noise area", so gate NQ entries on contemporaneous ES confirmation. On the
  common NQ∩ES set (3628 sessions) the PRIMARY `agree` variant (take the NQ signal only
  when ES has broken out of its own noise area the SAME direction) gives net daily Sharpe
  1.074 vs baseline 1.102 (uplift −0.029, fails the +0.05 gate) and cuts total net R
  ~25%. IMPORTANT contrast with GC EXP-0007: on NQ `agree` is NOT a rarity filter — it
  RAISES gross/trade (+5.302 vs +4.945), net/trade (+4.827 vs +4.470) and hit-rate
  (0.407 vs 0.380) while trading ~30% less, so ES confirmation genuinely concentrates
  per-trade quality (the user's "an NQ break with no ES break is noise" has real per-trade
  support). It just does not monetize: it is a turnover/capacity lever (day-net t 2.68 vs
  3.15, flat Sharpe), not risk-adjusted alpha. `gate` (ES in ANY breakout) ≈ `agree`
  because ES breakouts during an NQ signal are almost always same-direction (coupling).
  The softer `vwap` gate (user's "don't go long if ES is under its VWAP") is inert-to-
  harmful (gross/kept FELL) — the noise-area breakout, not ES's VWAP side, carries the
  info. `es_dir` (ES leads?) is worse (Sh 0.70) and `es_opp` genuinely negative (Sh
  −0.72, gross −0.51, no Rule-16 mirror-trap) so ES does not lead NQ. The only Sharpe-
  beater `disagree` (+0.105) fails its re-pairing null (200 draws, null center +0.0001,
  z=1.08, 14% of draws beat real) — null center ~0 rules out a pure rarity filter but the
  uplift is inside the null noise band and weaker than GC's already-marginal disagree
  (z=1.53); post-hoc family-of-6 on consumed history. Retain the unconditioned baseline.
  Overlay `ext_state`/`cond_mode` added default-off to `core/engine.py` (cond_mode=None
  parity verified: 2923 trades / 14454.25 gross). Evidence: `artifacts/runs/EXP-0018/`.
- `HYP-0009` is rejected as validated capital-allocation alpha, although it is
  a default-off future-shadow candidate. The frozen four-level gap/RVOL sizing
  schedule kept all 4,209 trades and improved real zero-day daily Sharpe from
  1.288 to 1.398, net R from 91.20 to 101.97, and max drawdown from 4.70R to
  4.42R at only 0.957x mean trade weight. Net-R uplift was positive pre-2023
  (+8.40R) and 2023+ (+2.38R). However, 30 paired full-pipeline Null C draws
  reproduced mean Sharpe uplift +0.074 (sd 0.045) versus real +0.111: z=0.81,
  with 30% of null draws at least as strong. Do not deploy or use this as an ML
  justification on consumed history; only future shadow can resolve the
  residual real-minus-null uplift. Evidence: `artifacts/runs/EXP-0017/`.
- `HYP-0008` is rejected: vetoing otherwise valid NQ breakouts when the
  overnight gap opposes the signal and signal-minute RVOL(90) is below 1.2
  raised real net R by +3.97R and daily Sharpe by +0.236, with positive deltas
  both pre-2023 and 2023+, but retained only 86.1% of trades and failed the
  paired full-pipeline Null C test. The null produced a larger mean uplift of
  +5.18R (sd 5.18; real-vs-null z=-0.23; 53.3% of draws beat real). The EXP-0015
  conditional bins therefore did not validate as predictive alpha; treat this
  fixed rule as selectivity/turnover and do not use it to justify XGBoost.
  Evidence: `artifacts/runs/EXP-0016/`.
- `HYP-0007` is rejected for unconditional ES production-default adoption, but
  confirms material execution utility for the frozen EXP-0012 `s0.5_y0.5` cell.
  At 0.25 tick/side, full-sample net R/Sharpe/maxDD improve from
  51.5/0.70/7.45R to 84.3/1.02/6.22R and trades fall 37%. The joint net-R and
  maxDD condition passes only 1 of 4 eras: drawdown worsens in 2020+ and 2023+,
  while both net R and drawdown worsen in 2025+. Full-sample cost resilience is
  strong (at 1 tick/side: +42.4R treatment versus -16.1R baseline), so retain the
  exit default-off as a forward-shadow/execution-cost lever, not alpha or an
  unconditional default. Evidence: `artifacts/runs/EXP-0014/`.
- The original local replication statistics are invalid as faithful-paper
  evidence because the decision clock and VWAP gate differed.
- Pre-fix Null C magnitude estimates are superseded for the current faithful
  configuration; preserve them as historical evidence, not the current verdict.
- `HYP-0001` is rejected: short lookbacks did not improve full-sample NQ
  performance (best nonbaseline ΔSharpe -0.065, p=0.8571) and ES's small uplift
  (+0.026) was not family-wise significant (p=0.1905). Evidence:
  `artifacts/runs/EXP-0008/`.
- `HYP-0006` is rejected for production adoption but is a qualified NQ-specific
  forward-shadow candidate. A fixed early-flat cutoff before the close: NQ best cutoff
  45 ΔSharpe +0.101 clears the Sharpe threshold but net R is −0.8 below baseline (fails
  the net-R gate) and maxDD is worse; ES all cutoffs hurt (net R +51.5→+43-44, best
  ΔSharpe −0.030) so the sign does not transfer. Unlike the looser-stop artifacts this
  is NOT tail truncation (top-decile winner-R preserved) — it reshapes late-session
  variance only, on NQ only. **Follow-up Null C (2026-07-20)**, run at user request under
  a variance-avoidance reframing (net-R PRESERVATION as control, not increase): NQ PASSED
  (real max ΔSharpe +0.101 vs null max mean −0.048, p=0.0323, 0/30 null draws beat real —
  the null centers NEGATIVE, so this is a real late-session-specific timing feature, NOT
  the "fewer trades → higher Sharpe" machinery that killed EXP-0010/0012). ES REJECTED
  (real −0.030 vs null +0.008, p=0.7419: noise beats the real tape). The user's pan-index
  structural thesis (3:45 MOC imbalance, passive-close rebalancing, 0DTE gamma — all ≥ as
  strong on the S&P) is FALSIFIED by ES: a pan-index cause would help ES as much or more,
  but ES inverts. So the surviving NQ effect is NQ-tape-specific, buys daily-dispersion
  Sharpe only (net R flat, maxDD WORSE), and concentrates in 2023+ (23+Sh 1.10→1.54) on
  consumed data. Forward-watch, do not bank historically, do not attribute to the
  MOC/rebalance/0DTE mechanism. `flat_before_close` default-off in `engine2` (parity
  verified). Evidence: `artifacts/runs/EXP-0013/` (`nullc_nq.txt`, `nullc_es.txt`).
- `HYP-0005` is rejected: a narrower noise exit band + looser (below-price)
  VWAP-sigma band does not validate. NQ best cell ΔSharpe +0.090 / ΔnetR +14.1
  MISSES the +0.10 gate (no null run per the standing rule); ES best +0.320 clears
  the gate but the family-max Null C reproduces +0.254 on noise (p=0.2903). The
  literal negative-y (tighter) grid was rejected on both markets first. This is the
  3rd looser-stop/fewer-trades "higher Sharpe" that Null C exposed as a
  variance/selectivity amplifier (after EXP-0010 VWAP-touch and the KAMA rarity
  filter): treat any "fewer trades → higher Sharpe" exit as machinery until Null C
  clears it. The looser exit is a turnover/capacity lever, not alpha. exit_band
  added default-off to `engine2` (s=1/y=0 parity verified). Evidence:
  `artifacts/runs/EXP-0012/`.
- `HYP-0004` is rejected: the paper's two-stage RR ladder exit (Table-2
  −1R/+2R → bank 50% → 0R/+5R, 1R = entry-frozen band distance) does not beat the
  `both` stop. NQ ΔSharpe −0.075 / ΔnetR −12.9 (fails +0.10 gate), loses to
  `tp1.0_50` by −0.131 Sharpe, Null C p=0.6129; ES ΔSharpe +0.014, Null C
  p=0.3226. The fixed −1R stop and +5R cap cut gross R (111→97), discarding the
  trailing stop's edge. Ladder added default-off to `engine2` (tests + parity
  verified). Retain `both`; keep `tp1.0_50`. Evidence: `artifacts/runs/EXP-0011/`.
- `HYP-0003` is rejected: the paper's flagship every-bar VWAP-touch exit
  (`stop_ref="vwap"`) does not beat the current `both` stop. NQ uplift ΔSharpe
  -0.031 (fails +0.10 gate), Null C p=0.8710; ES uplift +0.258 but Null C
  p=0.2903. The null-uplift mean is positive on both markets (+0.083 NQ, +0.178
  ES), so the looser stop is a variance/selectivity amplifier that lifts Sharpe
  as much on noise as on signal, not exit information. It does raise per-trade
  net R with ~27% fewer trades — a turnover/capacity lever only, never a Sharpe
  claim. Retain the `both` stop. Evidence: `artifacts/runs/EXP-0010/`.

## Decisions and constraints

- Preserve existing import paths and reports during migration to the standard
  project structure.
- TradingView VEI visualization: `pinescript/vei_rth_eth.pine` ports the
  session-reset short/long intraday ATR ratio with selectable SMA/Wilder/EMA,
  repaired or legacy exponential seed, optional final-ratio EMA smoothing, and
  independently reset 09:30--16:00 ET RTH and 18:00--16:00 ET ETH plots. Use a
  1-minute chart with electronic hours enabled; exact parity still depends on
  matching the research contract, roll treatment, OHLC feed, and session data.
- No historical period may be relabelled as sealed holdout after inspection.
- New strategy variants must use the audited engine and compare with the frozen
  faithful baseline.
- Routine ideas, hypotheses, experiment records, closeout, and hygiene checks use
  the shared `tools/research_admin.py` workflow.

## Known risks and open questions

- Obtain independent review of `EXP-0007` configuration and interpretation.
- Obtain independent review of the causal stop activation and cost treatment in
  `EXP-0009`; one-second OHLC still cannot resolve within-second path order.
- Quantify robustness to neighbouring parameters, costs, and post-publication
  regimes without treating searched variants as confirmatory evidence.
- Define the forward shadow start date and immutable observation protocol.

## Next actions

1. Review `EXP-0007`, `EXP-0008`, and `EXP-0009` independently.
2. Decide whether the 2023+ short-lookback regime observation belongs only in
   future shadow monitoring; do not optimize it further on consumed history.
3. Decide whether to enter a future-only shadow period or close the project.

## Promotion candidates

The clock and gate failures may become cross-project learnings after confirming
the same failure modes in another project. They remain project-specific here.
