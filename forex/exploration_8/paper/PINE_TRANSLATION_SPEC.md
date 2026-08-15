# Pine v6 Translation Specification

## Source

User-supplied `Synthetic EURUSD Triangular Strategy` Pine v6 script, received
2026-08-13. The translation changes EURUSD/EURJPY/USDJPY to
AUDUSD/AUDJPY/USDJPY and otherwise preserves the source defaults.

## Parameter mapping

| Pine input | Python parameter | Default |
| --- | --- | ---: |
| chart timeframe | `TIMEFRAME_MINUTES` | 5-minute local assumption |
| `lookbackPeriod` | `LOOKBACK_PERIOD` | 50 |
| `zEntry` | `Z_ENTRY` | 1.5 |
| `zExit` | `Z_EXIT` | 0.25 |
| `useAtrRisk` | `USE_ATR_RISK` | true |
| `atrPeriod` | `ATR_PERIOD` | 14 |
| `atrStopMult` | `ATR_STOP_MULT` | 2.0 |
| `atrTargetMult` | `ATR_TARGET_MULT` | 3.0 |
| `initial_capital` | `INITIAL_CAPITAL` | USD 100,000 |
| `default_qty_value` | `FIXED_QUANTITY_AUD` | AUD 100,000 |
| `commission_value` | `COMMISSION_PERCENT` | 0.0% per order |

## Strategy contract

- Synthetic AUDUSD is `AUDJPY close / USDJPY close`.
- Spread is `AUDUSD close - synthetic AUDUSD`.
- Z-score uses the current completed bar in an SMA(50) and population standard
  deviation window, matching Pine defaults.
- A flat strategy schedules a long after `z <= -1.5` and a short after
  `z >= +1.5`; market entry is the following bar open.
- A long schedules a market close after `z >= -0.25`; a short schedules a market
  close after `z <= +0.25`. The close fills at the following bar open.
- Wilder ATR(14) is known at the signal close. Stop and target are frozen from
  that signal close at 2 ATR and 3 ATR, respectively.
- ATR brackets are replayed on underlying one-minute AUDUSD bars, including the
  entry bar. Dual touch is adverse (stop first); gap-through uses minute open.
- Only one AUDUSD position may be open. The JPY crosses create the signal but are
  not traded.

## Known non-parity

- The source requests OANDA series with `barmerge.gaps_off`; local research uses
  exact synchronized complete bars and does not carry stale cross-leg prices.
- Exact TradingView parity is not claimed without the original chart symbol,
  timeframe, session/timezone, OANDA data vintage, and broker-emulator version.
- Local midpoint data omit executable bid/ask spreads.
