# EXP-0005 Results Discussion

- Hypothesis: `HYP-0003`.
- Status: completed.
- Builder: Codex.
- Reviewer: unassigned.
- Primary metric: full-sample net daily Sharpe; expected 0.99 +/-0.10.

## Result versus hypothesis

Primary Sharpe is 1.014, +0.024 above expected and inside tolerance. The
reproduction passes. All ten engine/feature tests pass.

## Gross, net, baseline, and controls

Gross/net compounded returns are 174.93%/144.85%; cost reduces Sharpe from
1.139 to 1.014. Net annualized return is 9.79%, realized volatility 9.67%, and
maximum drawdown -15.36%.

## Attribution and alternative explanations

Dropping inactive days raises Sharpe to 1.118; gating on the prior RTH close
gives 1.044; removing SMA gives 0.960; fixed 1x gives 1.082; close-to-close vol
sizing gives 0.917. None indicates a material unexplained gap from 0.99.

## Data and implementation risks

Both tiles are unique and ordered, and all 2,576 matched candidates have exact
15.5-hour clocks. However, LSE exposes only constant symbol `NQ.F`; contract
rolls cannot be identified or excluded. A large March 2020 data gap does not
form a candidate but remains a source-quality limitation.

## Builder interpretation

Mechanical figure parity succeeds. Preserve the primary convention as the
reference implementation. This is not a deployment validation of the LSE
continuous series.

## Independent review

- Review status: pending.
- Verdict: pending.

## Promotion decision

- Added to `reports/LSE_SMA200_FIGURE.md`, `reports/FINDINGS.md`, and `MEMORY.md`.
- Not eligible for shared learnings.

