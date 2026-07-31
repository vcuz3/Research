# EXP-0040 — Causal volatility-regime sizing (HYP-0028): NO-GO

**Reproduce:** `python -u -m futures.nq.noise_vwap.scripts.hyp_0028_vol_sizing real`

Overlaid a CAUSAL vol-regime weight on the deployed continuous-stop baseline. Weight =
schedule of the causal EXPANDING percentile of trailing-20d annualised vol (shifted 1),
normalised by the causal expanding PRIOR mean so mean exposure ~= 1 (EXP-0017 protocol,
no net-leverage artifact). 3628 labelled sessions, 0.25 tick/side.

Schedules: `high_boost` (PRIMARY: 1.0x, 1.5x above the causal 75th vol pct — matches the
EXP-0039 finding that ONLY the high band stood out); `vol_linear` (0.5→1.5x ramp);
`vol_down` (mirror control, overweight LOW vol).

## Frame A — deployable per-contract overlay (PRIMARY): flat

| schedule | mean_w | Sharpe | dSharpe | mean$/day | maxDD$ | dMaxDD$ | dCVaR5$ |
|---|---|---|---|---|---|---|---|
| unsized | 1.000 | +0.961 | — | +73.3 | −34,235 | — | — |
| **high_boost** | 1.037 | +0.955 | **−0.006** | +83.4 | −31,795 | **+2,440** | −217 |
| vol_linear | 1.074 | +0.936 | −0.025 | +86.6 | −38,598 | −4,363 | −406 |
| vol_down (mirror) | 0.926 | +0.925 | −0.036 | +59.7 | −34,122 | +113 | +331 |

- **The vol-regime overlay does not improve risk-adjusted return.** The PRIMARY
  `high_boost` Sharpe uplift is **−0.006 (flat)**; `vol_linear` −0.025; the mirror
  `vol_down` worst at −0.036.
- **Direction is consistent with EXP-0039, magnitude is not monetizable.** `high_boost`
  beats the mirror by +0.030 Sharpe — boosting high vol IS better than deweighting it,
  exactly as the real per-cell edge concentration predicts. But levering the
  high-Sharpe/high-VARIANCE days raises std about as much as mean, so the aggregate
  Sharpe is unmoved. The unconditioned 1x book is already ~Sharpe-optimal across vol.
- Only side effect: `high_boost` mildly SHALLOWS max drawdown (+$2,440) and lifts mean$
  (partly the mean_w 1.037 > 1), but Sharpe-neutral and tail (CVaR5) slightly worse.

This is the exact EXP-0028 outcome generalised: a REAL per-unit signal (EXP-0039's
vol-edge concentration is genuine, null-confirmed) that does NOT monetize as a portfolio
sizing lever — the [[nq-noise-vwap-hurst-filter]] / quality-not-alpha pattern.

## Frame B — vol-target interaction (DESCRIPTIVE): confounded, fails its own mirror

| schedule | Sharpe | dSharpe | maxDD | CAGR |
|---|---|---|---|---|
| unsized (vol-target) | +1.364 | — | −17.1% | +26.8% |
| high_boost | +1.893 | +0.529 | −17.9% | +28.2% |
| vol_linear | +1.924 | +0.560 | −17.0% | +28.7% |
| vol_down (mirror) | +1.603 | **+0.239** | −17.3% | +24.3% |

Every schedule — **including the mirror** — raises the vol-targeted Sharpe. A mirror
that also "wins" means the gain is NOT the vol signal; it is a generic artifact of
multiplying a mean-1 weight onto the integer-floored, vol-targeted return series (the
reweighting interacts with the vol-target quantisation, not with edge direction). Frame
B therefore fails its own control and provides NO evidence for vol-conditioned sizing.
The clean Frame-A overlay (no flooring/compounding confound) is the interpretable test.

## Verdict: NO-GO

Frame-A real fails the primary metric (Sharpe uplift ~0), so by the standing
[[gate-nullc-on-success-metric]] rule the 40-draw Null C is NOT spent — a real pass that
does not clear the primary is already a REJECT. Frame B's apparent uplift is
disqualified by its own mirror control.

**Synthesis across EXP-0038/0039/0040:** the strategy's intraday edge is genuinely
vol-DEPENDENT and concentrated in high vol (EXP-0039, real vs null z=4.26) — but that
concentration is (a) not gateable (elevated cells still carry positive edge; skipping =
turnover lever) and (b) not monetizable by sizing (Frame A flat; levering high-vol days
adds variance in step with return). The "edge is volatility-independent for TRADING
DECISIONS" prior stands: vol changes WHERE the edge is measured, not how to size or gate
it. Vol-targeting remains a survival/drawdown tool, not alpha. Retain the unconditioned
1x book. No core engine change (overlay lives only in `scripts/hyp_0028_vol_sizing.py`).

## Caveats
Consumed history (3rd look on this axis); the flat Frame-A result is a rejection, not a
survivor, so no forward shadow is triggered. The mild `high_boost` drawdown reduction at
flat Sharpe could be revisited ONLY on future/shadow data if drawdown (not Sharpe)
became the objective.

## Outputs
`real.json` (Frame A + B), this review.
