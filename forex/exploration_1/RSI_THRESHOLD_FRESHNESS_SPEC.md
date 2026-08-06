# Frozen specification — exhaustion-threshold control and freshness component

Written before execution. Two independent arms against the surviving configuration
of `RSI_REGIME_GATED_SYSTEM_REPORT.md` (components 1 + 2).

Data unchanged: EURUSD, GBPUSD, AUDUSD, NZDUSD one-minute midpoint OHLC,
2012-01-01 to 2023-12-29, New York 17:00 session boundary, decisions at completed
`:29`/`:59` bars, entry at the next one-minute open, exit at the open exactly 30
minutes later. Era split 2021-01-01. **2024+ remains sealed and is not read.**

---

## Arm 1 — is the vol-scaled threshold information, or a selectivity dial?

### The concern

`_run_rsi_regime_gated_system.py:201` compares a vol-scaled trigger
`|z| ≥ 1.5 × (1 + vol_pct)` against a fixed trigger `|z| ≥ 1.5`. The two select
**632 and 1,724 signals per year** respectively — a 2.7x difference in
selectivity. The project's own threshold sweep
(`RSI_MEAN_REVERSION_PROGRAMME_REPORT.md`) shows that depth alone raises
gross pips per signal monotonically: 0.616 at 455 signals/yr, 0.826 at 152. The
published gain (0.588 → 0.648) lies inside what a deeper fixed cut would produce
at the same count. The comparison therefore cannot attribute the gain to the
volatility scaling.

### Design

Every trigger rule is written as a **score**

```
s = |z| / g(vol_pct)
```

and each rule keeps the top `rate` fraction of decisions by its own score. This
makes all rules **exactly rate-matched by construction**; the only thing that
differs between them is the shape of `g`.

| Rule | `g(vol_pct)` | Reading |
|---|---|---|
| **A — published** | `1 + vol_pct` | require MORE stretch when volatility is high |
| **B — degenerate** | `1` | fixed depth; no volatility content at all |
| **C — mirror** | `2 − vol_pct` | require LESS stretch when volatility is high |

`vol_pct` is the causal same-slot percentile of RV(30) over 90 prior sessions,
unchanged from the audited run. Rule C is included because the project's own
results say reversion is *stronger* in high-RV states, which points the opposite
way from rule A.

Score cutpoints are fitted on the **early era (2012-2020) only** and applied
unchanged to the whole sample and to the late era, matching this project's
convention for quintile cutpoints.

Keep rates: 0.20, 0.14, 0.10, 0.07, 0.05, 0.03, 0.02. The published operating
point is ≈ 0.052 of decisions.

All rules are evaluated on one **common sample**: rows where `z`, `vol_pct`,
`vei_atr_z` and the 30-minute target are all defined. The literal published rule
(`k = 1.5` exactly, not rate-matched) is reported as a reference row to confirm
reproduction of the audited numbers.

Run twice: on the trigger alone, and with component 1 stacked (ATR(14)/ATR(50)
same-slot z-score, top 40%).

### Primary metric

Median across the four pairs of **gross pips per signal**, at matched keep rate.
Secondary: mean R (scale-free, rule 19), session-clustered t, hit rate, net at
0.2/0.5/1.0 pip.

### Kill test — declared before the run

At the keep rate nearest the published operating point (0.05):

- **Supported** if rule A beats rule B on gross pips per signal in **≥ 3 of 4
  pairs** and by a **median margin ≥ +0.03 pip** (half the originally claimed
  +0.060 gain), and the sign holds in the late era.
- **Rejected as a selectivity dial** if the median margin is ≤ 0, or if ≤ 2 of 4
  pairs improve. The recommendation then becomes a fixed threshold, which has one
  fewer moving part.
- **Inconclusive** in between; report as such rather than choosing after the fact.

If rule **C** beats rule A, the direction of the published scaling is wrong and
that is reported as the headline regardless of the A-vs-B outcome.

---

## Arm 2 — freshness (time-in-zone) as a new component

### The claim being tested

`RSI_RV_CLOCK_REGIME_REPORT.md` reports `scheduled_fresh` (RSI extreme age zero)
Q5 gross of 1.518 / 1.768 pip against 0.951 / 1.184 for all scheduled states, and
`ai_shared_memory/LEARNINGS.md` (2026-08-04) records expectancy decaying with
time-in-zone (tau = 0 best at +0.90/+1.04; tau 6-20 flat to negative). Age of the
extreme is causal, free, and known at the decision bar, and it is **not** in the
gated system.

### Definition

At every one-minute bar, evaluate the trigger condition against a **fixed** level
so the condition exists at all minutes rather than only at decision bars:

- `age_z` — consecutive one-minute bars, ending at and including the decision bar,
  on which `z ≤ −1.5` (long side) or `z ≥ +1.5` (short side) held continuously,
  minus one. `age = 0` means the level was first breached at this bar.
- `age_rsi` — the same construction on RSI(14) ≤ 30 / ≥ 70, to bridge to the
  RV-clock report's `scheduled_fresh` result.

Runs reset at any non-contiguous minute (weekend, holiday, or data gap), so an
age is never carried across a gap.

### Arms

1. **Dose-response.** Age buckets 0, 1-2, 3-5, 6-10, 11-20, 21+ on the surviving
   system (published trigger + ATR expansion top-40%). Report n, gross pips,
   mean R, hit rate, cluster t per bucket, per pair and as a median.
2. **Gate.** `age == 0` against `age > 0`, and against the ungated base.
3. **Rate-matched control.** Freshness keeps some fraction `f` of gated signals.
   Compare against tightening the **existing** expansion gate to the same `f`.
   This is the "is this new information, or just a cheaper way to trade less"
   test.
4. **Delay control — mandatory.** A fresh extreme is by construction a move that
   just happened, which is exactly the first-traded-minute microstructure effect
   this project has already documented (`RSI_CLOCK_CONFOUND_REPORT.md`; entry
   delay retains 53% of Q5 gross). Every freshness cell is reported at **delay 0**
   (entry `t+1`, exit `t+31`) and **delay 1** (entry `t+2`, exit `t+32`, holding
   period unchanged).
5. **Era split.** 2012-2020 against 2021-2023, because a pooled improvement driven
   by the early nine years is the exact failure mode that killed the kurtosis
   component.

### Kill test — declared before the run

Freshness is **adopted** only if all four hold:

1. `age == 0` beats `age > 0` on gross pips per signal in **≥ 3 of 4 pairs**;
2. it beats the **rate-matched expansion tightening** in ≥ 3 of 4 pairs;
3. the delta is **positive in the late era** (median across pairs);
4. **at least half** the delta survives the one-minute entry delay.

Failing (4) alone downgrades it to "real but first-minute", not deployable —
the same verdict the clock work reached, and reported as such rather than
suppressed. Failing (1), (2) or (3) rejects it.

Scale check throughout: mean R alongside mean pips, so an apparent gain that is
only "fresh extremes happen in more volatile minutes" is visible (rule 19).

---

## What neither arm does

- No null (rule 17). Both arms are comparisons between rate-matched rules on the
  same rows, not effect estimates against noise.
- No bid/ask model. All P&L is midpoint gross with hypothetical flat costs.
- Consumed history throughout. Nothing here is a holdout result.
- Four correlated pairs are nearer two or three effective agreements; "3 of 4" is
  a weak vote and is treated as a screening gate, not as inference.

## Reproduction

```
python -u _run_rsi_threshold_control.py
python -u _run_rsi_freshness.py
```
