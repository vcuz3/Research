# RSI joint current/expected volatility regime

> **SUPERSEDED INTERPRETATION — 2026-08-04.** The measurements below remain
> reproducible, but the expected-forward-RV “surprise” parameterization is not
> materially distinct from the canonical same-slot RV(30) percentile for the
> report's within-slot rank estimand (pooled within-slot rho about 0.968-0.977;
> frozen top-bin recall about 0.83-0.86). Carry `rv_30m_pct_90d`, not the ratio,
> as the canonical slow volatility-level regime. The no-RSI audit shows a
> generic short-horizon-reversion channel, but does not eliminate incremental
> RSI conditioning: a post-audit rank regression controlling for trailing 1m
> and 30m return interactions retains a negative RSI x regime coefficient in
> all four pairs (clustered t -2.75 to -5.74). See
> `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md` and project `MEMORY.md`.

## Verdict

**Superseded decision:** the original recommendation was to use both variables
through a continuous volatility-surprise ratio rather than a hard 3x3 corner
filter:

`volatility_surprise = log(past_30m_RV / prior_same_slot_median_forward_30m_RV)`

The 90-session version is the preferred smoother default. Its top surprise
quintile has stronger RSI IC than its bottom quintile in 7/8 pair-era cells,
positive gross-P&L separation in 8/8, positive expected-volatility-normalized
separation in 8/8, and a strengthening continuous RSI interaction in 8/8. The
30-session sensitivity agrees or is slightly stronger on IC.

This is a modest refinement over current RV percentile alone, not a new
independent edge. The joint hypothesis was formed after inspecting both marginal
effects, all history through 2023 is consumed, and 2024+ remains sealed.

## Frozen setup

- Pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD.
- Data: one-minute midpoint OHLC, 2012-2023; New York 17:00 session boundary.
- Decision: completed NY half-hour at :29/:59; entry next exact one-minute open;
  exit at the open exactly 30 minutes later.
- Pair-specific 2012-2020 cutpoints applied unchanged to 2021-2023.
- Current RV: past 30-minute realized volatility, causally ranked within the
  same NY slot over 30 or 90 prior sessions.
- Expected RV: causal median of next-30-minute realized volatility from prior
  observations of the same NY slot.
- IC: within-slot Spearman correlation of raw RSI(14) with the signed forward
  return; more-negative means stronger mean reversion.
- P&L: long RSI <= 30, short RSI >= 70; midpoint gross plus hypothetical 0.5-
  and 1.0-pip cost stresses.

Data-quality counts match the broad sweep: 149,129-149,133 decision rows per
pair, 95.8%-95.9% exact-target coverage, no duplicates or out-of-order rows.
Systematic weekend/holiday gaps remain and rollover midpoint results are not an
execution claim.

## 1. The 3x3 matrix

The primary candidate was high current RV / low expected forward RV. The
adverse comparison was high current RV / high expected forward RV.

| Memory | Candidate stronger IC | Median IC-strength advantage | Candidate better gross P&L | Median gross-P&L difference | Median hit-rate advantage |
|---|---:|---:|---:|---:|---:|
| 30 sessions | 8/8 | +0.0259 | 0/8 | -0.574 pip | +1.15 pp |
| 90 sessions | 7/8 | +0.0312 | 0/8 | -0.572 pip | +3.70 pp |

The matrix confirms the joint predictive pattern: RSI is most rank-predictive
when current volatility is elevated and the coming slot is normally quiet. But
the hard corner is not a good fixed-threshold P&L filter. The high-expected-RV
corner has larger raw pip moves, so it earns more pips despite weaker IC and hit
rate. Expected-RV-normalized payoff favors the candidate in only 5/8 cells for
each memory, so scale does not fully explain the mismatch.

The continuous three-way `RSI × current RV × expected RV` coefficient is also
not stable: its sign splits evenly at 90 sessions (four positive, four negative),
and only one of eight coefficients has BH-adjusted q < 0.10. There is no evidence
for a special nonlinear corner effect beyond the two directional regime
components.

![Joint 90-session matrix](charts/rsi_joint_volatility_regime/joint_regime_90d_heatmaps.png)

![Candidate versus adverse](charts/rsi_joint_volatility_regime/candidate_vs_adverse_90d.png)

## 2. Continuous volatility surprise

The ratio handles the two effects more cleanly: high current RV raises the score
and high expected slot RV lowers it.

| Memory | Q5 stronger IC | Q5 better gross P&L | Q5 better normalized payoff | Median Q5-Q1 IC gain | Median Q5-Q1 gross gain | Negative RSI interaction | q < 0.10 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 30 sessions | 8/8 | 7/8 | 7/8 | +0.0332 | +0.681 pip | 8/8 | 6/8 |
| 90 sessions | 7/8 | 8/8 | 8/8 | +0.0310 | +0.759 pip | 8/8 | 6/8 |

For the preferred 90-session Q5, medians across eight pair-era cells are:

- 214 signals/year;
- RSI IC -0.0703;
- 1.217 gross pips/signal, 0.717 after a hypothetical 0.5-pip cost, and 0.217
  after a 1.0-pip arithmetic cost stress;
- 57.6% hit rate;
- 1.43 gross and 0.87 cost-stressed session Sharpe;
- -246 pips maximum drawdown;
- 1.16 MFE/MAE ratio;
- 0.223 expected-RV units per signal, with median session-clustered t = 2.80.

The continuous interaction is negative in 8/8 cells, with median beta -0.0628
and median absolute clustered t = 3.49. Six of eight coefficients have q < 0.10
within this follow-up family. These q-values do not correct the preceding broad
feature search, so they are stability diagnostics rather than confirmatory
significance.

![Volatility-surprise quintiles](charts/rsi_joint_volatility_regime/surprise_quintile_curves.png)

## 3. Incremental value versus current RV alone

Against the standalone top quintile of current RV percentile:

| Memory | Surprise has stronger Q5 IC | Median Q5 IC improvement | Hit-rate improvement | Median gross improvement | Frequency change |
|---|---:|---:|---:|---:|---:|
| 30 sessions | 8/8 | +0.0076 | +3.39 pp (8/8) | +0.078 pip | -14 signals/year |
| 90 sessions | 6/8 | +0.0028 | +2.99 pp (8/8) | +0.016 pip | -26 signals/year |

The expected-slot denominator improves selectivity and hit rate consistently,
but the median P&L increment is small and appears in only 5/8 cells. Therefore
the ratio is preferable as a parsimonious combined regime score, but it has not
shown a large economic improvement over current RV percentile by itself.

## Decision — superseded

1. ~~Carry `log(past_30m_RV / expected_slot_forward_RV)` with a 90-session causal
   expected-volatility memory as the primary combined regime feature.~~ Carry
   `rv_30m_pct_90d`; the ratio is a near-reparameterization at this estimand.
2. Keep current-RV percentile alone as the benchmark; do not discard it.
3. ~~Use the continuous score or its top quintile.~~ Use canonical RV(30)
   percentile bins for follow-up work. Do not deploy the hard
   high-current/low-expected tercile corner as a raw-pip filter.
4. Treat all results as consumed-history exploratory evidence. Validation needs
   the sealed 2024+ period or future shadow data, plus bid/ask execution and a
   prespecified cost model.

## Evidence

- Frozen specification: `RSI_JOINT_VOLATILITY_REGIME_SPEC.md`
- Reproduction: `_run_rsi_joint_volatility_regime.py`
- Full results: `rsi_joint_volatility_regime_results.json`
- Joint matrix: `rsi_joint_volatility_regime_matrix.csv`
- Pair/era summary: `rsi_joint_volatility_regime_summary.csv`
- Joint interactions: `rsi_joint_volatility_regime_interactions.csv`
- Surprise interactions: `rsi_joint_volatility_regime_surprise_interactions.csv`
