# Research Administration Tool

`research_admin.py` standardizes routine record keeping for both Claude Code and
Codex. It uses only the Python standard library.

```powershell
python tools/research_admin.py --help
python tools/research_admin.py init-project --target futures/nq/new_project --name "New Project"
python tools/research_admin.py new-idea --project futures/nq/new_project --title "Idea title"
python tools/research_admin.py new-hypothesis --project futures/nq/new_project --title "Testable claim"
python tools/research_admin.py new-experiment --project futures/nq/new_project --hypothesis-id HYP-0001 --phase experiment --config-path experiments/configs/EXP-0001.json --run-command "python -m package.run" --builder codex
python tools/research_admin.py close-experiment --project futures/nq/new_project --experiment-id EXP-0001 --status completed --result "Rejected"
python tools/research_admin.py check --project futures/nq/new_project
```

The tool allocates stable IDs, creates standard discussion/review records,
updates CSV safely, and checks required structure. It intentionally does not run
backtests or decide whether evidence is valid.

## `preflight_kill_battery.py`

Cheap, one-line rejection tests for an edge candidate — run BEFORE spending the
engine + null stack. Each test encodes a trap already paid for in
`ai_shared_memory/LEARNINGS.md`: threshold-as-time-of-day selector, endogenous
signal count, shared-close reversion, paired-embargo survival, algebraic
identity, target rank-persistence, effective breadth, and win-rate-vs-break-even.
A PASS is not evidence of edge — it only means the cheap trap did not fire.

```powershell
python tools/preflight_kill_battery.py --self-test   # assert each test fires
python tools/preflight_kill_battery.py --demo        # fabricated data walkthrough
```

Import `run_battery(...)` (or the individual functions) from a project and feed
whichever inputs you have; missing inputs SKIP. Pairs with
`ai_shared_memory/EDGE_DENSITY_MAP.md`, which ranks *where* to point it.
