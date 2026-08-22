# Bitcoin Noise-Area + VWAP

This project transparently adapts the audited NQ Noise-Area + VWAP strategy to
Binance Spot BTCUSDT one-minute data. Start with
`baseline_replication/bitcoin_noise_vwap.ipynb`; its first parameter cell controls
the data start, in-sample and OOS ranges, ET anchor, session length, weekend
policy, band history, and costs.

The default 09:30 ET anchor and 390-minute weekday session preserve the source
strategy's U.S. cash-session decision universe. Results are research diagnostics,
not deployment evidence for a short-capable Bitcoin venue.
