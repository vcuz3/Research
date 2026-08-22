"""Synthetic tests for the frozen exchange calendar and data joins."""

from __future__ import annotations

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
import pytest

from futures.nq.opening_shock_continuation.backtest_engine import data


@pytest.fixture(autouse=True)
def _clear_cached_data_extracts():
    """Keep monkeypatched synthetic archives isolated from one another."""

    data.session_summary.cache_clear()
    data.one_second_execution.cache_clear()
    yield
    data.session_summary.cache_clear()
    data.one_second_execution.cache_clear()


def test_nyse_calendar_holidays_early_closes_and_weekends() -> None:
    sessions = data.nyse_session_dates("2023-11-20", "2023-11-27")
    assert sessions.tolist() == list(
        pd.to_datetime(
            ["2023-11-20", "2023-11-21", "2023-11-22", "2023-11-24", "2023-11-27"]
        )
    )
    # The day after Thanksgiving is an early close, not a full closure.
    assert pd.Timestamp("2023-11-24") in sessions


@pytest.mark.parametrize(
    ("year", "expected"),
    [
        (2012, ["2012-07-03", "2012-11-23", "2012-12-24"]),
        # Independence Day and Christmas are weekend-observed full closures.
        (2021, ["2021-11-26"]),
        (2024, ["2024-07-03", "2024-11-29", "2024-12-24"]),
    ],
)
def test_nyse_early_close_schedule_fixtures(year: int, expected: list[str]) -> None:
    actual = data.nyse_early_close_dates(f"{year}-01-01", f"{year}-12-31")
    assert actual.tolist() == list(pd.to_datetime(expected))
    assert set(actual).issubset(data.nyse_session_dates(f"{year}-01-01", f"{year}-12-31"))


def test_full_frozen_early_close_fixture_for_local_sample() -> None:
    expected = pd.to_datetime(
        [
            "2011-11-25",
            "2012-07-03", "2012-11-23", "2012-12-24",
            "2013-07-03", "2013-11-29", "2013-12-24",
            "2014-07-03", "2014-11-28", "2014-12-24",
            "2015-11-27", "2015-12-24",
            "2016-11-25",
            "2017-07-03", "2017-11-24",
            "2018-07-03", "2018-11-23", "2018-12-24",
            "2019-07-03", "2019-11-29", "2019-12-24",
            "2020-11-27", "2020-12-24",
            "2021-11-26",
            "2022-11-25",
            "2023-07-03", "2023-11-24",
            "2024-07-03", "2024-11-29", "2024-12-24",
            "2025-07-03", "2025-11-28", "2025-12-24",
            "2026-11-27", "2026-12-24",
        ]
    )
    actual = data.nyse_early_close_dates("2011-08-01", "2026-07-14")
    expected_in_scope = expected[(expected >= "2011-08-01") & (expected <= "2026-07-14")]
    assert actual.tolist() == expected_in_scope.tolist()


@pytest.mark.parametrize(
    "day",
    ["2012-10-29", "2012-10-30", "2018-12-05", "2025-01-09"],
)
def test_nyse_calendar_unscheduled_full_closures(day: str) -> None:
    assert pd.Timestamp(day) not in data.nyse_session_dates(day, day)


def test_nyse_calendar_historical_juneteenth_and_saturday_new_year_policy() -> None:
    # The exchange first observed Juneteenth as a full closure in 2022.
    assert pd.Timestamp("2021-06-18") in data.nyse_session_dates("2021-06-18", "2021-06-18")
    assert pd.Timestamp("2022-06-20") not in data.nyse_session_dates("2022-06-20", "2022-06-20")
    # NYSE did not shift Saturday 2022-01-01 back to Friday 2021-12-31.
    assert pd.Timestamp("2021-12-31") in data.nyse_session_dates("2021-12-31", "2021-12-31")


def test_nyse_calendar_is_inclusive_and_rejects_no_valid_dates() -> None:
    assert data.nyse_session_dates("2024-01-02", "2024-01-02").tolist() == [
        pd.Timestamp("2024-01-02")
    ]
    assert data.nyse_session_dates("2024-01-06", "2024-01-07").empty


def test_condition_calendar_normalizes_and_rejects_duplicates(tmp_path: Path) -> None:
    good = tmp_path / "good.csv"
    pd.DataFrame(
        {
            "date": ["2024-01-02 12:34:56", "2024-01-03 00:00:00"],
            "condition": ["available", "degraded"],
            "last_modified_date": ["2024-01-04", "2024-01-04"],
            "ignored": [1, 2],
        }
    ).to_csv(good, index=False)
    result = data.condition_calendar(good)
    assert result.columns.tolist() == ["date", "condition", "last_modified_date"]
    assert result["date"].tolist() == [pd.Timestamp("2024-01-02"), pd.Timestamp("2024-01-03")]

    duplicate = tmp_path / "duplicate.csv"
    pd.DataFrame(
        {
            "date": ["2024-01-02 01:00:00", "2024-01-02 22:00:00"],
            "condition": ["available", "available"],
            "last_modified_date": ["2024-01-04", "2024-01-04"],
        }
    ).to_csv(duplicate, index=False)
    with pytest.raises(ValueError, match="duplicate dates"):
        data.condition_calendar(duplicate)


def _bars_for_day(
    day: str,
    symbol: str,
    *,
    roll_at_open: bool = False,
    base_price: float = 100.0,
    omit_clocks: tuple[str, ...] = (),
) -> pd.DataFrame:
    wall = pd.date_range(f"{day} 09:30:00", periods=390, freq="min", tz="America/New_York")
    price = base_price + np.arange(390) / 100.0
    frame = pd.DataFrame(
        {
            "ts_utc": wall.tz_convert("UTC"),
            "symbol": symbol,
            "open": price,
            "high": price + 0.20,
            "low": price - 0.20,
            "close": price + 0.05,
            "volume": np.full(390, 10, dtype=np.int64),
            "is_roll": np.r_[roll_at_open, np.zeros(389, dtype=bool)],
        }
    )
    if omit_clocks:
        et_clock = frame["ts_utc"].dt.tz_convert("America/New_York").dt.strftime("%H:%M:%S")
        frame = frame.loc[~et_clock.isin(omit_clocks)].reset_index(drop=True)
    return frame


def _write_parquet(path: Path, frame: pd.DataFrame) -> None:
    connection = duckdb.connect()
    try:
        connection.register("synthetic_bars", frame)
        escaped = str(path).replace("'", "''")
        connection.execute(f"COPY synthetic_bars TO '{escaped}' (FORMAT PARQUET)")
    finally:
        connection.close()


def test_session_summary_masks_cross_contract_and_intraday_rolls(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    bars = pd.concat(
        [
            _bars_for_day("2024-01-02", "A"),
            _bars_for_day("2024-01-03", "A"),
            _bars_for_day("2024-01-04", "B"),
            _bars_for_day("2024-01-05", "B"),
            _bars_for_day("2024-01-08", "B", roll_at_open=True),
        ],
        ignore_index=True,
    )
    path = tmp_path / "synthetic.parquet"
    _write_parquet(path, bars)
    monkeypatch.setitem(data.DATA_PATHS, "NQ", path)
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03", "2024-01-04", "2024-01-05", "2024-01-08"]),
            "condition": ["available"] * 5,
            "last_modified_date": ["2024-01-09"] * 5,
        }
    )
    monkeypatch.setattr(data, "condition_calendar", lambda: calendar.copy())

    result = data.session_summary("NQ").set_index("date")
    assert result["complete"].all()
    assert result["prior_calendar_contiguous"].tolist() == [False, True, True, True, True]
    assert result["eligible"].tolist() == [False, True, False, True, False]
    assert not bool(result.loc[pd.Timestamp("2024-01-04"), "same_contract"])
    assert result.loc[pd.Timestamp("2024-01-08"), "rth_roll_rows"] == 1
    assert result.loc[pd.Timestamp("2024-01-03"), "prev_close"] == pytest.approx(103.94)


def test_prior_expected_session_skips_represented_nyse_closure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A CME record on an NYSE closure cannot become the next gap anchor."""

    bars = pd.concat(
        [
            _bars_for_day("2025-01-08", "A", base_price=100.0),
            # National day of mourning: represented by CME, closed on NYSE.
            _bars_for_day("2025-01-09", "X", base_price=200.0),
            _bars_for_day("2025-01-10", "A", base_price=300.0),
        ],
        ignore_index=True,
    )
    path = tmp_path / "closure_bridge.parquet"
    _write_parquet(path, bars)
    monkeypatch.setitem(data.DATA_PATHS, "NQ", path)
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(["2025-01-08", "2025-01-09", "2025-01-10"]),
            "condition": ["available"] * 3,
            "last_modified_date": ["2025-01-11"] * 3,
        }
    )
    monkeypatch.setattr(data, "condition_calendar", lambda: calendar.copy())

    result = data.session_summary("NQ").set_index("date")
    closure = result.loc[pd.Timestamp("2025-01-09")]
    after = result.loc[pd.Timestamp("2025-01-10")]
    assert not bool(closure["expected_session"])
    assert after["prev_expected_date"] == pd.Timestamp("2025-01-08")
    assert after["prev_close"] == pytest.approx(103.94)
    assert after["prev_symbol"] == "A"
    assert bool(after["prior_calendar_contiguous"])
    assert bool(after["opening_same_contract"])
    assert bool(after["causal_measurement_available"])


_CLOCK_TIMES = {
    "entry_100000": "10:00:00",
    "entry_100001": "10:00:01",
    "entry_100002": "10:00:02",
    "entry_100005": "10:00:05",
    "entry_100030": "10:00:30",
    "entry_100100": "10:01:00",
    "entry_153000": "15:30:00",
    "entry_153001": "15:30:01",
    "exit_155958": "15:59:58",
    "exit_155959": "15:59:59",
    "exit_160000": "16:00:00",
}


def _execution_rows(
    dates: list[str], *, missing: tuple[str, ...] = ()
) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    for row_number, day in enumerate(dates):
        row: dict[str, object] = {"date": pd.Timestamp(day), "instrument": "NQ"}
        for clock_number, label in enumerate(data.EXECUTION_CLOCKS):
            if label in missing:
                row[label] = np.nan
                row[f"{label}_ts"] = pd.NaT
                row[f"sym_{label}"] = None
                continue
            row[label] = 100.0 + row_number + clock_number / 100.0
            row[f"{label}_ts"] = pd.Timestamp(
                f"{day} {_CLOCK_TIMES[label]}", tz="America/New_York"
            ).tz_convert("UTC")
            row[f"sym_{label}"] = "A"
        rows.append(row)
    return pd.DataFrame(rows)


def _install_incomplete_causal_fixture(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> pd.Timestamp:
    decision_day = pd.Timestamp("2024-01-03")
    bars = pd.concat(
        [
            _bars_for_day("2024-01-02", "A"),
            # The signal and both endpoints exist; only an irrelevant future
            # midday minute is absent.
            _bars_for_day("2024-01-03", "A", omit_clocks=("12:00:00",)),
        ],
        ignore_index=True,
    )
    path = tmp_path / "incomplete_midday.parquet"
    _write_parquet(path, bars)
    monkeypatch.setitem(data.DATA_PATHS, "NQ", path)
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "condition": ["available", "available"],
            "last_modified_date": ["2024-01-04", "2024-01-04"],
        }
    )
    monkeypatch.setattr(data, "condition_calendar", lambda: calendar.copy())
    return decision_day


def test_causal_endpoint_cohort_does_not_condition_on_future_midday_completeness(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_day = _install_incomplete_causal_fixture(tmp_path, monkeypatch)
    summary = data.session_summary("NQ").set_index("date")
    row = summary.loc[decision_day]
    assert not bool(row["complete"])
    assert bool(row["causal_opening_complete"])
    assert bool(row["causal_measurement_available"])
    assert not bool(row["eligible"])

    seconds = _execution_rows([str(decision_day.date())])
    monkeypatch.setattr(data, "one_second_execution", lambda instrument: seconds.copy())
    causal = data.execution_sessions("NQ", strict_full_session=False)
    strict = data.execution_sessions("NQ", strict_full_session=True)
    assert causal["date"].tolist() == [decision_day]
    assert strict.empty


def test_missing_required_primary_exit_raises_instead_of_shrinking_cohort(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_day = _install_incomplete_causal_fixture(tmp_path, monkeypatch)
    seconds = _execution_rows([str(decision_day.date())], missing=("exit_155959",))
    monkeypatch.setattr(data, "one_second_execution", lambda instrument: seconds.copy())

    with pytest.raises(AssertionError, match="invalid required execution records"):
        data.execution_sessions(
            "NQ",
            required_clocks=("entry_100001", "exit_155959"),
            strict_full_session=False,
        )


def test_intraday_contract_switch_and_switch_back_is_a_hard_post_run_failure(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    decision_day = pd.Timestamp("2024-01-03")
    prior = _bars_for_day("2024-01-02", "A")
    current = _bars_for_day("2024-01-03", "A")
    # Opening and close endpoints return to A, so endpoint-only symbol checks
    # would miss this midday transition without the all-RTH identity assertion.
    current.loc[150:210, "symbol"] = "B"
    bars = pd.concat([prior, current], ignore_index=True)
    path = tmp_path / "switch_back.parquet"
    _write_parquet(path, bars)
    monkeypatch.setitem(data.DATA_PATHS, "NQ", path)
    calendar = pd.DataFrame(
        {
            "date": pd.to_datetime(["2024-01-02", "2024-01-03"]),
            "condition": ["available", "available"],
            "last_modified_date": ["2024-01-04", "2024-01-04"],
        }
    )
    monkeypatch.setattr(data, "condition_calendar", lambda: calendar.copy())
    seconds = _execution_rows([str(decision_day.date())])
    monkeypatch.setattr(data, "one_second_execution", lambda instrument: seconds.copy())

    summary = data.session_summary("NQ").set_index("date")
    assert bool(summary.loc[decision_day, "causal_measurement_available"])
    assert summary.loc[decision_day, "n_rth_symbols"] == 2
    with pytest.raises(AssertionError, match="invalid required execution records"):
        data.execution_sessions("NQ")


def test_one_second_execution_uses_first_record_at_or_after_each_activation(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    wall_times = [
        "10:00:00",
        "10:00:01",
        "10:00:02",
        "10:00:05",
        "10:00:30",
        "10:01:00",
        "15:30:00",
        "15:30:01",
        "15:59:58",
        "15:59:59",
        "16:00:00",
    ]
    wall = pd.DatetimeIndex(
        [pd.Timestamp(f"2024-07-08 {clock}", tz="America/New_York") for clock in wall_times]
    )
    frame = pd.DataFrame(
        {
            "ts_utc": wall.tz_convert("UTC"),
            "symbol": ["A"] * len(wall),
            "open": np.arange(len(wall), dtype=float) + 100.0,
        }
    )
    path = tmp_path / "seconds.parquet"
    _write_parquet(path, frame)
    monkeypatch.setitem(data.ONE_SECOND_PATHS, "NQ", path)

    row = data.one_second_execution("NQ").iloc[0]
    expected = {
        "entry_100000": 100.0,
        "entry_100001": 101.0,
        "entry_100002": 102.0,
        "entry_100005": 103.0,
        "entry_100030": 104.0,
        "entry_100100": 105.0,
        "entry_153000": 106.0,
        "entry_153001": 107.0,
        "exit_155958": 108.0,
        "exit_155959": 109.0,
        "exit_160000": 110.0,
    }
    for column, expected_price in expected.items():
        assert row[column] == expected_price
        assert row[f"sym_{column}"] == "A"
    assert row["entry_100001_ts"].tz_convert("America/New_York").strftime("%H:%M:%S") == "10:00:01"
    assert row["exit_155959_ts"].tz_convert("America/New_York").strftime("%H:%M:%S") == "15:59:59"
