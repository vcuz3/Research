# EXP-0004 Results Discussion

- Hypothesis: `HYP-0002` — Add uncertainty and lag sensitivity to A2 term structure
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: block-bootstrap CI for corrected H; coarse-band endpoint and era sensitivity
- Kill test: 95% block-bootstrap CI includes 0.5 OR coarse result is unstable across prespecified lag endpoints

## Result versus hypothesis

The full-sample corrected coarse exponent remains below 0.5: NQ 0.462 with
95% moving-block-bootstrap CI [0.432,0.490], ES 0.468 [0.440,0.495]. The primary
full-sample kill test does not fire, but the effect is mild.

## Gross, net, baseline, and null comparison

Each of 1,000 resamples repeats the complete real-minus-RW-control calculation.
Real sessions use circular five-session blocks and the 300 independent random
walk paths are resampled iid. Micro NQ is 0.504 [0.501,0.506]; meso is NQ 1m
0.491 [0.484,0.498], ES 1m 0.481 [0.474,0.489].

## Regimes, sensitivity, and alternative explanations

The result survives most 20/30/45-to-150/180 minute endpoint variants, although
ES 45--180m includes 0.5. Era splits weaken the universal claim: NQ 2023--2026
is 0.474 [0.443,0.502] and ES is 0.492 [0.463,0.520]. Earlier eras are below
0.5. NQ/ES agreement is corroboration, not independence.

## Artifact and implementation risks

The five-session block length is prespecified but not itself sensitivity-tested.
The RW control matches path length, not volatility seasonality or intraday
heteroskedasticity. Those limitations matter before giving H a causal mechanism.

## Builder interpretation

Retain coarse anti-persistence as a supported full-sample descriptive result,
but qualify it as era-dependent and avoid calling it an unconditional market
law. A3 should explain the time-of-day composition before B-series prediction.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: promoted with uncertainty and era qualifications
- `MEMORY.md`: updated; unconditional structural wording superseded
- Shared `LEARNINGS.md`: not eligible without cross-project verification
