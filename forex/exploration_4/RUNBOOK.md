# exploration_4 — Run-book: Characterize → Freeze → Overlay → Promote

**Purpose.** Execute the market-first research arc for mean-reversion on USD-major spot
FX: describe the market, freeze one honest reference book, label it post-hoc with
candidate regimes as overlays, and promote only survivors. This run-book is the ordered
execution contract. Do the stages in order; each has an exit gate that must pass before
the next begins.

---

## 0. HANDOFF — read this first

**Position (2026-08-09):** **Stage A is complete**, including a same-slot addendum that
changed the recommended feature. **Stage B (EXP-0004) is the next action and has not
started.** Nothing is deployed, nothing is promoted, and no reference book exists yet.

| Stage | Experiment | State |
| --- | --- | --- |
| — | EXP-0001, stopped 5-min baseline | Closed **NO-GO**; superseded *as reference book* (constraint set changed) |
| A characterize | **EXP-0002** | **Done.** τ\* = 5 min, H\* = 240 min. Gate passed as *documented disagreement* |
| A addendum | **EXP-0003** | **Done.** Clock confound found and fixed; τ\* re-confirmed; one EXP-0002 finding retracted |
| B freeze reference book | **EXP-0004** | **NOT STARTED — start here** |
| C regime overlays | EXP-0005+ | Not started |
| D promote survivors | EXP-0006+ | Not started |

> **Numbering.** This file originally assigned EXP-0003 to Stage B. The ledger enforces
> `EXP-\d{4}`, so the Stage-A addendum took EXP-0003 and **Stage B is EXP-0004**.

**Review status: all three runs are `pending` independent review** (builder: Codex for
EXP-0001, Claude for EXP-0002/0003). Each `review.md` ends with a reviewer checklist. If
you are the reviewer, do that before building anything new.

### Where things are

| What | Path |
| --- | --- |
| Project state and carry-forwards | `MEMORY.md` ← **read after this file** |
| Stage-A market map | `reports/MARKET_CHARACTERIZATION.md` (carries a partial-retraction banner) |
| Stage-A addendum | `reports/SAME_SLOT_ADDENDUM.md` |
| Rule 9a coverage gate | `reports/DATA_QUALITY.md` |
| EXP-0001 findings (superseded as reference) | `reports/FINDINGS.md` |
| Frozen pre-specs | `experiments/hypotheses/HYP-0002.md`, `HYP-0003.md` |
| Run artifacts + reviews | `artifacts/runs/EXP-000{1,2,3}/` |
| Ledger | `experiments/ledger.csv` |
| Reusable primitives (tested) | `_stage_a_lib.py` |
| Stage-A runners | `_run_stage_a.py`, `_run_same_slot.py` |

### Commands

```powershell
python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider   # 25 tests
python -u forex/exploration_4/_run_stage_a.py        # EXP-0002, ~6 min
python -u forex/exploration_4/_run_same_slot.py      # EXP-0003, ~3 min
python tools/research_admin.py check --project forex/exploration_4
```

### What `_stage_a_lib.py` already gives you (do not rewrite)

`build_grain_bars`, `same_slot_moments`, `first_crossing`, `MinuteGrid`
(`path_complete_span`, `forward_extremes`, `extract_paths`), `accumulate_vr` /
`variance_ratio` (Lo–MacKinlay robust), `cluster_stats`, `profit_factor`,
`greedy_non_overlap`, `three_sharpes`, `session_codes` (DST-aware), `to_text_table`.
`_run_stage_a.py` adds `cell_frames` (pooled cells without a memory blow-up),
`cluster_summary` (vectorised cluster-robust SE), `attach_forward_outcomes` (both entry
arms), `attach_costs`, `nearest_event_minutes`. Every one of these is under test.

---

## 1. Constraint set for this arc

- **No compulsory stop.** EXP-0001 showed the mandatory 1.5σ stop was the dominant
  expectancy tax; it must not define the reference book.
- **No fixed-clock rule on entries** — event-driven decisions only.
- **News blackout** remains a standing veto (±30 min, high-impact releases for that pair).
- **Flat over the weekend** — force-close at the Friday session close (16:55 New York, the
  last attainable open); no positions across the weekend gap.

---

## 2. Standing facts — do not re-derive

**Data.** `forex/data/clean/{PAIR}_1m_clean.parquet`, pairs **EURUSD, GBPUSD, AUDUSD,
NZDUSD** (≈2 effective independent). **Midpoint OHLC; no `volume`; no bid/ask.** Spread is
unmeasured → cost is always a **breakeven-pip curve**, never a single net number
(`../exploration_1/_cost_model.py`). 2012-01-01 onward; **2024+ is a sealed holdout**,
touched once per stage at the end of that stage's report.

**Engine.** Reuse the audited code in `forex/exploration_1/`: `_rsi_stop_engine.py`,
`_bracket_engine.py` (adverse intrabar resolution, gap-through fills), `_cost_model.py`,
`_run_rsi_axis6_calendar.high_impact_times`. Import; do not reimplement fills, costs, P&L
or metrics. If a core is copied, add a trade-level parity test.

**Estimand everywhere.** Per-signal **mean R** with **day/session block cluster-robust**
SE. Never session-averaged R as the headline (it inverts sign when signal count is
endogenous). Report gross / cost / net **by era**, the breakeven round-trip pip, and the
**three Sharpes** (zero-day, trade-days-only, vol-targeted).

**Rule 9a.** Every data-load and feature-construction stage emits a data-quality report
(coverage per pair/era/UTC-hour, gaps, duplicates, under-populated windows, and how many
decisions any coverage rule removes). A silent null is a reportable finding.

### Established by Stage A — these cost real time to find

1. **`open[i] == close[i-1]` for 99.99998% of contiguous minutes.** "Enter at the next
   bar's open" does **not** separate the feature window from the outcome window — the
   entry price is the same *number* that ends the displacement. This manufactured
   **56–78%** of EXP-0002's measured reversion (paired t = −12.2). **Any study here whose
   feature window ends where its outcome window starts must run a one-bar-delay control,
   paired on the identical signal set and screened on the same span.**
2. **σ windows must be counted in tradable bars, not calendar bins.** Spot FX covers ~71%
   of calendar minutes, so a 0.9 `min_periods` floor on raw bins nulls σ everywhere — the
   first implementation produced *zero signals*. `build_grain_bars` already compacts.
3. **A trailing all-hours σ makes a fixed `|z|` cut a time-of-day selector.** EXP-0002's
   σ moved only 3.156→3.179 pips across all 24 UTC hours while real bar sizes vary 2.2×,
   so `|z| ≥ 2` fired on 0.96% of 04:00 decisions and 10.11% at 14:00 (CV 0.707). **Run
   `fire_rate` by slot and its CV on every threshold rule before reading any conditional
   result.** Same-slot z fixes it (CV → 0.119) and *improves* the signal.
4. **Ambient and conditional reversion rank timescales in OPPOSITE directions.**
   `VR(τ)` deepens with τ (0.948 at 5m → 0.869 at 120m, robust z −12 to −15) while
   `E[R | |z|≥2]` shrinks with it. Both are correct; they measure different objects.
5. **A fixed-pip slippage against vol-unit barriers is a grain selector.** In EXP-0002's
   view 3 the realised loss exceeded the nominal 1.0R stop by exactly `slippage/σ_τ` at
   all five rungs (agreement within 0.011R). Charge slippage in σ units when comparing
   grains, or compare only at matched σ.
6. **Naive always-long drift is ~0** at every horizon pooled (H=240: −0.081 pips, CI
   [−0.384, +0.222]). No overlay may be credited with a baseline tilt. London alone
   carries a real −0.84 pip/240min always-long tilt.
7. **Session differences in the fade are NOT established.** EXP-0002's thin-hours
   localisation was retracted by EXP-0003 as a clock artifact. Do not carry it as a prior.
8. **Known coverage items.** NZDUSD has late-era 18:00–19:00 UTC holes; the 17:00 NY
   rollover bar is unavailable (use 16:55); the strict H=480 completeness rule removes
   33–42% of signals, concentrated on windows spanning the weekend or the daily
   ~21:00–22:00 UTC hole — the long-horizon common sample is **not** hour-neutral.

---

## 3. STAGE A — COMPLETE (EXP-0002 + EXP-0003)

**What it decided:** decision grain **τ\* = 5 min**, holding-horizon cap **H\* = 240 min**,
on the **same-slot z** (see §4). Chosen by the rule frozen in `HYP-0002.md` §6 and applied
mechanically in `apply_grain_rule`, then re-confirmed under `HYP-0003.md` §4.

**Method, for reuse in Stage C.** Three corroborating views: (1) variance ratio `VR(τ)`
with Lo–MacKinlay heteroskedasticity-robust inference — strategy-free, level-free, and
scale-invariant to the vol level; (2) conditional extreme→anchor reversion in R units,
gross and net — the entry-information view; (3) gross-R profit factor from a bounded
double barrier with vol-unit barriers and RR fixed. Views 1 and 2 disagreed on direction
(fact 4 above) and the frozen rule takes view 2. View 3's *ranking* is invalid (fact 5);
its absolute reading — profit factor < 1 at every rung — stands.

**Headline numbers** (consumed 2012–2023, pooled, per-signal mean R, day-clustered):

- τ=5 same-slot, delay-1, H=240: **0.1056 R, CI [0.045, 0.166]** — the only rung whose CI
  excludes zero (τ=15 → 0.050, τ≥30 ≈ 0 or negative).
- Same-slot beats all-hours at matched trade count: **0.1056 vs 0.0651 R**, gross **0.383
  vs 0.244 pips**.
- **Best breakeven round-trip ≈ 0.38–0.40 pips against a 1.21-pip modelled base round
  trip, of which 0.70 pips is commission alone. Short by ~3×.**
- Sealed holdout, opened once: τ=5 H=240 gross 0.187 R, CI [−0.020, +0.393] — same sign,
  CI includes zero. Not confirmatory.

**Read `artifacts/runs/EXP-0002/review.md` §4 and `EXP-0003/review.md` §1 before using any
Stage-A number.**

---

## 4. STAGE B — Freeze the reference book (EXP-0004) ← START HERE

**Objective.** Freeze **one** honest mean-reversion book under the updated constraints.
This is the ruler every overlay is measured against. Whether it is GO or NO-GO is *not*
the point — a negative reference book is still a valid ruler. Do not tune it to PnL.

### 4.1 Frozen spec (parameters by fiat, from Stage A — not by search)

| Element | Value | Source |
| --- | --- | --- |
| Decision grain | **5-minute** epoch-anchored bars, complete-only | Stage A τ\* |
| Feature | **same-slot z**: `(ret_5 − μ_slot)/σ_slot` | EXP-0003 Q1/Q4 |
| Slot | UTC minute-of-day // 5 | `same_slot_moments` |
| Slot window | **90 prior sessions**, `min_periods = ceil(2/3 × 90) = 60`, **prior sessions only** | frozen in EXP-0003 |
| Entry | fade **`\|z_slot\| ≥ 2.0`**, **first crossing** only | run-book fiat |
| Entry fill | open of the bar **two** bars after the signal bar (**one-bar delay**) | fact 1 |
| Holding cap | **240 minutes** | Stage A H\* |
| Reversion exit | **choose and freeze — see §4.2** | — |
| Stop | **none** (wide-stop variant is a diagnostic only) | constraint set |
| Vetoes | news blackout ±30 min; force-flat Friday 16:55 NY | constraint set |
| Concurrency | one position per pair, enforced statefully | Rule 13 |

**Use `k = 2.0`, not 2.14.** EXP-0003's 2.14 exists only to rate-match the all-hours arm;
it is not a chosen parameter and must not be inherited as one.

### 4.2 The exit decision you must make and freeze

This run-book previously said "exit at `z = 0`". **That is degenerate at τ = 5.** The
displacement is a *one-bar* return, so `z → 0` just means the next bar was small: `zcross`
is 0.96 by H=15 and 1.00 by H=60. It is a time exit wearing another name.

The discriminating alternative is **anchor retrace** — exit when price trades back to the
anchor (the close of the bar *before* the signal bar). Measured touch rates at τ=5:
**0.22 / 0.36 / 0.51 / 0.63 / 0.73** at H = 15 / 30 / 60 / 120 / 240.

**Trap you must handle:** an anchor-retrace exit is a **passive limit order**, and a touch
is not a fill (Rule 4). With midpoint data and no volume there is no queue evidence.
Either require adverse trade-through beyond the anchor by a **volatility-scaled** guard
(never a fixed tick — see fact 5), or report the touch-based result explicitly as an
upper bound alongside a time-exit lower bound. Do not credit a limit fill at a touch.

Recommended default: **anchor retrace with a volatility-scaled trade-through guard, capped
at 240 minutes**, with a pure 240-minute time exit reported as the conservative floor.
Freeze whichever you pick in `KILL_TEST.md` before the run.

### 4.3 Units — the trap the same-slot switch creates

Same-slot normalisation makes the **entry** clock-neutral but makes the **cost**
clock-dependent in the sizing unit. `σ_slot` at τ=5 ranges **2.27 → 5.05 pips** across UTC
hours (2.2×), so a flat ~1.2-pip round trip costs:

- **0.238 R_slot** at 13:00–14:00 UTC, but **0.529 R_slot** at 21:00 UTC — a 2.2× swing;
- a flat **0.379 R_abs** at every hour.

Consequences for Stage B, all mandatory:

1. **Report net in the same unit you size in.** A gross figure in `R_slot` against a cost
   in pips is not a net result.
2. **Report `R_abs` alongside** (`R = σ` from the 28,800-market-minute window) as the
   cross-arm/cross-hour comparison yardstick.
3. Expect net-of-cost results to **tilt toward busy hours** — structurally, and in the
   opposite direction to the retracted EXP-0002 finding. Report it; do not narrate it as
   a discovery, and do not build an overlay on it in Stage B.

### 4.4 Report

Gross **first** — with no stop, does the bare entry have any gross reversion at all? —
then the cost curve and breakeven pip, net by era, the three Sharpes, and the sealed
holdout segment **once**. Both entry arms: **delay-1 primary, delay-0 as diagnostic**.

### 4.5 Deliverables and exit gate

`KILL_TEST.md` for EXP-0004 frozen **before** the run (the existing `KILL_TEST.md` is
EXP-0001's — do not overwrite it; write a new file or move the old one under
`artifacts/runs/EXP-0001/`). Frozen config in `baseline_replication/configs/`.
`reports/FINDINGS.md` updated. `MEMORY.md` records EXP-0004 as the active reference book.
Ledger row. Run artifacts and a `review.md`.

**Exit gate.** Book is frozen and registered; gross, net-by-era, breakeven pip and the
three Sharpes are reported in both units; no parameter was tuned to PnL.

---

## 5. STAGE C — Post-hoc regime overlays (EXP-0005+)

**Objective.** Label the frozen EXP-0004 trades with candidate regimes and test each as a
**sizing or veto overlay on the existing book — never folded into the entry.**

**Candidate axes, in priority order:**

1. **Displacement depth (`|z_slot|` level) — FIRST and alone.** Prior FX work found depth
   a near-sufficient statistic, so it is the benchmark every other overlay must beat. If a
   later regime "helps", first suspect it is just selecting deeper `|z|`.
2. **Volatility regime** (compression vs expansion), same-slot z-scored. **Note: this axis
   is now a cleaner test than it was** — with the slot normaliser in the entry, the base
   signal no longer selects on the clock, so a vol overlay is no longer partly
   re-measuring its own entry condition.
3. **Cross-pair divergence** — relative value across the majors, applied to the *follower*
   leg identified a-priori from cointegration dynamics. The one axis found genuinely
   orthogonal to own-pair vol/direction, and null-fragile, so it gets the strictest
   re-pairing null.
4. **Session / time-of-day** — only *after* matching on volatility, and starting from a
   **null prior**: EXP-0003 retracted the previous session finding. Note the §4.3 cost
   asymmetry will produce a net-side session gradient by construction; an overlay must
   beat that mechanical effect, not rediscover it.
5. **Exit-side vol-conditional holding horizon** — newly live now the stop is gone.

**Evaluation protocol (non-negotiable):**

- Overlay acts as **sizing/veto** on frozen trades; do not change the entry.
- Compare at **matched selection rate**, in **R units**, on a **common sample**.
- **Matched-COUNT direct depth benchmark** for every overlay — not a frontier-interp,
  which clamps and flatters. An overlay must beat ranking by depth at equal trade count.
- **Frontier-excess** is available as a rate-matching tool, but **match rates by picking a
  threshold off a finely swept grid** (step 0.02 got within 1.2% in EXP-0003) rather than
  interpolating; assert every arm's rate lies inside the reference curve's range.
- Print the **per-cell COUNT** beside every regime stat; reject if counts move.
- **Within-vol control** for any time/session label.
- **Claim-matched null through the full pipeline** for each survivor: `signflip` for
  vol/memory axes, **circular-shift** for autocorrelated regime series, **re-pairing** for
  cross-pair divergence. Report null center, baseline and real value as three numbers;
  when selection occurred, compare the real MAX over the reproduced search to the null
  distribution of maxima.

**Deliverables per overlay.** `experiments/hypotheses/HYP-XXXX.md` with mechanism, exact
change, primary metric, kill test, controls, data scope; `artifacts/runs/EXP-XXXX/`; a
`review.md`; ledger row. **Register losers too.**

**Exit gate per overlay.** Accepted / rejected / inconclusive, with the matched-count depth
benchmark and the claim-matched null both reported. An overlay survives only if it beats
depth at matched count **and** clears its null.

---

## 6. STAGE D — Promotion + re-freeze (Stage-C survivors only)

Re-specify the strategy with the survivor built in; **re-freeze** a new reference book;
**re-run the claim-matched null** on the promoted form; report on the sealed holdout once.
Never promote in place. Historical survivors then require a paper/shadow period before any
capital — once history is inspected, only future observations are a clean holdout.

**Exit gate.** Promoted book is frozen, re-nulled, and its holdout result reported; shadow
plan recorded, or the arc is closed with a reason.

---

## 7. Honest prior

`exploration_1` already ran a large conditioner search on this z-fade family and found
depth near-sufficient / the search largely exhausted. **Expect most overlays to be
redundant.**

Stage A sharpened the prior rather than softening it. The reversion is **real** — VR is
below 1 at every timescale with robust z of −12 to −15, and the surviving conditional
effect at τ=5 has a CI excluding zero after both the shared-endpoint and clock controls
were applied. It is also **about three times too small to pay for itself**: ~0.38 gross
pips against a 1.21-pip modelled round trip whose commission component alone is 0.70 pips.

So the realistic outcome of Stages B–C is a well-characterised negative book. That is a
successful research outcome (Rule 25) and it is what the arc is set up to record. The two
places a positive result could still come from: an overlay that raises gross per trade by
a factor, not a few percent — **cross-pair divergence** is the only untested axis found
orthogonal — or a cost structure materially better than the modelled one, which this
archive **cannot** establish because it has no bid/ask. If the decision hinges on cost,
the honest next step is quote data, not another overlay.

---

## 8. Sequencing summary

`A (characterize → pick grain)` ✅ → gate ✅ → `A addendum (clock control)` ✅ →
**`B (freeze reference book, EXP-0004)` ← you are here** → gate →
`C (overlays, depth first, each null-tested)` → gate →
`D (promote survivors, re-freeze, re-null, shadow)`.

Stop for review at each gate. All three completed runs are still awaiting independent
review; each `review.md` carries its own reviewer checklist.
