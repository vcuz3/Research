"""Audited fixed-horizon execution for one-contract intraday strategies."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

import numpy as np
import pandas as pd

from .data import INSTRUMENT_SPECS


@dataclass(frozen=True)
class CostProfile:
    slippage_ticks_per_side: float = 1.0
    round_trip_fees_usd: float = 4.5

    def __post_init__(self) -> None:
        if self.slippage_ticks_per_side < 0 or self.round_trip_fees_usd < 0:
            raise ValueError("cost assumptions must be non-negative")


def _clock(value: str) -> time:
    try:
        return time.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"invalid ET clock: {value}") from exc


def _activation(dates: pd.Series, clock: str) -> pd.Series:
    wall = pd.to_datetime(pd.to_datetime(dates).dt.strftime("%Y-%m-%d") + " " + clock)
    return wall.dt.tz_localize("America/New_York")


def _side_series(sides: pd.Series | np.ndarray | list[float], index: pd.Index) -> pd.Series:
    if isinstance(sides, pd.Series):
        if not sides.index.equals(index):
            raise ValueError("side Series index must exactly match session index")
        raw = pd.to_numeric(sides, errors="coerce")
    else:
        values = np.asarray(sides)
        if len(values) != len(index):
            raise ValueError("one side is required for every eligible session")
        raw = pd.Series(pd.to_numeric(values, errors="coerce"), index=index)
    if len(raw) != len(index):
        raise ValueError("one side is required for every eligible session")
    if not np.isfinite(raw.to_numpy(dtype=float)).all() or not raw.isin([-1, 0, 1]).all():
        raise ValueError("sides must be finite exact values -1, 0, or 1")
    return raw.astype("int8")


def run_fixed_schedule(
    sessions: pd.DataFrame,
    sides: pd.Series | np.ndarray | list[float],
    *,
    instrument: str,
    entry_column: str,
    exit_column: str,
    decision_time_et: str,
    entry_time_et: str,
    exit_time_et: str,
    costs: CostProfile = CostProfile(),
    strategy_name: str = "strategy",
    entry_timestamp_column: str | None = None,
    exit_timestamp_column: str | None = None,
    entry_symbol_column: str | None = None,
    exit_symbol_column: str | None = None,
    extra_symbol_columns: tuple[str, ...] = (),
    allow_zero_latency: bool = False,
    max_fill_delay_seconds: float = 61.0,
) -> pd.DataFrame:
    """Execute one audited entry and pre-scheduled exit per selected session.

    Price columns are inseparable from their actual one-second event timestamps
    and contract symbols. Metadata strings therefore cannot turn an unavailable
    bar price into a legal fill.
    """

    instrument = instrument.upper()
    if instrument not in INSTRUMENT_SPECS:
        raise KeyError(f"unsupported instrument: {instrument}")
    if not sessions.index.is_unique:
        raise ValueError("session index must be unique")
    required = {"date", entry_column, exit_column}
    entry_timestamp_column = entry_timestamp_column or f"{entry_column}_ts"
    exit_timestamp_column = exit_timestamp_column or f"{exit_column}_ts"
    entry_symbol_column = entry_symbol_column or f"sym_{entry_column}"
    exit_symbol_column = exit_symbol_column or f"sym_{exit_column}"
    required.update(
        {
            entry_timestamp_column,
            exit_timestamp_column,
            "prev_symbol",
            "sym0930",
            "sym0959",
            entry_symbol_column,
            exit_symbol_column,
            *extra_symbol_columns,
        }
    )
    missing = sorted(required - set(sessions.columns))
    if missing:
        raise ValueError(f"entry, exit, timestamp, or symbol column missing: {missing}")

    dates = pd.to_datetime(sessions["date"])
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("sessions must have unique chronological dates")
    side = _side_series(sides, sessions.index)
    traded = side.ne(0)

    decision_clock, entry_clock, exit_clock = map(
        _clock, (decision_time_et, entry_time_et, exit_time_et)
    )
    causal_entry = decision_clock < entry_clock or (allow_zero_latency and decision_clock == entry_clock)
    if not causal_entry or not entry_clock < exit_clock:
        raise ValueError("ET clocks must satisfy decision < entry < exit (or explicit zero-latency bound)")

    entry = pd.to_numeric(sessions[entry_column], errors="coerce")
    exit_price = pd.to_numeric(sessions[exit_column], errors="coerce")
    if (~np.isfinite(entry[traded])).any() or (~np.isfinite(exit_price[traded])).any():
        raise ValueError("traded entry and exit prices must be finite")
    if (entry[traded] <= 0).any() or (exit_price[traded] <= 0).any():
        raise ValueError("traded prices must be positive")

    entry_ts = pd.to_datetime(sessions[entry_timestamp_column], utc=True, errors="coerce")
    exit_ts = pd.to_datetime(sessions[exit_timestamp_column], utc=True, errors="coerce")
    if entry_ts[traded].isna().any() or exit_ts[traded].isna().any():
        raise ValueError("traded event timestamps must be finite and timezone-aware")
    entry_et = entry_ts.dt.tz_convert("America/New_York")
    exit_et = exit_ts.dt.tz_convert("America/New_York")
    entry_active = _activation(dates, entry_time_et)
    exit_active = _activation(dates, exit_time_et)
    entry_delay = (entry_et - entry_active).dt.total_seconds()
    exit_delay = (exit_et - exit_active).dt.total_seconds()
    if (entry_et[traded].dt.normalize().dt.tz_localize(None) != dates[traded].dt.normalize()).any():
        raise ValueError("entry fill ET date must equal the session date")
    if (exit_et[traded].dt.normalize().dt.tz_localize(None) != dates[traded].dt.normalize()).any():
        raise ValueError("exit fill ET date must equal the session date")
    if (entry_delay[traded] < 0).any() or (exit_delay[traded] < 0).any():
        raise ValueError("fill timestamp precedes declared activation")
    if (entry_delay[traded] >= max_fill_delay_seconds).any() or (exit_delay[traded] >= max_fill_delay_seconds).any():
        raise ValueError("fill timestamp exceeds declared activation window")
    if (exit_ts[traded].array <= entry_ts[traded].array).any():
        raise ValueError("actual exit timestamp must be after actual entry timestamp")

    symbol_columns = [
        "prev_symbol",
        "sym0930",
        "sym0959",
        *extra_symbol_columns,
        entry_symbol_column,
        exit_symbol_column,
    ]
    symbols = sessions[symbol_columns].astype("string")
    if symbols.loc[traded].isna().any().any():
        raise ValueError("traded contract symbols must be present")
    if not symbols.loc[traded].eq(symbols.loc[traded, "sym0930"], axis=0).all().all():
        raise ValueError("traded feature and fill endpoints must share one contract symbol")

    spec = INSTRUMENT_SPECS[instrument]
    adverse_points = costs.slippage_ticks_per_side * spec.tick_size
    entry_fill = (entry + side * adverse_points).where(traded)
    exit_fill = (exit_price - side * adverse_points).where(traded)
    gross_points = pd.Series(
        np.where(traded, side * (exit_price - entry), 0.0), index=sessions.index, dtype=float
    )
    slippage_points = traded.astype(float) * 2.0 * adverse_points
    net_points_before_fees = pd.Series(
        np.where(traded, side * (exit_fill - entry_fill), 0.0), index=sessions.index, dtype=float
    )
    gross_dollars = gross_points * spec.multiplier
    slippage_dollars = slippage_points * spec.multiplier
    fees_dollars = traded.astype(float) * costs.round_trip_fees_usd
    net_dollars = gross_dollars - slippage_dollars - fees_dollars
    notional = entry * spec.multiplier
    gross_bps = pd.Series(np.where(traded, 10_000.0 * gross_dollars / notional, 0.0), index=sessions.index)
    net_bps = pd.Series(np.where(traded, 10_000.0 * net_dollars / notional, 0.0), index=sessions.index)

    out = pd.DataFrame(
        {
            "date": dates.to_numpy(),
            "instrument": instrument,
            "strategy": strategy_name,
            "side": side.to_numpy(),
            "trade": traded.to_numpy(),
            "entry_raw": entry.to_numpy(),
            "exit_raw": exit_price.to_numpy(),
            "entry_fill": entry_fill.to_numpy(),
            "exit_fill": exit_fill.to_numpy(),
            "entry_event_ts_utc": entry_ts.to_numpy(),
            "exit_event_ts_utc": exit_ts.to_numpy(),
            "entry_latency_seconds": entry_delay.to_numpy(),
            "exit_latency_seconds": exit_delay.to_numpy(),
            "gross_points": gross_points.to_numpy(),
            "slippage_points": slippage_points.to_numpy(),
            "net_points_before_fees": net_points_before_fees.to_numpy(),
            "gross_dollars": gross_dollars.to_numpy(),
            "slippage_dollars": slippage_dollars.to_numpy(),
            "fees_dollars": fees_dollars.to_numpy(),
            "net_dollars": net_dollars.to_numpy(),
            "gross_bps": gross_bps.to_numpy(),
            "net_bps": net_bps.to_numpy(),
            "decision_time_et": decision_time_et,
            "entry_time_et": entry_time_et,
            "exit_time_et": exit_time_et,
            "entry_column": entry_column,
            "exit_column": exit_column,
            "entry_timestamp_column": entry_timestamp_column,
            "exit_timestamp_column": exit_timestamp_column,
            "slippage_ticks_per_side": float(costs.slippage_ticks_per_side),
            "round_trip_fees_usd": float(costs.round_trip_fees_usd),
        }
    )
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
    if not np.isfinite(out[zero_columns].to_numpy(dtype=float)).all():
        raise AssertionError("PnL output must be finite")
    if not (out.loc[~out["trade"], zero_columns] == 0).all().all():
        raise AssertionError("flat sessions must have zero PnL and cost")
    return out.reset_index(drop=True)
