# Backtest Engine

This boundary owns execution timing, order/fill semantics, costs, accounting,
position state, sizing mechanics, calendars, and performance metric definitions.
It must not encode a paper-specific alpha hypothesis.

Required evidence includes tiny deterministic fixtures, next-available execution
tests, cost and P&L reconciliation, missing-session handling, metric unit tests,
and parity tests if multiple engine implementations exist. Index them in
`TEST_MATRIX.md` and summarize the audit in `../reports/ENGINE_AUDIT.md`.

---

**NOT APPLICABLE for this project.** Every result is an entry-information
measurement (rule 15): the feature is observed at `close(m)`, entry is
`open(m+1)` (rules 1, 2) and the exit is a bar close H minutes later. There are
no stops, targets or barriers, so there is no fill-path ambiguity to adjudicate
and nothing exit geometry could manufacture. If a barrier strategy is ever added,
this project needs a real engine and an explicit rule-3 intrabar policy first.
