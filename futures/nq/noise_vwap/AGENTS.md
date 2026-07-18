# Noise VWAP project instructions

Before working in this project, read `PROJECT_GUIDE.md` and `MEMORY.md` in
addition to the workspace-wide rules, learnings, and research workflow.

This is a legacy project with stable import paths. Do not move `core/`,
`scripts/`, existing reports, data, or outputs merely to match the new template.
The project folders added around them are authoritative indexes and boundaries.

## Required practice

- Preserve the paper-faithful baseline as a separate reference configuration.
- Use `core.engine` for the faithful engine and treat `signal_close` as an
  explicitly labelled ablation only.
- Require `core.engine2` changes to retain parity with `core.engine` under the
  faithful configuration.
- Do not implement fills, costs, P&L, sizing, or performance metrics in new ad
  hoc experiment scripts. Extend the audited engine with tests when necessary.
- Register every material run in `experiments/ledger.csv` and store new run
  outputs under a unique `artifacts/runs/<experiment_id>/` directory.
- Update `MEMORY.md` when the verdict, evidence, risks, or next actions change.
- For material work, record one builder and a separate reviewer in the ledger.
- Use the workspace `tools/research_admin.py` for new ideas, hypotheses,
  experiments, closeout, and hygiene checks.

Run the validation commands in `PROJECT_GUIDE.md` before accepting engine or
strategy changes. Explicit user instructions take precedence.
