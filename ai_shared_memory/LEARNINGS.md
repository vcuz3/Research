# Shared Research Learnings

Verified lessons reusable across more than one project. Mandatory invariants live
in `RULES.md`; project status and project-only findings live in each project's
`MEMORY.md`. Detail and the supporting numbers live in the linked reports — keep
entries here to the actionable rule plus a pointer.

**Entry criteria:** supported by code/data/a reproducible test; durable; useful
beyond its origin project; linked to evidence. Status ∈ {`confirmed`,
`provisional`, `invalidated`, `superseded`}; provisional items name the test to
confirm or kill them. Most items are provisional (found on one project — often
four correlated FX pairs ≈ 2 effective, or an NQ↔ES pair) but over-determined by
controls or an arithmetic mechanism.

---

## 1. Hidden selectors — any threshold that is a function of X is a selector for X

Unifying rule: **whenever a decision rule's threshold depends on something (a
clock, a window length, a regime), sweep that something as a placebo, and compare
rules at MATCHED selection rate in SCALE-FREE units.** The family is CONFIRMED via
several independent routes:

- **Session-reset feature → time-of-day selector.** A window that resets each
  session (intraday ATR, running-VWAP distance, cumulative RVOL) drifts through
  the day, so a fixed cut selects wildly different fractions per slot. Fix:
  normalise against the trailing SAME-SLOT distribution with a Z-SCORE `(x−μ)/σ`,
  not a ratio-to-mean (ratio removes per-slot location but not scale). Normalising
  does not destroy the information.
- **Estimator on a growing window → clock.** A persistence estimate (AR(1)φ,
  Hurst, variance ratio) on an expanding window has a sampling SD that shrinks as
  the window grows; a fixed cut selects a collapsing fraction. The mechanism is the
  estimator's SD, not its level. Control: `signflip` (real |returns|, iid signs).
- **Pooling a persistence stat across a deterministic profile INFLATES it**
  (opposite sign). Slot-demean before pooling.
- **Scheduled signal clock → minute-of-hour selector.** A ":29" scheduled clock
  can beat a first-crossing clock only because its entries all land on one phase.
  Control: rerun the scheduled clock at ALL phases of its interval.
- **Regime-scaled threshold → regime selector.** `|z| ≥ k·f(regime)` selects on
  the regime. Write down which states the scaled cut selects MORE of before reading
  P&L, and compare in R units, not pips.
- **A trailing ALL-HOURS vol window is the same selector from the other
  direction.** A long/stable σ cannot see the intraday profile, so all real size
  variation lands in `z` and a fixed cut fires at wildly different rates by slot.
  It *looks* conservative (long, slow) — that's the trap. Same-slot z fixes it and
  IMPROVES the information.

**Primary diagnostic: `fire_rate` by slot, then its CV** — one line, run on every
threshold rule before any conditional result is read. **Match rates by PICKING a
threshold off a finely-swept grid, never by interpolating a frontier** (`np.interp`
clamps).

Cross-cutting tool: **frontier-excess.** Sweep the base parameter's threshold to
get a (rate, mean-R) curve; score any arm as its excess over that curve at the
arm's own rate. Cheap way to rate-match gates whose rate you can't dial directly.

Evidence: `futures/nq/vei_exploration` (EXP-0008/0009), `futures/nq/estimator_bias`
(FINDINGS §A–C), `forex/exploration_1/RSI_*_REPORT.md`, `forex/exploration_4/reports/SAME_SLOT_ADDENDUM.md`.

---

## 2. Coverage, placebos & rolling-window construction (Rule 9a)

- **Placebos must be COVERAGE-MATCHED.** Print the per-cell COUNT next to every
  placebo/phase/permutation stat; reject the comparison if counts move. A statistic
  defined as EXCESS over a baseline measured in the SAME cell is immune — but run
  the baseline inside every cell.
- **Bar-unit lookbacks multiply when you resample to coarser bars.** Keep lookbacks
  in TIME units when porting.
- **`np.interp` CLAMPS outside its range** — a "rate-matched" comparison silently
  becomes extrapolation against the shallowest baseline cell. Assert every arm's
  rate lies inside the reference curve's range.
- **Strict `min_periods == window` on a same-slot rolling feature = a hidden,
  time-of-day-dependent liquidity filter.** One missing bar nulls the feature and
  silently deletes that decision, concentrated in thin hours. Fix: a fractional
  floor (2/3 or 0.9·window); report per-slot coverage. Uniform post-fix coverage is
  the pass signal.
- **A rolling window counted in CALENDAR bins is unsatisfiable on a market that
  isn't always open** (spot FX covers ~71% of calendar minutes). Count the window
  over the compacted series of TRADABLE bars; `min_periods` then degrades to a
  warm-up rather than a hidden filter. Sanity-check any "lookback in time units"
  rule against the instrument's actual session coverage.
- **Estimate a seasonal normaliser on the full grid, read it at the events** —
  never estimate it from sparse events (they reconstruct the schedule you meant to
  escape).
- **Apply a subgroup MASK after computing a rolling feature, not before.** Masking
  the input first leaves a scattered subgroup with an almost-NaN window.
- **Pin a decision clock to the WALL clock, not minutes-from-open**, when the
  archive has minute-of-hour structure. Check whether a coverage gap has a fixed
  minute-of-hour signature (a download-chunk artifact) before reading it as
  microstructure.
- **A PADDED data vintage deletes exactly the events a session-boundary study is
  about, silently, by making the boundary disappear** (`provisional`). Some spot-FX
  archives carry synthetic Saturday bars; a weekend gap defined as "the move across
  this series' own break" finds no break. Diagnostic: count bars on days the market
  is closed, and bars-per-day by YEAR (a step to exactly 1440/day, or a
  uniform-across-24h histogram on a closed day, is fabrication). Fix: derive one
  canonical session calendar from a clean archive and impose it on every
  instrument. Padding dilutes rather than manufactures an effect.
- **A delayed-entry (boundary-artifact) control must hold the HOLDING PERIOD
  constant, or it silently becomes a horizon sweep** (`provisional`). Anchor exits
  at `entry + H`, not at `event + h`. The distinction is fatal at short horizons —
  exactly where boundary artifacts live.

Evidence: `forex/exploration_1`, `futures/gc/noise_vwap/reports/DATA_QUALITY.md`,
`futures/forex/vwap_exploration`, `forex/exploration_4/reports/DATA_QUALITY.md`,
`forex/exploration_7/reports/DATA_QUALITY.md`.

---

## 3. Degenerate controls — score the variant that removes the thing under test

- **Never select a RATIO on a metric its own NUMERATOR maximises; score the bare
  numerator.** As the denominator's memory grows the ratio degenerates into a
  rescaled numerator, rewarding variants for ceasing to be ratios. Partialling the
  level out is only a partial repair — change the target instead. Corollary:
  `log(implied)−log(realised)` is mostly its denominator when the numerator is
  slow-moving.
- **To test whether missing DATA binds, score the variant that uses NONE of it.** A
  volume-free stop matching the volume-anchored rule proved missing FX volume was
  never the constraint.
- **The degenerate control for an ANCHOR study is NO ANCHOR.** Fading the trailing
  return (no anchor) beat VWAP/TWAP/open/prior-close; the anchor is a noisier proxy
  for short-horizon reversal.
- **Benchmark a new EXTERNAL data source against the cheapest INTERNAL column you
  have not yet used** before taking a production dependency (trailing realised vol
  beat engineered VIX features).

Evidence: `futures/nq/vei_exploration` EXP-0008/0017, `forex/noise_vwap`,
`futures/forex/vwap_exploration`.

---

## 4. Estimand & weighting

- **When SIGNAL COUNT is endogenous to the outcome, per-signal and block-averaged
  estimands disagree in SIGN.** Block-averaging looks conservative and is the more
  dangerous trap. Detect with `corr(block mean, block count)` — read its
  MAGNITUDE, not sign. Use the per-signal mean with a block cluster-robust SE.
- **Rank IC and MEAN quintile spread can give OPPOSITE readings.** Equity intraday
  momentum lives in the TAILS; a rank stat weights the median. Report both; say
  which the decision consumes (equal-risk sizing → mean).
- **An UNCONDITIONAL serial-dependence statistic and a CONDITIONAL-extreme one can
  rank timescales in OPPOSITE order.** Variance ratio prices the AVERAGE move's
  serial dependence (unconditional, linear); `E[fade R | |z|≥2]` prices reversion
  from an extreme. Never pick a decision grain from VR alone; use the
  heteroskedasticity-robust z. Name the object the decision consumes, then measure
  THAT one.

- **A VOL FORECAST that beats every daily benchmark can still fail to monetise as
  SIZING — check flat FIRST, and measure at scale-free Calmar** (`provisional`).
  First-30-min realised vol forecast rest-of-session vol adding +0.09 OOS R² over
  the best daily model, yet inverse-vol sizing LOST to flat 1-contract on TRAIN on
  both NQ and ES (flat won Sharpe AND Calmar). Two mechanisms, both general: (i) if
  the book's P&L is already vol-normalised (here net-R ÷ 14-day ATR), vol-targeting
  re-normalises what the accounting already handled; (ii) inverse-vol DOWN-sizes
  high-vol days, so if the edge CONCENTRATES in high vol (breakout/expansion
  strategies) it cuts the best days. Forecast skill ≠ sizing gain. Sharpe & Calmar
  are scale-free so exposure drift can't flatter them — compare the sizers there,
  and match exposure only for raw-total / vol-of-P&L.
- **A SINGLE trailing average of daily realised vol does NOT beat yesterday; only a
  multi-horizon HAR {1d,5d,22d} mix does** (`provisional`). ma5/ma22/EWMA all scored
  WORSE OOS than the naive 1-day (vol is most-recent-weighted); HAR beat yesterday by
  only +0.04. So the honest sizing/vol benchmark is HAR (or yesterday), never a lone
  moving average — and a new vol feature must add over HAR, not over an easy-to-beat
  long MA.
- **Causal rest-of-session vol forecast ladder: yesterday < HAR < HAR+opening-30m ≈
  +overnight; the OPENING PRINT is the biggest add and OVERNIGHT is a small,
  significant, largely-REDUNDANT top-up** (`provisional`, NQ+ES). Predicting
  log(rest-of-session RV of 1-min log returns): HAR daily ≈0.58 OOS R² → +first-30-min
  realised vol (`early_rv`) +0.07–0.08 (HAC t≈17) → +overnight RV (18:00→09:29) only
  +0.017–0.021 on TOP of the opening print (HAC t≈6–9, real but small). Overnight RV
  ALONE rivals yesterday and adds +0.066 over HAR, but it overlaps the opening 30 min
  because both read the SAME current vol regime. Full stack HAR+opening+overnight
  ≈0.68 (≈+0.10 over daily-only). The signed OPEN GAP magnitude is NOT a vol
  predictor (negative OOS R² alone, subtracts once RVs are present) — DISPERSION
  (sum of squared returns) carries the vol signal, the single jump does not. General
  recipe for future position-sizing vol forecasts on any session-anchored book.

Evidence: `forex/noise_vwap` FINDINGS §B–E, `futures/nq/claude_exploration_1` §B,
`forex/exploration_4/reports/MARKET_CHARACTERIZATION.md`,
`futures/nq/noise_vwap/artifacts/runs/HYP-0039-sizing` (EXP-0050).

---

## 5. Nulls & controls

- **Bar-shuffle nulls are INVALID for barrier/path-dependent strategies** —
  reordering whole bars destroys diffusivity (printed +0.27R at t=31 on pure
  noise). Use a path-preserving RETURN shuffle; references:
  `futures/nq/noise_vwap/core/nulls.py`, `futures/vwap_mean_version/core/nulls.py`.
- **Pin artificial opening sentinels in a return-shuffle null.** Including
  `link[0]=0` then re-anchoring discards a real link and changes the session net
  move. Test opening anchor, net move, atom multiset, and a path-continuity stat
  across seeds before reading P&L.
- **A single-market Null C pass does NOT validate a cross-market mechanism — the
  sibling market is the mechanism test.** The SIGN of the null center is the
  machinery discriminator: positive = fewer-trades variance amplification (reject);
  negative = the effect is genuinely tied to the thing being cut.
- **A side-folded feature (`side·X`) must be permuted WITHIN (slot, era, SIDE).**
  Assert the firing-rate invariant in code and don't read the null until it passes.
- **When the statistic is an EXCESS over an informative baseline, its null does NOT
  centre at zero.** Report null center, baseline, and real value as three numbers.
  When selection occurred, compare the real MAX over the reproduced search to the
  null distribution of MAXIMA.
- **Score an argmax agreement rate against the MODAL-CATEGORY base rate, not a
  uniform null.**
- **A synthetic-injection power check must inject into a DE-MEANED series**, or it
  measures real+injected and reports absurd sensitivity (`provisional`). For a
  simple mean, MDE ≈ 2 × the cluster-robust SE — compute that first; only build an
  injection harness if the estimator is not a mean. Tell: if a "detectable" effect
  isn't itself significant, the MDE is wrong.
- **For two autocorrelated series on a cyclical index, use a CIRCULAR SHIFT, not a
  label shuffle** (a free permutation destroys the autocorrelation, anti-conservative).
- **A conviction score / supervised model cannot manufacture orthogonality that
  isn't there.** Use a matched-COUNT direct benchmark, never a frontier-interp
  (clamps and flatters); SEED-SWEEP any tree top-bucket "win." A model on the base
  lever alone should ~tie the direct base ranking.
- **A small-n guard that returns NaN feeding a comparison that treats NaN as a pass
  prints false significance** (`NaN <= NaN` scored p=0.0000; `NaN >= real` counted
  as "did not beat"). Drop unusable cells from the null explicitly and REPORT the
  count.
- **A NULL RESULT IS UNINTERPRETABLE WITHOUT A POSITIVE CONTROL** (`provisional`).
  "X carries no information" and "my measurement cannot see information" are the
  same output. Before reading a null, run the identical code path on a KNOWN-real
  case and show it is detected — declare this as a VALIDITY GATE in the prereg
  ("control fails ⇒ INCONCLUSIVE, fix the method"). The control also CALIBRATES
  effect size (a real anchor stood ≈21× above its placebo median vs FX's ≈2.3×).
- **When porting a session-anchored construct, match the DECISION UNIVERSE, not
  just the anchor** (`provisional`). The identical NQ 09:30 anchor scored t +3.68 on
  its native 390-min RTH session and +1.60 forced to a 1425-min all-hours session.
  Spreading decisions across hours the construct never claimed dilutes the structure.
- **`Series.astype("int64")` on datetimes returns the integer in the dtype's UNIT,
  and this workspace MIXES units** (`forex/**` is `datetime64[us]`, `futures/nq/**`
  is `datetime64[ns, UTC]`). A hard-coded ns divisor is right on NQ and wrong by
  1000× on FX. Divide by a `pd.Timedelta` (exact at any unit) and assert index
  uniqueness. The danger: correct on the positive control, broken on the subject.
- **A PERSISTENT/stateful rule cannot be controlled by a ONE-SHOT filter —
  randomise the STATE TRANSITION, not the trade list** (`provisional`). A re-entry
  lock re-fires at every later decision bar while armed, so it maps to no set of
  blocked entry keys. Calibrate the control to reproduce the treatment's TRADE COUNT
  (not its rule firings) and print the achieved count; matching on firings
  overshoots. A control with sd==0 is not a null (matching a persistent lock can
  require the whole pool → a deterministic degenerate blocklist) — assert
  non-degeneracy before reading any frac. Fix: keep the state machine, randomise
  only its TRIGGER (release on a coin flip at a hazard bisected to match count).

Evidence: `futures/nq/noise_vwap` (EXP-0013/0043), `forex/exploration_1`,
`futures/forex/vwap_exploration` EXP-0007, `forex/noise_vwap/artifacts/runs/EXP-0003/review.md`.

---

## 6. Fills & bar resolution

- **A 1-minute gross edge on a TP/SL bracket can be a coarse-bar fill artifact.**
  1m OHLC can't order an intrabar stop-vs-target touch; re-run on 1s. If the win
  rate sits at the algebraic break-even `1/(1+RR)`, the barriers are efficient and
  there is no edge. 1m flatters brackets whose stop is nearer than the target.
- **A whole-BAR execution delay is NOT a latency model** (a 60s delay overstated a
  ~1.5s market-order fill cost by ~10×). Sub-second fill decay is FRONT-LOADED then
  plateaus; measure cost at the latency you'll actually run. A MID-only fine-bar
  test settles TIMING, not SPREAD — report the two as separate charges. Fine-bar
  coverage is biased against the illiquid signals you most need to check.
- **A shared decision-bar close manufactures reversion.** `past` ends and `fwd`
  starts at the same close, so pricing error enters with +1 and −1. Enter at
  `open(m+1)`, not `close(m)`. The artifact does NOT shrink with horizon.
- **`mean(open[i] == close[i-1])` is the one-line test for whether that artifact is
  even possible.** On the spot-FX midpoint archive it's ~100%, so "enter at next
  bar's open" does NOT separate the windows. Use a PAIRED one-bar delay (identical
  signal set, same span). Run the check before designing the study.
- **A CONDITIONER correlated with the boundary noise inherits the shared-close
  artifact and masquerades as a real effect** (`provisional`). A volume-confirms-move
  edge lost ~84% to a paired 1-bar embargo (`open[t+2]`). Run the paired embargo
  BEFORE reading any volume/vol/size-conditioned continuation result. The robust
  residual was volume→forward-|move| (magnitude), not direction.
- **A fixed-PIP slippage charged against VOL-UNIT barriers is a grain selector.** A
  PF/expectancy comparison ACROSS grains is mechanically biased against fine grains.
  Charge slippage in σ units when comparing grains, or compare only at matched σ.
  The absolute reading (PF<1 everywhere) still stands.
- **A passive level-retrace exit's entire edge can be the touch-vs-fill assumption
  when the retrace TARGET is also the reversal point** (confirmed on a 2nd
  instrument). A touch of the anchor booked +0.35 pips; requiring price to trade
  THROUGH by a vol-scaled guard flipped it to ≈−0.17. The level is resistance, so
  a touch is not a fill. Diagnostic: report a touch (g=0) ceiling, a guarded (g·σ)
  book, and a time-exit floor side by side; if the edge lives only at g≈0 it is
  not capturable. A fixed-horizon "reversion" result is NOT evidence a passive
  exit can harvest it. **Reconfirmed on NQ futures** (noise-VWAP EXP-0051, a
  post-stop-retrace fill scheduler): touch ceiling +1.091 tick (itself not sig)
  collapsed to a guarded −2.869 tick, per-day day-t −3.02, UNIFORMLY across the
  whole δ/g/K sweep (every guarded config ≤ +0.28 tick, t≈0). Same mechanism, new
  asset class — the retrace level is where price reverses, so leaning a limit into
  it adversely selects its own fills. Corollary: re-casting a dead directional
  reversion as an "execution saving with no position risk" does NOT rescue it —
  the more basic touch-vs-fill test kills it first.

Evidence: `futures/gc/vwap_reversion` EXP-0000, `forex/exploration_1/RSI_FILL_MODEL_REPORT.md`,
`futures/nq/noise_vwap/artifacts/runs/HYP-0038/FINDINGS.md`,
`futures/nq/claude_exploration_1` §G, `forex/exploration_4/artifacts/runs/EXP-0002,EXP-0004/review.md`.

---

## 7. Cross-market transfer & conditioning (Noise-VWAP family)

- **Transferability spans a full range and can fail at the GROSS level** (NQ works
  → ES weaker → GC/YM cost-fragile → RTY no gross edge). Read the gross number and
  the always-long drift control FIRST; a negative gross is a clean NO-GO no
  exit/sizing tweak rescues. The asset-class label does not guarantee transfer.
- **"Edge localised to a co-market's session hours" ≠ "edge follows that market's
  direction."** Read gross-per-trade on the KEPT trades: rising = real info; falling
  = a rarity filter selecting worse trades. Don't flip a negative conditioner whose
  gross≈0 — the loss is cost, and the flip keeps the cost.
- **Cross-market same-signal confirmation is a quality/turnover lever, not alpha.**
  On a tight pair (NQ↔ES) it raises gross/trade and hit-rate, but total net R falls
  and daily Sharpe stays flat. The one Sharpe-beater failed its re-pairing null
  (null centred at ~0 = consumed-history screen).
- **An IMPORTED rule's benefit can be entirely redundant with a fix your baseline
  already has — re-test it on YOUR baseline, and sweep the baseline choice it
  interacts with** (`provisional`). A "require_reset" re-entry lock reproduced its
  author's gain on their config yet was worth ~0 on the same code with a
  fast (every-minute) stop — the two are SUBSTITUTES. Tell: the sign of the
  removed-trade expectancy flips with the baseline; read it before the Sharpe.
- **Continuous/every-bar stop value scales with the drift/noise ratio.** It shrinks
  the loser tail everywhere but clips winners (NQ GO, ES wash, GC inverts). Never
  transfer an exit upgrade across instruments without re-measuring gross AND net.
  Extension-BANKING exits are safe-but-weak; stop-TIGHTENING is harmful on
  noise-dominated markets.
- **The noise band is fully summarized by its per-slot SYMMETRIC level/width.** A √t
  cone (worse), a quantile reshape (inert), and an up/down asymmetric band
  (inert-to-harmful) all add nothing. Method: split any "new dispersion statistic"
  test into a RAW view (the width dial) and a MATCHED-WIDTH view (isolates shape).
- **A cross-pair DIVERGENCE gate is the one conditioner orthogonal to the own-pair
  vol/directional axis** — but null-fragile. Own-pair structure estimators
  (efficiency, ADX, Hurst) are correlated restatements of one axis; use a
  cross-instrument relative-value feature. It's inherently DIRECTED: apply it to the
  error-correcting (follower) leg identified a-priori from cointegration. Keep
  divergence (signed level) distinct from coherence (comovement magnitude, dead here).

Evidence: `futures/{ym,rty,gc}/noise_vwap`, `futures/nq/noise_vwap` (EXP-0013/0018/0020-0022),
`forex/exploration_1/RSI_*COINT*`.

---

## 8. Event studies

- **Check your MEASUREMENT window against the INSTITUTIONAL window.** An entry
  inside the WM 16:00 fix's own averaging window "measured" the event, not a
  reaction. Two one-line controls: an entry-lag sweep (move entry one minute past
  the window) and a holding-horizon sweep at fixed entry.
- **A preregistered arm that fails BACKWARDS is more informative than three that
  pass.** A dated structural break meant to shrink an effect inverted it instead —
  which located the measurement bug. Check the construction first.
- **Derive an event clock from the event's OWN timezone with real DST** —
  hardcoding ET for a London fix misfiled sessions and understated the result.
- **A cross-sectional PANEL is a usable holdout for a pattern read off inspected
  data.** Declare a fresh-vs-consumed split in advance; add panel members at the
  ENDS of the predictor's range (an extreme counterexample beats near-duplicates).

Evidence: `futures/forex/vwap_exploration` (EXP-0003 §E/§F, EXP-0007 §H/§K).

---

## 9. Algebra, predictor stability & inference

- **Ask how much of a result is ALGEBRA before you read it.** A trend-following
  closed form matched realised P&L to 4e-17 — so it IS the backtest, and its screen
  was algebra (OOS ≈ 0). Print `Spearman(predicted, realised)` above the headline;
  ~1 means the comparison is an identity. A re-pairing null cannot detect an identity.
- **The unnamed failure mode: a STABLE predictor of an UNSTABLE target.** Realised
  trend P&L had ZERO year-to-year rank persistence while the predictor's was +0.71 —
  a confident smooth ranking uncorrelated with next year. Compute both persistences
  BEFORE building any screen; if the target's is ~0, no estimator can help.
- **Bootstrap the DIFFERENCE against a degenerate no-theory benchmark, not the
  statistic against zero** (second-project confirmed → standard). A percentile CI
  that doesn't bracket its own point estimate is biased — read as "no evidence."

Evidence: `futures/panel/trend_closedform` FINDINGS §A–H.

---

## 10. Lead-lag, regime splits & forward-looking inputs

- **For any lead-lag claim, run the REVERSE direction first.** A genuine lead is
  ASYMMETRIC; a symmetric "each predicts the other" is shared contemporaneous info.
  Read the contemporaneous link for scale (~75× the lagged one here).
- **Match a regime split on VOLATILITY, not just time-of-day.** Almost every
  intraday label carries a vol gradient (a coherence contrast of +0.05 collapsed to
  −0.005 when split within vol quintiles). Always run the MIRROR arm.
- **A forward-looking input can be an ANCHOR, not an anticipator — check WHERE it
  pays.** Intraday VIX helped a vol forecast on aggregate but the gain was WORST in
  the FOMC window its mechanism required; it anchors an over-extrapolating past-price
  model. Pick the cell where the mechanism MUST fire and name it before the run;
  prefer a mechanism prediction that is ASYMMETRIC across markets.

Evidence: `futures/nq/claude_exploration_1` §C/§E, `futures/nq/vei_exploration` EXP-0017.

---

## 11. Estimators — smoothers & warm-up

- **Compare smoothers at matched effective MEMORY (centre-of-mass), not nominal n.**
  Wilder (`α=1/n`) has com `n−1`, twice an SMA(n)'s; memory is the bigger lever. A
  com-matched SMA reversed a "Wilder wins" conclusion. Wilder `α=1/n` IS
  `ewm(span=2n−1)`.
- **`ewm(adjust=False, min_periods=n)` is NOT textbook Wilder ATR** — it seeds at
  the first observation and only masks the first n−1 outputs. Harmless as a one-off
  burn-in, but a feature that RESETS each session pays it every session, inflating
  apparent autocorrelation and injecting a time-of-day gradient. Seed with the n-bar
  SMA or set `min_periods ≈ 2n−1`.
- Small-sample AR-bias is a NON-ISSUE for pooled inference (max |bias| 0.0003 at
  T≈44k) but a real FEATURE-CONSTRUCTION problem at T=13–30. The analytic corrector
  `−(1+3φ)/T` fails below T≈20 — use a parametric bootstrap and run two independent
  correctors (their disagreement is the only tell).

Evidence: `futures/nq/vei_exploration` (EXP-0006), `futures/nq/estimator_bias`.
