# EXP-0003 Results Discussion

- Hypothesis: `HYP-0001` — Correct A1 bias calibration and cross-frequency matching
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: inverse-calibrated H by estimator; matched-date 1s/1m gap; Rule-9a exclusions
- Kill test: Bias-calibrated estimators do not converge materially OR matched-date 1s/1m comparison changes the conclusion

## Result versus hypothesis

The review objection was confirmed. Inverting each estimator's simulated
mean-versus-truth curve gives NQ H=0.473--0.499 and ES H=0.466--0.485, not the
previously reported 0.49--0.50. The old point-level claim is superseded.

## Gross, net, baseline, and null comparison

No trading. The reference is the 200-draw synthetic calibration surface at
n=390. The cross-frequency comparison now uses the same 149 complete-grid,
era>=2015, fill>=0.90 dates: GHE1 is 0.471 on 1m and 0.490 on minute-plus 1s.

## Regimes, sensitivity, and alternative explanations

Seven NQ and four ES incomplete one-minute grids were excluded. The remaining
1s sample has mean fill 0.967 and minimum fill 0.902. The matched-frequency gap
is small relative to session-level dispersion but was not given a paired CI;
it is therefore a consistency diagnostic, not independent validation.

## Artifact and implementation risks

The synthetic calibration spans H in {0.4,0.5,0.6}; inversion outside the
simulated observed range returns NaN rather than extrapolating. The manifest
freezes code hashes, data metadata fingerprints, environment, and output hashes.

## Builder interpretation

A1's central measurement-floor result survives. Its whole-session random-walk
interpretation becomes estimator-dependent: most corrected estimates are below
0.5, especially ES DFA/GHE2. Prefer reporting the panel rather than one level.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: promoted as a correction to EXP-0001
- `MEMORY.md`: updated; old 0.49--0.50 statement superseded
- Shared `LEARNINGS.md`: not eligible without cross-project verification
