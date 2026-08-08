# Holdout protocol for the single-pair workbench

`single_pair_zband_workbench.ipynb` uses Parquet predicate filtering so rows at
or after `HOLDOUT_START` do not enter pandas memory while `OPEN_HOLDOUT=False`.
The holdout switch also requires the exact phrase `FINAL CONFIGURATION IS FROZEN`.

Before opening it, freeze the pair, dates, strategy parameters, tuning grid,
selection metric, costs, and kill test. Save the training and OOS decision. Do
not open holdout after a failed OOS result, and do not retune after viewing it.

Project-history limitation: EXP-0001 already inspected 2024-01-01 through
2026-07-17 during an earlier misunderstood workflow. The guard now enforces the
user's intended procedure, but only future observations can be a scientifically
clean holdout for this project.
