# EXP-0043 Results Discussion

- Hypothesis: `HYP-0031` — require_reset re-entry: blocking same-side re-entry until price returns inside the Noise Area improves risk-adjusted performance
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: full-sample zero-trade-day daily net-ATR-R Sharpe uplift over the matched baseline; net R co-primary
- Kill test: REJECT unless, on the PRIMARY (deployed continuous-stop) NQ book, dSharpe >= +0.10 AND net R >= baseline
- Origin: user-supplied external spec (`Require reset rule.md`), an independent
  Noise-Area implementation's "run 18", reported there to improve Sharpe, CAGR,
  drawdown and P&L per trade versus its `later_decision` re-entry policy.

## Result versus hypothesis

**SPLIT VERDICT, and the splitting variable is the STOP-CHECK CADENCE.**

- **PRIMARY cell (deployed every-bar continuous stop): NO-GO on both markets.**
  NQ dSharpe **-0.011** with net R -4.41; ES dSharpe +0.003 with net R -2.45.
  Both fail the preregistered gate, so the drift-preserving Null C was not spent
  (standing project rule). An exposure-matched random drop from the same pool
  does at least as well as the rule: frac(random >= real) = **0.655** (NQ) /
  **0.825** (ES). On this book the lock carries no selection information.

- **SECONDARY cell (decision-clock stop = the source spec's run-18 cadence):
  PASSES its gate and its decisive control on both markets.** This cell is
  SEARCHED, not preregistered, and must be reported as such.
  NQ dSharpe **+0.117** / net R +4.77; ES dSharpe **+0.224** / net R +14.81.

Full 2x2 grid (`cells_{NQ,ES}.csv`), net-ATR-R daily Sharpe:

| market | stop book | reset cadence | n | retain | gross pt/trade | Sharpe | dSharpe | dNetR | maxDD |
|---|---|---|---|---|---|---|---|---|---|
| NQ | every_bar | (baseline) | 4209 | 1.000 | 3.509 | 1.288 | — | — | 4.70 |
| NQ | every_bar | every_bar | 3779 | 0.898 | 3.765 | 1.277 | -0.011 | -4.41 | 5.79 |
| NQ | every_bar | decision | 2829 | 0.672 | 3.889 | 1.251 | -0.037 | -12.90 | 5.28 |
| NQ | decision | (baseline) | 2923 | 1.000 | 4.945 | 1.292 | — | — | 7.45 |
| NQ | decision | every_bar | 2852 | 0.976 | 5.117 | 1.320 | +0.028 | +1.25 | 7.20 |
| NQ | decision | decision | 2528 | 0.865 | 6.087 | 1.409 | **+0.117** | +4.77 | 5.00 |
| ES | every_bar | (baseline) | 4326 | 1.000 | 0.730 | 0.698 | — | — | 7.45 |
| ES | every_bar | every_bar | 3872 | 0.895 | 0.759 | 0.700 | +0.003 | -2.45 | 7.54 |
| ES | every_bar | decision | 2884 | 0.667 | 0.829 | 0.717 | +0.019 | -7.10 | 10.18 |
| ES | decision | (baseline) | 2996 | 1.000 | 1.036 | 0.831 | — | — | 8.64 |
| ES | decision | every_bar | 2916 | 0.973 | 1.091 | 0.864 | +0.034 | +1.54 | 10.13 |
| ES | decision | decision | 2579 | 0.861 | 1.271 | 1.055 | **+0.224** | +14.81 | 6.83 |

## Gross, net, baseline, and null comparison

**Control 2 — what the lock trades away (`decomposition_*.json`).** The sign of
this diagnostic FLIPS between the two books, which is the mechanism evidence:

| cell | removed n | removed mean netR | removed gross pt | kept gross pt (vs base) |
|---|---|---|---|---|
| NQ every_bar/every_bar | 430 | **+0.0103** | +1.259 | 3.765 (3.509) |
| ES every_bar/every_bar | 454 | **+0.0054** | +0.483 | 0.759 (0.730) |
| NQ decision/decision | 395 | **-0.0121** | -2.362 | 6.087 (4.945) |
| ES decision/decision | 417 | **-0.0355** | -0.412 | 1.271 (1.036) |

On the continuous-stop book the rule deletes PROFITABLE trades (weaker winners)
— it is trimming exposure, not selecting. On the decision-clock book it deletes
genuine LOSERS and lifts per-trade quality by 23% (NQ) / 23% (ES). Set-difference
is descriptive, not causal (blocking an entry changes the state the rest of the
session simulates from), but the sign flip is unambiguous.

**Control 1 — exposure-matched random drop from the same pool.**
Valid on the primary cells only. NQ frac(random >= real) = 0.655 (real -0.011 vs
random +0.0115, sd 0.046; n 3779 vs 3776); ES 0.825 (real +0.003 vs random
+0.0484, sd 0.044; n 3872 vs 3875).

*This control was run twice and the first run was INVALID; both are preserved.*
The first version matched the number of times the lock FIRES (K=1129 NQ), which
is not the exposure it removes: the lock re-blocks the same suppressed breakout
at every later checkpoint, and conversely a blocked key is often recovered by
re-entering at the next checkpoint (calibration: one blocked key removes only
**0.586** trades). The random arm therefore cut ~666 NQ trades against the rule's
430, which flatters it in a book where fewer trades mechanically raises Sharpe.
Corrected results (above) are weaker than the first run's 0.740/0.955 but
unchanged in direction.

**Control 1 is DEGENERATE on the secondary cells and must not be read.**
Matching the rule's exposure there requires K == pool (797/797 NQ, 852/852 ES):
every draw is the same deterministic blocklist, sd = 0.0000, and it printed
frac = 0.000 — a false pass that would have been the run's strongest-looking
number. Root cause is structural: a one-shot entry blocklist cannot imitate a
PERSISTENT lock. Blocking 100% of the candidate pool once removes only ~153-310
trades versus the rule's 395. A guard now aborts this control when K >= pool.

**Control 1b (DECISIVE) — same lock, RANDOM unlock (`random_reset_null_*.csv`).**
The control the persistent lock actually admits: keep the lock, its side-scoping,
its cadence and its persistence, and replace ONLY its trigger — after a stop it
clears on a coin flip at hazard p per checked bar instead of on "price is back
inside the band". p is bisected to match the rule's trade count exactly.

| cell | hazard p | real n | null n mean [min,max] | real dSharpe | null dSharpe mean (sd) | frac(null >= real) |
|---|---|---|---|---|---|---|
| NQ decision/decision | 0.1773 | 2528 | 2541 [2506, 2567] | **+0.1170** | -0.0115 (0.0539) | **0.005** |
| ES decision/decision | 0.1730 | 2579 | 2567 [2543, 2608] | **+0.2240** | +0.0389 (0.0544) | **0.000** |

The null centres at ~0 on both markets: cooling off after a stop for the same
average duration, at the same trade count, is worth approximately NOTHING. The
entire effect is attributable to WHERE the lock releases — price returning inside
the noise area. This is the strongest single piece of evidence in the run.

**Control 6 — drift-preserving Null C (`nullc_*_decision_decision.csv`, 40 draws).**
- ES: real +0.224 vs null mean +0.023, z = +2.24, **frac(null >= real) = 0.000** — PASS.
- NQ: real +0.117 vs null mean **-0.038**, z = +1.75, **frac(null >= real) = 0.075** — MISS
  against the preregistered 0.05 (3 of 40 draws reproduced it). The null centre is
  NEGATIVE, which by this project's convention (EXP-0013) means the effect is tied
  to the thing being cut rather than fewer-trades variance amplification — but 0.075
  is a miss and is recorded as such, not rounded into a pass.

Diffusivity gate (median |next_open - close|), real vs one null draw:
NQ 0.2500/0.2500 (mean 0.2278 both, frac_zero 0.3926 both);
ES 0.0000/0.0000 (mean 0.1056 both, frac_zero 0.5797 both). Preserved exactly.

## Regimes, sensitivity, and alternative explanations

**The stop cadence is the whole story.** require_reset and the continuous stop
are SUBSTITUTES, not complements. A stop checked only 12x/day lets price run far
outside the band before exiting, so the breakout condition is usually still true
at the next checkpoint and the engine immediately re-buys the move that just
failed. The lock removes that churn. A stop checked every minute exits before
that state develops, so little churn is left for the lock to remove — and what it
does remove is profitable (control 2). This also predicts, correctly, that the
reset cadence matters much less than the stop cadence: on the decision-stop book,
every_bar reset gives only +0.028/+0.034 because a reset seen at ANY minute
releases the lock too easily; the value needs BOTH slow release and slow stop.

**Alternative explanation considered and rejected: clock artifact.** The winning
cell is the one where the reset check and stop check share a clock, which is the
shape of a phase artifact. Against this: the effect transfers to ES with the same
sign and larger magnitude (sibling-market mechanism test), the removed trades are
genuine losers with a large negative gross, and control 1b holds the cadence FIXED
while randomising only the trigger and kills the null. A pure clock coincidence
would not survive a control that shares its clock.

**Alternative explanation considered and NOT resolved: `retain` ~0.86.** The
effect is only measured on a book this project does not deploy and has already
rejected in favour of the continuous stop (EXP-0031: close-confirmed continuous
stop retained). Its practical value is therefore conditional on someone running
the slow-stop configuration.

**Rule 19 / shared-close caveat (pre-existing, project-wide, not introduced here):**
39% of NQ and **58%** of ES minutes open exactly at the prior minute's close. The
"honest" next-open fill is frequently the SAME NUMBER as the signal-bar close it
is meant to be separated from. This does not make the fill look-ahead (the market
did open there) and it affects treatment and baseline identically, but it means
the next-open convention buys less protection on ES than its name implies. Worth
recording against every ES result in this project, not just this one.

## Artifact and implementation risks

- Default-off parity asserted in code on BOTH stop books: `reentry="later_decision"`
  is bit-exact with the untouched engine (`assert_parity`, rule 23).
- 7 mechanics tests (`tests/test_require_reset.py`) pin the state machine,
  including the load-bearing evaluation order: the stop bar is itself usually
  INSIDE the band (the stop fires at the band edge when VWAP is inside), so
  checking reset AFTER the stop would clear the lock immediately and the rule
  would be a no-op. Spec order (reset -> stop -> entry) is enforced and tested.
- `random_reset` bounds verified: hazard 0 never unlocks; hazard 1 reproduces
  `later_decision` exactly.
- Full suite 59 passed (`test_vei.py` has a PRE-EXISTING relative-import
  collection error, untouched by this work).
- State is session-local; the first entry of each day is never blocked (tested).
  Carry-across-sessions was NOT tested — a documented scope choice, not a result.
- Two invalid controls were produced and corrected during this run (see above).
  Both are documented rather than discarded; the degenerate one is now guarded
  against in code.

## Builder interpretation

The rule is REAL and the friend's reported improvement REPRODUCES on this
project's audited engine — but only on the configuration they measured it on.
The decisive control (1b) is unusually clean: at matched exposure and matched
lock persistence, a random unlock is worth ~0 while the band-reset unlock is
worth +0.117/+0.224. That isolates the information to the reset CONDITION, which
is exactly the claim the spec makes. Cross-market sign transfer with a larger ES
effect, losing trades removed, and improved drawdown all corroborate it.

Against adoption here: it is worth nothing on the book this project actually
deploys (preregistered primary, both markets, NO-GO with a valid control), the
NQ Null C is a marginal miss at 0.075, and the passing cell is searched, on
consumed history, in a configuration already superseded by EXP-0031. The correct
reading is that the continuous stop ALREADY CAPTURES this value by a different
route, which is a satisfying convergence of two independent lines of work rather
than a new edge.

Recommendation: retain the deployed continuous-stop baseline unchanged. Keep
`reentry`/`random_reset` as tested, default-off engine machinery. Do NOT promote
require_reset as alpha. Report to the user that their friend's result is genuine
and well-controlled within its own configuration, and that the reason it does not
add here is a specific, testable structural fact about stop cadence.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: n/a — this project has no FINDINGS.md; confirmed findings
  live in `MEMORY.md` (see `reports/` = 5095349_EVALUATION, DATA_QUALITY, README).
- `MEMORY.md`: DONE — recorded under confirmed findings as EXP-0043, carrying the
  split verdict, the cadence-substitution mechanism, both invalid controls, and the
  ES shared-close caveat.
- Shared `LEARNINGS.md`: yes for the CONTROL-DESIGN lesson (a persistent stateful
  rule cannot be controlled by a one-shot filter; randomise the STATE TRANSITION,
  not the trade list), which is asset- and project-general and was demonstrated
  here by a degenerate control that printed a false frac=0.000. The require_reset
  finding itself stays project-local pending cross-project verification.
