"""Timezone-safe construction of complete NQ/ES cash-session records.

The shared clean files contain raw, tradable prices for Databento's volume-ranked
continuous contracts.  Intraday PnL stays on those raw prices.  Cross-session
features are disabled whenever the active contract changes, so a synthetic roll
gap can never become an opening signal.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date as Date
from datetime import timedelta
from hashlib import sha256
from functools import lru_cache
from pathlib import Path
from typing import Iterable

import duckdb
import numpy as np
import pandas as pd
from dateutil.easter import easter


WORKSPACE = Path(__file__).resolve().parents[4]
SHARED_DATA = WORKSPACE / "futures" / "nq" / "data"
CONDITION_PATH = (
    WORKSPACE
    / "futures"
    / "data"
    / "databento"
    / "GLBX_MDP3_dataset_condition_20110801_20260717.csv"
)
DATA_PATHS = {
    "NQ": SHARED_DATA / "NQ_1m_clean.parquet",
    "ES": SHARED_DATA / "ES_1m_clean.parquet",
}
ONE_SECOND_PATHS = {
    "NQ": SHARED_DATA / "NQ_1s_clean.parquet",
    "ES": (
        WORKSPACE
        / "futures"
        / "data"
        / "databento"
        / "ES_ohlcv-1s_ESv0_20100606_20260724.parquet"
    ),
}


@dataclass(frozen=True)
class InstrumentSpec:
    multiplier: float
    tick_size: float


INSTRUMENT_SPECS = {
    "NQ": InstrumentSpec(multiplier=20.0, tick_size=0.25),
    "ES": InstrumentSpec(multiplier=50.0, tick_size=0.25),
}


def file_sha256(path: Path, chunk_size: int = 8 * 1024 * 1024) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(chunk_size):
            digest.update(chunk)
    return digest.hexdigest()


def condition_calendar(path: Path = CONDITION_PATH) -> pd.DataFrame:
    frame = pd.read_csv(path, parse_dates=["date"])
    frame["date"] = frame["date"].dt.normalize()
    if frame["date"].duplicated().any():
        raise ValueError("duplicate dates in Databento condition calendar")
    return frame[["date", "condition", "last_modified_date"]].copy()


def _quoted_path(path: Path) -> str:
    return str(path.resolve()).replace("'", "''")


def _observed_fixed_holiday(day: Date, *, saturday_to_friday: bool = True) -> Date:
    if day.weekday() == 5 and saturday_to_friday:
        return day - timedelta(days=1)
    if day.weekday() == 6:
        return day + timedelta(days=1)
    return day


def _nth_weekday(year: int, month: int, weekday: int, occurrence: int) -> Date:
    first = Date(year, month, 1)
    offset = (weekday - first.weekday()) % 7
    return first + timedelta(days=offset + 7 * (occurrence - 1))


def _last_weekday(year: int, month: int, weekday: int) -> Date:
    first_next = Date(year + (month == 12), 1 if month == 12 else month + 1, 1)
    day = first_next - timedelta(days=1)
    return day - timedelta(days=(day.weekday() - weekday) % 7)


def nyse_session_dates(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Return the frozen US-equity trading calendar needed by this project.

    It covers the local 2011-2026 span and includes the three unscheduled full
    closures in that interval. Early closes remain sessions, as they should.
    """

    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    closed: set[Date] = set()
    for year in range(start_ts.year - 1, end_ts.year + 2):
        new_year = Date(year, 1, 1)
        # NYSE does not shift a Saturday New Year's Day back into December.
        closed.add(_observed_fixed_holiday(new_year, saturday_to_friday=False))
        closed.add(_nth_weekday(year, 1, 0, 3))  # Martin Luther King Jr. Day
        closed.add(_nth_weekday(year, 2, 0, 3))  # Washington's Birthday
        closed.add(easter(year) - timedelta(days=2))  # Good Friday
        closed.add(_last_weekday(year, 5, 0))  # Memorial Day
        if year >= 2022:
            closed.add(_observed_fixed_holiday(Date(year, 6, 19)))
        closed.add(_observed_fixed_holiday(Date(year, 7, 4)))
        closed.add(_nth_weekday(year, 9, 0, 1))  # Labor Day
        closed.add(_nth_weekday(year, 11, 3, 4))  # Thanksgiving
        closed.add(_observed_fixed_holiday(Date(year, 12, 25)))
    closed.update(
        {
            Date(2012, 10, 29),
            Date(2012, 10, 30),
            Date(2018, 12, 5),
            Date(2025, 1, 9),
        }
    )
    candidates = pd.date_range(start_ts, end_ts, freq="D")
    return pd.DatetimeIndex(
        [day for day in candidates if day.weekday() < 5 and day.date() not in closed]
    )


def nyse_early_close_dates(start: str | pd.Timestamp, end: str | pd.Timestamp) -> pd.DatetimeIndex:
    """Known 13:00 ET NYSE closes over this project's 2011-2026 span."""

    start_ts = pd.Timestamp(start).normalize()
    end_ts = pd.Timestamp(end).normalize()
    sessions = set(nyse_session_dates(start_ts, end_ts))
    early: set[pd.Timestamp] = set()
    for year in range(start_ts.year, end_ts.year + 1):
        thanksgiving = pd.Timestamp(_nth_weekday(year, 11, 3, 4))
        early.add(thanksgiving + pd.Timedelta(days=1))
        july_third = pd.Timestamp(Date(year, 7, 3))
        if july_third in sessions:
            early.add(july_third)
        christmas_eve = pd.Timestamp(Date(year, 12, 24))
        if christmas_eve in sessions:
            early.add(christmas_eve)
    return pd.DatetimeIndex(sorted(day for day in early if start_ts <= day <= end_ts))


@lru_cache(maxsize=2)
def session_summary(instrument: str) -> pd.DataFrame:
    """Return one row per represented ET RTH date before eligibility filtering."""

    instrument = instrument.upper()
    if instrument not in DATA_PATHS:
        raise KeyError(f"unsupported instrument: {instrument}")
    path = DATA_PATHS[instrument]
    query = f"""
    WITH rth AS (
      SELECT
        ts_utc,
        timezone('America/New_York', ts_utc) AS et_wall,
        CAST(timezone('America/New_York', ts_utc) AS DATE) AS session_date,
        CAST(timezone('America/New_York', ts_utc) AS TIME) AS tod,
        symbol, open, high, low, close, volume, is_roll
      FROM read_parquet('{_quoted_path(path)}')
      WHERE CAST(timezone('America/New_York', ts_utc) AS TIME) >= TIME '09:30:00'
        AND CAST(timezone('America/New_York', ts_utc) AS TIME) < TIME '16:00:00'
    ), links AS (
      SELECT
        *,
        ln(close / lag(close) OVER (PARTITION BY session_date ORDER BY et_wall)) AS log_ret,
        date_diff('second',
          lag(et_wall) OVER (PARTITION BY session_date ORDER BY et_wall),
          et_wall) AS gap_seconds
      FROM rth
    )
    SELECT
      session_date AS date,
      count(*) AS n_bars,
      count(DISTINCT et_wall) AS n_unique_bars,
      min(tod) AS first_tod,
      max(tod) AS last_tod,
      max(coalesce(gap_seconds, 0)) AS max_gap_seconds,
      sum(CASE WHEN is_roll THEN 1 ELSE 0 END) AS rth_roll_rows,
      count(DISTINCT symbol) AS n_rth_symbols,
      count(*) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS n_opening_bars,
      count(DISTINCT et_wall) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS n_unique_opening_bars,
      min(tod) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS first_opening_tod,
      max(tod) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS last_opening_tod,
      max(coalesce(gap_seconds, 0)) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS max_opening_gap_seconds,
      count(DISTINCT symbol) FILTER (WHERE tod >= TIME '09:30:00' AND tod < TIME '10:00:00') AS n_opening_symbols,
      max(CASE WHEN tod=TIME '09:30:00' THEN open END) AS o0930,
      max(CASE WHEN tod=TIME '09:59:00' THEN close END) AS c0959,
      max(CASE WHEN tod=TIME '10:00:00' THEN open END) AS o1000,
      max(CASE WHEN tod=TIME '10:00:00' THEN high END) AS h1000,
      min(CASE WHEN tod=TIME '10:00:00' THEN low END) AS l1000,
      max(CASE WHEN tod=TIME '10:01:00' THEN open END) AS o1001,
      max(CASE WHEN tod=TIME '15:00:00' THEN open END) AS o1500,
      max(CASE WHEN tod=TIME '15:29:00' THEN close END) AS c1529,
      max(CASE WHEN tod=TIME '15:30:00' THEN open END) AS o1530,
      max(CASE WHEN tod=TIME '15:59:00' THEN close END) AS c1559,
      max(CASE WHEN tod=TIME '15:59:00' THEN high END) AS h1559,
      min(CASE WHEN tod=TIME '15:59:00' THEN low END) AS l1559,
      max(CASE WHEN tod=TIME '09:30:00' THEN symbol END) AS sym0930,
      max(CASE WHEN tod=TIME '09:59:00' THEN symbol END) AS sym0959,
      max(CASE WHEN tod=TIME '10:00:00' THEN symbol END) AS sym1000,
      max(CASE WHEN tod=TIME '15:00:00' THEN symbol END) AS sym1500,
      max(CASE WHEN tod=TIME '15:29:00' THEN symbol END) AS sym1529,
      max(CASE WHEN tod=TIME '15:30:00' THEN symbol END) AS sym1530,
      max(CASE WHEN tod=TIME '15:59:00' THEN symbol END) AS sym1559,
      max(CASE WHEN tod >= TIME '09:30:00' AND tod < TIME '10:00:00' THEN high END) AS high30,
      min(CASE WHEN tod >= TIME '09:30:00' AND tod < TIME '10:00:00' THEN low END) AS low30,
      sum(CASE WHEN tod >= TIME '09:30:00' AND tod < TIME '10:00:00' THEN volume ELSE 0 END) AS volume30,
      sqrt(sum(CASE WHEN tod >= TIME '09:30:00' AND tod < TIME '10:00:00'
                    THEN pow(CASE WHEN tod=TIME '09:30:00' THEN ln(close/open)
                                  ELSE coalesce(log_ret, 0) END, 2) ELSE 0 END)) AS rv30,
      sum(CASE WHEN tod >= TIME '09:30:00' AND tod < TIME '10:00:00'
               THEN abs(CASE WHEN tod=TIME '09:30:00' THEN ln(close/open)
                             ELSE coalesce(log_ret, 0) END) ELSE 0 END) AS path30
    FROM links
    GROUP BY session_date
    ORDER BY session_date
    """
    frame = duckdb.sql(query).df()
    frame["date"] = pd.to_datetime(frame["date"])

    calendar = condition_calendar().rename(columns={"date": "session_date"})
    frame = frame.merge(
        calendar[["session_date", "condition"]],
        left_on="date",
        right_on="session_date",
        how="left",
    ).drop(columns="session_date")
    frame["condition"] = frame["condition"].fillna("unknown")

    key_prices = [
        "o0930",
        "c0959",
        "o1000",
        "o1001",
        "o1500",
        "c1529",
        "o1530",
        "c1559",
    ]
    frame["complete"] = (
        frame["n_bars"].eq(390)
        & frame["n_unique_bars"].eq(390)
        & frame["first_tod"].astype(str).str.startswith("09:30:00")
        & frame["last_tod"].astype(str).str.startswith("15:59:00")
        & frame["max_gap_seconds"].le(60)
        & frame[key_prices].notna().all(axis=1)
    )
    frame["causal_opening_complete"] = (
        frame["n_opening_bars"].eq(30)
        & frame["n_unique_opening_bars"].eq(30)
        & frame["first_opening_tod"].astype(str).str.startswith("09:30:00")
        & frame["last_opening_tod"].astype(str).str.startswith("09:59:00")
        & frame["max_opening_gap_seconds"].le(60)
        & frame[["o0930", "c0959", "o1000"]].notna().all(axis=1)
        & frame["n_opening_symbols"].eq(1)
    )
    frame["available"] = frame["condition"].eq("available")
    expected = nyse_session_dates(frame["date"].min(), frame["date"].max())
    early_closes = nyse_early_close_dates(frame["date"].min(), frame["date"].max())
    previous_expected = pd.Series(expected[:-1], index=expected[1:])
    frame["expected_session"] = frame["date"].isin(expected)
    frame["scheduled_full_session"] = frame["expected_session"] & ~frame["date"].isin(early_closes)
    frame["prev_expected_date"] = frame["date"].map(previous_expected)
    by_date = frame.set_index("date")
    frame["prior_calendar_contiguous"] = frame["prev_expected_date"].isin(by_date.index)
    frame["prev_close"] = frame["prev_expected_date"].map(by_date["c1559"])
    frame["prev_symbol"] = frame["prev_expected_date"].map(by_date["sym1559"])
    frame["prev_complete"] = frame["prev_expected_date"].map(by_date["complete"]).fillna(False).astype(bool)
    frame["prev_available"] = frame["prev_expected_date"].map(by_date["available"]).fillna(False).astype(bool)
    frame["prev_endpoint_present"] = frame["prev_close"].notna() & frame["prev_symbol"].notna()
    frame["opening_same_contract"] = (
        frame["prev_symbol"].eq(frame["sym0930"])
        & frame["sym0930"].eq(frame["sym0959"])
        & frame["sym0959"].eq(frame["sym1000"])
        & frame["n_opening_symbols"].eq(1)
    )
    frame["same_contract"] = (
        frame["prev_symbol"].eq(frame["sym0930"])
        & frame["sym0930"].eq(frame["sym0959"])
        & frame["sym0959"].eq(frame["sym1000"])
        & frame["sym1000"].eq(frame["sym1530"])
        & frame["sym1530"].eq(frame["sym1559"])
        & frame["rth_roll_rows"].eq(0)
        & frame["n_rth_symbols"].eq(1)
    )
    frame["eligible"] = (
        frame["complete"]
        & frame["available"]
        & frame["prev_complete"]
        & frame["prev_available"]
        & frame["expected_session"]
        & frame["prior_calendar_contiguous"]
        & frame["same_contract"]
    )
    frame["causal_candidate"] = (
        frame["scheduled_full_session"]
        & frame["prior_calendar_contiguous"]
        & frame["prev_endpoint_present"]
        & frame["causal_opening_complete"]
        & frame["opening_same_contract"]
    )
    frame["causal_measurement_available"] = (
        frame["causal_candidate"] & frame["available"] & frame["prev_available"]
    )
    frame["instrument"] = instrument
    return frame


def eligible_sessions(instrument: str) -> pd.DataFrame:
    frame = session_summary(instrument)
    return frame.loc[frame["eligible"]].reset_index(drop=True)


def common_sessions(instruments: Iterable[str] = ("NQ", "ES")) -> dict[str, pd.DataFrame]:
    frames = {name.upper(): eligible_sessions(name) for name in instruments}
    common_dates: set[pd.Timestamp] | None = None
    for frame in frames.values():
        dates = set(frame["date"])
        common_dates = dates if common_dates is None else common_dates & dates
    if common_dates is None:
        return frames
    ordered = sorted(common_dates)
    return {
        name: frame.set_index("date").loc[ordered].reset_index()
        for name, frame in frames.items()
    }


@lru_cache(maxsize=2)
def one_second_execution(instrument: str) -> pd.DataFrame:
    """Extract attainable, latency-aware market-order price proxies.

    The 09:59 one-minute close is known at 10:00:00 ET.  The primary order is
    active one second later, at 10:00:01.  The liquidation order is scheduled
    in advance and active at 15:59:59.  For each timestamp we use the open of
    the first one-second OHLCV record at or after activation, then let the
    execution engine impose adverse slippage.
    """

    instrument = instrument.upper()
    if instrument not in ONE_SECOND_PATHS:
        raise KeyError(f"unsupported instrument: {instrument}")
    path = ONE_SECOND_PATHS[instrument]
    timestamp_column = "ts_utc" if instrument == "NQ" else "ts_event"
    symbol_expression = "symbol" if instrument == "NQ" else "CAST(instrument_id AS VARCHAR)"
    ts = timestamp_column
    tod = f"CAST(timezone('America/New_York', {ts}) AS TIME)"
    activations = {
        "entry_100000": ("10:00:00", "10:01:00"),
        "entry_100001": ("10:00:01", "10:01:00"),
        "entry_100002": ("10:00:02", "10:01:00"),
        "entry_100005": ("10:00:05", "10:01:00"),
        "entry_100030": ("10:00:30", "10:01:00"),
        "entry_100100": ("10:01:00", "10:02:00"),
        "entry_153000": ("15:30:00", "15:31:00"),
        "entry_153001": ("15:30:01", "15:31:00"),
        "exit_155958": ("15:59:58", "16:00:00"),
        "exit_155959": ("15:59:59", "16:00:00"),
        "exit_160000": ("16:00:00", "16:01:00"),
    }
    filters = " OR ".join(
        f"({tod} >= TIME '{start}' AND {tod} < TIME '{end}')"
        for start, end in activations.values()
    )
    aggregates: list[str] = []
    for label, (start, end) in activations.items():
        predicate = f"tod >= TIME '{start}' AND tod < TIME '{end}'"
        aggregates.extend(
            [
                f"min(event_ts) FILTER (WHERE {predicate}) AS {label}_ts",
                f"arg_min(open, event_ts) FILTER (WHERE {predicate}) AS {label}",
                f"arg_min(symbol, event_ts) FILTER (WHERE {predicate}) AS sym_{label}",
            ]
        )
    aggregate_sql = ",\n      ".join(aggregates)
    query = f"""
    WITH selected AS (
      SELECT
        CAST(timezone('America/New_York', {ts}) AS DATE) AS date,
        {ts} AS event_ts,
        {tod} AS tod,
        {symbol_expression} AS symbol,
        open
      FROM read_parquet('{_quoted_path(path)}')
      WHERE {filters}
    )
    SELECT
      date,
      {aggregate_sql}
    FROM selected
    GROUP BY date
    ORDER BY date
    """
    frame = duckdb.sql(query).df()
    frame["date"] = pd.to_datetime(frame["date"])
    for column in [name for name in frame.columns if name.endswith("_ts")]:
        frame[column] = pd.to_datetime(frame[column], utc=True)
    frame["instrument"] = instrument
    return frame


EXECUTION_CLOCKS = (
    "entry_100000",
    "entry_100001",
    "entry_100002",
    "entry_100005",
    "entry_100030",
    "entry_100100",
    "entry_153000",
    "entry_153001",
    "exit_155958",
    "exit_155959",
    "exit_160000",
)


def execution_sessions(
    instrument: str,
    required_clocks: Iterable[str] = ("entry_100001", "exit_155959"),
    *,
    strict_full_session: bool = False,
) -> pd.DataFrame:
    """Join one-minute sessions to only the fill clocks an arm requires."""

    instrument = instrument.upper()
    required_labels = tuple(required_clocks)
    unknown = sorted(set(required_labels) - set(EXECUTION_CLOCKS))
    if unknown or not required_labels:
        raise ValueError(f"invalid required execution clocks: {unknown}")
    daily = session_summary(instrument)
    daily = daily.loc[daily["causal_measurement_available"]].reset_index(drop=True)
    seconds = one_second_execution(instrument)
    frame = daily.merge(seconds.drop(columns="instrument"), on="date", how="left")
    for label in EXECUTION_CLOCKS:
        columns = [label, f"{label}_ts", f"sym_{label}"]
        frame[f"clock_available_{label}"] = frame[columns].notna().all(axis=1)
    price_columns = list(required_labels)
    timestamp_columns = [f"{label}_ts" for label in required_labels]
    symbol_columns = [f"sym_{label}" for label in required_labels]
    frame["one_second_complete"] = frame[price_columns + timestamp_columns + symbol_columns].notna().all(axis=1)
    frame["one_second_same_contract"] = frame[symbol_columns].eq(frame["sym1000"], axis=0).all(axis=1)
    # This is a post-run integrity assertion, not an ex-ante sample filter.  It
    # catches a switch-and-switch-back path that endpoint checks alone would
    # miss while ensuring the day cannot simply disappear from the sample.
    frame["held_session_same_contract"] = (
        frame["one_second_same_contract"]
        & frame["n_rth_symbols"].eq(1)
        & frame["rth_roll_rows"].eq(0)
    )
    frame["execution_eligible"] = frame["one_second_complete"] & frame["held_session_same_contract"]
    invalid = frame.loc[~frame["execution_eligible"]]
    if len(invalid):
        raise AssertionError(
            f"{instrument} has {len(invalid)} causal sessions with invalid required execution records"
        )
    if strict_full_session:
        frame = frame.loc[frame["complete"]]
    return frame.reset_index(drop=True)


def common_execution_sessions(
    instruments: Iterable[str] = ("NQ", "ES"),
    required_clocks: Iterable[str] = ("entry_100001", "exit_155959"),
    *,
    strict_full_session: bool = False,
) -> dict[str, pd.DataFrame]:
    frames = {
        name.upper(): execution_sessions(
            name,
            required_clocks=required_clocks,
            strict_full_session=strict_full_session,
        )
        for name in instruments
    }
    common_dates: set[pd.Timestamp] | None = None
    for frame in frames.values():
        dates = set(frame["date"])
        common_dates = dates if common_dates is None else common_dates & dates
    if common_dates is None:
        return frames
    ordered = sorted(common_dates)
    return {
        name: frame.set_index("date").loc[ordered].reset_index()
        for name, frame in frames.items()
    }


def raw_quality(instrument: str) -> dict[str, int | float | str]:
    """Run source-level invariants without loading the full archive into pandas."""

    instrument = instrument.upper()
    path = DATA_PATHS[instrument]
    query = f"""
      SELECT
        count(*) AS rows,
        count(DISTINCT ts_utc) AS unique_timestamps,
        sum(CASE WHEN open IS NULL OR high IS NULL OR low IS NULL OR close IS NULL
                      OR volume IS NULL OR symbol IS NULL OR is_roll IS NULL
                 THEN 1 ELSE 0 END) AS null_rows,
        sum(CASE WHEN open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                 THEN 1 ELSE 0 END) AS nonpositive_price_rows,
        sum(CASE WHEN high < low OR high < greatest(open, close)
                      OR low > least(open, close)
                 THEN 1 ELSE 0 END) AS invalid_ohlc_rows,
        sum(CASE WHEN volume <= 0 THEN 1 ELSE 0 END) AS nonpositive_volume_rows,
        min(ts_utc) AS first_ts,
        max(ts_utc) AS last_ts,
        sum(CASE WHEN is_roll THEN 1 ELSE 0 END) AS roll_rows
      FROM read_parquet('{_quoted_path(path)}')
    """
    row = duckdb.sql(query).df().iloc[0].to_dict()
    ordered = duckdb.sql(
        f"""
        WITH x AS (
          SELECT ts_utc, lag(ts_utc) OVER (ORDER BY ts_utc) AS prior
          FROM read_parquet('{_quoted_path(path)}')
        )
        SELECT sum(CASE WHEN prior IS NOT NULL AND ts_utc <= prior THEN 1 ELSE 0 END) AS bad
        FROM x
        """
    ).fetchone()[0]
    row["out_of_order_or_duplicate_rows"] = int(ordered or 0)
    row["instrument"] = instrument
    return {key: (value.item() if isinstance(value, np.generic) else value) for key, value in row.items()}


def one_second_raw_quality(instrument: str) -> dict[str, int | float | str]:
    """Source-level one-second invariants without loading records into pandas."""

    instrument = instrument.upper()
    if instrument not in ONE_SECOND_PATHS:
        raise KeyError(f"unsupported instrument: {instrument}")
    path = ONE_SECOND_PATHS[instrument]
    timestamp_column = "ts_utc" if instrument == "NQ" else "ts_event"
    extra_condition = (
        ", sum(CASE WHEN data_condition NOT IN ('available','unknown') THEN 1 ELSE 0 END) AS nonavailable_condition_rows"
        if instrument == "NQ"
        else ""
    )
    query = f"""
      SELECT
        count(*) AS rows,
        count(DISTINCT {timestamp_column}) AS unique_timestamps,
        sum(CASE WHEN {timestamp_column} IS NULL OR open IS NULL OR high IS NULL
                      OR low IS NULL OR close IS NULL OR volume IS NULL
                 THEN 1 ELSE 0 END) AS null_rows,
        sum(CASE WHEN open <= 0 OR high <= 0 OR low <= 0 OR close <= 0
                 THEN 1 ELSE 0 END) AS nonpositive_price_rows,
        sum(CASE WHEN high < low OR high < greatest(open, close)
                      OR low > least(open, close)
                 THEN 1 ELSE 0 END) AS invalid_ohlc_rows,
        sum(CASE WHEN volume <= 0 THEN 1 ELSE 0 END) AS nonpositive_volume_rows,
        min({timestamp_column}) AS first_ts,
        max({timestamp_column}) AS last_ts
        {extra_condition}
      FROM read_parquet('{_quoted_path(path)}')
    """
    row = duckdb.sql(query).df().iloc[0].to_dict()
    ordered = duckdb.sql(
        f"""
        WITH x AS (
          SELECT {timestamp_column} AS ts,
                 lag({timestamp_column}) OVER (ORDER BY {timestamp_column}) AS prior
          FROM read_parquet('{_quoted_path(path)}')
        )
        SELECT sum(CASE WHEN prior IS NOT NULL AND ts <= prior THEN 1 ELSE 0 END) AS bad
        FROM x
        """
    ).fetchone()[0]
    row["out_of_order_or_duplicate_rows"] = int(ordered or 0)
    row["instrument"] = instrument
    return {key: (value.item() if isinstance(value, np.generic) else value) for key, value in row.items()}


def session_funnel(instrument: str) -> dict[str, int]:
    frame = session_summary(instrument)
    expected = nyse_session_dates(frame["date"].min(), frame["date"].max())
    return {
        "expected_exchange_sessions": int(len(expected)),
        "represented_sessions": int(len(frame)),
        "missing_exchange_sessions": int(len(set(expected) - set(frame["date"]))),
        "unexpected_represented_dates": int((~frame["expected_session"]).sum()),
        "scheduled_full_sessions": int(frame["scheduled_full_session"].sum()),
        "causal_opening_complete_sessions": int(frame["causal_opening_complete"].sum()),
        "causal_candidates": int(frame["causal_candidate"].sum()),
        "causal_measurement_available_sessions": int(frame["causal_measurement_available"].sum()),
        "complete_sessions": int(frame["complete"].sum()),
        "available_complete_sessions": int((frame["complete"] & frame["available"]).sum()),
        "prior_complete_available_sessions": int(
            (
                frame["complete"]
                & frame["available"]
                & frame["prev_complete"]
                & frame["prev_available"]
                & frame["prior_calendar_contiguous"]
            ).sum()
        ),
        "roll_safe_sessions": int(frame["same_contract"].sum()),
        "eligible_sessions": int(frame["eligible"].sum()),
        "degraded_complete_sessions": int((frame["complete"] & ~frame["available"]).sum()),
        "roll_exclusions": int(
            (frame["complete"] & frame["available"] & frame["prev_complete"] & frame["prev_available"] & ~frame["same_contract"]).sum()
        ),
    }
