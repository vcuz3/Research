# Shared AI Memory

This directory is the human-readable memory shared by Claude Code and Codex.
Markdown is the source of truth; no MCP database is currently used.

## Hierarchy

1. `RULES.md` — mandatory workspace-wide research and backtesting rules.
2. `RESEARCH_WORKFLOW.md` — the standard project layout and stage gates.
3. `LEARNINGS.md` — verified, reusable lessons spanning multiple projects.
4. `<project>/MEMORY.md` — current project status, decisions, and next steps.
5. Current prompt — task-specific instructions, which take precedence.

Existing nested `CLAUDE.md` files continue to serve as legacy project memory.
Migrate one when that project next receives substantial work: create its
`MEMORY.md` from `PROJECT_MEMORY_TEMPLATE.md`, move durable project context into
it, and leave the nested `CLAUDE.md` focused on Claude-specific commands or as a
small import wrapper.

## Maintenance rules

- Link findings to evidence rather than copying full reports.
- Replace or mark stale claims when conclusions change.
- Keep speculative notes in project memory, not shared learnings.
- Never store secrets or credentials here.

## Starting a project

Copy `templates/backtesting_project/` to the new project location, replace its
placeholders, and register the baseline before testing improvements. The CSV
schema is documented in `EXPERIMENT_LEDGER_SCHEMA.md`.
