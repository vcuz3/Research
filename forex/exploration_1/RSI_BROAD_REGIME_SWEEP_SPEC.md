# RSI broad regime sweep — frozen specification

## Status

- Broad exploratory sweep requested after the full-range RSI x VEI result was
  observed. This is consumed-history robustness work, not confirmation.
- Data: EURUSD, GBPUSD, AUDUSD, and NZDUSD one-minute midpoint OHLC, 2012-2023.
- The 2024+ holdout remains sealed.
- New York time controls the 17:00 session boundary, decision slots, same-slot
  normalizations, and time-of-day reporting.

## Clock, target, and signal

- Decision: completed New York half-hour bar (`:29` or `:59`).
- Entry: next available exact one-minute open.
- Exit: open exactly 30 minutes after entry.
- IC estimand: within-New-York-session-slot Spearman correlation between raw
  Wilder RSI(14) and signed 30-minute return. More-negative IC means stronger
  directional mean reversion.
- P&L diagnostic: long when RSI <= 30 and short when RSI >= 70, with endpoint
  gross pips, session-clustered t, hit rate, session-summed annualized Sharpe,
  drawdown, MFE/MAE, trade frequency, and hypothetical 0.5-pip cost stress.

## Declared sweep

### Volatility acceleration

For each raw measure, compute a causal same-New-York-slot percentile from the
previous 30 or 90 observed sessions (minimum 2/3 populated):

- Wilder ATR ratios: 25/100, 10/50, 5/25.
- realized-volatility ratios: 5/30, 10/50, 25/100.

### Volatility level/ranking

- Past 30-minute realized volatility, expressed as causal same-slot percentile
  and prior-window z-score, using 30 and 90 sessions.
- Prior same-slot median 30-minute forward realized volatility, using 30 and 90
  sessions. Only prior sessions' already-realized labels enter the median.

### Trend versus chop

At 15, 60, and 240 minutes, compute:

- path efficiency: absolute endpoint move / total absolute path;
- variance ratio: squared endpoint move / realized variance;
- lag-1 return autocorrelation.

Each is converted to a causal 90-session same-slot percentile. High percentile
means more trend-like for the declared measure; low means more chop-like.

## Comparison and reporting rules

- Pair-specific 2012-2020 quintile cutpoints are applied unchanged to 2021-2023.
- Report every quintile, Q5-Q1 IC-strength change, clustered rank-interaction
  inference, and P&L diagnostics by pair and era.
- Apply Benjamini-Hochberg adjustment within each pair/era interaction screen.
- A broad regime family is robust only when the Q5-Q1 IC direction and rank
  interaction agree across most pair/era cells, not merely when one selected
  specification has a small p-value.
- Compare 30 versus 90-session memories within the same raw definition and
  transform. Treat correlated variants as one family, not independent evidence.
- Report New York hourly behavior and flag rollover-hour midpoint results as
  non-actionable until bid/ask and missingness checks validate them.
- No strategy or deployability claim is allowed from gross midpoint P&L.

