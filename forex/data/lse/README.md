# London Strategic Edge data

Downloaded with `forex/download_lse_data.py`. The API key is read from the
workspace-root `.env` and is never written here.

## Contents

- `fx/`: 1-second OHLC bars for EUR/USD, GBP/USD, AUD/USD, and NZD/USD.
- `economics/`: all catalogued series for the United States, Euro Area, and
  Australia, plus the source series catalog.
- `economic_calendar/`: release events for US, Euro Area, and Australia,
  including actual, previous, consensus, forecast, revision flags, and UTC
  timestamps where supplied.
- `manifest.json`: SHA-256 hashes, schemas, row counts, coverage, and quality
  checks.

## Important FX coverage limitation

London Strategic Edge advertises FX history through 2026-07-31, but its bulk
export endpoint silently caps each request at exactly 2,500,000 rows. The four
current FX files therefore contain only the first returned segment beginning
in 2009. Their exact end timestamps are recorded in `manifest.json`; they are
not complete full-history files.

The continuation is handled by `forex/download_lse_fx_full.py`. It stores
additional immutable files as `fx_<PAIR>_1s_part_NNN.parquet`, removes the
overlapping boundary day locally, and records live progress in
`fx/full_history_state.json`. Runtime messages go to
`fx/full_history_download.log`; errors go to
`fx/full_history_download.error.log`. When all pairs reach the catalog's final
timestamp, it writes `fx/full_history_manifest.json`.

## Research caveats

- The economics series are downloaded values, not a point-in-time vintage
  archive. Do not assume historical observations reflect what was known on the
  original release date.
- The provider's Euro Area calendar begins in September 2025, while the US and
  Australian calendars begin in January 2015. Missing earlier Euro Area events
  are a source-coverage limitation.
- The 1-second FX feed is sparse/event-based rather than a guaranteed row for
  every wall-clock second. `manifest.json` reports timestamp gaps and ordering.
