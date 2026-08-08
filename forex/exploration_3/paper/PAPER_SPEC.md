# User strategy specification

## Frozen interpretation

The source is a user-supplied Pine v6 strategy. The user explicitly superseded
two pasted defaults: the strategy arms at **2.5 standard deviations** and uses
an **ATR-multiplier stop with a default multiplier of 2.0**, not the pasted
pivot stop / 2.0Z / 1.5ATR defaults.

- Price source: typical price, `(high + low + close) / 3`.
- Signal bars: 15 minutes (research assumption; source chart timeframe was unspecified).
- Baseline candidates: New-York 17:00 session-anchored cumulative TWAP or trailing SMA.
- Dispersion: session-running Pine-style cumulative residual dispersion for TWAP; population rolling standard deviation for SMA.
- Arm long when a completed close is below baseline minus 2.5 standard deviations.
- Arm short when a completed close is above baseline plus 2.5 standard deviations.
- Trigger after an armed close returns inside the same 2.5Z band, provided it has not crossed the baseline.
- Timeout: disarm when bar age is strictly greater than 10, matching the Pine condition.
- Entry: next observed complete 15-minute bar open; no same-close execution.
- Stop: 2.0 times causally seeded Wilder ATR(14), frozen from the signal bar and measured from the actual entry.
- Target: symmetric 1.0R from actual entry.
- Position constraint: one open position per pair; up to four pairs may overlap.
- Exit replay: underlying one-minute OHLC, starting on the fill minute. Gaps fill at the first tradable open. A one-minute bar touching both barriers is scored stop-first.
- Costs: midpoint gross result plus a baseline 1.0-pip round-trip cost; 0-2 pips are stressed.
- Sizing/estimand: equal fixed quantity per pair; portfolio daily P&L is summed in pips. Trade results are also reported in R.

## Training and evaluation

- Training/model selection: entry before 2020-01-01.
- Unused embargo: calendar 2020.
- Out of sample: 2021-01-01 through 2023-12-31.
- Historical holdout: 2024-01-01 through the latest local data (2026-07-17 for EXP-0001).
- Only baseline type is selected in training: session TWAP or SMA(10/20/40/80). The user-confirmed arming and stop parameters remain fixed.

## Known departures and ambiguities

- The source did not name a symbol or timeframe; the research baseline uses four shared FX pairs and 15-minute signals.
- Default Pine `time("D")` depends on chart/exchange context. This port uses the explicit 17:00 America/New_York session setting with real DST.
- Midpoint bars do not measure spread or executable bid/ask prices. Cost stress is not a substitute for quote-level fill validation.
- The requested 2024-latest window becomes consumed historical evidence once viewed; only future data is clean afterward.
