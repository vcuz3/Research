# Full-range RSI regime test

## Status and scope

- Status: frozen before the material run, but the primary EURUSD VEI pattern was
  already inspected and is therefore consumed exploratory evidence.
- Data: pre-2024 scheduled 30-minute decision rows for EURUSD, GBPUSD, AUDUSD,
  and NZDUSD. The 2024+ holdout remains sealed.
- Outcome: next-open to exact 30-minute future-open signed log return in basis
  points.
- Primary estimand: the magnitude of the negative Spearman association between
  raw RSI(14) and signed future return. This is directional mean-reversion IC,
  not IC against absolute returns and not RSI-depth IC inside 30/70 extremes.

## Primary VEI test and kill rule

Use early-period (2012-2020) pair-specific VEI-percentile quintile cutpoints and
apply them unchanged to 2021-2023. Report pooled and within-session-slot
Spearman IC by quintile. Fit a within-slot rank regression of future-return rank
on RSI rank, regime rank, and their interaction, clustering standard errors by
New York trading session.

The claim that higher VEI strengthens full-range RSI predictive value passes
this pre-holdout stability screen only if:

1. Q5 minus Q1 mean-reversion IC strength is positive in every pair and era;
2. the RSI x VEI interaction has the strengthening sign in every pair and era;
3. the result is not confined to a single time block or direction; and
4. economic interpretation remains gross and provisional pending costs and a
   genuinely uninspected holdout.

Failure of either sign-stability condition rejects the broad claim. Mixed
statistical significance with stable signs is inconclusive rather than a pass.

## Secondary regime screen

Screen causal volatility, path-shape, session-state, and time-of-day variables.
Continuous regimes reuse early-period quintile cutpoints in the late era. Apply
Benjamini-Hochberg adjustment within each pair/era screen. A regime is only a
promotion candidate when its interaction sign is consistent across all four
pairs and both eras and its Q5-Q1 effect is economically coherent. Correlated
features and correlated USD pairs are not independent confirmations.

