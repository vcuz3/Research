# Trend-following closed form as an instrument pre-screen instructions

Before project work, read `PROJECT_GUIDE.md` and `MEMORY.md` in addition to the
workspace `ai_shared_memory/RULES.md`, `LEARNINGS.md`, and
`RESEARCH_WORKFLOW.md`.

**Layout deviation from the template, deliberate.** There is no source paper, so
`paper/PAPER_SPEC.md` and `baseline_replication/` are not applicable (see
`reports/BASELINE_REPLICATION.md`), and `backtest_engine/` and `strategy/` are
unused. All tested code lives in `core/`: `panel.py` (loading, clocks, rolls,
measured price increments), `filters.py` (kernels), `closedform.py` (the
predicted side), `engine.py` (execution and accounting, audited in
`reports/ENGINE_AUDIT.md`), `stats.py` (rank statistics and nulls).

- Run `tests/test_core.py` (30 checks) before registering any run. The identity
  check inside `scripts/s1_screen.py` additionally halts the run in code if
  predicted and realised P&L disagree by more than 1e-9 at the same lag.
- Rebuild the derived panel with `scripts/build_panel.py` if the archive changes;
  it regenerates `data/` and `reports/DATA_QUALITY.txt` together.
- Register every material run in `experiments/ledger.csv` before execution when
  practical, and write outputs to `artifacts/runs/<experiment_id>/`.
- Update `MEMORY.md` when the durable verdict, evidence, risks, or next actions
  change. Promote only verified cross-project lessons to shared `LEARNINGS.md`.
- Record a builder and independent reviewer for material changes.
- Use `python <workspace>/tools/research_admin.py` for routine admin and run its
  `check` command before substantial handoff.

Project commands and data conventions are defined in `PROJECT_GUIDE.md`.
