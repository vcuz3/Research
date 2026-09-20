# Final Critical Review

## Evidence quality

- Baseline fidelity: passed against the frozen user-defined contract.
- Engine integrity: five builder tests pass; independent review pending.
- Data provenance: fingerprinted common NQ/VIX sources; exact anchors and roll
  exclusions reported.
- Search/reuse burden: high. Six MA cells, 27 overlapping VIX ranges, and four
  sizing modes used the full history.
- Null and negative controls: gross/net, causal-window, roll, sizing, and era
  controls exist; selection-aware nulls do not.
- Regime/cost robustness: four eras and ATR normalization reported; execution
  cost stress and official-settlement sensitivity are open.
- Holdout: historical sample consumed; only future data is clean.

## Decision

- Verdict: **watch / research only**.
- Deployment claim: none.
- Main failure modes: searched thresholds, crisis concentration, simple 18:00
  cost model, sparse internal source periods, fractional sizing, and no
  independent review.
- Required next evidence: selection-aware null, cost stress, reviewer sign-off,
  then a preregistered future shadow period.

