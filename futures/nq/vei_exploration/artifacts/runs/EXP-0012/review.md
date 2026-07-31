# EXP-0012 Results Discussion

- Hypothesis: `HYP-0009` — The frozen two-feature core carries conditional forward-30m volatility information beyond its causal same-slot median.
- Status: completed
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Within-slot rank IC delta of core forecast versus causal same-slot median, with session-block 90% CI; co-primary residualized log-vol correlation/R2 and log-MSE skill.
- Kill test: Calibration-only unless both NQ and ES have positive log-MSE skill versus the median and lower 90% session-block bounds above zero for within-slot IC delta and FWL residual correlation.

## Result versus hypothesis

**CONFIRMED on both NQ and ES.** The frozen two-feature core retains very strong
forecast information after conditioning on the causal same-slot median. The result
rejects the proposed explanation that the pooled IC is mostly a clock-composition
effect.

Annual expanding-window OOS evaluation covered 2016 through 2026-07-14, with 29,313
NQ and 29,315 ES decisions. The model's pooled raw-volatility IC was 0.8875 NQ / 0.8761
ES versus 0.4828 / 0.4271 for the median alone. The original normalized-target IC
reproduced at 0.8268 / 0.8271.

The primary within-slot rank IC was 0.8782 / 0.8711 for the core versus 0.4181 /
0.3825 for the median, a delta of **+0.4601 NQ** (90% session-block CI
[0.4365, 0.4833]) and **+0.4886 ES** ([0.4625, 0.5158]). The stricter same-slot ×
weekday delta was +0.4561 / +0.4839, so weekday/clock composition does not explain
the result.

After FWL-residualising `log(fwd_rv)` and `log(forecast)` on `log(slot_median)`, the
residual correlation was 0.8562 / 0.8560 and R² 0.7331 / 0.7328. Log-MSE skill versus
the median was **+73.56% NQ** (CI [72.23%, 74.71%]) and **+74.23% ES**
([72.84%, 75.46%]). Every preregistered gate passed on both markets.

## Gross, net, baseline, and null comparison

This is a forecasting experiment, not a trading backtest; gross/net P&L and trading
costs do not apply. The free baseline is the causal trailing 90-session same-slot
median. Raw MAE fell from 9.0063 to 4.7785 volatility bp on NQ and from 7.4733 to
3.9251 volatility bp on ES, roughly a 47% reduction. These units describe error in
realized-volatility basis points, not futures price points or P&L.

## Regimes, sensitivity, and alternative explanations

The within-slot IC delta, FWL residual correlation/R², and log-MSE skill were positive
in every evaluated year on both markets. All 11 forecast-start slots from 10:00 through
15:00 ET materially beat the median. Per-slot model IC ranged 0.8357-0.9021 NQ and
0.8324-0.8928 ES. Same-slot × weekday conditioning produced almost the same result as
same-slot conditioning alone.

NQ and ES are correlated markets and are not independent replications. The most direct
alternative explanation—intraday clock ordering—was removed by construction. Because
the only non-baseline input is `range_rv_15m`, the remaining information is attributable
to the current range state and its nonlinear interaction with the median; the experiment
does not claim a purely linear standalone range effect.

## Artifact and implementation risks

The notebook recomputes sampled range features, forward targets, and shifted rolling
medians from raw bars. Maximum errors were numerical zero; feature and target windows
did not overlap; forecast clocks were exact; duplicate and out-of-order timestamps were
zero. Full defaults were 220 boosting iterations and 300 session-block draws.

Evaluated source SHA-256:
`48c80063518d4d57b5d595144eb1004ffdba09ec1420f0015c9d65d887731d51`.

The evaluation is causally walk-forward but not a fresh research holdout: the
conditional question was posed after earlier results, and all data through 2026-07-14
is consumed. Only later observations can provide clean prospective confirmation.

## Builder interpretation

The two-feature core is a genuine **conditional forward-volatility forecast**, not
merely a time-of-day calibration instrument. Retain the operational specification:
causal same-slot median + `range_rv_15m`. Keep multi-horizon variables as a shadow
benchmark only. This establishes volatility forecast skill, not directional alpha or
economic value; any sizing, risk, execution, stop, or options application needs its own
preregistered decision-specific test.

## Independent review

- Review status: pending
- Objections: independent review not yet assigned
- Verdict: builder verdict confirmed; independent review pending

## Promotion decision

- `reports/FINDINGS.md`: focused handoff written to
  `reports/CONDITIONAL_FORWARD_VOL_HANDOFF.md`; main FINDINGS not rewritten
- `MEMORY.md`: promote the conditional-signal verdict, limitations, and next action
- Shared `LEARNINGS.md`: not eligible without cross-project verification
