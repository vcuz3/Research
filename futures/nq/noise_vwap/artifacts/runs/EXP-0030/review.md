# EXP-0030 Results Discussion

- Hypothesis: `HYP-0021` — Multi-horizon percentile-ranked breakout strength with hysteresis improves NQ
- Status: completed - rejected
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Family-best zero-trade-day daily net-ATR-R Sharpe uplift with net R co-primary
- Kill test: Reject unless family-best NQ dSharpe >= +0.10, net R >= baseline, and gross expectancy per trade rises; if passed require family-max paired Null C z>=2 and upper-tail fraction<0.05.

## Result versus hypothesis

The family failed decisively.  Baseline was 4,209 trades, 91.20 net R,
Sharpe 1.288, 3.509 gross points/trade, and 4.70R max drawdown.  The family-best
cell was `q_enter=0.60, q_exit=0.20`: 1,556 trades (37.0% retention), 39.42 net
R, Sharpe 0.694 (delta -0.594), 4.247 gross points/trade, and 7.18R max drawdown.
It raised trade-level quality but destroyed exposure and portfolio performance.

## Gross, net, baseline, and null comparison

Rank-only `q_enter=0.60` produced Sharpe 0.637 and 35.33R.  Adding the best
hysteresis exit lifted those to 0.694 and 39.42R, but remained far below the
unfiltered baseline.  No Null C was run because the real family missed both the
+0.10 Sharpe and non-negative net-R gates by wide margins.

## Regimes, sensitivity, and alternative explanations

The result is stable across the small frozen family: every arm reduced Sharpe by
0.594 to 0.988 and net R by 51.8R to 78.1R.  Stronger entry ranks were not
monotone: `q_enter=0.80` gross expectancy fell below baseline.  The inverted
weak-rank control (`side score <=0.40`) retained 2,948 trades and also lost to
baseline (Sharpe 1.138, net R 63.11R), although its 3.34R max drawdown improved.
Thus the score is neither a clean monotone strength factor nor a sign-reversed
edge.  Hysteresis lengthened mean holding time from 67.7 to 106.9 minutes and
reduced stop exits from 3,414 to 949, confirming that it changed churn/state as
intended; the economic trade-off was still strongly negative.

## Artifact and implementation risks

Feature coverage by minute-of-session was 96.45%-100%; missingness is the causal
252-session/minimum-same-sign warmup, not a time-of-day liquidity filter.  The
feature uses only closes through the decision/current bar, prior-known ATR, and
strictly prior same-minute observations; fills remain next-open.  Direct
invariant tests verified prior-only sign ranking and future-change invariance.
Default-off Python-engine output matched the existing numba baseline exactly.
`pytest` was unavailable in the environment, so the two new unit assertions
were run directly; the legacy standalone parity command exceeded 120 seconds,
but the in-script full-data parity assertion passed before treatments ran.

An initial provisional sweep used a direction-agnostic entry key.  It was
discarded before interpretation.  The engine gate was made backward-compatible
and side-aware, and all reported artifacts are from the corrected rerun.

## Builder interpretation

REJECT.  Percentile ranking does identify a modest higher-gross subset around
`q_enter=0.60-0.70`, and hysteresis adds a small conditional improvement, but
both are dominated by the exposure loss.  This repeats the project's Hurst and
cross-market-confirmation pattern: quality/capacity information does not become
portfolio alpha.  Retain the unconditioned continuous-stop baseline.

## Independent review

- Review status: pending independent review
- Objections: none recorded by builder
- Verdict: builder rejects

## Promotion decision

- `reports/FINDINGS.md`: not promoted; project memory is sufficient
- `MEMORY.md`: record the rejected branch and evidence
- Shared `LEARNINGS.md`: not eligible without cross-project verification
