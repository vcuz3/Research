"""Hand-reconciled fixed-schedule execution and accounting tests."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.backtest_engine.engine import (
    CostProfile,
    run_fixed_schedule,
)
from futures.nq.opening_shock_continuation.validation.pipeline import candidate_net_pnl


def _sessions() -> pd.DataFrame:
    dates = pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04"])
    entry_ts = pd.to_datetime(dates.strftime("%Y-%m-%d") + " 10:00:01").tz_localize(
        "America/New_York"
    ).tz_convert("UTC")
    exit_ts = pd.to_datetime(dates.strftime("%Y-%m-%d") + " 15:59:59").tz_localize(
        "America/New_York"
    ).tz_convert("UTC")
    return pd.DataFrame(
        {
            "date": dates,
            "entry": [100.0, 100.0, 100.0],
            "exit": [101.0, 99.0, 500.0],
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "prev_symbol": ["A", "A", "A"],
            "sym0930": ["A", "A", "A"],
            "sym0959": ["A", "A", "A"],
            "sym_entry": ["A", "A", "A"],
            "sym_exit": ["A", "A", "A"],
        }
    )


CLOCKS = {
    "decision_time_et": "10:00:00",
    "entry_time_et": "10:00:01",
    "exit_time_et": "15:59:59",
}


def test_nq_long_short_flat_hand_reconciliation_and_zero_day_accounting() -> None:
    result = run_fixed_schedule(
        _sessions(),
        pd.Series([1, -1, 0]),
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        costs=CostProfile(slippage_ticks_per_side=1.0, round_trip_fees_usd=4.50),
        **CLOCKS,
        strategy_name="fixture",
    )
    assert len(result) == 3
    assert result["trade"].tolist() == [True, True, False]
    np.testing.assert_allclose(result.loc[:1, "gross_points"], [1.0, 1.0])
    np.testing.assert_allclose(result.loc[:1, "entry_fill"], [100.25, 99.75])
    np.testing.assert_allclose(result.loc[:1, "exit_fill"], [100.75, 99.25])
    np.testing.assert_allclose(result.loc[:1, "net_points_before_fees"], [0.5, 0.5])
    np.testing.assert_allclose(result.loc[:1, "gross_dollars"], [20.0, 20.0])
    np.testing.assert_allclose(result.loc[:1, "slippage_dollars"], [10.0, 10.0])
    np.testing.assert_allclose(result.loc[:1, "fees_dollars"], [4.5, 4.5])
    np.testing.assert_allclose(result.loc[:1, "net_dollars"], [5.5, 5.5])
    assert result.loc[2, ["entry_fill", "exit_fill"]].isna().all()
    zero_columns = [
        "gross_points",
        "slippage_points",
        "net_points_before_fees",
        "gross_dollars",
        "slippage_dollars",
        "fees_dollars",
        "net_dollars",
        "gross_bps",
        "net_bps",
    ]
    assert result.loc[2, zero_columns].eq(0).all()
    assert result["decision_time_et"].eq("10:00:00").all()
    assert result["entry_time_et"].eq("10:00:01").all()
    assert result["exit_time_et"].eq("15:59:59").all()


def test_es_contract_multiplier_costs_and_bps() -> None:
    sessions = _sessions().iloc[:1]
    result = run_fixed_schedule(
        sessions,
        [1],
        instrument="es",
        entry_column="entry",
        exit_column="exit",
        costs=CostProfile(1.0, 4.50),
        **CLOCKS,
    ).iloc[0]
    assert result["gross_dollars"] == pytest.approx(50.0)
    assert result["slippage_dollars"] == pytest.approx(25.0)
    assert result["net_dollars"] == pytest.approx(20.5)
    assert result["gross_bps"] == pytest.approx(100.0)
    assert result["net_bps"] == pytest.approx(10_000.0 * 20.5 / (100.0 * 50.0))


def test_net_reconciles_from_adverse_fills_and_fees() -> None:
    result = run_fixed_schedule(
        _sessions(),
        [1, -1, 0],
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        costs=CostProfile(2.0, 7.25),
        **CLOCKS,
    )
    traded = result["trade"]
    fill_points = result.loc[traded, "side"] * (
        result.loc[traded, "exit_fill"] - result.loc[traded, "entry_fill"]
    )
    np.testing.assert_allclose(fill_points, result.loc[traded, "net_points_before_fees"])
    np.testing.assert_allclose(
        fill_points * 20.0 - result.loc[traded, "fees_dollars"],
        result.loc[traded, "net_dollars"],
    )
    np.testing.assert_allclose(
        result.loc[traded, "gross_dollars"]
        - result.loc[traded, "slippage_dollars"]
        - result.loc[traded, "fees_dollars"],
        result.loc[traded, "net_dollars"],
    )


def test_zero_cost_profile_preserves_gross_pnl() -> None:
    result = run_fixed_schedule(
        _sessions(),
        [1, -1, 0],
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        costs=CostProfile(0.0, 0.0),
        **CLOCKS,
    )
    np.testing.assert_allclose(result["net_dollars"], result["gross_dollars"])


def test_vectorized_candidate_pnl_matches_audited_engine_cost_algebra() -> None:
    sessions = _sessions()
    signals = pd.DataFrame(
        {
            "candidate_a": [1, -1, 0],
            "candidate_b": [-1, 0, 1],
        },
        index=sessions.index,
    )
    vectorized = candidate_net_pnl(
        sessions,
        signals,
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        slippage_ticks_per_side=1.0,
        round_trip_fees_usd=4.5,
    )
    for column, name in enumerate(signals):
        audited = run_fixed_schedule(
            sessions,
            signals[name],
            instrument="NQ",
            entry_column="entry",
            exit_column="exit",
            costs=CostProfile(1.0, 4.5),
            strategy_name=name,
            **CLOCKS,
        )
        np.testing.assert_allclose(vectorized[:, column], audited["net_dollars"])


def test_et_activation_is_named_zone_dst_safe_before_and_after_transitions() -> None:
    dates = pd.to_datetime(["2024-03-08", "2024-03-11", "2024-11-01", "2024-11-04"])
    entry_ts = pd.to_datetime(dates.strftime("%Y-%m-%d") + " 10:00:01").tz_localize(
        "America/New_York"
    ).tz_convert("UTC")
    exit_ts = pd.to_datetime(dates.strftime("%Y-%m-%d") + " 15:59:59").tz_localize(
        "America/New_York"
    ).tz_convert("UTC")
    # ET moves from UTC-5 to UTC-4 in March and back in November.
    assert entry_ts.hour.tolist() == [15, 14, 14, 15]
    sessions = pd.DataFrame(
        {
            "date": dates,
            "entry": [100.0] * 4,
            "exit": [101.0] * 4,
            "entry_ts": entry_ts,
            "exit_ts": exit_ts,
            "prev_symbol": ["A"] * 4,
            "sym0930": ["A"] * 4,
            "sym0959": ["A"] * 4,
            "sym_entry": ["A"] * 4,
            "sym_exit": ["A"] * 4,
        }
    )
    result = run_fixed_schedule(
        sessions,
        [1, 1, 1, 1],
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        **CLOCKS,
    )
    assert result["entry_latency_seconds"].eq(0).all()
    assert result["exit_latency_seconds"].eq(0).all()


@pytest.mark.parametrize(
    "costs",
    [CostProfile,],
)
def test_cost_profile_rejects_negative_inputs(costs) -> None:
    with pytest.raises(ValueError, match="non-negative"):
        costs(-0.1, 0.0)
    with pytest.raises(ValueError, match="non-negative"):
        costs(0.0, -0.1)


def test_engine_rejects_bad_shape_domain_instrument_and_prices() -> None:
    sessions = _sessions()
    kwargs = dict(instrument="NQ", entry_column="entry", exit_column="exit", **CLOCKS)
    with pytest.raises(ValueError, match="one side"):
        run_fixed_schedule(sessions, [1, -1], **kwargs)
    with pytest.raises(ValueError, match="-1, 0, or 1"):
        run_fixed_schedule(sessions, [1, 2, 0], **kwargs)
    with pytest.raises(ValueError, match="-1, 0, or 1"):
        run_fixed_schedule(sessions, [1.0, 0.5, 0.0], **kwargs)
    with pytest.raises(KeyError, match="unsupported instrument"):
        run_fixed_schedule(sessions, [1, -1, 0], instrument="YM", entry_column="entry", exit_column="exit", **CLOCKS)
    with pytest.raises(ValueError, match="column missing"):
        run_fixed_schedule(sessions, [1, -1, 0], instrument="NQ", entry_column="missing", exit_column="exit", **CLOCKS)

    bad = sessions.copy()
    bad.loc[0, "entry"] = np.nan
    with pytest.raises(ValueError, match="finite"):
        run_fixed_schedule(bad, [1, -1, 0], **kwargs)
    bad.loc[0, "entry"] = 0.0
    with pytest.raises(ValueError, match="positive"):
        run_fixed_schedule(bad, [1, -1, 0], **kwargs)


def test_unused_missing_price_still_produces_explicit_flat_zero() -> None:
    sessions = _sessions()
    sessions.loc[2, ["entry", "exit"]] = np.nan
    result = run_fixed_schedule(
        sessions,
        [1, -1, 0],
        instrument="NQ",
        entry_column="entry",
        exit_column="exit",
        **CLOCKS,
    )
    assert not result.loc[2, "trade"]
    assert result.loc[2, ["gross_dollars", "net_dollars", "gross_bps", "net_bps"]].eq(0).all()


@pytest.mark.parametrize(
    ("decision", "entry", "exit_time"),
    [
        ("10:00:01", "10:00:01", "15:59:59"),
        ("10:00:02", "10:00:01", "15:59:59"),
        ("09:59:59", "16:00:00", "15:59:59"),
    ],
)
def test_engine_rejects_noncausal_clock_order(decision: str, entry: str, exit_time: str) -> None:
    with pytest.raises(ValueError, match="decision.*entry.*exit"):
        run_fixed_schedule(
            _sessions(),
            [1, -1, 0],
            instrument="NQ",
            entry_column="entry",
            exit_column="exit",
            decision_time_et=decision,
            entry_time_et=entry,
            exit_time_et=exit_time,
        )


def test_engine_binds_actual_timestamp_symbol_and_side_index() -> None:
    sessions = _sessions()
    early = sessions.copy()
    early.loc[0, "entry_ts"] = pd.Timestamp("2024-01-02 14:59:59", tz="UTC")
    with pytest.raises(ValueError, match="precedes declared activation"):
        run_fixed_schedule(
            early, pd.Series([1, 0, 0]), instrument="NQ", entry_column="entry", exit_column="exit", **CLOCKS
        )

    wrong_symbol = sessions.copy()
    wrong_symbol.loc[0, "sym_entry"] = "B"
    with pytest.raises(ValueError, match="one contract symbol"):
        run_fixed_schedule(
            wrong_symbol, pd.Series([1, 0, 0]), instrument="NQ", entry_column="entry", exit_column="exit", **CLOCKS
        )

    reversed_side = pd.Series([1, 0, 0], index=[2, 1, 0])
    with pytest.raises(ValueError, match="index"):
        run_fixed_schedule(
            sessions, reversed_side, instrument="NQ", entry_column="entry", exit_column="exit", **CLOCKS
        )
