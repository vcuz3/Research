# Backtest Engine

This boundary owns execution timing, order/fill semantics, costs, accounting,
position state, sizing mechanics, calendars, and performance metric definitions.
It must not encode a paper-specific alpha hypothesis.

Required evidence includes tiny deterministic fixtures, next-available execution
tests, cost and P&L reconciliation, missing-session handling, metric unit tests,
and parity tests if multiple engine implementations exist. Index them in
`TEST_MATRIX.md` and summarize the audit in `../reports/ENGINE_AUDIT.md`.
