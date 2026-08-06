# RSI volatility-surprise x acceleration interaction

> **SUPERSEDED INTERPRETATION — 2026-08-04.** The reported surfaces and metrics
> remain valid, but “surprise x acceleration synergy” is withdrawn. In raw
> ratios the product collapses to RV(5)/expected RV(30), and for the within-slot
> rank estimand that collapsed feature is near-redundant with the canonical
> same-slot RV(5) percentile (pooled within-slot rho about 0.978-0.984). The
> stable high/high corner is therefore best interpreted as a short-horizon RV
> level effect, not confirmed nonlinear synergy. Carry `rv_5m_pct_90d` as the
> canonical fast regime. The no-RSI control establishes a generic reversal
> channel but does not eliminate incremental RSI conditioning after raw-return
> interactions are controlled. See `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md` and
> project `MEMORY.md`.

## Verdict

**Superseded attribution:** volatility surprise and fast RV acceleration appeared
complementary and showed directionally stable, but statistically weak,
non-additive interaction. The
high-surprise/high-RV(5)/RV(30)-acceleration corner has the strongest RSI IC.
The two regime ranks are not redundant: their median within-slot Spearman
correlation is only -0.062.

The originally proposed parsimonious implementation was a single fast
volatility-surprise score:

`log(RV_5m / expected_forward_RV_30m)`

because, in raw ratios,

`(RV_30m / expected_forward_RV_30m) × (RV_5m / RV_30m)
 = RV_5m / expected_forward_RV_30m`.

Do not place all three raw ratios in one model: the fast surprise is the sum of
the log 30-minute surprise and log acceleration, so they are algebraically
dependent before percentile transforms.

## Frozen setup

- EURUSD, GBPUSD, AUDUSD, NZDUSD; one-minute midpoint OHLC, 2012-2023.
- New York 17:00 sessions and :29/:59 decisions; next-minute-open entry and
  exact 30-minute open exit.
- 2012-2020 pair-specific cutpoints applied unchanged to 2021-2023.
- Primary: 90-session `RV(30)/expected forward RV(30)` surprise crossed with
  same-slot percentile of RV(5)/RV(30).
- Sensitivities: 30-session memory and VEI ATR(10)/ATR(50), ATR(25)/ATR(100).
- 2024+ remains sealed.

## 1. Primary RV(5)/RV(30) interaction

### Conditional and non-additive tests

| Memory | Acceleration improves IC within high surprise | Median IC gain | Gross P&L improves | Median gross gain | Positive IC difference-in-differences | Strengthening three-way sign | q < 0.10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30 sessions | 8/8 | +0.0554 | 7/8 | +0.505 pip | 7/8 | 7/8 | 1/8 |
| 90 sessions | 8/8 | +0.0493 | 6/8 | +0.350 pip | 6/8 | 8/8 | 1/8 |

At 90 sessions, surprise also improves IC within the high-acceleration regime
in 8/8 cells, with median gain +0.0379. The high/high corner therefore beats
both one-feature extreme corners in every pair-era cell.

The discrete IC difference-in-differences is positive in 6/8 with median
+0.0203, meeting the frozen directional synergy rule. The continuous three-way
coefficient is strengthening in 8/8, with median beta -0.0681. However, median
absolute clustered t is only 1.47 and only AUDUSD-early has BH-adjusted q < 0.10.
This supports **provisional directional synergy**, not a precisely estimated
nonlinear coefficient.

![Primary interaction surface](charts/rsi_surprise_acceleration_interaction/primary_90d_interaction_heatmaps.png)

![Incremental value and difference-in-differences](charts/rsi_surprise_acceleration_interaction/primary_90d_incremental_and_synergy.png)

### High/high operating cell

Median metrics across eight pair-era cells:

- RSI IC: -0.1003;
- 1.053 gross and 0.553 pip after a hypothetical 0.5-pip cost;
- 56.8% hit rate;
- gross session Sharpe 1.38 and cost-stressed Sharpe 0.67;
- 197 signals/year;
- MFE/MAE 1.16;
- maximum drawdown -262 pips;
- expected-RV-normalized payoff 0.182.

This hard corner has strong predictive ranking, but it is not automatically the
best trading filter: tercile intersections discard observations and interact
with absolute return scale.

## 2. VEI sensitivity

| Acceleration, 90 sessions | Median dependence with surprise | Adds IC within high surprise | Adds gross P&L | Positive IC DiD | Strengthening three-way sign | q < 0.10 |
|---|---:|---:|---:|---:|---:|---:|
| RV(5)/RV(30) | -0.062 | 8/8 | 6/8 | 6/8 | 8/8 | 1/8 |
| VEI ATR(10)/ATR(50) | +0.320 | 8/8 | 3/8 | 5/8 | 5/8 | 0/8 |
| VEI ATR(25)/ATR(100) | +0.504 | 8/8 | 7/8 | 7/8 | 6/8 | 0/8 |

All acceleration measures add some conditional IC, but the interaction is not
generic. VEI(10/50) behaves mainly as an additive IC context and hurts median
gross P&L. VEI(25/100) has supportive corner signs but is much more correlated
with surprise and its three-way coefficient is small and imprecise. The cleanest
interaction belongs to fast RV(5)/RV(30).

## 3. Collapsed fast-surprise feature

The post-run algebraic identity motivated a direct diagnostic of
`log(RV(5)/expected forward RV(30))`.

| Memory | Q5 stronger IC | Q5 better gross P&L | Q5 better normalized payoff | Median Q5-Q1 IC gain | Median Q5-Q1 gross gain | Negative interaction | q < 0.10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30 sessions | 8/8 | 8/8 | 8/8 | +0.0619 | +0.702 pip | 8/8 | 8/8 |
| 90 sessions | 8/8 | 8/8 | 8/8 | +0.0616 | +0.725 pip | 8/8 | 8/8 |

The 90-session Q5 medians are:

- RSI IC -0.0958;
- 0.972 gross and 0.472 pip after a hypothetical 0.5-pip cost;
- 57.8% hit rate;
- 1.61 gross and 0.79 cost-stressed session Sharpe;
- 346 signals/year;
- MFE/MAE 1.15 and maximum drawdown -187 pips.

The continuous RSI interaction is negative in 8/8, all eight have q < 0.10
within this derived feature family, and median absolute clustered t is 5.07.
These p/q values remain post-selection diagnostics because the feature was
derived after inspecting the interaction.

Compared with the original 30-minute-surprise Q5, fast surprise has stronger IC
in 8/8 by a median +0.0219 and roughly 132 more signals/year, but 0.159 fewer
gross pips/signal and similar hit rate. Compared with RV(5)/RV(30) acceleration
Q5, it has stronger IC in 6/8, 0.187 more gross pips in 6/8, and a 3.75-point
higher hit rate in 8/8.

## Decision — superseded

1. ~~Carry `log(RV_5m / expected_forward_RV_30m)` as the primary predictive
   regime candidate.~~ Carry `rv_5m_pct_90d`; the ratio is near-redundant at the
   within-slot rank estimand.
2. ~~Retain `log(RV_30m / expected_forward_RV_30m)` as the slower payoff-scale
   regime.~~ Retain `rv_30m_pct_90d` as the canonical slower benchmark.
3. Do not stack surprise, RV(5)/RV(30), and fast surprise in one raw-feature
   model. Use two of the three at most, and prefer the collapsed feature when
   parsimony matters.
4. The nonlinear-synergy claim is superseded, not promoted: the sign is
   explained more parsimoniously by RV(5) level, coefficient-level inference is
   weak, and all pre-2024 history is consumed.

## Evidence

- Frozen specification: `RSI_SURPRISE_ACCELERATION_INTERACTION_SPEC.md`
- Reproduction: `_run_rsi_surprise_acceleration_interaction.py`
- Full results: `rsi_surprise_acceleration_interaction_results.json`
- Matrix: `rsi_surprise_acceleration_interaction_matrix.csv`
- Pair/era summaries: `rsi_surprise_acceleration_interaction_summary.csv`
- Three-way regressions: `rsi_surprise_acceleration_interaction_regressions.csv`
- Fast-surprise quintiles: `rsi_fast_volatility_surprise_quintiles.csv`
- Fast-surprise interactions: `rsi_fast_volatility_surprise_interactions.csv`
