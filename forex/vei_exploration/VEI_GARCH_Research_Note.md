# Incorporating VEI into GARCH

## Objective

This note describes how to incorporate a Volatility Expansion Index (VEI) into a GARCH model for 5-minute data. Here, VEI is defined as the ratio of a short ATR to a long ATR:

$$
VEI_t = \frac{ATR_{short,t}}{ATR_{long,t}}
$$

The indicator measures volatility acceleration relative to a slower volatility baseline:

- $VEI_t>1$: recent volatility is above its longer-term baseline.
- $VEI_t<1$: recent volatility is below its longer-term baseline.
- Rising VEI: volatility acceleration is strengthening.
- Falling VEI: volatility acceleration is fading.

The central research question is whether VEI improves genuinely forward volatility forecasts after controlling for volatility persistence, the underlying volatility level, intraday seasonality, and the bar that triggered the VEI move.

## 1. Begin with a GARCH-X model

A standard GARCH(1,1) model is:

$$
r_t=\mu_t+\epsilon_t, \qquad \epsilon_t=\sigma_tz_t
$$

$$
\sigma_t^2=\omega+\alpha\epsilon_{t-1}^2+\beta\sigma_{t-1}^2
$$

VEI can enter as an exogenous variance predictor:

$$
\sigma_t^2=
\omega+
\alpha\epsilon_{t-1}^2+
\beta\sigma_{t-1}^2+
\gamma f(VEI_{t-1})
$$

A useful transformation is:

$$
x_t=\log(VEI_t)
$$

The log transformation maps the neutral value $VEI=1$ to zero and treats acceleration and deceleration more symmetrically.

Because $\log(VEI)$ can be negative, a log-variance specification is preferable to adding it directly to a conventional variance equation:

$$
\log(\sigma_t^2)=
\omega+
\beta\log(\sigma_{t-1}^2)+
\alpha g(z_{t-1})+
\gamma\log(VEI_{t-1})
$$

Interpretation:

- $\gamma>0$: volatility acceleration predicts higher subsequent variance.
- $\gamma=0$: VEI adds no information beyond existing GARCH dynamics.
- $\gamma<0$: extreme volatility acceleration tends to mean-revert.

Always use lagged VEI to forecast the next bar. Contemporaneous $VEI_t$ contains the current bar's high, low, and close and would leak current-bar information into a forecast for that same bar.

## 2. Separate acceleration from the volatility level

The same VEI value can occur in two very different environments:

1. A volatility shock emerging from a quiet long-term baseline.
2. Another large bar during an already-high-volatility regime.

Include both VEI and the underlying volatility level:

$$
LongVol_t=\frac{ATR_{long,t}}{Price_t}
$$

Then estimate:

$$
\log(\sigma_t^2)=
\omega+
\beta\log(\sigma_{t-1}^2)+
\alpha g(z_{t-1})+
\gamma_1\log(VEI_{t-1})+
\gamma_2\log(LongVol_{t-1})
$$

This separates:

- $\gamma_1$: the effect of volatility acceleration.
- $\gamma_2$: the effect of the underlying volatility regime.

Also consider the change in VEI:

$$
\Delta x_t=\log(VEI_t)-\log(VEI_{t-1})
$$

The augmented model becomes:

$$
\log(\sigma_t^2)=
\cdots+
\gamma_1x_{t-1}+
\gamma_2\Delta x_{t-1}+
\gamma_3\log(LongVol_{t-1})
$$

This distinguishes high-but-falling VEI from high-and-rising VEI.

## 3. Model asymmetric VEI effects

The relationship between VEI and future variance is unlikely to be linear. Moderate acceleration may signal continued expansion, while an extreme reading may indicate exhaustion.

### Piecewise acceleration and contraction

Define:

$$
x_t^+=\max(\log(VEI_t),0)
$$

$$
x_t^-=\min(\log(VEI_t),0)
$$

Then estimate:

$$
\log(\sigma_t^2)=
\cdots+
\gamma_+x_{t-1}^++
\gamma_-x_{t-1}^-
$$

This allows volatility acceleration and contraction to affect the forecast differently.

### Threshold states

Define states such as:

| VEI state | Definition |
|---|---|
| Contraction | $VEI<1$ |
| Ordinary acceleration | $1\le VEI<q_{80}$ |
| Extreme acceleration | $VEI\ge q_{80}$ |

Estimate the percentile threshold from training data only. State indicators can then enter the log-variance equation to test whether extreme expansion behaves differently from ordinary acceleration.

### Nonlinear terms

A simpler alternative to a full regime model is to include:

$$
x_{t-1}, \qquad x_{t-1}^2, \qquad \Delta x_{t-1}
$$

A negative coefficient on $x^2$ alongside a positive coefficient on $x$ could indicate that moderate VEI predicts persistence while very high VEI predicts diminishing incremental expansion.

## 4. Use VEI as a regime variable

VEI may be more valuable as a state variable than as a linear regressor. A threshold specification is:

$$
\sigma_t^2=
\begin{cases}
\omega_L+\alpha_L\epsilon_{t-1}^2+\beta_L\sigma_{t-1}^2,
& VEI_{t-1}<c\\
\omega_H+\alpha_H\epsilon_{t-1}^2+\beta_H\sigma_{t-1}^2,
& VEI_{t-1}\ge c
\end{cases}
$$

This permits contraction and expansion regimes to have different:

- Shock sensitivity, $\alpha$
- Volatility persistence, $\beta$
- Long-run variance
- Innovation distributions

Choose or estimate the threshold using the training sample only.

## 5. Consider smooth-transition GARCH

Instead of an abrupt threshold, VEI can smoothly alter the GARCH parameters:

$$
\sigma_t^2=
\omega+
\alpha(VEI_{t-1})\epsilon_{t-1}^2+
\beta(VEI_{t-1})\sigma_{t-1}^2
$$

For example:

$$
\alpha(VEI)=\alpha_0+\alpha_1S(VEI)
$$

$$
\beta(VEI)=\beta_0+\beta_1S(VEI)
$$

where $S(VEI)$ is a logistic transition function. This tests whether volatility shocks receive different weights and have different persistence as VEI moves from contraction to acceleration.

Because this model is more difficult to estimate and validate, test it only after simpler GARCH-X specifications demonstrate stable incremental value.

## 6. Control for duplicated information

VEI and GARCH both use recent volatility information:

- GARCH uses squared close-to-close return shocks.
- ATR uses high, low, and previous-close information.
- Short and long ATRs share many of the same true-range observations.

VEI may therefore duplicate information already captured by $\epsilon_{t-1}^2$ and $\sigma_{t-1}^2$. Its potential advantage is that true range contains intrabar information not present in close-to-close returns.

Compare models sequentially:

1. GARCH(1,1)
2. GARCH-X with normalised long ATR
3. GARCH-X with normalised long ATR and VEI level
4. GARCH-X with VEI level and VEI change
5. GARCH-X with asymmetric or nonlinear VEI terms
6. Threshold or smooth-transition VEI-GARCH

The improvement from model 2 to model 3 is the cleanest initial test of whether acceleration contributes beyond the underlying volatility level.

## 7. Control for the triggering bar

A large bar mechanically:

1. Raises the short ATR quickly.
2. Raises the long ATR more slowly.
3. Produces a higher VEI.
4. May also precede high volatility simply because volatility clusters.

Include controls such as:

$$
TRShock_t=\frac{TR_t}{ATR_{long,t}}
$$

and the current absolute return. A more rigorous variance specification is:

$$
\log(\sigma_t^2)=
\cdots+
\gamma_1\log(VEI_{t-1})+
\gamma_2\Delta\log(VEI_{t-1})+
\gamma_3\log(LongVol_{t-1})+
\gamma_4TRShock_{t-1}
$$

VEI is more convincing if it remains useful after controlling for the bar that generated the acceleration reading.

## 8. Adjust 5-minute data for intraday seasonality

Five-minute volatility follows a strong time-of-day pattern. Without adjustment, both VEI and GARCH may primarily learn structural volatility around the market open, scheduled data releases, or the close.

Estimate the historical volatility scale for each 5-minute time bucket using training data:

$$
s_{\tau(t)}=HistoricalVolatilityScale(TimeOfDay=\tau(t))
$$

Deseasonalise returns:

$$
r_t^{adjusted}=\frac{r_t^{raw}}{s_{\tau(t)}}
$$

Fit the model to the adjusted returns and restore the scale afterward:

$$
\widehat{\sigma}_{raw,t}^2=
\widehat{\sigma}_{adjusted,t}^2s_{\tau(t)}^2
$$

Alternatively, add time-of-day variables directly to a log-variance equation. All seasonal estimates must be calculated from past or training data only.

## 9. Recommended initial specification

Begin with an EGARCH-X model using Student-$t$ innovations:

$$
\log(\sigma_t^2)=
\omega+
\beta\log(\sigma_{t-1}^2)+
\alpha\left(|z_{t-1}|-E|z|\right)+
\theta z_{t-1}+
\gamma_1\log(VEI_{t-1})+
\gamma_2\Delta\log(VEI_{t-1})+
\gamma_3\log(LongVol_{t-1})+
\gamma_4TRShock_{t-1}
$$

Reasons for this starting point:

- Log variance guarantees positive forecasts.
- EGARCH handles asymmetric positive and negative return shocks.
- Student-$t$ innovations accommodate fat-tailed 5-minute returns.
- VEI can enter without requiring its coefficient to be nonnegative.
- The model distinguishes VEI level, VEI acceleration, baseline volatility, and the triggering-bar shock.

For markets in which positive and negative shocks do not have a stable asymmetric effect, compare EGARCH-X against a simpler symmetric log-GARCH-X model.

## 10. Forecast horizons

Evaluate several horizons:

- One bar: 5 minutes
- Three bars: 15 minutes
- Six bars: 30 minutes
- Twelve bars: 60 minutes

VEI may add the most information over short horizons and lose incremental value as the forecast horizon increases.

For multi-step forecasts, define in advance whether the model will:

- Recursively forecast each future conditional variance, or
- Predict aggregate realized variance over the entire horizon

Keep the forecasting method consistent across all benchmark models.

## 11. Validation design

Use chronological walk-forward evaluation rather than random train/test splits.

A practical design is:

- Train on two to three years
- Validate on the next three to six months
- Test on the following three to six months
- Roll forward and repeat

Apply:

- Purging around split boundaries equal to the longest target horizon
- Training-only feature normalisation and percentile thresholds
- Day- or week-level block bootstrap confidence intervals
- An untouched final test period
- Consistent refitting schedules across competing models

Monitor parameter constraints and convergence. A model should not be accepted merely because the optimiser returned a result.

## 12. Evaluation metrics

### QLIKE loss

QLIKE is particularly suitable for variance forecasts:

$$
QLIKE_t=
\frac{RV_t}{\widehat{\sigma}_t^2}+
\log(\widehat{\sigma}_t^2)
$$

Lower values indicate better forecasts.

### Additional forecast metrics

- Out-of-sample log-likelihood
- MAE against future realized variance
- MSE against future realized variance
- Rank correlation with realized volatility
- Calibration across forecast-volatility quantiles
- VaR exceedance frequency and clustering
- Diebold-Mariano comparisons of forecast loss

### Stability checks

- VEI coefficient sign and magnitude by walk-forward window
- Performance by year
- Performance by trading session and time of day
- Performance by underlying long-volatility regime
- Performance after extreme versus moderate VEI readings

Statistical significance without stable out-of-sample forecast improvement is insufficient.

## 13. Recommended research sequence

1. Clean and align 5-minute OHLC data.
2. Calculate returns, true range, short ATR, long ATR, and VEI.
3. Deseasonalise returns using training-only time-of-day estimates.
4. Fit Student-$t$ GARCH and EGARCH baseline models.
5. Add normalised long ATR to control for the volatility level.
6. Add lagged $\log(VEI)$.
7. Add $\Delta\log(VEI)$ and the current true-range shock.
8. Test separate expansion and contraction terms.
9. Test nonlinear VEI effects or training-derived VEI states.
10. Attempt threshold or smooth-transition GARCH only if simpler models succeed.
11. Compare all models with identical walk-forward windows and loss functions.
12. Confirm the selected model on a final untouched period.

## 14. Interpretation framework

The key test is not whether VEI has a statistically significant in-sample coefficient. It is whether VEI provides stable, incremental, out-of-sample information beyond:

- GARCH volatility persistence
- Recent squared return shocks
- The normalised long ATR
- The current true-range shock
- Intraday seasonality

Possible findings include:

- **Positive and stable VEI effect:** acceleration persists and improves subsequent variance forecasts.
- **Only VEI change matters:** the direction of acceleration is more informative than its level.
- **Nonlinear effect:** moderate acceleration persists, while extreme acceleration predicts exhaustion.
- **Regime effect:** VEI changes GARCH shock sensitivity or persistence rather than directly shifting variance.
- **No incremental effect:** VEI is a useful descriptive indicator but mostly repackages information already captured by GARCH and current true range.

The simplest specification that delivers stable walk-forward improvement should be preferred over a more complex regime model.
