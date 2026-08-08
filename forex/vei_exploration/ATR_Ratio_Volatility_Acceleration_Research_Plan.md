# ATR Ratio Volatility Acceleration: 5-Minute Research Plan

## Research objective

Investigate the statistical properties and predictive value of a short-to-long ATR ratio on 5-minute charts:

$$
R_t = \frac{ATR_{\text{short},t}}{ATR_{\text{long},t}}
$$

The ratio measures volatility acceleration relative to a slower volatility baseline:

- $R_t > 1$: recent volatility is above its longer-term baseline.
- $R_t < 1$: recent volatility is below its longer-term baseline.
- Rising $R_t$: volatility acceleration is strengthening.
- Falling $R_t$: volatility acceleration is fading.

The main question is not simply whether the ratio predicts high volatility. It is whether it predicts a subsequent change in volatility, breakout behaviour, trend continuation, or exhaustion beyond what is already known from current volatility and the triggering price bar.

## 1. Construct the signal

Begin with a representative specification such as:

$$
R_t = \frac{ATR_5(t)}{ATR_{60}(t)}
$$

Calculate several related features:

### Ratio level

$$
R_t = \frac{ATR_{s,t}}{ATR_{l,t}}
$$

### Log ratio

$$
X_t = \log(R_t)
$$

The log transformation centres the neutral point at zero and makes acceleration and deceleration more symmetric.

### One-bar change

$$
\Delta X_t = X_t-X_{t-1}
$$

### Multi-bar slope

$$
Slope_{t,k} = \frac{X_t-X_{t-k}}{k}
$$

### Threshold crossings

Record fresh crossings of:

- $R_t=1$
- Rolling 80th and 90th percentiles
- Rolling 20th and 10th percentiles

Use thresholds calculated from historical data available at time $t$ only.

### Initial parameter grid

Use a deliberately small grid:

- Short ATR: 3, 5, 10, and 14 bars
- Long ATR: 30, 60, and 120 bars
- Require the long window to be at least four to six times the short window
- Compare Wilder ATR with a rolling mean of true range

Avoid selecting a final parameter pair from a large grid without strong out-of-sample validation.

## 2. Examine statistical properties

For each candidate ratio, measure:

- Mean, median, standard deviation, skewness, and kurtosis
- Quantiles and tail behaviour
- Percentage of observations above and below 1
- Autocorrelation of $R_t$, $\log(R_t)$, and $\Delta\log(R_t)$
- Average duration above and below 1
- Frequency and spacing of threshold-crossing events
- Distribution by time of day and trading session
- Stability by year and market regime
- Behaviour conditional on the long ATR percentile

### State-transition analysis

Define volatility-acceleration states, for example:

| State | Definition |
|---|---|
| Strong contraction | Ratio below its rolling 20th percentile |
| Contraction | 20th percentile to 1 |
| Mild acceleration | 1 to the rolling 80th percentile |
| Strong acceleration | Above the rolling 80th percentile |

Estimate:

$$
P(State_{t+h}=j \mid State_t=i)
$$

This shows whether an acceleration state tends to persist or mean-revert, and how persistence changes across forecast horizons.

## 3. Define targets that measure acceleration

Predicting the future volatility level alone can exaggerate the ratio's usefulness. The long ATR already identifies the current volatility regime. Prefer targets that measure future volatility relative to recent or baseline volatility.

### Future realized volatility

For log returns $r_t$ over horizon $h$:

$$
RV_{t,h}^{future}=\sqrt{\sum_{i=1}^{h}r_{t+i}^2}
$$

### Future-to-past volatility change

$$
VolChange_{t,h}=
\log\left(
\frac{RV_{t+1:t+h}}
{RV_{t-h+1:t}}
\right)
$$

### Future volatility relative to the long ATR

$$
RelativeFutureVol_{t,h}=
\log\left(
\frac{RV_{t+1:t+h}}
{ATR_{\text{long},t}}
\right)
$$

### Future range expansion

$$
RangeExpansion_{t,h}=
\frac{
\max(High_{t+1:t+h})-
\min(Low_{t+1:t+h})
}{ATR_{\text{long},t}}
$$

### Binary expansion event

$$
Expansion_{t,h}=
\mathbb{1}\left(
RV_{t+1:t+h}>k\,RV_{past}
\right)
$$

### Price-behaviour targets

Also calculate:

- Absolute forward return
- Signed forward return
- Maximum favourable excursion (MFE)
- Maximum adverse excursion (MAE)
- Probability of hitting a target before a stop
- Breakout continuation or failure
- Trend continuation versus reversal

Suggested horizons on a 5-minute chart are 3, 6, 12, and 24 bars: 15, 30, 60, and 120 minutes.

## 4. Separate ratio level from ratio direction

Classify every observation into four states:

| Ratio level | Ratio change | Interpretation |
|---|---:|---|
| Above 1 | Rising | Active acceleration |
| Above 1 | Falling | Expansion losing momentum |
| Below 1 | Rising | Emerging expansion from contraction |
| Below 1 | Falling | Deepening contraction |

Test whether:

- Crossing above 1 predicts continued expansion.
- A rising ratio below 1 provides an early expansion warning.
- An extreme and still-rising ratio predicts persistence.
- An extreme but falling ratio indicates exhaustion.
- Crossing below 1 predicts continued contraction.

This distinction should help separate emerging acceleration from mature acceleration.

## 5. Run event studies

Create discrete, non-overlapping events such as:

- Fresh cross above 1
- Fresh cross below 1
- Cross above the rolling 80th or 90th percentile
- Exit from an extreme percentile
- Increase in the log ratio greater than a chosen threshold
- Local ratio peak while the ratio remains above 1
- Ratio acceleration following prolonged compression

For each event, examine the next 1 to 24 bars:

- Realized volatility
- Total range
- Absolute and signed return
- MFE and MAE
- Probability of hitting 0.5, 1.0, or 1.5 long-ATR units
- Probability that volatility continues expanding
- Probability of breakout continuation or failure

Do not treat every bar above a threshold as a new event. Require a fresh crossing, state reset, or cooldown period so that one volatility episode does not generate many highly correlated observations.

## 6. Perform conditional analysis

The same ratio reading may mean different things in different environments. Segment results by:

- Long ATR percentile: low, normal, or high
- Trading session and time of day
- Trend strength and recent directional return
- Distance from VWAP, session open, or opening range
- Position within the day's range
- Duration of the preceding compression
- Size of the bar that triggered the ratio change
- News and non-news periods, if event data are available

Important conditional comparisons include:

$$
P(Expansion \mid R_t>1.3,\ LongATR\ low)
$$

versus:

$$
P(Expansion \mid R_t>1.3,\ LongATR\ already\ extreme)
$$

A high ratio emerging from a quiet baseline may indicate the beginning of a breakout. The same ratio in an already extreme regime may represent a mature move or exhaustion.

## 7. Control for mechanical dependence

The short and long ATR share true-range observations. A single large bar mechanically:

1. Raises the short ATR sharply.
2. Raises the long ATR more slowly.
3. Produces a high ratio.
4. Raises any target that accidentally includes the triggering bar.

Therefore:

- Begin every target strictly after time $t$.
- Do not include the signal-generating bar in the future target.
- Control for the current bar's true range and absolute return.
- Control for past realized volatility, long ATR percentile, and time of day.

A useful incremental regression is:

$$
FutureVolChange_{t,h}=
\alpha+
\beta_1\log(R_t)+
\beta_2\Delta\log(R_t)+
\beta_3\frac{TR_t}{ATR_{long,t}}+
\beta_4 LongATRPercentile_t+
TimeControls_t+
\epsilon_t
$$

The ratio is more convincing if it improves genuinely forward predictions after controlling for the triggering bar and current volatility regime.

## 8. Establish benchmarks

Compare the ATR ratio against simpler predictors:

- Current true range divided by long ATR
- Absolute current return
- Past realized volatility
- Change in realized volatility
- Current bar range
- Long ATR percentile
- Time-of-day median volatility

Compare models in stages:

1. Time-of-day controls only
2. Baseline volatility features
3. Baseline plus ratio level
4. Baseline plus ratio level and ratio change
5. Baseline plus four-state or event features

The incremental out-of-sample improvement from stages 3 to 5 is the relevant measure of predictive value.

## 9. Test directional applications separately

ATR is directionless, so the ratio alone should not be expected to predict whether price rises or falls. Test whether it changes the effectiveness of an independent directional signal.

For example:

$$
Direction_t=sign(Close_t-Close_{t-k})
$$

Then define direction-adjusted forward performance:

$$
Continuation_{t,h}=Direction_t\times ForwardReturn_{t,h}
$$

Candidate hypotheses include:

- Rising ratio plus a directional breakout predicts continuation.
- Extreme ratio plus weakening price momentum predicts exhaustion.
- Prolonged contraction plus a ratio upswing predicts expansion, but not direction.
- Falling ratio after an extended price move reduces continuation probability.

## 10. Validate without leakage

Five-minute observations and forward targets overlap heavily. Conventional random train/test splits and ordinary p-values will overstate confidence.

Use:

- Chronological walk-forward evaluation
- Purging at split boundaries equal to the maximum forecast horizon
- An embargo where appropriate
- Block bootstrap by trading day or week
- Newey-West standard errors for overlapping observations
- Non-overlapping samples for event studies
- Training-only thresholds and normalisation parameters
- A final untouched test period

A practical walk-forward structure is:

- Train on two to three years
- Validate on the next six months
- Test on the following six months
- Roll forward and repeat

## 11. Evaluation metrics

### Continuous volatility targets

- Spearman rank correlation
- Out-of-sample $R^2$
- MAE and RMSE
- Quintile or decile monotonicity
- Top-minus-bottom quantile spread
- Stability by year and session

### Expansion classification

- ROC-AUC
- Precision-recall AUC
- Brier score
- Calibration curve
- Top-decile lift

### Event studies

- Mean and median response
- Bootstrap confidence intervals
- Number of independent events
- Persistence across years and sessions
- MFE, MAE, and target-before-stop probabilities

### Trading usefulness

- Improvement in position sizing
- Improvement in stop and target selection
- Change in breakout-filter performance
- Change in momentum versus mean-reversion performance
- Performance after fees and slippage

## 12. Recommended first experiment

Start with a compact, falsifiable specification:

### Signal features

- $\log(ATR_5/ATR_{60})$
- One-bar change in the log ratio
- Three-bar slope of the log ratio
- Four-state level-and-direction classification
- Fresh cross above and below 1

### Forecast horizons

- 15 minutes
- 30 minutes
- 60 minutes

### Targets

- Future-to-past realized-volatility ratio
- Future range divided by current long ATR
- Absolute forward return
- Direction-adjusted forward return
- Binary volatility-expansion event

### Controls

- Current true-range shock
- Current absolute return
- Past realized volatility
- Long ATR percentile
- Time of day and session
- Recent signed return

### Analysis

- Descriptive statistics and state durations
- Ratio quintile tables
- Four-state comparisons
- Non-overlapping crossing-event studies
- Baseline-versus-augmented predictive models
- Walk-forward out-of-sample evaluation
- Day-level block-bootstrap confidence intervals

## 13. Main interpretation framework

The central research distinction is:

$$
\text{Emerging acceleration}
\quad\text{versus}\quad
\text{Mature acceleration}
$$

A rising ratio following prolonged compression may predict further expansion. An extremely high but declining ratio may instead indicate volatility exhaustion. The ratio's path, starting volatility regime, and triggering-bar size are therefore likely to be more informative than its raw level alone.

The ultimate test is whether the ATR ratio adds stable, out-of-sample predictive information beyond current true range, past realized volatility, long-term volatility regime, and time of day.
