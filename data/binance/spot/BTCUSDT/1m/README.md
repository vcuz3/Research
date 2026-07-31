# Binance Spot BTCUSDT 1-minute OHLCV

Official Binance Spot candles, stored as partitioned ZSTD Parquet. The requested
range starts at 2017-06-01 UTC, but `BTCUSDT` data begins at Binance's first
available candle on 2017-08-17 04:00 UTC.

## Files

- `parts/monthly/year=YYYY/YYYY-MM.parquet`: historical monthly partitions.
- `parts/daily/year=YYYY/month=MM/YYYY-MM-DD.parquet`: recent daily archive tail.
- `parts/rest_tail.parquet`: candles after the newest archive through the latest
  completed minute at download time.
- `archives/`: original Binance ZIPs and official SHA-256 checksum files.
- `manifest.json`: source, schema, and generation metadata.
- `quality_report.json`: coverage, gaps, duplicates, timestamp alignment, and
  OHLCV integrity checks.

`open_time` and `close_time` are Unix milliseconds in UTC. Binance's archive
switches to microsecond timestamps in 2025; the Parquet conversion normalizes
both eras to milliseconds without changing candle times.

Some early Binance candles are not aligned to exact UTC minute boundaries. They
are retained exactly as published and counted in `off_grid_timestamp_rows`.
Historical exchange outages/maintenance gaps are also retained rather than
filled with synthetic candles.

## Read with pandas

```python
from pathlib import Path
import pandas as pd

root = Path("data/binance/spot/BTCUSDT/1m/parts")
files = sorted(root.rglob("*.parquet"))
btc = pd.concat((pd.read_parquet(path) for path in files), ignore_index=True)
btc = btc.sort_values("open_time").drop_duplicates("open_time", keep="last")
btc["timestamp"] = pd.to_datetime(btc["open_time"], unit="ms", utc=True)
```

## Update

The command is resumable and re-verifies cached archive checksums:

```powershell
python tools/download_binance_klines.py --symbol BTCUSDT --interval 1m --start 2017-06-01
```
