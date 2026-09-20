# NQ Globex to RTH Open

This project tests a long NQ position opened at 18:00 New York time and closed
at the 09:30 stock-market open. It includes an x-day moving-average gate, a
prior-close VIX range sweep, and equal, inverse-ATR14, inverse-VIX, and
inverse-prior-day-ATR sizing.

Run:

```powershell
python futures\nq\globex_to_rth_open\scripts\run_study.py
```

The frozen definitions are in `paper/PAPER_SPEC.md`. Results are written to the
registered run directory as a summary CSV, candidate-trade parquet, data-quality
JSON, minute-of-day coverage CSV, and fingerprinted manifest.

