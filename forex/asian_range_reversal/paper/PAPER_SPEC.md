# Frozen Strategy Specification

This is a user-specified strategy, not a paper replication. The faithful baseline
is frozen before the first material P&L run.

## Market and clock

- EURUSD and GBPUSD one-minute midpoint OHLC from `forex/data/`.
- All session clocks use `America/New_York` local time with DST.
- Trading day: 17:00 ET through 16:59 ET next calendar day.
- Asian range: observed high/low from 17:00 through 23:59 ET. The source commonly
  omits 17:00-17:14, so this is explicitly an observed-range proxy.
- London: 00:00-05:59; NY_AM: 06:00-11:59; NY_PM: 12:00-16:59 ET.
- Retain a day only when every named session has at least 95% minute coverage and
  the 16:59 bar exists. The exclusion count is reported.

## Five-minute construction

- Align bars to trading-day slots: 17:00-17:04, 17:05-17:09, and so on.
- A five-minute bar exists only with all five exact one-minute timestamps.
- RSI(14) uses close and Wilder smoothing.
- ATR(14) uses true range and Wilder smoothing.
- Recursive indicators restart after any missing five-minute bar and re-warm for
  14 complete bars.

## Signal and state

- From 00:00 through 16:54 ET, inspect every completed five-minute bar.
- When flat, a bar whose high is strictly above the frozen observed Asian high
  and whose completed-bar RSI is above 70 schedules a short.
- When flat, a bar whose low is strictly below the frozen observed Asian low and
  whose completed-bar RSI is below 30 schedules a long.
- If both signals are simultaneously true, skip the ambiguous bar.
- While a position is open, discard signals; do not queue them. After any stop,
  target, or end-of-day exit, later qualifying bars may generate a new trade.
- Midpoint and opposite-target variants run as separate state machines because
  their exit times change which later signals are eligible.

## Entry, exits, and fills

- Enter at the exact open of the next five-minute bar (also its first one-minute
  open). If absent, skip.
- Freeze stop at entry +/- 2.0 times signal-bar ATR(14).
- Compare two separately reported targets frozen from the Asian range:
  1. `midpoint`: `(Asian high + Asian low) / 2`.
  2. `opposite`: Asian low for a short; Asian high for a long.
- If a target is already marketable at entry, skip that target variant.
- Process exits from the entry one-minute bar. Gap-through fills use that minute's
  open. If stop and target can both be reached in one minute, assign the stop.
- If neither barrier is reached, exit at the 16:59 ET close. No overnight carry.
- Prices are midpoint; report gross and hypothetical 0.5/1.0-pip round-trip cost.

## Portfolio

- One unit per pair, no overlapping positions within a target variant, daily risk reset.
- Multiple sequential trades per pair/day are allowed.
- Target variants are alternative strategies and are never summed together.
- Report per-trade and daily-portfolio results including zero-trade eligible days.
