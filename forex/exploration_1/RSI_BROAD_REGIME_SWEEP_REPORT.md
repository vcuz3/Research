# RSI broad regime sweep — report

## Executive result

The broad pre-2024 sweep supports three conclusions:

1. **RSI mean-reversion IC is strongest when volatility is accelerating, not
   merely when volatility is historically high.** All six ATR/RV acceleration
   constructions strengthen full-range RSI IC broadly across pairs and eras.
   The best balanced specification is the 90-session percentile of RV(5)/RV(30).
2. **A 90-session normalization memory is modestly preferable to 30 sessions,
   especially for P&L stability, but the IC difference is small and not universal.**
   The more important choice is the raw acceleration horizon: short/fast ratios
   generally beat 25/100 RV for IC, while the slower 25/100 ATR ratio gives the
   most uniform fixed-threshold P&L uplift.
3. **Directional/trending paths strengthen RSI ranking, especially at the
   four-hour horizon, but do not provide a reliable 30/70 P&L filter.** Path
   efficiency and variance ratio work better than return autocorrelation.

These are exploratory results on consumed 2012-2023 history. The 2024+ holdout
remained sealed.

## Data and estimands

- Four pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD.
- 149,129-149,133 New-York-clock decision rows per pair from 2012-2023.
- New York 17:00 session boundary; decisions at completed `:29`/`:59` bars.
- Entry at the exact next-minute open and exit 30 minutes later at the open.
- Full-range IC: within-New-York-slot Spearman correlation of RSI(14) with
  signed forward return. A larger negative magnitude means stronger mean
  reversion.
- P&L: fixed RSI 30/70 signal, gross midpoint pips. Session Sharpe sums all
  selected signals per session and inserts zero on no-trade sessions.
- Early 2012-2020 quintile cutpoints are reused unchanged in 2021-2023.
- Interaction standard errors are clustered by New York session; q-values use
  Benjamini-Hochberg correction within each pair/era's 27-variant screen.

Target coverage is 95.8%-95.9%. Inputs have no duplicate/out-of-order timestamps
or invalid OHLC rows. Weekend/holiday gaps are excluded by exact-window checks.

## 1. Volatility acceleration

### Cross-specification comparison

The table aggregates eight cells: four pairs x early/late eras. `IC gain` is the
median increase in absolute signed IC from regime Q1 to Q5. `P&L + cells` counts
where fixed RSI 30/70 gross pips improve in Q5.

| Regime percentile | Memory | IC Q5 stronger | Interaction stronger | Median IC gain | P&L + cells | Median P&L uplift |
|---|---:|---:|---:|---:|---:|---:|
| VEI ATR(25)/ATR(100) | 90 | 8/8 | 8/8 | +0.0402 | 8/8 | +0.469 pip |
| VEI ATR(25)/ATR(100) | 30 | 8/8 | 8/8 | +0.0386 | 8/8 | +0.416 pip |
| VEI ATR(10)/ATR(50) | 90 | 8/8 | 8/8 | +0.0475 | 6/8 | +0.328 pip |
| VEI ATR(10)/ATR(50) | 30 | 8/8 | 8/8 | +0.0476 | 5/8 | +0.132 pip |
| VEI ATR(5)/ATR(25) | 90 | 8/8 | 8/8 | +0.0496 | 6/8 | +0.198 pip |
| VEI ATR(5)/ATR(25) | 30 | 8/8 | 8/8 | +0.0468 | 5/8 | +0.160 pip |
| RV(5)/RV(30) | 90 | 8/8 | 8/8 | **+0.0500** | **8/8** | +0.338 pip |
| RV(5)/RV(30) | 30 | 8/8 | 8/8 | +0.0448 | 8/8 | +0.242 pip |
| RV(10)/RV(50) | 90 | 8/8 | 8/8 | +0.0414 | 4/8 | +0.017 pip |
| RV(10)/RV(50) | 30 | 8/8 | 8/8 | +0.0350 | 4/8 | +0.009 pip |
| RV(25)/RV(100) | 90 | 8/8 | 7/8 | +0.0181 | 6/8 | +0.308 pip |
| RV(25)/RV(100) | 30 | 8/8 | 8/8 | +0.0289 | 5/8 | +0.177 pip |

### What this says about memory

- **Normalization history:** 90 sessions has higher IC separation in 6/9 paired
  comparisons and higher median P&L uplift in 8/9. The differences are generally
  small; 90 days is a smoother default, not a discovered sharp optimum.
- **Raw acceleration horizon:** fast ratios are better for ranking. RV(5)/RV(30)
  dominates the longer RV ratios on IC and P&L agreement. VEI(5/25) and VEI(10/50)
  produce the largest IC separation, while slower VEI(25/100) gives the most
  uniform P&L uplift and the strongest median interaction t-statistic.
- The variants are highly correlated. This is one acceleration family, not 12
  independent confirmations.

### Economic diagnostics for 90-session candidates

Values below are medians across the eight pair/era cells.

| Q5 regime | Signals/year | Gross pips/signal | Net after 0.5 pip | Hit rate | Gross session Sharpe | Net session Sharpe | MFE/MAE |
|---|---:|---:|---:|---:|---:|---:|---:|
| VEI 25/100 | 263 | 0.715 | 0.215 | 53.9% | 1.12 | 0.31 | 1.06 |
| VEI 10/50 | 394 | 0.713 | 0.213 | 54.1% | 1.39 | 0.42 | 1.07 |
| VEI 5/25 | 470 | 0.785 | 0.285 | 54.4% | 1.75 | 0.71 | 1.12 |
| RV 5/30 | 434 | **0.854** | **0.354** | 54.2% | 1.74 | **0.73** | 1.11 |

The 0.5-pip stress leaves positive median Q5 expectancy, but net Sharpe is much
smaller than gross and median drawdowns remain roughly 176-267 pips. These are
midpoint labels, not executable returns.

![IC robustness heatmap](charts/rsi_broad_regime_sweep/ic_robustness_heatmap.png)

![Memory comparison](charts/rsi_broad_regime_sweep/memory_30_vs_90.png)

## 2. Volatility ranking and forecastable volatility

### Current RV ranked against its own New York slot

RV(30) percentile and z-score give essentially the same result. The 30- versus
90-session memory choice is also negligible for IC.

| Variant | Q5 stronger | Interaction stronger | Median IC gain | P&L + cells | Median P&L uplift |
|---|---:|---:|---:|---:|---:|
| RV percentile, 30 sessions | 7/8 | 8/8 | +0.0354 | 8/8 | +0.605 pip |
| RV percentile, 90 sessions | 7/8 | 8/8 | +0.0349 | 8/8 | +0.651 pip |
| RV z-score, 30 sessions | 7/8 | 8/8 | +0.0328 | 8/8 | +0.847 pip |
| RV z-score, 90 sessions | 7/8 | 8/8 | +0.0330 | 8/8 | +0.698 pip |

For 90-session RV percentile Q5, median fixed-threshold performance is 1.184
gross pips/signal, 0.684 after a hypothetical 0.5-pip cost, 54.5% hit rate, and
0.79 net session Sharpe. One cell—late GBPUSD—has weaker Q5 IC, so this family is
slightly less rank-stable than acceleration.

### Prior same-slot median forward RV

This test gives a strong **inverse regime relationship**, rather than no regime
information. The high predicted-forward-volatility quintile has weaker absolute
RSI IC in **8/8 cells**. With a 90-session median, median RSI IC changes from
-0.094 in Q1 to -0.039 in Q5, median IC strength falls by 0.059, and the median
quintile-versus-IC-strength monotonic correlation is -0.90. Therefore **low**
expected same-slot forward volatility is the favorable IC regime; the forecast
can be used as an inverse RSI-strength filter or conditioning variable.

That IC result must be separated from fixed-threshold P&L. Q1 median hit rate and
gross session Sharpe are 57.1% and 1.75 versus 54.6% and 0.82 in Q5, but median
gross pips per fixed-threshold signal are 0.536 in Q1 versus 0.690 in Q5. The
latter can rise despite weaker rank IC because return scale changes with
volatility and the fixed RSI threshold samples different parts of the
distribution.

The correct distinction is therefore: unusually elevated **current** volatility
strengthens RSI, while higher **expected clock-slot** volatility weakens RSI's
cross-sectional/rank predictiveness. Both variables contain regime information,
but their useful directions are opposite.

![Quintile IC curves](charts/rsi_broad_regime_sweep/ic_quintile_curves.png)

## 3. Trend versus chop

### Detection-method comparison

| Detector | Horizon | Q5 stronger | Interaction stronger | P&L + cells | Median IC gain | Median P&L uplift |
|---|---:|---:|---:|---:|---:|---:|
| Path efficiency | 15m | 8/8 | 5/8 | 5/8 | +0.0507 | +0.892 pip |
| Path efficiency | 60m | 7/8 | 7/8 | 2/8 | +0.0411 | -0.152 pip |
| Path efficiency | 240m | **8/8** | **8/8** | 5/8 | +0.0339 | +0.094 pip |
| Variance ratio | 15m | 8/8 | 5/8 | 4/8 | +0.0475 | +0.253 pip |
| Variance ratio | 60m | 7/8 | 7/8 | 2/8 | +0.0380 | -0.189 pip |
| Variance ratio | 240m | **8/8** | **8/8** | 4/8 | +0.0352 | -0.028 pip |
| Return autocorrelation | 15m | 7/8 | 6/8 | 3/8 | +0.0127 | -0.050 pip |
| Return autocorrelation | 60m | 6/8 | 5/8 | 2/8 | +0.0122 | -0.220 pip |
| Return autocorrelation | 240m | 6/8 | 5/8 | 6/8 | +0.0171 | +0.198 pip |

Interpretation:

- High path efficiency/variance ratio means the preceding path was directional,
  not choppy. RSI ranks subsequent returns more strongly after such paths.
- The **240-minute detector is the cleanest statistical interaction**: both path
  efficiency and variance ratio agree in all eight cells. The 15-minute Q5-Q1
  IC contrast is larger but its regression interaction and P&L are unstable and
  partly mechanical because the detector overlaps the RSI formation window.
- Return autocorrelation is a poor regime classifier here.
- None of the trend detectors gives robust fixed-30/70 P&L uplift. Treat the
  trend result as context for full-range ranking, not a deployable filter.

![PnL uplift heatmap](charts/rsi_broad_regime_sweep/pnl_uplift_heatmap.png)

## 4. New York time

Median RSI IC is largest around the New York 16:00-18:00 period. VEI(10/50) Q5
is stronger than Q1 in 22 of 24 New York hours; the two exceptions are 09:00 and
23:00. The Q5-Q1 IC-strength gain is particularly large at 17:00-18:00 and
21:00-22:00.

The 16:30-17:30 rollover region is not actionable evidence: the files have
systematic rollover gaps, trading is thin, and midpoint OHLC omit the spread
widening that is likely largest there.

![New York hourly IC](charts/rsi_broad_regime_sweep/new_york_hourly_ic.png)

## Overall ranking and decision

1. **Best balanced acceleration candidate:** RV(5)/RV(30), 90-session same-slot
   percentile. It has 8/8 IC, interaction, and P&L agreement, the largest median
   IC gain (+0.050), and positive median cost-stressed P&L.
2. **Best slower sibling/control:** VEI ATR(25)/ATR(100), 90-session percentile.
   It has lower IC separation (+0.040) but the strongest median interaction t and
   8/8 P&L uplift.
3. **Best volatility-level candidate:** RV(30) same-slot percentile, 90 sessions.
   It has the largest fixed-threshold P&L uplift, but only 7/8 IC agreement and is
   more exposed to volatility-scale/cost mechanics.
4. **Trend context only:** 240-minute path efficiency. It is statistically stable
   for full-range IC but not for fixed-threshold P&L.

No candidate is approved for deployment. Before opening 2024+, freeze one primary
acceleration definition, run delayed-entry and realistic bid/ask cost stress, and
predeclare the holdout metric and kill threshold.

## Evidence

- Specification: `RSI_BROAD_REGIME_SWEEP_SPEC.md`
- Reproduction: `_run_rsi_broad_regime_sweep.py`
- Full JSON tables: `rsi_broad_regime_sweep_results.json`
- Compact stability table: `rsi_broad_regime_sweep_stability.csv`
- Pair/era summaries: `rsi_broad_regime_sweep_summaries.csv`
