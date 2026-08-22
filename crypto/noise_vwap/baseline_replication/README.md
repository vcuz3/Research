# Baseline Replication

`bitcoin_noise_vwap.ipynb` is the self-contained BTCUSDT adaptation requested by
the user. It keeps every calculation inline and exposes the dates, ET anchor,
session length, weekend policy, lookback, data coverage floors, costs, and
notional in one parameter cell.

Execute all cells in a notebook UI, or reproduce from the workspace root with:

```powershell
python crypto/noise_vwap/backtest_engine/run_notebook.py
```

The frozen EXP-0001 result is documented in
`../reports/BASELINE_REPLICATION.md`. Do not tune the baseline notebook and then
call the same temporal OOS period a sealed holdout.
