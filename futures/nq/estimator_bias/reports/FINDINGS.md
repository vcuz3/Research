# Findings — estimator bias in short-window persistence statistics

Evidence: `artifacts/runs/EXP-0001/` (`bias_table.txt`, `pooled_ac1_{NQ,ES}.txt`,
`hurst_gate_{NQ,ES}.txt`, `review.md`). Hypothesis: `experiments/hypotheses/HYP-0001.md`.
Core: `core/arbias.py`, `tests/test_core.py` (18 checks, all passing).

---

## A. Where the small-sample bias matters, and where it does not (EXP-0001, Study 1)

Status: **confirmed** (executable calibration, 20,000 draws per cell).

OLS on an AR(1) is pulled toward zero by Kendall's `-(1 + 3*phi)/T`. Measured at the
window lengths this workspace actually uses:

| T | what uses it | max abs bias over phi | sd(phi_hat) at phi=0.6 |
|---|---|---|---|
| 13 | one RTH session of 30-min decisions | **0.284** | 0.273 |
| 30 | the Hurst gate's FIRST decision window | **0.122** | 0.163 |
| 46 | one CME FX session | 0.079 | 0.128 |
| 90 | the standard same-slot lookback | 0.039 | 0.088 |
| 390 | the Hurst gate's LAST decision window | 0.009 | 0.041 |
| 3,710 | a per-session statistic over the sample | 0.0009 | 0.013 |
| 44,516 | `vei_exploration`'s pooled AC1 | **0.00025** | 0.0028 |

Two operational readings:

- **As inference this is a non-issue here.** Every headline IC/reversion statistic in this
  workspace pools 1e4-1e5 observations. Do not spend effort bias-correcting them.
- **The analytic formula itself fails at very small T.** It is accurate for T >= 30
  (measured vs predicted agree within 0.008) but at T = 13 it mispredicts badly — at
  phi = -0.4 it predicts +0.0154 against a measured +0.0001. **Below T ~ 20 use the
  parametric bootstrap corrector, not the closed form.** The two agree at T = 60 to within
  0.03 and diverge to 0.12 at T = 13.

**The quantity that carries the project:** the bias is a *deterministic function of the
window length*, so a feature whose window grows from 30 to 390 bars drifts by +0.03
(phi=0) to +0.11 (phi=0.8) from estimation alone — and its sampling **sd falls 3.9x** over
the same range. The sd effect is the larger one and it is what a fixed threshold reads.

## B. `vei_exploration`'s AC1: immune to the bias, but about half clock (EXP-0001, Study 2)

Status: **confirmed** (rule-23 reproduction exact; both markets agree).

Rule-23 reproduction: all 8 published cells to 1e-4 against the frozen
`vei_exploration/artifacts/runs/A_smoothing/smoothing_{NQ,ES}.csv`.

**Predicted null confirmed.** Bias correction moves the pooled AC1 by **at most 0.00006**
on either market (kill threshold 0.01). The estimator pools 40,806 within-session pairs;
§A says that is immune, and it is.

**The opposite-signed bias in the same statistic is large.** The published estimator pools
across decision slots, and VEI has a documented intraday level profile (0.745 -> 1.165).
Removing the per-slot mean first:

| variant | NQ pooled -> demeaned | ES pooled -> demeaned |
|---|---|---|
| `sma_10_50_raw` | -0.0112 -> **-0.1160** | -0.0151 -> **-0.1138** |
| `L:wilder_10_50` | +0.5495 -> **+0.2777** | +0.5062 -> **+0.2548** |
| `wilder_10_50` | +0.4411 -> **+0.2198** | +0.4036 -> **+0.2007** |
| `L:ema_10_50` | +0.1609 -> **+0.0048** | +0.1386 -> **+0.0002** |

**Roughly half of the persistence that motivated the Wilder estimator is the clock, and
the EMA variant's persistence is entirely clock.** The ranking wilder > ema > sma holds on
both markets, so `vei_exploration`'s estimator *choice* is unaffected; the *magnitude* of
"a much steadier regime read" should be halved.

Note the direction: pooling across a deterministic profile *inflates* a persistence
statistic, while small-sample bias *deflates* it. Both were live here; only one mattered,
and it was not the one the source article warns about.

## C. The `noise_vwap` Hurst gate is substantially a time-of-day selector (EXP-0001, Study 3)

Status: **confirmed on NQ and ES** for the calibration defect; the consequence for
`noise_vwap`'s per-trade claim is **provisional** (see below).

`noise_vwap/scripts/hyp_0017_hurst_filter.py:100` computes `H = ghe1(logp[:i+1])` — a
session-to-date expanding window, 30 bars at the mfo=29 decision and 390 at mfo=389 — then
applies a fixed `H_GRID` cut at every one.

**Primary metric — per-slot selection-rate CV vs a same-slot z of the same H at matched
global rate, on a common sample:**

| | min ratio | median | max | kill threshold |
|---|---|---|---|---|
| NQ | 2.88x | 23.93x | 45.59x | reject if <= 2.0x |
| ES | 5.90x | 21.75x | 46.48x | reject if <= 2.0x |

Not killed, at all 7 published thresholds, on both markets. For calibration the same-slot
z's own CV is 0.0025-0.0897, against the 0.060-0.064 that `vwap_exploration` finding I1
established as well-calibrated; the fixed cut runs 0.037-2.019.

**At the realistic operating point `H >= 0.55` the gate is 4.0x (NQ) / 6.1x (ES) more
likely to fire at 10:00 than at 15:59**, monotonically:

    NQ  0.335 0.294 0.260 0.242 0.212 0.188 0.169 0.145 0.136 0.121 0.109 0.095 0.084
    ES  0.317 0.268 0.226 0.197 0.166 0.144 0.122 0.106 0.095 0.083 0.073 0.064 0.052

**The mechanism is dispersion, not level.** Mean H moves by only 0.0225 (NQ) / 0.0203 (ES)
across the 13 windows, while sd compresses **3.80x / 3.54x** (0.176 -> 0.046). A fixed cut
in the tail of a distribution whose width collapses 3.8x must select a collapsing
fraction. Consistently, the CV ratio is *smallest* at `H >= 0.50` — nearest the
distribution's centre, where width matters least.

**The degenerate control decides it.** `signflip` — the session's real |returns| with iid
random signs, so real intraday volatility seasonality is preserved minute-by-minute and
memory is destroyed, true H = 0.50 by construction — reproduces the sd compression (3.64x
NQ / 3.70x ES) and produces a selection ramp of 0.330 -> 0.141 (NQ) / 0.333 -> 0.161 (ES)
on its own: **about half of the real gradient exists on a path with no memory at all.**
Even there, the fixed cut is 9.8-10.6x worse calibrated than a same-slot z of the same
feature. A constant-volatility fBm control (`fbm05`) gives the same answer, which rules
out volatility seasonality as the driver.

**A real residual does survive.** Late-session real H sits below both nulls
(real - signflip = -0.0100 NQ / -0.0286 ES at n=390), consistent with `hurst_explore` A2's
mild coarse-scale anti-persistence. It is an order of magnitude smaller than the estimator
gradient and cannot produce a monotone 4-6x ramp.

**Consequence for the standing claim (provisional).** `noise_vwap` records that "Hurst
LEVEL is a real per-trade quality signal (beats matched random NQ p=0.03)". That null
matched *count*, not *time of day*, and the gate preferentially fires in the morning —
where `noise_vwap` separately documents super-diffusion and the strongest part of its own
edge. **That claim should now be read as confounded with time of day and not separately
established.** It is not overturned: the repair is a slot-matched null, or a same-slot
z-scored H, and neither has been run. Nothing deployed is affected — the gate was already
rejected as selection (EXP-0026), exit conditioning (EXP-0027) and sizing (EXP-0028).

**Rule 9a.** The same-slot z comparator deletes decisions uniformly: per-slot coverage
0.9878 (NQ) / 0.9879 (ES), cross-slot spread **0.0000**. The comparator is not itself a
hidden filter.

---

## Reusable outputs

1. `core/arbias.py` — `ols_ar1`, `kendall_bias`/`kendall_correct`,
   `bootstrap_ar1_correct`, `pooled_lag1`(+`_slot_demeaned`), `ghe1`/`expanding_ghe1`,
   `causal_slot_stats`/`causal_slot_z`, `threshold_at_rate`,
   `per_slot_selection_rate`/`selection_rate_cv`. 18 invariant tests.
2. **The window-length table in §A** — consult before bias-correcting anything.
3. **The `signflip` null** — real volatility seasonality, zero memory. A strictly better
   degenerate control than constant-vol fBm for any intraday persistence question, and it
   is three lines.
4. **The selection-rate-CV diagnostic detects an estimator-induced clock**, not only a
   normalisation-induced one. Report it for any new thresholded feature.

## Not established

- Anything about instruments other than NQ/ES, or estimators other than `ghe1` and OLS
  AR(1). NQ+ES agreement on a correlated pair is corroboration, not replication.
- Whether the `noise_vwap` per-trade Hurst quality signal survives a slot-matched null.
  Open, and cheap to close.
- Cell C (`claude_exploration_1`'s reversion retention) was **bounded analytically rather
  than re-run** — a declared deviation from the preregistration. The bound (max possible
  movement 0.00025 at T=44,516) is two to three orders of magnitude below the published
  effects, but the direct reproduction was not executed.
