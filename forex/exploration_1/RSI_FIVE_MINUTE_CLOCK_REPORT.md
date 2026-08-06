# The z / RSI mean-reversion system on a FIVE-MINUTE bar clock

Frozen spec: `RSI_FIVE_MINUTE_CLOCK_SPEC.md` (written before the run, rule 24).
Script: `_run_rsi_five_minute_clock.py`. Outputs:
`rsi_five_minute_clock_results.json`, `rsi_five_minute_clock.csv`.
Data: cleaned 1-minute midpoint OHLC, 2012-01-01 to 2023-12-29, four USD pairs.
The 2024+ holdout was not opened.

Origin: user asked to run the strategy "on the 5 minutes instead of 1, first
crossing, with appropriate volatility regimes (using the conditions we have
created so far)".

---

## Headline

**The five-minute clock reproduces the one-minute edge almost exactly per unit of
risk, and buys nothing.** At the time-matched 30-minute horizon the base
`|z| >= 1.5` arm pays **0.0240 R** against the published one-minute **0.0230 R**,
at a near-identical risk unit (**8.11** against ~8.6 pips) and at more signals per
year (2,741 against ~1,700). It does not decay less under execution delay, it
does not survive cost any better, and its absolute level is flattered by the grid
phase.

**The one thing that did change, and it is the useful result: the volatility
regime gate is a SHORT-HORIZON effect.** Excess over the `|z|` depth frontier for
the confirmed `ATR40 + rv40` family collapses monotonically with holding period —
**+0.0100 R at 30 minutes, +0.0045 at 60, +0.0003 at 150** — and the collapse
holds at all five grid phases. At 150 minutes the gate this project confirmed
against a claim-matched null is a pure selectivity dial.

---

## A. Two rule-9a defects, one of them inside my own control

**A1. Preserving parameters in BAR units multiplies every lookback by five, and a
600-minute window no longer fits between the daily gaps.** The `z` scale is a
120-bar rolling dispersion. On the 1-minute clock that is 120 minutes and costs
two hours a session. On the 5-minute clock it is 600 minutes, and the daily 17:00
New York rollover gap never fits inside it: the strict contiguity rule returned
**coverage 0.000 for the first TEN hours of every session** — the entire Asia
session deleted, at 58% of all bars, invisible except as NaN.

**A2. The obvious repair silently broke the phase placebo, and the broken placebo
looked like a spectacular finding.** Allowing one session break inside the window
restores phase 0 to 99.5% coverage. It does **not** restore the other four grid
offsets: off-phase, the bar straddling the rollover is incomplete and therefore
invalid, which creates **two** breaks, so Asia is deleted again. The first
completed run therefore reported grid phase 0 at **rank 1/5 with roughly 3x the
mean R of every other offset** (0.0228 against 0.0024-0.0098) — which reads
exactly like the `:29` phase artifact this project already documented, and would
have been written up as "the five-minute result is entirely a clock-phase
artifact". It was not. Phase 0 had 1,212 signals per year against ~783 off-phase;
the placebo was comparing grid offsets against a ten-hour-a-day coverage hole.

The repair is to give the scale estimator **no break gate at all** — displacement
from the EMA is defined at every bar, a trailing dispersion estimate across a
weekend is still a valid causal dispersion estimate, and every phase is then
treated identically. Coverage becomes 0.9999 with a per-slot minimum of 0.9995,
and event counts match across phases (1,215 / 1,211 / 1,211 / 1,216 / 1,218).

**The reusable instruction: a phase or seasonality placebo must be coverage-matched
before it is read.** Check the per-arm signal COUNT across placebo cells first; a
placebo whose cells differ in n is measuring the estimator, not the phase.

**A3. Residual, disclosed.** `vei_atr_z` coverage is 0.81 (0.76 NZDUSD) with a
per-slot minimum of 0.000, i.e. some session-minute slots never obtain the ATR
expansion normaliser. The ATR-expansion arms are read with that caveat.
`rv_gate_pct` is 0.98 and `rv_30` 1.00. Events dropped for an incomplete
one-minute holding path: median 438 of 13,920 (3.1%), maximum 5,990.

---

## B. Execution and the stop

Signals, features and exits are on the 5-minute clock; **the compulsory stop is
resolved on the underlying ONE-MINUTE path.** A 5-minute bar hides a minute that
opens beyond the stop level, and scanning 5-minute bars would credit the exact
level there — a rule-5 violation in the optimistic direction. Single barrier at
2.0 R, 1 pip adverse slippage, entry bar inside the stop scan (rule 3),
gap-through fills at the open (rule 5), non-overlap enforced (rule 13).

---

## C. The `|z|` frontier is much flatter on this clock

Median across pairs, mean R by depth:

| horizon | z1.0 | z1.5 | z2.0 | z2.5 | z3.0 | risk unit |
|---|---|---|---|---|---|---|
| 6 bars / 30 min | 0.022 | 0.024 | **0.032** | 0.025 | 0.024 | 8.1-10.9 |
| 12 bars / 60 min | 0.018 | 0.027 | 0.030 | 0.028 | 0.022 | 8.0-12.2 |
| 30 bars / 150 min | 0.018 | 0.023 | 0.023 | 0.024 | 0.020 | 11.8-16.4 |

On the 1-minute clock this frontier was cleanly monotone (0.016 R at 7,947
signals/yr to 0.038 at 1,697), which is what made it a good reference. Here it is
**humped, peaking near `z = 2.0`, and nearly flat at the long horizon**. So depth
is a weaker lever on the 5-minute clock, and the excess-over-frontier metric has
a less informative baseline than it did. Cluster t falls sharply with horizon
(4.5 -> 2.9 -> 2.0 at z1.0), so the long-horizon rows are also the least certain.

---

## D. Clock comparison at the time-matched horizon

| arm | clock | signals/yr | mean R | mean pips | risk unit | excess |
|---|---|---|---|---|---|---|
| `z >= 1.5` base | 1-minute | ~1,700 | 0.0230 | — | ~8.6 | 0 |
| `z >= 1.5` base | 5-minute, 30 min | 2,741 | **0.0240** | 0.215 | 8.11 | 0 |
| `+ ATR40 + rv40` | 1-minute | 2,803 | 0.0451 | 0.382 | 8.41 | +0.0137 |
| `+ ATR40 + rv40` | 5-minute, 30 min | 1,334 | **0.0344** | 0.338 | 9.11 | +0.0100 |

The base edge per unit of risk transfers essentially unchanged. The **gate is
weaker** on the slower clock in both absolute R (0.0344 vs 0.0451) and in excess
(+0.0100 vs +0.0137). Per the spec's stated criterion, the five-minute clock is
**not preferred**: it matches on the base and loses on the conditioning.

---

## E. Kill test

Primary metric: mean R in excess of the `|z|` frontier interpolated in
log(signals/year) to the arm's own rate. SUPPORTED = median `>= +0.005 R` and
`>= 3/4` pairs.

### E1. Declared primary horizon, 30 bars = 150 minutes

Nine of ten arms rejected. Only `z1.5 + rv pct 20` passes: **+0.0081 R, 3/4
pairs, delay-1 +0.0040, late era +0.0086, and positive at all five grid phases
(+0.0081 / +0.0034 / +0.0054 / +0.0098 / +0.0117)**. That is 1 pass out of 10
declared arms on correlated pairs and is a screen (rule 26), not a result.

Notably the confirmed `ATR40 + rv40` family is a **dial** here (+0.0003), and
the ATR expansion gate alone is **worse than the frontier** (-0.0094, 0/4).

### E2. Time-matched horizon, 6 bars = 30 minutes

| arm | excess R | pairs | delay-1 | late | all-phase | verdict |
|---|---|---|---|---|---|---|
| `z1.5 + ATR40 + rv40` | **+0.0100** | 3/4 | +0.0064 | +0.0135 | +0.0077 | **SUPPORTED** |
| `z1.5 + rv pct 40` | +0.0048 | 2/4 | +0.0069 | +0.0020 | +0.0048 | dial |
| `z1.5 + rv pct 20` | +0.0026 | 2/4 | +0.0004 | +0.0028 | +0.0031 | dial |
| `z1.5 + ATR expansion 40` | +0.0022 | 2/4 | +0.0009 | -0.0000 | +0.0022 | dial |
| `z 1.5 AND rsi 30/70` | +0.0136 | 4/4 | +0.0082 | **-0.0026** | +0.0136 | fragile |
| `rsi 30/70` | +0.0077 | 2/4 | +0.0065 | -0.0018 | +0.0077 | dial |

**The combined gate is the one arm that passes cleanly**, and it is the same
family that `RSI_GATE_NULL_REPORT.md` confirmed against a claim-matched null on
the 1-minute clock. It passes at every grid phase (+0.0100 / +0.0077 / +0.0060 /
+0.0022 / +0.0080), at delay 1, and in the late era. Single gates remain dials,
reproducing the 1-minute finding.

### E3. A measurement flaw that must be stated with the RSI rows

`rsi 15/85` (+0.0294) and `rsi 20/80` fire at 272-401 signals/year, **below the
frontier's own minimum rate** (573 at H=6, 421 at H=30), and `rsi 25/75` is
outside on 2 of 4 pairs at H=6. `np.interp` clamps there, so those arms are
scored against the shallowest available frontier point rather than a genuinely
matched one. **They are not rate-matched and must not be promoted.** Every
regime-gate arm is inside the frontier's range, so the headline is unaffected.

This also means the apparent revival of RSI on the slower clock (`rsi 25/75`
+0.0186, 4/4) is partly an extrapolation artifact. The one clean RSI row,
`rsi 30/70` at +0.0077 with 2/4 pairs, remains a dial — consistent with the
1-minute conclusion that RSI and `z` are close to the same variable.

---

## F. The phase placebo, and why the primary metric survives it

Grid phase 0 (bars on `:00`, `:05`, ...) ranks **1/5 on both placebo arms** in
absolute mean R:

| arm | phase 0 | 1 | 2 | 3 | 4 | sd |
|---|---|---|---|---|---|---|
| `z 1.5` | 0.0228 | 0.0152 | 0.0142 | 0.0130 | 0.0096 | 0.0049 |
| `+ ATR40 + rv40` | 0.0245 | 0.0207 | 0.0158 | 0.0131 | 0.0167 | 0.0045 |

Phase 0 sits about **+0.0086 R above the phase median, roughly 38% of the base
arm's entire edge**. Phase 0 puts every entry on a UTC minute divisible by five,
which includes `:00` and `:30` — the two minutes this project's own
`RSI_CLOCK_CONFOUND_REPORT.md` identified as the most strongly reverting minutes
of the hour on spot FX. The story is consistent, and it means **every absolute
level quoted at phase 0 in this report is flattered**.

**But the excess over the frontier is phase-robust**, because a phase shift moves
the arm and its own frontier together and largely cancels: the combined gate at
H=6 scores +0.0100 / +0.0077 / +0.0060 / +0.0022 / +0.0080 across the five
offsets, all positive. This is a direct methodological vindication of scoring
against the base parameter's own frontier rather than against zero — the same
device retracted a component in `RSI_THRESHOLD_FRESHNESS_REPORT.md`, and here it
is what makes a phase-contaminated measurement still interpretable.

---

## G. Delay, era, cost

**Delay retention is not improved by the slower clock.** One full 5-minute bar of
delay retains **22-29% of pips and 25-37% of R**, against 72%/71% for a
one-*minute* delay on the 1-minute clock. Since the 1-minute clock at a
*five-minute* delay retained about 15%, the fair reading is that **the decay is a
wall-clock property of a few minutes and a coarser decision bar does not escape
it.** Moving to 5-minute bars does not buy latency robustness. The worst cell is
the combined gate at the 150-minute horizon, which retains only 3% of pips.

**The late era stays weak**, as on every other arm in this project: base cluster
t falls from 1.86 (2012-2020) to 1.10 (2021-2023) at the primary horizon.

**Cost decides everything, and it is still unmeasured.** Median annual net pips
per pair: at a 0.2 pip round trip **+40 to +199**; at 0.5 pip **all six cells
negative** (-126 to -781); at 1.0 pip -483 to -2,149. Gross mean pips per trade
is 0.21-0.34 against a 0.5-1.0 pip round trip. **No tradability claim is
available from this run and none is made.**

---

## H. Verdict

1. **The five-minute clock is not an improvement and not a failure — it is a
   wash on the base signal.** Same R per unit of risk, more trades, worse
   conditioning, no latency benefit. There is no reason to switch and no reason
   to believe the one-minute result was a sub-five-minute microstructure
   artifact: the edge is visible at both sampling rates.
2. **The volatility regime family is a short-horizon conditioner.** Its excess
   is +0.0100 R at a 30-minute hold and vanishes by 150 minutes, at every grid
   phase. If the gate is retained, the holding period must stay short.
3. **`z1.5 + rv pct 20` at the 150-minute horizon** is the only pass at the
   declared primary horizon (+0.0081, 3/4, phase-robust). It is 1 of 10 arms on
   correlated pairs with no null; treat it as a screen.
4. **Not deployable.** Gross 0.21-0.34 pip against an unmeasured spread, late-era
   cluster t near 1, and delay-0 dependence. Measuring the spread remains the
   binding next action, as it has been for every arm in this project.

## Reproduce

    python -u _run_rsi_five_minute_clock.py
