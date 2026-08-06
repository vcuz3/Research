# RSI mean-reversion programme — frozen specification (Arms 0-3)

## Origin and status

External commentary proposed a volatility-aware redesign of the RSI mean-reversion
work: regime detection upstream of the stress calculation, rolling kurtosis as a
secondary filter, vol-of-vol to separate snap-back from regime change, and
vol-adaptive thresholds. This spec translates that into preregistered arms,
declaring in advance which claims are already answered and which are live.

Written before any arm is run, per rule 24. Arm 0 is run first and gates the rest.

## Already answered — not retested

1. **"RSI treats every unit of displacement equally."** False about the indicator.
   `RSI(14) = 50 + 50·A(dp)/A(|dp|)` exactly: an average signed price change over
   an average absolute price change. It is already a displacement-over-scale
   ratio. See `futures/forex/vwap_exploration` EXP-0006 (RSI is the trailing
   return re-normalised) and `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md` §2.
2. **"Add a regime gate upstream."** A fixed threshold on a regime feature is a
   time-of-day selector in this workspace by three independent routes
   (`ai_shared_memory/LEARNINGS.md` 2026-07-27, and both 2026-08-03 entries). The
   supported repair is a same-slot z-score or percentile, not a gate. Any arm
   below that thresholds a regime feature must report per-slot selection-rate CV
   and compare at matched global selection rate.
3. **"VEI flags expansion, MRSI identifies the peak."** Tested and rejected in
   `RSI_SURPRISE_ACCELERATION_INTERACTION_REPORT.md`: VEI(10/50) hurt median gross
   P&L, and the proposed nonlinear synergy resolved to a main effect of RV(5).

## Standing controls for every arm below

- **No-RSI degenerate control.** Every regime claim must beat the same statistic
  computed on the raw trailing 30-minute return, with RSI removed from the
  pipeline. Established as necessary by `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md`
  §2. Note the review addendum to that report: reproducing a gradient without RSI
  establishes a generic short-horizon-reversion channel, it does **not** establish
  that RSI carries no incremental interaction. A controlled clustered rank
  regression (RSI × regime, controlling for trailing 1m and 30m returns and both
  return × regime interactions) is the arbiter when the two disagree.
- **Redundancy pre-screen.** Before any IC or P&L number is computed for a *new*
  regime feature, report its within-slot Spearman against the same-slot percentile
  of its own numerator, plus frozen top-bin Jaccard overlap. A within-slot rho at
  or above 0.90 means near-redundant for the within-slot rank estimand and the
  feature is dropped without further work.
- **Matched selection rate.** Any threshold comparison is made at identical global
  selection rate, or it is a selectivity dial rather than a result.
- **Holdout.** 2024+ stays sealed for every arm in this spec.

## Shared frozen setup

Unchanged from `RSI_BROAD_REGIME_SWEEP_SPEC.md`: EURUSD, GBPUSD, AUDUSD, NZDUSD
one-minute midpoint OHLC, 2012-2023; New York 17:00 session boundary; decisions on
completed half-hours at `:29`/`:59`; era split 2021-01-01 with pair-specific
cutpoints fitted on 2012-2020 and applied unchanged after.

The canonical regime variable for this programme is `rv_30m_pct_90d`, the causal
same-slot percentile of trailing 30-minute realized volatility. Per the audit
review addendum, `rv_5m_pct_90d` is retained as a **distinct** canonical level,
not a duplicate. The withdrawn `log(RV/E[RV])` "surprise" parameterisations are
not used.

Inference is session-clustered throughout. IC means within-slot Spearman of the
feature against the signed forward return; more negative is stronger reversion.

---

## Arm 0 — Is this a first-traded-minute effect? (gating arm)

### Mechanism under test

Every decision is taken at `:29`/`:59` and entered at the next one-minute open,
which is the `:00`/`:30` open. `RSI_CLOCK_CONFOUND_REPORT.md` established that
phase `:29` is rank 30/30 among the 30 half-hour phases across two vendors, and
that the advantage is concentrated in the **first traded minute**. If the RSI
reversion measured throughout this project is largely that first minute, then
every regime refinement in Arms 1-3 is decorating a microstructure artifact.

### Exact change

Delay both entry and exit by `d` minutes, holding the 30-minute holding period
fixed. Baseline `d = 0` is entry at `open(t+1)`, exit at `open(t+31)`. The ladder
is `d ∈ {0, 1, 2, 3, 5}`. Exactness of both legs is required at every `d`, so
coverage is recomputed per delay and reported.

Nothing else changes: same decisions, same RSI, same regime variable, same
quintiles.

### Primary metric

The Q5−Q1 gradient in IC strength across frozen `rv_30m_pct_90d` quintiles, at
each delay — that is, the size of the regime effect itself, not the level of
reversion. Reported for `ic_rsi` and for both no-RSI controls.

### Kill test (declared before running)

Let `G(d)` be the median across the four pairs of the Q5−Q1 IC-strength gradient
at delay `d`.

- **Retire the family** if `G(1) / G(0) < 0.50`. The regime effect would then be
  majority first-minute, and the RSI framing should be abandoned rather than
  refined. Arms 1-3 are not run.
- **Proceed to Arms 1-3** if `G(1) / G(0) ≥ 0.50`.
- Between those, additionally require that the overall reversion level (pooled IC
  at `d = 1`) retains at least half its `d = 0` strength; if the gradient survives
  but the level does not, the effect is real but too small to build on and the
  verdict is watch-only.

The `d ∈ {2, 3, 5}` rungs are sensitivity, not part of the decision rule. A
gradient that recovers at `d ≥ 2` after collapsing at `d = 1` is to be treated as
noise, not as evidence of a delayed effect.

### What would make this arm uninformative

If coverage drops materially with `d` (missing minutes at `t+31+d`), the delayed
cells are a different sample. Coverage per delay is therefore a reported
diagnostic and a drop beyond about two percentage points invalidates comparison.

---

## Arm 1 — Kurtosis and vol-of-vol: redundancy pre-screen only

Run **only if Arm 0 passes.** Two candidate features:

- rolling kurtosis of one-minute returns over the trailing 30 minutes;
- vol-of-vol, the trailing dispersion of the realized-volatility series itself —
  distinct from the ratio of two volatility windows, which is the already-rejected
  acceleration feature.

Pre-screen first: within-slot Spearman against `rv_30m_pct_90d` and against the
same-slot percentile of the feature's own numerator, plus top-bin Jaccard.

**Kill test:** within-slot rho at or above 0.90 against an existing canonical
feature drops the candidate with no further work. Kurtosis at a 30-observation
window is a fourth moment and is expected to be dominated by sampling noise; the
pre-screen is cheap and is the whole point.

---

## Arm 2 — Continuation versus snap-back at decision time

Run **only if Arm 0 passes.** This is the highest-value arm.

### Mechanism under test

The project's dominant loss mechanism is already measured: crossings into 21-45
minute extreme runs average **−17.4 pip**. The tempting split — by whether the
extreme survived to the next checkpoint — is not a filter, because survival is not
known at the crossing (`LEARNINGS.md` 2026-08-04, method note). The live question
is whether anything **observable at decision time** separates "stretched and about
to revert" from "stretched because a regime is changing".

### Exact change

Target is the binary label "the extreme persisted past the next checkpoint",
constructed after the fact but predicted only from decision-time information.
Candidate separators: vol-of-vol, rolling kurtosis (if either survives Arm 1),
trailing efficiency ratio, and realized-volatility acceleration.

### Kill test

If no candidate reaches an out-of-sample AUC meaningfully above 0.50 under
session-clustered inference, the continuation tail is unavoidable at this decision
clock and the strategy family is closed regardless of entry quality. Record that
as a NO-GO and stop; a negative result here answers the programme.

Per rule 15, any exit-geometry change arising from this arm must be evaluated
against a fixed-horizon entry-information diagnostic so that entry information and
exit design are not confounded.

---

## Arm 3 — Vol-adaptive thresholds at matched selection rate

Run **only if Arm 0 passes.** Replace the fixed RSI 30/70 cut with a threshold
expressed as a function of the same-slot volatility percentile.

**Mandatory control:** compare against fixed 30/70 at identical global selection
rate. Report per-slot selection-rate CV for both, per `LEARNINGS.md` 2026-07-27,
to show the adaptive version is better calibrated rather than merely more or less
selective.

**Kill test:** no improvement in IC or in cost-stressed P&L at matched selection
rate, or a per-slot selection-rate CV no better than the fixed cut, rejects.

---

## Reporting rules for all arms

- Gross and cost-stressed P&L reported side by side; midpoint bars are not an
  execution claim and no arm may present a deployment verdict without a bid/ask
  model.
- Effects reported in pips against an explicit round-trip assumption, per era.
- Vote counts across pair-era cells are to be reported with the caveat that four
  of eight cells are the cutpoint-fitting era and that AUDUSD/NZDUSD and
  EURUSD/GBPUSD are not independent draws; effective sample is nearer two or three
  than eight.
- A NO-GO on any arm is a successful outcome and is written up, per rule 25.

## Evidence

- Arm 0 reproduction: `_run_rsi_arm0_entry_delay.py`
- Arm 0 results: `rsi_arm0_entry_delay_results.json`
- Prior work this spec depends on: `RSI_REGIME_REDUNDANCY_AUDIT_REPORT.md`
  (and its review addendum), `RSI_CLOCK_CONFOUND_REPORT.md`,
  `RSI_BROAD_REGIME_SWEEP_SPEC.md`
