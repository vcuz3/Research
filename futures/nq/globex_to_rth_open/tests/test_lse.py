from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from strategy.lse import build_lse_sma_candidates


def _row(ts_et: pd.Timestamp, price: float) -> dict:
    return {
        "ts_utc": ts_et.tz_convert("UTC"), "symbol": "NQ.F", "open": price,
        "high": price + 1, "low": price - 1, "close": price + 0.5,
        "volume": 1.0, "is_roll": False,
        "local_date": ts_et.tz_localize(None).normalize(),
        "local_minute": ts_et.hour * 60 + ts_et.minute,
    }


def test_sma200_uses_only_completed_rth_dates_before_entry():
    sessions = pd.bdate_range("2020-01-02", periods=200)
    rows = []
    for i, day in enumerate(sessions):
        local_day = day.tz_localize("America/New_York")
        rows.append(_row(local_day + pd.Timedelta(hours=9, minutes=30), 100 + i))
        rows.append(_row(local_day + pd.Timedelta(hours=15, minutes=59), 100 + i))
    entry_date = sessions[-1]
    entry = entry_date.tz_localize("America/New_York") + pd.Timedelta(hours=18)
    exit_bar = (entry_date + pd.Timedelta(days=1)).tz_localize(
        "America/New_York") + pd.Timedelta(hours=9, minutes=30)
    rows += [_row(entry, 400.0), _row(exit_bar, 405.0)]
    frame = pd.DataFrame(rows).sort_values("ts_utc").reset_index(drop=True)
    candidates, _, quality = build_lse_sma_candidates(frame, sma_days=200)
    assert len(candidates) == 1
    assert candidates.loc[0, "feature_date"] == entry_date
    assert candidates.loc[0, "sma_available"]
    assert candidates.loc[0, "sma_gate_entry"]
    assert quality["sma_warmup_unavailable"] == 0

