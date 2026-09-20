# Strategy Specification

## Source

- Citation: user-supplied strategy request, 2026-08-24; no external paper.
- Version: study v1.
- Code/data links: `../scripts/run_study.py`, `../experiments/configs/study_v1.json`.

## Universe and data

- Instrument: CME E-mini Nasdaq-100 futures (NQ), long only.
- NQ source: `futures/nq/data/NQ_1m_clean.parquet`, unadjusted Databento
  `NQ.v.0` continuous front contract with contract IDs and roll flags.
- VIX source: `futures/data/vix/CBOE_DLY_VIX, 1D_021cd.csv`.
- Frequency/fields: one-minute NQ OHLCV and daily VIX OHLC.
- Calendar/timezone: all decisions use `America/New_York`, including DST.
- Roll rule: exclude a trade if the continuous contract changes after entry and
  through exit, or if entry and exit contract IDs differ. No back-adjusted price
  is used for execution P&L.

## Strategy contract

- Session label: an entry on local calendar date D at 18:00 belongs to trade
  date D+1. It exits at 09:30 on D+1.
- Baseline signal: long every valid session.
- Entry: market-order proxy at the exact 18:00 one-minute bar open.
- Exit: market-order proxy at the exact 09:30 one-minute bar open.
- Missing clock policy: require both exact bars; never substitute a later bar.
- Moving-average variant: enter only when the 18:00 entry price is strictly
  above an x-session simple moving average of completed 15:59 RTH closes. Sweep
  x over 5, 10, 20, 50, 100, and 200 sessions.
- VIX variant: enter only when the most recent VIX daily close available by
  18:00 is `>= lower` and `< upper`. Sweep the bounds frozen in the config.
  Joins are backward-only and capped at four calendar days.
- Equal sizing: one NQ contract.
- Inverse 14-day ATR sizing: prior causal median 14-day ATR divided by the
  current completed 14-day ATR.
- Inverse VIX sizing: prior causal median of `prior NQ close * VIX / sqrt(252)`
  divided by the current value.
- Inverse previous-day ATR sizing: prior causal median true range divided by
  the latest completed RTH true range. Here one-day ATR means true range.
- Sizing reference: shifted trailing 252-session median, minimum 60 earlier
  observations; research units clipped to [0.25, 4.0]. Fractional units are the
  default for clean sizing comparison. Set `integer_contracts=true` for nearest
  whole-contract deployment tests.
- True range: max of high-low, absolute high-prior-close, and absolute
  low-prior-close on 09:30-15:59 RTH bars.
- Costs: report gross and net. Default net deducts one NQ tick of slippage per
  side plus $2.50 commission per side: $15 round trip per contract.
- Contract economics: 0.25-point tick, $20 per point.
- Accounting: at most one position; daily portfolio P&L is the position P&L,
  never a mean across trades.
- Primary metrics: net dollars per trade, net daily Sharpe, HAC(5) t-statistic,
  total costs, turnover, hit rate, and maximum drawdown.

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative sensitivity | Evidence |
| --- | --- | --- | --- |
| “Globex start” | 18:00 New York time | Configurable future clock sweep | CME equity-index convention; user wording |
| “Previous day” for a Sunday entry | Latest completed market day, normally Friday | Require same calendar date | Causal bounded as-of join |
| Daily close for NQ indicators | Last RTH minute close at 15:59 | Settlement-price data | Only bar data supplied |
| Previous-day ATR | Latest one-session true range | A multi-day ATR with another lookback | User separately requested 14-day ATR |
| Inverse-vol scale | Prior rolling median/current proxy | Fixed dollar-vol target | Avoids full-sample normalization and arbitrary capital |
| Contract rounding | Fractional research units | Nearest whole contract via config | Separates signal/sizing study from account scale |
| Market-order cost | One tick per side plus commission | Cost stress required before deployment | No bid/ask data in baseline |

## Figure reproduction: 10% volatility-targeted leg

This separate arm preserves the baseline entry/exit candidates but changes the
estimand from contract dollars to daily capital returns.

- Gross leg return: `exit_price / entry_price - 1`.
- Volatility estimate: sample standard deviation of the prior 60 valid gross
  leg returns, multiplied by `sqrt(252)`. It is implemented as
  `gross_return.shift(1).rolling(60, min_periods=60).std(ddof=1) * sqrt(252)`.
- Leverage: `min(0.10 / annualized_vol_estimate, 3.0)`; no volatility floor or
  full-sample normalization.
- Costs per side: adverse price move of `min(0.5 bp * fill price, 0.25 point)`.
  Both entry and exit costs are divided by entry notional and scaled by leverage.
- Daily net return: leverage times gross leg return less both endpoint costs.
- Yearly return: compounded daily net returns. Annualized volatility and Sharpe
  use 252 observations; drawdown is computed on compounded within-year wealth.
- The first 60 otherwise-valid trades are explicit warm-up exclusions.
- Config/run: `experiments/configs/figure_vol_target_10pct.json` and
  `scripts/run_vol_target_figure.py`.

“Per leg” is interpreted as the overnight leg's own realized return volatility,
not full-session NQ close-to-close volatility. This is the load-bearing choice
to compare if the external figure used a different convention.

## LSE SMA200 figure reproduction

- Source tiles: both parquet files under `futures/nq/data/lse/`, concatenated by
  UTC timestamp, sorted, and de-duplicated.
- Source limitation: both identify every row only as `NQ.F`; underlying contract
  IDs and roll flags are absent, so roll-crossing trades cannot be excluded.
- Session/fills: unchanged exact 18:00 and next-date 09:30 New York bar opens.
- Daily feature: simple mean of the most recent 200 completed RTH closes, where
  RTH is 09:30-15:59 New York. The 18:00 entry price must be strictly above it.
- Warm-up/accounting: all dates before SMA200 is populated are excluded. After
  warm-up, below-SMA dates remain zero-return portfolio observations; they are
  not dropped from Sharpe or volatility calculations.
- Volatility targeting and costs: identical to the 10%/60-day/lag-one/3x/capped
  0.5-bp specification above. The volatility estimate uses all prior overnight
  leg returns, not only dates on which the SMA gate is active.
- Expected comparison: full-sample Sharpe 0.99, with a predeclared tolerance of
  +/-0.10. Outside tolerance triggers gross/net, active-day, close-gate,
  no-SMA, fixed-1x, and close-to-close-volatility attribution arms.
- Config/run: `experiments/configs/lse_sma200_vol_target.json` and
  `scripts/run_lse_sma200_figure.py`.

## LSE versus Databento source comparison

- The primary comparison applies the LSE figure's complete specification to
  both sources: strict 200-close warm-up, entry-price-above-SMA200 gate,
  zero-return inactive dates, 10% target from the lagged 60-leg volatility,
  3x cap, and capped 0.5-bp-per-side costs.
- Source-own-history yearly results answer what each complete pipeline produces.
  A separate common-date panel removes unequal calendar coverage.
- Common-date attribution holds the LSE gate and leverage fixed and substitutes
  only the Databento net leg return. The residual Databento-own minus this
  controlled Databento return measures signal/sizing-history effects; dates
  absent from either source are reported separately.
- EXP-0004's unfiltered Databento result is retained only as a diagnostic for
  the earlier non-like-for-like comparison. It is not evidence of a vendor
  difference.
- Config/run: `experiments/configs/compare_lse_databento.json` and
  `scripts/compare_lse_databento.py`.
