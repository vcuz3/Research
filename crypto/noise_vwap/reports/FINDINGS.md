# Findings

Summarize reviewed experiment evidence by experiment ID. Distinguish confirmed,
provisional, invalidated, and superseded findings. Include negative results and
link to ledger rows and immutable artifacts.

## EXP-0001 — frozen Bitcoin transfer baseline

- Confirmed implementation finding: the notebook executed with zero same-bar,
  non-exact-next-minute, or overlapping fills, and the causal band audit matched
  exactly. Missing BTC minutes were reported and never filled.
- Provisional performance finding: the frozen baseline produced OOS net Sharpe
  0.230 and 11.835 gross bps/trade at a 10 bps modeled round trip, but in-sample
  Sharpe was -0.223 and 2025-2026 were negative.
- Decision: narrow first-screen survival, not deployment-ready and not yet an
  edge claim. Independent review, a path-preserving Null C, neighboring anchors,
  and intended-venue execution/cost evidence remain open.
- Evidence: `../artifacts/runs/EXP-0001/review.md`.
