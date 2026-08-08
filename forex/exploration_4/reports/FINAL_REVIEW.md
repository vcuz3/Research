# Final Review — exploration_4

## Decision

**NO-GO; preserve as a frozen negative baseline.** The consumed-history primary
metric is −0.3733 base-cost net R/signal with a 95% day-clustered CI of
[−0.3880, −0.3585]. Gross is negative before costs, both compulsory-stop entry
diagnostics fail, and the sealed holdout is worse.

## Deployment boundary

This is research evidence against the frozen strategy, not deployment evidence.
Do not tune or trade it. The small advantage over the matched-duration random-exit
null is an exit-timing observation inside a negative book.

## Review status

Builder verification is complete: 4/4 invariant tests pass, the material command
reproduces exactly, the Rule 9a report precedes interpretation, and all requested
artifacts and notebook cells were verified. Independent review is still pending
and is recorded honestly as such in the ledger and run review.

## Evidence

- `FINDINGS.md`
- `DATA_QUALITY.md`
- `../artifacts/runs/EXP-0001/review.md`
- `../notebooks/trade_visualizations.ipynb`
