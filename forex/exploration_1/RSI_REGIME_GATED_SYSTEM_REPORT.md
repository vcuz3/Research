# Regime-gated mean-reversion system — component test

> **SUPERSEDED IN PART — 2026-08-04.** Component 2 (the vol-scaled exhaustion
> threshold) is **rejected** by `RSI_THRESHOLD_FRESHNESS_REPORT.md`. The
> comparison below ran the vol-scaled and fixed triggers at **632 and 1,724
> signals per year**, so it could not separate the volatility scaling from a
> deeper cut. At matched selection rate the scaling is **worse** than a plain
> fixed threshold: −0.241 pip on the trigger alone (0 of 4 pairs improved) and
> −0.172 pip with the expansion gate stacked (1 of 4). The +0.060 pip gain
> reported in the Verdict table and in §1 is **retracted**, and Decision item 1
> should read "component 1 with a fixed threshold". Rows 0/1 and 2 of the §1
> ablation remain correct as measurements; it is their comparison that is void.
>
> The mechanism: all three threshold rules tested carry the same edge per unit of
> risk (≈0.10 R) and differ only in the volatility of the states they select, so
> the pips-per-signal ranking was a risk-unit ranking. Report mean R alongside
> mean pips for every trigger comparison in this project.
>
> Components 1, 3, 4 and 5 are unaffected.

## Verdict

An externally proposed five-component system was implemented as specified and
tested by ablation, then by feature definition, normalisation, and era split.

**Two components work and survive the era split; three do not.**

| Component | Verdict |
|---|---|
| 1. Expansion phase (VEI) | **Works.** Best as **ATR(14)/ATR(50), same-slot z-score, top 40%**: 0.827 pips/signal against 0.648 ungated, per-signal Sharpe 0.073 → 0.085, 4/4 pairs positive, and it improves the late era (0.572 → 0.735). |
| 2. Vol-scaled exhaustion threshold | **Works.** `z < −1.5 × (1 + vol percentile)` lifts 0.588 → 0.648 pips and per-signal Sharpe 0.058 → 0.073 against a fixed cut. |
| 3. Rolling kurtosis tail filter | **Rejected.** Intraday: destroys the signal (t 6.57 → 1.74). Daily: helps in the early era (+0.10) and **hurts in the late era (−0.13)**. |
| 4. Vol-of-vol structural filter | **Rejected at every scale tested** — intraday 60/120/390 min and daily 20/60/250 sessions, raw/percentile/z, six keep rates each. Delta negative in essentially all cells. |
| 5. Dynamic z-breach stop | **Rejected.** 0.538 → 0.293 pips, t 1.07. Its apparent gain was a one-bar lookahead (see §2). |

Best surviving configuration is **components 1 + 2 only**. It beats the plain RSI
30/70 baseline by +41% per signal and +47% on per-signal Sharpe, but trades a third
as often, so annual net is slightly lower (138 against 149 pips). It remains
cost-bound: net per signal is +0.63 at a 0.2 pip round trip, +0.33 at 0.5, and
**−0.17 at 1.0**.

This is the first component-level improvement anything in this project has
produced. It is not a deployable result.

## Data period and setup

**2012-01-02 02:29 UTC to 2023-12-29 19:59 UTC.** One-minute midpoint OHLC for
EURUSD, GBPUSD, AUDUSD, NZDUSD; approximately 130,500 decisions per pair. New York
17:00 session boundary, decisions on completed half-hours at `:29`/`:59`, entry at
the next one-minute open, exit at the open exactly 30 minutes later. Era split
2021-01-01: early = 2012-2020, late = 2021-2023. **2024+ remains sealed** and was
not touched.

All history used here is consumed. Nothing below is a holdout result, and the
early era is nine of the twelve years, so it dominates any pooled statistic — a
fact that turns out to matter in §4.

## Feature definitions

**Exhaustion trigger.** `z = (log P − log EMA20) / sd`, where `EMA20` is a
20-period EMA of one-minute closes and `sd` is the rolling 120-minute standard
deviation of the displacement series, gap-exact. Entry when
`z ≤ −1.5 × (1 + vol_pct)` for longs and the mirror for shorts, where `vol_pct` is
the causal same-slot percentile of trailing 30-minute realized volatility over 90
prior sessions.

**Expansion.** Two definitions, tested against each other:

- `vei_rv = (RV(10)/√10) / (RV(50)/√50)` — per-minute normalised, see §2;
- `vei_atr = ATR(14)/ATR(50)`, Wilder recursion seeded per contiguous segment.

Each in three forms: raw level, causal same-slot percentile (90 sessions), causal
same-slot z-score (90 sessions).

**Daily-scale features.** Last one-minute close per New York session → daily log
return, and daily RV = `√Σ r²` over the session. Then `rolling(N).kurt()` or
`.std()` with `min_periods = 2N/3`, `.shift(1)` for causality, `+3` to put
kurtosis on the non-excess scale. Percentile and z-score computed over a trailing
250-session window, prior sessions only. `N ∈ {20, 60, 250}`.

Note a daily feature is constant within a session, so its same-slot percentile is
identical to a plain rolling percentile at every slot; the rolling form is used.

**Matched selection rates.** Every gate is compared at identical keep rates
(0.80/0.60/0.50/0.40/0.30/0.20). A filter evaluated at its own natural threshold
is a selectivity dial, not a result.

## 1. Component ablation (median across four pairs)

| Config | signals/yr | mean pips | t | per-signal Sharpe | net @0.5 | annual net @0.5 |
|---|---:|---:|---:|---:|---:|---:|
| 0/1 fixed z threshold | 1724 | 0.588 | 8.69 | 0.058 | 0.088 | **149** |
| 2 + vol-scaled threshold | 632 | 0.648 | 6.41 | 0.073 | 0.148 | 97 |
| 3 + expansion (VEI_rv > 1) | 499 | **0.710** | 6.57 | **0.080** | 0.210 | 106 |
| 4 + intraday kurtosis < 4.5 | 77 | 0.552 | 1.74 | 0.058 | 0.052 | 5 |
| 5 + vol-of-vol pct < 0.85 | 76 | 0.538 | 1.68 | 0.057 | 0.038 | 4 |
| 6 + dynamic z stop | 76 | 0.293 | 1.07 | 0.033 | −0.207 | −19 |

Components 2 and 3 each add. Components 3→4 is the collapse: the intraday kurtosis
veto cuts signals 6.5x and takes the t-statistic from 6.57 to 1.74.

## 2. Two implementation defects found, both worth recording

**Realized volatility ratios need per-minute normalisation.** RV over `w` minutes
scales as `√w`, so a raw `RV(10)/RV(50)` sits at `√(10/50) ≈ 0.447` by
construction. The specified gate `VEI > 1` therefore selected **zero rows** on all
four pairs, and every downstream cell was empty. After normalising each leg to a
per-minute rate the median is 0.93 and ~40% exceed 1. An ATR ratio does not have
this problem because ATR is already a per-bar average — which is a reason to
prefer it beyond the performance result in §3.

**The dynamic stop had a one-bar lookahead, and it was the entire result.** `z` at
a bar is known only at that bar's close, so a breach observed at bar `k` can only
be executed at the open of `k + 1`. Indexing the exit price at `k` credits an
impossible fill (rule 2). Before the fix the full system printed **1.346 pips,
t 5.88, per-signal Sharpe 0.179**; after the fix, **0.293 pips, t 1.07, Sharpe
0.033**. The entire apparent gain was one bar of hindsight. This is the fill-
feasibility rule biting on an exit rather than an entry.

## 3. Expansion gate: definition and normalisation, at matched keep rate

Spearman correlation between the two expansion definitions is only **0.464 to
0.498**. They are not two versions of the same feature.

| Variant | keep | mean pips | t | per-signal Sharpe | annual net @0.5 | pairs +ve |
|---|---:|---:|---:|---:|---:|---:|
| no expansion gate | 1.00 | 0.648 | 6.41 | 0.073 | 97 | 3/4 |
| **vei_atr slot z** | **0.40** | **0.827** | 6.23 | **0.085** | **138** | **4/4** |
| vei_atr slot pct | 0.40 | 0.800 | 6.02 | 0.084 | 127 | 4/4 |
| vei_atr raw | 0.40 | 0.719 | 5.92 | 0.077 | 103 | 4/4 |
| vei_rv raw | 0.40 | 0.707 | 6.55 | 0.080 | 104 | 4/4 |
| vei_rv slot pct | 0.40 | 0.682 | 6.13 | 0.077 | 88 | 4/4 |
| vei_rv slot z | 0.40 | 0.678 | 6.09 | 0.077 | 85 | 4/4 |

**ATR beats RV at every matched keep rate**, on mean pips, per-signal Sharpe and
annual net.

**Slot normalisation is not universally beneficial, and that is the reusable
finding here.** It *helps* the ATR ratio (0.719 → 0.827 at keep 0.40) and *hurts*
the RV ratio (0.707 → 0.678). This workspace's standing repair — slot-normalise a
thresholded feature — is a fix for a time-of-day drift in the raw feature; where
the raw feature does not carry one, the normalisation only adds estimation noise.
Check for the drift before applying the repair rather than applying it by default.

At the tightest keep rate (0.20) the three ATR forms converge (0.856-0.864), so
the normalisation matters in the middle of the distribution and not in the tail.

## 4. Kurtosis: the threshold was specified for the wrong timescale, and the fix does not survive the era split

The calibration diagnostic explains the intraday collapse in one line:

| Statistic | median | fraction > 4.5 |
|---|---:|---:|
| 30-minute kurtosis | 3.52-3.81 | 26-35% |
| **390-minute kurtosis** | **5.25-6.26** | **54-64%** |
| Daily, 60 sessions | 3.18-3.60 | 9-22% |
| Daily, 250 sessions | 3.58-4.28 | — |

**On intraday returns 4.5 sits below the median**, so `kurtosis < 4.5` is not a
rare-tail veto — it discards most of the sample. On daily returns the median is
3.18-3.60 and 4.5 is a genuine tail threshold, which is what the proposal
intends. The specification is coherent; it was being applied to a statistic whose
distribution is nothing like the one it assumes.

Tested at daily scale on top of the ATR expansion gate, daily kurtosis appeared to
help — the z-score form at 60 and 250 sessions gave **+0.11 to +0.18 pips** with
3/4 pairs improved, against a base of 0.800.

**That result does not survive the era split.**

| Config | early mean | early t | late mean | late t |
|---|---:|---:|---:|---:|
| trigger only | 0.670 | 5.84 | 0.572 | 2.66 |
| + ATR-VEI top 40% | 0.811 | 5.29 | **0.735** | 2.59 |
| + daily kurt60 filter | 0.908 | 4.09 | **0.602** | 2.06 |

The daily kurtosis filter **adds +0.10 in the early era and subtracts −0.13 in the
late era**. Because the early era is nine of the twelve years, it dominated the
pooled statistic and produced a confident wrong reading. The pooled "+0.088, 3/4
pairs" is retracted; daily kurtosis is rejected pending different evidence.

This is the same failure mode as `ai_shared_memory/LEARNINGS.md` 2026-08-03: a
result that exists only in the sample that generated it. The era split cost one
extra column and reversed the verdict.

## 5. Vol-of-vol

Tested at intraday windows 60/120/390 minutes and daily windows 20/60/250
sessions, in raw, percentile and z-score form, at six keep rates each — 54 daily
cells plus 9 intraday. Delta against base is **negative in essentially every
cell**, with the three trivially positive exceptions (+0.001 to +0.015) at 2/4
pairs or fewer. The component is rejected across timescales and normalisations.

## 6. Era split of the surviving system

| Config | era | signals/yr | mean pips | t | per-signal Sharpe | net @0.5 |
|---|---|---:|---:|---:|---:|---:|
| trigger only | early | 640 | 0.670 | 5.84 | 0.076 | 0.170 |
| | late | 589 | 0.572 | 2.66 | 0.063 | 0.072 |
| + ATR-VEI top 40% | early | 428 | 0.811 | 5.29 | 0.083 | 0.311 |
| | late | 371 | **0.735** | 2.59 | 0.076 | 0.235 |

The expansion gate is the only component that improves the late era. Per pair in
the late era it is uneven — the weakest cell (NZDUSD, with the daily filter
stacked) falls to 0.345 pips, net −0.155 at a 0.5 pip cost.

## Scorecard against the proposal

| Claim | Status |
|---|---|
| Normalise displacement by dynamic volatility before evaluating stretch | **Supported.** Vol-scaled threshold lifts per-signal Sharpe 0.058 → 0.073. |
| Vol-percentile scaling of the entry threshold | **Supported**, as above. |
| Expansion phase confirms the market is moving, not dead | **Supported**, and stronger with ATR than RV. |
| High kurtosis means stretched prices stay stretched | **Not supported.** Intraday destroys the signal; daily helps only in the generating era. |
| Vol-of-vol proxies structural regime shift | **Rejected** at every scale and normalisation tested. |
| Dynamic stop on z-breach | **Rejected.** Consistent with the separate finding that winners and losers are the same size (±0.9 R), so barrier truncation cuts both. |

## Limitations

- **All history consumed**; 2024+ sealed but untouched. Nothing here is a holdout
  result, and the surviving configuration was selected after inspecting the grid.
- **Selection.** Six expansion variants × six keep rates were searched. The
  winning cell is a maximum over 36 configurations plus the daily sweeps; the
  reported t-statistics are not corrected for that search.
- **Cost is assumed, never measured.** The verdict flips between +0.63 and −0.17
  per signal across a plausible cost range. This remains the single highest-value
  missing input in the project.
- **Midpoint bars**, no bid/ask model, and decisions concentrate at half-hour
  boundaries where spreads are least favourable.
- **No null** (rule 17) on any arm here.
- **Effective sample.** AUDUSD/NZDUSD and EURUSD/GBPUSD are correlated, so "4/4
  pairs" is nearer two or three independent agreements.
- The late era is only three years, so its t-statistics (2.6) are not strong
  evidence on their own.

## Decision

1. **Carry components 1 and 2 only.** `z < −1.5 × (1 + vol_pct)` with an
   ATR(14)/ATR(50) same-slot z-score expansion gate at a top-40% keep rate.
2. **Drop components 3, 4 and 5.** Kurtosis fails the era split, vol-of-vol fails
   at every scale, and the stop's gain was lookahead.
3. **Prefer ATR to RV for expansion ratios**, and check for a time-of-day drift in
   the raw feature before slot-normalising it — the normalisation helped one
   definition and hurt the other.
4. **Measure the bid/ask round trip** before any further work on this system.
5. Do not treat the surviving configuration as validated. It is a post-hoc
   maximum on consumed history that clears its own era split at t ≈ 2.6.
6. **2024+ stays sealed.**

## Evidence

- Ablation and intraday sweeps: `_run_rsi_regime_gated_system.py` →
  `rsi_regime_gated_system_results.json`, `rsi_regime_gated_ablation.csv`,
  `rsi_regime_gated_kurtosis_sweep.csv`, `rsi_regime_gated_vov_sweep.csv`
- Definition, normalisation and era split: `_run_rsi_regime_gated_followup.py` →
  `rsi_regime_gated_followup_results.json`, `rsi_followup_vei_variants.csv`,
  `rsi_followup_daily_variants.csv`, `rsi_followup_era_split.csv`
- Related: `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` (Arms 0 and 2, P&L
  distribution, stop and take-profit sweeps),
  `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md`, `RSI_CLOCK_CONFOUND_REPORT.md`
- Reproduce with `python -u _run_rsi_regime_gated_system.py` and
  `python -u _run_rsi_regime_gated_followup.py` from `forex/exploration_1`.
