# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — The weekday 09:30 ET Noise-VWAP timing rule transfers to BTCUSDT
- Status: completed
- Builder: Codex
- Reviewer: pending
- Primary metric: Temporal-OOS net daily Sharpe
- Kill test: Reject if OOS net Sharpe is not positive or OOS mean gross return per trade does not exceed 10 bps

## Result versus hypothesis

The frozen baseline passed its literal first-screen kill rule, but only
narrowly. Temporal-OOS net daily Sharpe was 0.230. Mean OOS gross return was
11.835 bps/trade versus the assumed 10 bps round trip, leaving 1.835 bps/trade
net. In-sample Sharpe was -0.223, so the sign did not persist across the split.

## Gross, net, baseline, and null comparison

At fixed one-unit notional:

- In sample (933 sessions, 691 trades): total net return -22.10%, annual net
  return -6.52%, Sharpe -0.223, max drawdown -55.71%, gross 7.52 bps/trade.
- Temporal OOS (942 sessions, 749 trades): total net return +9.45%, annual net
  return +2.44%, Sharpe 0.230, max drawdown -33.73%, gross 11.835 bps/trade.
- Always-long control net Sharpe: -0.507 in sample and -0.883 OOS.
- No path-preserving Null C was run. The result cannot yet be attributed to the
  same-time-of-day timing feature rather than drift/path geometry.

## Regimes, sensitivity, and alternative explanations

Annual net Sharpe was strongly unstable: 2019 +2.68, 2020 -1.72, 2021 -1.53,
2022 +0.01, 2023 +2.01, 2024 +0.56, 2025 -1.72, and 2026 YTD -0.66. The OOS
average is carried by 2023-2024 and reversed in the two most recent segments.
The gross edge is cost-fragile: a 5.92 bps per-side cost would consume the OOS
mean gross trade before any borrow, funding, spread, or impact.

## Artifact and implementation risks

The notebook uses spot bars as a reference series although shorts require a
different vehicle. It omits funding, borrow, liquidation, spread, and impact.
The OOS interval is temporal but not sealed. The 09:30 anchor and 390-minute
universe are economically prespecified, but no neighboring-anchor sensitivity
or full selection-adjusted null has been run.

Data gates passed: 4,000,250 loaded rows; 22 gaps / 4,090 missing minutes in the
loaded slice; 1,984 of 1,987 candidate sessions retained; 100% band coverage in
both evaluated splits; zero same-bar fills, zero non-exact next-minute fills,
and zero overlapping positions. Missing bars were never forward-filled.

## Builder interpretation

Treat as a narrow screen survival, not a GO. The positive OOS Sharpe and gross
expectancy clear the prespecified threshold, but the negative in-sample result,
recent reversal, and 1.835 bps/trade cost cushion are inconsistent with a robust
or deployable edge. The next useful test is a path-preserving Null C on this one
frozen cell, followed by intended-venue execution and cost replay only if it
survives.

## Independent review

- Review status: not reviewed
- Objections: independent review is still required; spot-to-shortable-vehicle
  basis and costs are unresolved.
- Verdict: pending independent review

## Promotion decision

- `reports/FINDINGS.md`: updated as provisional
- `MEMORY.md`: updated
- Shared `LEARNINGS.md`: not eligible without cross-project verification
