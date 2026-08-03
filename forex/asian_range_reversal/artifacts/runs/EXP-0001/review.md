# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — stateful Asian-range breaks with five-minute RSI extremes
- Status: completed; initial specification rejected
- Builder: Codex
- Reviewer: not independently reviewed
- Scope: EURUSD/GBPUSD, 2012-2020 only
- Primary metric: 0.5-pip-cost mean pips/trade, midpoint target

## Result versus hypothesis

The frozen strategy fails its kill test. Midpoint gross mean is -0.095 EURUSD
and -0.078 GBPUSD pips/trade. At 0.5-pip round-trip cost it is -0.595 and
-0.578. Long gross mean is negative in both pairs (-0.247/-0.248); short gross
is only +0.064/+0.104 and becomes negative after cost. The opposite target is
worse at -0.177/-0.114 gross.

The engine generated 9,402/9,797 midpoint trades, 4.11/4.30 per eligible day.
Daily Sharpe at 0.5-pip cost is -1.01 EURUSD and -0.78 GBPUSD. Equal-risk
aggregation does not rescue it: midpoint net mean after 0.5 pip is -0.035R and
-0.041R.

## Exit and state audit

Midpoint target rates are about 21%; stop rates about 63-66%; most remaining
trades exit at 16:59. The strategy discarded 21,088/22,045 qualifying midpoint
signals while already positioned. This confirms the full state machine was run;
completed trades were not retrospectively overlapped or averaged.

## Post-hoc discovery diagnostics

These are consumed-history screens, not validated filters:

- London is the only broadly favorable entry block. Midpoint shorts earn +0.66
  EURUSD and +0.72 GBPUSD gross there; after 0.5 pip, +0.16/+0.22. London longs
  are -0.13/+0.16 gross and fail cost.
- More extreme RSI is worse, especially for longs. The mildest 20-40% of RSI
  exceedances are positive in both long legs; the most extreme quintile loses
  roughly 1.8-2.0 pips. This suggests strong excursions are continuation, not
  exhaustion.
- Later repeat entries deteriorate. First entries gross +0.45/+0.65 for EURUSD/
  GBPUSD longs, but only GBPUSD long survives 0.5 pip; fourth-plus trades are
  negative for both long legs. Sequence behavior is unstable for shorts.
- The highest ATR quintile loses about 1.5 pips gross in both pairs and sides.
  Range-width and entry-extension quintiles are not monotone or pair-stable.
- Yearly direction results change sign frequently. No raw survivor is stable
  enough to call an edge without a tightly frozen revision and locked-era test.

## Artifact and implementation risks

- The 17:00-17:14 source gap narrows the observed Asian range.
- Midpoint OHLC omits executable spread and slippage; costs are hypothetical.
- One-minute same-bar stop/target ambiguity is resolved against the strategy.
- Recursive indicators restart after missing five-minute bars.
- This run does not load or score 2021-2023, but that interval is not pristine
  because related exploration has already displayed it.

## Builder interpretation

Reject the unrestricted RSI-extreme fade. The evidence argues against “more
extreme RSI means better fade.” If a single revision is advanced, the simplest
mechanistic version is London-only, midpoint target, and a bounded mild RSI
exceedance rather than an unbounded tail. Any trade-count cap, ATR filter, or
direction filter would add further searched degrees of freedom and should not be
stacked casually.

## Independent review

- Review status: pending
- Verdict: not independently reviewed

## Promotion decision

- Initial strategy: rejected.
- Post-hoc candidates: remain in discovery; do not score 2021-2023 until one is frozen.
