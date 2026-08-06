# Exhaustion-threshold control and freshness component

Frozen specification: `RSI_THRESHOLD_FRESHNESS_SPEC.md`, written before execution.

## Verdict

Two arms were run against the surviving configuration of
`RSI_REGIME_GATED_SYSTEM_REPORT.md`. Both reach a clear answer, and both are
governed by the same mechanism.

1. **Component 2 (the vol-scaled exhaustion threshold) is rejected.** At matched
   selection rate it is **worse** than a plain fixed threshold — median −0.241
   pip on the trigger alone (0 of 4 pairs improved) and −0.172 pip with the
   expansion gate stacked (1 of 4). Its published +0.060 gain was a depth dial:
   the audited comparison ran the two rules at 632 and 1,724 signals per year.
2. **Freshness (time-in-zone) is a real, scale-free effect that is not
   deployable.** Fresh extremes pay **1.363 pip against 0.824** for the gated
   base and **0.183 R against 0.097 R**, monotone in age, 4 of 4 pairs, and it
   survives the era split. But only **15% of the pip gain survives a one-minute
   entry delay**, so it is a higher-resolution restatement of this project's
   first-traded-minute effect rather than a new component.
3. **The unifying result, and the most useful output of the run: every threshold
   rule tested had the same edge per unit of risk (≈0.10 R) and differed only in
   the size of the risk unit it selected.** A threshold that scales with a
   volatility variable is a *volatility selector*. Its pips-per-signal number
   then follows the volatility of the states it picks, mechanically. Comparing
   trigger rules in pips compares risk units; comparing them in R compares edges.

Nothing here is deployable and nothing opens the holdout. The practical
consequence is that the surviving system is now **component 1 only**, with a
plain fixed exhaustion threshold.

## Reproduction (rule 23)

The audited rows reproduce on the common sample to within 0.003 pip:

| Row | Published | Here |
|---|---:|---:|
| Fixed `\|z\| ≥ 1.5`, trigger only | 0.588 | **0.585** |
| Vol-scaled `\|z\| ≥ 1.5(1+vol_pct)`, trigger only | 0.648 | **0.650** |
| Vol-scaled + ATR expansion top 40% | 0.827 | **0.824** |

Signals per year 1,727 and 645 against the published 1,724 and 632. Data
2012-03-25 to 2023-12-29, 125,894-127,950 decisions per pair after requiring
`z`, `vol_pct`, `vei_atr_z` and the 30-minute target to be jointly defined.
**2024+ was not read.**

---

## Arm 1 — the vol-scaled threshold is a selectivity dial, pointed the wrong way

### Design

Each trigger is written as a score `s = |z| / g(vol_pct)`, and each rule keeps
the top `rate` fraction by its own score, so the rules are **exactly rate-matched
by construction**:

| Rule | `g(vol_pct)` | Intent |
|---|---|---|
| A — published | `1 + vol_pct` | require MORE stretch when volatility is high |
| B — degenerate | `1` | fixed depth, no volatility content |
| C — mirror | `2 − vol_pct` | require LESS stretch when volatility is high |

Score cutpoints fitted on 2012-2020 and applied unchanged.

### Kill test at the published operating point (keep 0.05)

Gross pips per signal, per pair, trigger only:

| Pair | A published | B fixed | C mirror | A−B |
|---|---:|---:|---:|---:|
| EURUSD | 0.817 | 0.825 | 0.885 | −0.009 |
| GBPUSD | 0.833 | 1.201 | 1.204 | −0.368 |
| AUDUSD | 0.477 | 0.699 | 0.905 | −0.222 |
| NZDUSD | 0.639 | 0.898 | 1.098 | −0.259 |
| **median** | **0.728** | **0.862** | **1.001** | **−0.241** |

**A beats B on 0 of 4 pairs.** With the expansion gate stacked, A−B is −0.172 and
1 of 4. The spec's gate was "≥ 3 of 4 pairs and ≥ +0.03 pip"; the result is on the
wrong side of zero. **Verdict: REJECTED as a selectivity dial.**

### The signature confirms the diagnosis

A−B across the whole frontier (median across pairs, trigger only):

| Keep rate | A | B | C | A−B |
|---|---:|---:|---:|---:|
| 0.02 | 0.817 | 1.200 | 1.344 | **−0.383** |
| 0.03 | 0.788 | 1.056 | 1.215 | −0.268 |
| 0.05 | 0.692 | 0.906 | 1.023 | −0.214 |
| 0.07 | 0.647 | 0.798 | 0.837 | −0.152 |
| 0.10 | 0.585 | 0.712 | 0.746 | −0.127 |
| 0.14 | 0.557 | 0.623 | 0.616 | −0.066 |
| 0.20 | 0.485 | 0.522 | 0.539 | −0.037 |

The deficit is **monotone in selectivity** and vanishes as the rules converge on
the whole sample. That is the shape of a rule whose only content is how deep it
cuts, and the published operating point sits at the deep end where the damage is
largest.

### What the volatility scaling actually does

The three rules have **the same edge per unit of risk** and the same hit rate:

| Keep 0.05, trigger only | A | B | C |
|---|---:|---:|---:|
| gross pips | 0.728 | 0.862 | 1.001 |
| **mean R** | **0.096** | **0.106** | **0.103** |
| hit rate | 0.558 | 0.571 | 0.574 |
| **implied risk unit (pips)** | **7.39** | **8.58** | **10.14** |

Across the whole frontier `A−B` in R units runs −0.011 to +0.009 and `C−B` runs
−0.013 to +0.003, with pair votes at 1-3 of 4 in both directions. **In scale-free
units the three rules are indistinguishable.** The entire pip difference is the
risk unit: the implied 30-minute move of the selected states runs 7.1-8.2 pips
for A, 7.7-10.4 for B and 8.0-11.7 for C.

The mechanism is now plain, and it is the opposite of the rule's intent.
Demanding *more* stretch when `vol_pct` is high makes the high-volatility states
hardest to trigger, so rule A systematically samples the **calmest** states — the
ones with the smallest pip moves — while this project's own established finding
is that reversion is *stronger* in high-RV states. Component 2 was fighting the
project's own regime result, and the depth increase hid it.

### Does the mirror rule win?

On pips, yes: C beats A on 4 of 4 pairs (median +0.400) and beats B by +0.117 at
keep 0.05, and it is the only rule whose late-era cluster t exceeds 3 (3.77
trigger only, 3.16 gated, against 2.4-2.7 for A and B).

**It should not be adopted, for a reason the frozen metric cannot see.** C wins
by selecting the most volatile states available, where a fixed pip cost is a
smaller share of the move — and it does **not** win in R units (C−B is −0.003 to
−0.013). Under the flat cost assumption used throughout this project that reads
as an edge. Under a realistic spread, which widens with volatility, it may be
entirely absorbed. This is rule 19 in its purest form, and it means the
unmeasured bid/ask now decides not only whether the system is viable but **which
threshold rule is correct**.

The defensible recommendation is therefore **B — no volatility scaling at all**.
It matches or beats A on both metrics, matches C in R units, has one fewer moving
part, and does not deliberately tilt the sample toward the widest-spread states.

---

## Arm 2 — freshness is real, scale-free, and mostly one minute

`age` = consecutive one-minute bars ending at the decision bar on which
`z ≤ −1.5` (long) or `z ≥ +1.5` (short) held, minus one. Runs reset at any
non-contiguous minute, so an age never spans a gap. 18-20% of gated signals are
fresh; median age 2 minutes, mean 3.5.

### Dose-response, gated system, entry at `t+1`

| Age (minutes) | signals/yr | gross pips | **mean R** | cluster t | hit rate |
|---|---:|---:|---:|---:|---:|
| **0 (fresh)** | 81 | **1.363** | **0.183** | 3.53 | 0.587 |
| 1-2 | 136 | 0.710 | 0.090 | 3.14 | 0.559 |
| 3-5 | 113 | 0.838 | 0.090 | 3.03 | 0.566 |
| 6-10 | 66 | 0.529 | 0.039 | 1.63 | 0.552 |
| 11-20 | 23 | 0.495 | 0.048 | 0.80 | 0.555 |
| all ages | 423 | 0.824 | 0.097 | 6.14 | 0.564 |

The canonical RSI 30/70 signal reproduces it independently — fresh 0.777 against
0.585 for all ages, decaying monotonically to 0.058 at age 11-20 — which
confirms the `scheduled_fresh` result in `RSI_RV_CLOCK_REGIME_REPORT.md` at
higher resolution.

**Unlike every rule in arm 1, this is not a volatility-scale effect.** The mean R
nearly doubles (0.183 against 0.097), the implied risk unit of fresh signals is
*smaller* than the base (6.6-10.5 against 6.9-10.5 pips), and age correlates
*positively* with volatility (Spearman +0.13 to +0.20 with `vol_pct`), so the
scale effect runs against the result rather than producing it.

### The four frozen criteria

| # | Criterion | Result |
|---|---|---|
| 1 | fresh beats stale in ≥3/4 pairs | **PASS** — 4/4, +0.63 to +0.73 pip |
| 2 | fresh beats rate-matched expansion tightening in ≥3/4 (pips) | **FAIL** — 2/4, median −0.010 |
| 3 | late-era delta positive | **PASS** — median +0.675, 3/4 pairs |
| 4 | ≥50% survives the one-minute delay | **FAIL** — **15%** retained |

**Criterion 2, and a disclosed metric problem.** Tightening the existing expansion
gate to the same 20% keep rate gives 1.393 pip against freshness's 1.363, so on
the frozen metric freshness fails. But the two arms are not comparable in pips:
the tightened expansion gate selects states with an **11.8-18.6 pip** risk unit
against freshness's **6.6-10.5**. In R units freshness wins **4 of 4 pairs**,
0.183 against 0.088. Recording both readings: the frozen criterion fails, and
switching metric after seeing the result would be a search, so this is a
**disclosed amendment and not a pass**. It is the same rule-19 mechanism as arm 1
— the "control" is itself a volatility selector.

**Criterion 4 is the one that matters.** Delaying entry and exit by one minute
with the holding period unchanged:

| | delay 0 | delay 1 | retained |
|---|---:|---:|---:|
| gated base | 0.824 | 0.375 | 46% |
| fresh (age 0) | 1.363 | 0.537 | 39% |
| **fresh − base** | **0.539** | **0.162** | **15%** |

In R units retention of the excess is better but still fails: 39%. A fresh
extreme is by construction a move that has just happened, so this is the
first-traded-minute effect of `RSI_CLOCK_CONFOUND_REPORT.md` measured on a new
axis, not a new component.

**A separate finding worth flagging, because it is about the system rather than
the component:** at delay 1 the gated base is **net −0.125 pip at a 0.5 pip
cost**, and the *only* cell that stays net-positive is fresh signals in the late
era (+0.282). The surviving system's net edge is delay-0 dependent.

---

## What this changes

| Component | Was | Now |
|---|---|---|
| 1. Expansion phase (ATR VEI, slot z, top 40%) | Works | Unchanged — not retested here |
| 2. Vol-scaled exhaustion threshold | Works | **Rejected.** Use a plain fixed threshold |
| 3. Kurtosis | Rejected | Unchanged |
| 4. Vol-of-vol | Rejected | Unchanged |
| 5. Dynamic z stop | Rejected | Unchanged |
| — Freshness (new) | — | **Real and scale-free, not deployable**: 85% is the first traded minute |

`RSI_REGIME_GATED_SYSTEM_REPORT.md`'s component-2 verdict and its Decision item 1
are **superseded**. The reported +0.060 pip gain is retracted: it is a depth
effect, and at matched depth the scaling costs 0.17-0.24 pip.

## Limitations

- **Consumed history throughout.** No holdout was opened.
- **No null** (rule 17). Both arms are comparisons between rate-matched rules on
  identical rows, not effect estimates against noise.
- **Selection.** Arm 1 is 3 rules × 7 rates × 2 stacks. All three rules and the
  primary rate were named in the frozen spec before execution, and the spec
  declared in advance that a rule-C win would be reported as the headline — but
  the frontier is still a search and the t-statistics are uncorrected.
- **Cost is assumed, never measured**, and this run raises the stakes: the
  ranking of threshold rules depends on whether the spread scales with
  volatility. Midpoint bars cannot answer that.
- **Rule C is not endorsed** despite winning the frozen metric, for exactly that
  reason. This is stated as a limitation rather than a result.
- **Effective sample.** EURUSD/GBPUSD and AUDUSD/NZDUSD are correlated; "4 of 4"
  is nearer two or three independent agreements. EURUSD is the consistent
  dissenter in both arms.
- The freshness late-era pass is carried by NZDUSD (+1.91) and AUDUSD (+1.03);
  EURUSD is negative (−0.14). Late-era cluster t for fresh signals is 1.64.
- Arm 1's cutpoints are fitted on the early era, which is nine of twelve years,
  so the "late era" columns are a weaker test than they look.

## Decision

1. **Drop the volatility scaling from the exhaustion threshold.** Use a fixed
   `|z| ≥ k` at the desired selectivity. The surviving system is component 1 plus
   a fixed trigger.
2. **Do not adopt the mirror scaling**, despite it winning on pips, until the
   spread is measured. Record it as the direction the evidence points if costs
   turn out not to scale with volatility.
3. **Do not adopt freshness as a component.** Record it as a confirmed,
   scale-free, 1.9x-in-R dose-response that is 85% first-traded-minute — the
   same fragility the clock work already documented, now measured on the gated
   system.
4. **Report mean R alongside mean pips for every future trigger comparison in
   this project.** Arm 1 shows the two metrics can rank three rules completely
   differently, and the pip ranking was the wrong one.
5. **Measure the bid/ask round trip, conditional on the signal state.** This was
   already the top item; it is now also the tie-breaker between threshold rules.
6. **2024+ stays sealed.**

## Evidence

- Frozen specification: `RSI_THRESHOLD_FRESHNESS_SPEC.md`
- Arm 1: `_run_rsi_threshold_control.py` → `rsi_threshold_control_results.json`,
  `rsi_threshold_control_frontier.csv`, `rsi_threshold_control_era.csv`
- Arm 2: `_run_rsi_freshness.py` → `rsi_freshness_results.json`,
  `rsi_freshness_buckets.csv`, `rsi_freshness_gates.csv`, `rsi_freshness_era.csv`
- Audited report: `RSI_REGIME_GATED_SYSTEM_REPORT.md`
- Related: `RSI_RV_CLOCK_REGIME_REPORT.md` (the `scheduled_fresh` result this
  arm reproduces), `RSI_CLOCK_CONFOUND_REPORT.md` (the first-minute effect),
  `RSI_MEAN_REVERSION_PROGRAMME_REPORT.md` (the threshold-depth sweep that
  motivated arm 1)
- Reproduce with `python -u _run_rsi_threshold_control.py` and
  `python -u _run_rsi_freshness.py` from `forex/exploration_1`.
