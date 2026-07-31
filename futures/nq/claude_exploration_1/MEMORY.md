# Project Memory: Cross-Asset Macro Exploration (DXY / GC / ES)

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: does an explicit macro factor — the **dollar** — carry usable information
  about gold and the equity indices, either as a decomposition of their moves, as a lead,
  as a regime label, or across the overnight boundary? Measurement first; a preregistered
  kill test before any promotion.
- Instruments or markets: GC, ES, NQ (1-min RTH 09:30-16:00 ET) plus a synthetic causal
  DXY built from CME FX futures 6E/6J/6B/6C.
- Data coverage: 2011-08-01 → 2026-07-15, **3,710** near-complete non-degraded sessions on
  the ES calendar (same degraded-day list as `vei_exploration` and `hurst_explore`, so the
  calendars are comparable across projects).
- Current phase: exploration complete for this programme; **all four hypotheses closed**.

## Current status

- **Verdict: NO edge found. All four preregistered hypotheses REJECTED.** The dollar's
  relationship to gold and the equity indices is, at every horizon tested (5-minute,
  30-minute, overnight-to-session), **contemporaneous and efficiently transmitted**. It is
  large — gold's causal dollar beta is −0.90 and the same-window correlation is −0.40 —
  and it carries essentially nothing at a lag, in a decomposition, or as a regime label.
- The project's durable output is **method**, not alpha: findings B (rank versus mean), E
  (match on volatility, not only on time of day) and G (the shared-endpoint artifact), plus
  a tested, reusable causal dollar factor.
- Last verified: 2026-07-31 (EXP-0001..0005).
- Lifecycle phase: exploration / hypothesis testing. No baseline replication and no engine
  are needed or built — nothing here trades.
- Baseline replication: not applicable (no source paper; this is an original exploration).
- Engine audit: not applicable. `tests/test_core.py` (30 checks, all passing) is the
  causality and invariant gate that stands in for it.
- Holdout status: **consumed research history.** Everything through 2026-07-15 has been
  looked at. Only future observations are clean.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction: `python -u -m futures.nq.claude_exploration_1.scripts.build_panel` then
  `... .scripts.{s1_residual_momentum, s2_lead_lag, s3_factor_coherence, s3b_gold_coherence, s4_overnight_impulse}`.
- Tests: `python -m futures.nq.claude_exploration_1.tests.test_core` (30/30 pass).
- Primary evidence: `reports/FINDINGS.md`; data gate `reports/DATA_QUALITY.md`.

## Authoritative artifacts

- Operating manual: `PROJECT_GUIDE.md`
- Current findings: `reports/FINDINGS.md`
- Rule-9a data gate: `reports/DATA_QUALITY.md`
- Immutable runs: `artifacts/runs/EXP-0001..0005/` (each has `review.md` + a `.txt` output)
- Not applicable for this project: `paper/`, `baseline_replication/`, `backtest_engine/`

## Confirmed findings

- **A / EXP-0001 — the dollar decomposition separates nothing intraday. REJECTED (KT3).**
  Paired within-slot IC delta +0.0044 [+0.0005,+0.0078] GC but −0.0017 ES / −0.0027 NQ:
  sign disagrees with **both** siblings. The metric was also mis-signed for the effect that
  exists (gold reverts, the preregistration assumed momentum); on the hypothesis' actual
  |IC| claim the residual is **worse** — 0.0360 → 0.0317 = 87.9% of raw. The degenerate
  factor leg carries the **same-signed** reversion (|IC| 0.0155) and the undecomposed sum
  carries the most, so there is nothing to isolate. Durable descriptive by-product, the
  **cross-asset reversion ordering** (endpoint-corrected): DXY −0.031, GC −0.032,
  ES/NQ ≈ 0. Gold behaves like a currency, not like an index — consistent with
  `futures/gc`'s repeated finding that momentum systems do not transfer to it.
- **B / EXP-0001 — rank IC and MEAN spread give OPPOSITE readings, on both asset classes.**
  GC rank IC **−0.0360** [CI excludes 0] with a mean q5−q1 spread of −0.15 ticks [CI spans
  0]; ES/NQ rank IC ≈ 0 [CIs span 0] with mean spreads **+1.09 / +3.34 ticks** [CIs exclude
  0]. Equity intraday momentum lives in the **tails**, which a rank statistic cannot see —
  the mechanical reason a **breakout** rule works on NQ/ES in `noise_vwap`. Extends
  `vei_exploration` EXP-0013's warning from trade P&L to **raw returns**, and it flips the
  conclusion in both directions rather than merely inflating one. **Report both, always.**
- **C / EXP-0002 — the dollar does NOT lead. REJECTED (KT2).** Forward
  pIC(past_dxy, fwd_GC | past_GC) = −0.0049 [−0.0078,−0.0020], correctly signed and
  significant — KT1 does not fire — but the **REVERSE is −0.0115, 2.36x larger** (ES 1.37x,
  NQ 2.72x). Gold appears to lead the dollar more than the reverse: shared/non-synchronous
  contemporaneous information, not transmission. **Not staleness** (KT3 clean: EUR-only,
  0.42% stale versus 4.70%, retains the whole effect). Economically 0.27 ticks against a
  ~$20 round trip; the contemporaneous link is ~75x the 5-minute lagged one.
- **D / EXP-0003 — factor coherence is not a momentum regime. REJECTED (KT1 + KT3).**
  ES +0.0179 [−0.0326,+0.0743], NQ +0.0191 [−0.0337,+0.0637] on the two preregistered
  markets; the rule-18 re-pairing null centres at ≈0 (well-behaved) with both real values
  inside it. The same-slot z-score calibration transferred exactly as `vei_exploration`
  finding I predicts. Selection-rate dial swings ES +0.0806/+0.0179/−0.0031 at 20/30/40%.
- **E / EXP-0005 — MATCH ON VOLATILITY, NOT ONLY ON TIME OF DAY.** Gold's contrast
  collapses **+0.0496 [+0.0069,+0.0853] → −0.0047 [−0.0274,+0.0272]** once the split is
  made within volatility quintiles as well as within slots; the mirror arm is +0.0020;
  the 100-draw null centres at 0 and gold's frac≥real goes 0.067 → 0.600. **Not a weakened
  split** — coherence spread between cells is unchanged (0.451/0.093 → 0.439/0.095) while
  the volatility ratio falls 1.46 → 1.11. EXP-0003 matched slot composition **exactly** and
  it was still not enough. Sub-lesson from the *selection* side of `vei_exploration`
  finding P: a modest pairwise correlation between two labels does **not** mean the cells
  they select are matched.
- **F / EXP-0004 — the overnight dollar channel is empty. REJECTED (all three KTs).**
  IC(short_GC, rth_GC) = −0.0301 [−0.0570,+0.0000]: CI touches zero and the sign is
  **negative**, declared in advance as a rejection. Unconstrained pair b1 +0.0261 /
  b2 −0.0338, both wrong-signed, **R² 0.0017**. GC/ES/NQ indistinguishable when the
  mechanism required ES to be much weaker. **Root cause, and the generalisable half:** the
  dollar explains only **R² 0.127** of gold's overnight gap, so the shortfall degenerates
  into the negative of the raw gap (the two ICs print −0.0301 and +0.0301). **A factor
  decomposition is only informative where the factor's R² is large; below roughly 20% the
  residual is not a different variable.**
- **G / EXP-0001 + EXP-0002 — the shared decision-bar close manufactures reversion.**
  `past` ends and `fwd` starts at the same close, so pricing error there enters with +1 and
  −1. Lagging the past window by one bar: at **30 min** 12-33% of the reversion is
  artifact; at **5 min** 31-56% is, worst (56%) on the synthetic dollar index. The majority
  survives everywhere, so the reversions are real — but any short-horizon reversal quoted
  without this control is inflated by a third to a half. Costs one column.
- **H — data layer (rule 9a).** A causal synthetic DXY from **published ICE weights**
  (never a fitted PCA — that would be a two-sided statistic under rule 8). Every CME FX leg
  enters `log DXY` with a **negative** coefficient. **Drop CHF:** 5-leg is 10.47%
  forward-filled versus 4.70% for 4-leg, at corr **0.9992** on 30-minute returns. FX
  staleness is strongly time-of-day dependent (0.5% first RTH hour → 10.7% last), because
  FX volume collapses after the London close.

## Provisional hypotheses

- None. All four are closed. The live *ideas* are in `experiments/IDEA_BACKLOG.md`; the two
  most valuable are (1) re-running this workspace's existing headline ICs alongside their
  mean-based twins, per finding B, and (2) a **daily-cadence** coherence label, since the
  60-minute intraday estimate is noisy and its noise is volatility-dependent.

## Invalidated or superseded findings

- EXP-0003's gold cell (+0.0496, "gold's momentum is stronger when it moves with the
  dollar") is **INVALIDATED** by EXP-0005. It was a volatility confound. Do not cite it.

## Decisions and constraints

- **Canonical dollar factor = the 4-leg basket** (6E/6J/6B/6C, ICE weights renormalised).
  `DXY_LEGS_5` and `DXY_LEGS_EUR` exist as preregistered sensitivity arms only. EUR-only
  correlates 0.9637 with the basket at 30-minute returns, which is what makes it a usable
  staleness control rather than a different variable.
- **Every cross-asset claim must be re-run on EUR-only.** Staleness manufactures both
  autocorrelation and lead-lag — exactly the two effects this project measures.
- **Every reversal claim must carry the lagged-endpoint control** (finding G).
- **Every regime split must be matched on volatility as well as on time of day**
  (finding E).
- **Report the mean alongside the rank** (finding B), and say which the decision consumes.
- β is fitted on 20 **strictly prior** sessions, through the origin, on 1-minute returns;
  tested to be blind to its own session and the future.

## Known risks and open questions

- **Power.** The overnight test has ~3,700 observations and a detectable |IC| floor of
  about 0.03; the primary estimate sits at that floor. Its "no effect" means "no effect
  larger than ~0.03", not zero.
- **Horizon-dependent β.** β is estimated on RTH 1-minute returns and applied to 15/30/60
  minute windows. It was checked at the *overnight* horizon (−0.968 versus −0.902, close)
  but not at intraday horizons.
- **Quintile matching in EXP-0005 leaves an 11% residual volatility gradient** between
  cells. Finer conditioning would reduce it at the cost of thinner cells; since the
  contrast is already centred on zero, it could only move further from the hypothesis.
- **NQ's significant negative in EXP-0005** (−0.0348 [−0.0630,−0.0045]: momentum works when
  NQ is *decoupled* from the dollar, gross +0.452 bp/bet at t=3.59) is the largest single
  number in the project and is **not promoted** — gold points the opposite way, ES is flat,
  and it is one cell of a 3-market × 3-arm table read after the primary had failed.
- **GC weekend-gap cell in EXP-0004** (−0.1347 on 800 sessions) is likewise a sliced null,
  recorded and not promoted.
- Rank ICs at the 5-minute clock use `nboot=200` rather than 400 for runtime; no verdict
  turns on a marginal interval.

## Next actions

1. **Nothing in this programme.** The dollar channel is closed at every horizon tested. Do
   not open a fifth cross-asset hypothesis on this pair without a mechanism that is not
   "the factor predicts the instrument".
2. Highest-value follow-on is **finding B applied backwards**: recompute the headline ICs
   of `vei_exploration` EXP-0011/0012/0015 alongside their mean-based twins. Evaluation
   only, no refit, cannot be re-tuning; it would say whether any of those conclusions were
   also taken on a statistic that does not track expectancy.
3. If the coherence idea is revisited at all, revisit it at **daily cadence** (backlog 3),
   not intraday — and match on volatility from the start.

## Promotion candidates

- **Finding E** ("match a regime split on volatility, not only on time of day") and
  **finding C's method half** ("test the reverse direction before believing a lead-lag")
  are both method claims that **changed the verdict of a run here**. They are candidates
  for `ai_shared_memory/LEARNINGS.md` once confirmed on a second project; they are claims
  about statistics rather than about this tape, so they should transfer.
- **Finding B** (rank versus mean) is the strongest candidate of the three and the easiest
  to confirm elsewhere — next action 2 is exactly that confirmation.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
