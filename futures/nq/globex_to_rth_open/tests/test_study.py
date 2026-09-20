from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT = Path(__file__).resolve().parents[1]
if str(PROJECT) not in sys.path:
    sys.path.insert(0, str(PROJECT))

from backtest_engine.engine import CostModel, position_units, run_one
from strategy.features import build_rth_daily, build_trade_candidates, load_vix_daily


def _bar(ts: str, price: float, symbol: str = "A", roll: bool = False) -> dict:
    stamp = pd.Timestamp(ts, tz="America/New_York").tz_convert("UTC")
    return {"ts_utc": stamp, "symbol": symbol, "open": price, "high": price + 1,
            "low": price - 1, "close": price + 0.5, "volume": 10,
            "is_roll": roll}


def _decorate(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows).sort_values("ts_utc").reset_index(drop=True)
    local = frame.ts_utc.dt.tz_convert("America/New_York")
    frame["local_date"] = local.dt.tz_localize(None).dt.normalize()
    frame["local_minute"] = local.dt.hour * 60 + local.dt.minute
    return frame


def test_exact_next_date_anchors_and_fixed_clock_pnl():
    rows = []
    for day, close in [("2024-01-05", 100), ("2024-01-08", 105)]:
        rows += [_bar(f"{day} 09:30", close - 2), _bar(f"{day} 15:59", close)]
    rows += [_bar("2024-01-07 18:00", 100)]
    frame = _decorate(rows)
    daily, _ = build_rth_daily(frame, [2], reference_lookback=2, reference_min_obs=1)
    vix = pd.DataFrame({
        "vix_date": pd.to_datetime(["2024-01-05"]), "vix_open": [20.0],
        "vix_high": [21.0], "vix_low": [19.0], "vix_close": [20.0], "vix_ref": [19.0]})
    trades, quality = build_trade_candidates(
        frame, daily, vix, [2], 4, reference_lookback=2, reference_min_obs=1)
    assert quality["matched_anchor_pairs"] == 1
    assert len(trades) == 1
    assert trades.loc[0, "feature_date"] == pd.Timestamp("2024-01-05")
    assert trades.loc[0, "vix_date"] == pd.Timestamp("2024-01-05")
    assert trades.loc[0, "gross_points_per_contract"] == 3.0
    assert trades.loc[0, "holding_hours"] == 15.5


def test_roll_inside_holding_interval_is_excluded():
    rows = [
        _bar("2024-01-08 09:30", 100), _bar("2024-01-08 15:59", 101),
        _bar("2024-01-08 18:00", 102, "A"),
        _bar("2024-01-09 00:00", 103, "B", roll=True),
        _bar("2024-01-09 09:30", 104, "B"),
    ]
    frame = _decorate(rows)
    daily, _ = build_rth_daily(frame, [1], 2, 1)
    vix = pd.DataFrame({
        "vix_date": pd.to_datetime(["2024-01-08"]), "vix_open": [20.0],
        "vix_high": [21.0], "vix_low": [19.0], "vix_close": [20.0], "vix_ref": [20.0]})
    trades, quality = build_trade_candidates(frame, daily, vix, [1], 4, 2, 1)
    assert trades.empty
    assert quality["pairs_with_roll_inside"] == 1


def test_inverse_sizing_uses_reference_over_current_and_caps():
    frame = pd.DataFrame({"atr14_ref": [100.0, 100.0, 100.0],
                          "atr14": [50.0, 200.0, 10.0]})
    got = position_units(frame, "inverse_atr14", minimum=0.25, maximum=4.0,
                         integer_contracts=False)
    np.testing.assert_allclose(got, [2.0, 0.5, 4.0])


def test_costs_reconcile_exactly_for_one_contract():
    candidates = pd.DataFrame({
        "trade_date": pd.to_datetime(["2024-01-02"]),
        "gross_points_per_contract": [2.0],
        "atr14": [4.0],
    })
    cost = CostModel(multiplier=20, tick_size=.25, slippage_ticks_per_side=1,
                     commission_per_side=2.5)
    summary, trades = run_one(candidates, pd.Series([True]), "equal_contract", cost,
                              .25, 4, False)
    assert cost.round_trip_dollars_per_contract == 15.0
    assert trades.loc[0, "gross_dollars"] == 40.0
    assert trades.loc[0, "net_dollars"] == 25.0
    assert trades.loc[0, "gross_atr14_units_per_contract"] == 0.5
    assert trades.loc[0, "net_atr14_units_per_contract"] == 0.3125
    assert summary["total_net_dollars"] == 25.0


def test_daily_vix_reference_is_strictly_lagged(tmp_path: Path):
    path = tmp_path / "vix.csv"
    pd.DataFrame({
        "time": pd.date_range("2024-01-01", periods=4),
        "open": [10, 20, 30, 40], "high": [11, 21, 31, 41],
        "low": [9, 19, 29, 39], "close": [10, 20, 30, 40],
    }).to_csv(path, index=False)
    vix, _ = load_vix_daily(path, reference_lookback=2, reference_min_obs=2)
    assert np.isnan(vix.loc[1, "vix_ref"])
    assert vix.loc[2, "vix_ref"] == 15.0
    assert vix.loc[3, "vix_ref"] == 25.0
