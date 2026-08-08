# exploration_4 — Baseline Mean-Reversion Book for USD-major Spot FX

**Status:** planned, not built. This document is the build spec for the agent that
implements it. Read it end-to-end before writing code.

**Author of plan:** research design session, 2026-08-08.
**Builder:** _to be assigned._
**Reviewer:** _to be assigned (must not be the builder)._

---

## 0. Purpose and the one rule that governs this project

Build **one honest, pre-specified, naive mean-reversion baseline** and measure its
efficacy — nothing else. This is deliberately the *degenerate* mean-reversion
strategy: fade a standardized displacement, exit on reversion or a compulsory stop.

**Do not tune it. Do not add regimes, cross-pair features, vol-scaling of the
entry, or model layers.** Those are overlays that a *later* project holds up
against this frozen book. The entire value of this project is that it produces a
book whose contribution is a number you can trust, because it was frozen before
anyone looked at regime splits.

The ordering this project deliberately follows (agreed in design):
**describe → freeze a naive baseline → (later) post-hoc regime labels as overlays
→ (later) promote only survivors.** This project is the middle step only.

A baseline that is itself the winner of a sweep would launder overfitting into a
story when it is later split by regime. So the parameters below are **frozen by
fiat**, not chosen by search. If a parameter feels arbitrary, that is correct and
intended; do not "improve" it.

---

## 1. Data — read this before anything

- **Location:** `forex/data/clean/{PAIR}_1m_clean.parquet`
- **Pairs (the four available USD majors):** `EURUSD, GBPUSD, AUDUSD, NZDUSD`.
  Treat as **~2 effective independent** series for inference (they are highly
  correlated USD-quoted majors). There is **no USDJPY** in this archive; do not
  invent it.
- **Content:** 1-minute **midpoint** OHLC. **`volume == -1` throughout** — there is
  no volume and no bid/ask feed in this project. Consequences you must respect:
  - You cannot measure the real spread. **The cost side is a curve, not a number.**
    Report a **breakeven round-trip pip** and the gross/cost/net by era. See §6.
  - Any feature requiring volume (VWAP with real volume, order flow) is off-limits;
    the baseline does not use volume anyway.
- **Data-quality gate (Rule 9a, mandatory):** before interpreting any result, emit
  a short data-quality report (`reports/DATA_QUALITY.md`) covering, per pair and
  per UTC hour: bar/session coverage, missing-minute and gap counts, duplicate and
  out-of-order timestamps, and — for the rolling features in §3 — how often the
  window is under-populated and what the construction does when it is. A feature
  that silently nulls/drops decisions because of a coverage rule is a **reportable
  finding**, not an implementation detail. Quantify how many decision points it
  removes, per era and per UTC hour, and confirm the exclusion is causal.

---

## 2. Reuse the audited engine — do not reimplement fills, costs, P&L, or metrics

All of the following already exist and are audited in `forex/exploration_1/`.
Import them; do not rewrite them. (Several past false results in this workspace
were construction bugs in bespoke feature/fill code, not the thesis.)

| Need | Module (in `forex/exploration_1/`) | Key functions / constants |
|---|---|---|
| Single-barrier stop fills | `_rsi_stop_engine.py` | `load_minutes`, `build_features`, `ohlc_arrays`, `select_events`, `extract`, `shift_paths`, `simulate`, `metrics`, `years_of`, `drawdown_R`, `PIP` |
| Triple-barrier (TP+SL+timeout) fills with **adverse resolution** | `_bracket_engine.py` | `simulate_bracket` (returns `pnl_pips, kind` where kind ∈ {−1 stop, 0 timeout, 1 target}) |
| Parametrised causal cost / breakeven | `_cost_model.py` | round-trip pip curve keyed by pair/UTC-hour/era/scenario/vol; sweep `scenario` and report breakeven |
| High-impact news times (blackout) | `_run_rsi_axis6_calendar.py` | `high_impact_times`; source table `forex/data/macro/fx_macro_events.parquet` |
| Panel constants | `_run_rsi_broad_regime_sweep.py` | `PAIRS`, `ROOT`, `DATA`, `PIP` |

**Path-indexing convention (from `_bracket_engine.py` / `_rsi_stop_engine.py`):**
in the extracted path arrays, column `m` is bar `i+1+m`; **entry is `open(i+1) =
O[:,0]`**; the position lives through bars `0 .. horizon-1`; a timeout exits at
`O[:, horizon]`. This convention already enforces "enter at next-bar open, not the
signal-bar close" — keep it; it is what removes the shared-decision-bar reversion
artifact (LEARNINGS §6).

If a needed function turns out to be tightly coupled to RSI-specific code, **copy
the minimal audited core into `exploration_4/` and add a trade-level parity test
against the exploration_1 original** — do not fork silently.

---

## 3. The frozen strategy specification

**Feature — standardized displacement (no anchor).** Fade the trailing return,
standardized by trailing realized vol. (Prior work established that a fancy anchor
— VWAP/TWAP/open/prior-close — is a noisier proxy for exactly this, and that
`|z|` depth is a near-sufficient statistic; RSI(14) as the primitive was rejected
3/3. Do not reintroduce RSI or an anchor.)

```
r_trail  = close_t / close_{t-n} - 1          # trailing return, n bars
sigma    = rolling_std(1-bar returns, window=m)   # trailing realized vol, plain rolling
z_t      = r_trail / (sigma * sqrt(n))        # scale-free displacement
```

**Frozen parameters (by fiat — do NOT sweep):**

| Symbol | Value | Meaning |
|---|---|---|
| bar | 5-minute | resample 1m→5m with a roll/tz-safe resampler; keep lookbacks in **time units**, not bar counts, if you change bar size (LEARNINGS §2) |
| `n` | 6 bars (30 min) | trailing-return window |
| `m` | 100 bars | trailing-vol window; use a **fractional floor** (e.g. `min_periods = 0.9·m`), never strict `min_periods == m` (strict = hidden time-of-day liquidity filter, LEARNINGS §2) |
| `k` | 2.0 | entry threshold on `|z|` |
| stop | 1.5 · σ (in the same units as the displacement) | **compulsory single barrier**, frozen at entry |
| target | reversion to `z = 0` | chosen 2026-08-08; asymmetric vs the stop → see mandatory diagnostic §5 |
| slippage | use the same adverse-slippage convention as `_rsi_stop_engine.simulate` / `_bracket_engine` | applies to the stop |

**Entry — first-crossing (event-driven) clock.** Enter when `|z_t|` **first
crosses** `k` (not "every bar it is beyond k", and **not** a fixed wall-clock time
— a fixed time clock is forbidden for this project). Fade: **short if z > +k, long
if z < −k.** Fill at **next-bar open** (the engine's `O[:,0]` convention).
Enforce **one position per pair at a time** (non-overlap; use `select_events`
overlap/cooldown controls).

**Exit — reversion target OR compulsory stop, both frozen at entry.** Target = `z`
returns to 0 (displacement gone). Stop = 1.5σ adverse. No time stop (would need a
clock); if a hard cap is unavoidable for path extraction, make it an **event**
(e.g. session boundary) with a generous horizon and report it, do not make it a
tight minute count.

**News blackout (standing veto).** Veto any entry inside the high-impact-release
window via `high_impact_times`. Apply it as an entry filter, **and separately keep
the un-vetoed book labeled** so §7 can report what the blackout removed. Use the
entry-proximity form already validated (see `_run_rsi_news_blackout.py`); a ±15–30
min window is the established operating point.

---

## 4. Estimand, accounting, inference

- **Headline metric:** **per-signal mean net R** (R = P&L in stop-risk units).
- **SE:** **block cluster-robust**, clustered by **UTC day/session**. Report the
  cluster-robust t. **Never** use session-averaged R as the headline — when signal
  count is endogenous to the outcome it inverts the sign (LEARNINGS §4; this exact
  trap is confirmed on GBPUSD here). You may report the session-averaged number
  *alongside* only to show the divergence, and print `corr(block mean, block
  count)` (read its magnitude).
- **Accounting:** one position per pair; daily P&L is the sum of realized/marked
  position P&L, never the mean of that day's trades.
- **Report per pair and pooled**, and **by era** (spreads compressed 2012→2023, so
  a single long-sample normalization flatters recent eras — Rule 19).
- **Report the three Sharpes** (zero-day, trade-days-only, vol-targeted) per the
  standing preference.

---

## 5. Mandatory diagnostics (build into the same run, not as afterthoughts)

Because the target (reversion to 0) is **asymmetric** against the 1.5σ stop, a
positive headline is not admissible on its own. Both of these run in the same pass:

1. **Entry-information diagnostic (Rule 15).** Re-run the identical entries through
   a **symmetric bracket** (target at the same vol-distance as the stop, via
   `_bracket_engine.simulate_bracket`) and through a **fixed-horizon forward
   return**. If the edge vanishes without the reversion-target geometry, it was the
   exit design, not the entry — report that conclusion explicitly.
2. **Random-exit control at matched exit rate.** Prior work here found "exit if not
   reverted" was **indistinguishable from a random exit** at the same rate. Draw
   random exits matched to the reversion target's realized exit-rate distribution
   (repeated draws; compare against the distribution, do not subtract one draw).
   The reversion target must beat this null to count.

---

## 6. Cost treatment (spread is unmeasured — this is non-negotiable)

Because `volume == -1` and there is no bid/ask, **do not report a single net
number.** Use `_cost_model.py` to:

- sweep the `scenario` (optimistic / base / pessimistic) and the vol term,
- report **gross, cost, and net separately, by era and by UTC hour**,
- report the **breakeven round-trip pip** — the spread at which net crosses zero.

Note the known tension already documented in `_cost_model.py`: this family's
activity can concentrate in hours the model prices as *most expensive* (the ~21:00
UTC rollover). Report where in the clock the trades and the costs land.

---

## 7. Pre-registered KILL TEST (write into `KILL_TEST.md` and freeze BEFORE running)

State this before the material run; it cannot be edited after seeing results.

- **Primary metric:** per-signal mean net R, cluster-robust t (clustered by day).
- **NO-GO if ANY of:**
  1. **Gross ≈ cost:** gross per-signal ≤ modeled round-trip at the *base* cost
     scenario → cost-model-dependent, not an edge (Rule 20).
  2. **Break-even win rate:** realized win rate sits at the algebraic
     `1/(1+RR)` of the frozen stop/target geometry → barriers are efficient, no
     entry edge (LEARNINGS §6).
  3. **Zero CI:** net mean-R cluster-robust CI includes 0.
  4. **Fails a mandatory diagnostic (§5):** edge disappears under the
     symmetric-bracket / fixed-horizon rerun, OR does not beat the random-exit
     null at matched rate.
- **A NO-GO is a successful outcome** (Rule 25). If it dies, record the negative
  result in `MEMORY.md` and `reports/FINDINGS.md`; do not leave a handoff implying
  a live edge.
- **Holdout discipline:** 2024+ is sealed per this project's convention. Fit /
  inspect on the consumed history; report the sealed segment separately and only
  once, at the end.

---

## 8. Deliverables

1. `reports/DATA_QUALITY.md` — the Rule 9a report (§1).
2. `KILL_TEST.md` — the frozen pre-registration (§7), committed **before** the run.
3. Run scripts in `exploration_4/` (prefix `_run_*.py`), importing the
   exploration_1 engine; each reproducible with a one-line command documented in
   its module docstring.
4. `reports/FINDINGS.md` — gross/cost/net by era and UTC hour, per-pair and pooled;
   the two mandatory diagnostics; the breakeven-pip curve; the three Sharpes; and
   the explicit kill-test verdict (GO / NO-GO / inconclusive with reason).
5. `MEMORY.md` — concise project state and handoff (already stubbed).
6. A row in `experiments/ledger.csv` (use `python tools/research_admin.py
   new-experiment ...`) registering the baseline run, builder, reviewer, and
   review status. Register **losers and failures too**.

Scope discipline: implement **the frozen baseline + the two mandatory diagnostics
+ the cost curve + the kill-test verdict, and stop.** No regime overlays, no
parameter sweeps, no model layers. Those belong to a follow-on project.

---

## 9. Review

Per the two-model workflow: a reviewer who is not the builder independently
inspects the frozen spec, the diff, the run command, the ledger row, and the
artifacts, and re-runs the kill test. Record both roles and the verdict in the
ledger and in `MEMORY.md`. Agreement between models does not substitute for the
executable diagnostics in §5 and the kill test in §7.
