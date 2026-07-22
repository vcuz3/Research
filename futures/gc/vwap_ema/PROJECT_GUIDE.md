# GC VWAP-EMA Paper Validation Project Guide

## Objective and scope

- Test the machine-executable rules in SSRN 6650958 against historical GC data,
  treating GC prices and traded volume as the requested XAU/USD proxy.
- Primary comparison period: calendar 2024. Full history is context only.
- Source: `ssrn-6650958.pdf` (26 April 2026 version).
- Shared data: `../data/GC_1m_clean.parquet` and `../data/GC_1s_rth.parquet`.

## Conventions

- Session: 09:30-16:00 America/New_York. The paper simultaneously says "New
  York open" and fixed 13:30-20:00 UTC; those diverge in winter. The NY-local
  interpretation is selected because it preserves the named market session and
  matches the available 1-second validation stream.
- Signals use completed 15-minute bars; entry is next-bar open.
- Risk is 1% of current equity per completed trade; cost is exactly 0.24R round
  trip. One position at a time.
- Intrabar stop/target ordering uses 1-second data when present and adverse 15m
  fallback otherwise. Gap-through stops fill at the first supported open.

## Commands

```powershell
python -m futures.gc.vwap_ema.scripts.data_quality
python -m unittest futures.gc.vwap_ema.tests.test_engine -v
python -m futures.gc.vwap_ema.scripts.run_baseline futures/gc/vwap_ema/artifacts/runs/EXP-0000
python tools/research_admin.py check --project futures/gc/vwap_ema
```

## Acceptance gates

- Paper claim tolerance: trade count +/-5%; rates/expectancy +/-0.05; Sharpe
  +/-0.25; return and drawdown +/-2 percentage points. Because the published
  values are synthetic Monte Carlo inputs/outcomes, historical mismatch is
  reported rather than tuned away.
- Kill test: Stage 1 is NO-GO if the 2024 historical core has gross expectancy
  <=0R or net expectancy <=0R at 0.24R cost, provided engine tests and Rule-9a
  data checks pass. A positive survivor requires later null/control validation.
- All observed history is consumed; any future GO would require shadow data.
