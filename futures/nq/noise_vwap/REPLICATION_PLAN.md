# Intraday Momentum Noise Area + VWAP Replication Plan

## Sources Reviewed

- `4824172.pdf`: Zarattini, Aziz, and Barbon, "Beat the Market: An Effective Intraday Momentum Strategy for S&P 500 ETF (SPY)", version dated September 22, 2025.
- Quantitativo article: "Intraday Momentum for ES and NQ"  
  https://www.quantitativo.com/p/intraday-momentum-for-es-and-nq
- Local data inventory under `futures/`.

## Research Summary

The paper studies an intraday time-series momentum strategy originally applied to SPY. The core idea is that meaningful intraday trends begin when price moves far enough away from its normal same-time-of-day fluctuation from the regular trading hours open. The authors call this normal fluctuation zone the `Noise Area`.

For each trading day and each intraday minute, the strategy estimates the typical absolute move from the 09:30 ET open using prior sessions. In the paper, the default lookback is 14 days:

```text
move[t-i, HH:MM] = abs(close[t-i, HH:MM] / open[t-i, 09:30] - 1)
sigma[t, HH:MM] = average(move[t-1 ... t-14, HH:MM])
```

The upper and lower Noise Area boundaries are built from today's open, with an adjustment for overnight gaps:

```text
upper[t, HH:MM] = max(open[t, 09:30], close[t-1, 16:00]) * (1 + sigma[t, HH:MM])
lower[t, HH:MM] = min(open[t, 09:30], close[t-1, 16:00]) * (1 - sigma[t, HH:MM])
```

The strategy is trend-following:

- Go long when price is above the upper Noise Area.
- Go short when price is below the lower Noise Area.
- Stay flat when price remains inside the Noise Area.
- Evaluate trade decisions only at semi-hourly timestamps: `HH:00` and `HH:30`.
- Close all positions by the RTH close.

The initial paper version exits on a cross of the opposite Noise Area boundary. The improved version tightens risk by using the current Noise Area boundary plus RTH VWAP as a trailing stop:

```text
long_stop[t]  = max(upper[t], VWAP[t])
short_stop[t] = min(lower[t], VWAP[t])
```

For a long, exit when price crosses below `long_stop`. For a short, exit when price crosses above `short_stop`. VWAP is computed using only regular trading hours data.

The paper also applies dynamic sizing. It targets a fixed daily volatility using the recent realized daily volatility, with a leverage cap:

```text
exposure_multiplier[t] = min(leverage_cap, target_daily_vol / realized_daily_vol[t])
```

In the SPY paper, the target daily volatility is 2% and leverage is capped at 4x. The Quantitativo ES/NQ adaptation changes these assumptions for futures.

## Quantitativo ES/NQ Adaptation

The Quantitativo article ports the SPY strategy to E-mini futures:

- Instruments: ES and NQ.
- Data: Databento 1-minute futures data from 2010 onward.
- Baseline: same broad Noise Area + VWAP momentum idea.
- Improvement: increase the Noise Area lookback from 14 days to 90 days.
- Risk: target 3% daily volatility with an 8x leverage cap.
- ES cost assumption quoted in the article:
  - `$0.85` commission per transaction.
  - `$1.40` exchange/clearing/NFA fees per transaction.
  - `0.25 tick` slippage per transaction.

The article reports the following headline results:

| Strategy | Annual Return | Sharpe | Max Drawdown |
| --- | ---: | ---: | ---: |
| ES, 90-day lookback | 16.8% | 1.25 | 21% |
| NQ, 90-day lookback | 24.3% | 1.67 | 24% |
| Portfolio: 50% NQ strategy, 25% ES strategy, 25% long NQ | 22.4% | 1.57 | 15% |

## Back-Testing Plan

### 1. Build Instrument Datasets

Use 1-minute OHLCV bars for ES and NQ.

Required fields:

- Timestamp.
- Contract symbol.
- Open, high, low, close.
- Volume.
- Roll flag or enough symbol history to identify contract changes.

Timestamp convention should follow the existing local loaders:

- Raw futures timestamps are CME Central Time.
- Convert to America/New_York for RTH logic.
- RTH session is `09:30 <= ET < 16:00`.

Exclude or separately flag:

- Sessions with too few RTH bars.
- Sessions with intraday contract symbol changes.
- Known data gaps.
- Exchange holidays and shortened sessions.

### 2. Compute Daily Session Features

For each instrument and each RTH session:

- `rth_open`: open of the 09:30 ET bar.
- `prior_rth_close`: close of the prior regular session.
- `rth_close`: final RTH close.
- Daily return for volatility sizing.
- RTH VWAP, reset each session:

```text
typical_price = (high + low + close) / 3
VWAP[t] = cumulative_sum(typical_price * volume) / cumulative_sum(volume)
```

### 3. Compute Noise Area

For each time-of-day minute and instrument:

1. Compute prior-session absolute move from that session's RTH open.
2. Average the same time-of-day move over a fixed lookback.
3. Build current-day upper/lower bands using the gap-adjusted formulas.

Run at least two variants:

- Paper baseline: 14-day lookback.
- Quantitativo replication: 90-day lookback.

### 4. Implement Trading Engine

Decision clock:

- Evaluate entries, exits, and flips only at `HH:00` and `HH:30`.
- The paper states that stop losses can also be triggered only on semi-hourly intervals, so the first replication should follow that.

Signal rules:

- If flat and close is above upper band, enter long.
- If flat and close is below lower band, enter short.
- If long and close crosses below `max(upper, VWAP)`, exit.
- If short and close crosses above `min(lower, VWAP)`, exit.
- If signal reverses at a decision timestamp, close current position and enter the opposite side.
- Flatten at RTH close.

Fill convention:

- Primary implementation should use next available minute open after the decision timestamp.
- A secondary sensitivity run can use same-bar close if trying to match source-code outputs from the original paper.

### 5. Position Sizing

For each day:

```text
realized_vol[t] = stdev(daily_returns[t-14 ... t-1])
multiplier[t] = min(leverage_cap, target_daily_vol / realized_vol[t])
notional[t] = equity[t-1] * multiplier[t]
contracts[t] = floor(notional[t] / contract_value_at_open)
```

Run:

- Paper-like: 2% target daily volatility, 4x cap.
- Quantitativo-like: 3% target daily volatility, 8x cap.

For futures:

```text
ES tick size = 0.25
ES tick value = $12.50
NQ tick size = 0.25
NQ tick value = $5.00
```

Contract notional:

```text
ES notional = ES price * $50
NQ notional = NQ price * $20
```

### 6. Costs and Slippage

Apply costs per side, not round trip.

For ES, start with Quantitativo's stated assumptions:

```text
commission = $0.85 per contract per transaction
fees       = $1.40 per contract per transaction
slippage   = 0.25 tick per contract per transaction
```

For NQ, use the corresponding IBKR/exchange/NFA fee schedule if available. If not available locally, run a sensitivity grid:

- `0.25 tick` slippage per side.
- `0.50 tick` slippage per side.
- ES-like fixed per-side costs.
- NQ-specific fixed costs once confirmed.

### 7. Validation Outputs

Produce these result tables for ES, NQ, and the combined portfolio:

- Annualized return.
- Annualized volatility.
- Sharpe ratio.
- Max drawdown.
- Hit rate by day and by trade.
- Trade count.
- Average trade PnL in points and dollars.
- Long-only and short-only contribution.
- Monthly return table.
- Worst quarters and worst days.
- Exposure/leverage distribution.

Compare directly to the Quantitativo headline metrics:

- ES: 16.8% annual return, 1.25 Sharpe, 21% max drawdown.
- NQ: 24.3% annual return, 1.67 Sharpe, 24% max drawdown.
- Portfolio: 22.4% annual return, 1.57 Sharpe, 15% max drawdown.

## Local Data Inventory

### NQ

Primary file:

```text
futures/nq/data
```

### ES

Primary file:

```text
futures/es/data
```
