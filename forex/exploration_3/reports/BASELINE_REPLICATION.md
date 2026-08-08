# Baseline replication

The clarified strategy contract is implemented in `strategy/twap_zband.py` and
`backtest_engine/engine.py`. Exact TradingView performance parity is not claimed:
the source did not identify a symbol, chart timeframe, exchange timezone, or
broker-emulator settings, and the user superseded several pasted defaults.

The local baseline uses four FX pairs, 15-minute completed signals, a 17:00
America/New_York session with IANA DST, next-open entries, and one-minute exit
replay. Deterministic behavioral parity for this frozen interpretation is covered
by the engine audit.
