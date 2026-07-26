# Course: Building a Research-Grade Backtesting Engine

A practical, opinionated course on building and validating an intraday/daily
backtesting stack from scratch — written from the engine, nulls, and protocol
actually used in this workspace (`futures/nq/noise_vwap`, `futures/gc/...`,
`futures/nq/hurst_explore`).

Everything here is code you can run, not theory. Where a lesson exists because a
real result died in this workspace, the postmortem is cited.

---

## Who this is for

You can write Python and pandas. You want to run independent backtesting
research and produce results you would still believe six months later.

The hardest part of backtesting is **not** writing the simulator. It is
building an evidence process that makes it hard for you to fool yourself. Two
thirds of this course is about that.

---

## The one idea

> A backtest is not a measurement. It is a **hypothesis about a
> counterfactual**: "if I had placed these orders, this would have happened."
> Every number it prints is a claim about order feasibility, information timing,
> and accounting. Statistics come **last**, and they cannot rescue a broken
> counterfactual.

The canonical failure in this workspace:
`futures/nq/vwap_std_breakout_1/REVIEW.md` — a Sharpe 2.07, t = 9.5,
all-eras-positive, OOS-validated result that was **entirely** an
impossible-fill artifact. Every statistical test it passed was correct. The
counterfactual was impossible.

---

## Course map

Read in order the first time. Later, use as reference.

| # | File | What you get |
|---|------|--------------|
| 01 | [Data foundations & sessions](01_data_foundations.md) | Timestamps, timezones, sessions, rolls, the data-quality gate that must run before any feature is interpreted |
| 02 | [Indicators, causally and correctly](02_indicators.md) | ATR, VWAP, EMA/SMA, RSI, ADX, realized vol, Hurst, efficiency ratio, rolling z-scores — with the causality trap in each |
| 03 | [Vectorisation & performance](03_vectorisation.md) | The vectorise-what-you-can / compile-what-you-can't pattern; `groupby`, `pivot_table`, numba kernels, bit-exact parity testing |
| 04 | [Exploratory analysis: momentum vs mean reversion](04_exploratory_analysis.md) | Variance ratios, autocorrelation, IC, conditional expectancy, dose-response, event studies — and how to explore without burning your sample |
| 05 | [Writing the simulation engine](05_engine_design.md) | State machine, entry/exit mechanics, brackets, partials, trailing stops, costs, fills, the daily flat |
| 06 | [Lookahead, leakage & fill traps](06_lookahead_and_traps.md) | The full taxonomy, with the real postmortems and the assertions that catch each |
| 07 | [Performance metrics](07_performance_metrics.md) | CAGR, Sharpe, Sortino, Calmar, hit ratio, expectancy, R multiples, gross/net R, profit factor, turnover, capacity — formulas and code |
| 08 | [Statistical properties of returns](08_return_statistics.md) | Moments, fat tails, autocorrelation, heteroskedasticity, stationarity, why √T annualisation lies |
| 09 | [Statistical evaluation & inference](09_statistical_evaluation.md) | Clustered t-stats, HAC, block bootstrap, Lo's Sharpe SE, Ledoit–Wolf paired test, DSR, PBO/CSCV, multiple-testing haircuts |
| 10 | [Null models & negative controls](10_nulls_and_controls.md) | Return-shuffle Null C, re-pairing nulls, matched-count nulls, and how to *validate a null* before trusting it |
| 11 | [Testing a strategy variation](11_variation_testing.md) | The full decision protocol for "is this variant better, or is it noise?" |
| 12 | [Institutional protocol](12_institutional_protocol.md) | Stage gates, hypothesis preregistration, run ledger, immutable artifacts, builder/reviewer separation, deployment gates, shadow trading |
| 13 | [Worked example: engine from zero](13_worked_example.md) | ~350 lines, complete: data → features → engine → metrics → nulls → verdict |
| 14 | [Reference card](14_reference_card.md) | Every formula, threshold, and checklist on one page |

---

## Project layout you should copy

This workspace's standard skeleton (`templates/backtesting_project/`) exists
because the boundaries stop specific mistakes:

```
project/
  paper/                  # source spec + testable claims register
  baseline_replication/   # paper-faithful config, frozen. NEVER improved.
  backtest_engine/        # reusable execution/accounting/metrics + audit tests
  strategy/               # features, signals, filters, sizing
  experiments/
      IDEA_BACKLOG.md     # brainstorming (not findings)
      hypotheses/         # HYP-XXXX.md — preregistered, one per material test
      ledger.csv          # append-only run audit trail
  validation/             # nulls, negative controls, holdout plans
  artifacts/runs/EXP-XXXX # immutable outputs, one dir per material run
  reports/                # BASELINE, ENGINE_AUDIT, FINDINGS, FINAL_REVIEW
  MEMORY.md               # concise current state + handoff
```

Why each boundary matters:

- **`baseline_replication/` frozen** — otherwise your "baseline" drifts upward
  with every improvement you make and you can no longer measure a delta.
- **`backtest_engine/` separate from `strategy/`** — experiment scripts must
  *call* the audited engine, never reimplement fills, costs, P&L, or metrics.
  Every reimplementation is a new place for an artifact to hide.
- **`artifacts/runs/` immutable** — a result you cannot point at is not
  evidence.
- **`experiments/hypotheses/` written BEFORE the run** — see
  [12_institutional_protocol.md](12_institutional_protocol.md). This is the
  single highest-value habit in the whole course.

---

## Minimum stack

```
python >= 3.11
numpy, pandas, pyarrow      # data + vectorised compute
numba                        # compiled sequential kernels
scipy                        # distributions, tests
matplotlib                   # diagnostics only, never the evidence
pytest                       # engine invariant tests — mandatory, not optional
```

Store bars as **parquet**, not CSV. A 16-year 1-minute futures archive is ~50 M
rows; parquet + pyarrow reads it in seconds, CSV takes minutes and loses dtypes.

---

## How to use this course

1. Read 01–03, then build a data loader and an indicator module for one
   instrument. Run the data-quality gate. **Do not skip it.**
2. Read 05–06, then write the engine. Write its invariant tests the same day.
3. Read 04, then explore — but write down your hypothesis before you look.
4. Read 07–11 before you believe any result.
5. Read 12 and adopt the ledger + hypothesis files from day one. Retrofitting
   them is miserable.

---

## The five rules that would have saved the most time here

1. **Assert fill feasibility in code**, on every trade, before looking at any
   statistic. (Killed: a Sharpe 2.07 result.)
2. **Bar-close information cannot trade earlier in the same bar.** Next-bar
   open is the default. (Killed: most of a Sharpe 1.8 result.)
3. **Run a claim-matched null through the *complete* pipeline** on every edge
   candidate. Not on the trade list — on the pipeline. (Killed: at least eight
   "improvements" in this workspace.)
4. **Gate the expensive null on the primary metric.** If the real run doesn't
   clear the gate, it's already a REJECT; don't spend the null.
5. **A NO-GO is a successful outcome.** Write it up with the same care as a GO.
   Most of the durable knowledge in this workspace is in the rejections.

---

Sources for the institutional-statistics material in lesson 09:
- [Bailey & López de Prado — The Deflated Sharpe Ratio (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- [Bailey, Borwein, López de Prado, Zhu — The Probability of Backtest Overfitting](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting)
- [Deflated Sharpe Ratio (davidhbailey.com PDF)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Portfolio Optimization Book — 8.3 The Dangers of Backtesting](https://portfoliooptimizationbook.com/book/8.3-dangers-backtesting.html)
