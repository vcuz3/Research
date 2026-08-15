from __future__ import annotations

import pandas as pd

from forex.build_clean_futures_volume import join_volume, normalize_futures


def test_exact_join_preserves_spot_rows_and_leaves_missing_volume_null() -> None:
    spot = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2026-01-01 00:00", "2026-01-01 00:01", "2026-01-01 00:02"]),
            "open": [1.0, 1.1, 1.2],
            "high": [1.1, 1.2, 1.3],
            "low": [0.9, 1.0, 1.1],
            "close": [1.05, 1.15, 1.25],
        }
    )
    raw_futures = pd.DataFrame(
        {
            "ts_event": pd.to_datetime(["2026-01-01 00:00Z", "2026-01-01 00:02Z"]),
            "volume": [7, 11],
            "instrument_id": [100, 100],
        }
    )
    futures = normalize_futures(raw_futures, "6E")
    output = join_volume(spot, futures, "EURUSD")

    assert output["ts_utc"].tolist() == spot["ts_utc"].tolist()
    assert output["volume"].tolist() == [7, pd.NA, 11]
    assert str(output["volume"].dtype) == "UInt64"


def test_join_is_not_asof_or_forward_filled() -> None:
    spot = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2026-01-01 00:01"]),
            "open": [1.0], "high": [1.1], "low": [0.9], "close": [1.0],
        }
    )
    futures = pd.DataFrame(
        {
            "ts_utc": pd.to_datetime(["2026-01-01 00:00"]),
            "volume": pd.array([99], dtype="UInt64"),
            "instrument_id": pd.Series([100], dtype="uint32"),
        }
    )
    assert pd.isna(join_volume(spot, futures, "EURUSD").loc[0, "volume"])
