# EXP-0002 review — is T = -10.96 a signal statistic or a cost statistic?

- Hypothesis: HYP-0001
- Builder: Claude (Opus 5), 2026-08-26
- Reviewer: **pending independent review**
- Reproduce: `python futures\nq\asia_expansion\scripts\run_exp0002.py`

## What was run

On the identical firing bars, fills, sample and charge used by the article's rule, the
trade direction was replaced by a fair coin, 400 draws, and the net-of-2.00-points
cluster-robust t recorded each time. A coin flip has zero directional information by
construction, so its distribution of net t is exactly the part of the statistic that the
charge alone produces.

## Result

| Arm | gross t | net t @ 2.00 pt |
|---|---:|---:|
| Continuation (article's rule), article window | +0.50 | **-14.26** |
| Fade (mirror) | -0.50 | -15.25 |
| **Coin flip, 400 draws** | -0.04 [-1.61, +1.55] | **-15.18 [-17.33, -13.05]** |
| Article's reported figure | — | *-10.96* |

Full archive: continuation net t -42.99, coin flip -47.06 [-50.49, -43.85].

## Interpretation

The reported -10.96 is not a directional finding. A zero-information coin flip on the same
bars scores about -15, i.e. **more** negative. -10.96 lies above the 95th percentile of the
coin-flip distribution, so if anything it is weak evidence that the signal is slightly
better than random.

The arithmetic: net t is approximately `(mu - c) * sqrt(N) / sd`. With mu ~ 0.07 pt,
c = 2.00 pt, sd ~ 15 pt and N ~ 12,000, the `-c` term alone dominates completely. Any
signal, at this trade count and this charge, prints a large negative t.

## Alternative explanations considered

1. **Is the coin flip a fair comparison?** It preserves the firing bars, the entry and exit
   fills, the sample, the clustering and the charge, and destroys only the direction — which
   is precisely the quantity the article's claim is about. It is not a substitute for a
   path-preserving null of the *signal construction*; it is not intended to be, and no such
   claim is made.
2. **Does the cluster structure matter?** Yes and it is used: the SE is clustered on trade
   date in both the real arm and every null draw, so the comparison is like-for-like.
3. **Degenerate check.** A strategy with exactly zero gross P&L and a flat -2.00 charge has
   zero variance, so its t is undefined rather than infinite; the script reports NaN for
   that cell. This is a known degenerate output, not a bug, and it is why the coin flip
   (which has realistic variance) is the calibration used.

## Builder interpretation

This is the load-bearing result of the project. It does not overturn the article's
conclusion — nothing here clears costs — but it overturns the article's evidence for
*why*, and it generalises: a net-of-fixed-charge t-stat should never be reported as a
statement about signal direction without the gross figure beside it.
