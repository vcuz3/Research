# RSI joint current/expected volatility regime — frozen specification

## Status and scope

- Post-hoc exploratory follow-up to the broad regime sweep. The separate
  current-RV and expected-slot-RV effects were already observed, so this is not
  independent confirmation.
- EURUSD, GBPUSD, AUDUSD, and NZDUSD one-minute midpoint OHLC, 2012-2023.
- Pair-specific 2012-2020 cutpoints are applied unchanged to 2021-2023.
- The 2024+ holdout remains sealed.
- New York time controls the 17:00 session boundary and half-hour decision slots.
- Decision, entry, exit, RSI, return, and P&L definitions are unchanged from
  `RSI_BROAD_REGIME_SWEEP_SPEC.md`.

## Joint regime

For both 30- and 90-session memories:

1. Current volatility is past 30-minute realized volatility expressed as its
   causal same-New-York-slot percentile.
2. Expected volatility is the causal median of the next 30-minute realized
   volatility observed at that slot over prior sessions.
3. Each variable is divided into pair-specific terciles using 2012-2020
   cutpoints. This gives a 3x3 matrix with enough observations per cell.
4. The primary candidate is current-RV T3 / expected-RV T1. The adverse control
   is current-RV T3 / expected-RV T3.

The continuous companion is

`log((past 30-minute RV in bp) / expected next-30-minute RV in bp)`.

It is evaluated in frozen quintiles and in a clustered rank regression containing
RSI interactions with current RV, expected RV, and their product.

## Metrics

- Primary: within-slot Spearman RSI IC strength (`-IC`) in every joint cell and
  the candidate-minus-adverse difference by pair and era.
- Secondary: fixed RSI 30/70 signals/year, gross pips/signal, hypothetical 0.5-
  and 1.0-pip cost stress, hit rate, session-summed Sharpe, maximum drawdown, and
  MFE/MAE.
- Diagnostics: cell coverage, candidate/adverse sample and signal counts,
  continuous three-way interaction with session-clustered inference, and 30-
  versus 90-session agreement.

## Frozen interpretation rule

- Broad support requires stronger candidate IC in at least 6/8 pair-era cells
  for the 90-session primary version, the same direction in the 30-session
  sensitivity, and no critically sparse candidate/adverse cell.
- Fewer than 6/8 favorable cells, reversal between memories, or concentration in
  one pair/era kills the proposed joint filter.
- P&L alone cannot rescue a failed IC result. Gross midpoint P&L is diagnostic,
  not a deployment claim.

