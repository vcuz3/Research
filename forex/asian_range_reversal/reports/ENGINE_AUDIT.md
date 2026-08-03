# Engine Audit

- Five deterministic tests pass, including the bounded-RSI/daily-cap state fixture.
- Decision uses a completed five-minute bar; entry is the next five-minute open.
- Exit processing begins on the entry one-minute bar.
- Stop wins every one-minute stop/target ambiguity.
- Gap-through exits use the first available minute open.
- Targets already crossed before entry are not credited.
- Stop/target levels are frozen at entry; unresolved trades close at 16:59 ET.
- Each target variant runs its own state machine. Signals while positioned are
  discarded and counted. Daily P&L is the sum, never the mean, of trades.
- Five-minute indicators require exact bars, restart after gaps, and re-warm.

Command: `python -m pytest forex/asian_range_reversal/tests -q`.
