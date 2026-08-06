# RSI volatility-surprise x acceleration — frozen specification

## Status and data

- Post-hoc exploratory follow-up after separate surprise and acceleration
  effects were observed. It is not independent confirmation.
- EURUSD, GBPUSD, AUDUSD, NZDUSD one-minute midpoint OHLC, 2012-2023.
- New York 17:00 sessions; decisions at :29/:59; next-minute-open entry and
  exact 30-minute open exit. The 2024+ holdout remains sealed.
- Pair-specific 2012-2020 cutpoints are applied unchanged to 2021-2023.

## Features

- Volatility surprise:
  `log(past_30m_RV / prior_same_slot_median_forward_30m_RV)`.
- Primary acceleration: RV(5)/RV(30) same-slot percentile.
- Slower controls: VEI ATR(10)/ATR(50) and ATR(25)/ATR(100) same-slot
  percentiles.
- Run matched 30- and 90-session memories.

## Tests

1. Frozen 3x3 surprise-tercile x acceleration-tercile matrices.
2. Primary contrast: high surprise/high acceleration versus high surprise/low
   acceleration.
3. Discrete IC and P&L difference-in-differences across the four corner cells.
4. Clustered rank regression with RSI main effect, both regime main effects,
   both RSI two-way interactions, and `RSI x surprise x acceleration`.
5. Raw and within-slot Spearman dependence between the two regime variables.

Report within-slot RSI IC, fixed RSI 30/70 gross and 0.5-pip stressed P&L, hit
rate, session Sharpe, frequency, MFE/MAE, drawdown, and expected-RV-normalized
payoff by pair and era.

## Frozen interpretation

- **Synergy:** positive IC difference-in-differences and strengthening
  continuous three-way coefficient in at least 6/8 pair-era cells for the
  primary 90-session test, with 30-session and VEI controls broadly agreeing.
- **Additive complementarity:** acceleration improves IC within high surprise
  in at least 6/8, dependence is not excessive, but the difference-in-
  differences or three-way term is unstable.
- **Redundancy/no incremental value:** acceleration improves IC within high
  surprise in fewer than 6/8, reverses across memories, or has absolute rank
  correlation above 0.70 without incremental performance.
- P&L cannot rescue a failed IC interaction. All inference remains
  consumed-history exploratory evidence.

