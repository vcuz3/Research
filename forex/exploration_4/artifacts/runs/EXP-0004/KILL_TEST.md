# EXP-0004 — Pre-registered Kill Test / freeze contract (FREEZE before the material run)

**Stage B of `RUNBOOK.md`: freeze one honest reference book.** This file is written and
frozen **before** any Stage-B P&L is computed. Corrections and results discussion go in
`artifacts/runs/EXP-0004/review.md`, never here.

> This is **not** the EXP-0001 kill test. EXP-0001's root `KILL_TEST.md` (a compulsory-stop
> baseline) is a different, superseded contract and is left untouched.

## What Stage B is

Stage B freezes **one** mean-reversion book to serve as the **ruler** every Stage-C overlay
is measured against. Its parameters are fixed **by fiat from Stage A**, not by search, and
**nothing is tuned to PnL**. A GO or a NO-GO are equally acceptable outcomes: a negative
reference book is still a valid ruler (Rule 25). The exit gate is a *process* gate — the
book is frozen and honestly reported — not a performance threshold.

## Thesis (one line)

The Stage-A same-slot z-fade, frozen as a deployable book (event entry, no stop, anchor
exit, news + weekend vetoes), has the small positive **gross** reversion EXP-0003 measured
(≈0.38 pips at τ=5/H=240, delay-1) and a **net** expectancy that is negative under the
modelled cost curve.

## Frozen book (all values from Stage A; none chosen by Stage-B PnL)

| Element | Value | Source |
| --- | --- | --- |
| Decision grain | 5-minute epoch-anchored bars, complete-only | Stage A τ\* |
| Feature | same-slot z `(ret_5 − μ_slot)/σ_slot` | EXP-0003 |
| Slot window | 90 prior sessions, `min_periods=60`, prior sessions only | EXP-0003 |
| Entry | fade `\|z_slot\| ≥ 2.0`, **first crossing** only | run-book fiat (k=2.0, NOT 2.14) |
| Entry fill (primary) | open of the bar **two** bars after the signal bar (**delay-1**) | shared-endpoint fact |
| Entry fill (diagnostic) | one bar after the signal bar (**delay-0**) | shared-endpoint control |
| Holding cap | 240 minutes | Stage A H\* |
| **Exit (frozen = the book)** | **guarded anchor-retrace**: limit at the anchor (close of the bar before the signal bar), credited only when the favourable extreme trades **through** the anchor by **g = 0.25·σ_slot**, filled conservatively **at the anchor price**; else market exit at the cap | run-book §4.2 recommended default |
| Exit floor (reported alongside) | pure **240-minute time exit** (market at cap), no anchor logic | run-book §4.2 conservative floor |
| Exit ceiling (reported alongside) | anchor **touch** (g = 0), limit credited on first touch | run-book §4.2 upper bound |
| Stop | none | constraint set |
| Vetoes | news blackout ±30 min high-impact for that pair; force-flat Friday 16:55 NY | constraint set |
| Concurrency | one position per pair, greedy non-overlap for the book/Sharpe accounting | Rule 13 |

The guard `g = 0.25σ_slot` is a declared modelling choice, frozen here. The touch (g=0)
and time-exit variants **bracket** it, so the book's sensitivity to the fill assumption is
visible rather than hidden. No parameter above is chosen to maximise any P&L.

## Primary metric

Per-signal **mean gross R**, **delay-1**, τ=5, H=240, guarded-anchor exit, with a
**UTC-day cluster-robust** SE and 95% CI. Reported in **two units**:
`R_slot` (σ_slot — the unit the book sizes in) as the headline, and `R_abs`
(σ_abs from the 28,800-min window — the cross-arm/cross-hour yardstick) alongside. Also in
pips. Reported per pair, pooled, and by era.

## What the run reports, in order (run-book §4.4)

1. **Gross first** — does the bare entry have any gross reversion at all? — for all three
   exit treatments, both entry arms.
2. Cost curve (optimistic/base/pessimistic + vol term) and the **breakeven round-trip pip**.
3. **Net by era**, in the sizing unit and the yardstick unit.
4. The **three Sharpes** (zero-day, trade-days-only, vol-targeted) on the one-position book.
5. The sealed **2024+ holdout** segment, opened **once**, at the end.

## Pre-registered readings (from Stage A — recorded so they cannot be re-narrated later)

- Expected gross ≈ 0.35–0.40 pips (delay-1); net **negative** in every cell at base cost
  (gross ~3× short of the ~1.21-pip modelled round trip, 0.70 pip of which is commission).
- Same-slot normalisation makes net **structurally** tilt toward busy hours in `R_slot`
  (σ_slot is 2.2× larger at 21:00 than 13:00). This is mechanical; it is **not** a finding
  and no overlay is built on it in Stage B.

## What would surprise (and what to do)

- **Net CI excludes zero on the positive side at base cost** → do not deploy; escalate to an
  independent review and re-examine the cost model and the guarded-fill assumption, because
  the archive has no bid/ask and cannot establish a real spread (run-book §7).
- **Gross reversion absent at delay-1** (CI includes zero) → the EXP-0003 τ=5 result did not
  survive the book's exit geometry; record it and note the ruler is a null book.

## Controls / diagnostics in the same pass

- delay-1 (primary) vs delay-0 (shared-endpoint diagnostic).
- Three exit treatments (touch ceiling / guarded / time-exit floor) bracket the fill model.
- Cost-scenario sweep; breakeven round-trip pip reported beside gross.
- News-blackout removals and Friday-flat truncations separately quantified (Rule 9a).
- Both risk units reported for every headline number.

## Data scope

Consumed history 2012–2023 for construction/inspection; **2024+ sealed**, opened once at the
end of the report. Pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD (midpoint 1m→5m; ≈2 effective
independent). Midpoint OHLC only — **no volume, no bid/ask** — so cost is always a
breakeven-pip curve, never a measured spread.

## Deliverables and exit gate

`reports/STAGE_B_REFERENCE_BOOK.md`; frozen config `baseline_replication/configs/stage_b.json`;
`artifacts/runs/EXP-0004/` (verdict.json, manifest, CSVs, review.md); `reports/FINDINGS.md`
and `MEMORY.md` updated to record EXP-0004 as the active reference book; ledger row.

**Exit gate (process, not performance):** the book is frozen and registered; gross,
net-by-era, breakeven pip and the three Sharpes are reported in both units; no parameter was
tuned to PnL; the sealed holdout was read once.

---
Frozen by: Claude (builder)   Date: 2026-08-09   Reviewer: pending independent review
