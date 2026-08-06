# Project Memory: Forex Exploration 1

## 2026-08-05 Cross-pair COINTEGRATION / DIVERGENCE conditioner — NO-GO (null 2/4), but the most INDEPENDENT conditioner found; conditioner search now exhausted

- Status: **NO-GO under the frozen spec** (rule 25, recorded). Frozen
  `RSI_COINTEGRATION_GATE_SPEC.md`, report `RSI_COINTEGRATION_GATE_REPORT.md`; screen
  `_run_rsi_cointegration_gate.py`, step-2 null `_run_rsi_cointegration_null.py`; results
  `rsi_cointegration_{gate,null}_*.json`/`.csv`. Consumed history; 2024+ sealed.
- **Feature (distinct from the DEAD coherence gate, LEARNINGS 2026-08-04):** built purely
  from the PARTNER pair (EUR↔GBP, AUD↔NZD) so it cannot restate P's own |z|. `z_partner` =
  partner's displacement z joined by timestamp; `xalign = side·z_partner` (positive =
  favorable relative-value DIVERGENCE: partner did not confirm the move). Coherence was a
  second-moment return-CORRELATION magnitude; this is a first-moment signed LEVEL divergence.
- **Screen: first survivor of the whole conditioner search to clear the delay bar.**
  `diverge_hi` monotone in keep (−0.0015/+0.0083/+0.0140 R at keep 40/20/10), mirror
  `diverge_lo` uniformly worse; `diverge_hi 10` +0.0140 R (3/4) with **delay0 +0.0056**
  (Hurst failed exactly this). Risk unit 7.18 < frontier 9.5 → not a vol selector.
- **Step-2 INDEPENDENCE = clean PASS (the only conditioner that is):** orthogonal to (even
  mildly anti-correlated with) the own-pair vol/directional axis — xalign~vei_atr_z ≈ −0.15,
  ~adx_z ≈ −0.10, P(diverge|vol) ≈ marginal. Stacks on the vol gate 3/4 (EUR +0.018, AUD
  +0.025, NZD +0.014; GBP −0.003); within-vol split diverge>confirm 4/4 at matched risk unit.
  Contrast KER/ADX/Hurst, which were all +0.4–0.6 correlated with each other (same axis).
- **Step-2 symmetric NULL = FAIL (2/4), block-structured — but the DIRECTED follow-up
  SUPPORTED it 2/2.** Selection-corrected donor null (re-pair z_partner within (slot,era,SIDE)
  — see method note): **EURUSD PASS** (frac 0.000), **NZDUSD PASS** (frac 0.000), GBPUSD FAIL
  (0.100), AUDUSD FAIL (0.130) — one leg of each block passes decisively. The asymmetry is
  EXPLAINED and confirmed: `RSI_DIRECTED_COINT_SPEC/REPORT.md` (`_run_rsi_directed_coint.py`,
  `rsi_directed_coint_results.json`) identifies each block's FOLLOWER (error-correcting) leg
  a-priori from early-era error-correction betas (forward-30m Δlog leg on the cross deviation,
  price levels only, no fade P&L): EUR/GBP β_EUR −0.0082 vs β_GBP −0.0007 → **EURUSD** (which
  DISAGREES with liquidity — EUR is the more liquid pair yet the error-correcting leg); AUD/NZD
  β_NZD +0.0262 vs β_AUD −0.0067 → **NZDUSD**. The rule independently selects {EURUSD, NZDUSD}
  = the exact symmetric passers, and a directed null (diverge_hi only) clears **2/2 followers
  at frac 0.000** while both anchors fail (GBP 0.060, AUD 0.090). So the divergence signal lives
  on the error-correcting leg; the symmetric 4-leg test diluted a real 2/2 directed effect.
  Caveat: the follower β shares reversion info with the fade (partial circularity), mitigated by
  the a-priori rule disagreeing with liquidity and by the null being independent of β. Status:
  SUPPORTED, provisional (2 effective blocks). Rule 26 respected (follower assigned by rule, not
  by the winners).
- **Method note (reusable, → LEARNINGS):** the FIRST null run FAILED its firing-rate invariant
  4/4 because `xalign` folds in `side`; permuting z_partner ACROSS sides flips signs and
  scrambles the rate + null-max means. Fix = permute WITHIN (slot,era,side). The in-code
  invariant (RULES 17) caught it before interpretation; corrected null kept the 2/4 verdict
  but gave trustworthy null-max means.
- **Economics unchanged:** best arm ~0.24 pip gross; even vol-stacked diverge cells top ~0.18–
  0.37 pip (GBP), still below the ~0.70 pip commission floor.
- **CONDITIONER SEARCH NOW EXHAUSTED across three axes:** directional structure (KER/ADX/Hurst)
  — real direction but redundant, sub-floor; cross-pair COHERENCE — dead (null centred 0);
  cross-pair DIVERGENCE — orthogonal, stacks, and CONFIRMED under a directed null (2/2 on the
  error-correcting leg), but STILL sub-floor (~0.24 pip gross vs ~0.70 pip commission floor).
  The one confirmed, deployable-quality regime remains the VOLATILITY gate (+0.0137 R, null 4/4
  family); divergence is a real second orthogonal conditioner that stacks with it but neither
  alone nor stacked crosses the cost floor. No conditioner crosses the floor. The remaining
  lever is Workstream C (FTMO challenge simulator: pass-probability × payout, size + trade cap
  as levers), the only avenue that changes the estimand rather than the per-bet edge. #1
  macro/news gating remains deferred.

## 2026-08-05 Hurst-exponent regime conditioner — NO-GO; reproduces the ADX direction on a third estimator but redundant + fails the delay bar

- Status: **NO-GO under the frozen spec** (rule 25, recorded). Frozen `RSI_HURST_GATE_SPEC.md`,
  report `RSI_HURST_GATE_REPORT.md`, results `rsi_hurst_gate_results.json`/`.csv`; feature
  `_hurst_feature.py` (+ `_test_hurst_feature.py` 7/7), `_run_rsi_hurst_gate.py`. Consumed
  history; 2024+ sealed. Reproduce: `python -u _run_rsi_hurst_gate.py`.
- **Feature built to dodge the LEARNINGS 2026-08-03 landmine:** generalized Hurst exponent
  order 1 on a FIXED 120-bar trailing window (NOT session-to-date, so sampling dispersion
  does not shrink through the session) + same-slot z-score. A fixed cut on a growing-window
  persistence estimate is a time-of-day selector (the `noise_vwap` Hurst-gate defect); this
  construction avoids it. Both LOW and HIGH sides run, directional kill decides (no post-hoc
  flip).
- **Direction reproduces ADX on a third, independent estimator:** HIGH Hurst
  (persistent/trending) reverts better than LOW on all three keeps; LOW-Hurst gates all
  worse than the frontier (classical "reversion likes anti-persistence" falsified again).
  So directional STRUCTURE → better reversion is now seen on KER-family (weak), ADX (best),
  and Hurst — same axis, same sign.
- **But NO-GO as a gate, two reasons:** (1) the positive delay-1 arms (`high_hurst_z 20`
  +0.0138 R 3/4, `high_hurst_z 40` +0.0073 R 3/4) **flip NEGATIVE at delay 0** (−0.0033,
  −0.0007), breaching the preregistered "delay 0 does not contradict" clause → not clean
  SUPPORTED (ADX held +0.0021 at delay 0, so Hurst is the more fragile of the two). EURUSD
  is the negative delay-1 pair, as usual. (2) **Redundant with the ADX axis, not vol:**
  Spearman(hurst_z, adx_z) ≈ +0.47 on all pairs, ker_z ≈ +0.37, but vei_atr_z only +0.11
  and rv30_pct +0.06–0.09 → a partial restatement of the already-tested (and non-deployable)
  directional axis, NOT new information and NOT a volatility proxy.
- No step-2 null run: the spec gates it on a clean survivor and there is none. Economics
  unchanged (same sub-0.70-pip-floor size as the rest of this axis). Coverage clean (hurst_z
  defined 0.974–0.977 EUR/GBP/AUD, 0.925/0.948 NZD; incremental deletion is the session-open
  sliver, base `z` already excludes the first 120 min).
- **Takeaway for the search:** three estimators on the "directional structure conditions
  reversion" axis (KER, ADX, Hurst) now agree on direction, but none clears the deployment
  bar and each tops out ~+0.007–0.014 R, all ~3× below the commission floor. This axis is
  understood and exhausted for deployment purposes; further conditioners should probe a
  DIFFERENT axis (the open items are #4 cointegration-only and Workstream C the account sim).

## 2026-08-05 Directional-EFFICIENCY conditioner — preregistered thesis REJECTED and FALSIFIED in the opposite direction (ADX/DI, not KER)

- Status: **the preregistered hypothesis is dead** (rule 25 NO-GO, recorded). Reports:
  frozen `RSI_EFFICIENCY_GATE_SPEC.md`, results `rsi_efficiency_gate_results.json`/`.csv`;
  code `_efficiency_features.py` (+ `_test_efficiency_features.py` 10/10 — KER=1 on a
  straight line, 0 on a zigzag, ADX high on a trend / low on chop, both causal, ADX
  resets per session), `_run_rsi_efficiency_gate.py`. Consumed history; 2024+ sealed.
- **Preregistered direction (choppy/low-efficiency → better reversion): REJECTED on
  every arm and falsified in the OPPOSITE direction on 6/6 low-vs-high comparisons.**
  Screen = excess mean R over the |z| frontier at matched rate, delay 1, engine identical
  to the confirmed regime matrix (event clock, 2R stop, 1-pip slip, 30-min horizon).
  LOW-efficiency gates are all **worse** than the frontier (low_adx_z 20 **-0.0208 R**,
  low_ker_z 20 -0.0144, 0/4 pairs); HIGH-efficiency gates are all **better**. Fading a
  |z| extreme reached via a CLEAN directional push reverts better than one reached by a
  choppy grind — the reverse of the standard "reversion likes chop" intuition.
- **The channel is ADX/DI, not generic path efficiency (KER).** `high_adx_z 20` scored
  **+0.0069 R excess, 4/4 pairs**, surviving delay 0 (+0.0021) and delay 1; `high_adx_z 40`
  +0.0070, 3/4. The KER mirror was weak (+0.0015..+0.0036, 1/4 pairs), so it is
  specifically the directional-movement (ADX/DI) structure that carries the reversed
  signal, not net/gross path efficiency. HTF-slope arms (with/counter-trend) both negative.
- **The reversed direction was then preregistered and CONFIRMED as a mechanism, but NOT
  as a deployable lever** (follow-up run, frozen `RSI_ADX_REVERSAL_SPEC.md`, report
  `RSI_ADX_REVERSAL_REPORT.md`, `_run_rsi_adx_reversal.py`,
  `rsi_adx_reversal_results.json`/`_draws.csv`). Because the DIRECTION and the ARM were
  both chosen post hoc (rule 26), the test was a selection-corrected claim-matched donor
  null (joint re-pairing of ker/ker_z/adx/adx_z/htf_slope within (slot,era); real MAX over
  the whole efficiency search vs null MAX) PLUS a redundancy check against the confirmed
  vol gate. The script's automatic panel-count gate said "REAL & INDEPENDENT"; read
  per-pair the honest verdict is **narrower**:
  - **Conditioning relationship CONFIRMED (family level).** The clean decisive test — a
    within-vol conditional split (among vol-gate signals, high vs low adx_z at the median,
    depth- and rate-matched) — is **4/4 pairs**, high-ADX half out-reverts low by +0.0069
    to +0.0096 R. The **risk-unit guardrail (rule 19) splits the panel**: on EUR/GBP the
    high-ADX half has a *lower* risk unit (8.4 vs 9.0) → NOT vol-selection, clean
    vol-independent evidence; on AUD/NZD it has a *higher* risk unit (8.3 vs 6.4; 8.2 vs
    7.2) → partly residual volatility. Real on the majors, partly vol-confounded on the
    carry pairs — opposite split from where the null was strongest.
  - **NOT a robust independent GATE.** As a hard AND conjunction on the vol gate it stacks
    on only **2/4 pairs meaningfully** (EUR +0.0080, NZD +0.0191; GBP ≈0 +0.0004, **AUD
    −0.0073 — combining HURTS**). Selection-corrected null passes **3/4** (EURUSD FAILS
    frac 0.070; NZD's pass is a KER arm `low_ker_raw 10`, not the ADX candidate; high-ADX
    itself clears the null only on GBP/AUD). Best cell is pair-specific (keep 10 EUR/GBP,
    20 AUD) — "family confirmed, cell not identified", same as the vol-regime family.
  - Redundancy is **partial not full**: adx_z~vei_atr_z ≈ +0.24, ~rv30_pct ≈ +0.15 (far
    from ~0.9), ~ker_z ≈ +0.62. P(high-adx|vol) ≈ 0.45 vs 0.35 marginal.
- **Economically it changes nothing.** ~+0.008 R, comparable to but NOT additive-robustly
  with the confirmed vol gate (+0.0137 R); at 30-min horizon ~0.2-0.3 pip gross vs the
  ~0.70 pip commission floor, ~3x underwater. **Not adopted; not a holdout candidate.**
  Logged as confirmed mechanism + negative-for-deployment evidence (rule 25). Coverage
  clean (adx_z defined 1.000 EUR/GBP/AUD, 0.974/0.993 NZD, thin late-session minutes).
- Reproduce: `python -u _run_rsi_efficiency_gate.py` then `_run_rsi_adx_reversal.py` from
  `forex/exploration_1`.

## 2026-08-05 MODELLED prop-firm cost economics — DECISIVE NO-GO for a cost-taker

- Status: **the spread/commission-taking version of this strategy is NOT deployable
  on an FTMO-style cost structure.** Gross edge ~0.23-0.29 pip/trade vs a modelled
  ~0.70-1.15 pip round-trip floor. Reports `RSI_COST_HOUR_ECONOMICS_REPORT.md`
  (+ frozen `RSI_COST_HOUR_ECONOMICS_SPEC.md`); scripts `_run_cost_hour_economics.py`,
  `_run_depth_cost.py`; shared cost model `_cost_model.py` (tested, `_test_cost_model.py`
  15/15). Consumed history; 2024+ still sealed.
- **The binding killer is the per-lot COMMISSION, not the spread.** FTMO-style
  $3.5/side on a $10/pip pair = **0.70 pip round trip on its own, ~2.4x the 0.286 pip
  gross edge**, and it is depth-, hour-, and gate-independent. Even with commission
  ZEROED the modelled spread over the traded hours averages ~0.45 pip and the strategy
  is still net -0.15 pip (t -3.1). Negative in the optimistic scenario too.
- **D2 (time-of-day): dead.** Best cell, base scenario, delay 1: net **-0.85 pip /
  -0.113 R, net t -16**, and **gross < cost in all 24 UTC hours** (cheapest is the
  15:00 UTC overlap, gross 0.43 vs cost 1.03). Restricting to liquid 07:00-20:00 UTC
  only lifts net R to -0.06; overlap 12-16 UTC -0.04 to -0.10. **0/4 pairs net-positive
  in liquid hours.** The project's edge leans into the WIDE-spread late hours, so hour
  selection makes it worse, not better.
- **D3 (depth): dead, and worse than expected — gross does not even rise with depth.**
  Ungated `|z|` swept 1.5->5.0 (delay 1, median): gross pips PEAK at **0.230 at z=2.0**
  and FALL thereafter (0.196 at z=3.0, negative beyond z=3.5). Under the compulsory 3R
  stop + 30-min horizon deep signals overshoot and the risk unit grows faster than the
  pip capture, so R-excess selectivity does not translate into cost-clearing pips. Gross
  ceiling 0.230 pip is a THIRD of the 0.700 pip commission floor; no depth net-positive
  under any scenario/pair.
- **D5 (passive entry) and D4 (target exit) NOT built — bounded and moot.** Passive
  entry saves at most ~0.45 pip spread but the 0.70 pip commission still exceeds the
  0.23 pip gross. A target exit would need to ~3x the per-trade capture; the project's
  own MFE/exit work already found stops/TPs do not help (|win|~|loss|, shared tail).
- **D6/D7 (FTMO challenge sim, portfolio) NOT built — moot.** A challenge cannot be
  passed by compounding net-negative trades; a portfolio of net-negative legs is
  net-negative. Gated on a positive per-trade stream that does not exist.
- **Load-bearing caveat (rule 25 preserved honestly):** cost is MODELLED not measured;
  the verdict rests almost entirely on the **$3.5/side commission** assumption (it is
  negative even commission-free, but the *decisive* margin is the commission). If a
  target account has materially lower/zero commission, re-run with that `CostParams`
  before accepting NO-GO. That single number is the highest-value input the project can
  now obtain. `_cost_model.py` constants (HALF_SPREAD_BASE, HOUR_MULT, ERA_MULT,
  SCENARIO_MULT, VOL_BETA, COMMISSION_USD_PER_SIDE) are all declared assumptions.
- Only routes that could change the verdict are outside this strategy's reach: a
  genuinely commission-free account with a sub-0.2-pip round-trip spread (not available
  in retail/prop FX), or a fundamentally larger-per-trade-move strategy (a different
  programme). The mean-reversion *signal* remains real (confirmed vs null); it is the
  *economics on this cost structure* that are dead.

## 2026-08-05 GO/NO-GO on the user's REAL costs — MARGINAL positive on AUDUSD, screen-stage

- Status: **from a decisive NO-GO to a thin, screen-stage POSITIVE on AUDUSD (taker) and
  AUD+NZD (passive). Not yet a confirmed edge — every cluster t < 2 and the 240m horizon is
  a searched peak.** Script `_run_final_economics.py` -> `final_economics_results.json`.
  User costs: AUDUSD 0.3 / NZDUSD 0.5 pip avg spread, $5 RT commission (=0.5 pip). abs_sigma
  top10 pocket, 240m hold, 3R stop, delay 1. Consumed history; 2024+ sealed.
- **Taker (pay spread+commission), 240m, delay 1:** AUDUSD net **+0.327 pip/trade
  (+153 pips/yr, t 0.77)** at the stated average spread, +0.177 at spread x1.5, +0.027 at
  x2 — positive but NOT significant and knife-edge on the high-vol spread. NZDUSD +0.101 at
  avg, NEGATIVE at x1.5+. GBPUSD negative everywhere (assumed 0.6 spread). The pocket trades
  the highest-vol minutes where the real spread exceeds the daily average, so x1.5-2 is the
  honest operating point -> only AUDUSD survives, barely.
- **Passive entry (earn spread, cost=commission 0.5 only) ~doubles it:** AUDUSD **+0.627
  pip/trade, 0.058 R, t 1.48, +293 pips/yr, daily Sharpe 0.65**; NZDUSD **+0.601, 0.050,
  t 1.59, +304 pips/yr, Sharpe 0.57**; GBPUSD marginal. This is an UPPER BOUND — real resting
  limits at a reverting extreme suffer non-fill/adverse selection (rule 4), unmodellable
  without bid/ask.
- **THREE weaknesses that keep this a screen (rule 26), not a GO:** (1) all cluster t < 2;
  (2) **240m is a sharp searched PEAK** — taker net at 180m and 300m (spread x1.5) is
  negative for both pairs, so the horizon is a consumed search parameter and the cost eats a
  searched margin; (3) AUD/NZD are ~1 effective test. Worst day -10 to -13 R (size trades so
  that is <5% for an FTMO daily-loss limit).
- **Delay fragility differs by pair:** AUDUSD 240m taker x1.5 delay0 +0.446 -> delay1 +0.177
  (holds); NZDUSD +0.100 -> -0.149 (flips negative). AUD is the more robust member.
- **Frozen candidate for the holdout:** abs_sigma top10 pocket, |z|>=1.5 fade, 240m hold,
  3R stop, 1-pip slippage, delay 1, AUDUSD (primary) + NZDUSD (secondary, passive only),
  EURUSD excluded (momentum). Decisive next test is the 2024+ holdout; before that, get real
  high-vol-state spread and (for passive) a bid/ask adverse-selection model. Do NOT deploy on
  a t<1 consumed-history screen.

## 2026-08-05 the 240m edge is REAL REVERSION (not drift) on AUD/NZD; EURUSD INVERTS to momentum

- Status: **the long-horizon pocket edge survives a drift null on the two commodity pairs
  and is confirmed as signed mean reversion, not directional drift.** Script
  `_run_horizon_null.py` -> `horizon_null_results.json`/`.csv`. abs_sigma top10, event clock,
  non-overlap, 3R stop, delay 1. Consumed history; 2024+ sealed (screen, rule 26).
- **240m is a PEAK, not a runaway ramp** (the drift tell): median gross R 0.022(30m) ->
  0.044(180) -> **0.065(240)** -> 0.060(300) -> 0.060(360) -> 0.046(480). A pure
  hold-for-daily-drift effect would keep rising; it turns over at 4h.
- **NOT drift — the always-long control is negative/zero on every pair** (AUD -0.003,
  NZD -0.053, GBP -0.021, EUR -0.072 at 240m). There is no free directional drift in these
  states to harvest; the P&L is the signed signal.
- **IS reversion — side-permutation null (300 draws, re-executed on real paths, preserves
  L/S balance), 240m:** AUDUSD real **+0.095 R, t+2.66, null centered ~0, p>=0.000**,
  follow -0.098; NZDUSD real **+0.091 R, t+2.91, p>=0.000**, follow -0.108. Both decisive.
  GBPUSD real +0.039, t+0.88, p>=0.083 (directionally reversion, follow -0.043, but WEAK).
  **2/4 pairs clear p<=0.05; follow_R<0 on 3/4 (fading is the profitable direction).**
- **LONG/SHORT SYMMETRY confirms reversion on 3 pairs:** at 240m both sides pay on AUD
  (long +1.18 / short +1.07), NZD (+0.63 / +1.58), GBP (+0.22 / +0.87). A one-directional
  drift would load one side only.
- **EURUSD INVERTS to MOMENTUM at long horizon:** real -0.050 R (t-1.60), **null p>=0.880
  (below null), follow +0.022, long side -1.83** — oversold EUR extremes in high-vol states
  CONTINUE DOWN over 4h, they do not revert. Exclude EUR from the long-hold reversion book;
  the inversion is structural (weak-member behaviour taken to the trend regime).
- **CAVEAT: AUD and NZD are the most correlated pair (~1 effective test), so "2/4 decisive"
  is really the Antipodean bloc**; GBP weak, EUR opposite. Real but thin. Needs the 2024+
  holdout eventually.
- **Economics unchanged by this — still net-negative under full base cost** (240m net_base_R
  -0.025 median, net_nocomm_R +0.022): the signal is now KNOWN real, so the remaining work
  is purely the cost side (passive entry / low commission) on the AUD/NZD/GBP basket. The
  ~0.42 pip spread residual is the gate; commission is the floor.
- Next: price the spread/commission residual on the AUD/NZD(/GBP) 240m basket; investigate
  whether the EUR momentum inversion is its own (post-hoc) signal; then the holdout.

## 2026-08-05 LONGER HORIZON is the first numerator win; the vol-sized BRACKET is not

- Status: **a 240-minute hold on the abs_sigma pocket triples gross to 0.825 pip and is
  net-POSITIVE commission-free (+0.209 pip median), 3/4 pairs (EURUSD inverts). The
  vol-sized TP/SL bracket does NOT beat a fixed-horizon exit.** Scripts
  `_run_horizon_bracket.py`, `_bracket_engine.py` (+ `_test_bracket_engine.py` 11/11).
  Event clock, non-overlap, 3R stop, delay 1, modelled cost. Consumed history; 2024+ sealed.
- **Horizon sweep (abs_sigma top10, delay 1, median across pairs):** gross pips
  0.272 (30m) -> 0.176 (60) -> 0.322 (120) -> **0.825 (240)**; gross R 0.022 -> 0.065;
  risk unit ~12-13 pip; stopped only 14% at 240 (a 4h hold with a loose 3R safety stop).
  **At 240m gross (0.825) EXCEEDS the commission floor (0.70) for the first time**;
  net commission-free **+0.209 pip**, net base (comm+spread ~1.12) still -0.491.
- **EURUSD INVERTS at the long hold** (gross -0.875) while AUD/GBP/NZD are +1.13/+0.55/
  +1.10 — the reversion->trend crossover. So 3/4 pairs, ~2 effective (AUD/NZD paired).
- **OPEN QUESTION before trusting it: is a 4h hold in high-vol states booking directional
  DRIFT, not reversion?** Needs a claim-matched null / no-signal 4h-hold control (rule 17)
  before promotion. The gross-R rise could be a different (trend) effect.
- **The vol-sized bracket adds nothing.** 16-cell (k_tp,k_sl) grid, timeout 120m: best
  gross 0.33 (tp1.5/sl3.0) ~= the plain 120m hold (0.322); tight stops catastrophic
  (sl1.0 gross negative), wide targets rarely hit (tp3.0 target_frac 0.067). Confirms the
  project's "TPs don't help |win|~|loss|" under the honest engine + cost. NB the bracket
  IS exposed to the 1-min intrabar-ordering ambiguity (resolved adversely, rule 3); the
  horizon result is single-barrier+timeout so it is NOT.
- **Economic picture now:** the ~0.42 pip residual after commission is the only remaining
  gap on the 3 good pairs. Live routes to close it: (a) LOW/ZERO commission account,
  (b) PASSIVE entry to earn the spread, (c) trading only liquid hours. Concrete viable
  stack: **abs_sigma pocket + ~240m hold + spread recovery, on AUD/GBP/NZD, EURUSD
  excluded.** Not yet a GO — needs the drift null, a longer-horizon optimum sweep, and a
  real commission number.

## 2026-08-05 regime-pocket economics (honest engine) — ABSOLUTE-vol is the best lever, still short

- Status: **no pocket clears the FTMO floor at delay 1, but absolute-sigma selection
  roughly HALVES the loss and reaches ~breakeven commission-free.** Script
  `_run_regime_pocket_economics.py` -> `regime_pocket_economics_results.json` / `.csv`.
  Event clock, non-overlap, 3R stop, delay 1, modelled cost (`_cost_model.py`).
- **The documented 1.2-pip vol-Q5 pockets were a measurement mirage** (delay 0, no stop,
  `:29` clock). Honestly every pocket's gross collapses to ~0.3 pip, and the tight cells
  lose **60-68% of gross to the one-minute delay** (rv30 top5 retains 0.32, vei&rv30 top10
  0.36) against 0.79 for the base — the highest-conviction signals are the MOST
  execution-fragile (first-traded-minute concentration).
- **SAME-SLOT PERCENTILE selection does NOT pull the commission-fraction lever**: rv30
  top5/top10 percentile *lowered* the risk unit to 6.5 pip (top-5% for a quiet slot is
  absolutely quiet), so net R only reached -0.077.
- **ABSOLUTE risk-unit selection (`rv30_pips` = rv_30m in pips, early-era cut) is the
  best arm and validates the user's regime-pocket instinct:** abs_sigma top10 lifts sigma
  to **12.2 pip** (from 7.5), net R **-0.046** (best of 17 arms), net t -3.7; abs_sigma
  top20 net R -0.061 but **commission-free net -0.039 pip = ~breakeven**. The mechanism
  (rule 19) is real money against a FIXED commission.
- **But grossR is stubbornly ~0.02-0.04 in EVERY pocket** — pockets move sigma and
  frequency, not the edge fraction, so gross ~0.3 pip regardless of entry selection. The
  ~0.30 pip gross vs ~0.70 pip commission gap is unbridgeable from the ENTRY side.
- **What this localises: the residual cost after commission is the VOL-WIDENED SPREAD.**
  In the abs_sigma pocket the modelled spread alone (~0.39 pip round trip) keeps it
  marginally negative even commission-free, so the two live levers are now (a) a LOW/ZERO
  commission account and (b) PASSIVE entry to earn rather than pay that spread. The one
  untested NUMERATOR lever is a LONGER HOLDING HORIZON (more gross pips per trade against
  the fixed commission; the project's own notes say net rises with horizon via cost
  amortisation) — next test, combined with the abs_sigma pocket.
- Rangebreak added nothing honestly (gross 0.217, net R -0.166, retains 0.81 so not
  fragile, just weak). rv5/vei percentile pockets all -0.11 to -0.14 R.

## 2026-08-05 the system on a FIVE-MINUTE bar clock — a wash on the base, and
## the regime gate is revealed as a SHORT-HORIZON conditioner

- Status: **no clock change recommended; one real finding about the gate.**
  Frozen spec `RSI_FIVE_MINUTE_CLOCK_SPEC.md`, report
  `RSI_FIVE_MINUTE_CLOCK_REPORT.md`, script `_run_rsi_five_minute_clock.py`.
  Parameters preserved in BAR units (EMA20, z sd 120, RSI 14, ATR 14/50); risk
  unit = trailing RV over one holding period; gate keeps the canonical 30-minute
  RV percentile. Signals/exits on the 5m clock, **stop resolved on the 1-minute
  path** (a 5m bar hides a minute that opens through the level — rule 5).
- **The base edge transfers essentially unchanged per unit of risk.** Time-matched
  30-minute horizon: 5m `|z|>=1.5` pays **0.0240 R** against the published 1m
  **0.0230 R**, risk unit 8.11 vs ~8.6 pips, at 2,741 signals/yr vs ~1,700. So the
  one-minute result was NOT a sub-five-minute microstructure artefact — the edge is
  visible at both sampling rates. Equally, slowing the clock buys nothing.
- **The gate is WEAKER on the slower clock**: combined `ATR40 + rv40` gives
  0.0344 R / excess +0.0100 against 1m's 0.0451 R / +0.0137.
- **THE USEFUL RESULT: the regime gate's excess collapses monotonically with
  HOLDING PERIOD** — **+0.0100 R at 30 min, +0.0045 at 60, +0.0003 at 150** — and
  the collapse holds at all five grid phases. At 150 minutes the family confirmed
  against a claim-matched null in `RSI_GATE_NULL_REPORT.md` is a pure selectivity
  dial, and the ATR expansion gate alone is *worse* than the frontier (-0.0094,
  0/4). **If the gate is retained the hold must stay short.**
- At the declared primary horizon (150 min) only `z1.5 + rv pct 20` passes
  (+0.0081 R, 3/4, delay-1 +0.0040, late +0.0086, positive at all 5 phases). That
  is 1 of 10 arms on correlated pairs with no null — a screen (rule 26).
- **The `|z|` frontier is much FLATTER on this clock**: humped with a peak near
  `z=2.0` and nearly flat at 150 min, against a cleanly monotone 0.016->0.038 on
  the 1-minute clock. Depth is a weaker lever here, so the excess metric has a
  less informative baseline than it did.
- **Delay retention is NOT improved**: one 5-minute bar retains 22-29% of pips
  (25-37% of R) against 72%/71% for a one-*minute* delay on the 1m clock. Since
  the 1m clock at a five-minute delay retained ~15%, the decay is a **wall-clock
  property of a few minutes** and a coarser bar does not escape it.
- **RULE-9a, TWICE, and the second one nearly produced a false headline.**
  (a) Preserving the z window in BAR units makes it 600 minutes, which no longer
  fits between daily gaps: the strict rule gave **coverage 0.000 for the first TEN
  hours of every session** (all of Asia, 58% of bars). (b) The obvious repair
  (allow one break) works at grid phase 0 ONLY — off-phase the bar straddling the
  17:00 rollover is incomplete, hence invalid, hence TWO breaks, so Asia is deleted
  again. The first completed run therefore reported **phase 0 at rank 1/5 with ~3x
  the mean R of every other offset**, which reads exactly like the `:29` artefact
  and would have been written up as "the 5-minute result is entirely a phase
  artefact". It was a coverage hole: phase 0 had 1,212 signals/yr against ~783
  off-phase. Fix: give the scale estimator no break gate at all (coverage 0.9999,
  per-slot min 0.9995, event counts matched across phases).
  **A phase/seasonality placebo must be COVERAGE-MATCHED before it is read; check
  the per-cell signal COUNT first.**
- **The phase confound is real but cancels out of the primary metric.** Phase 0
  ranks 1/5 in absolute mean R on both arms, sitting **+0.0086 R above the phase
  median = ~38% of the base arm's entire edge** (phase 0 puts every entry on a UTC
  minute divisible by 5, including `:00`/`:30`, the most reverting minutes per
  `RSI_CLOCK_CONFOUND_REPORT.md`). But excess-over-frontier is phase-robust
  (+0.0100/+0.0077/+0.0060/+0.0022/+0.0080), because a phase shift moves the arm
  and its own frontier together. **Direct vindication of scoring against the base
  parameter's own frontier rather than against zero.** All absolute levels quoted
  at phase 0 are flattered.
- **Measurement flaw to state with the RSI rows**: `rsi 15/85` and `rsi 20/80`
  fire at 272-401 signals/yr, BELOW the frontier's own minimum rate (573 at H=6,
  421 at H=30), where `np.interp` clamps — so they are scored against the
  shallowest frontier point, not a matched one, and must not be promoted. The
  apparent revival of RSI on the slower clock is partly that artefact. The one
  clean row, `rsi 30/70` at +0.0077 / 2-4 pairs, remains a dial, reproducing the
  1-minute "RSI and z are the same variable" conclusion.
- Cost unchanged and still binding: gross 0.21-0.34 pip/trade; annual net per pair
  +40 to +199 pips at a 0.2 pip round trip, **all cells negative at 0.5 pip**.
- Consumed history; 2024+ holdout untouched. No null run (rule 17).

## 2026-08-05 claim-matched null on the volatility-regime gate — PASSES

- Status: **the regime family is CONFIRMED real; the specific gate cell is NOT
  identified.** Report `RSI_GATE_NULL_REPORT.md`, script `_run_rsi_gate_null.py`,
  100 draws/pair.
- Null: within each **(session minute, era)** cell, permute the triple
  `(vei_atr_z, rv30_pct, rv5_pct)` **JOINTLY** across dates on the full minute grid.
  Preserves every price path and P&L-given-entry, the `|z|` trigger and its depth, the
  event clock, non-overlap, stop and slippage, each feature's exact marginal within
  every cell (hence the firing rate), the joint dependence between the two gates, and
  the slot seasonality. Destroys only the contemporaneous feature-to-forward-return
  link. **All four preservation claims asserted in code and PASS on 4/4 pairs.**
- **Selection-corrected result (real MAX over the 5-arm search vs the null MAX):
  4/4 pairs clear p<=0.05** — frac null max >= real = 0.010 (EURUSD), 0.000, 0.000,
  0.000. The "1 pass out of 13 arms" concern is answered.
- **METHOD CATCH, and it must always be stated with this pass: the null centres
  NEGATIVE (-0.0012 to -0.0130), not zero**, because the subtracted baseline (the
  `|z|` frontier) is itself an informative selection — a RANDOM gate at the same rate
  keeps the shallow z=1.5 mix and so lands below a deeper frontier cell. Two distinct
  bars: **"beats the null" = carries information**; **"excess > 0" = beats the cheaper
  option of just deepening `z`**, which is the deployment bar and the harder one.
  Quoting only the null p-value would have overstated this by ~0.010 R, most of the
  effect.
- **Combining beats either component at matched rate on 4/4 pairs**: combined minus
  same-rate ATR-alone median **+0.0085 R**, minus same-rate rv30-alone **+0.0032 R**.
  True even on EURUSD, where both single gates are more negative than the combination.
  This is the strongest evidence in the run and is why the combined gate stays the
  default.
- **But the argmax arm DIFFERS ON EVERY PAIR**: EURUSD ATR40 (+0.0056), GBPUSD
  rv30_40 (+0.0204), AUDUSD ATR40+rv30_40 (+0.0130), NZDUSD rv30_20 (+0.0219). The
  combined gate is the winner on **1 of 4**, is flat on EURUSD (-0.0002) and fails its
  own null there (0.270). One arm is wrong-signed (EURUSD rv30_20, -0.0109, frac
  0.970). **Promote the FAMILY, not the cell; do not tune keep fractions per pair.**
- Partly retracts the previous day's "the single gates are selectivity dials" wording:
  they are weak against the FRONTIER (+0.004 to +0.006, 2/4) but decisively real
  against a RANDOM gate. The earlier phrasing conflated the two bars.
- **EURUSD is the weakest member on every regime arm.** Do not read panel medians
  without it.
- Unchanged: no spread measurement, late-era cluster t 1.46, p-floor 0.01 at 100 draws.

## 2026-08-04 trigger redundancy and the regime-filter matrix

- Status: **RSI-on-z rejected; the single regime gates are all selectivity dials; one
  combined gate is a new leading candidate needing a null.**
- Frozen spec `RSI_Z_REGIME_MATRIX_SPEC.md`, report `RSI_Z_REGIME_MATRIX_REPORT.md`,
  script `_run_rsi_z_regime_matrix.py`. Event clock, non-overlap, compulsory stop
  2.0 R + 1 pip slippage, as `RSI_COHERENCE_TIMEEXIT_SPEC.md`.
- **Method to reuse here: every arm is scored as EXCESS mean R over the `|z| >= k`
  FRONTIER interpolated in log signals/year to that arm's own rate.** An arm on the
  frontier added nothing but selectivity. The frontier is monotone (0.016 R at 7,947
  signals/yr to 0.038 R at 1,697) with a flat risk unit (8.2-9.6 pips), so it is a
  genuine depth effect and a clean reference.
- **RSI and `z` are the same variable: Spearman 0.9684 on 4.21M minutes**,
  `P(z<=-1.5 | RSI<=30) = 0.821`, and **zero** minutes where they disagree on
  direction. RSI extremes are close to a subset of `z` extremes.
- **Stacking RSI on `z` is REJECTED and is mildly WORSE than a matched-rate deeper
  `z`**: `z1.5 AND rsi30/70` excess **-0.0025 R (0/4 pairs)**, `z1.5 AND rsi25/75`
  -0.0043 (1/4), `z2.0 AND rsi30/70` -0.0010 (0/4). All five standalone RSI
  thresholds also sit on the frontier (-0.0024 to +0.0018). The conjunction reaches
  RSI-like selectivity by an indirect route that discards deep-`z` signals RSI did
  not flag, and those are not worse than average. **Set depth on `z`; do not stack.**
- **Only ONE of three documented regime survivors had been applied.** The prior run
  used the ATR expansion gate alone; `rv_30m_pct_90d` and `rv_5m_pct_90d` had never
  been run on an event clock. Individually all are dials (excess +0.0042 ATR40,
  +0.0061 rv30_40, +0.0050 rv5_40, +0.0037 rv30_20 — every one at **2/4 pairs**,
  inside the +/-0.005 no-effect band). **This downgrades the deployed ATR expansion
  gate to a selectivity dial on its own.**
- **The one arm that passes: `|z|>=1.5` + ATR expansion top40 AND rv30 pct top40.**
  Excess **+0.0137 R, 3/4 pairs**, delay-1 +0.0126 (92% retained), late era +0.0079.
  2,803 signals/yr, 0.382 pip, **0.0451 R against 0.0230 for the plain `|z|>=1.5`
  base**. Not arithmetic: two +0.005 dials do not compose to +0.0137, consistent with
  this project's own finding that volatility ACCELERATION and volatility LEVEL are
  distinct low-correlation conditioners. Risk unit 8.41 pips against 8.6-8.9 at the
  matched frontier point, so the gain is **not** a risk-unit artefact.
- **But it is 1 pass out of 13 declared arms, EURUSD is flat (-0.0002) while the
  other three carry it, the four pairs are correlated tests, late-era cluster t is
  1.46, and NO NULL was run (rule 17).** Treat as a screen (rule 26). Required before
  promotion: a claim-matched null through the full pipeline, and a check that no other
  single same-rate own-pair statistic reproduces it.
- Cost: 0.382 pip x 2,803 trades/pair/yr is about **+510 pips/pair/yr at a 0.2 pip
  round trip and -331 at 0.5 pip**. Better than the ungated base; still decided by the
  unmeasured spread.

## 2026-08-04 event clock, compulsory stop, coherence gate and time exit

- Status: **both tested components rejected; two framework changes adopted**.
- Frozen spec `RSI_COHERENCE_TIMEEXIT_SPEC.md` written before both runs; report
  `RSI_COHERENCE_TIMEEXIT_REPORT.md`. New engine `_rsi_stop_engine.py` with
  `_test_rsi_stop_engine.py` (17 passing checks on the fill rules).
- **The fixed `:29`/`:59` decision clock is RETIRED at the user's instruction.**
  Signals are now events (the first minute the entry condition becomes true) with
  **non-overlap enforced** (rule 13, one position at a time). This also removes
  the phase selector `RSI_CLOCK_CONFOUND_REPORT.md` documented. Placebo check
  passes: top minute-of-half-hour holds 4.6-5.4% of events against 3.33% uniform,
  `:29` holds 3.5-4.1%. Event entries run **4,400-4,800 per pair per year**,
  about 4x the fixed clock, median 55-62 minutes apart.
- Rule-23 reproduction is against the published **first-crossing** figures, not
  the fixed-clock ones (a different clock is a different sample): EURUSD early
  0.4135, GBPUSD early 0.3954, EURUSD late 0.2212, GBPUSD late 0.3376, against
  published 0.397-0.418 early / 0.220-0.341 late. Three inside outright, the
  fourth 0.0016 low.
- **A single-price-barrier stop is COMPULSORY (prop-firm challenge), and it is a
  monotone tax on expectancy, 4/4 pairs, larger than either component tested.**
  Gated signal, median, 1-pip slippage: no stop 0.333 pip / 0.047 R, 3.0 R 0.308
  / 0.042, 2.0 R 0.269 / 0.034, 1.5 R 0.185 / 0.019, **1.0 R 0.030 / -0.008 with
  cluster t falling 8.65 to 0.90** and mean R negative on 3/4 pairs. Winners and
  losers are both about +/-0.9 R, so truncating losses truncates gains by more.
  The 649 R drawdown at 1.0 R is the negative mean compounding, not a separate
  risk effect.
- **What tight stops DO buy is a smaller worst day** (-13.9 R at 1.0 R against
  -18.6 R with no stop, monotone). A challenge's daily-loss limit binds on that
  while its profit target binds on expectancy, so the two rules pull stop width
  in opposite directions. Recommendation: **widest stop the risk budget allows
  (3.0 R if it fits, 2.0 R compromise, never below 1.5 R); control daily loss
  with size and a trade cap, not stop tightness.**
- **The event clock's edge retains 72% of pips and 71% of R under a one-minute
  entry delay** (0.269 -> 0.193 pip), far better than the 15% that killed the
  freshness component on the fixed clock. The best news in the run.
- **Arm 3, cross-pair coherence as a trending-regime gate: REJECTED.**
  `coh = sign(own u) x mean(u of the OTHER three pairs)`, `u` = trailing 30-min
  return / trailing 30-min RV, causal same-slot percentile. Own pair excluded, and
  it is not a restatement of `|z|` (Spearman 0.10-0.13 gated, -0.003 to +0.04 on
  RSI). Median T1-T3 gap **-0.0012 R, 2/4 pairs**; wrong sign on EURUSD and
  AUDUSD; quintile profile flat and non-monotone; volatility-matched split flips
  the sign; **re-pairing null centres at 0.000 with sd 0.010-0.013 and only 1/4
  pairs falls outside it**. The null was adequately powered — a +0.02 R effect
  would have sat ~2 sd outside. GBPUSD alone behaves as predicted (+0.0276 R,
  null frac 0.015) and is recorded as a curiosity, not promoted: two of four go
  the wrong way and these are correlated USD pairs.
- **Arm 4, time-based non-reversion exit: REJECTED, and the decisive control is
  the matched-rate RANDOM-time exit.** Exiting a randomly chosen 46% of trades at
  minute 10 does as well or better than exiting the 46% that had not yet reverted
  (median -0.0021 R, 1/4 pairs). Exiting **everyone** at minute 10 gives the same
  0.032 R as the conditional rule. Three ways of shortening exposure, three
  identical answers: the condition carries no information.
- The time exit does cut the tail as designed (worst-5% -3.548 -> -3.232, max DD
  111 -> 86 R, worst day -15.6 -> -11.7 R) but the random control achieves the
  same, so it is bought with exposure, not information. Hit rate falls 0.534 ->
  0.390. The matched-rate tighter STOP control (0.64 R) is catastrophic (-0.039 R)
  — so **if exposure must be shed, shed it on the clock, not by tightening the
  stop** — but that control passing is not evidence for the time exit.
- Late era remains weak system-wide: gated base **0.123 pip / 0.014 R, t 1.81** in
  2021-2023 against 0.329 / 0.044, t 7.13 in 2012-2020.
- Incidental repair: the audited fixed-clock script fitted the expansion-gate
  quantile on the whole sample (two-sided); it is now fitted on the early era only.
- **Cost sensitivity is now worse, not better**: 0.269 pip x 4,380 trades/pair/yr
  is roughly +300 pips/pair/yr at a 0.2 pip round trip and **-1,010 at 0.5 pip**.
  Measuring the spread is the binding next action.
- Evidence: `_run_rsi_coherence_gate.py`, `_run_rsi_time_exit.py` and their
  JSON/CSV outputs. Consumed history; 2024+ untouched.

## 2026-08-04 exhaustion-threshold control and freshness component

- Status: **component 2 rejected; freshness confirmed but not deployable**.
- Frozen spec `RSI_THRESHOLD_FRESHNESS_SPEC.md` written before both runs; report
  `RSI_THRESHOLD_FRESHNESS_REPORT.md`. Rule-23 reproduction of the three audited
  rows within 0.003 pip.
- **The vol-scaled exhaustion threshold `|z| >= 1.5(1+vol_pct)` is a selectivity
  dial.** The audited run compared it against a fixed `|z| >= 1.5` at 632 versus
  1,724 signals/yr. Rewriting every trigger as a score `s = |z|/g(vol_pct)` and
  keeping the top rate by that score makes them exactly rate-matched; the
  published rule then **loses**: median -0.241 pip trigger-only (0/4 pairs),
  -0.172 pip with the expansion gate (1/4). The deficit is monotone in
  selectivity (-0.383 at keep 0.02 to -0.037 at 0.20). The +0.060 gain is
  retracted; `RSI_REGIME_GATED_SYSTEM_REPORT.md` component 2 is marked superseded
  in place.
- **The mechanism, and the reusable part: all three threshold rules carry the
  same edge per unit of risk (~0.10 R) and differ only in the volatility of the
  states they select.** Implied risk unit at keep 0.05: 7.4 pips (published), 8.6
  (fixed), 10.1 (mirror `2-vol_pct`). `A-B` and `C-B` in R units run -0.013 to
  +0.009 with pair votes 1-3 of 4 either way. The pips ranking was a risk-unit
  ranking. Report mean R alongside mean pips for every trigger comparison here.
- Demanding MORE stretch when vol is high makes high-vol states hardest to
  trigger, so the published rule samples the **calmest** states — fighting this
  project's own finding that reversion is stronger in high-RV states.
- **The mirror rule (shallower threshold in high vol) wins on pips 4/4 (+0.400)
  and is the only rule with late-era t > 3, but is NOT adopted**: it does not win
  in R units, so its advantage is that it selects high-volatility states where a
  flat pip cost is a smaller share of the move. The unmeasured spread now decides
  which threshold rule is correct, not only whether the system is viable.
  Recommendation is the degenerate fixed threshold, no volatility scaling.
- **Freshness (time-in-zone) is real and scale-free**: gated system, age 0 pays
  1.363 pip / 0.183 R against 0.824 / 0.097 for all ages, monotone decay to 0.495
  / 0.048 at age 11-20, 4/4 pairs, late era positive (median +0.675). Reproduced
  independently on canonical RSI 30/70 (0.777 against 0.585). Age correlates
  positively with volatility, so the scale channel runs against the result.
- **But 85% of the freshness gain is the first traded minute** (fresh-minus-base
  0.539 -> 0.162 pip at a one-minute entry/exit delay; 39% retained in R units).
  It is the `RSI_CLOCK_CONFOUND_REPORT.md` effect on a new axis, not a new
  component. Not adopted. It also fails the frozen pips comparison against
  tightening the existing expansion gate (2/4) — though that "control" is itself
  a volatility selector with an 11.8-18.6 pip risk unit, and freshness wins 4/4
  in R units. Recorded as a disclosed amendment, not a pass.
- **Separate system-level finding: at a one-minute delay the gated base is net
  -0.125 pip at a 0.5 pip cost.** The surviving system's net edge is delay-0
  dependent.
- Surviving system is now **component 1 only** (ATR(14)/ATR(50) same-slot z-score,
  top 40%) with a plain fixed exhaustion threshold.
- Evidence: `_run_rsi_threshold_control.py`, `_run_rsi_freshness.py` and their
  JSON/CSV outputs. No null (rule 17). Consumed history; 2024+ untouched.

## 2026-08-04 volatility-feature breadth audit

- Status: **confirmed scope correction; negative exploratory screen**.
- The current `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` correctly treats its
  original feature result as non-exhaustive. A frozen audit broadened it to 28
  causal price-only volatility features and three frozen targets, plus one
  disclosed post-run scale diagnostic.
- The expanded model added no stable value over RSI depth plus canonical RV(30):
  median AUC delta -0.0138 for RSI survival, +0.0017 for fixed-pip tail loss, and
  +0.0028 for volatility-scaled tail loss.
- The frozen univariate gate formally passed only because it allowed the known
  RV-level family to count; this is recorded as a gate-design flaw, not a new
  feature discovery. The incremental model gate failed.
- RV level predicts fixed-pip tail loss (median AUC 0.557-0.580), partly a scale
  channel. In RV units the sign reverses (RV30 median AUC 0.406): high current RV
  has fewer exceptionally bad normalized losses, consistent with stronger
  reversion in high-RV states. This is already captured by RV(30), not a new edge.
- Broader kurtosis/quarticity/jump/vol-of-vol constructions produced no stable
  incremental survivor. Genuine implied-volatility term structure was not tested
  and is unavailable in the current midpoint dataset.
- Evidence: `RSI_VOLATILITY_FEATURE_BREADTH_AUDIT_REPORT.md`, its specification,
  `_run_rsi_volatility_feature_breadth_audit.py`, and the audit CSV/JSON outputs.
  The 2024+ holdout remains sealed.

## Scope

- Objective: explore whether causal one-minute price/path features predict signed
  or absolute forward returns on EURUSD, GBPUSD, AUDUSD, and NZDUSD, while porting
  the VEI and forward-volatility notebook investigations to spot FX.
- Instruments or markets: EURUSD, GBPUSD, AUDUSD, NZDUSD midpoint OHLC.
- Data coverage: cleaned `forex/data/clean/*USD_1m_clean.parquet` files are now
  preferred, with the original `forex/data/archive/*usd_intraday_1min.csv` files
  retained as loader fallbacks. Exploration remains capped at 2023-12-29.
- Current phase: interpreted pre-holdout exploration; no candidate has yet been
  frozen or tested on the 2024+ holdout.

## Current status

- Verdict: provisional. Full pre-2024 results support short-horizon directional
  mean reversion and volatility persistence, but not a net tradable strategy.
- Last verified: 2026-08-04.
- Lifecycle phase: experiments / exploratory screening.
- Baseline replication: implemented. The futures VWAP-side diagnostic is adapted
  to cumulative New-York-roll session TWAP because FX volume is unavailable.
- Engine audit: smoke/integration checks passed; not a deployable backtest engine.
- Execution profile: decision at completed one-minute bar, next-minute open entry,
  exact configurable-horizon open exit, default non-overlapping 30-minute clock.
- Holdout status: 2024 onward is operationally sealed by the notebook loader and
  final assertions. Do not imply it is workspace-wide untouched without a separate
  audit of other forex work.
- Experiment ledger: not created; register any promoted material experiment before
  opening the holdout.
- Reproduction command: open and run
  `forex/exploration_1/forex_feature_ml_research.ipynb` from the workspace root.
- Primary evidence: the notebook plus `_build_notebook.py`,
  `_smoke_run_notebook.py`, and `evaluation_results.json`.
- A separate `rsi_parameter_exploration.ipynb` now provides a single-pair RSI
  research lab. It is reproducibly generated by
  `_build_rsi_exploration_notebook.py` and validated by
  `_smoke_run_rsi_notebook.py`.
- `rsi_clock_feature_interactions.ipynb`, generated by
  `_build_rsi_clock_interactions_notebook.py`, tests whether RSI severity explains
  the scheduled-versus-first-crossing difference and screens 47 causal RSI ×
  market-state interactions across EURUSD/GBPUSD and 5/15/30/60-minute outcomes.
  `_run_rsi_clock_interactions_notebook.py` executes the full notebook and exports
  `rsi_clock_feature_interactions_results.json` as durable table evidence.
- `tsi_vs_rsi_mean_reversion.ipynb` compares canonical TSI(25,13) with the
  existing close/Wilder RSI(14) result on EURUSD and GBPUSD. It is reproducibly
  generated by `_build_tsi_vs_rsi_notebook.py`, executed by
  `_smoke_run_tsi_notebook.py`, and exports `tsi_vs_rsi_results.json`.
- `asian_range_sweep_reversal_exploration.ipynb` is a new pre-2024 descriptive
  lab for the user-defined ET sessions and the claim that both sides of the
  observed Asian range are swept by 17:00 ET. It is reproducibly generated by
  `_build_asian_range_sweep_notebook.py` and smoke-tested by
  `_smoke_run_asian_range_sweep_notebook.py`. It includes coverage/start-time
  gates, buffered and width-conditioned sweeps, sequential re-entry/midpoint/
  opposite-side paths, next-open timing diagnostics, alternative seven-hour
  anchors, a within-year day re-pairing null, and EURUSD/GBPUSD dependence.

## Confirmed findings

- Data/schema only: all four input files have ordered, unique timestamps, valid
  positive OHLC, and `volume == -1` throughout the retained pre-2024 sample.
- The four-pair integration build completed with 154,834 EURUSD, 154,826 GBPUSD,
  154,831 AUDUSD, and 149,997 NZDUSD decision rows at the default 30-minute clock.
- NZDUSD has materially more within-session missing minutes than the other three
  pairs. Recursive indicators restart and re-warm after gaps; exact rolling/target
  windows null around gaps; cumulative partial-history use is exposed by
  `session_gap_count_to_date` and coverage reports.
- At the default 30-minute horizon, the strongest signed-return features are a
  redundant mean-reversion family. RSI(14) within-slot IC is -0.065 EURUSD,
  -0.066 GBPUSD, -0.054 AUDUSD, and -0.057 NZDUSD; the sign is negative in every
  sample year. Donchian position and 5-to-30-minute past returns show the same
  effect. This is a provisional screened finding, not an independent confirmation.
- At the same horizon, the strongest absolute-return features are recent range and
  realized-volatility measures. Range RV(60) within-slot IC is 0.319 EURUSD,
  0.275 GBPUSD, 0.295 AUDUSD, and 0.252 NZDUSD, positive in every sample year.
  This is a provisional screened volatility-persistence finding.
- Annual walk-forward models for 2016-2023 produced positive signed IC in every
  pair-year. Pooled IC is 0.033-0.051 for ridge and 0.041-0.052 for histogram
  gradient boosting; direction accuracy is approximately 51.3%-52.3%.
- Absolute-return walk-forward full-model IC is 0.463 EURUSD, 0.471 GBPUSD,
  0.382 AUDUSD, and 0.353 NZDUSD. It exceeds the core model in every pair-year;
  the mean annual incremental IC ranges from 0.015 to 0.022. Attribution among
  the correlated added feature families remains unresolved.
- The TWAP-side momentum baseline is invalidated at 30 minutes: mean gross return
  per trade is -0.054, -0.043, -0.067, and -0.117 bp for EURUSD, GBPUSD, AUDUSD,
  and NZDUSD respectively, before any spread or slippage. Reversing it has not
  been evaluated as a properly specified strategy and must not be inferred by
  simply negating these aggregate results.
- Provisional RSI-grid finding (EURUSD only): the executed
  `rsi_parameter_exploration.ipynb` searched 42 RSI definitions across 5, 15,
  30, 60, 120, and 240-minute targets. Close-source RSI beat OHL3 source on all
  126 paired smoother/length/horizon cells (mean mean-reversion IC advantage
  0.0070). Wilder and EMA were broadly similar and both exceeded SMA; the effect
  was broad across lengths rather than isolated at 14. Median IC decayed
  monotonically from 0.079 at 5 minutes to 0.017 at 240 minutes.
- The manually selected EURUSD close/Wilder/RSI14/30-minute 30/70 rule produced
  0.646 gross pips per signal in 2012-2020 (9,630 signals, session-cluster t 6.97)
  and 0.695 gross pips in the already-exposed 2021-2023 check (3,607 signals,
  t 5.48). Both long and short sides were positive. Session-block intervals for
  mean log-bp return excluded zero in both periods. This is exploratory evidence,
  not a fresh holdout result.
- The RSI14/30-minute path geometry is only modestly favorable: in-sample mean
  MFE/MAE was 6.14/5.74 pips (ratio 1.074), the 90th-percentile adverse excursion
  exceeded favorable excursion (13.75 vs 12.95 pips), and the fixed-horizon exit
  captured about 10.7% of mean MFE. Gross breakeven cost was about 0.65 pips;
  at a hypothetical 0.50-pip round trip the mean fell to 0.146 pips with t 1.56.
- Timing is the primary RSI risk: a one-minute feature lag reduced in-sample mean
  edge from 0.646 to 0.348 pips and cluster t from 6.97 to 3.92; a five-minute lag
  reduced it to -0.041 pips. The 2021-2023 check retained 0.485 pips at one minute
  and only 0.177 pips at five minutes. Close-source dominance plus this rapid
  decay requires first-minute return decomposition and adverse execution tests.
- Provisional two-pair fakeout finding: close/Wilder RSI(14) 30/70 mean reversion
  is positive in all 12 pre-2024 sample years for both EURUSD and GBPUSD under
  both signal clocks. Scheduled 30-minute-state gross P&L is 0.637-0.646 pips in
  2012-2020 and 0.679-0.695 pips in the exposed 2021-2023 robustness era; first-
  crossing gross P&L is smaller at 0.397-0.418 and 0.220-0.341 pips respectively.
  Both long-after-oversold and short-after-overbought directions are positive.
- The scheduled edge is front-loaded. In 2012-2020, its first five minutes account
  for about 85% of EURUSD and 99% of GBPUSD 30-minute gross P&L. A five-minute
  delayed fixed-clock entry leaves 0.092 EURUSD and 0.005 GBPUSD; the later era
  leaves 0.243 and 0.209 pips. First-crossing events decay less abruptly but start
  with lower gross expectancy.
- Requiring the scheduled RSI-extreme close to break the preceding 30-minute range
  is the strongest provisional condition found so far. It raises 30-minute gross
  P&L from 0.646 to 1.046 EURUSD and 0.637 to 1.051 GBPUSD in 2012-2020, and from
  0.695 to 0.911 and 0.679 to 0.897 pips in 2021-2023. MFE/MAE improves from about
  1.05-1.17 to 1.15-1.24. The separate directional-impulse condition adds little;
  for the 30-minute definition it is redundant with the range-break subset.
- The full RSI clock-interaction run completed on 151,810 pre-2024 event rows
  (74,704 EURUSD; 77,106 GBPUSD), reproduced all eight prior clock/era 30-minute
  means within 0.0015 pip, and retained no row after 2023-12-29. Primary-target
  coverage is about 97.1%; overall causal VEI-percentile coverage is about 95.5%.
  Exact continuous 60-minute features fall to 74.4% coverage in the worst
  late-era 16:00-24:00 UTC cell, so long-window/time-of-day interpretations use a
  selected subset rather than uniform event coverage.
- The hypothesis that scheduled signals win mainly because their RSI is more
  extreme is rejected on the inspected pre-2024 history. Scheduled states are
  indeed deeper (mean threshold depth about 4.9-5.4 RSI points versus 2.1-2.5 for
  first crossings), but half-point common-support matching still leaves scheduled
  30-minute gross P&L ahead by +0.306/+0.244 pip in EURUSD early/late and
  +0.213/+0.306 pip in GBPUSD. Session-clustered depth-adjusted clock coefficients
  are also positive in all four cells (+0.203, +0.343, +0.242, +0.224 pip), though
  GBPUSD late is weak (t=1.09). Additional state controls increase rather than
  remove the coefficient, but that selected regression is diagnostic and must not
  be read causally. The residual clock effect remains unexplained.
- SUPERSEDED 2026-08-04: the residual clock effect IS explained, and the framing
  that scheduled sampling carries extra information is WITHDRAWN. The comparison
  confounds signal definition with sampling PHASE. The scheduled clock is 100% on
  minute-of-half-hour :29; first crossings spread over all 30 phases. First
  crossings that land ON :29 average +1.214/+0.716 pip (EURUSD early/late) and
  +1.427/+1.377 (GBPUSD), i.e. equal to or BETTER than the scheduled clock, at
  matched threshold depth; off-phase crossings average +0.206 to +0.380, and the
  published crossing mean is just their 1:29 mixture. Phase :29 is rank 30/30
  (29/30 in one cell) across a 30-phase placebo sweep, and is the most negative
  full-range RSI mean-reversion IC phase in 3 of 4 cells on ~107k rows per phase.
  The excess is concentrated in the first traded minute (entirely so on GBPUSD)
  and survives as an unconditional effect with no RSI involved: one-minute return
  lag-1 autocorrelation is -0.085/-0.082 at :00 and -0.062/-0.074 at :30 against a
  60-minute median of -0.016/-0.024, and a :29/:59 signal is entered at the
  :30/:00 open. Two further candidate explanations are ruled out: within the
  scheduled clock expectancy DECAYS with time-in-zone (tau=0 is the best cell at
  +0.90/+1.04, tau 6-20 is flat to negative), and length-biased sampling works
  AGAINST the scheduled clock (reweighting crossings to the scheduled run-length
  mix gives -1.61/-1.99 pip). Evidence: `RSI_CLOCK_CONFOUND_REPORT.md`,
  `_run_rsi_clock_{decomposition,phase_forensics,boundary_test}.py` and their
  three JSON outputs; 7 of 8 published clock means reproduced within 0.0021 pip
  (GBPUSD early crossing -0.0147, a post-gap NaN-RSI edge case in crossing
  detection). Consequence: run every future clock comparison at matched sampling
  phase or sweep the phase as a placebo. Not a trade recommendation — the on-phase
  cells are 0.7-1.4 pip gross against a 0.5-1.0 pip round trip, post hoc, n=475 to
  1952, and their first-minute concentration is the same fragility the existing
  one-minute-lag decay records. Open question: whether the :00/:30 reversal is
  real boundary flow or an IBKR spot bar-construction artifact — repeat the
  unconditional test on CME 6E/6B minute data to separate them.
- CROSS-VENDOR CHECK 2026-08-04, two sources added: LSE tick-derived 1s bars for
  EUR/USD + GBP/USD (`forex/data/lse/fx/`, 2009-09 to 2012-02/04, a different
  vendor and an almost non-overlapping period) and Databento GLBX.MDP3 ohlcv-1m
  for CME 6E + 6B (2010-06 to 2026-07, exchange-reported prints, returns masked
  across contract changes). THE FINDING REPLICATES: phase :29 is rank 30/30 among
  the 30 half-hour phases on IBKR EURUSD, IBKR GBPUSD, LSE GBPUSD, CME 6E and CME
  6B, with excesses of +0.267 to +0.717 pip; the sixth cell, LSE EURUSD, is 22/30
  and is also the thinnest (2,155 signals per phase) with a near-zero base rate.
  The threshold-free version agrees (Spearman IC by phase, 26k-133k rows/phase:
  :29 most negative on LSE GBPUSD, 6E and 6B, 3rd on LSE EURUSD). THE PROPOSED
  MECHANISM ONLY HALF REPLICATES: aligned one-minute close-to-close lag-1
  autocorrelation puts :00 at rank 1/60 and :30 at 3-4/60 on both LSE pairs
  (surviving an activity control), matching IBKR — but on CME it is absent, and
  6E's :30 is the LEAST reverting minute of the hour (rank 60/60). CME trade
  prints carry bid-ask bounce of about -0.35 that dwarfs any minute-of-hour
  structure, and :00 volume is about 2x the median minute, so the raw CME profile
  is largely a liquidity profile; after regressing ac1 on log activity both CME
  contracts are unremarkable at :00 and :30. Shape check: the first-minute
  component of the phase-:29 excess is rank 30/30 in every cell INCLUDING both
  futures, but on CME the remaining 29 minutes are also rank 30/30 and 29/30 and
  carry MORE of the excess (first-minute share 36%/51% on 6E/6B versus 56%-107%
  on spot). So the effect is concentrated near trade start everywhere and runs
  deeper into the holding period on futures. Net: the phase confound is confirmed
  on three vendors and two venues; the ":00/:30 reversal spike" explanation is
  spot-FX-specific and the mechanism is OPEN again. Also fixed a real measurement
  bug: IBKR bars satisfy open(t) == close(t-1) exactly and LSE bars do not, so an
  open-to-open series on one vendor is a close-to-close series on the other
  shifted by one minute; the first cross-check compared them unaligned and read
  as "LSE does not replicate" when it does. Evidence:
  `_run_boundary_crosscheck.py`, `_run_boundary_crosscheck_aligned.py`,
  `_run_phase_shape_crosscheck.py` + JSON outputs, and the cross-vendor section
  of `RSI_CLOCK_CONFOUND_REPORT.md`.
- No RSI-depth interaction from the 47-feature screen is promoted. At the primary
  30-minute horizon, the only locally BH-significant interaction among 376
  pair/era/clock tests is late-era EURUSD first-crossing return autocorrelation
  (standardized beta +0.516 pip, t=3.32, q=0.041); it does not reproduce in the
  other pair/era cells. The descriptive four-of-four sign lists are not independent
  confirmation: 80.9% of all scheduled-clock coefficients are positive and 75.0%
  of first-crossing coefficients are negative, while many volatility/path features
  are near-duplicates. No feature has both replicated sign and corrected evidence
  across all four cells. This interaction search is a NO-GO, not a strategy filter.
- A separate full-range scheduled-clock test resolves the apparent conflict with
  the user's original VEI quintiles. It uses raw RSI versus signed 30-minute return,
  not RSI depth versus side-adjusted payoff inside 30/70 extremes. Causal VEI Q5
  has stronger within-slot RSI mean-reversion IC than Q1 in all eight pair/era
  cells: Q1 ranges from -0.009 to -0.042 and Q5 from -0.036 to -0.087, with
  Q5-Q1 IC-strength gains of +0.028 to +0.054. The session-clustered RSI x VEI
  interaction has the strengthening sign in 8/8 cells; seven are locally
  BH-significant and late AUDUSD is directionally consistent but weak (t=-1.78,
  raw p=0.075, q=0.253). This is provisional consumed-history stability evidence,
  not a fresh confirmation.
- The supported regime is volatility ACCELERATION, not high absolute volatility.
  VEI is ATR(10)/ATR(50) relative to its prior same-slot history. RV(5)/RV(30) and
  RV(15)/RV(60) also show Q5 strengthening and negative interactions in all 8/8
  pair/era cells. In contrast, absolute RV(30/60), range RV, accumulated session
  RV, prior-session RV, and daily-volatility percentile do not have stable Q5
  strengthening; session-RV Q5 is stronger in only 1/8 cells.
- Full-range RSI IC is strongest during 16:00-24:00 UTC in all eight pair/era
  cells (median absolute within-slot IC 0.0836 versus 0.0351-0.0578 in the other
  blocks), and the VEI interaction strengthens in all eight cells in that block
  and 30/32 time-block cells overall. Do not promote the exceptionally large
  rollover-hour IC: that period has systematic missingness, thin trading, midpoint
  data, and no spread model, making microstructure artifact a leading explanation.
- VEI is not yet a symmetric 30/70 strategy filter. VEI-Q5 extreme-signal payoff
  is positive for both sides in all 16 pair/era/direction cells, but Q5 improves
  over Q1 in only 10/16 (6/8 overbought/short, 4/8 oversold/long). The robust claim
  is about full-range ranking; fixed-threshold economic uplift is asymmetric and
  needs timing, cost, and holdout validation. Evidence: `RSI_REGIME_TEST_REPORT.md`,
  `RSI_REGIME_TEST_SPEC.md`, `_run_rsi_regime_test.py`, and
  `rsi_regime_test_results.json`.
- A frozen 27-variant broad regime sweep on roughly 149,130 New-York-clock
  decisions per pair confirms the acceleration family across alternative horizons
  and normalization memories. Every VEI variant (ATR 5/25, 10/50, 25/100) and
  RV-ratio variant (5/30, 10/50, 25/100) has stronger Q5 full-range RSI IC in all
  8/8 pair/era cells; all but RV(25)/RV(100)-90d also have the strengthening
  rank-interaction sign in 8/8. RV(5)/RV(30) with a 90-session same-slot
  percentile is the best balanced survivor: median Q5-Q1 IC-strength gain +0.050,
  8/8 positive fixed-30/70 P&L uplift, Q5 median 0.854 gross and 0.354 pip after a
  hypothetical 0.5-pip cost, with median net session Sharpe 0.73. It is a
  promotion candidate, not a deployable strategy.
- Normalization-memory evidence modestly favors 90 over 30 sessions: 90 days has
  higher IC separation in 6/9 paired definitions and higher median P&L uplift in
  8/9, but differences are small and RV(25)/RV(100) IC favors 30. The more durable
  distinction is horizon: fast RV(5)/RV(30) beats longer RV ratios, while slower
  VEI(25)/VEI(100) has lower IC separation but the most uniform 8/8 P&L uplift.
- Same-slot RV(30) percentile and z-score rankings are near-equivalent across
  30/90-session memories: Q5 IC is stronger in 7/8 cells, the continuous
  interaction strengthens in 8/8, and fixed-30/70 P&L improves in 8/8. A causal
  prior same-slot median forecast of forward RV is also informative, but in the
  **inverse** direction: Q5 has weaker absolute RSI IC in 8/8 cells. With the
  90-session forecast, median IC moves from -0.094 in Q1 to -0.039 in Q5, median
  strength changes by about -0.059, and median quintile-versus-strength rho is
  -0.90. Thus low expected clock-slot volatility is the favorable RSI-IC regime,
  whereas high current RV or volatility acceleration is favorable; the two
  conditioning variables have opposite directions. Fixed-threshold gross pips do
  not strictly follow IC because volatility scale and threshold sampling also
  change across the forecast regime.
- Trend/chop screens support high-timeframe directional-path context but not a
  trading filter. At 240 minutes, both path efficiency and variance ratio have
  stronger Q5 RSI IC and strengthening interactions in 8/8 cells; fixed-30/70 P&L
  uplift is only 5/8 and 4/8. Fifteen-minute contrasts are larger but interaction
  and P&L stability are weak/mechanically entangled with RSI; lag-1 autocorrelation
  is not a useful classifier. Evidence: `RSI_BROAD_REGIME_SWEEP_REPORT.md`,
  `RSI_BROAD_REGIME_SWEEP_SPEC.md`, `_run_rsi_broad_regime_sweep.py`,
  `rsi_broad_regime_sweep_results.json`, and the charts under
  `charts/rsi_broad_regime_sweep/`.
- **Superseded 2026-08-04 (parameterization/attribution, measurements retained):**
  the prior consumed-history joint-volatility result combined current RV and
  expected slot RV as
  `log(past_30m_RV / prior_same_slot_median_forward_30m_RV)`, preferably with a
  90-session memory. Its Q5 has stronger RSI IC than Q1 in 7/8 pair-era cells,
  better gross and expected-RV-normalized payoff in 8/8, and a strengthening
  continuous RSI interaction in 8/8 (6/8 q<0.10 within the follow-up family).
  Median Q5 metrics are IC -0.0703, 1.217 gross and 0.717 pip after a hypothetical
  0.5-pip cost, 57.6% hit rate, net session Sharpe 0.87, and 214 signals/year.
  Versus current-RV-percentile Q5 alone, the ratio improves Q5 IC in 6/8 and hit
  rate in 8/8, but median gross uplift is only +0.016 pip and frequency falls by
  26/year. A hard high-current/low-expected 3x3 corner strengthens IC in 7/8 but
  loses raw-pip P&L to high-current/high-expected in 8/8; do not use that corner
  as a P&L filter. The continuous three-way interaction is unstable, so claim a
  parsimonious surprise score, not nonlinear synergy. Evidence:
  `RSI_JOINT_VOLATILITY_REGIME_REPORT.md`,
  `RSI_JOINT_VOLATILITY_REGIME_SPEC.md`,
  `_run_rsi_joint_volatility_regime.py`, and
  `rsi_joint_volatility_regime_results.json`. A redundancy audit finds the ratio
  near-equivalent to `rv_30m_pct_90d` for within-slot ranking (exact pooled
  within-slot rho 0.968-0.977; frozen top-bin recall 0.83-0.86). Carry the
  percentile, not “surprise,” as the canonical slow RV regime. The 2024+ holdout
  remains sealed.
- **Superseded 2026-08-04 (synergy attribution, measurements retained):** the
  prior surprise x acceleration result found that 90-session
  RV(5)/RV(30) acceleration adds RSI IC within the high 30-minute-volatility-
  surprise tercile in 8/8 pair-era cells (median gain +0.0493) and gross P&L in
  6/8 (+0.350 pip). Surprise also adds IC within high acceleration in 8/8. The
  two ranks have low median within-slot correlation (-0.062). Discrete IC
  difference-in-differences is positive in 6/8 (median +0.0203), and the
  continuous three-way coefficient strengthens in 8/8, but median |t| is only
  1.47 and only 1/8 has q<0.10: call this directional, statistically weak
  synergy. The redundancy audit shows the high/high corner is more parsimoniously
  a high-RV(5) main effect; do not retain a nonlinear-synergy claim. VEI(10/50)
  is mainly additive; VEI(25/100) partly agrees but is more correlated and its
  three-way inference is weak.
- **Superseded 2026-08-04 (name/parameterization):** the prior parsimonious
  derivative was called fast volatility surprise:
  `log(RV_5m / prior_same_slot_median_forward_RV_30m)`, because raw
  `(RV30/expected_RV30)*(RV5/RV30)=RV5/expected_RV30`. Its 90-session Q5 beats
  Q1 on IC, gross P&L, and expected-RV-normalized payoff in 8/8; the continuous
  RSI interaction strengthens in 8/8 with all 8 q<0.10 within this post-hoc
  family. Median Q5 is IC -0.0958, 0.972 gross and 0.472 pip after a hypothetical
  0.5-pip cost, 57.8% hit, net session Sharpe 0.79, and 346 signals/year. Versus
  30-minute surprise Q5 it improves IC in 8/8 by +0.0219 median but gives 0.159
  fewer gross pips/signal; use fast surprise as a predictive regime and slower
  surprise as a payoff-scale benchmark. Do not put all three raw ratios in one
  model because they are algebraically dependent. The audit finds this feature
  near-equivalent to `rv_5m_pct_90d` for within-slot ranking (exact pooled
  within-slot rho 0.978-0.984); carry the percentile as the canonical fast RV
  regime. Evidence:
  `RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md`,
  `RSI_SURPRISE_ACCELERATION_INTERACTION_SPEC.md`,
  `_run_rsi_surprise_acceleration_interaction.py`, and
  `rsi_surprise_acceleration_interaction_results.json`. The 2024+ holdout remains
  sealed.
- The 2026-08-04 no-RSI audit confirms that RV level conditions generic
  short-horizon reversion, so RSI exclusivity is rejected. It does **not** kill
  incremental RSI conditioning: a post-audit full-sample clustered rank model
  controlling for trailing 1m and 30m return main effects and their regime
  interactions retains negative RSI x RV-regime coefficients in all four pairs
  (beta -0.044 to -0.093; t -2.75 to -5.74). Treat this as post-hoc diagnostic
  evidence pending a frozen test, not confirmation. Evidence:
  `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md` and
  `_run_rsi_regime_redundancy_audit.py`.
- Going forward, every RSI regime result must compare **scheduled state** with
  **first crossing**. Because the clocks have different minute-of-half-hour
  mixtures, report phase-matched crossings (especially phase :29), all-phase
  crossings with phase controls/placebos, and identical execution delays. Never
  interpret scheduled-minus-crossing without holding phase fixed. Evidence for
  the requirement: `RSI_CLOCK_CONFOUND_REPORT.md`.
- The frozen pre-2024 clock/delay kill test is now complete for canonical
  `rv_5m_pct_90d` and `rv_30m_pct_90d`. Both survive directionally. Scheduled
  Q5-Q1 gross uplift is positive in 8/8 cells for RV(5) and 8/8 for RV(30);
  all-phase first-crossing uplift is positive in 8/8 and 7/8; after shifting the
  entire 30-minute holding window one minute later it remains positive in 6/8
  and 5/8. Minute-of-half-hour/year-controlled crossing betas are positive in
  7/8 delayed RV(5) cells and 8/8 delayed RV(30) cells. Scheduled within-slot IC
  also strengthens from Q1 to Q5 after delay in 8/8 and 7/8 cells. This is
  consumed-history evidence, not holdout confirmation.
- Phase-matched first crossings are not intrinsically weaker than scheduled
  states. At zero delay their Q5 gross medians are larger, but after a one-minute
  shift they converge closely: RV(5) scheduled 0.452 versus phase-29 crossing
  0.486 pip; RV(30) 0.572 versus 0.613. Thus the relative volatility gradient
  persists, while much of the absolute base P&L level is boundary sensitive.
  All-phase crossing Q5 means remain below a hypothetical 0.5-pip round trip,
  delayed scheduled RV(5) is slightly negative after that stress, and delayed
  scheduled RV(30) is only +0.072 pip. Carry both canonical RV levels as
  provisional regime variables; make no tradability claim. Evidence:
  `RSI_RV_CLOCK_REGIME_REPORT.md`, `RSI_RV_CLOCK_REGIME_SPEC.md`,
  `_run_rsi_rv_clock_regime.py`, and `rsi_rv_clock_regime_results.json`.
- The prior-range-break result survives as a feature main effect, not as evidence
  that range breaks strengthen RSI severity. For scheduled signals, break versus
  no-break 30-minute gross means are 1.044 versus 0.279 pip (EURUSD early), 0.911
  versus 0.539 (EURUSD late), 1.052 versus 0.263 (GBPUSD early), and 0.897 versus
  0.448 (GBPUSD late). The early-era range-break main effect is BH-significant in
  both pairs (q=0.0079/0.0274), but late-era main effects are not, and all four
  scheduled 30-minute RSI-depth interaction q-values are at least 0.696. Preserve
  range break as the provisional payoff-level candidate already identified; do not
  market it as an RSI-depth amplifier.
- Path geometry supports fast re-entry/partial retracement more strongly than an
  immediate full reversal. Roughly 76%-80% of events neutralize through RSI 50
  within 30 minutes. Scheduled 30-minute impulse signals reach half retracement
  about 50% and full retracement about 22% of the time within 30 minutes, rising
  to roughly 81% and 62%-65% over four hours. First-crossing rates are higher,
  about 57%-61% half and 30%-32% full within 30 minutes, and about 85% and 70%-71%
  over four hours. These are path reaches, not executable bracket results.
- The endpoint selection null was evaluated with 100 within-year New-York-session
  re-pairings across five RSI lengths, two thresholds, two signal clocks, and four
  horizons. EURUSD observed max cluster t was 16.58 versus null 95th percentile
  3.09; GBPUSD was 17.40 versus 2.80. Neither was exceeded (Monte Carlo p floor
  1/101 = 0.0099). The maxima were scheduled RSI(7) at five minutes, reinforcing
  a generic fast mean-reversion effect rather than uniqueness of RSI(14)/30m.
- Provisional TSI comparison: canonical double-EMA TSI(25,13) has negative
  within-slot IC at every 5-120 minute horizon and in every pre-2024 sample year,
  but is consistently weaker than RSI(14). At 30 minutes, discovery mean-reversion
  IC is 0.0509/0.0534 TSI versus 0.0681/0.0719 RSI on EURUSD/GBPUSD.
- Fixed TSI +/-25 fires about twice as often as RSI 30/70. Discovery-calibrated
  thresholds of |TSI| 32.60/32.43 approximately match RSI frequency; matched TSI
  then earns only 0.192/0.141 gross pips per signal versus RSI's 0.646/0.637.
  The exposed 2021-2023 check is 0.331/0.365 versus 0.695/0.679 pips.
- TSI does not add useful information to RSI. Discovery TSI-only extremes earn
  -0.039/-0.119 pips while RSI-only extremes earn 0.935/0.984. TSI partial IC
  conditional on RSI is generally wrong-signed, whereas RSI partial IC conditional
  on TSI remains mean-reverting across every pair, era, and horizon.
- The TSI improvement hypothesis is rejected. A one-minute feature lag leaves
  discovery TSI at +0.154 EURUSD and -0.021 GBPUSD pips; five minutes leaves
  +0.017/-0.085. A hypothetical 0.50-pip round trip makes matched TSI negative in
  both pairs and eras. In 100 within-year session re-pairings, TSI's one-sided
  p-values are 0.059/0.109, while its -0.454/-0.496 pip disadvantage to RSI is
  more extreme in absolute value than every null draw (two-sided p floor 1/101).
  Evidence: `tsi_vs_rsi_mean_reversion.ipynb` and `tsi_vs_rsi_results.json`.
- Confirmed descriptive Asian-range result on the inspected pre-2024 sample:
  among days with at least 95% coverage in every user-defined ET session, the
  observed-range dual-sweep rate is 58.1% EURUSD (3,054 days; year-block 95%
  interval 55.6%-60.7%) and 59.5% GBPUSD (3,046; 56.8%-62.7%). Every individual
  year is above 50%, and requiring a 10%-of-range penetration leaves 51.5% and
  53.6%. The effect is strongly mechanical with range width: narrowest-quintile
  rates are 69%-75% versus 35%-45% in the widest quintile, depending on pair/era.
- The stronger predictive/reversal interpretation is rejected on this history.
  A within-pair/year day re-pairing null is centered above observed (EURUSD
  58.7% null vs 58.1% observed, one-sided p=0.836; GBPUSD 60.4% vs 59.5%,
  p=0.930), so the day's own Asian geometry does not create excess dual sweeps
  beyond generic later-path geometry. Session-return reversal rates are about
  48%-52% with return Spearman correlations -0.059 to +0.036, not a strong
  throughout-day reversal tendency. Nearby seven-hour anchors produce similar
  or higher dual rates, so 17:00 ET is not uniquely privileged.
- First unambiguous sweeps occur in London on 97%-98% of eligible event days.
  A subsequent bar re-enters the observed range on 98.6%, reaches its midpoint
  on 78%-79%, and later reaches the opposite side on 58%-60%; later first touches
  have much lower opposite-side rates because less day remains. Next-open fade
  returns are economically weak and asymmetric: pooled 30-minute gross midpoint
  return is +0.073 EURUSD and -0.099 GBPUSD pips; high-side fades outperform
  low-side fades, so there is no symmetric sweep-fade strategy evidence.
- EURUSD and GBPUSD are correlated rather than independent confirmations: both
  dual-sweep on 40.4% of synchronized days versus 34.6% under independence,
  dual indicators correlate 0.239, and the first side agrees 73.6% of the time.
  Exact 1,440-minute coverage retains zero days because rollover missingness is
  systematic, so all claims remain about the `observed_asian_range` proxy and
  likely overstate sweeps of the complete intended range. Evidence:
  `asian_range_sweep_reversal_exploration.ipynb` and
  `asian_range_sweep_results.json` (full run 2026-08-03).

## Decisions and constraints

- `PREDICTION_WINDOW_MIN = 30` is the default and is user-configurable.
- A New York 17:00 rollover defines the FX session. Typical daily coverage for the
  first three pairs begins at session minute 15; the quality table reports this.
- For the Asian-range notebook, the user-defined 17:00-23:59 ET interval is
  retained as the intended definition, but results are explicitly labelled an
  `observed_asian_range` proxy because the source commonly begins near 17:15 ET.
  No complete-range claim is allowed from these files without another source.
- TWAP carries the last observed typical price through missing minutes. No volume
  features are used.
- Midpoint data have no bid/ask spread. TWAP strategy output is gross plus
  hypothetical cost stress only; no net tradability claim is allowed.
- IC is reported within session slot and pooled, with yearly stability, quintile
  mean spread, and session-block intervals for top screened features.
- Each valid forward target now includes entry-to-exit holding-path extrema and
  long/short MAE and MFE in log basis points and raw pips. The parameterized
  feature lab defaults to RSI(14) mean reversion (long at/below 30, short at/above
  70) and reports clustered edge, tail, excursion, capture/giveback, yearly, and
  touch-rate diagnostics. These are midpoint-path labels, not bracket fills;
  simultaneous stop/target ordering remains unknown on one-minute OHLC.
- The RSI lab compares source (`close` versus `(O+H+L)/3`), SMA-seeded Wilder,
  EMA, and SMA smoothing, lengths 5-50, and 5-120 minute horizons. Its default
  discovery interval is 2012-2019; 2020-2023 is an already-exposed internal
  temporal check, and 2024+ remains sealed. It includes factor/heatmap summaries,
  BH-adjusted exploratory edge p-values, threshold dose response, long/short and
  regime slices, timing placebos, session-block intervals, MFE/MAE, pips, and
  hypothetical cost sensitivity.
- `rsi_fakeout_reversal_exploration.ipynb` extends the selected close/Wilder
  RSI(14) path into a pre-2024 EURUSD/GBPUSD fakeout study. It compares
  non-overlapping scheduled 30-minute states with first-crossing events under a
  30-minute cooldown; decomposes 0-1, 1-5, 5-15, and 15-30 minute returns;
  stresses delayed entry; and labels prior-range re-entry/midpoint/opposite-side,
  half/full impulse retracement, and causal RSI-50 exits. Its late 2021-2023 era
  is an internal robustness slice, not a holdout. The 2024+ data remain sealed.
- Fakeout path probabilities condition on exact continuous future-minute coverage.
  Minute highs/lows measure target reach and time only; they do not resolve
  same-bar order or establish executable bracket fills. The notebook includes a
  within-year New York-session re-pairing null that repeats the declared endpoint
  search over RSI length, threshold, horizon, and signal-clock choices.
- The clock-interaction notebook uses half-RSI-point common-support standardization
  and session-clustered clock regressions, then early-era median/IQR scaling and
  feature cutpoints applied unchanged to 2021-2023. It separates feature main
  effects from RSI-depth interaction effects, reports conditional RSI IC by
  feature bin, applies BH adjustment within each declared screen, and ranks sign
  stability across pair and era. It remains exploratory and does not open 2024+.
- Cross-pair inputs use exact synchronized timestamps and are contemporaneous common
  factor/residual features, not a lead-lag claim.

## Known risks and open questions

- The full default notebook is compute-heavy because it reads about 18.2 million
  pre-holdout minute rows and runs annual walk-forward models.
- Pre-2024 feature/model selection is multiple searching. Any survivor needs a
  frozen primary metric and kill rule before the 2024+ holdout is opened.
- A calibrated spread/slippage series is required before economic interpretation.
- The direction result is economically small and could be sensitive to adjacent
  one-minute midpoint microstructure. Run a feature-timing placebo (at least one
  additional minute of lag) and block-based inference before promotion.
- The four USD-quoted pairs are correlated tests, not four independent markets.
- The fakeout notebook passed a real-data EURUSD smoke execution and its full
  EURUSD/GBPUSD pre-2024 Sections 1-8 were subsequently executed and interpreted.
  The saved notebook currently contains code but not persisted execution outputs.
- The clock-interaction notebook's full EURUSD/GBPUSD run is now executed and
  interpreted. Its interaction hypothesis is rejected; the remaining clock effect
  and range-break main effect require a frozen experiment rather than more ranking
  of this consumed feature screen.
- The RSI-50 variable-exit mean excludes the roughly 1%-4% of signals that do not
  neutralize within the available four-hour path and permits overlapping signals.
  It is therefore a conditional path diagnostic, not yet an unbiased strategy
  return. A strategy test must apply a timeout exit and portfolio position policy.
- Baseline MFE and MAE are large relative to gross expectancy (approximately
  5-8 pips each versus less than one pip endpoint edge). At a hypothetical
  0.50-pip round trip, unconditioned scheduled means fall to 0.137-0.195 pips
  with cluster t only 1.02-1.56; first-crossing means are negative except under
  lower costs. Executable spread/slippage data remain a binding requirement.
- The 87-feature full model is highly redundant. Group ablations are required to
  identify whether cross-pair, session/path, or volatility-shape features add
  durable information beyond the compact core.

## Next actions

1. Before opening the holdout, specify and test a pre-2024 candidate around the
   scheduled RSI-extreme plus prior-30-minute range break. Add condition-specific
   1-60 minute return decomposition, delayed entry, cost, MAE/tail, and matched
   range-break-without-RSI controls.
2. Evaluate causal RSI-50, range-reentry, and partial-retracement exits with a
   mandatory timeout, one-position/overlap policy, and adverse same-bar ordering;
   do not infer a strategy from conditional touch/exit rows.
3. Run feature-family ablations for absolute returns and retain the smallest model
   that preserves incremental annual IC.
4. Calibrate executable bid/ask costs and assess turnover-aware decision rules;
   do not use the current TWAP baseline as a candidate.
5. Register the promoted experiment, freeze code and kill rules, then open the
   2024+ holdout once.

## Promotion candidates

- Provisional only: compact signed mean-reversion and absolute-volatility models.
  Neither is independently confirmed; neither is approved for live use.
