# RSI volatility-feature breadth audit

## Verdict

The concern is **confirmed on inference scope** and **not confirmed as a new
feature discovery**.

The current `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` now correctly describes its
result as a narrow, non-exhaustive negative. The underlying Arm 2 tested one
vol-of-vol estimator, conventional sample kurtosis at two short windows, one
backward-looking RV ratio, and one 30-minute RSI-survival label. Those are valid
tests of those exact constructions; they cannot establish that kurtosis, term
structure, or volatility structure generally do not distinguish continuation
from snap-back.

A frozen breadth audit expanded the search to 28 causal features spanning RV
level, multi-horizon RV ratios, two normalized vol-of-vol constructions, four
kurtosis windows, quarticity, bipower jump share, largest-return concentration,
and downside semivariance. It tested RSI survival, any loss, fixed-pip tail loss,
and (as a disclosed post-run diagnostic) volatility-scaled tail loss. The result
is still negative for *incremental* engineered-volatility information:

- median expanded-minus-baseline AUC is **-0.0138** for RSI survival;
- **+0.0017** for fixed-pip tail loss;
- **+0.0028** for volatility-scaled tail loss;
- no target improves by at least 0.015 in three of four pairs;
- filtering the half scored riskiest has inconsistent P&L effects and usually
  reduces the clustered t-statistic.

The defensible conclusion is: **none of the tested engineered volatility
features adds stable information beyond RSI depth and the already-known RV(30)
percentile on consumed 2012-2023 midpoint data.** The canonical 30/70 × 30-minute
strategy remains a NO-GO on economics. The evidence does **not** support the
universal statement that volatility structure contains no useful information.

The frozen univariate gate formally passes because all RV-level horizons predict
the fixed-pip tail and RV(30) predicts the survival label. That is a gate-design
flaw for the narrower question of *incremental* feature value: the gate allowed
the known baseline family to count as a breadth-screen discovery. The separately
frozen incremental model gate fails. The run is therefore recorded as a formal
univariate pass but **no new engineered-feature survivor**.

## Reading the external commentary precisely

### RSI and volatility scaling

The sentence that RSI “treats every unit of price displacement equally” is not
literally correct. Wilder RSI can be written as a signed average change divided
by an average absolute change, so it contains an internal L1 scale estimate.
Multiplying every return in the lookback by the same positive constant leaves
RSI unchanged.

But “false about the indicator” was also too categorical in the earlier report.
RSI is locally scale-invariant; it does not condition that ratio on a broader
volatility state, tail distribution, horizon, or transition probability. Two
paths can have identical RSI and very different absolute RV, jump concentration,
or volatility histories. The literal claim is wrong, but the regime-conditioning
intuition is valid.

### Regime detection versus a regime gate

The commentary says regime measurement is upstream of stress measurement. The
programme answered a narrower proposition: a fixed raw threshold can become a
time-of-day selector. Those statements are compatible. The project's causal
same-slot percentile is itself a regime-normalization device. The evidence
supports same-slot normalization over a raw global gate; it does not make regime
detection the wrong prescription.

### Kurtosis

The original result is accurately summarized as: conventional rolling sample
kurtosis over 30 and 60 one-minute returns did not predict the specific 30-minute
RSI-survival label (median AUC 0.507/0.500, q near 0.9). It should not be
summarized as “kurtosis is not a variable at this horizon.”

The breadth audit adds 120/240-minute kurtosis, realized-quarticity ratios,
largest-return concentration, and bipower jump share. None adds stable
incremental model value. Some isolated cells pass row-level corrected tests, but
no novel tail feature meets the frozen cross-pair effect-size gate. This expands
the negative search boundary without making it exhaustive. Robust quantile or
L-moment kurtosis, conditional distribution models, and multi-day memories remain
untested.

### “What if it does not revert?”

This remains the strongest part of the commentary and programme. Only 6.0-7.5%
of signals remain extreme at the next checkpoint, but those signals lose
8.3-12.4 pips and remove roughly 45% of the gross gains from the remainder.

However, “RSI remains beyond 30/70 in 30 minutes” is not synonymous with a
structural regime transition or an economically catastrophic loss. The breadth
audit therefore added direct loss targets.

### Vol-of-vol and “term structure”

The original report tested the standard deviation of overlapping RV(5) estimates
over 60 minutes. This audit additionally tested level-normalized RV(5)
dispersion and dispersion of log-RV(5) innovations over 60 and 120 minutes. The
new constructions still do not add stable value. That is a broader negative for
price-only vol-of-vol in this dataset, not a universal rejection.

Calling RV(5)/RV(30) “term structure” is especially strong. It is one
backward-looking ratio of realized-volatility estimates. A market volatility
term structure contains distinct maturity prices or forecasts, such as implied
volatility or variance-swap tenors. No such data exists in this spot-FX midpoint
dataset, so the commentary's term-structure proposal was not tested.

## Breadth-audit results

### Frozen design

- Four USD spot-FX pairs, 2012-2023; 2024+ untouched.
- Same half-hour signal clock and fixed 30-minute return as the programme.
- 28 causal features transformed to 90-session same-slot percentiles.
- Train 2012-2018, choose L2 regularization on 2019-2020, refit through 2020,
  and evaluate 2021-2023. This is historical robustness, not a clean holdout.
- Baseline model: RSI depth plus canonical RV(30) percentile.
- Expanded model: baseline plus all 28 volatility features.
- 500-draw session-block bootstrap and BH correction over the full univariate
  screen.

Feature coverage is not uniform. Median late-era coverage is 89.0%; the minimum
is 70.1% for NZDUSD 240-minute kurtosis. Expanded-model common test samples are
2,362-2,753 signals versus 3,052-3,346 for the baseline. AUC deltas below are
computed on the common sample.

### Model comparison on common rows

| Target | EURUSD | GBPUSD | AUDUSD | NZDUSD | Median delta |
|---|---:|---:|---:|---:|---:|
| RSI survives 30m | -0.0239 | +0.0363 | -0.0272 | -0.0036 | **-0.0138** |
| Fixed-pip tail loss | +0.0086 | -0.0051 | +0.0093 | -0.0099 | **+0.0017** |
| Vol-scaled tail loss* | -0.0307 | +0.0073 | +0.0075 | -0.0017 | **+0.0028** |

\* Added after the first run to diagnose the scale channel and excluded from the
frozen decision gate.

### What RV level actually predicts

All five RV levels predict the fixed-pip bottom-decile loss in the same direction
on all four pairs (median AUC 0.557-0.580). This is useful for risk sizing but is
partly mechanical: a fixed pip loss is easier to reach when conditional scale is
larger.

After defining the tail in trailing-RV units, the relationship reverses. Median
AUC is 0.406 for RV(30), 0.412 for RV(15), and 0.447 for RV(120): higher current
RV predicts a lower probability of an exceptionally bad loss relative to that
scale. This agrees with the existing finding that reversion is stronger in
high-current-RV states. It is not a new engineered feature, and the expanded
model does not improve on the baseline that already contains RV(30).

For the original survival label, RV(30) remains the clearest volatility
separator (median AUC **0.4595**, below 0.5 in all four pairs): high RV predicts
less persistence. The best novel vol-of-vol candidate, log-RV innovation
dispersion over 60 minutes, points toward more persistence in all four pairs but
is small (median AUC 0.5199, minimum full-screen q 0.109) and fails the frozen
effect-size gate.

## Correct conclusion and next step

Retain the current report's economic warning, continuation-tail finding, and
exact negatives for its tested features. State the feature conclusion as:

> No tested price-only engineered volatility feature materially improved on RSI
> depth plus canonical RV(30). Conventional intraday kurtosis and the tested
> vol-of-vol/RV-ratio constructions failed; genuine implied-volatility term
> structure was not tested.

This remains a broad screen on consumed history. It has no bid/ask execution,
options-implied volatility, spread/liquidity state, news state, cross-asset
volatility, or latent regime model. Correlated pairs are not four independent
replications, and longer features lose material coverage.

The next defensible feature experiment is not another large price-only sweep. It
is a small, preregistered test of genuinely new information: executable FX
spread/liquidity data, implied-volatility tenors or risk reversals, and a target
defined directly from adverse path/economic loss. Without those data, close the
price-only feature line while keeping the broader causal claim open.

Two measurement references support the scope distinction. Kim and White show
that conventional sample skewness/kurtosis can be extremely sensitive to a small
number of outliers and compare robust alternatives
(https://doi.org/10.1016/S1544-6123(03)00003-5). Barndorff-Nielsen and Shephard
develop bipower variation specifically to separate continuous variation from
jump variation, motivating the jump-share arm here
(https://doi.org/10.1093/jjfinec/nbh001). These references motivate alternative
measurements; they do not validate a trading signal in this dataset.

## Evidence

- Frozen/amended specification: `RSI_VOLATILITY_FEATURE_BREADTH_AUDIT_SPEC.md`
- Reproduction: `_run_rsi_volatility_feature_breadth_audit.py`
- Results: `rsi_volatility_feature_breadth_audit_results.json`
- Univariate screen: `rsi_volatility_feature_breadth_audit_univariate.csv`
- Model comparison: `rsi_volatility_feature_breadth_audit_models.csv`
- Coverage: `rsi_volatility_feature_breadth_audit_coverage.csv`
- Audited report: `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md`
