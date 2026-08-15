# Shared Research Learnings

Verified lessons reusable across more than one project. Mandatory invariants live
in `RULES.md`; project status and project-only findings live in each project's
`MEMORY.md`. Detail lives in the linked reports — keep entries here concise.

**Entry criteria:** supported by code/data/a reproducible test; durable; useful
beyond its origin project; linked to evidence. Status ∈ {`confirmed`,
`provisional`, `invalidated`, `superseded`}; provisional items name the test to
confirm or kill them.

Entries are grouped by theme. Most are `provisional` (found on one project, often
four correlated FX pairs ≈ 2 effective, or an NQ↔ES pair) but each is
over-determined by controls or an arithmetic mechanism; the named cross-project
test would confirm. Dates tag the contributing runs.

---

## 1. Hidden selectors — any threshold that is a function of X is a selector for X

Unifying rule: **whenever a decision rule's threshold depends on something (a
clock, a window length, a regime), sweep that something as a placebo, and compare
rules at MATCHED selection rate in SCALE-FREE units.** Five independent routes into
this family, all confirmed by the same fix.

- **Session-reset feature → time-of-day selector** (2026-07-27). A window that
  resets each session (intraday ATR, running-VWAP distance, cumulative RVOL) drifts
  deterministically through the day, so a fixed cut selects wildly different
  fractions per slot (VEI>1.10 fired on 1.5% of 10:30 vs 18.4% of 15:30 decisions).
  **Fix: normalise against the trailing SAME-SLOT distribution with a Z-SCORE
  `(x−μ)/σ`, not a ratio-to-mean** (ratio removes per-slot location but not scale;
  selection-rate CV 0.93→0.05 for z vs 0.135 for ratio). Normalising did NOT destroy
  the information.
- **Estimator on a growing window → clock** (2026-08-03). A persistence estimate
  (AR(1)φ, Hurst, variance ratio) on an expanding/session-to-date window has a
  sampling SD that shrinks as the window grows, so a fixed cut selects a collapsing
  fraction — **the mechanism is the estimator's SD, not its level** (Hurst gate mean
  H moved 0.02 but SD compressed 3.8× across the session). Control: `signflip` (real
  |returns| with iid random signs) preserves vol seasonality, destroys memory.
- **Pooling a persistence stat across a deterministic profile → INFLATES it** (the
  opposite sign, same date). Slot-demean before pooling: a VEI AC1 of +0.44 fell to
  +0.20 (half was clock); an EMA variant's +0.16 went to ~0.
- **Scheduled signal clock → minute-of-hour selector** (2026-08-04, confirmed
  cross-vendor). A ":29" scheduled clock beat a first-crossing clock only because all
  its entries landed on one phase; crossings that also land on :29 tie it. **Control:
  rerun the scheduled clock at ALL phases of its interval** (:29 was rank 30/30). The
  proposed :00/:30 reversal mechanism is spot-FX-specific and open (absent on CME).
- **Regime-scaled threshold → regime selector** (2026-08-04). `|z| ≥ k·f(regime)`
  selects on the regime: a vol-scaled exhaustion cut "beat" a fixed one by +0.06 pip
  but lost by −0.24 at matched selection rate. **Write down which states the scaled
  cut selects MORE of before reading P&L**, and compare in R units, not pips (three
  rules with identical R-per-risk spanned 37% in pip means because each picked a
  different volatility).

- **A TRAILING ALL-HOURS vol window is the same selector, from the other direction**
  (2026-08-08, third independent route → the family is now CONFIRMED). A 4-week σ cannot
  see the intraday profile — on spot FX its median moved only 3.156→3.179 pips across all
  24 UTC hours — so every bit of real intraday size variation lands in `z` and a fixed
  `|z|≥2` cut fired on **0.96%** of 04:00 decisions vs **10.11%** at 14:00 (CV 0.707).
  The trap is that this σ *looks* like the conservative choice (long, stable, slow).
  **Diagnostic: `fire_rate` by slot, then its CV** — one line, and it should be run on
  every threshold rule before any conditional result is read. Same-slot z fixed it
  (CV 0.663→0.119, hourly 0.90–8.15% → 2.37–4.08%) and — as in the VEI case — **did not
  destroy the information: it IMPROVED it** (+0.041 R at matched trade count, 0.106 vs
  0.065, and the CI went from barely-excluding to clearly-excluding zero). Cost: it
  killed a session-localisation finding that the all-hours cut had made look significant.
  **Match rates by PICKING a threshold off a finely swept grid (step 0.02 got within
  1.2%), never by interpolating a frontier** — `np.interp` clamps.

Cross-cutting tool: **frontier-excess** (2026-08-04). Sweep the base parameter's one
threshold to get a (rate, mean-R) curve; score any arm as its excess over that curve
interpolated to the arm's own rate. Cheap way to rate-match gates whose rate you
can't dial. Settled two long-open questions: stacking RSI on |z| is negative at every
matched rate (they're the same variable, Spearman 0.97, zero direction disagreements);
four vol-regime gates were all inside the ±0.005 R no-effect band.

Evidence: `futures/nq/vei_exploration` (EXP-0009 §I; EXP-0008 §H), `futures/nq/estimator_bias`
(FINDINGS §A/§B/§C), `forex/exploration_1/RSI_{CLOCK_CONFOUND,THRESHOLD_FRESHNESS,Z_REGIME_MATRIX,GATE_NULL}_REPORT.md`,
`forex/exploration_4/reports/SAME_SLOT_ADDENDUM.md`.

---

## 2. Coverage, placebos & rolling-window construction (Rule 9a)

- **Placebos must be COVERAGE-MATCHED** (2026-08-05). Print the per-cell COUNT next
  to every placebo/phase/permutation stat and reject the comparison if counts move
  (a phase placebo faked a 3× effect from a coverage hole: 1,212 vs ~783 signals/yr).
  A statistic defined as **excess over a baseline measured in the SAME cell** is
  immune — it cancels nuisance shifts shared by arm and reference — but you must run
  the baseline inside every cell.
- **Bar-unit lookbacks multiply when you resample to coarser bars** (2026-08-05). A
  120-bar window becomes 600 minutes on 5-min bars and stops fitting between data
  gaps, nulling the whole Asia session. Keep lookbacks in TIME units when porting.
- **`np.interp` CLAMPS outside its range**, so a "rate-matched" comparison silently
  becomes an extrapolation against the shallowest baseline cell (2026-08-05). Assert
  every arm's rate lies inside the reference curve's range.
- **Strict `min_periods == window` on a same-slot rolling feature = a hidden,
  time-of-day-dependent liquidity filter** (2026-07-19, confirmed; re-seen on GC, YM,
  RTY, 6B, CL energy). One missing bar in the window nulls the feature and silently
  deletes that decision, concentrated in thin hours (up to 28% of GC's 15:29
  decisions; 0.0% of CL's rows survived a strict 63-session vol scale). **Fix: a
  fractional floor (2/3 or 0.9·window); report per-slot coverage — a silent null is a
  reportable finding, not an implementation detail.** Uniform post-fix coverage is the
  pass signal.
- **A rolling window counted in CALENDAR bins is unsatisfiable on a market that isn't
  always open** (2026-08-08). Spot FX covers ~71% of calendar minutes, so a 20-day σ
  window resampled to bins with a 0.9 `min_periods` floor can NEVER fill — σ came back
  NaN everywhere and the run produced zero signals. Count the window over the compacted
  series of TRADABLE bars: the bar count per grain is identical, the window then spans the
  same MARKET time at every grain, and `min_periods` degrades to a warm-up rather than a
  hidden time-of-day filter. Sanity check any "lookback in time units" rule against the
  instrument's actual session coverage before trusting it.
- **Estimate a seasonal normaliser on the full grid, read it at the events** — never
  estimate it from sparse events (2026-08-04). An event clock scattered a 90-session
  same-slot window to 3.5% coverage, and the survivors quietly reconstructed the
  round-clock schedule the change was meant to escape; full-grid estimation restored
  94.9%.
- **Apply a subgroup MASK after computing a rolling feature, not before** (2026-08-02).
  Masking the input first leaves a scattered subgroup (month-end) with an almost-NaN
  window that silently returns "too few events." Contiguous masks (eras) survive;
  scattered ones don't.
- **Pin a decision clock to the WALL clock, not minutes-from-open**, when the archive
  has minute-of-hour structure (2026-08-01) — otherwise a per-pair session-varying
  open silently deletes some pairs' decisions. Check whether a coverage gap has a
  fixed minute-of-hour signature (a download-chunk artifact) before reading it as
  microstructure.
- **A PADDED data vintage deletes exactly the events a session-boundary study is
  about, and it deletes them SILENTLY by making the boundary disappear** (2026-08-12,
  `provisional`; confirm on a second padded archive). Three of nine spot-FX archives
  carry **Saturday bars** — NZDJPY 181,699 of them, uniform across all 24 hours in
  2021-23, with weekday bars rising to exactly 1440/day against ~1400 elsewhere.
  Spot FX does not trade Saturdays, so that vintage is gap-filled. The trap is the
  failure MODE: a weekend gap defined as "the move across this series' own ≥24h
  break" found only 637/782 and 653/782 weekends on the padded pairs, because
  padding means **no break exists** — and the ~145 missing weekends were not random,
  they were precisely the padded era. **Diagnostic: count bars on days the market
  is closed, and bars-per-day by YEAR** (a step from ~1400 to exactly 1440 is the
  tell); a uniform-across-all-24-hours histogram on a closed day is fabrication, a
  high zero-range fraction is stale padding. **Fix: derive one canonical session
  calendar from a clean archive and impose it on every instrument**, snapping each
  to its own nearest real bar with a recorded tolerance. This also removes a
  confound that exists even with clean data — otherwise pairs are compared on
  slightly different session windows. Reassuring check afterwards: the six CLEAN
  archives carried the effect more strongly (+0.356, t 4.52) than the three padded
  ones (+0.177, t 1.87), i.e. padding dilutes rather than manufactures.
- **A delayed-entry (boundary-artifact) control must hold the HOLDING PERIOD
  constant, or it silently becomes a horizon sweep** (2026-08-12, `provisional`).
  Anchoring the exit at `event + h` while sweeping entry delay `d` shortens the
  trade by `d`; at `h=60min, d=60min` the trade had **zero duration** and the
  control read as a total collapse of the effect. Anchor exits at `entry + H`
  instead. The distinction is invisible at long horizons (a 60-min delay costs 4%
  of a 1-day hold) and fatal at short ones — which is exactly where boundary
  artifacts live, so the control is broken precisely where it is needed.

Evidence: `forex/exploration_1/RSI_FIVE_MINUTE_CLOCK_REPORT.md`, `futures/gc/noise_vwap/reports/DATA_QUALITY.md`,
`forex/exploration_1/RSI_COHERENCE_TIMEEXIT_REPORT.md`, `futures/forex/vwap_exploration` (EXP-0003, EXP-0001),
`forex/exploration_4/reports/DATA_QUALITY.md`, `forex/exploration_7/reports/DATA_QUALITY.md`
+ `artifacts/runs/EXP-0002/review.md`.

---

## 3. Degenerate controls — score the variant that removes the thing under test

- **Never select a RATIO on a metric its own NUMERATOR maximises; score the bare
  numerator** (2026-07-27, confirmed). As the denominator's memory grows the ratio
  degenerates into a rescaled numerator; if the numerator predicts the target the
  metric rewards variants *for ceasing to be ratios* (`IC = 0.89·corr(variant,level)`,
  R² 0.992; the no-denominator ATR won outright). Partialling the level out is only a
  partial repair — change the target instead. Corollary: `log(implied)−log(realised)`
  is mostly its denominator when the numerator is slow-moving (spot VIX barely moves
  over a 30-min clock; the "variance premium" was −0.85 correlated with realised vol
  alone).
- **To test whether missing DATA binds, score the variant that uses NONE of it**
  (2026-08-01). A volume-free stop matched the VWAP-anchored rule on 8/8 cells, so
  missing FX volume was never the constraint — without that arm the plausible, wrong
  next step was building volume proxies.
- **The degenerate control for an ANCHOR study is NO ANCHOR** (2026-08-02). Fading the
  trailing return (no anchor, no volume) beat VWAP/TWAP/open/prior-close by 1.5–8×;
  the anchor is a noisier proxy for short-horizon reversal. On CME FX futures VWAP and
  TWAP genuinely differ (real volume) and it still doesn't help.
- **Benchmark a new EXTERNAL data source against the cheapest INTERNAL column you have
  not yet used** (2026-07-31). Trailing realised vol (one existing column) beat three
  engineered features off an external VIX feed before taking a production dependency.

Evidence: `futures/nq/vei_exploration` EXP-0008, `forex/noise_vwap`, `futures/forex/vwap_exploration`,
`futures/nq/vei_exploration` EXP-0017.

---

## 4. Estimand & weighting

- **When SIGNAL COUNT is endogenous to the outcome, per-signal and block-averaged
  estimands disagree in SIGN** (2026-08-01, confirmed on 3 asset classes). GBPUSD
  per-signal +0.01 pip vs session-averaged −9.66 (t −16.7); the flagship NQ strategy's
  own entry even "loses" under session averaging. **Detect with `corr(block mean,
  block count)` — read its MAGNITUDE, not sign** (it manufactured t≈16 at both +0.41
  and −0.46). Block-averaging looks conservative and is the more dangerous trap. Use
  the **per-signal mean with a block cluster-robust SE**.
- **Rank IC and MEAN quintile spread can give OPPOSITE readings** (2026-07-31). GC had
  significant rank reversion with no expectancy; NQ/ES had no rank momentum but real
  positive expectancy — because **equity intraday momentum lives in the TAILS** and a
  rank stat weights the median. This is why a breakout rule works on NQ where a
  momentum tilt doesn't. Report both; say which the decision consumes (equal-risk
  sizing → mean).
- **An UNCONDITIONAL serial-dependence statistic and a CONDITIONAL-extreme one can rank
  timescales in OPPOSITE order** (2026-08-08). On 4 USD-major spot FX the variance ratio
  DEEPENS with horizon (VR 0.948 at 5m → 0.869 at 120m, Lo–MacKinlay robust z −12 to −15,
  VR<1 in every session and every pair) while `E[fade R | |z|≥2]` SHRINKS with it (0.190R
  at 5m → 0.000R at 120m — same ordering on the maximal sample, so not coverage). Both are
  right: VR is unconditional and LINEAR, so it prices the AVERAGE move's serial dependence,
  not reversion from an extreme to an anchor. **Never pick a decision grain from VR alone**;
  and use the heteroskedasticity-robust z, because vol clustering inflates the estimator's
  SE without moving its point estimate. Same family as the rank-IC vs mean-spread split
  above: name the object the decision consumes, then measure THAT one.

Evidence: `forex/noise_vwap` FINDINGS §B–E, `futures/nq/claude_exploration_1` §B,
`forex/exploration_4/reports/MARKET_CHARACTERIZATION.md`.

---

## 5. Nulls & controls

- **Bar-shuffle nulls are INVALID for barrier/path-dependent strategies** — reordering
  whole bars destroys diffusivity (printed +0.27R at t=31 on pure noise). Use a
  path-preserving RETURN shuffle; the maintained references are
  `futures/nq/noise_vwap/core/nulls.py` and `futures/vwap_mean_version/core/nulls.py`.
- **Pin artificial opening sentinels in a return-shuffle null** (2026-07-18,
  confirmed). Including `link[0]=0` in the permutation then re-anchoring discards a
  real link and changes the session net move. Test opening anchor, net move, atom
  multiset, and a path-continuity stat across seeds before reading the P&L.
- **A single-market Null C pass does NOT validate a cross-market mechanism — the
  sibling market is the mechanism test** (2026-07-20, confirmed). NQ's early-flat
  cutoff passed its null but ES inverted, falsifying the pan-index MOC/0DTE story.
  **The SIGN of the null center is the machinery discriminator:** positive =
  fewer-trades variance amplification (reject); negative = the effect is genuinely
  tied to the thing being cut.
- **A side-folded feature (`side·X`) must be permuted WITHIN (slot, era, SIDE)**
  (2026-08-05). Otherwise a large partner value flips sign across trade side,
  scrambling the feature's marginal and distorting the null-max. Assert the
  firing-rate invariant in code and don't read the null until it passes (it caught the
  bug here).
- **When the statistic is an EXCESS over an informative baseline, its null does NOT
  centre at zero** (2026-08-04). "Real beats null" only says the gate carries info;
  "excess > 0" says it beats just deepening the base parameter (the deployment bar).
  Report null center, baseline, and real value as three numbers. When selection
  occurred, compare the real MAX over the reproduced search to the null distribution
  of MAXIMA.
- **Score an argmax agreement rate against the MODAL-CATEGORY base rate, not a uniform
  null** (2026-08-03). "Predicted cell won on 3/3" looked like p≈1/64 but the modal
  block wins 71% of units, so expected hits = observed = zero information.
- **A synthetic-injection power check must inject into a DE-MEANED series, or it
  measures real+injected and reports absurd sensitivity** (2026-08-12,
  `provisional`). Injecting `m` on top of the effect already present made a
  weekend-gap study report a minimum detectable effect of **0.05 sigma** when the
  true MDE was **0.58 sigma** — an order of magnitude wrong, and wrong in the
  dangerous direction (it certified the measurement as sensitive enough to trust a
  null). For a simple mean the whole thing collapses to one line: **MDE ≈ 2 × the
  cluster-robust SE**, so compute that first and only build an injection harness if
  the estimator is not a mean. The tell that something was off: the study's headline
  effect (0.53) was *below* its claimed MDE yet had t=1.85 — if a "detectable"
  effect isn't significant, the MDE is wrong. Pairs with the positive-control gate
  above: that gate proves the measurement can see a KNOWN effect, this one prices
  how big the effect must be.
- **For two autocorrelated series on a cyclical index, use a CIRCULAR SHIFT, not a
  label shuffle** (2026-08-03) — a free permutation destroys the autocorrelation and
  is anti-conservative.
- **A conviction score / supervised model cannot manufacture orthogonality that isn't
  there** (2026-08-07). After a per-axis search found every conditioner redundant with
  one base lever (|z_twap| depth), both a hand-built orthogonal score and a
  purged/embargoed GBT (OOF AUC ≈ 0.51) LOST to ranking by depth at matched trade
  count. Traps: use a matched-COUNT direct benchmark, never a frontier-interp (which
  clamps and flatters); SEED-SWEEP any tree top-bucket "win" (a +0.02 top decile came
  from an AUC-0.507 model and swung −0.038→+0.072 across seeds). Sanity check: a model
  on the base lever alone should ~tie the direct base ranking.
- **A small-n guard that returns NaN feeding a comparison that treats NaN as a pass**
  prints false significance (2026-08-03) — `NaN <= NaN` scored as p=0.0000 on all
  units. Guards that degrade to NaN are only safe if every downstream comparison
  treats NaN as a FAILURE. **Re-seen 2026-08-11 in a placebo family**: a degenerate
  anchor with a handful of date clusters printed |t| = 1.4e16, and because
  `NaN >= real` is False the NaN cells silently counted as "did not beat the real
  arm" — i.e. the guard made the test EASIER to pass. Drop unusable cells from the
  null explicitly and REPORT the count; never let them sit in the comparison.
- **A NULL RESULT IS UNINTERPRETABLE WITHOUT A POSITIVE CONTROL** (2026-08-11,
  `provisional`; confirm the second time a diagnostic's null is read). "X carries no
  information" and "my measurement cannot see information" are the same output. So
  before reading a null, run the identical code path on a case where the effect is
  KNOWN to exist and show it is detected. On an FX session-anchor sweep the control
  (NQ's real 09:30 cash open, which the sibling project proves is load-bearing)
  **FAILED on the first execution** — which located a construction bug in the sweep,
  not a fact about FX. Declare the control as a VALIDITY GATE in the preregistration
  with "control fails ⇒ INCONCLUSIVE, fix the method", because that converts the
  most likely way to fool yourself into a routine, non-negotiable step. Corollary:
  the control also CALIBRATES the effect size — the real NQ anchor stood **≈21×**
  above its placebo family's median effect while FX's best stood ≈2.3×, which is a
  far more legible discriminator than either t-stat alone.
- **When porting a session-anchored construct, match the DECISION UNIVERSE, not just
  the anchor** (2026-08-11, `provisional`; confirm on a second port). The identical
  NQ 09:30 anchor scored cluster-t **+3.68** on its native 390-min RTH session and
  **+1.60** when forced to a 1425-min all-hours session — same instrument, same
  anchor, same code, only the session length differing. Spreading decisions across
  hours the construct never claimed to work in dilutes the structure the anchor
  organises, and it will suppress a real effect and fake a null.
- **`Series.astype("int64")` on datetimes returns the integer in the dtype's UNIT,
  and this workspace MIXES units across instruments** (2026-08-11). `forex/data/**`
  is `datetime64[us]`; `futures/nq/data/**` is `datetime64[ns, UTC]`. Both hold
  exact whole-minute values (0 of 5.54M EURUSD rows have a nonzero second or
  microsecond) — this is a STORAGE-unit hazard, not data precision, which is why it
  reads as harmless. A hard-coded `// 60_000_000_000` was therefore right on the NQ
  control and wrong by 1000× on FX, collapsing 576,000 distinct minutes onto 577
  colliding values. **The danger is that it is instrument-dependent inside ONE code
  path: correct on the positive control, broken on the subject** — the exact
  configuration that would have validated a method and then fed it garbage. Divide
  by a `pd.Timedelta` (exact at any unit) and assert index uniqueness after
  building it. Check `df[ts].dtype` when a loader spans two data sources.
- **A PERSISTENT/stateful rule cannot be controlled by a ONE-SHOT filter — randomise
  the STATE TRANSITION, not the trade list** (2026-08-11, `provisional`; confirm on a
  second stateful rule — a cooldown, a hysteresis latch, a regime lock). A re-entry LOCK
  ("after a stop, block this side until condition X") re-fires at every later decision
  bar while it stays armed, so it is not equivalent to any set of blocked entry keys.
  Two control failures in one run: (1) matching on the number of times the lock FIRES
  overshoots badly — one blocked key removed only **0.586** trades (the engine re-enters
  at the next checkpoint), so the "matched" random arm cut ~666 trades against the rule's
  430 and was flattered in a book where fewer trades mechanically raises Sharpe.
  **Calibrate to reproduce the treatment's TRADE COUNT and print the achieved count.**
  (2) Even corrected, the control went **degenerate at K == pool**: matching a persistent
  lock's exposure required 100% of the candidate pool, so all 200 draws were the same
  deterministic blocklist, sd=0.0000 — and it printed **frac=0.000**, which would have
  read as the run's strongest confirmation. Blocking the whole pool once still removed
  only ~153–310 trades vs the lock's 395. **Fix: keep the state machine, randomise only
  its TRIGGER** — same arming, side-scoping, cadence and persistence, but release on a
  coin flip at a hazard bisected to match the trade count. Decisive and well-powered: it
  centred at ~0 (random release is worth nothing) while the real condition scored +0.117
  NQ / +0.224 ES, frac 0.005/0.000. Generalises the NaN-guard trap above: **a control
  with sd==0 is not a null — assert non-degeneracy before reading any frac.**

Evidence: `futures/nq/noise_vwap` (EXP-0013, EXP-0043), `forex/exploration_1` (cointegration
null, gate null, conviction/supervised reports), `futures/forex/vwap_exploration` EXP-0007,
`forex/noise_vwap/artifacts/runs/EXP-0003/review.md` (positive control, NaN-in-null,
decision-universe and datetime-resolution items).

---

## 6. Fills & bar resolution

- **A 1-minute gross edge on a TP/SL bracket can be a coarse-bar fill artifact**
  (2026-07-19, confirmed). 1m OHLC can't order an intrabar stop-vs-target touch;
  re-running on 1s exposed stop-first paths and collapsed a GC fade from Sharpe +0.57
  to +0.08. **If the win rate sits at the algebraic break-even `1/(1+RR)`, the barriers
  are efficient and there is no edge.** 1m flatters brackets whose stop is nearer than
  the target.
- **A whole-BAR execution delay is NOT a latency model** (2026-08-06). A 60s (one bar)
  delay overstated the real ~1.5s market-order fill cost by ~10×. Sub-second fill decay
  is FRONT-LOADED (first ~5–15s) then plateaus, so measure the cost at the latency you
  will actually run. **A MID-only fine-bar test settles TIMING, not SPREAD** — report
  the timing haircut and the spread as two separate charges; a clean fill result is not
  permission to drop the cost floor. Fine-bar coverage is biased against the illiquid
  signals you most need to check.
- **A shared decision-bar close manufactures reversion** (2026-07-31). `past` ends and
  `fwd` starts at the same close, so pricing error enters with +1 and −1; lagging the
  past window by one bar removed 31–56% of measured reversion at 5 min (up to 87% at a
  30-min horizon on 6B — the artifact does NOT shrink with horizon). Enter at
  `open(m+1)`, not `close(m)`.
- **`mean(open[i] == close[i-1])` is the one-line test for whether that artifact is
  even possible** (2026-08-08, second asset class → CONFIRMED). On the spot-FX midpoint
  archive it is **99.99998%** of contiguous minutes, so "enter at the next bar's open"
  does NOT separate the windows — the entry price is the same NUMBER that ends the
  displacement. A PAIRED one-bar delay (identical signal set, screened on the same span,
  not two separately filtered samples) removed **56–78%** of the measured conditional
  reversion, paired t=−12.2 at n=112k. Run the check before designing the study, not after:
  it decides whether `open(m+1)` is a real fix or a cosmetic one. What survived was still
  real at the finest grain and zero at τ≥60min.
- **A CONDITIONER correlated with the boundary noise inherits the shared-close artifact
  and masquerades as a real effect** (2026-08-09, `provisional`; confirm on a second
  conditioner or asset). Testing whether *volume* confirms a move (high-vol → continue,
  thin move → reverse) on spot FX + CME-futures volume, EURUSD showed a dir-return spread
  of +1.49 pips (day-clustered t=4.21) among |z|≥2 displacements. A **paired 1-bar
  embargo** (enter `open[t+2]`) removed **~84%** of it (t→0.70); post-embargo all 4 USD
  majors were insignificant AND sign-disagreed. Because volume co-moves with the size of
  the shared-close pricing error, the artifact's manufactured reversion sorted on the
  conditioner and looked like a volume edge. **Run the paired embargo BEFORE reading any
  volume/vol/size-conditioned continuation result.** Post-embargo the residual directional
  IC(volume, dir) was ≈ −0.008 (sub-pip, gone by τ≥15min); the only robust signal was
  volume→forward-|move| (IC +0.084) — magnitude, not direction (name the object the
  decision consumes, §4). Two-sided slot-z normalisation is anti-conservative, so this
  null is strong. Evidence: `forex/exploration_6/reports/FINDINGS.md`.
- **A fixed-PIP slippage charged against VOL-UNIT barriers is a grain selector**
  (2026-08-08). With TP=SL=1.0σ_τ and 1 pip adverse stop slippage, the realised mean loss
  exceeded the nominal 1.0R stop by exactly `slippage/σ_τ` at all five rungs (0.327 vs
  0.316 at τ=5min … 0.063 vs 0.064 at τ=120min, agreement within 0.011R). So a
  profit-factor / expectancy comparison ACROSS grains is mechanically biased against fine
  grains, and its ranking is uninterpretable (here it inverted the conditional view's).
  Rule 19 in its sharpest form: **charge slippage in σ units when comparing grains, or
  compare only at matched σ.** The ABSOLUTE reading (PF<1 everywhere) still stands. Tell:
  a win rate ABOVE the algebraic break-even `1/(1+RR)` alongside negative expectancy means
  the asymmetry is in the fill charge, not the barriers.
- **A passive level-retrace exit's entire edge can be the touch-vs-fill assumption when the
  retrace TARGET is also the reversal point** (2026-08-09, `provisional`; confirm by
  re-running on a second retrace-target family — VWAP or prior-close — or with L1 quote data).
  A spot-FX z-fade whose exit is a limit at the pre-displacement anchor prints **≈+0.35 gross
  pips** if a bare TOUCH of the anchor is credited as a fill, but **≈−0.17 (CI includes 0)** once
  the fill requires trading THROUGH the anchor by a vol-scaled guard of 0.25·σ — same entries,
  same paths, fill still credited AT the anchor (Rule 1). Trade-by-trade the both-fill and
  both-timeout cells are identical; the whole ~0.5-pip swing is a **~2.6% marginal band** where
  price reverts *just* to the anchor and reverses, so touch books +7.6 pips and the guarded arm
  misses and times out at −12.1. (Robust to the deployable one-position estimand.) The reversion completes to the level and stalls there — the
  level is resistance — so a touch is not a fill (Rule 4) in the strongest way: crediting it
  manufactures the edge. Diagnostic: report a **touch (g=0) ceiling, a guarded (g·σ) book, and a
  time-exit floor** side by side; if the edge lives only at g≈0 it is not capturable. A pure
  fixed-horizon/time exit reproduces the touch number (both credit the level implicitly), so a
  fixed-horizon "reversion" result is NOT evidence a passive exit can harvest it.

Evidence: `futures/gc/vwap_reversion` EXP-0000, `forex/exploration_1/RSI_FILL_MODEL_REPORT.md`,
`futures/nq/claude_exploration_1` §G, `futures/forex/vwap_exploration`,
`forex/exploration_4/artifacts/runs/EXP-0002/review.md` §2/§4,
`forex/exploration_4/reports/STAGE_B_REFERENCE_BOOK.md` + `artifacts/runs/EXP-0004/review.md` §3.

---

## 7. Cross-market transfer & conditioning (Noise-VWAP family)

- **Transferability spans a full range and can fail at the GROSS level** (2026-07-19,
  confirmed). NQ (strong intraday drift) works → ES weaker → GC/YM cost-fragile → RTY
  no gross edge at all (its naive always-long drift is also negative). **Read the gross
  number and the always-long drift control FIRST**; a negative gross is a clean NO-GO
  no exit/sizing tweak rescues. The equity-index label does not guarantee transfer.
- **"Edge localised to a co-market's session hours" ≠ "edge follows that market's
  direction"** (2026-07-19, confirmed). GC's edge lives only in equity RTH, but
  conditioning GC direction on ES state DESTROYED it. **Read gross-per-trade on the
  KEPT trades:** rising = real info; falling = a rarity filter selecting worse trades.
  Don't flip a negative conditioner whose gross≈0 — the loss is cost, and the flip
  keeps the cost (Rule-16 mirror trap, cost form).
- **Cross-market same-signal confirmation is a quality/turnover lever, not alpha**
  (2026-07-20, confirmed). On a tight pair (NQ↔ES) confirmation genuinely raises
  gross/trade and hit-rate, but total net R falls ~25% and daily Sharpe stays flat —
  better selection + less exposure = no risk-adjusted gain. The only Sharpe-beater
  (`disagree` filter) failed its re-pairing null with the null centred at ~0 =
  consumed-history screen, not an edge.
- **An IMPORTED rule's benefit can be entirely redundant with a fix your baseline
  already has — re-test it on YOUR baseline, and sweep the baseline choice it
  interacts with** (2026-08-11, `provisional`). An external "require_reset" re-entry
  lock (block same-side re-entry after a stop until price returns inside the noise
  band) reproduced its author's reported gain on THEIR configuration (+0.117 NQ /
  +0.224 ES, and it survives a matched random-unlock null at frac 0.005/0.000) yet was
  worth **−0.011 / +0.003** on the same code with the stop checked every minute instead
  of 12×/day. The two are SUBSTITUTES: a slow stop lets price run outside the band, so
  the breakout is still true at the next checkpoint and the engine re-buys the failed
  move; a fast stop exits before that state forms. Tell: the trades the rule removes are
  LOSERS under the slow stop (−0.012 R) but PROFITABLE under the fast one (+0.010 R) —
  **the sign of the removed-trade expectancy flips with the baseline**, so read it before
  reading the Sharpe. Corollary: when importing any overlay, the first sweep is the
  baseline parameter it is implicitly compensating for.
- **Continuous/every-bar stop value scales with the drift/noise ratio** (2026-07-19,
  confirmed). It shrinks the loser tail identically everywhere but clips winners:
  NQ +0.145 Sharpe (GO), ES wash, GC inverts (−0.52). Never transfer an exit upgrade
  across instruments without re-measuring gross AND net per instrument. Extension-
  BANKING exits (partial-TP) are safe-but-weak on noise-dominated markets where
  stop-TIGHTENING is actively harmful.
- **The noise band is fully summarized by its per-slot SYMMETRIC level/width**
  (2026-07-20, confirmed, programme exhausted). A √t cone (worse — the morning is
  super-diffusive, ~1.4× wider than a random walk), a quantile reshape (inert — the
  mean is a sufficient statistic at matched width), and an up/down asymmetric band
  (inert-to-harmful — the asymmetry just restates the drift the strategy already
  monetizes) all add nothing. Method: split any "new dispersion statistic" test into a
  RAW view (shows the width dial) and a MATCHED-WIDTH view (isolates shape).
- **A cross-pair DIVERGENCE gate is the one conditioner orthogonal to the own-pair
  vol/directional axis** (2026-08-05) — but null-fragile. Own-pair "directional
  structure" estimators (efficiency, ADX, Hurst) are mutually correlated restatements
  of one axis; switch to a CROSS-instrument relative-value feature for orthogonality. A
  cross-instrument conditioner is inherently DIRECTED: apply it to the error-correcting
  (follower) leg identified a-priori from cointegration dynamics (NOT the P&L, NOT
  liquidity — the follower can be the most liquid leg). Keep divergence (signed level)
  distinct from coherence (comovement magnitude, which was dead here).

Evidence: `futures/{ym,rty}/noise_vwap`, `futures/gc/noise_vwap` (EXP-0002/0004/0006/0007),
`futures/nq/noise_vwap` (EXP-0013/0018/0020-0022), `forex/exploration_1/RSI_{COINTEGRATION,DIRECTED_COINT}*`.

---

## 8. Event studies

- **Check your MEASUREMENT window against the INSTITUTIONAL window** (2026-08-02). An
  entry 30 seconds inside the WM 16:00 fix's own averaging window "measured" a +1.5 pip
  edge that was the event, not a reaction. **Two one-line controls:** an entry-lag sweep
  (move entry one minute past the window → it dies) and a holding-horizon sweep at
  fixed entry (a 30-min result that is entirely its first minute isn't a 30-min result).
- **A preregistered arm that fails BACKWARDS is more informative than three that pass**
  (2026-08-02). A dated structural break (the 2015 fix-window widening, meant to shrink
  the effect) inverted it instead — which located the measurement bug. When an arm fails
  backwards, look for what flips its sign; check the construction first.
- **Derive an event clock from the event's OWN timezone with real DST** (2026-08-02) —
  hardcoding 11:00 ET for a London 16:00 fix misfiled 6% of sessions and understated a
  result by 35%.
- **A cross-sectional PANEL is a usable holdout for a pattern read off inspected data**
  (2026-08-03). A home-market mechanism that fit 3/3 markets died wrong-signed on 4
  fresh CME FX contracts (pooling all 7 would have shown a soft, surviving −0.07).
  **Declare a fresh-vs-consumed split in advance; add the panel members at the ENDS of
  the predictor's range** (an extreme counterexample beats several near-duplicates).

Evidence: `futures/forex/vwap_exploration` (EXP-0003 §E/§F, EXP-0007 §H/§K).

---

## 9. Algebra, predictor stability & inference

- **Ask how much of a result is ALGEBRA before you read it** (2026-08-03). A
  trend-following closed form matched realised P&L to 4e-17 — so it IS the backtest, and
  its +0.87 cross-product screen was algebra (OOS +0.03). **Print
  `Spearman(predicted, realised)` above the headline; ~1 means the comparison is an
  identity that only tests whatever differs between the two arms. A re-pairing null
  cannot detect an identity.**
- **The unnamed failure mode: a STABLE predictor of an UNSTABLE target** (2026-08-03).
  Realised trend P&L has ZERO year-to-year rank persistence while the predictor's is
  +0.71 — the worst combination, a confident smooth ranking uncorrelated with next
  year. **Compute both persistences BEFORE building any screen;** if the target's is
  ~0, no estimator can help.
- **Bootstrap the DIFFERENCE against a degenerate no-theory benchmark, not the statistic
  against zero** (2026-08-03, now second-project confirmed → standard). Also: a
  percentile CI that doesn't bracket its own point estimate is biased — read as "no
  evidence," never a signed result.

Evidence: `futures/panel/trend_closedform` FINDINGS §A–§H.

---

## 10. Lead-lag, regime splits & forward-looking inputs

- **For any lead-lag claim, run the REVERSE direction first** (2026-07-31). It is one
  line and beats staleness controls, horizon surfaces and sibling splits combined: a
  genuine lead is ASYMMETRIC; a symmetric "each predicts the other" is shared/
  non-synchronous contemporaneous info (gold "led" the dollar 2.4× more than the
  reverse). Read the contemporaneous link for scale (~75× the lagged one).
- **Match a regime split on VOLATILITY, not just time-of-day** (2026-07-31). Almost
  every intraday label carries a vol gradient; a coherence contrast of +0.05 collapsed
  to −0.005 when split within vol quintiles as well as slots. Always run the MIRROR arm
  (the other label conditioned on this one). A modest pairwise label correlation does
  NOT imply the cells they select are matched.
- **A forward-looking input can be an ANCHOR, not an anticipator — check WHERE it pays**
  (2026-07-31). Intraday VIX helped a vol forecast on every aggregate stability check,
  but the gain was monotone DECREASING in the implied/realised premium and WORST in the
  FOMC window (the one cell its stated mechanism required). It anchors an
  over-extrapolating past-price model after a vol spike. **Pick the cell where the
  assumed mechanism MUST fire and name it before the run; prefer a mechanism prediction
  that is ASYMMETRIC across markets** (ES > NQ for an SPX-native input held).

Evidence: `futures/nq/claude_exploration_1` §C/§E, `futures/nq/vei_exploration` EXP-0017.

---

## 11. Estimators — smoothers & warm-up

- **Compare smoothers at matched effective MEMORY (centre-of-mass), not nominal n**
  (2026-07-26, confirmed). Wilder (`α=1/n`) has com `n−1`, twice an SMA(n)'s — so
  `sma(10,50)` vs `wilder(10,50)` changes form AND memory, and memory is the bigger
  lever (a com-matched SMA reversed the "Wilder wins" conclusion). Wilder `α=1/n` IS
  `ewm(span=2n−1)`, so a "Wilder vs EMA" row is the same recursion at two alphas.
- **`ewm(adjust=False, min_periods=n)` is NOT textbook Wilder ATR** (same date). It
  seeds at the first observation and only masks the first n−1 outputs. Harmless as a
  one-off burn-in, but **a feature that RESETS each session pays it every session** — a
  slowly-decaying common component that inflates apparent autocorrelation (0.55→0.44 on
  repair) and injects a time-of-day gradient later studies read as signal. Repairing it
  shrank that project's headline finding past its own kill test. Seed with the n-bar SMA
  or set `min_periods ≈ 2n−1`.
- Small-sample AR-bias is a NON-ISSUE for this workspace's inference (max |bias| 0.0003
  at the pooled T≈44k used for headline stats) but a real FEATURE-CONSTRUCTION problem
  at T=13–30. The analytic corrector `−(1+3φ)/T` fails below T≈20 — use a parametric
  bootstrap and run two independent correctors (their disagreement is the only tell).

Evidence: `futures/nq/vei_exploration` (EXP-0006, A_smoothing), `futures/nq/estimator_bias`.

<!--
Entry format for a NEW standalone lesson (fold into a theme section above when it fits):

### YYYY-MM-DD — Short title
- Status / Applies to / Learning (one atomic statement) / Evidence path / Consequence
-->
