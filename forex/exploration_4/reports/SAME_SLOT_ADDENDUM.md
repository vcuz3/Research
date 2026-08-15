# Same-Slot Addendum — Stage A (EXP-0003)

Contract: `experiments/hypotheses/HYP-0003.md`, frozen before this run. Reproduce with
`python -u forex/exploration_4/_run_same_slot.py`.

**Numbering:** the run-book assigns EXP-0003 to Stage B; the ledger requires
`EXP-\d{4}`, so this addendum is EXP-0003 and **Stage B becomes EXP-0004**.

**Honest label (Stage-A repair F1):** this addendum re-runs the grain/threshold
selection on the SAME inspected 2012–2023 outcomes with a new normaliser. It is a
confound test and a reconstruction, **not independent confirmation**. τ\*=5 / H\*=240
remain **consumed-history, gross-P&L-selected candidates**; "confirmed under the
same-slot arm" below means the selection is stable to removing the clock confound, not
that it cleared a fresh holdout. Any inferential claim on the selected maximum needs a
full-pipeline null that repeats the selection. Only future data is a clean holdout now.

## Why

EXP-0002 measured `z = ret_τ / σ_τ` against an all-hours 28,800-minute σ. That window
cannot see the intraday volatility profile — median σ moves only 3.156→3.179 pips across
all 24 UTC hours at τ=5 — while actual bar sizes move a great deal. The fixed `|z| ≥ 2`
cut therefore fired on **0.96%** of decisions at 04:00 UTC and **10.11%** at 14:00
(**CV 0.707**). That is a threshold acting as a time-of-day selector.

Both arms are built on **one common decision sample** (bars where *both* σ estimators are
warmed up), so neither arm can look better merely by being defined on different rows.
Thresholds are **matched by picking a swept `k`**, never by interpolating a frontier —
`np.interp` clamps, which would silently turn a matched-rate comparison into an
extrapolation.

`gross_R_abs` is the cross-arm yardstick: mean R with **R = absolute σ_τ for both arms**.
Each arm's own-σ R is also carried in `surface.csv`, but own-R figures are not comparable
across arms.

---

## Q1 — Does the normaliser work?

Selection rate by UTC hour at τ=5, `abs` at k=2.0 vs `slot` at
k=2.14 (rate-matched), consumed history, percent of eligible decisions:

```text
 utc_hour  fire_rate_abs  fire_rate_slot
        0          2.677           3.691
        1          3.238           3.582
        2          2.009           3.669
        3          1.241           3.570
        4          0.898           3.824
        5          1.157           4.021
        6          3.557           4.078
        7          6.242           3.909
        8          6.168           3.709
        9          4.576           3.722
       10          3.842           3.838
       11          3.770           3.794
       12          4.050           2.371
       13          6.533           2.912
       14          8.147           3.164
       15          7.379           3.652
       16          4.268           3.916
       17          2.402           3.815
       18          1.810           2.696
       19          1.648           3.221
       20          1.163           3.840
       21          0.928           3.839
       22          1.089           3.699
       23          1.313           4.017
```

Cross-hour CV by grain and threshold:

```text
 tau  arm    k  signals  mean_rate  min_rate  max_rate     cv  max_over_min
   5  abs 2.00   118529     0.0334    0.0090    0.0815 0.6629        9.0712
   5 slot 1.50   302648     0.0862    0.0612    0.0993 0.1194        1.6226
   5 slot 2.00   153048     0.0437    0.0296    0.0495 0.1177        1.6756
   5 slot 2.14   126254     0.0361    0.0237    0.0408 0.1195        1.7202
   5 slot 2.50    79123     0.0226    0.0144    0.0270 0.1335        1.8741
   5 slot 3.00    43722     0.0125    0.0075    0.0161 0.1694        2.1419
  15  abs 2.00    40609     0.0343    0.0074    0.0850 0.6959       11.5116
  15 slot 1.50   100626     0.0865    0.0657    0.1001 0.1238        1.5235
  15 slot 2.00    50035     0.0431    0.0318    0.0487 0.1118        1.5322
  15 slot 2.12    42373     0.0365    0.0263    0.0410 0.1092        1.5556
  15 slot 2.50    25774     0.0222    0.0157    0.0250 0.0998        1.5916
  15 slot 3.00    14212     0.0123    0.0082    0.0149 0.1241        1.8287
  30  abs 2.00    22546     0.0387    0.0093    0.1040 0.7264       11.1856
  30 slot 1.50    50573     0.0907    0.0553    0.1396 0.1745        2.5265
  30 slot 2.00    25687     0.0461    0.0270    0.0731 0.1755        2.7035
  30 slot 2.10    22444     0.0403    0.0249    0.0640 0.1718        2.5767
  30 slot 2.50    13427     0.0243    0.0170    0.0419 0.1828        2.4728
  30 slot 3.00     7587     0.0139    0.0106    0.0263 0.2179        2.4855
  60  abs 2.00    11680     0.0409    0.0031    0.1124 0.7294       35.9178
  60 slot 1.50    24569     0.0908    0.0159    0.1920 0.3329       12.0415
  60 slot 2.00    12447     0.0465    0.0089    0.1100 0.3577       12.3053
  60 slot 2.06    11509     0.0432    0.0089    0.1039 0.3610       11.6217
  60 slot 2.50     6655     0.0249    0.0049    0.0586 0.3556       11.9178
  60 slot 3.00     3779     0.0144    0.0028    0.0392 0.4335       13.8419
 120  abs 2.00     5497     0.0419    0.0073    0.0974 0.7121       13.3327
 120 slot 1.50    11152     0.0875    0.0350    0.1218 0.2777        3.4771
 120 slot 2.00     5550     0.0444    0.0162    0.0699 0.2972        4.3032
 120 slot 2.50     2889     0.0240    0.0095    0.0472 0.3697        4.9441
 120 slot 3.00     1579     0.0137    0.0054    0.0330 0.4926        6.1526
```

**abs CV = 0.663 → slot CV = 0.119**
(pass threshold 0.25). **normaliser works; Q2/Q3 interpretable**

## Q2 — Was the thin-hours localisation real, or was it the clock?

τ=5, H=240, **delay-1 arm**, at matched firing rate. The pre-committed rule: the
localisation survives only if `off` or `asia` still exceeds `london` by more than the
sum of the two cells' 95% CI half-widths.

```text
session  arm      n  gross_R_abs  gross_R_abs_ci_low  gross_R_abs_ci_high  gross_R_abs_t  gross_pips
    all  abs 111023       0.0651              0.0036               0.1265         2.0755      0.2435
    all slot 110124       0.1056              0.0448               0.1663         3.4065      0.3834
   asia  abs  16689       0.2300              0.0856               0.3743         3.1224      0.8858
   asia slot  33255       0.2066              0.1143               0.2988         4.3892      0.8736
 london  abs  35720      -0.0440             -0.1584               0.0705        -0.7528     -0.2257
 london slot  27396       0.0206             -0.1155               0.1568         0.2971      0.0035
     ny  abs   9124       0.1171             -0.0618               0.2961         1.2827      0.3981
     ny slot  11427       0.1032             -0.0443               0.2506         1.3708      0.3510
    off  abs  12061       0.3832              0.1955               0.5710         4.0015      1.5024
    off slot  21238       0.1896              0.0611               0.3181         2.8920      0.7004
overlap  abs  37429      -0.0196             -0.1302               0.0910        -0.3473     -0.0384
overlap slot  16808      -0.0603             -0.2496               0.1290        -0.6240     -0.3458
```

```json
{
  "abs": {
    "k": 2.0,
    "cells": {
      "off": {
        "n": 12061,
        "gross_R_abs": 0.38323788290020666,
        "ci_low": 0.19552252371839735,
        "ci_high": 0.570953242082016,
        "half_width": 0.18771535918180937
      },
      "asia": {
        "n": 16689,
        "gross_R_abs": 0.2299528287555477,
        "ci_low": 0.08560579811041102,
        "ci_high": 0.3742998594006844,
        "half_width": 0.14434703064513668
      },
      "london": {
        "n": 35720,
        "gross_R_abs": -0.04396151965215104,
        "ci_low": -0.15841717131016278,
        "ci_high": 0.07049413200586069,
        "half_width": 0.11445565165801172
      }
    },
    "vs_london": {
      "off": {
        "gap": 0.4271994025523577,
        "combined_half_width": 0.3021710108398211,
        "exceeds": true
      },
      "asia": {
        "gap": 0.27391434840769874,
        "combined_half_width": 0.2588026823031484,
        "exceeds": true
      }
    },
    "localisation_survives": true
  },
  "slot": {
    "k": 2.14,
    "cells": {
      "off": {
        "n": 21238,
        "gross_R_abs": 0.18959729282318913,
        "ci_low": 0.06110174408829527,
        "ci_high": 0.318092841558083,
        "half_width": 0.12849554873489386
      },
      "asia": {
        "n": 33255,
        "gross_R_abs": 0.20657941279028236,
        "ci_low": 0.11433175599611049,
        "ci_high": 0.2988270695844542,
        "half_width": 0.09224765679417185
      },
      "london": {
        "n": 27396,
        "gross_R_abs": 0.02064294561442528,
        "ci_low": -0.11552698765336672,
        "ci_high": 0.1568128788822173,
        "half_width": 0.136169933267792
      }
    },
    "vs_london": {
      "off": {
        "gap": 0.16895434720876384,
        "combined_half_width": 0.26466548200268586,
        "exceeds": false
      },
      "asia": {
        "gap": 0.18593646717585707,
        "combined_half_width": 0.22841759006196385,
        "exceeds": false
      }
    },
    "localisation_survives": false
  },
  "outcome": "thin-hours localisation is NOT ESTABLISHED under the same-slot normalisation: the EXP-0002 session breakdown is retracted as an actionable prior. The clock-artifact ATTRIBUTION is PROVISIONAL (this screen compares a gap to the sum of two marginal half-widths, not a difference CI; see the clustered contrast for the proper test)",
  "matching_departure": "HYP-0003 \u00a74 specifies matching at a per-hour firing rate; choose_matched_k matches ONE pooled crossing rate across all hours (matched total count). Sensible, but a declared departure from the frozen contract, not 'no departures'.",
  "clustered_conclusion": "Proper UTC-day-clustered difference (slot arm): off\u2212london +0.169 CI[-0.023,+0.361] (includes 0); asia\u2212london +0.186 CI[+0.019,+0.353] (excludes 0). Normalising SHRINKS both gaps versus the confounded abs arm (off +0.427\u2192+0.169, asia +0.274\u2192+0.186), so the clock explained most of off's apparent localisation and part of asia's. What remains is a MARGINAL asia gap on INSPECTED history, one of several contrasts, without the arm-by-session interaction Codex asked for. Verdict: off\u2212london not established; asia\u2212london provisional and NOT actionable yet \u2014 it is the motivation for the axis-4 session test (full pipeline), not a prior to fold into an overlay now."
}
```

**thin-hours localisation is NOT ESTABLISHED under the same-slot normalisation: the EXP-0002 session breakdown is retracted as an actionable prior. The clock-artifact ATTRIBUTION is PROVISIONAL (this screen compares a gap to the sum of two marginal half-widths, not a difference CI; see the clustered contrast for the proper test)**

### Proper UTC-day-clustered difference contrast (F3)

The screen above compares a session gap to the **sum of two marginal CI half-widths** —
a deliberately conservative heuristic, not a confidence interval for the difference, and
blind to the covariance between two session estimators that share a UTC day. The correct
test is a UTC-day-clustered CI on the difference itself (`off − london`, `asia − london`),
influence functions subtracted within each cluster. Both arms shown; the `slot` arm is the
decision arm.

```json
{
  "tau": 5,
  "horizon_minutes": 240,
  "note": "UTC-day-clustered CI for the difference in mean gross_R_abs; captures same-day covariance, unlike the sum-of-half-widths screen",
  "slot": {
    "off_minus_london": {
      "a": "off",
      "b": "london",
      "diff": 0.16895434720876387,
      "se": 0.0978077924593324,
      "ci_low": -0.022748926011527615,
      "ci_high": 0.36065762042905536,
      "n_a": 21238,
      "n_b": 27396,
      "clusters": 3665
    },
    "asia_minus_london": {
      "a": "asia",
      "b": "london",
      "diff": 0.1859364671758571,
      "se": 0.08507378643611754,
      "ci_low": 0.019191845761066723,
      "ci_high": 0.3526810885906475,
      "n_a": 33255,
      "n_b": 27396,
      "clusters": 3100
    }
  },
  "abs": {
    "off_minus_london": {
      "a": "off",
      "b": "london",
      "diff": 0.42719940255235783,
      "se": 0.11298195446546619,
      "ci_low": 0.20575477180004412,
      "ci_high": 0.6486440333046716,
      "n_a": 12061,
      "n_b": 35720,
      "clusters": 3509
    },
    "asia_minus_london": {
      "a": "asia",
      "b": "london",
      "diff": 0.27391434840769874,
      "se": 0.09680946643560806,
      "ci_low": 0.08416779419390694,
      "ci_high": 0.4636609026214905,
      "n_a": 16689,
      "n_b": 35720,
      "clusters": 3103
    }
  }
}
```

**Proper UTC-day-clustered difference (slot arm): off−london +0.169 CI[-0.023,+0.361] (includes 0); asia−london +0.186 CI[+0.019,+0.353] (excludes 0). Normalising SHRINKS both gaps versus the confounded abs arm (off +0.427→+0.169, asia +0.274→+0.186), so the clock explained most of off's apparent localisation and part of asia's. What remains is a MARGINAL asia gap on INSPECTED history, one of several contrasts, without the arm-by-session interaction Codex asked for. Verdict: off−london not established; asia−london provisional and NOT actionable yet — it is the motivation for the axis-4 session test (full pipeline), not a prior to fold into an overlay now.**

The sum-of-half-widths screen (above) is strictly more conservative than this difference CI;
where the two disagree, the difference CI is the correct test. It clears zero for `asia` and
not for `off`, so the clean "both retracted" reading from the screen is too strong. The
economics are unchanged either way: gross stays ~3× under cost, and a thin-hour like `asia`
carries a mechanical R_slot lift (its σ_slot is small), so a positive `asia` R gap is exactly
what the busy/thin-hour σ structure predicts and is not by itself evidence of tradable edge.

**Departure from the frozen contract:** HYP-0003 §4 specifies matching at a per-hour firing rate; choose_matched_k matches ONE pooled crossing rate across all hours (matched total count). Sensible, but a declared departure from the frozen contract, not 'no departures'.

## Q3 — Does the grain choice survive?

**Primary ranking: fixed preregistered horizon H\*=240** (HYP-0003 §4).
Ladder ranked by `gross_R_abs`, `slot` arm, delay-1, each rung at its own rate-matched
`k`, **no horizon searched**:

```text
 tau    k  gross_R_abs  horizon_minutes      n  ci_low  ci_high
   5 2.14       0.1056              240 110124  0.0448   0.1663
  15 2.12       0.0498              240  36737 -0.0108   0.1104
  30 2.10      -0.0171              240  19315 -0.0780   0.0438
  60 2.06      -0.0181              240   9420 -0.0757   0.0395
 120 2.00      -0.0428              240   4387 -0.1043   0.0186
```

**tau*=5 CONFIRMED under same-slot normalisation at fixed H*=240**

*Robustness only (not the decision):* the same ladder ranked by the **best of horizons
{60, 240}** — a two-horizon search that can only flatter a grain by picking its better
horizon. It ranks [5, 15, 60, 30, 120] with top τ=5. This is
reported for transparency; the grain decision rests on the fixed-H\* table above.

```text
 tau    k  gross_R_abs  horizon_minutes      n  ci_low  ci_high
   5 2.14       0.1056              240 110124  0.0448   0.1663
  15 2.12       0.0498              240  36737 -0.0108   0.1104
  30 2.10      -0.0040               60  21448 -0.0324   0.0243
  60 2.06       0.0047               60  10669 -0.0234   0.0328
 120 2.00      -0.0156               60   5138 -0.0442   0.0130
```

### Full ladder, both arms side by side (delay-1, rate-matched)

```text
 tau  arm    k  horizon_minutes      n  gross_R_abs  gross_R_abs_t  gross_pips  cost_pips_base
   5  abs 2.00               60 117456       0.0601         3.7967      0.1941          1.1329
   5 slot 2.14               60 121743       0.0612         4.3848      0.2111          1.1776
   5  abs 2.00              240 111023       0.0651         2.0755      0.2435          1.1380
   5 slot 2.14              240 110124       0.1056         3.4065      0.3834          1.1961
  15  abs 2.00               60  40214       0.0272         1.7217      0.1530          1.1191
  15 slot 2.12               60  40750       0.0200         1.3894      0.1506          1.1628
  15  abs 2.00              240  37927       0.0146         0.4542      0.0750          1.1244
  15 slot 2.12              240  36737       0.0498         1.6115      0.3903          1.1811
  30  abs 2.00               60  22265      -0.0028        -0.1779     -0.0462          1.1092
  30 slot 2.10               60  21448      -0.0040        -0.2794     -0.0934          1.1535
  30  abs 2.00              240  20778      -0.0186        -0.6050     -0.2316          1.1162
  30 slot 2.10              240  19315      -0.0171        -0.5498     -0.2082          1.1715
  60  abs 2.00               60  11174       0.0005         0.0361     -0.0314          1.0949
  60 slot 2.06               60  10669       0.0047         0.3282      0.0085          1.1390
  60  abs 2.00              240  10190      -0.0473        -1.5852     -0.4272          1.1049
  60 slot 2.06              240   9420      -0.0181        -0.6154     -0.1791          1.1598
 120  abs 2.00               60   5251      -0.0172        -1.2254     -0.3448          1.0992
 120 slot 2.00               60   5138      -0.0156        -1.0687     -0.2196          1.1346
 120  abs 2.00              240   4137      -0.0600        -1.8783     -0.6494          1.1339
 120 slot 2.00              240   4387      -0.0428        -1.3658     -0.4184          1.1580
```

## Q4 — Does normalising destroy the information?

Compared at matched firing rate, same risk unit, delay-1, τ=5:

```json
{
  "abs": {
    "n": 111023,
    "horizon_minutes": 240,
    "gross_R_abs": 0.06507436949813895,
    "gross_pips": 0.24351564540681123,
    "cost_pips_base": 1.138005175000098,
    "ci_low": 0.003621410268292845,
    "ci_high": 0.12652732872798506
  },
  "slot": {
    "n": 110124,
    "horizon_minutes": 240,
    "gross_R_abs": 0.10558788343798566,
    "gross_pips": 0.3834251616359732,
    "cost_pips_base": 1.1961326276984214,
    "ci_low": 0.04483648078407933,
    "ci_high": 0.16633928609189197
  },
  "slot_minus_abs_R": 0.0405135139398467,
  "note": "compared at matched firing rate on the common decision sample; gross_R_abs uses the SAME (absolute sigma) risk unit for both arms"
}
```

Read `gross_pips` against `cost_pips_base`: the breakeven round-trip pip is the number
that decides deployability, and renormalising a threshold cannot move a ~0.4-pip gross
edge past a ~1.2-pip round trip.

## Limitations

- UTC slots do not track DST, so a slot's meaning shifts by an hour twice a year against
  London and New York local time, blending two adjacent hours' volatility for part of the
  year. Documented, not corrected.
- The slot estimator warms up ~90 sessions later than the all-hours one. Handled by the
  common-sample construction rather than by ignoring it.
- 2024+ remains sealed; nothing here reads it.
