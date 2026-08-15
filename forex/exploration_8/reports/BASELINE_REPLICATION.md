# Baseline Replication

- Baseline experiment ID: none; no material run registered.
- Source version: user description received 2026-08-13.
- Data scope/fingerprint: user-selectable local window; fingerprints must be frozen before a material run.
- Frozen config: none; timeframe, lookback, threshold, and horizon remain exploratory.
- Exact command: `python _build_notebook.py` builds the workbench only.

## Claim results

| Claim ID | Published | Local | Tolerance | Status | Explanation/evidence |
| --- | ---: | ---: | ---: | --- | --- |
| CLM-001 | exact identity | zero on constructed fixture | 1e-12 | pass | `test_synthetic_identity_and_zero_basis` |
| CLM-002 | not supplied | pending | frozen null comparison | open | requires a registered experiment |
| CLM-003 | not supplied | pending | positive after executable costs | open | midpoint data are insufficient |
| CLM-004 | not supplied | pending | stable OOS residual decay | open | requires validation and review |

## Verdict

The algebraic fixture passes. No empirical or deployable edge has been tested.
