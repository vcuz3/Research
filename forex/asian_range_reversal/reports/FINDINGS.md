# Findings

## EXP-0001 — unrestricted stateful RSI-extreme fades (2012-2020)

Verdict: **REJECT**. Both midpoint and opposite-boundary variants have negative
gross pips/trade in EURUSD and GBPUSD. A 0.5-pip hypothetical cost makes daily
Sharpe -1.01 and -0.78 for the midpoint variant. See
`artifacts/runs/EXP-0001/review.md` and immutable CSV/JSON artifacts beside it.

Post-hoc only: London shorts and mild (not severe) RSI exceedances are the most
coherent screens. The most extreme RSI and highest ATR quintiles are negative in
both pairs, consistent with continuation overwhelming the fade. These screens
have consumed 2012-2020 and require one frozen revision before 2021-2023 is run.

## EXP-0002 — frozen London first-trade revision (2021-2023)

Verdict: **FAIL declared locked-era gate**. Gross expectancy improved to +0.476
EURUSD and +0.808 GBPUSD pips/trade, but at 0.5 pip EURUSD is -0.024 and GBPUSD
+0.308. Required direction slices fail for EURUSD shorts (-0.139) and GBPUSD
longs (-0.213). All 20-day block intervals include zero; equal-risk pair results
are negative; annual signs are unstable. Do not select the strong GBPUSD-short
cell post hoc. Evidence: `artifacts/runs/EXP-0002/review.md`.
