# Validation

Run every notebook code cell on the shortened sealed-holdout fixture:

```powershell
python forex/trade_regime_tester/_smoke_run_notebook.py
python forex/trade_regime_tester/_smoke_run_notebook.py --full
```

The smoke mode uses 2019 as training and 2021 as test, reduces expensive
statistical strides and permutation count, and leaves 2024+ physically excluded
from parquet reads. It validates execution and leakage guards, not a tradeable
regime claim.

The `--full` variant uses the notebook defaults and the full 500-shift null.
EXP-0003 completed it in 21.3 seconds on 4,085 trades and 306,471 market bars;
the holdout remained sealed.
