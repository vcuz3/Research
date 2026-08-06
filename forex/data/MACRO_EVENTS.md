# FX macro-event source of truth

`macro/fx_macro_events.parquet` is the canonical, pair-expanded release table for
EURUSD, GBPUSD, AUDUSD, and NZDUSD. Build it with:

```powershell
python forex/build_macro_events.py
```

The primary calendar is ForexFactory, fetched with the public scraper at
<https://github.com/ehsanrs2/forexfactory-scraper>. LSE calendar records are
matched conservatively and retained in `lse_*` enrichment columns. LSE's economics
observation files are not included because they are not point-in-time vintages and
their observation dates are not verified publication timestamps.

## Join contract

- `ts_utc`: exact release timestamp, stored as timezone-naive UTC to match the
  `ts_utc` dtype in `data/clean/*_1m_clean.parquet`.
- `join_bar_ts_utc`: first available clean minute at or after the release, capped
  at 15 minutes. Join this to the matching pair file's `ts_utc`.
- `pair`: one of `EURUSD`, `GBPUSD`, `AUDUSD`, or `NZDUSD`.
- USD events appear once for every pair; base-currency events appear only for the
  corresponding pair.
- Several releases can occur in the same minute. Aggregate them deliberately
  before joining onto a unique minute-bar table, or join prices onto events for an
  event-study layout.

Raw strings are authoritative. Parsed numeric columns are convenience fields;
percentages remain in percentage points and K/M/B/T suffixes are converted to base
units. `surprise_value` is only populated when actual and forecast/consensus parse
to compatible units.

See `macro/manifest.json` for hashes, schemas, coverage, join rates, and known
limitations. Historical values are snapshots and are not vintage-verified; do not
claim a causal point-in-time macro feature without separately validating vintages.

The 2026-08-06 build contains 105,737 pair-event rows (50,391 unique source
events), with no duplicate canonical keys or out-of-order pair timestamps. 104,780
rows (99.09%) map to a clean bar within 15 minutes. Cross-provider validation found
that most matched LSE timestamps are exactly 60 minutes later than ForexFactory;
this is why `ts_utc` comes from ForexFactory even when LSE enrichment is present.
