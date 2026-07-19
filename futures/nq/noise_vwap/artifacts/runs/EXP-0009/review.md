# EXP-0009 Results Discussion

- Hypothesis: `HYP-0002` — One-second first-touch exits preserve the GO continuous-stop edge
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: zero-eligible-day one-contract daily net Sharpe at 0.5
  tick/side plus fees versus the current one-minute continuous stop
- Kill test: reject preservation if first-touch Sharpe is more than 0.15 below
  the one-minute continuous-stop Sharpe or if net daily mean is non-positive

## Result versus hypothesis

PASS. On the common 3,628-session sample (2011-12-08 through 2026-07-14),
the existing one-minute close/next-open continuous stop produced zero-day daily
net Sharpe 0.923 at the primary 0.5-tick/side slippage assumption. The causal
one-second first-touch version produced 0.883, a change of -0.040. This is inside
the predeclared maximum degradation of 0.15 and its daily net mean remained
positive at $66.57 per eligible session.

## Gross, net, baseline, and null comparison

Primary cost is 0.5 NQ tick plus $2.25 per side. All daily metrics include the
zero-trade eligible sessions.

| execution | trades | gross pt/trade | net pt/trade | daily net $ | t | Sharpe |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| 1m baseline, next open | 2,923 | 4.945 | 4.470 | 72.03 | 3.15 | 0.829 |
| 1m continuous, next open | 4,209 | 3.509 | 3.034 | 70.40 | 3.50 | 0.923 |
| 1s touch, decision refresh | 4,372 | 3.428 | 2.953 | 71.17 | 3.58 | 0.942 |
| 1s touch, every-minute refresh | 4,663 | 3.065 | 2.590 | 66.57 | 3.35 | 0.883 |

The project's vol-targeted headline Sharpe was 1.184 for the one-minute
continuous stop and 1.090 for the every-minute-refreshed one-second touch exit.
Their CAGR/max drawdown figures were 22.5%/-18.1% and 19.5%/-24.4%, respectively.
No Null C was run because this experiment tests execution-timing preservation,
not a newly selected predictive feature; both versions retain the same entry
information and are compared directly on the same sessions.

## Regimes, sensitivity, and alternative explanations

The preservation conclusion is stable across the prespecified slippage range:

| slippage/side | 1m continuous Sharpe | 1s every-minute touch Sharpe | delta |
| ---: | ---: | ---: | ---: |
| 0.25 tick | 0.961 | 0.926 | -0.035 |
| 0.50 tick | 0.923 | 0.883 | -0.040 |
| 1.00 tick | 0.846 | 0.797 | -0.049 |

The decision-refreshed one-second control was slightly stronger than the
every-minute-refreshed version. That is an inspected historical comparison, not
an independently validated improvement. First-touch exits increase turnover by
closing on wicks that a close-confirmed engine ignores, explaining part of the
lower net return and the larger cost sensitivity.

## Artifact and implementation risks

- The 142,481,276-row source was column-pruned and scanned once. Vectorized UTC
  interval lookup retained 68,265,250 RTH second bars; all 3,628 eligible sessions
  were covered. Runtime was 55.7 seconds.
- A 20-session/7,800-minute alignment sample matched the clean one-minute
  open/high/low values exactly (maximum absolute difference 0 for each field).
- Stop levels use only the prior completed one-minute bar. Current incomplete
  minute VWAP is never read. Synthetic tests cover first-touch ordering and
  adverse gap-through fills.
- One-second OHLC cannot resolve price order within a second. An entry-minute
  touch is resolved adversely as active after entry. This is conservative but
  not tick-by-tick reconstruction.
- The stop is modeled as a market order, so queue priority is irrelevant; spread
  and impact are approximated by fixed slippage. No bid/ask or depth data were
  available, hence the 0.25-1.0 tick sensitivity.
- The experiment has not received independent review.

## Builder interpretation

The user's expectation is supported: moving from close-confirmed next-open exits
to causal first-touch exits does not destroy the continuous-stop Sharpe. It is not
an improvement on this consumed history: it trades more often, gives up about
0.04 zero-day Sharpe at the primary cost, and has a weaker vol-targeted CAGR and
drawdown than the current one-minute continuous-stop implementation. Treat the
one-second engine as a more execution-realistic sensitivity, not a new GO signal.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: not promoted; execution sensitivity only
- `MEMORY.md`: update with the confirmed preservation result and limitations
- Shared `LEARNINGS.md`: not eligible without cross-project verification
