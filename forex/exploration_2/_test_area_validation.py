"""Executable checks for paired area validation and spread diagnostics."""

import numpy as np
import pandas as pd

from _area_validation import (
    add_signal_state_costs,
    common_date_portfolio,
    moving_block_bootstrap_mean,
    paired_session_panel,
)


def frame_for_validation(periods=80):
    times = pd.date_range("2023-01-02", periods=periods, freq="5min", tz="UTC")
    close = 1.0 + np.r_[0.0, np.cumsum(np.full(periods - 1, 0.0001))]
    session_date = pd.Series(pd.Timestamp("2023-01-02"), index=range(periods))
    session_date.iloc[40:] = pd.Timestamp("2023-01-03")
    return pd.DataFrame({
        "bar_open": times, "open": close, "close": close,
        "complete_5m": True, "contiguous": np.r_[False, np.ones(periods - 1, bool)],
        "segment": 1, "session_date": session_date, "band_ready": True,
    })


def test_session_panel_includes_zero_trade_sessions_and_pairs_variants():
    frame = frame_for_validation()
    frame.loc[40:, "session_date"] = pd.Timestamp("2023-01-03")
    trades = pd.DataFrame({
        "session_date": [pd.Timestamp("2023-01-02"), pd.Timestamp("2023-01-02")],
        "variant": ["first_cross", "large_move_control"],
        "gross_pips_60m": [2.0, 0.5],
    })
    panel = paired_session_panel(frame, trades, 60)
    assert len(panel) == 2
    assert panel.difference.tolist() == [1.5, 0.0]


def test_block_bootstrap_constant_difference_is_exact():
    result = moving_block_bootstrap_mean(np.full(200, 0.25), block_length=20, draws=500)
    assert result["mean_difference_pips_per_session"] == 0.25
    assert np.isclose(result["ci_2_5"], 0.25)
    assert np.isclose(result["ci_97_5"], 0.25)
    assert result["bootstrap_probability_positive"] == 1.0


def test_state_cost_proxy_is_explicit_and_volatility_scaled():
    frame = frame_for_validation()
    trades = pd.DataFrame({
        "signal_bar_open": [frame.bar_open.iloc[20], frame.bar_open.iloc[60]],
        "decision_time": [frame.bar_open.iloc[20] + pd.Timedelta(minutes=5),
                          frame.bar_open.iloc[60] + pd.Timedelta(minutes=5)],
        "gross_pips_15m": [3.0, 3.0], "gross_pips_30m": [3.0, 3.0],
        "gross_pips_60m": [3.0, 3.0], "gross_pips_120m": [3.0, 3.0],
    })
    priced, diagnostics = add_signal_state_costs(
        frame, trades, base_round_trip_spread_pips=0.5,
        commission_round_trip_pips=0.7, slippage_per_side_pips=0.1,
    )
    assert priced.estimated_all_in_cost_pips.ge(1.4).all()
    assert np.allclose(priced.proxy_net_pips_60m, 3.0 - priced.estimated_all_in_cost_pips)
    assert diagnostics.base_rt_spread_pips == 0.5


def test_common_date_portfolio_preserves_pair_date_alignment():
    a = pd.DataFrame({"session_date": pd.date_range("2023-01-01", periods=3),
                      "difference": [1.0, 2.0, 3.0]})
    b = pd.DataFrame({"session_date": pd.date_range("2023-01-02", periods=3),
                      "difference": [3.0, 4.0, 5.0]})
    got = common_date_portfolio({"A": a, "B": b})
    assert got.session_date.tolist() == list(pd.date_range("2023-01-02", periods=2))
    assert got.difference.tolist() == [2.5, 3.5]


if __name__ == "__main__":
    test_session_panel_includes_zero_trade_sessions_and_pairs_variants()
    test_block_bootstrap_constant_difference_is_exact()
    test_state_cost_proxy_is_explicit_and_volatility_scaled()
    test_common_date_portfolio_preserves_pair_date_alignment()
    print("4 area validation invariants passed")
