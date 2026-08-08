# Strategy

Fade the first crossing of `|z| >= 2`, where `z` is the six-bar return divided by
the 100-bar rolling one-bar-return standard deviation times `sqrt(6)`. Enter at
the next 5-minute bar open. Exit after an observed close crosses `z=0`, at the
following bar open, or at a compulsory 1.5-sigma stop. A 30-minute high-impact
news blackout veto applies to entries.
