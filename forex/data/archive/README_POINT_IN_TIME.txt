Point-in-time note
==================

Use audusd_point_in_time_macro_factors.csv after running:

    $env:FRED_API_KEY = "your_key_here"
    python download_public_macro_factors.py

The older file audusd_public_macro_factors.csv was generated from latest-vintage
FRED and World Bank data and should not be used for no-lookahead backtests.

The current script refuses to run without FRED_API_KEY so it cannot silently
fall back to revised macro data.
