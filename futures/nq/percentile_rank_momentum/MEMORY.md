# Project Memory: NQ/ES Percentile-Rank Momentum + Bimodal Expected-Value

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: Test a **synthesis** — source (1) bimodal paper's expected-value-over-bins
  readout + source (2) percentile-rank paper's self-ranking bridge + hysteresis gate —
  as a **single-instrument** signal. Import machinery only; re-earn any edge on NQ under
  workspace RULES. See `paper/PAPER_SPEC.md`.
- Instruments or markets: NQ primary; ES sibling-transfer test only.
- Data coverage: `futures/nq/data/NQ_1m_clean.parquet` (1m RTH, UTC); 1s available.
- Current phase: HYP-0001 completed and rejected after EXP-0001/EXP-0002.

## Current status

- Verdict: rejected / NO-GO
- Last verified: 2026-08-22
- Lifecycle phase: closeout
- Baseline replication: not applicable; this is a synthesis, not a faithful replication
- Baseline tolerance and result: B0-B4 completed; B4 gross -0.122 and net -2.022 NQ ticks/trade
- Engine audit: faithful `core.engine` parity passed; adapter/unit suite passed; inherited generalized parity harness has a documented schema failure
- Execution profile: bar-close desired state, unchanged audited next-5-minute-open engine, RTH flatten, 1.9 NQ ticks modeled round-trip cost
- Holdout status: consumed; future-only
- Experiment ledger: `experiments/ledger.csv`
- Reproduction command: `python -m futures.nq.percentile_rank_momentum.experiments.run_hyp0001 --experiment-id EXP-0002`
- Primary evidence: `artifacts/runs/EXP-0002/review.md` and `reports/FINDINGS.md`

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline report: `reports/BASELINE_REPLICATION.md`
- Engine audit: `reports/ENGINE_AUDIT.md`
- Current findings: `reports/FINDINGS.md`

## Confirmed findings

- The amended 40%-of-W coverage rule is feasible: 85.5%–89.9% eligible.
- Hysteresis improves direct-feature gross retention but does not pay the 1.9-tick
  cost anywhere on the 24-cell alpha × W surface.
- NQ B4 has negative gross expectancy (-0.122 tick/trade) and underperforms
  matched-count B1 by -0.400 net tick/trade.
- ES B4 has the opposite gross sign (+0.331 tick/trade) and remains net-negative.

## Provisional hypotheses

- None active.

## Invalidated or superseded findings

- HYP-0001's expected-value ML edge is invalidated by EXP-0002's gross and
  matched-count gates. The deployable self-rank/hysteresis strategy is also a
  NO-GO because every stability cell is net-negative.

## Decisions and constraints

- Do not spend Null C on HYP-0001; its prerequisite real-data gates failed.
- Do not tune further on the inspected archive. A materially new mechanism needs
  a new hypothesis and future data is the only clean holdout.

## Known risks and open questions

- EXP-0002 independently reviewed by Claude (2026-08-22): reject / NO-GO
  confirmed; pipeline verified causal, cost/matched-count logic correct.
- The inherited generalized numba parity command fails on output-column mismatch
  before comparison; the faithful engine path used here passes.

## Next actions

1. Close the project or leave it as preserved negative evidence.
2. If a materially new feature is proposed, preregister it separately and use
   future shadow data rather than retuning HYP-0001 on consumed history.

## Promotion candidates

- None yet. Promote only findings verified and reusable across projects.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
