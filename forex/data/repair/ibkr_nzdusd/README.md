# NZDUSD IBKR gap repair workspace

Status: inventory complete; fetch waiting for a running IBKR Gateway/TWS API
session at the configured endpoint.

The canonical `forex/data/clean/NZDUSD_1m_clean.parquet` has **not** been changed.
The generated inventory proves exact timestamp parity between the archived raw
IBKR CSV and the clean Parquet, so the cleaner did not create the holes.

## Frozen repair scope

- 2,944 acquisition-hole windows at 13:00–13:14, 14:00–14:14, or
  15:00–15:14 America/New_York.
- 44,160 target minutes across 2011-12-07 through 2026-07-16.
- 1,507 resumable one-/two-day IBKR MIDPOINT requests; a missing target gets a
  four-hour fallback request with the hole away from the response boundary.
- The 17:00 ET rollover/reopen is excluded from this repair.

## Commands

```powershell
python forex/repair_fx_ibkr_gaps.py inventory
.venv\Scripts\python.exe forex/repair_fx_ibkr_gaps.py fetch
python forex/repair_fx_ibkr_gaps.py build
python forex/repair_fx_ibkr_gaps.py promote
```

`fetch` is resumable and checkpoints every request under `requests/`. `build`
refuses to run until every target minute exists. `promote` verifies hashes,
archives the original canonical Parquet, and only then performs an atomic
replacement.
