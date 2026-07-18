# Research workspace instructions

@ai_shared_memory/RULES.md
@ai_shared_memory/LEARNINGS.md
@ai_shared_memory/RESEARCH_WORKFLOW.md

The imported files are the shared, workspace-wide source of truth for research
rules and durable cross-project learnings.

For work inside a specific project, also read the closest `MEMORY.md` between
that project and this workspace root. Existing nested `CLAUDE.md` files are
legacy project memory and remain authoritative for their projects until they
are migrated to `MEMORY.md`.

Before finishing substantial research work:

1. Put project status, decisions, evidence paths, and project-only findings in
   that project's `MEMORY.md`.
2. Put a finding in `ai_shared_memory/LEARNINGS.md` only when it is verified,
   durable, and useful across projects.
3. Update or clearly mark invalidated and superseded findings; do not leave a
   stale edge claim looking current.
4. Never store credentials, private keys, tokens, account details, or raw
   secrets in instruction or memory files.

Create new backtesting projects from `templates/backtesting_project/`. Keep
paper-faithful baseline replication, reusable engine code, strategy logic, and
experiments separate. Register every material run in `experiments/ledger.csv`.
Use `python tools/research_admin.py` for routine project, idea, hypothesis,
experiment, closeout, and hygiene operations.
