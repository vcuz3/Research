# EXP-0006 Results Discussion

- Hypothesis: `HYP-0004` — Reconcile LSE and Databento yearly figures under the identical SMA200 volatility-targeted strategy.
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Calendar-year net return and Sharpe; common-date source-return, signal/sizing, and coverage attribution
- Kill test: If matching the specification does not materially reduce prior gaps, reject the specification explanation and report remaining source components.

## Result versus hypothesis

The hypothesis was partly confirmed. Matching the SMA200 specification explains
the extreme 2022 discrepancy: Databento changes from -15.88% unfiltered to
-3.35%, versus LSE -3.40%. It does not explain the 2023-2025 gaps. Common-date
reconciliation locates those gaps in quarterly LSE continuous-contract splices.

## Gross, net, baseline, and null comparison

Both matched arms use identical net cost and zero-return inactive-day
accounting. The SMA gate agrees on every common observation. Holding the LSE
gate and leverage fixed while substituting Databento leg returns attributes
6.79 percentage points of the 2024 common-date gap to source returns and only
-0.11 points to Databento signal/sizing history. This is a reconciliation audit,
so no null-distribution edge test applies.

## Regimes, sensitivity, and alternative explanations

The large mismatches cluster in March, June, September, and December roll
windows. Fifteen common observations differ by at least 50 bp; ten are active.
After their diagnostic removal, 2023-2025 annual gaps are -0.31, +0.19, and
-0.35 percentage points. Older 2018-2019 residuals reflect smaller systematic
bar differences. Coverage explains much of 2017, and unequal endpoints explain
the apparent 2026 gap.

## Artifact and implementation risks

LSE carries only constant symbol `NQ.F`, so its contract changes cannot be
identified directly. The >=50-bp classification is a post-run diagnostic, not
a predeclared filter and not suitable as a trading rule. Databento candidates
retain contract identity and exclude detected roll-crossing holds. Independent
review remains outstanding.

## Builder interpretation

The ~0.99 LSE reproduction is mechanically valid for that file but is not a
clean same-contract strategy estimate. For research or deployment, prefer the
contract-aware Databento construction or obtain documented roll/back-adjustment
metadata for LSE.

## Independent review

- Review status: not reviewed
- Objections: none recorded; reviewer unassigned
- Verdict: builder-complete, independent review pending

## Promotion decision

- `reports/LSE_DATABENTO_COMPARISON.md`: updated
- `MEMORY.md`: updated with the confirmed reconciliation facts
- Shared `LEARNINGS.md`: not eligible without cross-project verification
