# Experiments

`ledger.csv` is the append-only audit trail. Its initial rows reconstruct major
legacy milestones from existing reports and were not predeclared. All new rows
must follow `../../../../ai_shared_memory/EXPERIMENT_LEDGER_SCHEMA.md`.

For a new material run:

1. Add a unique row with status `planned`, a falsifiable hypothesis, primary
   metric, kill test, frozen config path, data scope, and intended command.
2. Store outputs under `../artifacts/runs/<experiment_id>/`.
3. Update the same row with the result and evidence; never delete losing runs.
4. Have the other model or a human review the config, diff, command, artifacts,
   and interpretation. Record the reviewer and status.
5. Update `../MEMORY.md` only if the durable verdict or next actions changed.

Long-form hypotheses or reviews may be stored as Markdown beside the ledger and
linked from `notes` or `artifact_path`.

Use `IDEA_BACKLOG.md` for uncommitted brainstorming and
`hypotheses/HYP-XXXX.md` for promoted, falsifiable proposals. Discuss each run in
`../artifacts/runs/EXP-XXXX/review.md`, then synthesize reviewed results in the
existing `../REVIEW.md`. Use the workspace `tools/research_admin.py` commands for
routine administration.
