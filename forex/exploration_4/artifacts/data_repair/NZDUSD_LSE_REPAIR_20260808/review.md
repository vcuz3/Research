# NZDUSD repair sensitivity review

Status: builder-complete; independent review pending.

This is a post-closeout data-quality sensitivity, not a new hypothesis or a
replacement for immutable `EXP-0001`. It reruns the identical frozen baseline
after the documented hybrid NZDUSD repair.

NZD candidate-path exclusions fall from 17,063 to 140 and the consumed NZD
sample rises from 3,973 to 15,886. The restored observations do not rescue the
strategy: NZD gross mean is −0.0617 R (95% CI [−0.0854, −0.0379]), and pooled
base-cost net mean is −0.3937 R (95% CI [−0.4077, −0.3797]). The verdict remains
NO-GO.

Builder checks: repair placebo and structural gates passed; post-promotion FX
data-quality report passed; exploration invariant tests 4/4; visualization
notebook smoke-executed every code cell against this artifact directory.

Limitation: repaired bars are adjusted LSE estimates rather than exact IBKR
midpoints. The repair manifest identifies 365 carried sparse minutes and 172
filtered source fields for future exclusion sensitivity.
