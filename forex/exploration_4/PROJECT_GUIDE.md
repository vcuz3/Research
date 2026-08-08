# exploration_4 — Project Guide

This project implements the frozen USD-major standardized-displacement baseline
specified in `PROJECT_PLAN.md`. It is a baseline measurement, not a parameter
search. The implementation imports the audited execution, bracket, cost, and
calendar components from `forex/exploration_1/`.

## Reproduction

```powershell
python -u forex/exploration_4/_run_baseline.py
jupyter nbconvert --to notebook --execute forex/exploration_4/notebooks/trade_visualizations.ipynb --output trade_visualizations.executed.ipynb --output-dir forex/exploration_4/notebooks
python tools/research_admin.py check --project forex/exploration_4
```

The material run writes immutable evidence to `artifacts/runs/EXP-0001/` and
current summaries to `reports/`.
