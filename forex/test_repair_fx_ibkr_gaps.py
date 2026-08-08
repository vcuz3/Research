"""Synthetic invariants for repair_fx_ibkr_gaps.py."""

from __future__ import annotations

import pandas as pd

from repair_fx_ibkr_gaps import detect_target_holes, normalize_ibkr_bars, request_plan


def synthetic_minutes(date: str, hour: int, include_prefix: bool) -> pd.DatetimeIndex:
    local = pd.Timestamp(f"{date} {hour:02d}:00", tz="America/New_York")
    start = 0 if include_prefix else 15
    return pd.date_range(local + pd.Timedelta(minutes=start),
                         local + pd.Timedelta(minutes=59), freq="min").tz_convert("UTC")


def test_detects_only_complete_fifteen_minute_prefix_hole():
    ts = synthetic_minutes("2020-01-06", 13, False).append(
        synthetic_minutes("2020-01-07", 13, True))
    holes = detect_target_holes(pd.Series(ts))
    assert len(holes) == 1
    assert holes.iloc[0].et_hour == 13
    assert holes.iloc[0].pre15 == 0
    assert holes.iloc[0].post15 == 45
    assert len(holes.iloc[0].expected_utc) == 15


def test_does_not_target_rollover_or_sparse_holiday():
    rollover = synthetic_minutes("2020-01-05", 17, False)
    sparse = synthetic_minutes("2020-01-06", 14, False)[:20]
    holes = detect_target_holes(pd.Series(rollover.append(sparse)))
    assert holes.empty


def test_request_plan_pairs_consecutive_dates_only():
    ts = synthetic_minutes("2020-01-06", 13, False)
    ts = ts.append(synthetic_minutes("2020-01-07", 14, False))
    ts = ts.append(synthetic_minutes("2020-01-09", 15, False))
    holes = detect_target_holes(pd.Series(ts))
    plan = request_plan(holes)
    assert len(plan) == 2
    assert plan[0]["duration"] == "2 D"
    assert plan[1]["duration"] == "1 D"


def test_empty_ibkr_response_has_typed_timestamp_column():
    frame = normalize_ibkr_bars([], None)
    assert frame.empty
    assert str(frame.ts_utc.dtype) == "datetime64[ns, UTC]"
