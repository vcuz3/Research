import pandas as pd
import pytest

from forex.download_aonia_futures_ibkr import (
    add_implied_rate_columns,
    selection_window,
)


def test_selection_window_is_previous_sydney_month():
    start, end = selection_window("20260930")
    assert str(start) == "2026-08-01 00:00:00+10:00"
    assert str(end) == "2026-09-01 00:00:00+10:00"


def test_price_to_rate_ohlc_reverses_high_and_low():
    frame = pd.DataFrame(
        {"open": [95.60], "high": [95.65], "low": [95.55], "close": [95.62]}
    )
    out = add_implied_rate_columns(frame)
    assert out.loc[0, "rate_open"] == pytest.approx(4.40)
    assert out.loc[0, "rate_high"] == pytest.approx(4.45)
    assert out.loc[0, "rate_low"] == pytest.approx(4.35)
    assert out.loc[0, "rate_close"] == pytest.approx(4.38)
