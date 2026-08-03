# VEI Exploration — Idea Backlog (dimension map)

Uncommitted ideas for exploring the Volatility Expansion Index. Brainstorming, not
findings. Promote a surviving idea to `experiments/hypotheses/HYP-XXXX.md` before any
material run. Done items link to the run.

## Done (see reports/FINDINGS.md)

- [x] **Smoothing** — ATR estimator (SMA / Wilder / EMA) + ratio EMA. Wilder wins big.
  (EXP-0001, Study A)
- [x] **Vol forecasting** — does the VEI ratio add over the vol level? Marginal.
  (EXP-0002, Study B)
- [x] **Contraction→expansion** — coiled-spring test intraday. Not supported at 30–60m.
  (EXP-0002, Study C)
- [x] **Regime selector** — does VEI switch momentum vs mean-reversion? Momentum turns
  on when VEI>1.1, both markets. (EXP-0003, Study D)
- [x] **Momentum-in-high-VEI strategy** — preregistered promotion of Study D. Mechanism
  CONFIRMED (gross dose-response high≫low, cross-market) but edge REJECTED (daily
  Sharpe ≈0, sub-cost; kill-test 1 failed). (EXP-0004, HYP-0001)
- [x] **Term structure + time-of-day audit** — Study D is NOT a clock effect (within-slot
  contrast retains 106%/105% of pooled, both markets); momentum info is FRONT-LOADED
  (peaks H=5–10, gone by 90–120), correcting E's "strengthens with hold"; raw level beats
  a same-slot percentile at matched count; VR shows no regime difference. Folds in item 5
  (the (short,long) grid + percentile normalisation). (EXP-0005, HYP-0002, Study F)

## Next dimensions (proposed, unstarted)

### On the strongest lead (D)
1. ~~**Preregistered momentum-in-high-VEI strategy test.**~~ **Done — EXP-0004/HYP-0001.**
   Mechanism confirmed, edge rejected.
2. **Short-horizon mean-reversion side.** D found no MR at 30 min. Re-run the
   trailing→forward correlation at 1/3/5-min horizons by VEI regime — a fade edge, if
   any, lives in calm/contraction at fast horizons (pairs with the momentum switch).
   *Partly informed by Study F:* at H=5 the low/calm regimes are flat (NQ +0.003/−0.019,
   ES −0.002/−0.034) at the 30-min decision clock, so any fade would need a faster
   decision clock than the one measured, not just a shorter horizon.
3. **VEI as a strategy ALLOCATOR.** Combine: run the momentum leg in high VEI and the
   MR leg in low VEI on the same tape; does regime-switching beat either alone?

### On the indicator itself
4. **Timescale / squeeze at daily cadence.** The coiled-spring (C) may be a multi-day
   phenomenon. Build a DAILY VEI (e.g. ATR(5d)/ATR(20d)) and test whether a multi-day
   squeeze (VEI in a low percentile for k days) precedes a daily-range expansion /
   directional breakout the next day. **Now the biggest untouched dimension** — VEI is
   intraday-only with a session reset, so its "long" leg is only 50 *minutes*. The shared
   parquets already carry full 24h coverage (tod 0–1439, 2011→2026), so no new data pull
   is needed, only a new loader (+ a rule-9a gate on overnight coverage and rolls).
   Secondary payoff: a day-level VEI is a one-label-per-session regime classifier, which
   fits gating an existing book far better than Study E's 0.7-bets-per-session tilt.
5. ~~**(short,long) surface + normalisation.**~~ **Done — EXP-0005, superseded in part by
   EXP-0006/0009.** The old claim that percentile normalisation is worse was a warm-up-bug
   artefact. EXP-0009 established the causal trailing same-slot z-score as the calibrated
   regime label at no information cost. Do not re-run this surface on consumed history.
6. **Threshold hysteresis.** The regime switch (D) at a hard VEI=1.1 line will chatter;
   test entry/exit hysteresis bands around the momentum-on threshold. Expect a small
   effect — Study A's Wilder AC1 of 0.55 means the chatter is already modest.

### New leads from Study F (EXP-0005)
10. **Regime-persistence exit.** Replace Study E's arbitrary fixed horizon with "hold
    while VEI stays above T, exit when it decays below" (hysteresis per item 6). Causal
    and rule-14-compliant if the update clock is explicit; non-overlapping by
    construction, which also sidesteps the H=60 estimand problem. Caveat from F1: the
    information decays after ~30–60 min, so this is a *cost-efficiency* lever more than
    an edge lever — preregister it that way.
11. ~~**Expansion onset vs late-chase, and volume participation.**~~ **Done — EXP-0010 /
    HYP-0007.** Pooled mechanism confirmed: volume-confirmed first crossings have positive
    momentum alignment while unconfirmed crossings are negative, and mature-high cells
    are weak on both markets. Standalone alpha rejected: primary H=10 t +0.19 NQ / -0.76
    ES, with strong era dependence (negative 2011–19, positive 2020+). Preserve only as
    a possible veto/allocator input for an independently validated strategy.
12. **The 13:30 slot.** F3a/b found a VEI-independent momentum effect at the 13:30
    decision on both markets (+0.101 NQ / +0.108 ES, vs ≈0 at nearly every other slot),
    and it is also the largest high-VEI contrast cell. Unexplained; a candidate
    intraday-seasonality finding in its own right, adjacent to noise_vwap EXP-0034's
    phase-sensitivity result. Descriptive first — do not treat one slot as an edge.

### On applying it (vol's role in every strategy)
7. ~~**Sizing / risk-targeting.**~~ **Done — EXP-0013 / HYP-0010. CLOSED.** Tested with
   the stronger EXP-0011 forecast rather than VEI: the per-trade standardised edge
   `net/forecast` on the frozen noise_vwap book is FLAT in the causal same-slot forecast
   percentile (slope −0.005 NQ / +0.048 ES, both CIs spanning 0, signs disagreeing).
   Expectancy is proportional to forecast volatility, so sizing at `1/forecast` is the
   complete and optimal use and no tilt remains. The forecast is also NOT distinguishable
   from the trailing ATR14 already deployed as the sizing denominator. Do not re-open
   this as an alpha lever; risk-targeting remains a survival tool (rule 22).
8. **Event / open behaviour.** Characterise VEI around the RTH open and scheduled
   macro releases; does a VEI spike mark exploitable post-event continuation?
   *Superseded in priority by item 13, which is the same intuition made testable.*
9. **Cross-instrument VEI divergence.** NQ vs ES VEI gap — does one index's vol
   expanding while the other's is calm carry information (a re-pairing null gate)?

### New leads from EXP-0013 (the forecast has skill but no application here)
13. **The scheduled-calendar residual — the highest-value untouched channel, and after
    EXP-0016 the ONLY one aimed at an axis that can still move: every feature tested so far
    (the two-input core, EXP-0011's multi-horizon set, EXP-0016's decorrelated six and its
    redundant-level control) is a function of PAST PRICE, and they all converge to the same
    level-IC ceiling. Scheduled events are the one information source none of them contain.
    Originally, and after
    EXP-0015 a TARGETED one.** The number to beat is now specific: the core's expansion-call
    log-MSE skill over persistence is only **+0.008 NQ / +0.061 ES** (against +0.300/+0.211
    on contraction calls), i.e. it ranks expansions correctly but cannot size them. Scheduled
    events are the anticipatable source of volatility EXPANSION, so this is the one channel
    aimed straight at the weak cell. EXP-0011
    showed six extra realised-volatility state variables buy only +0.009 IC, i.e. the
    realised-vol channel is close to saturated; more lags will not help. The obvious
    MISSING information is **scheduled** volatility, which is knowable in advance and
    point-in-time safe: FOMC, CPI/NFP and other 08:30 releases, 10:00 releases, opex,
    quarter-end, index rebalance. First step is diagnostic and cheap — rank the two-input
    core's largest forecast errors and measure how much of the residual is
    calendar-clustered, per era and per slot. Only if a material share is should a
    calendar feature be built. Unlike volatility persistence, a scheduled dislocation is
    the kind of thing that can plausibly monetize.
    **UPDATE (EXP-0017): do NOT use VIX as the proxy for this channel.** Spot VIX was
    tested as exactly that and failed where the mechanism most strongly predicted it would
    succeed: at the 13:59 slot forecasting the 14:00–14:30 FOMC window its contribution is
    +0.0004 NQ / +0.0237 ES, the bottom of all eleven slots, while its best slots are the
    information-poor morning ones — anchoring after a shock, not anticipation of an event.
    The residual-ranking diagnostic this item asks for is already built
    (`scripts/hyp_0014b_premium_cell.py` §4) and shows the core's error tail is where any
    new information must land: VIX helps there (+0.10..+0.13 on deciles 9–10) while
    *hurting* the easy deciles. Item 13 therefore still stands, but it needs an **explicit
    event calendar**, or a tenor-matched implied series (VIX1D/VIX9D) — the one instrument
    that could carry near-term scheduled risk, which 30-day VIX structurally cannot.
14. ~~**Downside semivariance as the target.**~~ **Done — EXP-0014 / HYP-0011. Channel
    CLOSED.** Claim A (transfer) CONFIRMED on both markets: the frozen recipe applied
    unchanged to `fwd_dsv_bp` retains 92.3% (NQ) / 92.8% (ES) of the within-slot IC delta
    it achieves on total RV, positive in all eleven tested years — so the leg a stop or
    barrier calculation needs is available at no extra cost, and the downside leg is only
    marginally harder than the upside one. Claim B (asymmetry) REJECTED on both: all four
    `fwd_down_share` cells span zero and the markets disagree on which candidate is
    better. The degenerate control settles it more firmly than the CIs — the realised
    down-share is a constant near 0.494 whose per-slot means span only 0.486–0.500, and
    subtracting its causal trailing same-slot median *increases* the variance by ~2%.
    **Downside volatility is total volatility times one half.** The noise_vwap EXP-0022
    drift trap was checked explicitly and there is no drift channel either. Do not
    revisit the asymmetry on this pair at this horizon.
15. **A decision-shaped target: P(|move| ≥ d) instead of E[RV].** A conditional mean is
    not what any barrier decision consumes. Validate the QUANTILE calibration of the
    two-input core (pinball loss, PIT histogram), especially the right tail, and convert
    it into a barrier-reachability probability over the actual holding window. This is
    the only bridge from "forecast" to "trade" that survives EXP-0013, because EXP-0013
    closed the conditional-mean route specifically.
16. ~~**The disagreement set.**~~ **Done - EXP-0015 / HYP-0012. PASS, and it
    reframed EXP-0012.** The core IS a timing tool: within-slot IC between the predicted
    and realised log-change from trailing 30-minute RV is +0.377 (NQ) / +0.390 (ES), the
    preregistered expansion-only gate clears at +0.220/+0.238, and skill rises
    MONOTONICALLY with the size of the disagreement (decile 1->10: IC +0.033->+0.643).
    But the run's larger result is that PERSISTENCE is a far harder benchmark than
    seasonality: within-slot IC vs realised RV is model +0.881, persistence +0.867,
    seasonality +0.419, so EXP-0012's ~+0.47 delta over the same-slot median is only
    +0.013 over persistence. Levels are nearly all persistence; deltas are where the
    model lives. Weakest cell = expansion MAGNITUDE (log-MSE skill over persistence
    +0.008 NQ / +0.061 ES), which is exactly what item 13 should improve.
17. ~~**Trade volatility as the object itself — DATA-BLOCKED.**~~ **Partly DONE —
    EXP-0017 / HYP-0014. The data block is LIFTED and the forecast-side question is
    ANSWERED; the traded-object side remains open.** The premise was wrong on one point:
    `futures/data/vix/` already held ten contiguous TradingView `CBOE_DLY_VIX, 15` exports
    covering 2011-08-01..2026-07-17 (101,981 bars, zero duplicate timestamps), so an
    intraday implied series did exist. Joined causally (`core/vix.py`, staleness 0 min on
    99.95% of rows), VIX carries real incremental forward-vol information — within-slot IC
    delta +0.0034 NQ / +0.0063 ES, positive in 11/11 years and 11/11 slots on both markets
    — but on the declared decision metric it is **beaten by `past_rv30_bp` alone**
    (+0.0656/+0.0972 against +0.0717/+0.1061) and beaten more decisively by three redundant
    realised-vol windows (+0.1069/+0.1311). **And the mechanism is reversed:** VIX pays
    most where implied is unusually CHEAP (just after a realised-vol spike, where the core
    over-extrapolates) and least at the FOMC window — an ANCHOR, not an ANTICIPATOR.
    Still open, and now better specified: pricing a forecast against an implied benchmark
    needs a **tenor-matched** series (VIX1D/VIX9D) or real option quotes; spot 30-day VIX
    cannot express near-term scheduled risk, which is exactly where it failed.
18. **Rerun the EXP-0011 shuffled-target placebo on Part B.** The Part-A placebo did not
    centre at zero (null mean +0.0101 NQ / +0.0042 ES vs observed +0.0192 / +0.0160), and
    NQ's confirmed OOS delta of +0.0088 sits inside that Part-A null band. The frozen
    `oos_prediction_cache` makes this an evaluation-only rerun — no refit, no
    specification change — so it cannot be re-tuning. Until it is run, EXP-0011's
    multi-horizon INCREMENT should read "qualified-confirmed", not "confirmed". Does not
    affect the adopted two-input core, which never depended on the increment.

19. **Re-score EXP-0011's ACTUAL multi-horizon set on the expansion cell.** EXP-0016
    showed the LEVEL axis is saturated at +0.009..+0.011 for every feature set tried, so
    the metric EXP-0011 used to decline the multi-horizon variables could not discriminate
    — while the expansion-magnitude cell moved from +0.006/+0.056 to +0.100/+0.120 for a
    three-variable redundant analogue. EXP-0011's own six variables were never measured on
    that cell. Evaluation-only on frozen predictions if they can be regenerated; cheap,
    and it decides whether the "confirmed but not adopted" ruling was made on the wrong
    axis. Note this cannot be re-tuning: no feature or parameter changes.
20. **Choose the scoring metric BEFORE the next feature test, and always run the redundant
    control.** Two decisions in this project have now been taken on a metric that could not
    discriminate: `IC_fwdvol` (finding H, retired) and level IC for feature selection
    (finding P). Before any further feature work, declare a decision-shaped metric that is
    demonstrably still moving — the expansion-call log-MSE skill over persistence is the
    obvious candidate — and pair every clever candidate with a deliberately REDUNDANT
    control set. In both cases the degenerate control was the most informative arm in the
    run.

## Standing cautions

- Every promotion needs a preregistered kill test + a claim-matched null run through the
  full pipeline (RULES 17/24). A descriptive IC or regime split is a screen (rule 26).
- Prior from noise_vwap: the momentum breakout there is volatility-INDEPENDENT and every
  vol-selectivity screen (RVOL/gap/Hurst/ATR-buffer/VEI-gate) was a turnover lever, not
  alpha. A VEI edge must beat that prior by monetizing at the portfolio/Sharpe level,
  not just improving per-trade quality.
- **Do not open a sixth volatility-overlay experiment on the noise_vwap book.** Entry
  gate (EXP-0035/0036), exit cadence (EXP-0019), adaptive stop width (EXP-0032),
  day-level sizing (EXP-0040) and intraday entry-level sizing (EXP-0013) have all been
  rejected. EXP-0013 supplies the mechanical reason: the noise-band entry rule is itself
  a volatility filter, already placing ~35% of its trades in the top forecast-volatility
  quintile, so an overlay re-spends information the entry has already spent. A new
  overlay proposal needs a mechanism that is not volatility level, expansion, or scale.
- **A saturated metric cannot select between candidates.** EXP-0016: three unrelated
  feature sets — six redundant multi-horizon variables, four orthogonal new dimensions,
  and three redundant level proxies — all buy +0.009..+0.011 of within-slot level IC on
  both markets. When every candidate scores the same, the score is measuring the target's
  ceiling, not the candidates. Check that the metric MOVES before searching on it, and run
  the deliberately redundant/degenerate control alongside the clever one; in this project
  it has twice been the arm that decided the run.
- When a book has a low hit rate and a skewed P&L, do not read a **rank** IC of a
  conditioning variable against per-trade P&L: it tracks the median trade, so a pure
  scale effect prints a large negative IC while expectancy is flat (EXP-0013 measured
  −0.36 NQ / −0.32 ES this way). Use the mean/slope in standardised units.

## IDEA-0001 — Legacy Wilder seed as an accidental opening-condition feature

- Created: 2026-07-26
- Observation: repairing the Wilder seed reduced Study D even though the legacy and
  repaired `VEI>1.10` sets overlapped by ~92%. The few legacy-only observations began
  with unusually quiet first bars and showed strong historical continuation; the larger
  repaired-only set began with unusually large first bars and showed negative
  continuation.
- Proposed mechanism: first-observation seeding accidentally encodes the shape of the
  opening transition. A quiet first minute followed by expansion lifts the fast/slow
  ratio; an opening shock followed by cooling depresses it. The bug may therefore act as
  an undocumented opening-condition filter.
- Expected improvement: not to restore the bug, but to extract and test an explicit,
  causal opening feature alongside repaired VEI.
- Main artifact risk: the motivating fringe is only 23 NQ / 40 ES observations and was
  found post-hoc; a few sessions, time-of-day composition, or correlated sibling-market
  dates could explain it.
- Motivating evidence: EXP-0006 plus the user-requested read-only boundary diagnostic.
- Status: promoted to HYP-0004
