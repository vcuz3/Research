# Paper Specification

## Source and empirical status

- Amaanullah Bhatti, *A Regime-Filtered Intraday Trading Framework for Gold*,
  SSRN 6650958, 26 April 2026; local source `../ssrn-6650958.pdf`.
- The reported 247-trade result is a calibrated Monte Carlo simulation, not a
  bar-by-bar historical backtest (sections 6.1 and 7.2).

## Universe and data

- Paper: XAU/USD spot, 15-minute OHLCV, January-December 2024.
- Local proxy by user instruction: unadjusted continuous GC futures with actual
  traded volume. Indicators are computed with pre-2024 history for warmup, but
  the primary engine run opens trades only in 2024.
- VWAP: session-cumulative typical price `(H+L+C)/3`, weighted by volume.

## Strategy contract

- EMA200 regime; reject signals within 0.1% of EMA200.
- Long requires close above EMA200 and VWAP, EMA50 touched by current/prior low
  and close above it, bullish pin or full bullish engulfing candle, volume above
  1.1x SMA20, and range at least 0.8x ATR14. Short is symmetric.
- Signal on completed 15m close; fill next 15m open.
- Initial stop: signal low/high plus 0.5 ATR14 adverse buffer. Target: 3R.
- Close-only EMA50 trail; after favourable price reaches 2.5R, switch to the
  close-only EMA20 trail. Force flat at session close.
- Risk 1% of current equity per trade. Deduct 0.24R once per completed trade.
- Stop new entries after three consecutive net losses or daily net P&L <= -3R.
- No new entry within +/-15m of specified macro events. In 2024 only 14:00 ET
  FOMC decisions overlap the selected session; other named releases occur 08:30.

## Ambiguities and resolutions

| Ambiguity | Resolution | Consequence |
| --- | --- | --- |
| "NY open 13:30 UTC" and "close 20:00 UTC" ignore winter DST | Use 09:30-16:00 America/New_York | Preserves named session and 1s coverage; differs from fixed UTC in winter |
| Entry order/time omitted | Next-bar market open | Causal conservative default |
| Engulfing prose requires candle colours but displayed formula does not | Require prior opposite colour and current directional colour plus displayed inequalities | Stricter literal-prose interpretation |
| Section 4.3 says a favourable post-entry approach to VWAP, while C2 enters long above/short below VWAP | Do not invent a partial-fill rule | Full historical replication of this component is impossible |
| Existing-position news stop is "manually overridden" to undefined swing structure | Keep algorithmic paper stop/trail; apply entry blackout only | Discretionary override excluded and disclosed |
| Cost table says 0.24R while text reports post-cost expectancy above pre-cost | Apply 0.24R subtraction exactly | Paper's +0.414R cannot follow from its stated pre-cost +0.373R |
| Benchmark mechanics unspecified | Do not claim benchmark replication | Strategy verdict uses its own gross/net expectancy |
