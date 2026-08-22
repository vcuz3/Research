# Bitcoin Noise-Area + VWAP Adaptation Specification

## Source

- Citation: Zarattini, Aziz, and Barbon, "Beat the Market: An Effective
  Intraday Momentum Strategy for S&P 500 ETF (SPY)", September 22, 2025;
  Quantitativo, "Intraday Momentum for ES and NQ".
- Local reference implementation: `../../../futures/nq/noise_vwap/`.
- This project is a transparent BTCUSDT transfer test, not a claim that the
  equity-index result should transfer to Bitcoin.

## Universe and data

- Instrument: Binance Spot BTCUSDT used as the price and volume reference.
- Default load range: 2019-01-01 through 2026-08-12; all dates are editable in
  the notebook.
- Frequency and fields: one-minute OHLCV bars from the audited shared Parquet.
- Timezone: timestamps originate in UTC and are converted with the IANA
  `America/New_York` timezone. All displayed clocks and session labels are ET.
- Default session: weekdays, 09:30 through 15:59 ET (390 minutes). The anchor,
  session length, and weekend inclusion are parameters.
- No rolls or corporate actions apply. BTCUSDT is a continuous spot pair.

## Strategy contract

- Feature definitions and lookbacks: cumulative session typical-price VWAP;
  same-minute absolute displacement from the anchor open averaged over the
  prior 90 eligible sessions. A configurable 90% observation floor prevents a
  single missing BTC bar from silently deleting an entire decision slot.
- Bands: `upper = max(anchor_open, prior_session_close) * (1 + sigma)` and
  `lower = min(anchor_open, prior_session_close) * (1 - sigma)`.
- Signal decision clock: every 30 minutes, with the open bar counted as minute
  one, so the default decisions are 09:59, 10:29, ..., 15:59 ET.
- Entry: long above both upper band and VWAP; short below both lower band and
  VWAP. Stops use `max(upper, VWAP)` for longs and `min(lower, VWAP)` for shorts.
  Opposite signals flip the position. Stops are checked on decision bars.
- Position sizing and constraints: one non-overlapping unit of notional; no
  volatility targeting in this diagnostic baseline.
- Fill convention and order type: decisions use a completed bar and market
  orders fill only at the exact next one-minute bar open. Orders are skipped if
  that bar is missing. Existing positions flatten at the final session close.
- Costs: editable basis points per side, default 5 bps. This is a sensitivity
  assumption, not a statement of a particular venue's current fee schedule.
  Borrow, funding, and liquidation are not modelled.
- Accounting: simple return on constant session notional; daily P&L is the sum
  of sequential, non-overlapping trades. Report gross and net separately.
- Metrics: total and annualized return, annualized volatility, Sharpe, maximum
  drawdown, trade frequency, win rate, exposure, and dollar P&L at an editable
  reference notional. Annualization is 252 for weekday-only sessions and 365
  when weekends are included.

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative sensitivity | Evidence |
| --- | --- | --- | --- |
| Bitcoin has no natural daily open | 09:30 ET, tied to U.S. cash-market price discovery | Change `ANCHOR_TIME_ET`; also change `SESSION_LENGTH_MINUTES` if testing a different decision universe | NQ source project uses the 09:30 ET cash open |
| 24/7 versus RTH decision universe | Default 390-minute weekday window to match the NQ estimand | Set `WEEKDAYS_ONLY=False` or use a 1,440-minute session, interpreted as a different strategy | `../../../ai_shared_memory/LEARNINGS.md`, section 5 |
| Missing BTC minutes | Never fill; require anchor/final bars, minimum session coverage, and exact next-minute fills | Tighten the coverage parameter to 1.00 | Shared BTC data-quality report |
| Spot data with short signals | Treat BTCUSDT spot as a reference series only | Re-run on the intended margin/perpetual venue with funding and executable quotes | Deployment requires a short-capable vehicle |
| Historical OOS label | Temporal OOS only, not sealed | Future shadow period | Shared BTC history was already available in the workspace |
