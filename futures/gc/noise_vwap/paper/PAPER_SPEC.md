# Noise Area VWAP Faithful Specification (GC port)

The strategy specification is identical to the NQ/ES project; see
`futures/nq/noise_vwap/paper/PAPER_SPEC.md` and `paper/CLAIMS.md` for the source
paper (Zarattini / Quantitativo intraday momentum) and the full contract. Only
the instrument, data path, and contract economics change here.

- Universe: one-minute RTH GC (COMEX Gold) futures, timestamps normalized to
  America/New_York, regular session bars 09:30 through 15:59 ET. (Equity-RTH
  window inherited from NQ/ES; a gold-native session is an open research question.)
- Noise estimate: mean absolute same-time-of-day move from the RTH open over the
  prior 90 sessions.
- Bands: gap-adjusted upper/lower Noise Area boundaries from the current RTH open
  and prior RTH close.
- VWAP: cumulative RTH typical-price volume-weighted average, reset daily.
- Decisions: Concretum clock at 09:59, 10:29, ..., 15:59 ET.
- Long entry: close above both the upper band and VWAP. Short entry: mirror.
- Stops (at decision times): long below `max(upper, VWAP)`, short above
  `min(lower, VWAP)`; reverse signals may flip.
- Fills: next available one-minute bar open after the decision. Final flatten is
  the last RTH close proxy. Same-close fills are an ablation, not faithful.
- Contract economics: GC = 100 troy oz, tick 0.10 = $10, 1 point = $100.
- Costs: explicit fees plus tick slippage per side; gross and net inspectable.

The executable reference is `../core/engine.py` (a verbatim copy of the audited NQ
engine).
