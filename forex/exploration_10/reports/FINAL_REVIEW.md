# Final Critical Review

## Evidence quality

- Baseline fidelity: exact requested parameters, with documented conservative
  resolutions for fill and collision ambiguities.
- Engine integrity: 7 deterministic tests pass; independent review pending.
- Data provenance: shared clean midpoint archives with committed fingerprints
  and coverage reports.
- Search burden: 243 candidates per asset in EXP-0002. Rolling forward results
  were worse than the static baseline, directly exposing selection overfit.
- Controls: four sibling pairs and cost sensitivity completed; claim-matched null,
  clock-matched control, and parameter neighbours remain pending.
- Robustness: gross-positive in all pairs and in 2020+; negative pooled expectancy
  at 0.5 and 1.0 pip round-trip costs.

## Decision

- Verdict: **NO-GO for optimisation; WATCH, not deploy, for the baseline thesis**.
- Deployment claim: none.
- Main failure modes: time-of-day selection, midpoint/spread optimism, correlated
  markets, untested null, and no clean historical holdout.
- Required evidence: do not spend the reserved optimisation holdout on the failed
  selection rule. First redesign using a clock-matched control or simpler frozen
  rule, then preregister a new forward test; retain future data for clean evidence.
