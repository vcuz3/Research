# HYP-0039 mechanism gate — first-30-min realized vol forecasts rest-of-session vol

Diagnostic (not a P&L experiment). Answers kill test 1 (does early realized vol
ADD over prior-session vol, out-of-sample) and placebo 3 (no directional leak)
before any sizing run. Script: `scripts/hyp_0039_vol_gate.py`. TRAIN 2011-08→2020-07
(n=2230) / TEST 2020-07→2026-07 (n=1487). HAR-style OLS in log-vol; Newey-West
HAC(5) t; forecast target = realized vol of 1-min log returns from mfo 30 to close.

## Result — GATE PASS on both markets, clean placebo, transfers

| | OOS R² prior_vol only | OOS R² + early_rv | added by early_rv | TRAIN HAC t (early_rv) | dir. placebo |
|---|---|---|---|---|---|
| **NQ** | +0.522 | +0.641 | **+0.119** | +23.96 | t +0.21 / OOS corr +0.035 — clean |
| **ES** | +0.540 | +0.651 | **+0.111** | +25.13 | t +1.22 / OOS corr +0.038 — clean |

- **Early realized vol is a strong causal forecaster of rest-of-session vol** and
  adds materially (+0.11–0.12 OOS R²) over yesterday's vol. Both markets, same sign.
- **No directional leak** (placebo 3 passes): `early_rv` does not predict the SIGN
  of the rest-of-session return (HAC t≈0, |OOS corr|<0.04). Confirms the feature
  is a *magnitude* read, consistent with `nq-post-lunch-opening-range-nogo` — so
  the sizing-only constraint is honoured and the feature is not smuggling direction.

## Daily-vol baseline horse-race (which forecaster to benchmark against)

`scripts/hyp_0039_vol_baselines.py`, OOS R² for log(rest_rv):

| forecaster | NQ | ES |
|---|---|---|
| yesterday only (yday) | 0.522 | 0.542 |
| trailing 5-day mean | 0.502 | 0.497 |
| trailing 22-day mean | 0.359 | 0.343 |
| EWMA (hl=10) | 0.412 | 0.397 |
| **HAR {yday, ma5, ma22}** | **0.568** | **0.577** |
| HAR + early_rv | 0.656 | 0.664 |

- **A single trailing average does NOT beat yesterday** — vol is most-recent-weighted;
  ma5/ma22/EWMA are all worse than the naive 1-day. Only the **HAR** multi-horizon
  mix beats yesterday (+0.046 NQ / +0.036 ES).
- **early_rv still adds +0.087/+0.087 over the best daily baseline (HAR).** So the
  sizing benchmark is a HAR-vol sizer, and early_rv must beat THAT — which it does
  by a wide margin in forecast terms.

## Caveat before the sizing step (kill test 2)

This is a **necessary, not sufficient** result and it is a **known stylized fact**
(intraday realized vol is autocorrelated; HAR-RV). Two honest cautions for the P&L
sizing run:

1. **prior_vol alone already forecasts at R²≈0.53.** So sizing on *yesterday's vol*
   is a strong baseline; `early_rv`'s value to SIZING is only its **+0.11 marginal**
   — i.e. whether re-sizing intraday at mfo 30 beats a size set at the open from
   yesterday's vol. The sizing experiment must benchmark against the prior_vol-only
   sizer, not against flat size (the LEARNINGS §3 degenerate control), or it will
   credit `early_rv` with the whole vol-persistence effect.
2. **Forecast skill ≠ Calmar improvement.** Whether this translates to a
   drawdown-aware trading gain (Calmar at matched long-run exposure) is open;
   RULES C/E (no leverage manufacturing, matched exposure, 1-contract gross
   preserved) govern the P&L read. Many vol-persistence facts do not beat a simple
   prior-vol sizer net of contract-floor granularity.

## Overnight-vol uplift addendum (general vol-forecasting, reusable)

`scripts/hyp_0039_overnight.py`. Same target log(rest_rv), OOS on TEST, but on the
subsample with near-complete ETH/Globex coverage (NQ n_tr=1428/n_te=952; ES
n_tr=1013/n_te=676 — smaller than the gate, so marginals here are internally
comparable but not one-to-one with the gate table above). Overnight predictors:
`overnight_rv` = realized vol of 1-min log returns 18:00→09:29 ET; `gap_abs` =
|log(rth_open / prior_rth_close)|. Both strictly known before the RTH open.

| OOS R² predicting log(rest_rv) | NQ | ES |
|---|---|---|
| yday (yesterday full rv) | 0.546 | 0.535 |
| **overnight_rv** alone | 0.552 | 0.519 |
| **early_rv** alone (first 30m) | 0.580 | 0.599 |
| gap_abs alone | −0.481 | −1.058 |
| HAR {yday,ma5,ma22} | 0.584 | 0.577 |
| HAR + overnight_rv | 0.650 | 0.644 |
| HAR + early_rv | 0.655 | 0.660 |
| **HAR + early_rv + overnight_rv** | **0.676** | **0.677** |
| + gap_abs | 0.670 | 0.676 |

**Marginal OOS R² (what each block adds):**

| increment | NQ | ES | TRAIN HAC t |
|---|---|---|---|
| overnight_rv over HAR | +0.066 | +0.067 | — |
| early_rv over HAR | +0.071 | +0.083 | +18.5 / +16.4 |
| **overnight_rv over HAR + early_rv** | **+0.021** | **+0.017** | +8.6 / +5.8 |
| gap_abs over HAR + early + overnight | −0.006 | −0.002 | — |

**What genuinely uplifts the vol forecast (both markets, same story):**

1. **The single biggest lever beyond daily history is the first 30 min of the
   session** (`early_rv`): +0.071/+0.083 OOS R² over HAR, HAC t≈17–18. This is the
   dominant intraday source.
2. **Overnight realized vol IS informative but largely REDUNDANT with the opening
   30 min.** On its own it rivals yesterday's vol (0.55/0.52) and adds +0.066 over
   HAR — comparable to early_rv's raw uplift — but once `early_rv` is in the model
   it adds only **+0.021/+0.017** (still HAC-significant, t 8.6/5.8). The overnight
   and the opening print overlap because both read the *current* vol regime; the
   opening 30 min reads it slightly better.
3. **The best causal forecast stacks all three: HAR + early_rv + overnight_rv →
   OOS R² ≈ 0.68 both markets**, up from ≈0.58 daily-only — a ~+0.09–0.10 lift for
   future position sizing.
4. **The signed open GAP is not a vol predictor.** `gap_abs` alone has NEGATIVE OOS
   R² (its TRAIN fit does not generalize) and subtracts once realized vols are
   present. Dispersion (sum of squared overnight returns) carries the vol signal;
   the single open jump does not.

Reusability: this is a general daily→intraday→overnight RV nesting, instrument-
agnostic. For any session-anchored book, the causal-forecast ladder is
yesterday < HAR < HAR+opening-30m ≈ +overnight, with the opening print the biggest
add and overnight a small significant top-up. (The separate question of whether the
forecast *monetizes* as sizing is answered NO for this ATR-pre-normalized book —
see `HYP-0039-sizing/FINDINGS.md`.)

## Next step

Build the causal vol-target sizing layer on the deployed clock book and evaluate
Calmar / vol-of-daily-P&L at matched exposure on TEST, benchmarking BOTH vs flat
1-contract AND vs the prior_vol-only sizer. Register as EXP when run. *(Done —
EXP-0050, NO-GO for this book; see `HYP-0039-sizing/FINDINGS.md`.)*
