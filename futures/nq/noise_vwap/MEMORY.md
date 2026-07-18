# Project Memory: Noise Area VWAP

This file is the concise handoff for the project. Detailed evidence remains in
the linked reports, code, and run artifacts.

## Scope

- Objective: faithfully reproduce the published Noise Area VWAP strategy, audit
  its implementation, and test whether robust NQ/ES improvements exist.
- Instruments or markets: NQ and ES futures.
- Data coverage: 2011-2026 clean Databento research history.
- Current phase: final validation / future-shadow planning.

## Current status

- Verdict: qualified paper replication; research watchlist, not deployment-ready.
- Last verified: 2026-07-18 from the current forensic and review reports plus
  Null C invariant tests.
- Lifecycle phase: final validation.
- Baseline replication: passed after correcting decision-clock and VWAP-gate
  discrepancies.
- Baseline tolerance and result: clean faithful headline is approximately NQ
  28.3% return / 1.31 Sharpe, ES 15.5% / 0.81, and equal-weight portfolio 23.8%
  / 1.52; compare published NQ 24.3% / 1.67, ES 16.8% / 1.25, portfolio 22.4%
  / 1.57.
- Engine audit: next-open faithful path and parity tooling exist. The Null C
  opening-sentinel defect is fixed and its anchor, net-move, atom, diffusivity,
  and pairing invariants are tested; the faithful configuration still needs a
  clean post-fix Null C rerun.
- Execution profile: signal after the decision bar, fill at the next available
  bar open with explicit costs; `signal_close` is an ablation only.
- Holdout status: consumed. Only future shadow data can be clean holdout evidence.
- Experiment ledger: `experiments/ledger.csv` (legacy rows are reconstructed).
- Reproduction command: `python -m futures.nq.noise_vwap.scripts.forensic`.
- Primary evidence: `FORENSIC.md` and `REVIEW.md`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Baseline evidence: `FORENSIC.md`
- Engine and pipeline review: `REVIEW.md`
- Data audit: `DATA_AUDIT.md`
- Kill tests: `KILL_TEST.md`
- Experiment history: `experiments/ledger.csv`

## Confirmed findings

- The original large replication gap was primarily caused by an off-by-one
  decision clock and a missing VWAP gate; the corrected clean run is broadly
  consistent with the paper's headline return claims.
- Faithful execution is next-open. Same-close execution is useful only as a
  labelled diagnostic.
- Performance is regime dependent and 2025 was weak; aggregate Sharpe alone is
  insufficient evidence of a persistent edge.
- A pre-fix valid Null C analysis showed material P&L drift, but its numerical
  conclusion is superseded until rerun on the current faithful configuration.
- The former Null C implementation could shuffle its artificial zero-link
  sentinel away from index 0 and omit one real inter-bar link. The core and
  legacy study implementations now pin the opening atom and pass multi-seed
  invariant tests in `tests/test_nulls.py`.

## Provisional hypotheses

- Hypothesis: the faithful edge remains distinguishable from a session-valid
  Null C on clean data.
  - Kill test: the faithful strategy does not materially outperform the valid
    null distribution after using the same universe, clocks, costs, and metrics.
  - Evidence needed: registered post-fix Null C run and independent review.

## Invalidated or superseded findings

- The original local replication statistics are invalid as faithful-paper
  evidence because the decision clock and VWAP gate differed.
- Pre-fix Null C magnitude estimates are superseded for the current faithful
  configuration; preserve them as historical evidence, not the current verdict.

## Decisions and constraints

- Preserve existing import paths and reports during migration to the standard
  project structure.
- No historical period may be relabelled as sealed holdout after inspection.
- New strategy variants must use the audited engine and compare with the frozen
  faithful baseline.
- Routine ideas, hypotheses, experiment records, closeout, and hygiene checks use
  the shared `tools/research_admin.py` workflow.

## Known risks and open questions

- Complete a clean faithful-config Null C rerun using the corrected,
  invariant-tested implementation.
- Quantify robustness to neighbouring parameters, costs, and post-publication
  regimes without treating searched variants as confirmatory evidence.
- Define the forward shadow start date and immutable observation protocol.

## Next actions

1. Register and run the faithful-config Null C validation as `EXP-0007`.
2. Review its configuration, output, and interpretation independently.
3. Decide whether to enter a future-only shadow period or close the project.

## Promotion candidates

The clock and gate failures may become cross-project learnings after confirming
the same failure modes in another project. They remain project-specific here.
