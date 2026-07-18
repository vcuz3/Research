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
