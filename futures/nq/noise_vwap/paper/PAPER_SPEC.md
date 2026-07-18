# Noise Area VWAP Faithful Specification

This is a compact contract derived from `../REPLICATION_PLAN.md` and the
forensic review. It describes the current faithful ES/NQ adaptation.

- Universe: one-minute RTH ES and NQ futures, with timestamps normalized to
  America/New_York and regular session bars from 09:30 through 15:59 ET.
- Noise estimate: mean absolute same-time-of-day move from the RTH open over the
  prior 90 sessions for the Quantitativo case (14 sessions for the paper case).
- Bands: gap-adjusted upper and lower Noise Area boundaries based on the current
  RTH open and prior RTH close.
- VWAP: cumulative RTH typical-price volume-weighted average, reset daily.
- Decisions: Concretum clock at 09:59, 10:29, ..., 15:59 ET.
- Long entry: close above both the upper band and VWAP.
- Short entry: close below both the lower band and VWAP.
- Stops: at decision times, long below `max(upper, VWAP)` and short above
  `min(lower, VWAP)`; reverse signals may flip.
- Fills: next available one-minute bar open after the decision. Final flatten is
  the last RTH close proxy. Same-close fills are an ablation, not faithful.
- Quantitativo sizing: 3% target daily volatility, 8x leverage cap, 14-session
  realized-volatility estimate through the prior session, floor contracts.
- Costs: explicit fees plus 0.25 tick slippage per side in the headline case;
  gross and net results remain separately inspectable.

The executable reference is `../core/engine.py`; discrepancies between this
specification and code are defects until resolved explicitly.
