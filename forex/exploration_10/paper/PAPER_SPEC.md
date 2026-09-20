# Strategy Specification

## Source

- Citation: user-supplied strategy, 2026-09-19.
- Source: conversation request; no external paper.

## Strategy contract

- Instruments: EURUSD, GBPUSD, AUDUSD, NZDUSD spot-FX midpoint OHLC.
- Source bars: clean 1-minute UTC bars in `forex/data/clean/`.
- Decision bars: left-labelled UTC bars, default 30 minutes. Incomplete decision
  bars are excluded; rolling windows count valid tradable bars, not calendar bins.
- ATR: textbook Wilder true range average, default period 14, seeded with the
  first 14-bar simple mean. The current completed bar ATR may be used at its close.
- Low-volatility gate: current ATR must be strictly below the configured quantile
  (default 0.15) of the previous 100 valid decision-bar ATR observations. The
  current ATR is excluded from its threshold.
- Breakout levels: highest high and lowest low of the previous 10 valid decision
  bars, excluding the current bar.
- Signal: sell (`-1`) when the completed bar closes strictly above the prior high;
  buy (`+1`) when it closes strictly below the prior low. This is contrarian.
- Entry: market order at the first available 1-minute open at or after the signal
  candle closes. No same-candle-close fill is credited.
- Position constraint: at most one position per instrument. Same-side signals are
  ignored while holding. An opposite signal closes the position at its next
  executable open and does not reverse at that same timestamp.
- Bracket: stop and target are frozen from the signal ATR at entry. Defaults are
  1.5 ATR on each side.
- Time exit: first available minute-bar open at or after 12 elapsed hours.
- Exit precedence: a gap through a live stop fills at the first tradable open; a
  favorable gap is conservatively capped at the target. At a scheduled exit open,
  live gap logic is checked first. Within a 1-minute bar, stop/target ambiguity is
  resolved adversely at the stop. Brackets are active on the entry minute.
- Sizing: results are per equal-risk trade in R and per one-unit position in pips;
  no leverage or capital claim is made.
- Costs: gross baseline plus configurable round-trip cost deductions. Default
  report sensitivities are 0.2, 0.5, and 1.0 pip per trade.

## Parameters

The JSON configuration and CLI expose `timeframe`, `atr_period`,
`atr_percentile`, `stop_atr`, and `target_atr`. Other mechanics are also recorded
in the configuration for reproducibility.

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Rationale |
| --- | --- | --- |
| ATR convention | Textbook Wilder ATR | Standard interpretation; exact seeding is tested. |
| Percentile includes current ATR? | No | Uses only the stated previous 100 candles. |
| Breakout window includes current bar? | No | Implements "previous 10 candles" literally. |
| Fill on signal close? | Next available 1-minute open | Completed-bar information is causal only then. |
| Opposite signal reverses? | Exit only | The request specifies it as an exit, not a reversal. |
| Stop and target both touched in a minute | Stop first | Conservative unresolved-path convention. |
| Weekend and data gaps | First available open; elapsed wall time | Avoids fabricated bars and stale fills. |

## Frozen baseline

- Config: `baseline_replication/configs/baseline.json`
- Command: `python run_backtest.py --config baseline_replication/configs/baseline.json --output artifacts/runs/EXP-0001`
