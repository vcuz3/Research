# EXP-0007 Results Discussion

- Hypothesis: the clean faithful strategy outperforms a session-valid Null C.
- Status: planned.
- Builder: unassigned.
- Reviewer: unassigned.
- Primary metric: null-relative effect and P&L drift.
- Kill test: the faithful result is not materially distinguishable from the
  valid null distribution.

## Result versus hypothesis

Pending.

## Gross, net, baseline, and null comparison

Pending.

## Regimes, sensitivity, and alternative explanations

Pending.

## Artifact and implementation risks

The null must use the current decision clock, VWAP gate, costs, data scope, and
metric units. The opening-anchor, net-move, atom, and diffusivity invariants now
pass in `tests/test_nulls.py`; retain these gates when producing and reviewing
the experiment artifacts.

## Builder interpretation

Pending.

## Independent review

- Review status: pending.
- Objections: pending.
- Verdict: pending.

## Promotion decision

- `REVIEW.md`: pending.
- `MEMORY.md`: pending; update only if durable state changes.
- Shared `LEARNINGS.md`: not eligible without cross-project verification.
