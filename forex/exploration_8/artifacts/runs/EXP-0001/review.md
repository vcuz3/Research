# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` - Minute-level decay of AUD triangular pricing signal
- Status: completed; prespecified KILL
- Builder: Codex
- Reviewer: unassigned
- Primary metric: three-leg residual mean net basis points per signal at a five-minute delay, on the identical paired signal set.
- Kill test: the capturable-dislocation thesis is materially weakened if five-minute residual net expectancy is non-positive at 0.5 bp round-trip cost per leg, or if five-minute gross retains less than 50% of delay-zero gross.

## Result versus hypothesis

Both kill conditions fired. On 610 exactly paired signals, five-minute residual
gross was +0.0306 bp, only 2.5% of delay-zero gross (+1.2429 bp). Five-minute
residual net was -1.4694 bp after the frozen 0.5 bp round-trip cost per leg.

The residual deterioration was already nearly complete after one minute: gross
fell to +0.1221 bp (9.8% retention), and the paired change versus delay zero was
-1.1208 bp with UTC-day clustered t = -7.81. At five minutes the paired change
was -1.2124 bp, t = -8.17.

## Gross, net, baseline, and null comparison

| Delay | AUDUSD gross | AUDUSD net | Residual gross | Residual net |
| ---: | ---: | ---: | ---: | ---: |
| 0 min | +2.3043 | +1.8043 | +1.2429 | -0.2571 |
| 1 min | +0.4856 | -0.0144 | +0.1221 | -1.3779 |
| 2 min | +0.6025 | +0.1025 | +0.0950 | -1.4050 |
| 5 min | -0.2206 | -0.7206 | +0.0306 | -1.4694 |
| 10 min | +0.0510 | -0.4490 | +0.0400 | -1.4600 |
| 15 min | +0.3775 | -0.1225 | +0.0950 | -1.4050 |
| 30 min | +0.0596 | -0.4404 | +0.1700 | -1.3300 |

Units are basis points per signal. Delay zero residual was already negative net
because three legs incur 1.5 bp total assumed round-trip cost. No re-pairing null
was run in this experiment; the claim-matched discriminator was paired temporal
decay on an identical signal set.

## Regimes, sensitivity, and alternative explanations

- Five-minute residual gross was only +0.008 to +0.071 bp in every individual
  year from 2015 through 2020; net was negative in all six years.
- The original feature grid produced 1,307 crossings. Only 619 had an immediately
  contiguous 30-minute common one-minute window; requiring validity at every
  delay left 610 paired signals.
- Candidate signals were dominated by 21:00-22:00 UTC (58.2%). Those hours were
  only 12.0% of the paired sample because most session-boundary signals lacked an
  immediately tradable common minute. The verdict therefore applies primarily to
  the exact-aligned, continuously tradable sample, not the missing rollover events.
- A sub-minute effect could exist, but one-minute midpoint bars cannot establish
  it. Delay-zero fills use the boundary open, which is numerically the signal close
  in this archive.

## Artifact and implementation risks

- Inputs are midpoint archives from separate sources, not synchronized bid/ask
  quotes. The cost is assumed rather than observed.
- Delay 0 and 30 endpoints had been inspected before registration; intermediate
  delays were frozen before the material run. This is exploratory, not clean
  confirmatory evidence.
- Overlapping signal-level observations are retained for an identical paired
  decay estimand; inference clusters by UTC day. This is not a deployable
  one-position portfolio simulation.

## Builder interpretation

The apparent 30-minute convergence is almost entirely a signal-boundary effect:
about 90% of residual gross disappears by the first one-minute delay and about
97.5% by five minutes. At the assumed costs the three-leg trade is negative even
at delay zero. AUDUSD-only gross also loses about 79% after one minute and becomes
approximately zero net. The historical minute data do not support a capturable
minute-scale trading edge.

## Independent review

- Review status: pending
- Objections: no independent reviewer assigned
- Verdict: pending independent review; builder verdict is KILL

## Promotion decision

- `reports/FINDINGS.md`: updated with the EXP-0001 result.
- `MEMORY.md`: updated with the durable current verdict.
- Shared `LEARNINGS.md`: not eligible without cross-project verification.
