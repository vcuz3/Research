"""Synthetic invariants for the hybrid NZDUSD reconstruction."""

from __future__ import annotations

import pandas as pd

from forex.repair_nzdusd_lse_gaps import BAR_COLUMNS, reconstruct_window


def fixture_frames():
    index = pd.date_range("2022-01-03T17:30:00Z", periods=51, freq="min")
    clean = pd.DataFrame({
        "ts_utc": index,
        "open": 0.6500,
        "high": 0.6501,
        "low": 0.6499,
        "close": 0.6500,
    }).set_index("ts_utc")
    source = clean.copy() - 0.0001
    source = source.drop(pd.Timestamp("2022-01-03T18:02:00Z"))
    source.loc[pd.Timestamp("2022-01-03T18:00:00Z"), "open"] = 0.6000
    source.loc[pd.Timestamp("2022-01-03T18:00:00Z"), "low"] = 0.5000
    return source, clean


def test_reconstruction_rejects_gross_fields_and_carries_sparse_minute():
    source, clean = fixture_frames()
    rebuilt, meta = reconstruct_window(
        source, clean, pd.Timestamp("2022-01-03T18:00:00Z"))
    assert list(rebuilt.columns) == BAR_COLUMNS
    assert len(rebuilt) == 15
    assert rebuilt.isna().sum().sum() == 0
    assert meta["carried_minutes"] == 1
    assert meta["max_source_age_minutes"] == 1
    assert meta["filtered_source_values"] >= 2
    first = rebuilt.iloc[0]
    assert abs(first.open - 0.6500) < 0.0002
    carried = rebuilt.loc[rebuilt.ts_utc.eq(pd.Timestamp("2022-01-03T18:02:00Z"))].iloc[0]
    assert carried.open == carried.high == carried.low == carried.close
    assert (rebuilt.high >= rebuilt[["open", "close"]].max(axis=1)).all()
    assert (rebuilt.low <= rebuilt[["open", "close"]].min(axis=1)).all()
