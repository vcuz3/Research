# Full-range RSI regime test — result

## Verdict

High **recent volatility acceleration** strengthens the full-range directional
RSI association on the inspected pre-2024 panel. This is a robust descriptive
pattern, but not yet a symmetric or net-tradable RSI regime filter.

The result does not contradict the RSI-depth interaction NO-GO. This test uses
all scheduled 30-minute observations and asks whether raw RSI ranks future signed
returns more strongly in a regime. The prior notebook selected RSI 30/70 extremes
and asked whether additional threshold depth predicts side-adjusted payoff.

## Primary VEI result

VEI is ATR(10) / ATR(50), converted to a causal percentile using only prior
observations at the same session minute. High VEI therefore means short-term
volatility is elevated relative to its slower baseline; it does not mean the
absolute volatility level is high.

Early-period pair-specific quintile boundaries were applied unchanged to
2021-2023. The table reports within-session-slot Spearman IC. More-negative IC
means stronger RSI mean reversion.

| Pair | Era | VEI Q1 IC | VEI Q5 IC | Strength gain | Interaction t | Raw p | Screen q |
|---|---|---:|---:|---:|---:|---:|---:|
| AUDUSD | 2012-2020 | -0.0422 | -0.0865 | +0.0443 | -4.54 | <0.0001 | 0.0000 |
| AUDUSD | 2021-2023 | -0.0087 | -0.0363 | +0.0276 | -1.78 | 0.0749 | 0.2526 |
| EURUSD | 2012-2020 | -0.0289 | -0.0825 | +0.0536 | -4.44 | <0.0001 | 0.0000 |
| EURUSD | 2021-2023 | -0.0236 | -0.0661 | +0.0425 | -2.44 | 0.0147 | 0.0249 |
| GBPUSD | 2012-2020 | -0.0334 | -0.0841 | +0.0508 | -3.28 | 0.0010 | 0.0019 |
| GBPUSD | 2021-2023 | -0.0269 | -0.0702 | +0.0433 | -2.86 | 0.0043 | 0.0111 |
| NZDUSD | 2012-2020 | -0.0419 | -0.0851 | +0.0432 | -4.56 | <0.0001 | 0.0000 |
| NZDUSD | 2021-2023 | -0.0119 | -0.0592 | +0.0473 | -2.97 | 0.0030 | 0.0076 |

Q5 is stronger than Q1 and the clustered interaction has the strengthening sign
in all eight pair/era cells. Seven cells are individually significant before and
after the local secondary-screen correction; late AUDUSD has the same sign but
does not clear conventional significance. Quintile-strength monotonicity is high
in every cell (Spearman 0.7-1.0 across the five bins).

## Which regimes matter

### 1. Volatility acceleration — strongest and cleanest

- VEI percentile and VEI z-score: Q5 stronger in 8/8 cells; strengthening
  interaction in 8/8.
- RV(5)/RV(30): Q5 stronger in 8/8; interaction stronger in 8/8. Median Q5-Q1
  IC-strength gain is +0.0578.
- RV(15)/RV(60): Q5 stronger in 8/8; interaction stronger in 8/8. Median gain is
  +0.0375.
- A single large bar relative to ATR also has Q5 stronger in 8/8, but its
  interaction inference is much weaker and it should not be preferred to the
  smoother acceleration ratios.

This agreement identifies the useful state as **volatility expanding over the
last few minutes relative to the previous 30-60 minutes**.

### 2. High absolute volatility — not a reliable condition

Absolute RV(30), RV(60), range RV, accumulated session RV, prior-session RV, and
daily-volatility percentile do not show stable Q5-over-Q1 strengthening. For
accumulated session RV, Q5 is stronger in only 1/8 cells and the median Q5-Q1
change is negative. A negative continuous interaction can coexist with a weak
Q5 because the relationship is nonlinear and confounded by time of day; the
quintile result is the safer regime description.

Therefore “higher volatility makes RSI better” is too broad. The supported
version is “a recent volatility burst relative to its local baseline makes the
full-range RSI ranking stronger.”

### 3. Time of day — strongest after 16:00 UTC

Median within-slot RSI strength across the eight pair/era cells is:

| UTC block | Median absolute signed IC |
|---|---:|
| 16:00-24:00 | 0.0836 |
| 00:00-07:00 | 0.0578 |
| 12:00-16:00 | 0.0437 |
| 07:00-12:00 | 0.0351 |

The VEI interaction has the strengthening sign in all eight 16:00-24:00 cells
and in 30/32 pair/era/time-block cells overall, so it is not solely a clock
artifact. The apparent 16:30-17:30 New York rollover IC is extremely large, but
that hour is illiquid, the source has systematic rollover missingness, and the
data are untradeable midpoints without spreads. Treat rollover as a likely
microstructure/data artifact until bid/ask data validate it.

### 4. Direction — useful association, incomplete strategy filter

In VEI Q5, RSI 30/70 extreme-signal mean-reversion payoff is positive for both
directions in all 16 pair/era/direction cells. However, Q5 improves over Q1 in
only 10/16 cells: 6/8 overbought/short cells and 4/8 oversold/long cells. The
full-range rank interaction is therefore much more stable than the incremental
payoff of a fixed 30/70 trading rule, and the filter appears stronger on the
overbought/short side.

## Interpretation and limits

- Status: provisional, consumed-history stability evidence. The motivating
  EURUSD pattern and all pre-2024 panels had already been inspected.
- The four USD-quoted pairs are correlated, not independent replications.
- Results are gross midpoint labels. They do not include spreads, slippage,
  position overlap, or capital usage.
- VEI, RV ratios, and normalized bar range are related measures; agreement among
  them supports one volatility-acceleration family, not several independent
  discoveries.
- 2024 onward remained sealed. A candidate should freeze one simple acceleration
  definition and threshold, apply timing/cost stress, then use the holdout once.

## Evidence

- Frozen specification: `RSI_REGIME_TEST_SPEC.md`
- Reproduction script: `_run_rsi_regime_test.py`
- Full tables: `rsi_regime_test_results.json`
- Source feature panel: `forex_feature_ml_research.ipynb`

