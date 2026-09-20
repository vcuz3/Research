# Walk-forward Parameter Optimisation

EXP-0002 used 243 configurations per asset across:

- timeframe: 15, 30, 60 minutes;
- ATR period: 7, 14, 28;
- ATR percentile: 0.10, 0.15, 0.20;
- stop: 1.0, 1.5, 2.0 ATR;
- target: 1.0, 1.5, 2.0 ATR.

Each fold selected the highest training daily Sharpe after a 0.5-pip round-trip
charge, subject to at least 200 trades, from a rolling five-year window. The
winner was then evaluated on the next year. Eight folds begin in 2017; the last
is a disclosed partial fold from 2024-01-01 to 2024-07-18.

The stitched forward result was 4,824 trades, -0.0195 mean net R, -0.442 daily
Sharpe, and -147.1 R maximum drawdown. The static baseline on identical windows
had -0.292 Sharpe. Zero of four optimised assets had positive mean net R.

Verdict: **NO-GO**. See `artifacts/runs/EXP-0002/review.md` and
`validation/HOLDOUT_PROTOCOL.md` for complete assumptions and immutable outputs.
