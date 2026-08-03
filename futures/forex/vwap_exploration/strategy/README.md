# Strategy

Put features, signal rules, filters, and sizing hypotheses here. Strategy code
must emit decisions/configuration for the audited engine and must not reproduce
fill, cost, P&L, or metric logic.

Each improvement begins as a falsifiable, registered experiment and is compared
with the frozen honest baseline.

---

No strategy code: the anchors, deviations and statistics live in `core/`
(`data`, `vwap`, `frame`, `stats`, `fix`) because they are measurement
primitives, not tradable logic. Nothing in this project reached the point of
being a strategy — see `reports/FINDINGS.md` for why.
