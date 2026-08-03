# FX futures VWAP exploration (6E/6B) instructions

Before project work, read `PROJECT_GUIDE.md` and `MEMORY.md` in addition to the
workspace `ai_shared_memory/RULES.md`, `LEARNINGS.md`, and
`RESEARCH_WORKFLOW.md`.

- `paper/`, `baseline_replication/` and `backtest_engine/` are **not applicable**
  here and say so in their own READMEs: there is no source paper and no barrier
  strategy, so every result is an entry-information measurement (rule 15). If a
  barrier strategy is ever added, build a real engine with an explicit rule-3
  intrabar policy BEFORE running it.
- Measurement primitives live in `core/` (`data`, `vwap`, `frame`, `stats`,
  `fix`); `tests/test_core.py` must pass 15/15 before any run is registered.
- Register every material run in `experiments/ledger.csv` before execution when
  practical, and write outputs to `artifacts/runs/<experiment_id>/`.
- Update `MEMORY.md` when the durable verdict, evidence, risks, or next actions
  change. Promote only verified cross-project lessons to shared `LEARNINGS.md`.
- Record a builder and independent reviewer for material changes.
- Use `python <workspace>/tools/research_admin.py` for routine admin and run its
  `check` command before substantial handoff.

Project commands and data conventions are defined in `PROJECT_GUIDE.md`.

Standing cautions for this project, each earned by a result here:

1. Always run the **no-anchor** control (`past30`). It beat every session anchor
   on both products; a new anchor variant must clear it, not just clear zero.
2. Never enter at `close(m)` — the shared-print artifact is worth 68-88% of the
   measured reversal on this data.
3. Never session-average a per-signal effect; it produced t≈+15 from a null.
4. Check any event window against the **published institutional window**. The
   whole London-fix result was a 30-second overlap with the WM benchmark window.
5. Costs come from `core.data.tick_size(product, year)` — 6E's tick halved in
   2016, so a cost quoted in ticks across the sample is wrong by 2x.
6. The 2024/2025/2026 holdout is sealed. `load_bars` defaults to
   `scope="explore"`; do not pass `scope="holdout"` without a reason worth
   spending it on.
