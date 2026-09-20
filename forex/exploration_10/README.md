# Low-volatility false-breakout reversion

Configurable backtest for fading 10-candle range breakouts when Wilder ATR is
below its trailing percentile. The baseline covers EURUSD, GBPUSD, AUDUSD, and
NZDUSD with 30-minute signals and 1-minute execution replay.

```powershell
python -m pytest -q
python run_backtest.py --config baseline_replication/configs/baseline.json --output artifacts/runs/EXP-0001
```

The requested parameters can be overridden directly:

```powershell
python run_backtest.py --timeframe 60min --atr-period 20 --atr-percentile 0.10 --stop-atr 2.0 --target-atr 2.5 --output artifacts/runs/<new-experiment-id>
```

Register a new experiment before running an alternative configuration. Current
results and limitations are in `reports/FINDINGS.md`.

The registered walk-forward optimisation is reproduced with:

```powershell
python run_walk_forward.py --config experiments/configs/walk_forward_grid.json --output artifacts/runs/EXP-0002
```

The interval beginning 2024-07-18 UTC is reserved and must not be tested yet.
