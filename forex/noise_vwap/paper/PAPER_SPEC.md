# FX Noise-Area + TWAP faithful specification

A compact contract for the FX port of the Zarattini / Quantitativo intraday
Noise-Area + VWAP momentum strategy. The reference implementation it is derived
from is `futures/nq/noise_vwap/` (`paper/PAPER_SPEC.md`, `core/engine.py`,
`core/data.py`); the source PDFs live there (`paper/4824172.pdf`,
`paper/5095349.pdf`).

Discrepancies between this specification and the code in `core/` are defects
until resolved explicitly.

## Universe and data

- EURUSD, GBPUSD, AUDUSD, NZDUSD spot, 1-minute IBKR **midpoint** bars.
- Source `forex/data/{pair}_intraday_1min.csv`, cleaned to
  `forex/data/clean/{PAIR}_1m_clean.parquet` by `core/build_clean.py`.
- Coverage 2011-07-20 → 2026-07-17 (NZDUSD from 2011-12-07).
- Timestamps are tz-aware UTC in the source and are converted directly to
  America/New_York; no lossy intermediate zone.

## The one structural difference from the NQ/ES reference

IBKR cash FX publishes **no size**: `volume == -1` on 100% of the 22.0M source
rows across the four pairs. The published strategy uses the session VWAP in two
roles — an entry gate and the stop reference — so both need a replacement.

The replacement is the session **TWAP**: the causal cumulative mean of the
typical price `(H+L+C)/3` within the session. This is not a new indicator; it is
the VWAP formula evaluated with the only volume vector the data supports:

    VWAP = sum(tp_i * v_i) / sum(v_i)    with v_i constant    =>    mean(tp_i)

`tests/test_core.py` pins both directions of that claim: TWAP equals VWAP under
a constant volume column, and TWAP is NOT equal to a volume-weighted average
when the weights actually vary. The substitution is exact under the data's
constraint and honestly lossy relative to a market that publishes size.

## Sessions

Two definitions are carried; both are anchored on the ET wall clock (US DST
switches at 02:00 on a Sunday, inside the closed FX weekend, so no session
crosses a transition).

| id | window (ET) | minutes | rationale |
| --- | --- | ---: | --- |
| `fxday` | 17:15 → 16:59 | 1425 | the FX trading day; the faithful "one instrument-day" port |
| `active` | 03:00 → 16:59 | 840 | London open → NY close; the closer analogue of an equity cash session, and the only one with a real overnight gap |

The `fxday` anchor is 17:15 ET rather than the nominal 17:00 roll because of a
measured archive defect — see `reports/DATA_QUALITY.md`.

## Noise estimate and bands

Identical construction to the reference:

    move[d, mfo]  = |close[d, mfo] / open[d, 0] - 1|
    sigma[d, mfo] = mean of move over the prior `lookback` sessions (shift 1)
    upper[d, mfo] = max(open[d], prior_close[d]) * (1 + sigma)
    lower[d, mfo] = min(open[d], prior_close[d]) * (1 - sigma)

`lookback = 90` (the Quantitativo case). `min_periods` is the rule-9a fractional
floor `ceil(0.9 * lookback)`, not the strict `min_periods = lookback` that
silently deleted 28% of GC's late-day decisions.

## Anchor

Causal cumulative session TWAP of `(H+L+C)/3`, reset each session. Bar `t` uses
only bars `0..t`.

## Decision clock

Concretum clock, pinned to the **ET wall clock**: decide on the close of every
bar whose ET minute-of-hour is `:29` or `:59`. Decisions inside the first
30-minute block and inside the final block are dropped. This gives 46 decisions
per `fxday` session and 27 per `active` session.

Pinning to the wall clock rather than to minutes-from-open keeps every decision
out of the `:00–:14` archive gaps documented in `reports/DATA_QUALITY.md`.

## Signal

- long: `close > upper` and (gate on) `close > twap`
- short: `close < lower` and (gate on) `close < twap`
- a reverse signal flips at the same decision bar
- flat at the session close

## Stops

Checked every bar by default (`exit_check="every_bar"`, close-confirmed), with
`decision` cadence as the declared alternative. Three references:

| `stop_ref` | long stop below | short stop above | volume-free? |
| --- | --- | --- | --- |
| `both` | `max(upper, twap)` | `min(lower, twap)` | no |
| `band` | `upper` | `lower` | **yes** |
| `anchor` | `twap` | `twap` | no |

## Fills

Signals are taken on the decision bar's CLOSE; every entry, exit and flip fills
at the **next 1-minute bar's open**. The forced flatten uses the last session
bar's close. No fill ever occurs at the signal bar's own close or at the band or
stop level; both are asserted in `tests/test_core.py`.

## Costs and units

- 1 pip = 1e-4 of quote for all four USD-quoted majors; $10 per pip per
  100,000-unit lot.
- Headline cost 0.50 pip per side (1.0 pip round trip) on midpoint data;
  sensitivity at 0.25 and 1.00 pip per side. Gross is always reported separately
  (rule 20).
- Effect sizes in pips and in R, where R = net pips / causal prior-session
  ATR(14) in pips (rule 19: a fixed pip cost consumes a smaller fraction of a
  wider range, so pip-normalised results flatter high-volatility eras).
- The P&L series is the per-SESSION SUM with no-trade sessions entering as 0
  (rule 13). Inference is session-clustered (rule 12).
