# Final Critical Review — Cross-Asset Macro Exploration (DXY / GC / ES / NQ)

Date: 2026-07-31. Builder: Claude. Independent reviewer: **not yet assigned** — this
review is the builder's own, and the workflow's two-model requirement is unmet.

## Evidence quality

- **Baseline fidelity:** not applicable — there is no source paper. In its place each study
  asserts its own algebraic identities in-run and prints them into the artifact (`beta=0`
  reproduces raw momentum exactly; `resid + factor == past` to 1.7e-18). Those are weaker
  than a replication tolerance, and the project should be read as an original measurement
  exercise, not a validated reproduction of anything.
- **Engine integrity:** no execution engine exists because nothing trades. The substitute
  is `tests/test_core.py` — 30 checks, all passing — covering the failure modes that have
  produced false results in this workspace: roll splices entering returns, windows spanning
  sessions, a feature seeing its own future, a "de-seasonalised" label that is still a
  clock, a matched split that is not actually matched, and a null that does not destroy
  what it claims to. The regime-contrast statistic is additionally validated against a
  *planted* effect and against pure noise.
- **Data provenance:** Databento v0 continuous 1-minute files, tz-aware UTC throughout.
  Coverage, missing bars, forward-filled minutes and roll counts are reported per era and
  per 30-minute block in `reports/DATA_QUALITY.md` (rule 9a), for three separately-built
  dollar baskets. The gate found a real defect before any study ran — CHF more than doubles
  basket staleness for a 3.6% index weight — and it changed the primary specification.
- **Search/reuse burden:** four hypotheses, five runs, one primary cell declared per
  hypothesis in advance, with the sign declared in advance where the mechanism implied one.
  Searched surfaces are labelled as searches and read as slopes rather than argmaxes: the
  3x3 (W,H) grid in EXP-0001, the H term structure in EXP-0002, the selection-rate dial in
  EXP-0003. Two post-hoc slices are recorded and explicitly **not promoted** (EXP-0004's
  weekend-gap cell, EXP-0005's NQ negative). All history is consumed; nothing earned a
  forward test.
- **Null and negative controls:** the rule-18 re-pairing null was built as a
  **full-pipeline** null — the donor dollar path is a real dollar path from another session
  in the same calendar year, and β, coherence, the same-slot z-score, the quintiles, the
  split and the contrast are all recomputed on it. It was spent only where the real pass
  cleared its primary metric (EXP-0003, 30 draws; EXP-0005, 100 draws) and withheld
  elsewhere, per the standing gating rule. It centred at zero on every market in both runs,
  which is the well-behaved outcome and is itself evidence the null is doing its job.
  Degenerate or reversed controls decided three of the five runs.
- **Regime/cost/cross-market robustness:** every claim carries an era split (2011-2018 /
  2019-2026), an economic conversion into ticks and dollars against a round trip, and at
  least two markets. Nothing survived all three.
- **Holdout or future shadow evidence:** none. Everything through 2026-07-15 is consumed.

## Decision

- **Verdict: abandon this programme.** Not "watch" — there is no candidate to watch. All
  four preregistered hypotheses were rejected, the one attractive intermediate result
  (gold's coherence contrast) was destroyed by its own preregistered control, and the
  largest surviving economic number in the project is +0.238 ticks against a ~$20 round
  trip.
- **Deployment claim: none.** No configuration, market or cell here is proposed for
  capital, paper trading, or shadow logging.
- **What the project does establish.** The dollar's relationship to gold and the equity
  indices is large and **contemporaneous** — gold's causal beta is −0.90, same-window
  correlation −0.40 — and carries essentially nothing at a lag, in a decomposition, or as a
  regime label, at any of the three horizons tested. On gold the cross-asset relationship
  is roughly **75x larger contemporaneously than at one 5-minute lag**. That is what
  efficient transmission looks like: a coherent negative result, not an absence of one.
- **Remaining failure modes, honestly stated:**
  1. **Power.** The overnight test's detectable |IC| floor is ~0.03 and its estimate sits
     at that floor. Effects smaller than that were not resolved anywhere in this project.
  2. **Resolution.** Cross-asset transmission may be a seconds-scale phenomenon that
     1-minute bars cannot see. EXP-0002 bounds it at the 5-minute scale; it does not prove
     absence at finer resolution. 1-second NQ/ES/GC data exists in this workspace and was
     not used.
  3. **Unconditional only.** Every test measured the *average* tape. The one place a
     cross-asset lead is mechanically plausible — the minutes after a scheduled macro
     release — was not tested, and cannot be without an economic calendar.
  4. **Horizon-dependent β.** β is fitted on RTH 1-minute returns and applied to 15/30/60
     minute windows. Checked at the overnight horizon and clean; not checked intraday.
  5. **Single-reviewer risk.** No independent model or human has reviewed these runs. The
     preregistration defect in HYP-0001 — a signed metric written for an effect whose sign
     turned out to be the opposite — is exactly what a second reader catches, and here it
     surfaced only because the artifact printed the |IC| reading alongside.
- **Required next evidence:** none for the dollar channel itself. The valuable follow-on is
  orthogonal and re-analytic — recompute this workspace's existing headline ICs alongside
  their mean-based twins (finding B), which is evaluation-only and cannot be re-tuning.
  See `experiments/IDEA_BACKLOG.md` item 1.

## Note on what this project is for

Four rejections is the expected outcome of an honest exploration, and rule 25 says so
explicitly. The output that justifies the run is the section of `reports/FINDINGS.md`
headed *"What would have been concluded without the controls"*: on three of five runs a
normal exploratory pass would have produced a confident, correctly-signed,
CI-excluding-zero result that a single extra control then destroyed. Those three
controls — the degenerate factor leg, the reversed direction, and the volatility-matched
split — cost a few lines each.
