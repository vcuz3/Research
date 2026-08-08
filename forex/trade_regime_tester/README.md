# Reusable Trade Regime Tester

The main artifact is [trade_regime_tester.ipynb](trade_regime_tester.ipynb), a
strategy-agnostic notebook for attributing a frozen strategy's completed trades
to causal market regimes.

Only the trades table is strategy-specific. By default the notebook reads the
frozen `AUDUSD / sma_80` artifact from `forex/exploration_3`; change the path,
column mapping, frozen filters, instrument, timeframe, and split dates in its
single configuration cell. Reusable adapters load clean OHLC, point-in-time
macro factors, a benchmark market, cross-asset levels, and an optional event
calendar.

The example records the frozen strategy provenance explicitly: SMA 80, 2.5
standard-deviation arming, 2.0 ATR stop multiplier, and 1% equity risk per trade.
The regime notebook does not retune or regenerate those trades.

Implemented regime families include:

- macro growth, inflation, rates, external balance, and cross-asset risk;
- volatility acceleration (VEI, short/long RV, ATR ratio, GARCH) and level;
- strategy-timeframe and completed higher-timeframe trend;
- ADX and Kaufman Efficiency Ratio;
- ADF stationarity, Hurst, skewness, kurtosis, autocorrelation, and variance ratio;
- rolling covariance, correlation, beta, downside dependence, and relative momentum;
- jump/tail asymmetry, bar quality, gaps, calendar/session, event proximity, and
  causal completed-trade strategy state;
- train-fitted composite clusters, persistence/transitions, and predeclared
  pairwise interactions.

All continuous cut points, GARCH parameters, imputation/scaling, and clusters
are fitted on training data only. Test uses the frozen definitions. Parquet
predicate reads exclude the 2024+ holdout unless the notebook's explicit
confirmation phrase is entered.

## Input contract

Required after column mapping: a decision timestamp and a realised net outcome.
Direction plus entry/exit timestamps are recommended. Existing causal regime
columns can be listed in `PRECOMPUTED_FEATURE_COLUMNS`.

## Rebuild and validate

```powershell
python forex/trade_regime_tester/_build_notebook.py
python forex/trade_regime_tester/_smoke_run_notebook.py
python forex/trade_regime_tester/_smoke_run_notebook.py --full
python tools/research_admin.py check --project forex/trade_regime_tester
```

The smoke runner uses a shortened 2019 training / 2021 test sample and never
loads the 2024+ holdout. The notebook itself defaults to pre-2020 training,
2021-2023 testing, a 2020 embargo, and a sealed 2024+ holdout.
