# EXP-0007 Results Discussion

- Hypothesis: the clean faithful strategy outperforms a session-valid Null C.
- Status: completed.
- Builder: Codex.
- Reviewer: unassigned.
- Primary metric: instrument-level daily net P&L versus corrected Null C.
- Kill test: reject if upper-tail `p > 0.05` or if the null captures at least
  60% of real P&L.

## Result versus hypothesis

Passed on both instruments. NQ exceeded all 30 null draws (`p=1/31=0.0323`)
with 49.0% null capture. ES exceeded all 30 null draws with the null negative
after costs.

## Gross, net, baseline, and null comparison

| Instrument | Real daily net | Null mean | Null SD | z | Upper-tail p | Null capture |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| NQ | $74.04 | $36.31 | $13.43 | 2.81 | 0.0323 | 49.0% |
| ES | $33.91 | -$11.17 | $8.01 | 5.63 | 0.0323 | -32.9% |

Costs are 0.25 tick slippage plus $2.25 fees per side. Daily means include
eligible zero-trade sessions. Gross points per trade were NQ 4.945 real versus
2.214 null, and ES 1.036 real versus -0.014 null.

## Regimes, sensitivity, and alternative explanations

This test does not establish era stability, future persistence, capacity, or a
deployable edge. Thirty draws give only coarse tail resolution; the result is a
pass at the declared 5% threshold, not a precise p-value estimate.

## Artifact and implementation risks

The null used the faithful 90-session bands, Concretum 30-minute clock, VWAP
entry gate, decision-clock exits, next-open fills, and frozen costs. Opening
anchor, net move, atom, and diffusivity invariants pass. Diffusivity matched
exactly for both instruments (NQ 0.25 point; ES 0.00 point median).

## Builder interpretation

The corrected faithful timing signal is distinguishable from the session-drift-
preserving null in both NQ and ES. The NQ result still obtains roughly half of
daily P&L from path features retained by the null, so the verdict remains
qualified and is not deployment evidence.

## Independent review

- Review status: pending.
- Objections: pending.
- Verdict: pending.

## Promotion decision

- `REVIEW.md`: pending independent synthesis.
- `MEMORY.md`: updated with the completed post-fix result.
- Shared `LEARNINGS.md`: not eligible without cross-project verification.
