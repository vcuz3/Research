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
5. ~~**(short,long) surface + normalisation.**~~ **Done — folded into Study F (EXP-0005).**
   At matched selectivity (10,50) with past_win=30 is the best cell on both markets and
   past_win is load-bearing; the percentile-rank normalisation is WORSE than the raw ratio
   (VEI's information is in its absolute level, not its time-of-day-relative rank). Do not
   re-run.
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
11. **Expansion onset vs late-chase, and volume participation.** Everything so far uses
    the VEI *level*; the *first crossing* of the threshold in a session is a different
    object, and Study C's "low VEI keeps decelerating" says nothing about the moment
    expansion begins. Pairs with a participation split (`volume` is loaded but used by
    nothing here): expansion on rising volume = information, on falling volume = a
    liquidity vacuum. F3c's per-slot detail hints at this — *rare* expansions (morning)
    show the largest contrast.
12. **The 13:30 slot.** F3a/b found a VEI-independent momentum effect at the 13:30
    decision on both markets (+0.101 NQ / +0.108 ES, vs ≈0 at nearly every other slot),
    and it is also the largest high-VEI contrast cell. Unexplained; a candidate
    intraday-seasonality finding in its own right, adjacent to noise_vwap EXP-0034's
    phase-sensitivity result. Descriptive first — do not treat one slot as an edge.

### On applying it (vol's role in every strategy)
7. **Sizing / risk-targeting.** Even if VEI barely improves the vol forecast (B), test
   VEI-scaled position sizing (cut size when VEI spikes) for drawdown/tail control on an
   existing positive strategy — a risk lever, not an alpha claim (report per rule 22).
8. **Event / open behaviour.** Characterise VEI around the RTH open and scheduled
   macro releases; does a VEI spike mark exploitable post-event continuation?
9. **Cross-instrument VEI divergence.** NQ vs ES VEI gap — does one index's vol
   expanding while the other's is calm carry information (a re-pairing null gate)?

## Standing cautions

- Every promotion needs a preregistered kill test + a claim-matched null run through the
  full pipeline (RULES 17/24). A descriptive IC or regime split is a screen (rule 26).
- Prior from noise_vwap: the momentum breakout there is volatility-INDEPENDENT and every
  vol-selectivity screen (RVOL/gap/Hurst/ATR-buffer/VEI-gate) was a turnover lever, not
  alpha. A VEI edge must beat that prior by monetizing at the portfolio/Sharpe level,
  not just improving per-trade quality.
