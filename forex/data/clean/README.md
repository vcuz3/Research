# Canonical clean FX minute data

The four `*_1m_clean.parquet` files contain spot-FX midpoint OHLC joined to
exchange-traded futures volume at the exact UTC minute.

## Schema

- `ts_utc`: timezone-naive UTC minute (`datetime64[us]`).
- `open`, `high`, `low`, `close`: spot-FX midpoint prices from the existing
  canonical IBKR/LSE-hybrid price files.
- `volume`: nullable `UInt64` contract volume from Databento `GLBX.MDP3`, schema
  `ohlcv-1m`, using the volume-ranked continuous contract.

Mappings are EURUSD→6E, GBPUSD→6B, AUDUSD→6A, and NZDUSD→6N.

The join is an exact timestamp left join. A null volume means there was no
matching Databento futures bar. It is deliberately not filled with zero or
carried from another minute because missing/degraded feed periods cannot be
distinguished safely from a no-trade minute in this derived dataset.

## Reproduction and evidence

1. Build price-only files from the IBKR CSV sources with
   `python -m forex.noise_vwap.core.build_clean` when required.
2. Join futures volume and archive the price-only files with
   `python forex/build_clean_futures_volume.py`.

`futures_volume_manifest.json` records source and output hashes, coverage by
year and UTC hour, gaps, roll boundaries, and unmatched-minute counts. The
pre-volume files from the current build are retained under `../archive/` with
the suffix `pre_futures_volume_20260809T101545Z`.
