# RSI mean-reversion programme — Arms 0 and 2, plus P&L distribution and economics

> **AMENDMENT — 2026-08-04.** Arm 1's feature families were subsequently tested
> properly in `RSI_REGIME_GATED_SYSTEM_REPORT.md`, at intraday windows
> (30/60/120/390 min) and daily windows (20/60/250 sessions), in raw, percentile
> and z-score form, at matched selection rates. Conclusions that supersede the
> limitations noted below: **kurtosis is rejected** — intraday it destroys the
> signal, and the daily version helps in the early era (+0.10) but hurts in the
> late era (−0.13), so the pooled improvement was generating-sample-driven.
> **Vol-of-vol is rejected** at every scale and normalisation tested. Arm 3
> (vol-adaptive thresholds) is **supported**: a vol-percentile-scaled threshold
> lifts per-signal Sharpe 0.058 → 0.073, and an ATR(14)/ATR(50) expansion gate
> lifts it further to 0.085. The "untested, family remains open" language below
> should be read as closed for kurtosis and vol-of-vol.
>
> Data period for all of this work: **2012-01-02 to 2023-12-29**, ~130,500
> decisions per pair, era split 2021-01-01, 2024+ sealed.

## Verdict

Not viable at the tested configuration, and **the surface is not exhausted**. This
is a qualified negative on a narrow slice, not a closed line.

1. **Arm 0 (entry delay).** Delaying entry and exit by one minute retains 70% of
   the volatility-regime gradient and 67% of the reversion level, so the effect is
   not majority first-traded-minute — a better outcome than the clock work
   suggested. But it retains only **53% of Q5 gross P&L** (0.941 → 0.503 pip).
   About half the tradable edge at the canonical settings sits in the single
   minute at the `:00`/`:30` open.
2. **Arm 2 (continuation).** The loss mechanism is confirmed and is the dominant
   fact about this strategy: 6.0-7.5% of signals persist past the next checkpoint
   and lose 8.3-12.4 pip. At the distribution level the **worst 1% of trades
   remove 52-79% of total gross P&L** and the worst 5% remove 150-210%. Of eight
   decision-time separators tested, two survive multiplicity correction with
   consistent sign — RSI depth and the canonical RV(30) percentile — at AUC ~0.54
   and 0.46. The two volatility-structure features tested, **30/60-minute rolling
   kurtosis and 60-minute vol-of-vol, do not separate at those windows**. Longer
   memories were not tested; see limitations.
3. **Economics.** Per-signal Sharpe *falls* monotonically with horizon
   (0.108 at 5 min to 0.029 at 480 min) while net P&L *rises*, because a fixed
   round-trip cost is amortised over a larger move. Viability is therefore almost
   entirely a cost question: workable across much of the grid at 0.2 pip,
   workable at long horizons at 0.5 pip, essentially dead at 1.0 pip.

Arms 1 and 3 remain **open**, not closed. Arm 2 tested two specific windows of two
of Arm 1's candidates; it did not test the feature families.

## Specification amendment (disclosed)

`RSI_MEAN_REVERSION_PROGRAMME_SPEC.md` set Arm 2's kill test as "no candidate
reaches an out-of-sample AUC meaningfully above 0.50" without defining
*meaningfully*. After the first execution, two conditions were added: a
Benjamini-Hochberg correction across the full 4-pair × 8-feature scan, and a
requirement that a separator point the same way on all four pairs.

Decided after seeing output; recorded as an amendment, not as a frozen condition.
It makes the gate stricter — under raw CI exclusion alone 7 of 32 tests passed
against ~1.6 expected by chance.

## Frozen setup

Unchanged from `RSI_BROAD_REGIME_SWEEP_SPEC.md`: EURUSD, GBPUSD, AUDUSD, NZDUSD
one-minute midpoint OHLC, 2012-2023; New York 17:00 session boundary; decisions on
completed half-hours at `:29`/`:59`; entry at the next one-minute open; era split
2021-01-01; 2024+ sealed and untouched. Regime variable `rv_30m_pct_90d` per the
review addendum to `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md`. Session-clustered
inference throughout.

---

## Arm 0 — the effect is broader than one minute, but the money is not

Entry and exit delayed together by `d` minutes, 30-minute holding period fixed.
Coverage is **exactly 1.00 at every delay**, so the delayed cells are the same
sample.

| Delay | RSI regime gradient | no-RSI gradient | pooled IC | Q5 gross pips |
|---:|---:|---:|---:|---:|
| 0 | 0.0267 | 0.0170 | −0.0611 | **0.941** |
| 1 | 0.0187 | 0.0184 | −0.0412 | **0.503** |
| 2 | 0.0179 | 0.0141 | −0.0378 | 0.458 |
| 3 | 0.0127 | 0.0098 | −0.0333 | 0.303 |
| 5 | 0.0080 | 0.0075 | −0.0286 | 0.221 |

`G(1)/G(0) = 0.703` against the 0.50 threshold; level retention 0.674. **PROCEED**
as specified.

The decay is smooth and monotone rather than a cliff, with residual structure to
`d = 5`. A pure first-minute artifact would collapse at `d = 1` and stay flat.
`RSI_CLOCK_CONFOUND_REPORT.md` should be read alongside this rather than as having
pre-empted it.

No P&L condition was preregistered, and the P&L reading is weaker than the
statistical one: Q5 gross retains 53%, GBPUSD's Q5 t falls 2.64 → 1.39 at `d = 1`.

Two secondary observations. The **no-RSI gradient is the most stable of the three**
(0.0170 → 0.0184 at `d = 1`, rising on EURUSD), while the RSI gradient falls on all
four pairs — consistent with RSI's incremental interaction being real but
disproportionately first-minute. And **heterogeneity is large**: NZDUSD's gradient
is 0.0764 against 0.0222-0.0272 elsewhere and survives at every delay, while
EURUSD's reaches zero by `d = 3`. With effective sample nearer two or three than
four, the median should not be leaned on.

---

## Arm 2 — the tail is confirmed; the tested volatility features do not predict it

Survival means the RSI extreme was still in the same zone at the next scheduled
checkpoint. Not actionable — survival is unknown at the decision — and reported
only to establish the target.

| Pair | Survival rate | Survivors | Reverters | Tail cost |
|---|---:|---:|---:|---:|
| EURUSD | 6.0% | −10.29 pip (t −24.1) | +1.36 (t +18.4) | −0.62 pip |
| GBPUSD | 7.0% | −12.41 pip (t −29.6) | +1.64 (t +18.2) | −0.87 pip |
| AUDUSD | 6.5% | −8.71 pip (t −34.6) | +1.17 (t +18.6) | −0.57 pip |
| NZDUSD | 7.5% | −8.31 pip (t −36.0) | +1.26 (t +21.8) | −0.62 pip |

### Decision-time separators, out of sample (fit 2012-2020, tested 2021-2023)

| Feature | Pairs above 0.50 | Median AUC | min q | Sign-consistent |
|---|---:|---:|---:|:--|
| **rsi_depth** | 4/4 | **0.5436** | 0.036 | yes |
| **rv_30m_pct** | 0/4 | **0.4595** | 0.053 | yes |
| vol_of_vol_60m | 1/4 | 0.4818 | 0.036 | no |
| efficiency_60m | 3/4 | 0.5114 | 0.320 | no |
| efficiency_15m | 2/4 | 0.5030 | 0.142 | no |
| kurtosis_30m | 3/4 | 0.5070 | 0.916 | no |
| kurtosis_60m | 2/4 | 0.4997 | 0.836 | no |
| rv_ratio_5_30 | 2/4 | 0.5050 | 0.916 | no |

**Kurtosis, at the two windows tested, is flat.** Median AUC 0.507 and 0.500,
q ≈ 0.9 on both windows and all four pairs. The likely reason is estimator noise:
a fourth moment on 30 or 60 observations has very large sampling variance. That is
a statement about **30- and 60-minute rolling kurtosis of one-minute returns**, and
nothing more. Daily, multi-day, and same-slot-conditioned kurtosis are untested and
the family remains open — see limitations.

**Vol-of-vol at a 60-minute window is one pair and wrong-signed.** Only EURUSD is
significant (AUC 0.441, q 0.036), and its direction says high vol-of-vol predicts
*less* persistence, opposite to the proposed mechanism. Sign consistency 1/4. Again
this tests one window of one construction.

**What survives is a within-signal magnitude measure and a variable we already
had.** `rsi_depth` — distance past 30/70 — is the strongest separator, consistent
on 4/4: deeper extremes persist more often. `rv_30m_pct` is consistent on 4/4 but
restates the known result that reversion is stronger in high-volatility states.

Note the interesting tension with the economics below: deeper extremes **persist
more often** (Arm 2) *and* **pay more per signal when they do revert** (threshold
sweep). Both are true and they are not in conflict.

### What the filter is worth

Logistic fit on the early era, dropping the half of late-era signals scored most
likely to persist:

| Pair | Test AUC | All signals | Kept half | Gain | Cluster t: all → kept |
|---|---:|---:|---:|---:|---|
| EURUSD | 0.539 | 0.695 | 0.793 | +0.098 | 5.14 → **3.92** |
| GBPUSD | 0.510 | 0.626 | 0.965 | +0.339 | 3.21 → **3.03** |
| AUDUSD | 0.508 | 0.285 | 0.062 | **−0.223** | 2.13 → **0.33** |
| NZDUSD | 0.552 | 0.470 | 0.803 | +0.333 | 3.69 → 4.12 |

Mean pips improves on three of four; the t-statistic falls on three of four,
because half the sample is discarded. This matches the turnover-lever signature in
`ai_shared_memory/LEARNINGS.md` 2026-07-20.

---

## 3. P&L distribution and where the economics could work

### The per-signal distribution, RSI 30/70 at 30 minutes

| Pair | n | mean | median | sd | hit | mean win | mean loss | skew | worst 1% share | worst 5% share |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| EURUSD | 13,236 | 0.659 | 0.85 | 8.94 | 57.1% | +5.44 | −5.70 | +0.34 | −0.59 | −1.62 |
| GBPUSD | 14,454 | 0.648 | 0.95 | 11.16 | 56.3% | +6.77 | −7.24 | −1.99 | −0.79 | −2.10 |
| AUDUSD | 13,610 | 0.521 | 0.70 | 7.44 | 55.7% | +4.97 | −5.07 | −0.73 | −0.57 | −1.67 |
| NZDUSD | 15,204 | 0.544 | 0.75 | 7.30 | 55.4% | +4.91 | −4.87 | +0.23 | −0.52 | −1.50 |

Three things this corrects about earlier framing in this project:

- **Trades are not ~1 pip.** They are **±5 to 7 pips**, won 55-57% of the time,
  with a win/loss ratio of 0.94-1.01. The ~0.6 pip mean is the thin residual of a
  near-symmetric bet, not the size of a typical outcome.
- **The median exceeds the mean on all four pairs** (0.70-0.95 against 0.52-0.66).
  The typical trade is better than the average; a left tail drags the mean down.
- **The worst 1% of trades remove 52-79% of total gross P&L; the worst 5% remove
  150-210%.** Excluding the worst 5%, gross would be roughly 2.5-3x larger. This is
  Arm 2's continuation problem at the distribution level and it is far more severe
  than the AUC work implied. It also means tail control, not entry selection, is
  where the leverage is.

### Horizon sweep, RSI 30/70, median across pairs

| Horizon | gross | sd | cluster t | gross/hour | per-signal Sharpe | net @0.5 | annual net @0.5 |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 5m | 0.493 | 4.49 | 12.9 | 5.92 | **0.108** | −0.007 | −10 |
| 15m | 0.542 | 6.30 | 9.9 | 2.17 | 0.085 | 0.042 | 46 |
| 30m | 0.596 | 8.19 | 8.3 | 1.19 | 0.072 | 0.096 | 113 |
| 60m | 0.543 | 11.48 | 5.6 | 0.54 | 0.049 | 0.043 | 50 |
| 120m | 0.714 | 16.16 | 4.8 | 0.36 | 0.042 | 0.214 | 223 |
| 240m | 0.792 | 22.89 | 3.6 | 0.20 | 0.035 | 0.292 | 268 |
| 480m | 1.039 | 32.34 | 2.7 | 0.13 | **0.029** | 0.539 | **409** |

**Longer horizons buy cost amortisation, not signal.** Gross rises 1.74x from 30m
to 480m while sd rises 3.95x, so per-signal Sharpe falls monotonically. Net
improves only because a fixed round trip is spread over a larger move.

### Threshold sweep at 30 minutes, median across pairs

| Cut | signals/yr | gross | median | cluster t | hit | net @0.5 | annual net @0.5 |
|---|---:|---:|---:|---:|---:|---:|---:|
| 15/85 | 46 | **0.950** | 0.99 | 2.19 | 59.5% | 0.450 | 22 |
| 20/80 | 152 | 0.826 | 0.95 | 4.14 | 57.7% | 0.326 | 49 |
| 25/75 | 455 | 0.616 | 0.93 | 5.23 | 57.0% | 0.116 | 54 |
| 30/70 | 1,137 | 0.596 | 0.80 | 8.32 | 56.0% | 0.096 | **113** |
| 35/65 | 2,479 | 0.512 | 0.63 | 10.41 | 54.9% | 0.012 | 27 |
| 40/60 | 4,712 | 0.402 | 0.53 | 12.33 | 54.1% | −0.098 | −466 |

Depth monotonically improves per-signal gross and per-signal Sharpe, but signal
count collapses, so annual net peaks in the middle. **The risk-adjusted optimum
(deep and short — 15/85 × 15m, per-signal Sharpe 0.151) and the cost-amortised
optimum (shallower and long — 35/65 × 480m, 602 annual net pips at 0.5) point in
opposite directions.**

### Viability by cost assumption

| Round trip | Reading |
|---|---|
| **0.2 pip** | Viable across most of the grid; 30/70 × 480m ≈ 660 pips/pair/yr |
| **0.5 pip** | Viable at longer horizons; best cells 400-600 pips/pair/yr, 4/4 pairs positive, t 2.7-3.6 |
| **1.0 pip** | Essentially dead; only 15/85 and 20/80 at ≥120m survive, at 26-86 pips/yr |

The whole question is therefore the true round trip, which this project has never
measured. Everything above is midpoint bars.

### Outcomes in volatility units, and whether a stop fixes the tail

Risk unit is the causal expected 30-minute move for the slot
(`slot_fwd_rv_median_90d`, prior sessions only), converted to pips at the entry
price. Median unit is 5.4-7.2 pips.

| Pair | σ (pips) | mean R | median R | hit | winners mean/median R | losers mean/median R |
|---|---:|---:|---:|---:|---:|---:|
| EURUSD | 5.76 | 0.120 | 0.172 | 56.9% | +0.927 / +0.697 | −0.946 / −0.636 |
| GBPUSD | 7.22 | 0.084 | 0.144 | 56.0% | +0.896 / +0.678 | −0.950 / −0.635 |
| AUDUSD | 5.65 | 0.100 | 0.131 | 55.5% | +0.911 / +0.679 | −0.913 / −0.616 |
| NZDUSD | 5.41 | 0.112 | 0.138 | 55.5% | +0.917 / +0.702 | −0.892 / −0.622 |

**Winners and losers are the same size**, about ±0.9 R mean and ±0.65 R median.
The entire edge is the hit rate: 0.56 × 0.91 − 0.44 × 0.92 ≈ +0.11 R. Excursions
agree — MFE averages 0.97-1.00 R against MAE 0.85-0.91 R, a mild favourable tilt,
with MAE's 99th percentile at 4.5-5.4 R. The strategy is **+0.08 to +0.12 R per
bet**, about a tenth of a typical 30-minute move, with no payoff asymmetry to
harvest.

Stop at k × σ, single barrier so no intrabar ordering is required, median across
pairs, no slippage:

| Stop | stopped | mean pips | sd | per-signal Sharpe | worst 5% share | annual net @0.5 |
|---:|---:|---:|---:|---:|---:|---:|
| 0.5 R | 54.5% | 0.557 | 5.76 | **0.096** | **−0.52** | 57 |
| 1.0 R | 30.0% | 0.521 | 6.87 | 0.080 | −0.91 | 23 |
| 1.5 R | 16.5% | 0.561 | 7.38 | 0.075 | −1.19 | 66 |
| 2.0 R | 9.5% | 0.588 | 7.65 | 0.073 | −1.40 | 96 |
| 3.0 R | 3.8% | 0.598 | 7.94 | 0.074 | −1.55 | 106 |
| none | 0% | **0.605** | 8.34 | 0.073 | −1.62 | **114** |

**A volatility-scaled stop does not improve economics, and this reverses the
natural inference from the tail concentration above.** The stop works as intended
— a 0.5 R stop cuts the worst-5% drag from −1.62 to −0.52 — but mean P&L is
monotone increasing as the stop widens, because the winners live in the same tail.
Truncating the loss distribution truncates the gain distribution by more. Tight
stops raise per-signal Sharpe (0.096 against 0.073) purely by variance reduction on
a smaller mean, the turnover-lever pattern of `LEARNINGS.md` 2026-07-20.

**With a 1-pip stop slippage it collapses.** Mean falls to 0.015 (0.5 R), 0.218
(1.0 R), 0.495 (2.0 R), and net at a 0.5 pip cost is negative for every finite stop
except 3.0 R. Crediting a fill at exactly the stop level is optimistic (rule 5);
filled realistically, stops are destructive here.

**Take-profit is the same in mirror**: no TP (0.605) beats every level tested
(0.75 R → 0.523, 1.0 R → 0.549, 1.5 R → 0.578). Both barriers hurt. Per pair, only
EURUSD gains from a 1.5-2.0 R stop (0.705 against 0.682); GBPUSD is a wash, AUDUSD
and NZDUSD are worse. One of four, not consistent.

The trailing-RV(30) risk unit gives the same picture, with 3.0 R marginally ahead
of no stop (0.617 against 0.605) — inside noise.

---

## Limitations and what remains open

- **Kurtosis is tested at two intraday windows only.** 30- and 60-minute rolling
  kurtosis of one-minute returns. Daily, multi-day, same-slot-conditioned, and
  jump-robust tail measures are **untested**, and a fourth moment estimated on
  longer memory would not carry the sampling-noise problem that most likely
  explains the intraday null. The external commentary's kurtosis claim is **not
  refuted** — one narrow version of it is.
- **Vol-of-vol likewise** is one 60-minute construction. Longer-memory and
  daily-scale vol-of-vol are untested.
- **Cost is assumed, never measured.** No bid/ask study exists for these pairs at
  half-hour boundaries, which Arm 0 shows is exactly where the edge concentrates.
  This is the single highest-value missing input; it decides viability by itself.
- **Overlap is unmodelled at long horizons.** An 8-hour hold with signals every
  30 minutes implies up to ~16 concurrent positions. The per-signal estimand must
  be replaced by portfolio accounting (rule 13) before any long-horizon annual
  figure is used.
- **Exact-exit coverage falls with horizon**, from 0.95 at 30m to 0.65-0.67 at
  480m, so long-horizon cells are a partly different sample.
- **No null** (rule 17) on either arm.
- **Cell independence.** AUDUSD/NZDUSD and EURUSD/GBPUSD are correlated;
  "4/4 sign-consistent" is nearer two or three effective agreements.
- **Consumed history.** All pre-2024 data is inspected; nothing here is a clean
  holdout result.

## Decision

1. **Do not deploy at the canonical 30/70 × 30-minute configuration.** Net is
   0.096 pip at a 0.5 pip cost assumption, and roughly half of it is one minute.
2. **Measure the actual bid/ask round trip before any further modelling.** It is a
   single input that moves the verdict from "viable across the grid" to "dead", and
   every conclusion above is conditional on it.
3. **Barrier-based tail control is tested and rejected.** Despite the worst 5% of
   trades removing more than the whole gross, neither a volatility-scaled stop nor
   a take-profit improves mean P&L at any level on any risk unit, and stops turn
   strictly destructive under 1-pip slippage. Winners and losers are the same size
   (±0.9 R) so there is no asymmetry to exploit by truncation. What remains
   untested for the tail is **time-based exit on non-reversion** and **position
   sizing on RSI depth** — neither truncates the payoff distribution, so neither
   is answered by this result.
4. **Arms 1 and 3 stay open.** Arm 1 should be rerun with daily and multi-day
   kurtosis and vol-of-vol before the family is judged. Arm 3 is untested.
5. Record `rsi_depth` as the one positive finding: a within-signal magnitude
   measure beat every engineered volatility feature at predicting continuation,
   and separately it monotonically improves per-signal gross and Sharpe. Not
   deployable at AUC 0.54, but the right starting point.
6. **Holdout 2024+ remains sealed.**

## Evidence

- Frozen specification: `RSI_MEAN_REVERSION_PROGRAMME_SPEC.md`
- Arm 0: `_run_rsi_arm0_entry_delay.py` → `rsi_arm0_entry_delay_results.json`,
  `rsi_arm0_entry_delay_quintiles.csv`, `rsi_arm0_entry_delay_gradients.csv`
- Arm 2: `_run_rsi_arm2_continuation.py` → `rsi_arm2_continuation_results.json`,
  `rsi_arm2_continuation_univariate.csv`, `rsi_arm2_continuation_summary.csv`
- Distribution and economics: `_run_rsi_pnl_distribution_horizon.py` →
  `rsi_pnl_distribution_horizon_results.json`, `rsi_pnl_distribution.csv`,
  `rsi_horizon_threshold_grid.csv`
- Volatility units and stop/take sweeps: `_run_rsi_vol_units_stop.py` →
  `rsi_vol_units_stop_results.json`, `rsi_vol_units_distribution.csv`,
  `rsi_vol_stop_sweep.csv`
- Upstream: `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md` (and its review addendum),
  `RSI_CLOCK_CONFOUND_REPORT.md`, `RSI_BROAD_REGIME_SWEEP_SPEC.md`
