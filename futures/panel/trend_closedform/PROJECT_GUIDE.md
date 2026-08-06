# Trend-following closed form as an instrument pre-screen — Project Guide

## Objective and scope

- Research question: does the closed-form expression for a European trend
  follower's P&L — a weighted sum of the return series' lagged autocorrelations
  plus a drift-squared term — **pre-screen instruments**? That is, can two cheap
  statistics per product predict which market a trend strategy should be ported
  to next, replacing a three-week empirical port?
- Instruments: the **30 distinct CME products** in `futures/data/databento/`:
  FX `6A 6B 6C 6E 6J 6N 6S`; equity index `ES NQ RTY YM`; metals
  `GC SI HG PL PA MGC`; energy `CL BZ NG HO RB MCL`; rates
  `ZT ZF ZN ZB UB SR3 ZQ`.
- Source: no paper PDF. `research_papers/ALIGRITHM_HYPOTHESES_2026-08.md` item
  **H-A1**, translating aligrithm.com *6.48 Trend-Following P&L Is a Function of
  Autocorrelation (Closed Form)* (2026-07-10), which reports Sepp & Lucic
  plumbing. `paper/` holds the transcribed claim register; there is no faithful
  replication target, so the baseline-replication gate does not apply.
- Data source and coverage: Databento `GLBX.MDP3` `ohlcv-1m`, volume-ranked
  continuous front `<sym>.v.0`, **unadjusted**, 2010-06-07 .. 2026-07-28 (later
  starts: `MGC` 2010-10, `ES`/`NQ`/`GC` 2011-08, `RTY` 2017-07, `SR3` 2019-06,
  `MCL` 2021-07). Shared instrument data — do not copy into the project.
  `data/` holds only derived caches built by `scripts/build_panel.py`.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/CLAIMS.md` — the article's claims, no PDF |
| Faithful replication | `baseline_replication/` — **not applicable** |
| Execution/accounting | `core/engine.py` (see below) |
| Panel, clocks, rolls, ticks | `core/panel.py` |
| Filters and kernels | `core/filters.py` |
| The predicted side | `core/closedform.py` |
| Rank statistics and nulls | `core/stats.py` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls/holdout | `validation/` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/` |
| Durable handoff | `MEMORY.md` |

**Why the engine is 150 lines.** The strategy is a continuously-held linear
vol-targeted position with no stop, target or barrier, so there is no intrabar
path to adjudicate (rule 3) and no queue to model (rule 4). What the engine must
get right is causality, execution timing, the roll and the accounting, and those
are what it asserts. If this project ever acquires a barrier rule it needs a real
engine and a rule-3 intrabar policy, and this section must be revisited.

## Data and session conventions

- Timestamp source and timezone: Databento `ts_event` in UTC; every derived clock
  is `America/New_York` wall time.
- Trading calendar/session: the **CME trade date**, `sdate = date(t_ET + 6h)`.
  Verified in `scripts/build_panel.py`, not assumed: all 30 products have an
  empty ET block ending 17:59 and resume at 18:00 ET. The halt *start* differs
  by product (17:00 / 17:01 / 17:15 / 17:30 ET); its end does not.
- Clocks: **daily** (last close of each trade date) is primary; **30-minute** on
  the ET wall clock (`mfo // 30`, 46 slots) is secondary. The intraday grid is
  pinned to the wall clock, never to minutes-from-open.
- Instrument/roll convention: volume-ranked continuous front, **unadjusted**. A
  price change across an `instrument_id` change is a contract substitution, not
  a return, and is dropped on both the estimation and the P&L side (rule 11).
  Nothing is back-adjusted: a back-adjusted series has different variance and
  different autocorrelations at the roll, which are the quantities under study.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: sessions with fewer than 60 bars are dropped. Windowed
  features use a **fractional** `min_periods` — daily vol `63, 2/3`; intraday
  same-slot vol `90, 45`. This is load-bearing: a strict floor deleted 100% of
  all six energy products in the first build (see `reports/FINDINGS.md`).
- Holdout: **none sealed.** This project measures an externally published formula
  against results the workspace already owns; there is no candidate edge to
  protect. If `PHI` were ever used to open a new project, that project's own data
  would be its holdout.
- Data fingerprint command:
  `.\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.build_panel`

## Units and contract economics (rule 19)

Everything is in **risk units**: `x = dp / v`, with `v` a strictly causal
trailing scale. A position of 1 risk unit carries one period-volatility of risk,
so P&L is dimensionless and comparable across a panel whose native units span
1/256 of a Treasury point to a dollar of crude. **Never put two products' native
units side by side.**

Costs are built from the **measured effective price increment** per product per
year (`data/ticks.csv`), never assumed: ten of 30 products changed increment
mid-sample at ten different dates. This is the largest increment 99% of that
year's closes lie on, which on a thin product can exceed the exchange minimum
(`PA` trades a 0.5 grid from 2021 against a 0.05 exchange tick). For a cost floor
the effective grid is the more honest input; it is labelled so it is not mistaken
for the contract specification.

Note also that **contract turnover is not comparable across products** — it
carries each product's own price scale and ranged 0.002 to 6090 in the first
build. Use `turnover_pos` (risk units) for any cross-product statement.

## Commands

```powershell
# Core invariants (30 checks) -- must pass before any run is registered
.\.venv\Scripts\python.exe -m futures.panel.trend_closedform.tests.test_core

# Build the derived panel + rule-9a data gate -> reports/DATA_QUALITY.txt
.\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.build_panel

# EXP-0001, both clocks (~2 min daily, ~15 min intraday)
.\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.s1_screen daily
.\.venv\Scripts\python.exe -u -m futures.panel.trend_closedform.scripts.s1_screen slot30
```

## Acceptance gates

- Baseline tolerance: not applicable (no replication target). The equivalent is
  **control 1**, the identity check: predicted and realised P&L at the same
  execution lag must agree to 1e-9 on every product. It currently agrees to
  4.16e-17. A failure there halts the run in code.
- Engine tests required: `tests/test_core.py` must pass 30/30. It pins, among
  others, the exact closed-form identity at both lags and through dropped rolls,
  the price-kernel to return-weight conversion for the crossover, that `w[0]`
  multiplies `x_t` (an off-by-one there shifts every lag in the formula), that a
  strict `min_periods` deletes a series with scattered roll gaps, and that
  contract turnover is not the risk-unit turnover.
- Minimum validation suite for any claim that a statistic **predicts**: an
  out-of-sample arm, a degenerate no-theory benchmark, a bootstrap of the
  **difference** between them, a re-pairing null, cluster-aware uncertainty, and
  the identity diagnostic below.
- Holdout protocol: none sealed; see above.

## Standing cautions specific to this project

1. **Ask how much of a result is algebra BEFORE reading it, not after.** `PHI`
   over a window is that window's in-sample trend P&L plus a drift term; the two
   correlate at +0.98. Any same-sample comparison of predicted against realised
   is an identity, not a test, and reporting one would be the rule-16 failure
   mode. `scripts/s1_screen.py` prints the diagnostic above the K1 block on
   purpose.
2. **Cluster by asset class, always.** `MGC` is `GC` at 1/10 notional, `MCL` is
   `CL` likewise, and `ZT ZF ZN ZB UB` are five points on one curve. The
   effective panel size is far below 30. Leave-one-class-out is more informative
   than any interval at this n.
3. **On an intraday clock, ρ(1) is largely bid-ask bounce, and it correlates
   with cost.** `Spearman(ρ1, cost) = −0.514` and `Spearman(cost, net) = −0.863`
   there, so a net-P&L arm can look predictive for reasons that have nothing to
   do with trend. Report the confound block with any intraday result.
4. **A percentile bootstrap that does not bracket its own point estimate is
   biased.** The intraday K2b difference interval does not; the daily one does.
   Read the former as "no evidence", never as a signed result.
