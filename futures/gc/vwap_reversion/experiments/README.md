# Experiments

The append-only `ledger.csv` follows
`../../../ai_shared_memory/EXPERIMENT_LEDGER_SCHEMA.md`.

Before a material run, register its hypothesis, kill test, frozen config, data
scope, code reference, command, and primary metric. After it finishes, update the
same row with its result, immutable artifact path, builder, reviewer, and review
status. Preserve failed, losing, abandoned, and superseded runs.

Workflow:

1. Capture brainstorming in `IDEA_BACKLOG.md`.
2. Promote a viable idea to `hypotheses/HYP-XXXX.md` and complete its mechanism,
   exact change, metric, kill test, controls, and data scope.
3. Register an `EXP-XXXX` row and corresponding immutable run directory.
4. Record the result discussion and independent review in the run's `review.md`.
5. Synthesize reviewed evidence in `../reports/FINDINGS.md`.

Use the workspace `tools/research_admin.py` commands to allocate IDs, create
files, update the ledger, and check hygiene.
