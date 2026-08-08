# Project Memory: Shared FX data

## Scope

- Objective: maintain reusable clean price and macro-event data for FX research.
- Instruments or markets: EURUSD, GBPUSD, AUDUSD, NZDUSD.
- Data coverage: minute prices from 2011-07/2011-12 through 2026-07; 105,737 pair-event rows through 2026-07-17.
- Current phase: data engineering.

## Current status

- Verdict: provisional
- Last verified: 2026-08-06
- Lifecycle phase: data engineering
- Reproduction command: `python forex/build_macro_events.py`
- Primary evidence: `data/macro/manifest.json`, `data/MACRO_EVENTS.md`, `build_macro_events.py`
- NZDUSD gap repair: inventory and resumable repair tooling completed at
  `repair_fx_ibkr_gaps.py` / `data/repair/ibkr_nzdusd/README.md`; fetching is
  waiting for a running read-only IBKR Gateway/TWS API session.

## Confirmed findings

- The four clean price files have unique, monotonically increasing, timezone-naive UTC minute timestamps.
- LSE calendar coverage is incomplete for this use: no GBP/NZD, USD/AUD begin in 2015, and EUR begins in 2025-09.
- The referenced ForexFactory scraper labels displayed page times with the supplied timezone; for the 2026-08-06 pull the page was rendered in Australia/Sydney. A 2025 NFP probe parsed correctly only with that display timezone.
- The canonical output has 50,391 unique provider events expanded to 105,737 pair-event rows, zero duplicate IDs/keys, zero out-of-order pair timestamps, and 104,780 rows (99.09%) mapped to a clean price bar within 15 minutes.
- Conservative matching links 8,499 unique LSE/ForexFactory events. Of 7,622 comparable actual values, 6,974 (91.50%) agree exactly; 7,252 matched LSE timestamps are exactly 60 minutes later than ForexFactory, supporting the decision not to use LSE timestamps as canonical.

## Decisions and constraints

- ForexFactory is the primary release calendar; conservatively matched LSE rows are enrichment/provenance, not duplicate canonical releases.
- LSE economics observation series are excluded from the event table because they are not point-in-time vintages and do not provide verified release timestamps.
- Canonical event timestamps are stored as timezone-naive UTC to match `data/clean`; `join_bar_ts_utc` is capped at the first clean bar within 15 minutes.
- Raw macro values remain authoritative. Numeric parsing is convenience-only.

## Known risks and open questions

- Historical actual, forecast, and previous values are snapshots and have not been vintage-verified.
- ForexFactory page display timezone must be revalidated if the fetch location or session changes.
- Conservative fuzzy matching leaves some LSE rows unmatched by design; exact counts live in the manifest.
- The archived NZDUSD IBKR data has 2,944 fixed 15-minute acquisition holes at
  13:00–15:14 ET (44,160 minutes). Archived raw/clean timestamp parity is exact,
  confirming the defect is upstream of cleaning. The canonical Parquet remains
  unchanged until the full repair passes and is promoted.

## Next actions

1. Treat macro studies as exploratory until forecast/actual vintages and publication latency are independently verified.
2. Re-run the builder and inspect the manifest whenever either raw calendar changes.
3. Start IBKR Gateway/TWS with read-only API enabled, run the resumable NZDUSD
   repair fetch, then build/promote and rerun all FX data-quality reports.

## Promotion candidates

- None.
