# Research workspace instructions

Before research, backtesting, implementation, review, or reporting work, read:

- `ai_shared_memory/RULES.md`
- `ai_shared_memory/LEARNINGS.md`
- `ai_shared_memory/RESEARCH_WORKFLOW.md`

Treat `RULES.md` as mandatory across the workspace.

## Project memory

Determine the project containing the files in scope. Read the closest
`MEMORY.md` between those files and this workspace root. If the project has no
`MEMORY.md` but has a nested `CLAUDE.md`, read that file as legacy project
memory. Do not treat the root `CLAUDE.md` as project-specific memory.

When durable project knowledge changes:

- Update the project's `MEMORY.md`, creating it from
  `ai_shared_memory/PROJECT_MEMORY_TEMPLATE.md` if needed.
- Include evidence paths and distinguish confirmed, provisional, invalidated,
  and superseded findings.
- Promote a finding to `ai_shared_memory/LEARNINGS.md` only when it is verified
  and reusable across projects.
- Correct or mark stale claims instead of silently appending contradictions.

Never store credentials, private keys, tokens, account details, or raw secrets
in instruction or memory files.

Nested `AGENTS.md` files may add project-specific commands and conventions.
Explicit user instructions take precedence over memory.

## New backtesting projects

Start new projects from `templates/backtesting_project/`. Keep paper-faithful
baseline replication separate from the reusable backtest engine and from later
strategy experiments. Record every material run in the project's
`experiments/ledger.csv`; do not put execution or fill logic in ad hoc
experiment scripts.

Use `python tools/research_admin.py` for routine project, idea, hypothesis,
experiment, closeout, and hygiene operations. Do not hand-edit generated IDs or
create competing admin formats when the tool supports the operation.
