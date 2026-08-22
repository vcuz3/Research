# Paper Specification

## Source

- Citation: Lei Gao, Yufeng Han, Sophia Zhengzi Li, and Guofu Zhou,
  "Market Intraday Momentum," *Journal of Financial Economics* 129(2),
  394-414 (2018), DOI `10.1016/j.jfineco.2018.05.009`.
- Working-paper version inspected: October 2014, SSRN 2440866.
- Source links:
  - https://doi.org/10.1016/j.jfineco.2018.05.009
  - https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2440866
- No paper code or source data are locally available.

## Published universe and data

- Instrument: SPDR S&P 500 ETF (SPY), plus ten ETFs in extensions.
- Date range: 1993-02-01 through 2013-12-31.
- Source: TAQ intraday trades; one-minute observations for realized volatility.
- Session: 09:30-16:00 US Eastern time, divided into thirteen half-hours.
- Exclusion: days with fewer than 500 trades.
- The paper studies an ETF, not NQ or ES futures, and does not face futures
  contract-roll handling.

## Published strategy contract

- `p0,t`: prior trading day's 16:00 price.
- `r1,t = p10:00,t / p0,t - 1`: overnight plus first cash half-hour.
- `r12,t = p15:30,t / p15:00,t - 1`.
- `r13,t = p16:00,t / p15:30,t - 1`.
- At 15:30, the `r1` arm is long when `r1 > 0` and short otherwise.
- The joint arm trades only when `r1` and `r12` have the same sign; it follows
  that sign and otherwise stays flat.
- Every position is closed at 16:00. The always-long benchmark holds SPY only
  over the same last half-hour.
- Returns are unlevered market returns. Summary means and standard deviations
  are annualized by 252; Newey-West robust t-statistics are reported.
- The inspected paper does not specify executable bid/ask, latency, or
  transaction-cost assumptions for the sign-timing table.

## Local rule-transfer contract

The user restricted this study to local data, which do not contain the paper's
SPY/TAQ sample. Therefore this project **cannot reproduce the published result**.
It applies the published equations to NQ and ES as a futures persistence test.

- Data: local raw, unadjusted Databento volume-ranked continuous NQ/ES one-minute
  and one-second OHLCV, 2011-08-01 through 2026-07-14.
- Feature prices: prior 15:59 one-minute close, 09:59 close, 15:00 open, and
  15:29 close. Log returns are used; the paper reports similar results with logs.
- Roll safety: prior close, all feature endpoints, and both fills must share the
  identical instrument ID. Raw cross-roll gaps are never signals.
- Local eligibility: scheduled full NYSE session; `available` source condition
  on it and the previous expected NYSE session; present previous 15:59 endpoint;
  exactly 30 unique one-minute opening records from 09:30 through 09:59 with no
  gap over 60 seconds; a present 10:00 one-minute open and symbol; one contract
  across the previous close, 09:30, 09:59, 10:00, and held RTH session; no RTH
  roll row; and both required one-second fills. Missing feature endpoints
  hard-fail. Unrelated midday bars are not used as a selector; the strict
  390-bar cohort is a data-quality sensitivity only.
- Main `r1` entry: because `r1` is known at 10:00, schedule the first one-second
  record at or after 15:30:00 ET, plus adverse slippage.
- Joint `r1+r12` entry: the completed 15:29 bar is known at 15:30:00, so use the
  first one-second record at or after 15:30:01 ET, plus adverse slippage.
- Exit: a pre-scheduled liquidation instruction active at 15:59:59 ET; use the
  first one-second record at or after that instant but strictly before 16:00:00,
  plus adverse slippage. A missing record hard-fails the run rather than
  silently removing the session.
- Position: one full-size contract; no compounding or intraday flip.
- Primary costs: one tick adverse per side plus $4.50 round-trip fees. NQ is
  $20/point and ES is $50/point; both ticks are 0.25 point.
- All eligible sessions, including joint-signal flat days, enter daily Sharpe.

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative sensitivity | Evidence |
| --- | --- | --- | --- |
| Paper market differs from local data | Label as a futures rule transfer, never a faithful replication | None possible under local-only instruction | Published data section |
| Simple versus log returns | Log return for signs | Signs agree except exact-zero edge cases | Paper footnote 3 |
| 15:30 entry timing | r1-only: scheduled first record at/after 15:30:00; joint r1+r12: first record at/after 15:30:01 | Raw one-minute open is never an executable credit | Causality rule |
| Market-close fill | Pre-scheduled order active 15:59:59; first one-second record thereafter | 16:00:00 active-time stress if warranted | Attainable-fill rule |
| Trading costs absent in timing table | Report gross, fixed primary costs, and 0.5/1/2-tick-per-side stress | No-cost result only for paper comparability | Research config |
