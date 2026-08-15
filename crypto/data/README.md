# Bitcoin kline data

`download_binance_btcusdt_1m.py` downloads official Binance Spot `BTCUSDT`
1-minute kline archives from 17 August 2017 through the last complete UTC day.
`download_binance_btcusdt_1s.py` downloads 1-second archives from 1 January
2020 through the last complete UTC day.
It requires Python and `pyarrow`:

```powershell
python -m pip install -r crypto/data/requirements.txt
```

Run from the workspace root:

```powershell
python crypto/data/download_binance_btcusdt_1m.py
```

For 1-second data:

```powershell
python crypto/data/download_binance_btcusdt_1s.py
```

This is equivalent to:

```powershell
python crypto/data/download_binance_btcusdt_1m.py --interval 1s --start 2020-01-01
```

To test a small date range first:

```powershell
python crypto/data/download_binance_btcusdt_1m.py --start 2017-08-17 --end 2017-08-18 --output-dir crypto/data/test_download
```

The default output directory is `crypto/data/binance_spot_btcusdt_1m/` and
contains:

- `raw/`: original ZIP archives and official `.CHECKSUM` files;
- `BTCUSDT-1m-<start>-to-<end>.parquet`: typed, Zstandard-compressed Parquet;
  timestamps are normalized to `timestamp[ms, tz=UTC]`, prices and volumes are
  `float64`, and trade counts are `int64`;
- `BTCUSDT-1m-data-quality.json`: requested-range coverage (including leading
  and trailing unavailable minutes), internal gaps, duplicates, invalid rows,
  per-year and per-UTC-hour counts, and the output SHA-256;
- `manifest.json`: exact source archives used.

The downloader is resumable: rerunning it verifies and reuses cached archives.
Missing bars are reported and never filled. `--end` is inclusive and only
complete UTC days are accepted. Use `--download-only` to retain verified raw
archives without building the combined file.

The 1-second output is stored separately under
`crypto/data/binance_spot_btcusdt_1s/`. Expect roughly 210 million calendar
seconds from 2020 through mid-2026, so allow substantial download time and disk
space. The script streams 100,000 rows at a time rather than holding the whole
dataset in memory.

Example read:

```python
import pyarrow.parquet as pq

bars = pq.read_table("crypto/data/binance_spot_btcusdt_1m/BTCUSDT-1m-2017-08-17-to-2026-08-12.parquet")
```

Source documentation: Binance's official
[`binance-public-data`](https://github.com/binance/binance-public-data)
repository.
