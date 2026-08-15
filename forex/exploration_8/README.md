# AUD triangular pricing exploration

Open `triangular_arbitrage_workbench.ipynb` to explore causal dislocations among
AUDUSD, AUDJPY, and USDJPY. The first configuration cell lets you choose the bar
timeframe, Z-score lookback, and entry threshold.

`audusd_pine_triangular_strategy.ipynb` is a separate stateful translation of the
user-supplied EURUSD Pine v6 strategy, adapted to AUDUSD/AUDJPY/USDJPY. It keeps
the Pine Z-reversion exits and ATR stop/target behavior.

The workbench uses local midpoint data and is explicitly a relative-value study,
not proof of executable triangular arbitrage. Build and verify it with:

```powershell
python _build_notebook.py
python _build_pine_translation_notebook.py
python -m pytest test_triangle.py -q
python -m pytest test_pine_translation.py -q
```
