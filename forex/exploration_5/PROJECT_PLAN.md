# exploration_5 — Reference-location reversion

## The idea (user, 2026-08-09)

> Is there a **reference location** that price is more likely to invert (mean-revert)
> from? Candidate reference levels:
> 1. previous daily high / low
> 2. the 12:00 ET opening price
>
> When price extends **beyond a certain z-score past that level**, does it revert
> **more than a matched control**?

## How this differs from exploration_4

`exploration_4` measured z-fade reversion from a **rolling same-slot mean** — a moving
anchor that tracks price. That project's honest verdict was NO-GO: the surviving
reversion at τ=5min was ~3× too small for cost, and it was not capturable by a passive
exit. It also carried a structural artifact — the anchor's endpoint *was* the decision
bar's close (`open[i]==close[i-1]` at 99.99998%), so undelayed reversion was 56–78%
shared-endpoint.

This project asks a **different** question: are **fixed structural levels** (a level set
by a *prior* session, or by a *fixed earlier time*) *special* — does reversion from them
exceed reversion from a generic "price is far from typical" extension of equal size?

Two properties make the structural-level framing cleaner than the rolling-mean one:
- The anchor is fixed **before** the crossing, so it is not the decision bar's close;
  the shared-endpoint artifact is not structurally present (we still run the delay-1
  diagnostic to confirm).
- The hypothesis is inherently a **relative** one ("more than a control"), which forces a
  matched control up front rather than a bare mean.

## Reference locations (anchors)

Structural anchors under test:
- `pdh` / `pdl` — previous UTC-day high / low (Donchian(1))
- `dch` / `dcl` — prior N-day Donchian channel high / low (N=20, the Turtle number). Fading
  an ATR-overshoot of this is the classic **"Turtle Soup"** false-breakout pattern.
- `swing_high` / `swing_low` — the most recent **confirmed** swing pivot (fractal, half-width
  3). A pivot is only knowable `w` days after it forms, so its level is placed at the
  confirmation day and forward-filled — no look-ahead.
- `noon_et` — the current day's 12:00 America/New_York open price (DST-aware)

### Mechanism (user, 2026-08-09): forced-liquidation snapback

Stop-loss orders cluster **just beyond visible structure** (Donchian extremes, swing pivots,
the prior high/low). When price pokes through by an ATR buffer it triggers a cascade of
forced liquidations (and breakout entries whose own stops then feed the move), which
**overshoots** and then snaps back. The reference location is therefore the stop cluster at
`level ± k·ATR`, and the `k` I already sweep **is** that ATR buffer. Testable signatures the
mechanism predicts, each a control here:
- The snapback is **fast** — strongest at short `H`, decaying — not a slow drift. (Read the
  horizon profile; contrast with the genuine-continuation reading.)
- It **beats a re-pairing null**: a real stop cluster sits at a real structural extreme, so a
  randomly-relocated level should not reproduce it.
- **Continuation confound:** a Donchian breakout is also the canonical *trend* signal (Turtles
  trade it the other way). Fade and continuation cannot both be positive on average, so I
  report the naive always-with-breakout reading alongside the fade; "reversion" must beat both
  the trend tilt and the generic-extension control.
- **No order-flow data:** this archive is midpoint OHLC with no volume/quotes, so liquidations
  are inferred only from the price overshoot-revert signature — a stated limitation, not a
  measurement of flow.

Control / placebo anchors (the "matched control"):
- `mean_slot` — exploration_4's rolling same-slot mean (a *generic* extension anchor; a
  moving, non-structural reference). Primary "is the LEVEL special vs just being far out?"
  benchmark, compared at matched selection rate on a common sample.
- `repair`/**re-pairing null** — for each structural anchor, replace day *d*'s level with a
  level drawn from a *different* day (same pair, same era), then re-run the whole
  crossing→forward-return pipeline. This preserves "a horizontal level at a plausible
  price" and each pair's own path dynamics, but destroys the specific relationship between
  the level and today's path. Many draws → a null distribution of mean reversion R. This is
  the decisive control for "this exact level is special."

## Displacement and vol unit

- Vol unit `U` = trailing **ATR**: mean true range over the prior `atr_lookback_days`
  daily bars (causal, prior sessions only). One scalar per pair per day.
- Displacement `d(t) = (price(t) − A)` in price; standardized excursion `z(t) = d(t)/U`.
- A **crossing event** fires at the first minute where `|z| ≥ k` on the *outside* of the
  level (price above `pdh` / below `pdl`; either side for `noon_et`/`mean_slot`), with a
  gap re-arming the signal (reuse `first_crossing` semantics).

## Estimand (discovery phase — signal-only forward return, NO fill)

Per RULES this is a signal/forward-return study, so next-bar-open entry is legal and there
is no bracket fill to validate yet.

- Entry = **open(m+1)** after the crossing bar (undelayed primary; **delay-1 diagnostic**
  mandatory to bound any residual shared-endpoint effect).
- Outcome = forward return over horizon `H`, **signed toward the anchor** (reversion
  positive), reported in **pips** (tradable unit, Rule 19) and in **ATR units**.
- Aggregation = **per-signal mean** with **UTC-day cluster-robust SE**, pooled across the
  4 pairs (≈2 effective independent). Report per-pair. (Rule 12; endogenous-count trap in
  LEARNINGS §4 — read `corr(day-mean, day-count)`.)
- All comparisons across anchors are at **matched selection rate on a common sample**, k
  picked off a finely-swept grid (never `np.interp`, which clamps — LEARNINGS §2).

## Mandatory controls / traps to clear (before any positive read)

1. **Coverage / Rule 9a:** per-slot (UTC-hour) fire rate + count for every anchor; the
   structural crossings will cluster in active hours — that is a property, not an artifact,
   *only if the control is slot/coverage-matched*. Print counts next to every stat.
2. **Shared-endpoint:** paired delay-1 on the identical signal set; report the fraction of
   reversion it removes (expect ≈0 here, unlike exploration_4).
3. **Generic-extension control:** `mean_slot` at matched selection rate — does the
   structural level beat "just far from typical"?
4. **Re-pairing null:** the decisive test that the *specific* level matters.
5. **Cost reality check:** express the surviving gross reversion against the same
   breakeven-pip round trip exploration_4 used (~1.2 pip base; 0.7 pip is commission). A
   gross edge below cost is a descriptive finding, not a tradable one.

## KILL TEST (pre-registered, before the material run)

The reference-location hypothesis is **rejected / dead** if ANY of:

- **K1 (no excess over generic extension):** at matched selection rate on the common
  sample, no structural anchor's reversion mean R exceeds the `mean_slot` control by more
  than the tie band (±0.005 R, LEARNINGS convention) with a cluster-robust CI excluding
  zero, at the primary horizon.
- **K2 (fails its re-pairing null):** the real structural-anchor mean R lies inside the
  central 95% of the re-pairing null distribution (i.e. a randomly-shuffled level reverts
  as much) at the primary horizon.
- **K3 (pure shared-endpoint):** the delay-1 paired arm removes essentially all of the
  measured reversion (as in exploration_4), leaving a delay-1 mean R with CI including zero.

A structural anchor **survives discovery** only if it beats the generic-extension control
(not K1), clears its re-pairing null (not K2), and is not a delay artifact (not K3). Even a
survivor is then subject to the cost reality check and is a *forward-return* finding, not a
tradable edge, until a fill model is validated (exploration_4 shows a level-retrace fill is
where these edges die).

Primary horizon: `H* = 60min`; secondary `H ∈ {15, 30, 120, 240}`. Threshold is in **ATR
units** (`z = (price−level)/ATR`); primary `k* = 0.25` (a modest failed-breakout excursion —
`k ≥ 1` full ATR *beyond* a daily level is an extreme move that fires only ~10²×/12yr and is
underpowered). The whole `k`-sweep is reported so no single point is cherry-picked. The
generic-extension control is a **trailing-price anchor** (`price` vs `price L=60min ago`),
not `mean_slot` (a return-mean, unit-mismatched to a price level); the re-pairing null is the
decisive control. Discovery on consumed history
(2012–2023); 2024+ is a sealed holdout, opened at most once and only if discovery survives.

## Layout

- `_ref_lib.py` — new primitives (daily bars, anchors, ATR, crossing on the minute grid,
  re-pairing), unit-tested in `test_ref_lib.py`. Reuses `exploration_4/_stage_a_lib.py`
  for calendars/eras/MinuteGrid/cluster_stats/same-slot moments.
- `_run_ref_reversion.py` — orchestration → `artifacts/runs/EXP-0001/`, `reports/`.
- `configs/exp_0001.json` — frozen config.
