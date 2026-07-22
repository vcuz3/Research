"""Paper-specified 2024 US macro entry exclusions.

NFP, CPI, and GDP releases are normally at 08:30 ET, outside the selected
09:30-16:00 ET session and therefore cannot block an entry. FOMC statements are
at 14:00 ET and can. Dates below are the eight scheduled 2024 decisions. The
paper's discretionary swing-stop override for already-open positions has no
machine-testable definition and is not invented here.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FOMC_2024 = {
    "2024-01-31", "2024-03-20", "2024-05-01", "2024-06-12",
    "2024-07-31", "2024-09-18", "2024-11-07", "2024-12-18",
}


def add_2024_news_exclusion(bars: pd.DataFrame) -> pd.DataFrame:
    """Block entries whose next-bar open is within +/-15m of 14:00 ET FOMC."""
    out = bars.copy()
    dates = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    # A 15m bar timestamp is its open. The inclusive window is 13:45..14:15.
    event_day = dates.isin(FOMC_2024).to_numpy()
    out["entry_blocked"] = event_day & np.isin(out["tod"].to_numpy(), [825, 840, 855])
    return out
