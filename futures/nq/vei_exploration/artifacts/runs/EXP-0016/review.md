# EXP-0016 Results Discussion

- Hypothesis: `HYP-0013` — a low-correlation six-feature set adds incremental
  forward-vol information beyond the two-input core.
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: PAIRED within-slot Spearman IC delta of `user6` over `core` against
  realised `fwd_rv_bp`, identical rows, 90% session-block-bootstrap CI, both markets.
- Kill test: REJECT unless the delta is positive with its CI excluding zero on BOTH
  markets (KT1); do not adopt unless it is >= +0.010 on both (KT2, the bar EXP-0011's
  +0.009 failed); report whether it lifts EXP-0015's expansion-magnitude cell (KT3).
- Reproduce: `python -u -m futures.nq.vei_exploration.scripts.hyp_0013_decorrelated_features {NQ|ES}`
- Outputs: `decorrelated_NQ.txt`, `decorrelated_ES.txt`, `decorrelated_{NQ,ES}.csv`

## Verdict in one line

**KT1 PASSES on both markets — the set really does add information — but the mechanism
proposed for it is REFUTED, and the disposition is CONFIRMED, NOT ADOPTED.** A post-hoc
control of three deliberately REDUNDANT volatility-level proxies matches or beats the
decorrelated six on every metric with half the features, including the one cell where the
candidate looked most exciting.

## Result versus hypothesis

| | NQ | ES |
| --- | --- | --- |
| core within-slot IC | +0.8802 | +0.8735 |
| `user6` within-slot IC | +0.8892 | +0.8834 |
| **PRIMARY paired delta** | **+0.0090 [+0.0082, +0.0099]** | **+0.0099 [+0.0091, +0.0109]** |
| KT1 (positive, CI excludes 0, both markets) | PASS | PASS |
| KT2 (delta >= +0.010, both markets) | FAIL | FAIL |
| KT3 (expansion-call skill vs persistence) | +0.0063 -> +0.0580 | +0.0558 -> +0.0943 |
| positive years / slots | 11/11, 11/11 | 11/11, 11/11 |

Evaluated on 29,254 (NQ) / 29,265 (ES) walk-forward rows over 2,711 / 2,714 sessions,
2016 through 2026-07-14. Rule-23 reproduction of the EXP-0011 notebook passed before any
comparison (|delta| 1.5e-05 and 6.8e-05 against a 5e-4 tolerance).

KT1 is a clean pass and it is not marginal in the statistical sense: the delta is positive
in every one of the eleven tested years, at every one of the eleven decision slots, on both
markets, with a session-block CI comfortably clear of zero. The set is not noise.

KT2 fails on both. The delta is +0.009 / +0.010 against a bar of +0.010 that was set
before the run from EXP-0011's precedent, where a +0.0088 / +0.0095 gain from six
multi-horizon variables was confirmed and then declined. Four new production dependencies
for the same gain must inherit that ruling.

## The control that decides what this means

`core_levels3` (core + `rv_15m`, `rv_60m`, `rv_120m` — three more measurements of the SAME
quantity, the redundancy the proposal was designed to avoid) was added AFTER the
preregistered arms had run, once the level-IC delta came out indistinguishable from
EXP-0011's. It is a control, not a candidate; the gates stayed on `user6`.

| | NQ | ES |
| --- | --- | --- |
| `user6` delta / `core_levels3` delta | +0.0090 / **+0.0093** | +0.0099 / **+0.0107** |
| log-MSE (lower better) | 0.07241 / **0.07134** | 0.07473 / **0.07423** |
| MAE bp | 4.490 / **4.454** | 3.686 / **3.657** |
| **expansion-call skill vs persistence** | +0.0580 / **+0.1000** | +0.0943 / **+0.1195** |
| change-IC | +0.4299 / +0.4301 | +0.4443 / +0.4423 |
| features added to core | 4 (+1 swap) / **3** | 4 (+1 swap) / **3** |

**Three redundant level proxies match or beat four orthogonal dimensions on every axis
except a tied change-IC, and beat them decisively on the expansion cell.** The stated
mechanism — that redundancy rather than saturation was the binding constraint — is
therefore refuted on this evidence. What produced the gain is having ANY additional local
state beyond the core's single `range_rv_15m`, not the particular dimensions added.

This is the EXP-0008 pattern recurring: the persuasive explanation loses to a deliberately
degenerate control, and the control is the most informative thing in the run.

## The premise, measured

The hypothesis required the correlation claim to be tested rather than assumed. It is
partly right and partly not (NQ figures; ES within +/-0.03 of each):

- **Genuinely orthogonal, as claimed:** `jump_share_60m` ~ `rv_ratio_15_60` **+0.000**,
  `overnight_rv_slot_z` ~ `path_efficiency_15m` **+0.009**, `path_efficiency_15m` ~ the
  seasonal **+0.020**. The four new variables really are near-independent of each other.
- **Not low at all:** the two SEASONALS `fwd_rv_bp_slot_median90` ~
  `fwd_abs_bp_slot_median90` correlate **+0.937 (NQ) / +0.910 (ES)**. The requested set's
  "swap" of one for the other is close to a no-op, which the `swap_only` arm confirms
  directly: +0.0005 / +0.0006. `user6` is, in substance, `core_plus4` with a marginally
  noisier seasonal — and the two arms are indeed identical to three decimal places.
- Also not low: `overnight_rv_slot_z` ~ `range_rv_15m` +0.429 / +0.460, and
  `range_rv_15m` ~ the seasonal +0.516 / +0.453.

So the set was less decorrelated than described, and the part that WAS decorrelated turned
out not to be what generated the gain. Low mutual correlation is necessary for incremental
value, not sufficient — the same conclusion EXP-0008 reached from the opposite direction.

`new4_only` (the four additions with no seasonal and no range) collapses to +0.4491 /
+0.5251, below even the seasonal median alone. They are supplements, not standalone
predictors.

## Regimes, sensitivity, and alternative explanations

- Per-year `user6`-minus-core delta: NQ +0.0057..+0.0202, ES +0.0061..+0.0202, positive in
  11/11 years on both. Per-slot: NQ +0.0059..+0.0134, ES +0.0049..+0.0137, positive at all
  11 slots on both. No era or time-of-day concentration.
- Alternative explanation considered and REJECTED: that the gain is the seasonal swap
  rather than the additions. `swap_only` isolates it at +0.0005 / +0.0006, and
  `core_plus4` (additions, original seasonal) reproduces the full `user6` delta to
  +0.0090 / +0.0098. The gain is entirely the additions.
- Alternative explanation considered and UPHELD: that the gain is generic to adding local
  state rather than specific to these dimensions. See the control section above.
- Reference legs that are not models: persistence within-slot IC +0.8668 / +0.8605,
  seasonal median +0.4199 / +0.3855. Every model arm except `new4_only` sits above
  persistence, consistent with EXP-0015.

## Artifact and implementation risks

- **Rule 9a.** Per-slot definedness of all candidate features is 0.983–1.000, and the
  common sample retains 40,585/41,710 (NQ) and 40,746/41,712 (ES) decision rows =
  97.3% / 97.7%. Per-slot retention 0.955–0.983, spread < 0.03 — UNIFORM, the pass signal.
  Per-year retention >= 0.976 everywhere except 2011 (0.43), the partially covered first
  year, which is outside the 2016+ test window. The 60-minute windows run on the
  continuous series and do reach across the overnight session at the early slots as
  anticipated, but the resulting loss does NOT track time of day.
- **All arms on one common sample.** Every arm trains and tests on identical rows, so no
  arm can win by being evaluated on an easier subset.
- **Sample sensitivity of the expansion cell, reported because it limits reading.** Adding
  `rv_120m` to the common-sample requirement moved NQ's core expansion skill from +0.0128
  to +0.0063 between two runs on nearly identical samples. Comparisons WITHIN a run are
  valid (identical rows), but small differences in that cell across runs must not be
  over-read. The `core_levels3` margin (+0.100 vs +0.058) is well outside that wobble; the
  precise size of `user6`'s own KT3 lift is not.
- Causality of each new feature is pinned in both directions by
  `tests/test_forward_vol.py` (perturbing a later bar must not change it; perturbing a bar
  inside its trailing window must), plus tests that a masked link voids rather than
  bridges the window, that `path_efficiency_15m` reads 1.0 on a straight line and < 0.1 on
  churn, that `jump_share_60m` is bounded in [0,1] and rises with an injected jump, and
  that overnight RV is keyed to the FOLLOWING RTH session with RTH bars excluded.
- `build_decision_frame(candidates=True)` is proved not to perturb the frozen core: the
  core columns are bit-identical with candidates on and off.
- **Consumed history.** 2024-01-01..2026-07-14 was already spent by EXP-0011 choosing
  between feature sets. This is a second search against the same target on the same
  window. Under rule 26 nothing here is confirmatory evidence.

## Builder interpretation

The proposal was a good one and it was right about the thing it could be checked on: the
four dimensions ARE nearly orthogonal, and the set DOES add real, era-stable, both-market
information. KT1 is a genuine pass, not a courtesy one.

But the reason it works is not the reason given. Three redundant windows of the same
quantity do the same job better with fewer features, so the binding constraint was never
redundancy — it was that the core had exactly ONE state variable. Add a second piece of
local state, of almost any kind, and you collect essentially the whole available gain.
Decorrelation bought nothing beyond that.

Three independent feature sets now buy the same amount on the LEVEL axis:

| set | level-IC delta over core, NQ / ES |
| --- | --- |
| EXP-0011 multi-horizon (6 redundant) | +0.0088 / +0.0095 |
| EXP-0016 `user6` (4 orthogonal + a swap) | +0.0090 / +0.0099 |
| EXP-0016 `core_levels3` (3 redundant) | +0.0093 / +0.0107 |

Everything lands at +0.009 to +0.011. **The level axis is saturated, now confirmed from
three directions, and the saturation is a property of the TARGET, not of any feature set.**

The genuinely new and valuable output is the asymmetry between the two axes. EXP-0015's
expansion-magnitude cell is NOT saturated, and this run is the first time it was measured
for a feature addition: core +0.006 / +0.056 rises to +0.100 / +0.120 on the best arm,
while the level moves by ~1%. **EXP-0011 rejected multi-horizon on the level metric, which
is exactly the metric that cannot discriminate between feature sets because it is
saturated.** That decision was taken on the wrong axis. This does not overturn the
operational ruling — "do not add six dependencies" may still be right — but its stated
ground ("the gain is only +0.009") is now known to be measuring the saturated axis.

Caveat, stated rather than buried: EXP-0011's actual six-variable multi-horizon set was
NOT re-run here, so the implication for that specific set is suggestive, not proven.
`core_levels3` is a three-variable analogue, not that set.

This project has now twice taken a decision using a metric that could not discriminate —
EXP-0008's `IC_fwdvol`, and now level IC for feature selection. The lesson generalises:
before running a feature search, check that the scoring metric still MOVES.

It also sharpens backlog item 13 rather than displacing it. Scheduled events remain the one
information source genuinely absent from every arm here — all six candidates and all three
redundant levels are functions of past price. That the expansion cell responds strongly to
more price-based state is encouraging for the calendar channel, not a substitute for it.

## Independent review

- Review status: pending
- Objections: independent review not yet assigned
- Verdict: builder verdict recorded — KT1 PASS both markets, KT2 FAIL both markets,
  mechanism REFUTED by the post-hoc redundant-level control; disposition CONFIRMED, NOT
  ADOPTED. Independent review pending.

## Promotion decision

- `reports/FINDINGS.md`: promote as finding section P.
- `MEMORY.md`: record the three-way level saturation, the refuted mechanism, and the
  level-IC-cannot-select-feature-sets warning.
- `experiments/IDEA_BACKLOG.md`: add the follow-up — re-score EXP-0011's multi-horizon set
  on the expansion cell, and choose a decision-shaped scoring metric before the next
  feature test.
- Shared `LEARNINGS.md`: candidate, held for one cross-project confirmation — "a saturated
  headline metric cannot discriminate between candidates; before a feature search, check
  the metric still moves, and run the redundant control against the clever one."
