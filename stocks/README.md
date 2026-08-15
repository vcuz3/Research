# Nasdaq-100 historical 1-minute stock archive

This folder targets every security that was a Nasdaq-100 constituent at any
time from 2016-08-11 through 2026-08-11. Prices are requested from the London
Strategic Edge (LSE) vault API at one-minute resolution.

The point-in-time universe is reconstructed from a current constituent snapshot
and the complete component-change table. It includes additions, deletions,
acquired/delisted names, temporary constituents, share classes, and ticker
changes recorded by the source. The exact source tables and an LSE catalog
snapshot are retained under `universe/`.

The safety gate intentionally refuses to start a normal download if LSE lacks a
required historical ticker or its catalog coverage begins after that ticker's
membership began. This prevents an incomplete archive from being mistaken for
a survivorship-bias-free dataset.

Commands (run from `Research`):

```powershell
python stocks/download_nasdaq100_1m.py prepare
python stocks/download_nasdaq100_1m.py download
python stocks/download_nasdaq100_1m.py verify
python stocks/download_nasdaq100_1m.py status
```

LSE allows five exports per hour on the current account. State is saved after
every file and downloads resume safely. Data files are written to `stocks/stocks/`.
`--allow-provider-gaps` exists only for fetching a knowingly incomplete subset;
such an archive is not suitable for a survivorship-free backtest.
