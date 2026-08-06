# Cross-pair coherence gate and time-based non-reversion exit — event clock, compulsory stop

Frozen specification: `RSI_COHERENCE_TIMEEXIT_SPEC.md`, written before either run.
Scripts `_run_rsi_coherence_gate.py` (arm 3) and `_run_rsi_time_exit.py` (arm 4),
both on the shared engine `_rsi_stop_engine.py` with its executable checks in
`_test_rsi_stop_engine.py` (17 checks, all passing). 2024+ never opened.

## Verdict

| Arm | Result |
|---|---|
| **3. Cross-pair coherence as a regime filter** | **REJECTED.** Median T1−T3 gap **−0.0012 R, 2/4 pairs**. Wrong sign on EURUSD and AUDUSD. Quintile profile non-monotone. Re-pairing null centres at 0.000 with sd 0.011 and only **1 of 4** pairs falls outside it. |
| **4. Time-based non-reversion exit** | **REJECTED.** Beats hold-to-30 on **1/4** pairs (median **−0.0047 R**), and — the decisive control — beats a **matched-rate random-time exit on 1/4** pairs (median −0.0021 R). "Has not reverted yet" carries no information about what happens next. |
| **Incidental, and the most useful output of the run** | The **compulsory stop is a pure, monotone tax on expectancy, 4/4 pairs**, and the cost is far larger than either component being tested. Sizing the mandatory stop is a bigger lever than any signal work now open. |

Neither arm is deployable. The two changes to the *framework* — the event clock and
the compulsory stop — both stand, and both are improvements on what the project had.

---

## What changed in this run, and why

Two constraints supplied before execution, both altering the estimand rather than
decorating it.

**1. Decisions are no longer on the fixed `:29`/`:59` clock.** That grid was
exploration scaffolding. Dropping it is also a correction: this project's own
`RSI_CLOCK_CONFOUND_REPORT.md` established that the `:29` schedule ranks **30/30**
among the 30 half-hour phases, i.e. it was a minute-of-half-hour selector. Every
signal here is now an **event** — the first minute the entry condition becomes true —
with **non-overlap enforced** (rule 13) so only one position is open at a time, which
is what a single challenge account runs.

The placebo check confirms the clock is genuinely free: the most common
minute-of-half-hour holds **4.6-5.4%** of accepted events against 3.33% under
uniformity, and phase `:29` holds **3.5-4.1%**. The schedule has not been
reconstructed by the back door.

Two consequences worth stating:

- Non-overlapping event entries run at **4,400-4,800 per pair per year**, roughly
  4x the fixed clock's 1,137, with a median 55-62 minutes between entries.
- Because every signal is a first crossing, **every trade is `age == 0`** in the
  sense of `RSI_THRESHOLD_FRESHNESS_REPORT.md`. That report's fragility warning
  therefore applies to the whole strategy, not to an optional component — which is
  why the one-minute delay is a primary result below, not a sensitivity.

**2. A single-price-barrier stop is compulsory on every trade.** Every headline
number is simulated with a stop already in place. Single barrier means there is no
intrabar stop-versus-target ordering to resolve; the rules that still bite are rule 3
(the entry bar is inside the stop scan) and rule 5 (a minute that *opens* beyond the
stop fills at that open, and slippage is always reported).

One incidental repair: the audited fixed-clock script took the expansion-gate
quantile over the **whole sample**, a two-sided statistic. Here it is fitted on the
early era only (2012-2020) and applied unchanged to the late era.

---

## Rule-23 reproduction

The clock change means the published *fixed-clock* means are the wrong target — a
different clock is a different sample. Reproduction was declared in advance against
the published **first-crossing** figures (`MEMORY.md`,
`RSI_CLOCK_CONFOUND_REPORT.md`): 0.397-0.418 pip in 2012-2020 and 0.220-0.341 pip in
2021-2023, EURUSD and GBPUSD, RSI 30/70, no stop.

| Cell | Published range | This run | Verdict |
|---|---|---:|---|
| EURUSD early | 0.397 – 0.418 | **0.4135** | inside |
| GBPUSD early | 0.397 – 0.418 | **0.3954** | 0.0016 below, inside the ±0.05 tolerance |
| EURUSD late | 0.220 – 0.341 | **0.2212** | inside |
| GBPUSD late | 0.220 – 0.341 | **0.3376** | inside |

Three of four land inside the published range outright and the fourth misses by
0.0016 pip. The event clock is implemented consistently with the earlier crossing
work despite the added non-overlap rule and the exact 32-minute contiguity
requirement.

---

## A. The compulsory stop is the largest single lever in the system

Gated signal, median across the four pairs, 1-pip stop slippage (rule 5: crediting a
fill at exactly the stop level is optimistic and a challenge account does not get it).

| Stop | stopped | mean pips | mean R | cluster t | worst-5% share | max DD (R) | worst day (R) |
|---:|---:|---:|---:|---:|---:|---:|---:|
| none | 0.0% | **0.333** | **0.047** | 8.65 | −3.36 | 116 | −18.6 |
| 3.0 R | 2.6% | 0.308 | 0.042 | 8.32 | −3.44 | 104 | −16.3 |
| **2.0 R** | 8.0% | 0.269 | 0.034 | 7.44 | −3.67 | 117 | −15.9 |
| 1.5 R | 15.3% | 0.185 | 0.019 | 5.44 | −4.73 | 182 | −14.9 |
| 1.0 R | 29.6% | **0.030** | **−0.008** | 0.90 | −11.49 | 649 | −13.9 |

**The relationship is monotone and it is monotone on all four pairs with no
exceptions.** Mean R at 1.0 R / 2.0 R / no stop:

| Pair | 1.0 R | 1.5 R | 2.0 R | 3.0 R | none |
|---|---:|---:|---:|---:|---:|
| EURUSD | −0.0040 | 0.0218 | 0.0363 | 0.0441 | 0.0493 |
| GBPUSD | 0.0095 | 0.0302 | 0.0400 | 0.0469 | 0.0485 |
| AUDUSD | −0.0117 | 0.0122 | 0.0242 | 0.0338 | 0.0365 |
| NZDUSD | −0.0121 | 0.0162 | 0.0325 | 0.0398 | 0.0445 |

Three readings, in order of practical importance.

- **The mandate itself costs about 19% of gross at 2.0 R and 8% at 3.0 R.** That is
  the price of the challenge rule, and it is unavoidable. It is larger than any
  effect either arm of this run was testing for.
- **A tight stop destroys the strategy.** At 1.0 R with realistic slippage, mean R
  is **negative on three of four pairs** and the cluster t falls from 8.65 to 0.90.
  This is the same mechanism `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` recorded on the
  fixed clock — winners and losers are both about ±0.9 R, so truncating the loss
  distribution truncates the gain distribution by more — but the event clock makes it
  sharper, and the slippage is what converts "mildly costly" into "fatal".
- **The drawdown column at 1.0 R is not an independent finding.** 649 R is the
  negative mean compounding over 52,000 trades, not a separate risk effect. Do not
  read it as "tight stops cause drawdown".

**The one thing tight stops genuinely buy is a smaller worst day** (−13.9 R at 1.0 R
against −18.6 R with no stop, and improving monotonically as the stop tightens). For
a challenge that is not a footnote: the **daily loss limit** is precisely the
constraint that a worst-day number binds against, while the profit target binds
against expectancy. So the two challenge rules pull the stop in opposite directions,
and the correct choice is an explicit trade-off, not an optimisation of either alone.

**Operational recommendation on the current evidence: use the widest stop the
challenge's per-trade and daily-loss budget permits — 3.0 R if it fits, 2.0 R as a
compromise — and never below 1.5 R.** Achieve daily-loss protection through position
size and a daily trade cap instead, which cost expectancy proportionally rather than
asymmetrically.

### The one-minute delay

| Signal | delay | mean pips | mean R | cluster t |
|---|---:|---:|---:|---:|
| gated | 0 | 0.269 | 0.034 | 7.44 |
| gated | 1 | 0.193 | 0.024 | 5.36 |
| rsi3070 | 0 | 0.235 | 0.024 | 6.46 |
| rsi3070 | 1 | 0.170 | 0.019 | 4.52 |

**72% of the pip edge and 71% of the R edge survive a one-minute entry delay.** This
is materially better than the 15% retention that killed the freshness component on
the fixed clock, and it is the run's one genuinely encouraging result: the event
clock's edge is not a first-traded-minute artifact in the way the scheduled clock's
was. It is still a real decay and it still means execution latency is a first-order
design constraint.

---

## B. Arm 3 — cross-pair coherence: REJECTED

### The feature

All four pairs are quoted against USD, so a USD repricing moves all four the same
way. For each pair, `u = trailing 30-minute log return / trailing 30-minute realised
volatility` (signed, scale-free), then

`coh = sign(own u) × mean(u of the OTHER three pairs)`,

turned into a causal same-slot percentile over 90 prior sessions. Own pair is
excluded from the basket, so the feature cannot mechanically restate `|z|` — and it
does not: Spearman(coh, `|z|`) is **0.10-0.13** on the gated signal and **−0.003 to
+0.04** on RSI 30/70.

High coherence = the pair is moving with the basket (a broad USD move, which the
mechanism says should continue). Low = idiosyncratic (which the mechanism says should
be safe to fade). The preregistered prediction was **T1 > T3**.

### Result

Gated signal, primary stop, median across pairs:

| Cell | per year | stopped | mean pips | mean R | risk unit | cluster t | worst-5% |
|---|---:|---:|---:|---:|---:|---:|---:|
| T1 idiosyncratic | 1,460 | 8.0% | 0.266 | **0.035** | 7.93 | 4.35 | −3.54 |
| T2 | 1,460 | 7.9% | 0.261 | 0.030 | 8.27 | 3.78 | −4.20 |
| T3 broad USD | 1,460 | 7.9% | 0.279 | **0.031** | 7.75 | 3.78 | −4.05 |

Per pair, the gap `T1 − T3` in mean R:

| Pair | T1 | T2 | T3 | gap R | gap pips |
|---|---:|---:|---:|---:|---:|
| EURUSD | 0.0361 | 0.0299 | 0.0429 | **−0.0068** | −0.052 |
| GBPUSD | 0.0592 | 0.0291 | 0.0316 | **+0.0276** | +0.247 |
| AUDUSD | 0.0183 | 0.0265 | 0.0278 | **−0.0095** | −0.043 |
| NZDUSD | 0.0345 | 0.0330 | 0.0301 | +0.0044 | +0.023 |

| Criterion | Result |
|---|---|
| 1. T1 beats T3 in ≥3/4 pairs, median ≥ +0.02 R | **FAIL** — median −0.0012 R, 2/4 |
| 2. ≥50% retained under the volatility-matched split | **FAIL** — the gap changes sign (retention −0.60) |
| 3. Beats the rate-matched own-`|z|` control in ≥3/4 | PASS (+0.0031 R, 3/4) — but on an effect that is itself zero |
| 4. Real gap outside the re-pairing null in ≥3/4 | **FAIL** — 1/4 |

Supporting evidence, all pointing the same way:

- **The quintile profile is flat and non-monotone**: 0.034 / 0.032 / 0.029 / 0.035 /
  0.030. There is no dose-response.
- **In pips the ranking inverts** — T3 pays 0.279 against T1's 0.266 — while in R
  units T1 is nominally ahead. The implied risk unit differs (7.93 against 7.75), so
  this is the risk-unit artefact of `LEARNINGS.md` 2026-08-04 appearing again. Both
  readings are inside noise; the point is that neither is stable enough to trade.
- **The re-pairing null is clean and the test was adequately powered.** With the
  other three pairs' state drawn from a different date at the same slot and era, 200
  draws, the null centres at **+0.0001 to −0.0008 with sd 0.010-0.013**. A real
  +0.02 R effect would have sat about 2 sd outside it. The nulls did not fail to
  detect an effect; there was no effect to detect.
- **RSI 30/70 agrees and is slightly worse**: median gap −0.0031 R, 2/4 pairs, and it
  fails the own-`|z|` control too (1/4).

### GBPUSD, and why it is not promotable

GBPUSD is the one pair that behaves as predicted: +0.0276 R, and its re-pairing null
gives frac ≥ real of **0.015**. Taken alone that reads as a result. It is not one:

- two of the other three pairs go the **wrong way**, which is a different failure from
  "underpowered". Noise gives noisy zeros; it does not usually give confident
  inversions in a 4-cell panel;
- these are four USD-quoted pairs, i.e. correlated tests, so 1/4 at p = 0.015 is
  weaker than it looks;
- the mechanism, if real, should be *stronger* on the more idiosyncratic pairs, and
  the two commodity pairs are exactly where it fails.

Recorded as a curiosity. It would need an independent instrument (a non-USD cross, or
CME 6B against 6E) before being taken seriously, and this project has already had one
pattern that fit 3/3 markets die on 4 fresh ones (`LEARNINGS.md` 2026-08-03).

### Era

The late era is weak for every cell, which is a system-level fact rather than a
coherence result: gated base at the primary stop pays **0.329 pip / 0.044 R (t 7.13)
early** against **0.123 pip / 0.014 R (t 1.81) late**.

---

## C. Arm 4 — time-based non-reversion exit: REJECTED

### The rule

At elapsed minute `N`, observe `close(i+N)`; if the position P&L is not positive,
exit at `open(i+1+N)`; otherwise hold to 30 minutes. The compulsory stop stays live
and takes precedence. Primary cell `N = 10`, condition `P&L ≤ 0`.

### Result

Gated signal, median across pairs, primary stop:

| Arm | triggered | early exit | mean pips | mean R | hit | worst-1% | worst-5% | max DD (R) |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| base, hold 30 | — | 7.9% | **0.278** | **0.037** | 0.534 | −1.108 | −3.548 | 111 |
| time exit N=10, P&L ≤ 0 | 45.8% | 46.9% | 0.231 | 0.032 | 0.390 | −1.043 | −3.232 | 86 |
| CTRL3 unconditional exit at 10 | — | 100% | 0.230 | 0.032 | 0.541 | −1.016 | −2.977 | 55 |
| CTRL1 matched-rate stop (0.64 R) | — | 47.0% | −0.143 | −0.039 | 0.433 | +0.763 | +2.526 | 2,171 |

Per pair, mean R:

| Pair | base | time exit | vs base | vs matched stop | vs random time |
|---|---:|---:|---:|---:|---:|
| EURUSD | 0.0379 | 0.0329 | −0.0050 | +0.0685 | −0.0017 |
| GBPUSD | 0.0428 | 0.0339 | −0.0088 | +0.0485 | −0.0038 |
| AUDUSD | 0.0272 | 0.0298 | +0.0026 | +0.0725 | +0.0026 |
| NZDUSD | 0.0358 | 0.0315 | −0.0043 | +0.0709 | −0.0026 |

| Criterion | Result |
|---|---|
| 1. Beats hold-to-30 in ≥3/4 by ≥ +0.02 R | **FAIL** — median −0.0047 R, 1/4 |
| 2. Beats the matched-rate tighter stop in ≥3/4 | PASS (+0.070 R, 4/4) — see below, this proves nothing about the time exit |
| 3. Beats the matched-rate random-time exit in ≥3/4 | **FAIL** — median −0.0021 R, 1/4 |

### The decisive comparison, and why criterion 2 passing is not evidence

**Criterion 3 is the one that settles it.** Exiting a *randomly chosen* 46% of trades
at minute 10 performs **the same or better** than exiting the 46% that had not yet
reverted (median −0.0021 R against the conditional rule, 50 draws). The condition
carries no information: not having reverted after 10 minutes says nothing about the
next 20.

The unconditional control makes the same point from the other side: exiting
**everyone** at minute 10 gives 0.032 R, identical to the conditional rule's 0.032 R.
Three ways of shortening the average holding period, three identical answers. What is
being measured is exposure, not selection.

**Criterion 2 passes by a wide margin and must not be read as support.** The
rate-matched stop had to be set at 0.64 R to terminate the same 47% of trades early,
and a 0.64 R stop is catastrophic (−0.039 R, and every tail metric flips sign because
total gross goes negative). All this shows is the section-A finding again: a tight
price barrier is far more destructive than any time-based exit at the same
termination rate. It is a fact worth having — **if you must shed exposure, shed it on
the clock rather than by tightening the stop** — but it is not evidence that the
non-reversion condition works.

### The tail did improve, and it still does not help

The rule does what it was designed to do. Worst-5% share improves from −3.548 to
−3.232, worst-1% from −1.108 to −1.043, max drawdown from 111 R to 86 R, worst day
from −15.6 R to −11.7 R. The problem is that the random-time control achieves the
same improvement, so **the tail reduction is bought with exposure, not with
information** — the turnover-lever signature of `LEARNINGS.md` 2026-07-20.

Hit rate falls from 0.534 to 0.390, which is the mechanical fingerprint: the rule
converts a large block of trades that would have recovered into small realised
losses.

Neither `N` nor the condition rescues it. Across `N ∈ {5, 10, 15, 20}` and both
conditions, every cell sits at 0.030-0.036 R against the base's 0.037, and the
`P&L ≤ −0.25 R` variant — which triggers on 29% rather than 46% — is uniformly
closer to the base simply because it does less.

---

## What this changes

| Claim | Status after this run |
|---|---|
| Fixed `:29`/`:59` decision clock | **Retired.** Replaced by an event clock with enforced non-overlap. Rule-23 reproduction against the published crossing figures passes on 4/4 cells. |
| Cross-pair coherence as a trending-regime gate | **Rejected.** No effect, adequately powered null, wrong sign on 2/4 pairs. |
| Time-based non-reversion exit | **Rejected.** Indistinguishable from a random exit at the same rate. |
| "Tail control, not entry selection, is where the leverage is" (`RSI_MEAN_REVERSION_PROGRAMME_REPORT.md`) | **Qualified.** True that the tail dominates gross, but three separate tail-control devices — a tighter stop, a conditional time exit, an unconditional shorter horizon — all cut expectancy by at least as much as they cut the tail. Tail control is available and it is not free. |
| Stop sizing | **Promoted to the top of the list.** Monotone, 4/4 pairs, and larger than either component tested here. |

The surviving system is unchanged in content — the ATR(14)/ATR(50) same-slot
expansion gate with a plain fixed `|z| ≥ 1.5` threshold — but is now specified on an
event clock with non-overlap and a wide compulsory stop.

---

## Limitations

- **The spread is still unmeasured**, and it is now decisive rather than merely
  important. The gated event strategy grosses **0.269 pip per trade at 4,380 trades
  per pair per year** under the primary stop. At a 0.2 pip round trip that is roughly
  +300 pips per pair per year; at 0.5 pip it is **−1,010**. The entire question is a
  number this project has never measured, and the event clock's higher trade count
  makes the sensitivity worse, not better, than on the fixed clock.
- **No null was run on arm 4** (rule 17). Its three degenerate controls are the
  substitute; this was declared in the spec, not discovered afterwards. Arm 3 does
  have a proper re-pairing null.
- **The late era is weak across the board** — gated base 0.123 pip / t 1.81 in
  2021-2023 against 0.329 / t 7.13 in 2012-2020. Nothing here is promoted on the
  strength of the early nine years, but the base itself now needs that explained.
- **Four USD-quoted pairs are correlated tests**, closer to two effective independent
  observations than four.
- **`sigma` is the trailing RV(30) unit.** The causal expected-slot unit was declared
  as a sensitivity and was not run; the published sweep found the two give the same
  picture on the fixed clock, and that has not been re-verified on the event clock.
- **Stop slippage is a flat 1 pip.** Real slippage widens with volatility, which
  would make the tight-stop cells worse still and the ranking more, not less,
  monotone.

## Decisions

1. **Adopt the event clock with enforced non-overlap.** It removes the documented
   phase selector and its base edge retains 72% under a one-minute delay.
2. **Set the compulsory stop as wide as the challenge risk budget allows** (3.0 R if
   it fits, 2.0 R as a compromise, never below 1.5 R), and control daily loss with
   size and a trade cap rather than stop tightness.
3. **Close both cross-pair coherence and time-based non-reversion exits.** Neither
   needs a follow-up; the nulls and degenerate controls were adequately powered.
4. **Measure the bid/ask spread before any further signal work.** Every remaining
   open question is downstream of it, and at 4,400 trades per pair per year the
   strategy is now more cost-sensitive than at any earlier point in this project.

## Evidence

- Spec `RSI_COHERENCE_TIMEEXIT_SPEC.md` (frozen before both runs).
- Engine `_rsi_stop_engine.py`; checks `_test_rsi_stop_engine.py` (17 passing,
  including rule-3 entry-bar inclusion, rule-5 gap-through fills, adverse slippage on
  both fill kinds, the short-side mirror, and that a breach at the exit bar does not
  fire).
- Arm 3: `_run_rsi_coherence_gate.py` → `rsi_coherence_gate_results.json`,
  `rsi_coherence_cells.csv`, `rsi_coherence_null.csv`.
- Arm 4: `_run_rsi_time_exit.py` → `rsi_time_exit_results.json`,
  `rsi_time_exit_cells.csv`.
- Reproduce with `python -u _run_rsi_coherence_gate.py` and
  `python -u _run_rsi_time_exit.py` from `forex/exploration_1`.
