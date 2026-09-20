# NQ Asia Session Range Expansion instructions

Before project work, read `PROJECT_GUIDE.md` and `MEMORY.md` in addition to the
workspace `ai_shared_memory/RULES.md`, `LEARNINGS.md`, and
`RESEARCH_WORKFLOW.md`.

- Preserve `baseline_replication/` as the paper-faithful reference.
- Keep execution, fills, costs, accounting, and metrics in `backtest_engine/`.
- Keep features, signals, filters, and sizing in `strategy/`.
- Register every material run in `experiments/ledger.csv` before execution when
  practical, and write outputs to `artifacts/runs/<experiment_id>/`.
- Update `MEMORY.md` when the durable verdict, evidence, risks, or next actions
  change. Promote only verified cross-project lessons to shared `LEARNINGS.md`.
- Record a builder and independent reviewer for material changes.
- Use `python <workspace>/tools/research_admin.py` for routine admin and run its
  `check` command before substantial handoff.

Project commands and data conventions are defined in `PROJECT_GUIDE.md`.
