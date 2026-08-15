# EXP-0004 review — Stage B: frozen same-slot z-fade reference book

- **Pre-specs:** `experiments/hypotheses/HYP-0004.md` and `artifacts/runs/EXP-0004/KILL_TEST.md`,
  both frozen before the run.
- **Config:** `baseline_replication/configs/stage_b.json`
- **Command:** `python -u forex/exploration_4/_run_stage_b.py` (~1 min)
- **Simulator + tests:** `_stage_b_lib.simulate_anchor_retrace`;
  `python -m pytest forex/exploration_4/test_stage_b.py -q -p no:cacheprovider` — 12 passed;
  `test_stage_a.py` still 25 passed (conftest adds `exploration_1` to the path).
- **Builder:** Claude. **Reviewer:** unassigned. **Review status:** pending.

---

## 1. What was frozen

One reference book, all parameters by fiat from Stage A (`RUNBOOK.md` §4.1), nothing tuned to
PnL: τ=5 same-slot z, fade `|z_slot| ≥ 2.0` first crossing, **delay-1** entry, 240-min cap,
**no stop**, news ±30 min and Friday-16:55-NY vetoes, one position per pair. The only new
element is the exit: a **guarded anchor-retrace** limit (credited only on a 0.25·σ_slot
trade-through of the anchor, filled conservatively **at the anchor price**), bracketed by a
**touch** ceiling (g=0) and a pure **time-exit** floor.

## 2. Headline result (pooled, consumed, delay-1)

| exit treatment | n | gross R_slot | 95% CI | gross pips | fill rate | timeout | win rate |
| --- | --- | --- | --- | --- | --- | --- | --- |
| time (floor) | 137,807 | 0.1466 | [0.072, 0.222] | 0.368 | — | 1.000 | 0.510 |
| touch (ceiling) | 137,807 | 0.1578 | [0.099, 0.217] | 0.377 | 0.714 | 0.286 | 0.763 |
| **guarded (the book)** | 137,807 | **−0.0245** | **[−0.085, 0.036]** | **−0.137** | 0.688 | 0.312 | 0.744 |

- **Machinery check:** the `time` treatment reproduces EXP-0003 (+0.368 gross pips vs 0.383;
  R_slot CI excludes zero) — the runner is consistent with the characterization it rests on.
- **The book's verdict:** under a realistic guarded fill, gross reversion at delay-1 is
  **−0.137 pips, CI includes zero** — no capturable gross edge. Net at base cost is
  **−0.563 R_slot** [−0.624, −0.502]; negative in every cost scenario and every era. The
  three Sharpes are ≈ −4.6 to −5.6 on net. The sealed 2024+ holdout, opened once, agrees
  (gross −0.206 pips, net −0.686 R_slot).

## 3. The finding beyond EXP-0003 (verified trade-by-trade)

EXP-0003 said the τ=5 reversion is real but ~3× too small to pay costs. Stage B adds a
second, independent reason it is not tradable: **it is not capturable by a realistic passive
exit.** Decomposing touch vs guarded on the identical 137,807-trade set (`trades.parquet`):

- **Both fill (68.8%)** → identical +6.90 pips (fill-at-anchor logic is consistent across
  treatments, as designed).
- **Both timeout (28.6%)** → identical −15.95 pips.
- **Marginal 2.6%** (touch fills, guarded misses) → touch books **+7.64**, guarded rides to
  timeout for **−12.13**. The 19.8-pip swing × 2.6% = **0.51 pips**, which is *exactly* the
  touch→guarded gross gap (0.377 → −0.137).

Interpretation: on these trades price mean-reverts *just* to the anchor and reverses — the
anchor is itself the reversal point. Crediting a fill on a bare touch (the geometry implicit
in a fixed-horizon/touch measurement) captures those; requiring the vol-scaled trade-through
evidence Rule 4 demands does not, and you give back ~20 pips each. The book also shows the
classic no-stop mean-reversion payoff: win rate 0.74 but negative expectancy, because the
~31% timeouts (−16 pips) outweigh the ~69% anchor wins (+7 pips).

## 4. Alternative explanations considered

- **Is the guard a bug that suppresses fills it shouldn't?** No. `test_stage_b.py` pins the
  fill/gap/guard/cap rules against hand-computed answers, and the both-fill / both-timeout
  cells are byte-identical between touch and guarded — only the marginal band moves, and it
  moves in the direction and magnitude arithmetic predicts.
- **Is −0.137 just the shared-endpoint artifact removed?** Partly the opposite: delay-0
  (artifact-inflated) guarded is only +0.091 pips and delay-1 guarded is −0.137, so even the
  optimistic entry arm barely clears zero gross under a realistic fill. The delay-1 `time`
  arm (+0.368) matches EXP-0003, so the sign flip is the *exit*, not the entry.
- **Did same-slot sizing distort the comparison?** Both units are reported; `R_abs` tells the
  same story (guarded −0.040, touch +0.110). The busy-hours net tilt in `R_slot` is present
  and mechanical (per-session table), and no overlay is built on it (`RUNBOOK.md` §4.3).
- **g = 0.25σ arbitrary?** Yes, it is a frozen fiat choice. The touch (g=0) ceiling and the
  time floor bracket it, so the reader sees the full sensitivity: the edge exists only at
  g≈0, i.e. only if a bare touch is a fill. A guard sweep is a fair Stage-C diagnostic but
  changes nothing about the cost verdict (best gross 0.38 pips « 1.23 pip round trip).

## 5. Departures and limitations

- **No departures from HYP-0004/KILL_TEST.** All parameters are as frozen; the exit was
  chosen and frozen in the kill test before the run (`RUNBOOK.md` §4.2 recommended default).
- **The guarded fill is a model**, not a measured fill — the archive has no bid/ask. The
  time-exit floor needs no fill assumption and is itself net-negative, so the NO-GO does not
  rest on the fill model. If a decision ever hinged on cost/fill, the honest next step is
  quote data (`RUNBOOK.md` §7), not another overlay.
- **UTC slots do not track DST.** Documented, not corrected.
- **2024+** read exactly once, at the end; it informed no frozen choice.

## 6. Builder interpretation

The reference book is frozen and is a **valid ruler** (Rule 25). It is a well-characterised
NO-GO: at τ=5 the same-slot z-fade has no gross reversion that survives a realistic passive
exit, and even its optimistic gross is ~3× short of modelled cost. Stage C overlays are to be
scored as **excess over THIS book at matched count**, not against zero — and the honest prior
(`RUNBOOK.md` §7) is that most will be redundant. The one finding that would change the
picture is an overlay that raises gross *per trade by a factor* (cross-pair divergence is the
only untested orthogonal axis), or genuine quote data that overturns the cost side.

**Candidate LEARNINGS entry (provisional, pending review):** an anchor-/level-retrace passive
exit's apparent edge can live *entirely* in the touch-vs-fill assumption when the retrace
target is also the reversal point; require a vol-scaled trade-through before crediting the
limit and a fixed-horizon-positive book can go gross-negative. Added to
`ai_shared_memory/LEARNINGS.md` §6 as provisional.

## 8. Response to independent review (Codex, 2026-08-09)

Reviewer file: `independent_review_codex.md` (verdict: *changes required before EXP-0004 is
the Stage-C ruler*; NO-GO direction judged robust). All findings accepted; the run was
repaired and re-run. **Sections 1–7 above are the pre-review builder notes and are
superseded where they conflict with this response** (notably the "floor/ceiling/bracket"
language and the all-signal headline). Corrected artifacts regenerated by the same command.

**F1 (High) — headline estimand ≠ the one-position book. Fixed.** `apply_non_overlap` now
marks the stateful one-position-per-pair set (greedy non-overlap per pair/delay/treatment,
full timeline, causal), and **every book-labelled metric** — surface, CIs, era/pair/session,
cost curve, Sharpes, holdout — runs on it. The all-signal per-signal mean survives only as an
explicitly labelled diagnostic. Primary n falls 137,807 → **66,912**; the direction is
unchanged (guarded gross −0.028 R_slot, CI **[−0.083, +0.027]** now includes zero → *not
established*; net −0.565 R_slot). `overlap_reduction.csv` reports the occupancy drop
(guarded ≈49%, time ≈68%). Noted for Stage C: because exits differ by treatment the surviving
set differs, so overlays must be re-run through this machinery, not filtered post-hoc.

**F2 (High) — already-crossed limits held to cap. Fixed with a causal no-entry rule.**
`_stage_b_lib.anchor_favourable` (parity-tested) rejects, at entry, any signal whose anchor is
already crossed — both the entry price and anchor are known then, so it is causal. **7,105
delay-1 signals** are removed and enumerated in the funnel; the simulator keeps its defensive
ride-to-cap only as an unreachable safety branch.

**F2/cost — holdout leaks into consumed cost normalisation. Fixed.** The vol-ratio median is
now taken from the **consumed era only** (`sig.era != "holdout"`), so the sealed 2024+ segment
no longer touches pre-2024 cost/net columns. Effect is tiny (cost ≈1.234 pips) and does not
change the verdict, as the reviewer expected.

**F3 (Medium) — floor/ceiling/bracket language. Fixed.** `touch` and `time` are now labelled
**diagnostics/comparators, not payoff bounds**; the report states explicitly that `touch`
maximises fill probability (not P&L) and that guarded gross sits *below* both, so neither
brackets it. A callout box carries the correction.

**F4 (Medium) — unreported exclusions. Fixed.** A rerunnable Rule-9a funnel
(`exclusion_funnel.csv` + report §1) separates news / zero-cap / already-crossed / incomplete-
path / Friday-shortened / book-eligible, by pair, era and UTC hour. It shows the post-news
path loss is not hour-neutral (incomplete paths concentrate at 17–21 UTC from the rollover/
weekend hole; news vetoes at 12–15 UTC).

**Minor wording. Fixed.** "CI includes 0" is now reported as *positive reversion not
established* (never "reversion absent"); the negative gross is described as the **rebate to
zero** (−0.172 pips), not a breakeven round trip.

**Stage-A review F1 (inherited τ/H are P&L-selected). Relabelled.** The report and verdict now
state τ=5/H=240 are **Stage-A consumed-history gross-P&L-selected candidates**, not untuned or
confirmed, and that a selection-aware null is required for any inferential claim about the
selected maximum. The "nothing tuned to PnL" claim is narrowed to "Stage B adds no *new* P&L
tuning". The remaining EXP-0002/0003 code repairs (Stage-A review F3–F5: session-retraction
attribution as provisional, the addendum's two-horizon search, per-session VR demeaning) are
Stage-A tasks tracked in `MEMORY.md`, not resolved here.

**Reviewer verdict recorded:** changes required → **corrections applied, pending reviewer
re-verification.** The NO-GO direction is unchanged and now rests on the deployable one-
position estimand with causal fills and full coverage accounting.

## 7. Independent review checklist

1. Rerun the tests and the EXP-0004 command; confirm `verdict.json` reproduces.
2. Confirm the `time` treatment reproduces the EXP-0003 delay-1 gross (machinery parity).
3. Re-derive the touch→guarded decomposition in §3 from `trades.parquet` (the whole verdict
   turns on it).
4. Check `simulate_anchor_retrace`: fill-at-anchor (no gap improvement), guard as a live-bar
   trade-through, `anchor_dist ≤ 0` rides to cap, per-row Friday cap. Confirm the parity tests
   cover each branch.
5. Confirm no frozen choice reads 2024+, and that no parameter was tuned to PnL.
