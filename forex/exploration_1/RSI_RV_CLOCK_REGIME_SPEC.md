# RSI canonical-RV regime x signal clock — frozen specification

## Status and purpose

- Post-hoc exploratory kill test requested after the volatility-regime
  redundancy audit and the established scheduled-clock phase confound.
- Tests whether canonical RV(5) and RV(30) same-slot percentiles condition RSI
  under both scheduled-state and first-crossing clocks, and whether the regime
  gradient survives moving the traded window one minute away from the signal.
- EURUSD, GBPUSD, AUDUSD, NZDUSD clean one-minute midpoint OHLC, 2012-2023.
  The 2024+ holdout remains sealed.

## Features

- `rv_5m_pct_90d`: exact trailing five-minute realized volatility, ranked
  causally against the prior 90 observations at the same New York session
  minute; minimum 60 prior observations.
- `rv_30m_pct_90d`: the analogous trailing 30-minute RV percentile.
- Pair-specific quintile cuts are fitted on 2012-2020 scheduled observations
  and applied unchanged to all clocks and to 2021-2023.

## RSI and clocks

- SMA-seeded Wilder RSI(14), reset and re-warmed after minute gaps.
- Extreme side: long when RSI <= 30; short when RSI >= 70.
- `scheduled_state`: every extreme observation at New York :29/:59.
- `first_crossing_all`: first minute entering either extreme, subject to a
  30-minute cooldown, at all minute-of-half-hour phases.
- `first_crossing_phase29`: the subset of accepted crossings occurring at phase
  :29; this holds sampling phase fixed against scheduled state.
- `scheduled_fresh`: scheduled observations whose extreme age is zero; a
  no-cooldown diagnostic of the exact fresh state at the scheduled phase.

Never interpret scheduled-minus-all-crossing as a signal-quality difference;
their phase mixtures differ. The phase-matched and phase-controlled arms decide
clock comparisons.

## Execution

- Base: decision at completed minute t, entry at exact open t+1, exit at exact
  open t+31 (30-minute hold).
- Delayed: same signal and regime observed at t, entry at exact open t+2, exit
  at exact open t+32. This keeps the 30-minute hold and moves the whole traded
  window one minute later.
- Gross midpoint pips plus hypothetical 0.5-pip cost stress. No bid/ask or
  deployability claim.

## Metrics and frozen interpretation

- By pair, 2012-2020/2021-2023 era, clock, feature, quintile, and delay: signal
  count/frequency, mean gross and stressed pips, session-clustered t, hit rate,
  session-summed Sharpe, drawdown, and Q5-Q1 uplift.
- First-crossing all-phase regressions include minute-of-half-hour and year fixed
  effects with session clustering.
- Scheduled full-range within-slot RSI IC is reported as a Rule-23 bridge to the
  broad sweep; event clocks are evaluated on signed P&L because crossing RSI has
  intentionally restricted support near the threshold.
- A canonical RV regime survives the phase kill test only if Q5-Q1 gross uplift
  has the same sign in at least 6/8 pair-era cells for both scheduled and
  all-phase crossings, remains positive in at least 5/8 after the one-minute
  delay, and the phase-controlled crossing coefficient is positive in at least
  6/8. Phase-29 crossings are a sparse mechanism check, not the primary vote.
- Failure of the delayed and phase-controlled arms supersedes the regime family
  as likely boundary microstructure. Passing remains consumed-history evidence,
  not confirmation.

