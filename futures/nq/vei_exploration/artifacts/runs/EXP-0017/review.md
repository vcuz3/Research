# EXP-0017 — Intraday implied volatility (VIX) vs the two-input forward-vol core

- Hypothesis: `experiments/hypotheses/HYP-0014.md` (preregistered before the run)
- Builder: Claude, 2026-07-31
- Reviewer: unassigned — review pending
- Verdict: **KT1 PASS both markets. KT2 FAIL both. KT4 FAIL both. KT3 direction holds.**
  → **Real information, REJECTED for adoption. Backlog item 17 is CLOSED: no longer
  data-blocked, now tested and answered.**
- Reproduce:
  `python -u -m futures.nq.vei_exploration.scripts.hyp_0014_implied_vol {NQ|ES}`
  `python -u -m futures.nq.vei_exploration.scripts.hyp_0014b_premium_cell {NQ|ES}`
- Artifacts: `implied_vol_{NQ,ES}.{txt,csv}`, `premium_cell_{NQ,ES}.txt`

## Why this run exists

Backlog item **17** recorded "trade volatility as the object itself" as DATA-BLOCKED:
"no options data exists in this workspace, and there is no good intraday implied proxy
from futures alone." `futures/data/vix/` — ten contiguous TradingView `CBOE_DLY_VIX, 15`
exports covering 2011-08-01..2026-07-17 — unblocks it. Backlog item **13** names the same
gap from the other side: every feature this project has tested is a function of PAST
PRICE, and finding P showed they all converge on the same saturated level-IC ceiling.
VIX is the first available input that is not past price, so it is the first that can
contain volatility which has been *scheduled* but has not yet happened.

Per backlog item **20**, the deciding metric was declared before the run and is NOT level
IC (saturated, cannot discriminate) but the **expansion-call log-MSE skill over
persistence** — and the bar was set at EXP-0016's deliberately REDUNDANT control, not at
the bare core.

## Data quality (rule 9a)

- 10 tiles, 101,981 bars, **zero duplicate timestamps**, contiguous and non-overlapping,
  median 27 bars/session (09:30..16:00 at 15 minutes), VIX range 8.96..84.56, no
  non-positive prints.
- **Causal join, asserted in code:** a VIX bar stamped `T` covers `[T, T+15m)`, so it is
  admissible only if `T + 15m <= ts_utc + 1m` (the decision's information cutoff).
  The clocks align exactly — decision cutoffs at :00/:30 coincide with VIX bar closes —
  so quote staleness is **0 minutes on 41,115 of 41,134 joined rows**, and >20 minutes on
  4 rows. Nothing is forward-filled beyond a 45-minute tolerance.
- **Join rate 98.62%.** The loss is 576 rows over **87 US market holidays** on which CME
  trades a shortened session while cash VIX does not publish at all; 86 of the 87 are
  partial futures sessions and 85 are wholly unjoined. The apparent "morning slots join
  worse" pattern (97.8% vs 100%) is entirely this: holiday sessions only *have* morning
  decision rows. The loss is therefore whole-session, not slot-selective, and the holiday
  calendar is known in advance, so the exclusion is causal.
- Common sample 96.53% NQ / 96.82% ES, per-slot retention 0.939–0.983 (NQ) and
  0.955–0.984 (ES) — **uniform, the pass signal**. Every arm trains and tests on
  identical rows.
- Rule 23: the core reproduced EXP-0011's published pooled ICs to |diff| 1.5e-05 and
  6.8e-05 before anything was compared to it.
- Tests 43/43 (35 existing + 8 new in `tests/test_vix.py`, pinning the join causality,
  the `lag_bars` direction, the no-forward-fill rule, the bp conversion and the slot-z).

## What VIX is, measured

| feature | NQ within-slot IC | ES within-slot IC |
|---|---|---|
| `range_rv_15m` (the core's only state variable) | **+0.8586** | **+0.8538** |
| `past_rv30_bp` (persistence benchmark) | +0.8453 | +0.8377 |
| `vix_fwd30_bp` | +0.6739 | +0.6697 |
| `vrp_log` | −0.6112 | −0.6070 |
| `fwd_rv_bp_slot_median90` (the core's seasonal) | +0.3946 | +0.3643 |

Three structural facts, all of which reproduce prior project findings in a new domain:

1. **As a volatility-LEVEL proxy VIX is worse than what the core already holds** (+0.674
   against +0.859). It does beat the causal same-slot median, i.e. it is a better
   *seasonal anchor* than a 90-session trailing median — which is not what the core needs.
2. **The naive variance risk premium is mostly its own DENOMINATOR.**
   `corr(vrp_log, past_rv30_bp) = −0.857 NQ / −0.843 ES`. VIX is a daily-scale quantity
   that barely moves across a 30-minute clock, so `log(implied) − log(realised)` is
   dominated by the realised leg. **This is finding H in a new costume**, and the
   degenerate control settles it the same way: the bare denominator (|IC| 0.845) beats
   the ratio (|IC| 0.611). Residualising the premium on realised volatility leaves the
   VIX level plus noise, so there is no separate "premium" dimension to exploit.
3. **The raw premium is a CLOCK** (finding I): mean `vrp_log` runs −0.110 → +0.689 across
   the eleven NQ slots (implied/realised 0.85 → 1.78; ES 1.23 → 2.12), because implied is
   flat by construction while realised decays through the session. Note the level is
   economically sensible and validates the units: NQ's opening 30 minutes realise *more*
   than the daily-average VIX implies (ratio 0.85) while ES is above 1.0 all day, exactly
   as expected for an SPX-derived measure applied to a more volatile index.
4. `vix_chg_15m` correlates −0.47 NQ / −0.51 ES with the market's own trailing return, so
   a "VIX change" feature is substantially a restatement of past price.

## Primary result

Walk-forward, expanding window, first tested year 2016, one frozen learner, 28,942 NQ /
28,946 ES evaluated rows over 2,646 sessions.

**Expansion-call log-MSE skill over persistence** (the declared deciding metric):

| arm | NQ | ES |
|---|---|---|
| `core` | +0.0164 | +0.0638 |
| **`core_vix`** (candidate) | **+0.0656** | **+0.0972** |
| `core_vix_all` (broad diagnostic, not a selection) | +0.0897 | +0.1103 |
| `core_pastrv` (**degenerate control**: core + `past_rv30_bp`) | +0.0717 | +0.1061 |
| `core_levels3` (**redundant control**, EXP-0016) | +0.1069 | +0.1311 |
| `vix_only` | −0.6494 | −0.8811 |

Secondary within-slot IC delta over `core` (saturated axis, reported not deciding):
`core_vix` **+0.0034 [+0.0024,+0.0044] NQ** and **+0.0063 [+0.0053,+0.0074] ES**,
positive in **11/11 years and 11/11 slots on both markets**; `core_levels3` +0.0095/+0.0108;
`core_pastrv` +0.0030/+0.0039; `vix_only` −0.0708/−0.0879.

### Gates

- **KT1 (statistical) — PASS both.** The delta is positive with its CI excluding zero,
  and stable across every year and every slot. VIX carries real incremental information;
  that is not in doubt.
- **KT2 (decision metric) — FAIL both.** +0.0656 vs the +0.100 bar (NQ) and +0.0972 vs
  +0.120 (ES). The in-run redundant control landed at +0.1069/+0.1311, reproducing
  EXP-0016's published +0.100/+0.120 closely. **Three redundant measurements of past
  realised volatility beat implied volatility on the metric that matters, on both
  markets.**
- **KT4 (degenerate control) — FAIL both.** +0.0656 vs +0.0717 (NQ) and +0.0972 vs
  +0.1061 (ES). Simply handing the model **one extra column it already computes** — its
  own persistence benchmark — beats adding three VIX features. This is the decisive arm.
- **KT3 (mechanism) — direction HOLDS.** VIX is an SPX measure, so the mechanism predicted
  ES ≥ NQ. It is: expansion skill +0.0972 ES vs +0.0656 NQ, level delta +0.0063 vs
  +0.0034. The market where VIX is the *native* implied measure gets roughly twice as
  much from it. So the thing being measured genuinely is implied-volatility content
  rather than a generic artifact — it is simply too small to matter.

### Robustness

Lagging the quote a further full 15 minutes (`lag_bars=1`) changes essentially nothing:
NQ expansion skill +0.0691 (fresh +0.0656), ES +0.0890 (fresh +0.0972); within-slot IC
+0.8807/+0.8767 against +0.8811/+0.8773. Nothing depended on the join boundary.

## The mechanism is REVERSED — the follow-up's real contribution

EXP-0017b (post-hoc, not a gate) asked where the aggregate metric might be hiding a
pocket. The hypothesised mechanism was *anticipation*: implied rich against realised is
the pre-announcement signature, so VIX should pay most where the premium is extreme and
at the FOMC window. **The data says the opposite, identically on both markets.**

`core_vix − core` expansion skill by premium quintile (q5 = options richest vs realised):

| | q1 | q2 | q3 | q4 | q5 |
|---|---|---|---|---|---|
| NQ | **+0.2220** | +0.0933 | +0.0971 | +0.0528 | **+0.0189** |
| ES | **+0.2746** | +0.1068 | +0.0616 | +0.0269 | **+0.0121** |

Monotone *decreasing*. VIX pays most where implied is unusually **CHEAP** relative to
realised — i.e. immediately after a realised-volatility spike, where the past-price core
over-extrapolates (its skill there is −0.187 NQ / −0.203 ES, worse than persistence) and a
slow daily-scale anchor pulls the forecast back toward normal. **VIX's contribution is
ANCHORING, not ANTICIPATION.**

Three confirmations of the same reading:

- **The announcement window is VIX's worst slot.** At mfo 269 (13:59, forecasting
  14:00–14:30 ET — the FOMC statement window and the most concentrated scheduled
  intraday volatility event in the session) the gap is **+0.0004 NQ / +0.0237 ES**, at or
  near the bottom of all eleven slots. The largest gaps are the *morning* slots
  (+0.1678/+0.2028 NQ at 09:59/10:29), where the past-price state is thinnest and an
  overnight-informed anchor helps most.
- **VIX makes the easy calls worse and the hard calls better.** By decile of the core's
  own error, `core_vix − core` is negative in d1–d5 (−0.18 to −0.05) and positive in
  d7–d10 (+0.04 to +0.13), on both markets. It is a redistribution of accuracy, not a
  uniform gain.
- **Even in its best cell, the redundant control matches it.** In q1, `core_levels3`
  scores +0.0381 NQ / +0.0190 ES against `core_vix`'s +0.0351/+0.0719 — the anchoring job
  is done about as well by a longer realised-volatility window (`rv_120m`).

### One caveat on the follow-up's own precondition test

`vrp_log_slot_z` has within-slot IC +0.322 NQ / +0.339 ES with the realised log-change
`log(fwd/past)`, and the quintile means rise monotonically. **This number is inflated by a
shared term and must not be quoted as evidence of anticipation:** the premium is
`log(implied) − log(past)` and the target is `log(fwd) − log(past)`, so both carry
`−log(past)` and are mechanically linked. This is the same family as
`claude_exploration_1`'s shared-decision-bar artifact. The quintile table in §1 is the
load-bearing evidence; this one is not.

## Alternative explanations considered

- *Timing/staleness.* Ruled out: staleness is 0 minutes on 99.95% of joined rows and the
  `lag_bars=1` arm reproduces the result.
- *The holiday exclusion is a hidden filter.* Ruled out: whole-session, calendar-known,
  and per-slot retention is uniform (0.939–0.983).
- *VIX is simply a weak level proxy and the level axis is saturated, so any feature would
  fail.* Not the explanation — the expansion cell is demonstrably NOT saturated (it moves
  from +0.016 to +0.107 within this run), and VIX moves it materially (+0.049/+0.033). It
  simply moves it less than two past-price controls do.
- *The learner cannot use VIX.* Argues against itself: `core_vix_all` (11 VIX features)
  reaches +0.0897/+0.1103, closer to the bar. More VIX featurisation narrows the gap but
  never closes it against `core_levels3`, and `core_vix_all` is explicitly a diagnostic,
  not a selection — if it won it would identify nothing about which ingredient earned it.
- *Spot VIX is the wrong instrument.* **This survives as the strongest live objection.**
  VIX is 30-*day* implied volatility; VIX1D/VIX9D would encode "the next few hours
  specifically are dangerous" in a way a 30-day measure structurally cannot. The
  announcement-window result is evidence *for* this objection, not against it: the
  mechanism failed exactly where a tenor-appropriate instrument should have succeeded.
  Recorded as the surviving lead, not as a rescue of this result.

## Builder interpretation

VIX is real information and it is not a fluke: the increment is positive in 11/11 years
and 11/11 slots on both markets, its CI excludes zero, it survives a 15-minute lag, and
its cross-market asymmetry points the way the mechanism predicts. It is nevertheless
**not worth a production dependency on an external daily-scale data feed**, because on
the metric declared in advance it is beaten by adding one column the project already
computes (`past_rv30_bp`) and beaten more decisively by three redundant realised-vol
windows.

The finding worth keeping is the mechanism reversal. The project sought an *anticipator*
of scheduled expansion and found an *anchor* against realised-vol shocks — most valuable
where implied is cheap, in the information-poor morning, and on the hardest calls; least
valuable at the FOMC window and where the premium is richest. That is a genuine and
cross-market-confirmed correction to the stated thesis, and it redirects backlog item 13:
**VIX is not a usable proxy for the scheduled-event channel.** If that channel is pursued
it needs an explicit event calendar, or a tenor-matched implied series (VIX1D/VIX9D),
not spot VIX.

Consumed history throughout (rule 26). Nothing here is confirmatory, and nothing is
promoted.
