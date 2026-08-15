# Paper Specification: AUD triangular-pricing dislocation

## Source

- Citation: user-supplied strategy description; no external paper supplied.
- Version/date: received 2026-08-13.
- Paper code/data links: not applicable.

## Universe and data

- Instruments: AUDUSD, AUDJPY, and USDJPY spot-FX midpoint archives.
- Date range: user-selectable; notebook defaults to 2015-01-01 through 2019-12-31.
- Frequency and fields: one-minute OHLC resampled to user-selected 1/5/15/30/60-minute complete bars.
- Sessions/calendar/timezone: UTC; AUDUSD is the canonical session calendar; exact timestamp inner join; no forward fill.
- Adjustments/rolls: not applicable to spot FX. Vendor/source differences remain a material risk.

## Strategy contract

- Feature definitions and lookbacks: synthetic AUDUSD = AUDJPY/USDJPY; arithmetic spread and log basis are both reported. A user-selected rolling Z-score uses prior bars only and a fractional 90% history floor.
- Signal decision clock: completed user-selected bar. Positive Z above the threshold is short; negative Z below minus the threshold is long. First threshold crossing is the default; repeated state signals are optional.
- Entry/exit/flip rules: enter the requested AUDUSD-only arm or a three-leg residual at the next complete bar open; exit after a fixed user-selected number of complete bars. No overlapping events by default. A two-bar entry is a mandatory boundary control.
- Position sizing and constraints: unit log-return exposure per leg for the diagnostic; no capital or leverage claim.
- Fill convention and order type: midpoint next-bar open and later close for research only. This is not an executable fill model.
- Fees, spread, slippage, and financing: editable round-trip basis-point sensitivity per leg; financing omitted. Quote-level follow-up is required.
- P&L/accounting convention: AUDUSD-only return and residual return `r_AUDUSD - r_AUDJPY + r_USDJPY`, oriented to fade the basis. Daily P&L sums non-overlapping events.
- Metrics and annualization: mean/median bps per event, hit rate, UTC-day clustered t-statistic, and daily Sharpe.

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative sensitivity | Evidence |
| --- | --- | --- | --- |
| “Triangular arbitrage” versus relative value | Midpoint bars test only relative-value mean reversion | synchronized bid/ask cycle inequalities | user text and executable FX conversion algebra |
| Timeframe | user selectable; default 5 minutes | 1/5/15/30/60 minutes | user requested choice |
| Z-score parameter | threshold and lookback both user selectable | neighboring frozen values | user requested choice |
| Exit rule | fixed horizons | later preregistered zero-crossing exit | user did not specify an exit |
| Repeated extreme bars | first crossing by default | every-state-bar mode | avoids mechanically repeated entries |
| Same close/next open boundary | next-bar open baseline | paired two-bar embargo | shared workspace learning on midpoint-bar reversion |
