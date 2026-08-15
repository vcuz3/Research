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

**Independent review completed (Codex, 2026-08-09); Stage-B (EXP-0004) corrections APPLIED
and re-run 2026-08-09, pending reviewer re-verification.** The directional NO-GO holds and is
now on the deployable estimand. Stage-B repairs done: F1 stateful one-position estimand on
every book metric (not just Sharpes); F2 causal no-entry for already-crossed anchors + the
consumed-only cost median (holdout no longer leaks); F3/minor language (touch/time are
diagnostics not bounds; "not established" not "absent"; rebate not breakeven); F4 Rule-9a
exclusion funnel emitted. **Stage-A code repairs (EXP-0002/0003) F1–F5 APPLIED + re-run
2026-08-09; pending reviewer re-verify.** τ\*=5/H\*=240 unchanged by every repair. Evidence:
`reports/STAGE_A_INDEPENDENT_REVIEW.md` (Codex findings + builder response),
`artifacts/runs/EXP-0004/independent_review_codex.md`, response in `artifacts/runs/EXP-0004/review.md` §8.

| Stage | Experiment | State |
| --- | --- | --- |
| — | EXP-0001 stopped 5-min baseline | **Closed NO-GO**; superseded *as reference book* |
| A characterize | EXP-0002 | **Repairs F1(labels)/F2(cost-leak)/F5(per-session VR) APPLIED + re-run; pending reviewer re-verify.** Descriptive map stands; tau/H are consumed-history GROSS-P&L-selected candidates |
| A addendum | EXP-0003 | **Repairs F1(labels)/F3(clustered contrast + departures)/F4(fixed-H\* ranking) APPLIED + re-run; pending reviewer re-verify.** Clock flattening confirmed; session: off not established, asia MARGINAL/provisional (see below) |
| B freeze reference book | **EXP-0004** | **Corrections APPLIED + re-run; pending reviewer re-verify.** NO-GO on the stateful one-position book |
| C regime overlays | **EXP-0005 (depth)** | **Done — depth REJECTED as rescue, retained as benchmark.** Started at user direction despite open Stage-A/EXP-0004 items |
| C regime overlays | **EXP-0006 (vol regime)** | **Done — vol regime REJECTED as rescue** (both arms; net never clears zero; depth-orthogonal so the null is informative) |
| C regime overlays | EXP-0007+ (x-pair divergence, session, exit) | Not started |

## Stage-B result (EXP-0004) — the frozen reference book

Report: `reports/STAGE_B_REFERENCE_BOOK.md`; review + response: `artifacts/runs/EXP-0004/review.md`
(§8 responds to Codex); frozen spec `experiments/hypotheses/HYP-0004.md` +
`artifacts/runs/EXP-0004/KILL_TEST.md`. Reproduce: `python -u forex/exploration_4/_run_stage_b.py`
(~1 min); tests `python -m pytest forex/exploration_4/test_stage_b.py -q` (13).

**The book (params inherited from Stage A — τ=5/H=240 are P&L-selected candidates, NOT
confirmed; Stage B adds no new PnL tuning):** τ=5 same-slot z, fade `|z_slot| ≥ 2.0` first
crossing, **delay-1** entry, 240-min cap, **no stop**, **causal no-entry** if the anchor is
already crossed at entry, news ±30 min + Friday-16:55-NY vetoes. **Exit = guarded
anchor-retrace:** limit at the anchor, credited only on a **0.25·σ_slot trade-through**,
filled at the anchor price. `touch` (g=0) and `time` are **diagnostics, not payoff bounds**.
**Estimand = the STATEFUL one-position-per-pair book** (greedy non-overlap); all-signal
per-signal is a diagnostic only. Audited simulator `_stage_b_lib.simulate_anchor_retrace` +
`anchor_favourable` (parity-tested).

- **NO-GO, two independent reasons.** (1) EXP-0003: gross ~3× too small for cost. (2) the
  reversion is **not capturable by a realistic passive exit**. Stateful guarded gross at
  delay-1 = **−0.028 R_slot, CI [−0.083, +0.027] includes 0 → positive reversion NOT
  established**, −0.172 pips (a 0.172-pip rebate would be needed to reach zero); net −0.565
  R_slot [−0.621, −0.510] base, negative every scenario/era; net Sharpe ≈ −4.7. Holdout agrees
  (gross −0.255 pips, net −0.692). n=66,912 (stateful) vs 132,614 (all-signal diagnostic).
- **The mechanism:** the un-fillable band. `touch` (+0.348 pips) and `time` (+0.628) stay
  positive but `guarded` (−0.172) does not — price reverts *just* to the anchor and reverses,
  so a bare-touch fill books a profit the guard (realistic trade-through) misses. **The
  retrace target is the reversal point.** `time` reproduces EXP-0003 direction (machinery
  parity). Provisional LEARNINGS §6 entry.
- **Coverage (funnel, `exclusion_funnel.csv`):** 198,812 signals → 15,471 news → 7,105
  already-crossed no-entry → 15,985 incomplete-path → **160,040 book-eligible**; non-overlap
  then drops ≈49% (guarded). Path loss is NOT hour-neutral (17–21 UTC rollover/weekend).
- **The book is the Stage-C RULER.** Overlays scored as **excess over this stateful book at
  matched count**, re-run through the non-overlap machinery (an overlay changes exits →
  occupancy → surviving set), never by filtering a completed-trade list.

> **Numbering:** the run-book text assigns EXP-0003 to Stage B. The ledger requires
> `EXP-\d{4}`, so the Stage-A addendum took EXP-0003 and **Stage B is EXP-0004**.

## Stage-C findings

### Axis 1 — displacement depth |z_slot| (EXP-0005) — REJECTED as rescue, kept as BENCHMARK

Report: `reports/STAGE_C_DEPTH.md`; review: `artifacts/runs/EXP-0005/review.md`; frozen spec
`experiments/hypotheses/HYP-0005.md`; benchmark curve `artifacts/runs/EXP-0005/depth_frontier.csv`.
Reproduce: `python -u forex/exploration_4/_run_stage_c_depth.py` (reuses `_run_stage_b`).
Overlay = depth veto on the frozen guarded book, **non-overlap re-applied after each veto**
(Stage-B F1). Started at the user's direction; conditional on EXP-0004 re-verify + Stage-A repairs.

- **t=2.0 reproduces EXP-0004 exactly** (n=66,912, gross −0.028, net −0.565) — parity check.
- **Depth ORDERS gross** (+0.057 R_slot per unit |z|): gross crosses zero at |z|≈2.8, reaches
  +0.13 pips at |z|≥3.8 — real reversion signal (the LEARNINGS "depth near-sufficient statistic"
  reappears). Each deep-tail gross CI still includes zero; it's the *ordering* that's real.
- **But NET never clears zero at any deployable depth:** best |z|≥3.8 (n=10,286) net −0.500
  R_slot [−0.707, −0.294]; net ≈ −0.5 to −0.57 across the whole grid. The ~1.25-pip cost dwarfs
  the ≤0.13-pip gross. **σ_slot FALLS slightly with depth** (2.93→2.73 pips: a big z often comes
  from a small σ), so there is no cost rescue at depth.
- **Null GATED OUT** (`gate-nullc-on-success-metric`): primary never cleared. Holdout deepest
  (|z|≥4.0, n=1,536) net −1.03, gross −0.81 pips — worse.
- **Use in Stage C:** `depth_frontier.csv` is the matched-count benchmark. Every later overlay
  must beat this (count→gross-R) curve at equal count; if one "helps", first suspect it is just
  selecting deeper |z_slot|.

### Axis 2 — volatility regime (compression vs expansion) (EXP-0006) — REJECTED as rescue

Report: `reports/STAGE_C_VOL.md`; review: `artifacts/runs/EXP-0006/review.md`; frozen spec
`experiments/hypotheses/HYP-0006.md`; frontiers `artifacts/runs/EXP-0006/regime_frontier_{compression,expansion}.csv`.
Reproduce: `python -u forex/exploration_4/_run_stage_c_vol.py` (~1 min, reuses `_run_stage_b`
book + `_run_stage_c_depth` benchmark). Overlay = a same-slot-normalized ambient-vol veto on
the frozen guarded book, **non-overlap re-applied after each veto**, scored as **excess over the
EXP-0005 depth benchmark at matched count**. Two symmetric arms (compression / expansion) swept.

- **Feature `vr_z` = same-slot z-score of `sigma_abs`** (the slow all-hours 28,800-min σ,
  deliberately NOT `sigma_slot` = depth's denominator). It is **largely depth-orthogonal**:
  `corr(vr_z, |z_slot|) = +0.134`, available on 99.8% of 160,040 trades — so this is a genuinely
  different axis and the null result is informative, not a depth restatement.
- **NET never clears zero on either arm at any deployable count.** Compression best net −0.526
  R_slot [−0.627,−0.425] (keep=0.15, n=11,869); expansion best −0.547 [−0.626,−0.468]
  (keep=0.60, n=36,965); net ≈ −0.53…−0.58 across both grids — the ~1.25-pip cost dwarfs any
  gross ordering (same wall as EXP-0004/0005).
- **Direction, such as it is: COMPRESSION mildly better, EXPANSION actively worse.** Expansion
  tight cuts go strongly gross-NEGATIVE (−0.38/−0.25/−0.10 R_slot at keep=0.10/0.15/0.20) and
  select deeper |z_slot| (abs_z 3.25 vs 2.77): **deep displacement in high ambient vol reverts
  LESS**, not more. Top `vr_z` bucket has the worst gross (−0.076). No cost rescue.
- **Null GATED OUT** (`gate-nullc-on-success-metric`): primary never cleared. The lone +0.023
  expansion excess over depth (keep=0.60) is a non-result — net still −0.547, CI far below 0,
  and it does not clear the net-zero bar the frozen rule requires. Holdout (compression
  keep=0.15, n=2,794) net −0.787, gross −0.279 pips — worse.
- **Verdict:** vol regime does not separate capturable from un-capturable reversion beyond
  depth; REJECTED as a rescue. Consistent with the honest prior (most overlays redundant).

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
- ~~**The effect concentrates in thin hours**~~ — **RETRACTED/NUANCED by EXP-0003.** See
  the addendum section below. The all-hours session breakdown was mostly a time-of-day
  selection artifact; a proper clustered difference (F3) leaves `off` not established and
  `asia` marginal/provisional only.
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
- **RETRACTED/NUANCED: the thin-hours localisation.** The original sum-of-half-widths
  screen cleared neither `off` nor `asia` under the same-slot arm. But that screen is a
  deliberately conservative heuristic, not a difference CI. The F3 repair added the proper
  **UTC-day-clustered difference CI** (captures same-day covariance): slot arm
  `off − london` = +0.169 CI [−0.023, +0.361] **includes 0** (not established);
  `asia − london` = +0.186 CI [+0.019, +0.353] **marginally excludes 0**. Normalising
  shrinks both gaps vs the confounded abs arm (off +0.427→+0.169, asia +0.274→+0.186), so
  the clock explained most of `off` and part of `asia`. **Verdict: `off` not established;
  `asia` provisional and NOT actionable** — marginal, on inspected history, one of several
  contrasts, without the arm-by-session interaction Codex asked for. Do not build a session
  overlay on it now; it is the **motivation for the axis-4 session test (full pipeline)**.
  Also: normalising nearly doubles Asia's count (16,689 → 33,255) and halves overlap's
  (37,429 → 16,808), so the old all-hours table never compared like with like. A thin hour
  like `asia` also carries a mechanical R_slot lift (small σ_slot), so a positive asia R gap
  is partly expected from the σ structure, not by itself tradable edge.
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
- Tests: `python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider` (26)

## Next action

**Stage-A code repairs are now PAID (2026-08-09):** EXP-0002/0003 F1–F5 applied + re-run
(cost-leak rebuild F2, per-session VR demean F5, fixed-H\* grain ranking F4, clustered session
contrast + provisional attribution + declared departures F3, honest P&L-selected labels F1);
τ\*=5/H\*=240 unchanged. Response in `reports/STAGE_A_INDEPENDENT_REVIEW.md`. **Two debts remain:**
(a) reviewer re-verification of the repaired EXP-0002/0003 and (b) Codex's re-verification of the
corrected EXP-0004. Every Stage-C result stays conditional on (b). Stage-B corrections (F1–F4)
ARE applied.

**Axis 1 (depth, EXP-0005) and axis 2 (vol regime, EXP-0006) are DONE — both REJECTED as
rescues.** **Next = axis 3: cross-pair divergence** (the one axis LEARNINGS flags as genuinely
orthogonal to the own-pair vol/directional lever) → **EXP-0007**, with the strictest re-pairing
null (destroy contemporaneous cross-information, preserve each leg's own dynamics; apply to the
error-correcting/follower leg identified a-priori from cointegration, NOT from P&L). Then axis 4
session (only after within-vol matching, null prior; note the F3 clustered contrast leaves a
MARGINAL/provisional `asia` gap — that is what axis 4 must test with a full-pipeline
arm-by-session interaction, not a prior to assume), axis 5 exit-side vol-conditional horizon.
Non-negotiable protocol: overlay acts as sizing/veto on the frozen trades (never fold into
entry); compare at matched selection rate in R units on a common sample; **beat the EXP-0005
depth benchmark at matched COUNT** (read `depth_frontier.csv` directly, not a frontier-interp);
claim-matched null through the full pipeline for each survivor, **gated on the primary metric
first**. An overlay survives only if it beats depth at matched count **and** clears its null.

**Stage-C carry-forwards from Stage B:**
- Score overlays as **excess over the EXP-0004 guarded book at matched count**, not vs zero.
- Test every overlay on the **guarded** book, not the optimistic touch/time variants, or it
  will inherit the un-fillable bare-touch profit that the guard removes.
- Expect a mechanical busy-hours net tilt in `R_slot` (σ_slot 2.2× across hours); an overlay
  must beat that, not rediscover it. Honest prior (`RUNBOOK.md` §7): most overlays redundant;
  cross-pair divergence is the only untested orthogonal axis; a real GO likely needs quote
  data, which this archive lacks.
