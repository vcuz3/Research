# Conditional Forward-Volatility Handoff

## Read this first

The canonical forward-30-minute volatility model is intentionally simple:

1. the causal trailing 90-session median of forward 30-minute realized volatility at
   the same decision slot; and
2. `range_rv_15m`, the realized high-low range state over the latest 15 one-minute bars.

EXP-0011 established that six additional multi-horizon volatility variables add a real
but operationally marginal amount of accuracy. They were not adopted. EXP-0012 then
tested the more fundamental objection: perhaps the simple core's high pooled IC mostly
comes from ordering naturally quiet and naturally volatile clock slots. That objection
is decisively rejected on consumed history. The core remains very strong within a fixed
slot and within a fixed slot × weekday.

**Current verdict:** the core is a genuine conditional volatility forecast, not merely
a clock calibration/normalisation device. This is forecast skill, not directional alpha
or demonstrated economic value.

## Evidence and status

- Experiment: `EXP-0012`, hypothesis `HYP-0009`.
- Builder: Codex; independent reviewer: unassigned/pending.
- Source: `notebooks/conditional_forward_vol_signal.py`.
- Evaluated source SHA-256:
  `48c80063518d4d57b5d595144eb1004ffdba09ec1420f0015c9d65d887731d51`.
- Run artifact: `artifacts/runs/EXP-0012/review.md`.
- Data: clean Databento NQ and ES one-minute RTH data.
- Annual expanding-window OOS predictions: 2016 through 2026-07-14.
- Evaluation rows: 29,313 NQ / 29,315 ES.
- Model: `HistGradientBoostingRegressor`, frozen 220-iteration specification, trained
  on `log1p(fwd_rv_bp_norm)`; 300 session-block bootstrap draws.
- Research-holdout status: consumed. Walk-forward prediction is causal, but the test was
  proposed after prior results. Only data after 2026-07-14 is clean future evidence.

To reproduce interactively from the Research workspace:

```powershell
marimo edit futures/nq/vei_exploration/notebooks/conditional_forward_vol_signal.py
```

Use the full defaults and press **Build data and run conditional test**.

## Exact forecast construction

At decision row `d,s`, where `s` is one of 11 fixed RTH slots:

```text
slot_median[d,s]
    = median of fwd_rv_bp at the same slot over at most 90 earlier sessions
      after shift(1), requiring at least 60 valid observations

fwd_rv_bp_norm[d,s]
    = fwd_rv_bp[d,s] / slot_median[d,s]

model inputs
    = [slot_median[d,s], range_rv_15m[d,s]]

forecast_bp[d,s]
    = model_forecast_norm[d,s] * slot_median[d,s]
```

`fwd_rv_bp` is `10,000 * sqrt(sum of 30 squared one-minute open-to-open log
returns))`, beginning at the next minute's open. `range_rv_15m` is
`sqrt(sum(log(high/low)^2))` over the 15 completed one-minute bars ending at the
decision row. Sampled reconstruction audits confirmed exact clocks, no feature/target
overlap, no roll inside target paths, and numerical-zero formula errors.

## Why EXP-0012 was necessary

The skeptical claim was:

> A pooled IC near 0.83 might mostly reward the model for ranking a naturally quiet
> morning observation below a naturally volatile late-day observation. A live decision
> is made at one fixed slot, so that cross-slot ordering may be operationally irrelevant.

The preregistered gate required both markets to have:

1. positive log-MSE skill versus the median;
2. a lower 90% session-block bound above zero for the within-slot IC improvement; and
3. a lower 90% bound above zero for the residual log-volatility correlation after
   removing the median from actual and forecast volatility.

Both markets passed every gate.

## Headline results

| Metric | NQ | ES | Meaning |
| --- | ---: | ---: | --- |
| Pooled raw IC, model | 0.8875 | 0.8761 | Overall rank ordering of raw forward volatility |
| Pooled raw IC, median | 0.4828 | 0.4271 | Rank ordering available from the free baseline |
| Pooled normalized IC | 0.8268 | 0.8271 | Ordering of volatility relative to the slot median |
| Within-slot IC, model | 0.8782 | 0.8711 | Ordering across days at the same clock slot |
| Within-slot IC, median | 0.4181 | 0.3825 | Same comparison for the median alone |
| **Within-slot IC delta** | **+0.4601** | **+0.4886** | Core improvement over the median |
| 90% CI for delta | [0.4365, 0.4833] | [0.4625, 0.5158] | Session-block uncertainty |
| Slot × weekday IC delta | +0.4561 | +0.4839 | Removes clock and weekday composition |
| FWL residual correlation | 0.8562 | 0.8560 | Remaining log-vol association after median removal |
| **FWL residual R²** | **0.7331** | **0.7328** | Remaining log-vol variation associated with forecast |
| Log-ratio R² | 0.7420 | 0.7453 | Direct ratio-to-median diagnostic |
| **Log-MSE skill vs median** | **+73.56%** | **+74.23%** | Reduction in squared log error versus median |
| 90% CI for skill | [72.23%, 74.71%] | [72.84%, 75.46%] | Session-block uncertainty |
| Raw MAE, model | 4.7785 vol bp | 3.9251 vol bp | Mean absolute forecast error |
| Raw MAE, median | 9.0063 vol bp | 7.4733 vol bp | Mean absolute error of free baseline |

Do not read +74% log-MSE skill as "74% accurate." It is a 74% reduction in one loss
function relative to the median. Volatility basis points are not futures price points
and are not P&L.

## Metric interpretation

### IC

IC is Spearman rank correlation. It asks whether high forecasts correspond to high
outcomes, not whether the forecast has the correct numerical scale. One is perfect
ordering and zero is no ordering. The model's 0.88 pooled raw IC is extremely strong,
but pooled IC alone was the disputed measure.

### Within-slot IC

Each forecast and outcome is ranked only against observations from the same clock slot;
the ranks are then pooled after removing group means. A 10:00 forecast is never rewarded
for ranking below a 15:00 outcome. The core retains 0.878/0.871 IC and improves on the
median by 0.460/0.489. This directly rejects the clock-composition explanation.

### Slot × weekday IC

This repeats the test inside cells such as Tuesday 10:00 or Friday 15:00. The result is
almost unchanged, so weekday composition is not the hidden source of forecast skill.

### FWL residual R²

`log(fwd_rv)` and `log(forecast)` are separately regressed on an intercept and
`log(slot_median)`. The residuals are compared. The residual correlation is about 0.856
and its square is about 0.733 on both markets: after linearly removing the median, the
forecast is still associated with roughly 73% of the remaining log-volatility variation.
This is a diagnostic association from OOS predictions, not a causal economic effect.

### Log-MSE skill

This is `1 - model squared-log-error / median squared-log-error`. Positive means the
model is numerically more accurate than the free median, not merely better ranked. The
core reduces this error by about 74% on both markets. Raw MAE also falls by about 47%.

## Stability

All evaluated years had positive within-slot delta, positive residual correlation, and
positive log-MSE skill on both markets. 2026 is partial through July 14.

| Market | Year | Within-slot delta | FWL residual R² | Log-MSE skill |
| --- | ---: | ---: | ---: | ---: |
| NQ | 2016 | +0.442 | 0.662 | +65.2% |
| NQ | 2017 | +0.766 | 0.586 | +56.1% |
| NQ | 2018 | +0.823 | 0.812 | +84.8% |
| NQ | 2019 | +0.556 | 0.657 | +67.5% |
| NQ | 2020 | +0.911 | 0.795 | +85.8% |
| NQ | 2021 | +0.734 | 0.746 | +73.5% |
| NQ | 2022 | +0.791 | 0.631 | +67.3% |
| NQ | 2023 | +0.493 | 0.583 | +61.0% |
| NQ | 2024 | +0.760 | 0.620 | +61.5% |
| NQ | 2025 | +0.717 | 0.781 | +77.6% |
| NQ | 2026 YTD | +0.659 | 0.613 | +61.1% |
| ES | 2016 | +0.417 | 0.644 | +63.1% |
| ES | 2017 | +0.392 | 0.453 | +42.2% |
| ES | 2018 | +0.898 | 0.808 | +84.5% |
| ES | 2019 | +0.538 | 0.623 | +65.9% |
| ES | 2020 | +0.908 | 0.801 | +85.8% |
| ES | 2021 | +0.685 | 0.724 | +72.4% |
| ES | 2022 | +0.816 | 0.653 | +70.7% |
| ES | 2023 | +0.524 | 0.592 | +61.9% |
| ES | 2024 | +0.769 | 0.611 | +61.1% |
| ES | 2025 | +0.756 | 0.789 | +79.7% |
| ES | 2026 YTD | +0.817 | 0.629 | +61.8% |

All 11 forecast-start slots from 10:00 through 15:00 ET materially beat the median.
Per-slot model IC ranged 0.8357-0.9021 NQ and 0.8324-0.8928 ES. The weakest observed
slot was still strong; there is no single time-of-day cell carrying the result.

## Interpretation and limits

The same-slot median is useful: it has pooled raw IC 0.48/0.43 and within-slot IC
0.42/0.38 because volatility regimes persist over time. It is not sufficient. Once its
information is removed, the two-feature model remains strongly predictive. Since the
only other input is `range_rv_15m`, the incremental information comes from the current
15-minute range state and its nonlinear interaction with the baseline.

This does **not** establish:

- return direction or directional alpha;
- an economically valuable sizing, execution, stop, or options rule;
- independent confirmation from NQ and ES, which are highly correlated markets;
- a fresh holdout result, because the research history is consumed; or
- that histogram gradient boosting is the simplest deployable mapping. The feature set
  is simple, but the nonlinear model may still need compression or calibration for a
  production implementation.

## Decisions already made

- Production feature specification remains the causal same-slot median plus
  `range_rv_15m`.
- Do not add the six multi-horizon variables; keep them as a shadow benchmark only.
- Do not tune features, model hyperparameters, slots, or lookbacks on data through
  2026-07-14.
- Do not call this directional alpha. Forecast skill needs a separately specified use
  case and economic estimand.

## Recommended next work for the taking-over agent

1. **Independently review EXP-0012.** Reproduce the full Marimo defaults, inspect the
   target/range/median audits, verify the grouped-rank IC implementation, and challenge
   the very large conditional effect. Record reviewer name and status in the ledger.
2. **Choose one operational use case before more modelling.** Candidate uses are
   volatility targeting, position-size caps, execution urgency, stop/target scaling, or
   options/variance decisions. Define exactly how forecast error changes that decision.
3. **Specify the correct decision loss.** MAE/QLIKE/log-MSE are forecast diagnostics;
   the chosen application may require asymmetric underprediction penalties, tail recall,
   calibration by forecast bucket, or dollar-risk utility.
4. **Benchmark simpler mappings without feature search.** A transparent log-linear or
   monotone two-variable mapping may retain enough of the gradient-boosting benefit. Any
   model comparison on consumed history is descriptive and must not silently become a
   promoted selection.
5. **Begin future-only shadow logging after 2026-07-14.** Store timestamp, median,
   `range_rv_15m`, forecast ratio, forecast bp, and realized forward bp. Do not refit or
   change the specification based on the shadow sample before its planned review date.
6. **Keep multi-horizon state in shadow only.** EXP-0011 found a statistically real but
   operationally marginal gain of about +0.009 normalized IC and 0.18 bp raw MAE for six
   extra variables.

## Relevant files

- `notebooks/conditional_forward_vol_signal.py` — EXP-0012 executable Marimo analysis.
- `artifacts/runs/EXP-0012/review.md` — immutable run interpretation.
- `experiments/hypotheses/HYP-0009.md` — predeclared conditional test.
- `experiments/ledger.csv` — experiment status and result.
- `notebooks/range_multihorizon_vol_confirmation.ipynb` — EXP-0011 simple-versus-multi
  confirmation.
- `artifacts/runs/EXP-0011/review.md` — EXP-0011 operational non-adoption verdict.
- `MEMORY.md` — current project-wide durable state.
