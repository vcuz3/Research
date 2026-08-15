# Idea Backlog

Uncommitted brainstorming belongs here. An idea is not a finding or approved
experiment. Use `python tools/research_admin.py new-idea` to add entries.

## Ideas


## IDEA-0001 — AUDUSD versus AUDJPY/USDJPY triangular pricing dislocation

- Created: 2026-08-12
- Observation: AUDUSD should equal AUDJPY divided by USDJPY under synchronized frictionless pricing.
- Proposed mechanism: local liquidity shocks temporarily dislocate one leg and the residual subsequently mean-reverts.
- Expected improvement: cross-pair information may be more informative than AUDUSD's own price history.
- Main artifact risk: non-synchronous midpoint archives manufacture a basis; shared-close reversal and omitted three-leg spread can manufacture profitability.
- Motivating evidence: algebraic identity only; no market evidence yet.
- Status: exploratory workbench built; not promoted to a hypothesis.
