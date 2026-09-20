# EXP-0004 Results Discussion

- Hypothesis: `HYP-0002`.
- Status: completed.
- Builder: Codex.
- Reviewer: unassigned.
- Primary metric: calendar-year compounded net return and realized annualized
  volatility.

## Result versus hypothesis

All mechanical kill tests passed. Sixty trades were used only for warm-up,
leverage never exceeded 3x, and endpoint costs never exceeded one tick.

## Gross, net, and costs

Across 3,701 sized trades, gross compounded return is 329.79% and net is
214.68%. Net annualized compound return is 8.12%, realized annualized volatility
11.06%, Sharpe 0.762, and maximum drawdown -23.82%. The cap bound on 11 days.

## Regimes and alternative explanations

Fourteen of sixteen calendar-year rows are positive. 2016 returned -7.42% and
2022 -15.88%. The largest positive year is 2017 at 32.51%, when average leverage
was 2.227x and all 11 capped days occurred. The “per leg” volatility convention
is load-bearing: an external implementation using NQ close-to-close volatility
will not match this series.

## Artifact and implementation risks

The run reuses the audited EXP-0003 candidates and therefore inherits their
one-minute fill and sparse-window limitations. External figure values were not
provided, so deterministic mechanics are reproduced but numerical parity is
not yet testable.

## Builder interpretation

The supplied specification produces a reasonably close 10% risk target, with
11.06% realized net volatility. Preserve this as the overnight-leg convention;
request the reference numbers or code before changing the estimator definition.

## Independent review

- Review status: pending.
- Verdict: pending.

## Promotion decision

- Added provisionally to `reports/FINDINGS.md` and `MEMORY.md`.
- Not eligible for shared learnings.

