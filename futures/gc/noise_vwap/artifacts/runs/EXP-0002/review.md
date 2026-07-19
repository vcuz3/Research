# EXP-0002 — HYP-0001: gold-native COMEX pit hours vs equity-RTH window

Tests whether aligning the strategy to gold's liquid COMEX floor session
(08:20-13:30 ET) beats the inherited equity window (09:30-16:00 ET). Identical
machinery for both windows via `core/session_hours.py`; Concretum 30-min clock,
VWAP anchor, noise-band open, and forced flatten all re-anchored to the window
open. Each window judged against its own claim-matched Null-C.

## Command

```
python -m futures.gc.noise_vwap.scripts.hyp_0001_comex_hours GC 90 20 0.50
```

## Results (0.50 tick/side)

| Window | sessions | n | net pt | day$net t | net Sharpe | gross Sharpe | Null-C z | Null-C p | null capture |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| equity 09:30-16:00 | 3647 | 2641 | +0.214 | +1.25 | 0.46 | 0.77 | +2.66 | 0.048 | −26% |
| comex 08:20-13:30 | 3763 | 2379 | +0.097 | +0.56 | 0.21 | 0.53 | +0.04 | 0.476 | 96% |

Parity guard: the equity window re-run through the generalized loader reproduces
EXP-0000 exactly (n=2641, gross +0.359, net +0.214, t=+1.25, netSh 0.46). Both
windows pass the diffusivity gate (real=null=0.1000 pt).

## Interpretation — hypothesis INVERTED

Moving to the gold-native COMEX pit hours makes the strategy **worse on every
metric**: net Sharpe 0.46 → 0.21 (Δ −0.25), gross Sharpe 0.77 → 0.53, day-net
t 1.25 → 0.56. More decisively, **the COMEX window fails its own Null-C**: real
+6.42 vs null mean +6.18, z=+0.04, p=0.476, null captures 96%. The COMEX-window
"edge" is entirely path-shuffle machinery — there is no real intraday-momentum
timing signal in 08:20-13:30.

The marginal-but-real timing trace (Null-C z=+2.66 at 0.50 tick) lives ONLY in the
equity 09:30-16:00 window. Whatever gold intraday momentum the strategy captures is
tied to the equity cash session, not to gold's own floor hours — plausibly gold
reacting to equity/risk-asset flows during US cash hours, whereas the 08:20 open +
08:30 data cluster produces a noisy open the noise-band mechanism cannot exploit.

## Kill test

Both kill conditions fired: (1) COMEX does NOT beat equity net Sharpe (it is 0.25
worse); (2) COMEX gross fails its Null-C. **HYP-0001 REJECTED.**

## Verdict

- Reviewer: claude (builder self-review; independent review outstanding)
- Date: 2026-07-19
- Decision: **REJECTED.** Do not adopt COMEX hours. Do NOT sweep window start/end
  times on this consumed history to find a survivor (multiple-testing; would be
  discovery, not confirmation). The equity window remains the frozen baseline.
- Objections / limits: 20 null draws (coarse p); windows differ in decision count
  (13 vs 10) and session-eligibility (min-bars threshold), but the finding —
  weaker AND null-failing — is robust to those.
