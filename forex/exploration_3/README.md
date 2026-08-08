# Anchored TWAP/SMA Z-band ATR strategy

Use `single_pair_zband_workbench.ipynb` for the editable research workflow. Its
first control cell selects one pair, train/OOS dates, manual parameters, tuning
grids, percentage-of-equity risk, optional leverage cap, costs, and the trade to
visualize. Units are recalculated from equity and ATR-stop distance on every
entry. It does not load 2024+ data by default and requires an explicit
confirmation before opening the holdout.

Use `single_pair_rsi_crossover_workbench.ipynb` for the RSI arm/reset workflow.
The default short setup arms on an RSI cross above 0.70 and enters on a later
cross down through 0.65; the long setup mirrors it at 0.30/0.35. The control
cell exposes RSI length and thresholds, arm expiry, ATR length and stop
multiplier, take-profit R multiple, dates, pair, timeframe, equity risk, costs,
and an optional train-only grid. It shares the same sealed-holdout and
one-minute bracket-replay conventions as the Z-band workbench.

`anchored_twap_sma_zband_atr.ipynb` preserves the earlier four-pair material run;
that specific run was a NO-GO at a 1-pip round-trip cost.

```powershell
python -m pytest backtest_engine/test_engine.py -q
python run_research.py --output-dir artifacts/runs/EXP-0001
python _build_notebook.py
python _smoke_run_notebook.py
python _build_single_pair_notebook.py
python _smoke_run_single_pair_notebook.py
python _build_rsi_crossover_notebook.py
python _smoke_run_rsi_crossover_notebook.py
```

The data lives in `../data/clean/`; immutable material outputs live under
`artifacts/runs/EXP-0001/`.
