# exploration_4 — Project Memory

## What this project is

> **Taking over? Read `RUNBOOK.md` §0 first** — it is the ordered execution contract and
> carries the handoff (what is done, what is next, where everything lives, and the traps
> that cost time). This file is the state; the run-book is the plan.

Mean-reversion research on four USD-major spot FX pairs, now running the run-book arc
in `RUNBOOK.md`: **characterize → freeze a reference book → post-hoc regime overlays →
promote survivors**. EXP-0001 was a single frozen, stopped baseline and closed NO-GO;
the constraint set has since changed (no compulsory stop), so the arc restarted at
Stage A.

## Status

**Stage A complete, including its same-slot addendum (EXP-0002 + EXP-0003,
2026-08-08).** Stage B not started. Independent review pending for all three runs;
builder for EXP-0002/0003: Claude.

| Stage | Experiment | State |
| --- | --- | --- |
| — | EXP-0001 stopped 5-min baseline | **Closed NO-GO**; superseded *as reference book* |
| A characterize | EXP-0002 | **Complete.** τ\* = 5 min, H\* = 240 min; gate passed as *documented disagreement* |
| A addendum | EXP-0003 | **Complete.** Clock confound removed; τ\* confirmed, one EXP-0002 finding retracted |
| B freeze reference book | **EXP-0004** | Not started |
| C regime overlays | EXP-0005+ | Not started |

> **Numbering:** the run-book text assigns EXP-0003 to Stage B. The ledger requires
> `EXP-\d{4}`, so the Stage-A addendum took EXP-0003 and **Stage B is EXP-0004**.

## Stage-A confirmed findings (EXP-0002)

Consumed history 2012–2023, pooled across pairs, per-signal mean R with UTC-day
cluster-robust SE. Full report: `reports/MARKET_CHARACTERIZATION.md`.

- **Spot FX majors revert at every timescale, and ambient reversion DEEPENS with the
  timescale.** `VR(τ)` = 0.948 (5m), 0.906 (15m), 0.888 (30m), 0.876 (60m), 0.869
  (120m), Lo–MacKinlay heteroskedasticity-robust `z` between −12.4 and −15.2; `VR < 1`
  in all five session cells and all four pairs.
- **Reversion conditional on an extreme runs the OPPOSITE way across the ladder** —
  gross mean R at `|z| ≥ 2`, best over horizon: 0.190 (τ=5), 0.100 (τ=15), 0.058
  (τ=30), 0.021 (τ=60), −0.000 (τ=120). Same ordering on the maximal sample, so it is
  not a coverage artifact. The unconditional and conditional views genuinely invert.
- **56–78% of the measured conditional reversion is a shared-endpoint artifact.**
  `open[i] == close[i-1]` for 99.99998% of contiguous minutes here, so the undelayed
  entry price *is* the price ending the displacement window. A paired one-bar entry
  delay on the identical signal set removes 0.086R at τ=5/H=240 (t = −12.2), leaving
  0.067R. What survives is real at τ=5 and indistinguishable from zero at τ ≥ 60.
- **The surviving effect is smaller than its own cost by ~3×.** Best breakeven
  round-trip is 0.79 pips (k=2.5) and 0.64 at the k=2.0 headline; the delayed arm is
  ~0.40 pips. The modelled base round trip is 1.21 pips, of which **0.70 is commission
  alone**. Net expectancy is negative in every cell of the surface.
- ~~**The effect concentrates in thin hours**~~ — **RETRACTED by EXP-0003.** See the
  addendum section below. The session breakdown was a time-of-day selection artifact.
- **Breadth is weak:** NZD 0.252 (t=5.7), EUR 0.227 (t=3.0), AUD 0.208 (t=3.4), GBP
  0.043 (t=0.54, negative under the delay control) — on ≈2 effective independent pairs.
- **Coherent dose-response in `|z|`** (0.134 → 0.190 → 0.249 → 0.231 at k = 1.5 / 2.0 /
  2.5 / 3.0), which is not the shape a searched artifact usually has.
- **Naive always-long drift is ~0** at every horizon pooled (H=240: −0.081 pips, CI
  [−0.384, +0.222]), so the fade is not harvesting a directional tilt. London does carry
  a real −0.84 pip/240min always-long tilt; that is an unconditional tape measurement and
  is unaffected by the EXP-0003 retraction, which concerns the *fade's* session split.
- **Sealed holdout (2024+), opened once, changed nothing:** τ=5 gross 0.187R at H=240,
  CI [−0.020, +0.393] — same sign, CI includes zero. Not confirmatory.

## Stage-A addendum (EXP-0003) — the `|z|` cut was a time-of-day selector

EXP-0002's σ was a trailing **all-hours** 28,800-minute window, which cannot see the
intraday volatility profile (median σ moves only 3.156→3.179 pips across all 24 UTC
hours at τ=5). The fixed `|z| ≥ 2` cut therefore fired on **0.96%** of decisions at
04:00 UTC and **10.11%** at 14:00. EXP-0003 rebuilt the same family against a causal
**same-slot** σ (90 prior sessions of the same time-of-day slot, 2/3 fractional floor,
prior sessions only) and compared at matched trade count. Report:
`reports/SAME_SLOT_ADDENDUM.md`.

- **The normaliser works.** Selection-rate CV **0.663 → 0.119**; hourly firing rate
  0.90–8.15% → 2.37–4.08%. Counts matched to 0.8%; the matched `k` is **picked from a
  fine swept grid** (step 0.02), never interpolated.
- **RETRACTED: the thin-hours localisation.** Under the same-slot arm,
  `off − london = 0.169` against a combined CI half-width of 0.265, and
  `asia − london = 0.186` against 0.228 — neither clears the pre-committed bar (both
  cleared it under the all-hours arm). Normalising nearly doubles Asia's count
  (16,689 → 33,255) and halves overlap's (37,429 → 16,808): the old table was never
  comparing like with like. **Session differences are not established.** Do not carry
  "the edge lives in off-hours" into Stage C, and do not build a session overlay on it.
- **τ\* = 5 CONFIRMED and sharpened:** 0.1056 R [0.045, 0.166] — the only rung whose CI
  excludes zero (τ=15 0.050, τ≥30 ≈ 0 or negative). H\* = 240 stands.
- **Normalising IMPROVES the signal:** slot 0.1056 R vs abs 0.0651 R at matched count
  (+0.041), gross 0.383 vs 0.244 pips. Removing the clock removed a confound *and*
  sharpened the estimate.
- **Cost verdict unchanged:** 0.383 gross pips against a 1.209-pip modelled round trip.
  Still short by ~3×. Renormalising a threshold cannot fix that.
- **Knock-on: the cost side becomes clock-dependent.** `σ_slot` runs 2.27→5.05 pips
  across UTC hours (2.2×), so a ~1.2-pip round trip costs 0.238 R_slot at 13:00–14:00 but
  0.529 R_slot at 21:00, against a flat 0.379 R_abs. Stage B must report net in the unit
  it sizes in, and should expect a *mechanical* busy-hours tilt in net — opposite to the
  retracted finding, and not a discovery. Evidence:
  `artifacts/runs/EXP-0003/intraday_sigma_profile.csv`, reproduce with
  `python -u forex/exploration_4/_diag_intraday_sigma.py`.
- Limitation: UTC slots do not track DST, so a slot's meaning shifts by an hour twice a
  year against London/NY local time. A local-time slot variant is worth one run if
  Stage B adopts the feature.

## Carry-forwards that constrain Stage B

- **Freeze the reference book on the SAME-SLOT z, not the all-hours z** (EXP-0003).
  It is confound-free on the clock and strictly better at matched count. There is no
  remaining argument for the absolute σ.
- **Use the one-bar-delayed entry as Stage B's PRIMARY arm**, undelayed as diagnostic.
  The artifact is too large for a reference book built on the undelayed arm to be an
  unbiased ruler.
- **The run-book's proposed "exit at z = 0" is near-degenerate at τ = 5:** `zcross` is
  0.96 by H=15 and 1.00 by H=60 — at this grain it is a time exit under another name.
  The anchor-retrace rate actually discriminates (0.22 / 0.36 / 0.51 / 0.63 / 0.73 at
  H = 15 / 30 / 60 / 120 / 240). Pick one deliberately.
- **Do not reuse EXP-0002's view-3 bracket as a cross-grain comparator.** Its fixed
  1-pip stop slippage against vol-unit barriers is the *entire* payoff asymmetry
  (implied loss over the 1.0R target matches slippage/σ_τ to within 0.011R at all five
  rungs), so it is biased against fine grains by construction. Its absolute reading —
  profit factor < 1 everywhere — still stands.

## Data quality and implementation boundary

- Midpoint OHLC only: **no volume, no bid/ask**. Cost is always a breakeven-pip curve,
  never a measured spread.
- `open[i] == close[i-1]` for essentially every contiguous minute. Any study whose
  feature window ends where its outcome window starts will manufacture reversion here.
- σ windows must be counted in **tradable bars, not calendar bins**: spot FX covers
  ~71% of calendar minutes, so a 0.9 `min_periods` floor on raw bins nulls σ everywhere
  (this produced zero signals on the first implementation).
- The **H = 480 completeness rule removes 33–42% of signals**, concentrated on windows
  spanning the weekend or the archive's daily ~21:00–22:00 UTC rollover hole, so the
  common sample is not hour-neutral. Enumerated by UTC hour
  in `reports/DATA_QUALITY.md` §3; the maximal-sample surface is reported alongside.
- NZDUSD's late-era 18:00–19:00 UTC holes persist and limit NZD-specific claims.
- The 17:00 New York rollover bar is unavailable; 16:55 is the last attainable open and
  is where the Friday-flat minute is set.

## Evidence and reproduction

- Stage A map: `reports/MARKET_CHARACTERIZATION.md`; coverage gate: `reports/DATA_QUALITY.md`
- Stage A addendum: `reports/SAME_SLOT_ADDENDUM.md`
- Runs + reviews: `artifacts/runs/EXP-0002/`, `artifacts/runs/EXP-0003/`
- Pre-specs frozen before their runs: `experiments/hypotheses/HYP-0002.md`, `HYP-0003.md`
- EXP-0001 (superseded as reference): `reports/FINDINGS.md`, `artifacts/runs/EXP-0001/`
- Ledger: `experiments/ledger.csv`
- Reproduce: `python -u forex/exploration_4/_run_stage_a.py` (~6 min), then
  `python -u forex/exploration_4/_run_same_slot.py` (~3 min)
- Tests: `python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider` (25)

## Next action

**Stage B (EXP-0004)** — freeze one reference book at τ = 5 min with a 240-minute
holding cap, on the **same-slot z**, under the updated constraints (no compulsory stop,
event-driven entry, news blackout, weekend-flat), with a `KILL_TEST.md` frozen before
the run. Honour the four carry-forwards above. A negative reference book is still a valid ruler; the point
of Stage B is the denominator for Stage C, not a GO.
