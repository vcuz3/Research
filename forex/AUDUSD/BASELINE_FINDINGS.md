# AUDUSD Baseline Predictive Model — Findings (Step 2)

**Date:** 2026-07-09 · **Panel:** `data/audusd_intraday_modeling_panel.csv`
(332,453 × 15-min bars, 2013-01-02 → 2026-07-08) · **Verdict: NO tradable baseline
edge.** A *statistically detectable* but *economically negligible* short-horizon
signal exists in the technical features; it does not survive transaction costs.

This is the intended deliverable: a **clean, leakage-safe benchmark** against which
future regime-conditioned models must prove a *net-of-cost* improvement.

---

## What was built

| Output | File |
|---|---|
| Reusable feature/target module (causal) | `baseline_features.py` |
| Walk-forward validator (expanding, embargoed, causal-standardized) | `walkforward.py` |
| Overlap-aware regression / classification / trading metrics | `metrics.py` |
| End-to-end driver → result tables | `run_baseline.py` → `results/*.csv` |
| Clean reproducible notebook | `baseline_model.ipynb` |

**Models:** Ridge (forward returns) and Logistic (direction). ElasticNet is wired in
`walkforward.py` as an option; LightGBM is deliberately deferred (the brief marks it
"later comparison, not primary", and a linear baseline with ~0 IC gives a tree nothing
to exploit that would change the verdict).

**Horizons:** 1h = 4 bars, 4h = 16 bars, 1d = 96 bars.

### Leakage controls (all enforced in `walkforward.py`)
- **Expanding** train window; refit once per calendar quarter.
- **Embargo of `horizon` bars** between train end and test start, so a training label
  that looks `h` bars forward can never overlap the test block.
- **Causal standardization**: median-impute + `StandardScaler` fit on the *train* slice
  only, applied to test.
- **No random splits.** Significance reported on **non-overlapping** samples (one every
  `horizon` bars) — the honest basis given the overlapping forward labels
  (CLAUDE.md gotcha #3).
- Daily `f_*` / monthly `macro_*` conditioning features enter the panel already lagged
  one business day (upstream guarantee) and are consumed as-is.

---

## Results

### 1. Regression — out-of-sample rank IC (non-overlapping)

| Horizon | Feature set | rank IC | t-stat | dir. acc | n (non-ovlp) |
|---|---|---:|---:|---:|---:|
| 1h | technical | **+0.0137** | **+3.76** | 0.506 | 76,970 |
| 1h | conditioning | −0.0021 | −0.26 | 0.497 | 76,970 |
| 1h | combined | +0.0038 | −0.26 | 0.501 | 76,970 |
| 4h | technical | +0.0164 | +1.21 | 0.504 | 19,242 |
| 1d | technical | +0.0206 | +1.99 | 0.504 | 3,207 |
| 1d | combined | +0.0079 | −0.31 | 0.504 | 3,207 |

Only the **technical** set has a positive OOS IC, and it is ~0.01–0.02. The 1h t-stat of
3.8 is "significant" only because n≈77k; the effect size (≈1.4% IC, 50.6% directional
accuracy) is trivial. The 38 macro/cross-asset **conditioning** features sit at ~0 and
**dilute** the technical signal when combined.

### 2. Classification (logistic direction)

| Horizon | accuracy | ROC AUC | F1 | base rate |
|---|---:|---:|---:|---:|
| 1h | 0.507 | 0.510 | 0.520 | 0.502 |
| 4h | 0.507 | 0.507 | 0.545 | 0.504 |
| 1d | 0.508 | 0.513 | 0.525 | 0.502 |

AUC ≈ 0.51 everywhere. Calibration is poor at the extremes (the predicted-0.9–1.0 bin
realizes < 0.50). No directional edge.

### 3. Confidence buckets (1h, combined Ridge)
Directional hit rate is **flat ~0.50** across predicted-magnitude quintiles — the
highest-confidence bucket (Q5) is *no* better than the middle. No usable conviction.

### 4. Transaction-cost-aware trading (combined Ridge, non-overlapping threshold rule)

| Horizon | Sharpe (gross) | Sharpe (net @0.5pip) | Profit factor | Cost drag |
|---|---:|---:|---:|---:|
| 1h | +0.016 | **−0.19** | 0.99 | **12.7× gross PnL** |
| 4h | −0.25 | −0.31 | 0.96 | 0.27× |
| 1d | +0.058 | +0.033 | 1.01 | 0.43× |

*Gross* Sharpe is already ≈0; 4h is negative even gross. After a realistic 0.5-pip one-way
cost, net Sharpe is ≤0 at 1h/4h and a negligible +0.03 at 1d. At 1h, cost drag is ~13× the
gross PnL — costs dominate exactly as the paper's TCA section warns.

**Fair test of the *only* set with signal:** trading the **technical-only** model (the one
with t=3.8) gives *gross* Sharpe −0.11 at 1h (its high-confidence trades are its worst) and
+0.036 at 1d (net +0.006). The detectable IC is **not monetizable**.

### 5. Benchmark — vs naive AUDUSD momentum (sign of `ret_12b`)

| Horizon | mom rank IC | mom Sharpe (net) |
|---|---:|---:|
| 1h | −0.021 | −2.30 |
| 4h | −0.014 | −1.25 |
| 1d | −0.013 | −0.50 |

Naive momentum is **negative** at these horizons — AUDUSD 15-min is mildly mean-reverting.
The model beats this bar, but the bar is unprofitable, so beating it means little.

### 6. Which features carry the (tiny) weight — 1h Ridge, standardized coefs
AU–US short-rate differential, US 2s10s slope, distance-from-MA (48/192 bar), realized
vol / ATR. Economically sensible (carry + mean-reversion/vol microstructure), magnitudes
tiny.

---

## Answers to the required questions

1. **Is there baseline predictive value?** Statistically yes at short horizons (technical
   rank IC ≈ 0.014, t ≈ 3.8 at 1h), economically **no** — net Sharpe ≤ 0 after costs.
2. **Which features matter most?** Intraday technicals: carry (rate) differential, MA
   distance, realized-vol/ATR. The macro/cross-asset conditioning block adds nothing
   intraday and dilutes signal.
3. **Most promising horizon?** 1-day — largest, most stable IC and least cost-dominated —
   but still net-flat.
4. **Stable out-of-sample?** No. Weak and unstable: flat confidence buckets, AUC ≈ 0.51,
   poor calibration, IC not robust across feature sets.
5. **Better than simple AUDUSD momentum?** Yes, but momentum is *negative* here, so it is a
   low, unprofitable bar.
6. **Proceed to regime modelling?** **Yes, as research — not with tradability expectations.**
   This baseline is the benchmark. Any regime/Hurst-conditioned model must be judged as a
   **net-of-cost** improvement over it, on the same overlap-aware, embargoed protocol.

---

## Caveats / honesty notes
- **Costs are a placeholder** (0.5-pip one-way). Real spread has not been pulled — the
  BID_ASK IBKR pass (CLAUDE.md gotcha #2) is still required before any PnL is trusted. The
  cost sweep (0 → 1 pip) is in `results/trading_metrics.csv`; the verdict is robust: even at
  **zero cost**, gross Sharpe is ≈0.
- Significance uses non-overlapping samples to avoid the inflated t-stats that overlapping
  12-bar labels would produce.
- `volume` is not real for FX and was not used.
- Reproduce everything: `python run_baseline.py --rebuild` (~4 min), then open
  `baseline_model.ipynb`.
