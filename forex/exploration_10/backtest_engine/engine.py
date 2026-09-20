"""One-position event engine with minute-grain bracket replay."""
from __future__ import annotations

from dataclasses import dataclass, asdict

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class Trade:
    asset: str
    side: int
    signal_time: pd.Timestamp
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    signal_atr: float
    stop_price: float
    target_price: float
    exit_reason: str
    gross_pips: float
    gross_r: float
    holding_minutes: float


def _first_barrier_arrays(
    o: np.ndarray,
    h: np.ndarray,
    l: np.ndarray,
    start: int,
    end: int,
    side: int,
    stop: float,
    target: float,
    scheduled_global_index: int | None,
) -> tuple[int, float, str] | None:
    """Vectorised first bracket exit; scheduled bar checks opening gaps only."""
    oo, hh, ll = o[start:end], h[start:end], l[start:end]
    if not len(oo):
        return None
    if side == 1:
        gap_stop = oo <= stop
        gap_target = oo >= target
        bar_stop = ll <= stop
        bar_target = hh >= target
    else:
        gap_stop = oo >= stop
        gap_target = oo <= target
        bar_stop = hh >= stop
        bar_target = ll <= target
    if scheduled_global_index is not None and start <= scheduled_global_index < end:
        scheduled_local = scheduled_global_index - start
        bar_stop[scheduled_local:] = False
        bar_target[scheduled_local:] = False

    def first(mask: np.ndarray) -> int | None:
        hits = np.flatnonzero(mask)
        return int(hits[0]) if len(hits) else None

    gs, gt, bs, bt = map(first, (gap_stop, gap_target, bar_stop, bar_target))
    candidates = []
    if gs is not None:
        candidates.append((gs, 0, float(oo[gs]), "stop_gap"))
    if gt is not None:
        candidates.append((gt, 1, target, "target"))
    if bs is not None:
        reason = "stop_ambiguous" if bt == bs else "stop"
        candidates.append((bs, 2, stop, reason))
    if bt is not None:
        candidates.append((bt, 3, target, "target"))
    if not candidates:
        return None
    local_i, _, price, reason = min(candidates)
    return start + local_i, price, reason


def simulate_asset(
    asset: str,
    minute_bars: pd.DataFrame,
    signal_bars: pd.DataFrame,
    stop_atr: float,
    target_atr: float,
    max_holding_hours: float,
    pip_size: float = 0.0001,
) -> pd.DataFrame:
    """Simulate causal fills for one asset, with no overlapping positions."""
    if stop_atr <= 0 or target_atr <= 0 or max_holding_hours <= 0 or pip_size <= 0:
        raise ValueError("stop_atr, target_atr, max_holding_hours and pip_size must be positive")
    required = {"open", "high", "low", "close"}
    if required - set(minute_bars.columns):
        raise ValueError("minute bars require open/high/low/close")
    if minute_bars.index.has_duplicates or not minute_bars.index.is_monotonic_increasing:
        raise ValueError("minute timestamps must be unique and sorted")

    signals = signal_bars.loc[signal_bars["signal"].ne(0),
                              ["decision_time", "signal", "atr"]].dropna().copy()
    signals = signals.sort_values("decision_time").reset_index(names="signal_time")
    minute_index = minute_bars.index
    signal_times = signals["decision_time"].to_numpy(dtype="datetime64[ns]")
    signal_source_times = pd.DatetimeIndex(signals["signal_time"])
    signal_sides = signals["signal"].to_numpy(np.int8)
    signal_atrs = signals["atr"].to_numpy(float)
    minute_open = minute_bars["open"].to_numpy(float)
    minute_high = minute_bars["high"].to_numpy(float)
    minute_low = minute_bars["low"].to_numpy(float)
    minute_close = minute_bars["close"].to_numpy(float)
    records: list[Trade] = []
    s = 0
    while s < len(signals):
        decision_time = pd.Timestamp(signal_times[s])
        entry_i = int(minute_index.searchsorted(decision_time, side="left"))
        if entry_i >= len(minute_bars):
            break
        entry_time = minute_index[entry_i]
        side = int(signal_sides[s])
        atr = float(signal_atrs[s])
        entry = float(minute_open[entry_i])
        stop = entry - side * stop_atr * atr
        target = entry + side * target_atr * atr

        # First later signal that opposes the held position.
        opp_s = s + 1
        while opp_s < len(signals) and int(signal_sides[opp_s]) == side:
            opp_s += 1
        opposite_time = (pd.Timestamp(signal_times[opp_s])
                         if opp_s < len(signals) else pd.Timestamp.max)
        deadline = entry_time + pd.Timedelta(hours=max_holding_hours)
        scheduled_time = min(opposite_time, deadline)
        scheduled_i = int(minute_index.searchsorted(scheduled_time, side="left"))
        has_scheduled_bar = scheduled_i < len(minute_bars)
        final_i = scheduled_i if has_scheduled_bar else len(minute_bars) - 1
        barrier = _first_barrier_arrays(
            minute_open, minute_high, minute_low, entry_i, final_i + 1,
            side, stop, target, scheduled_i if has_scheduled_bar else None)

        if barrier is not None:
            exit_i, exit_price, reason = barrier
        elif has_scheduled_bar:
            exit_i = scheduled_i
            exit_price = float(minute_open[exit_i])
            reason = "opposite_signal" if opposite_time <= deadline else "time"
        else:
            exit_i = len(minute_bars) - 1
            exit_price = float(minute_close[exit_i])
            reason = "end_of_data"

        exit_time = minute_index[exit_i]
        gross_price = side * (exit_price - entry)
        risk_price = stop_atr * atr
        records.append(Trade(
            asset=asset, side=side, signal_time=signal_source_times[s],
            entry_time=entry_time, exit_time=exit_time, entry_price=entry,
            exit_price=float(exit_price), signal_atr=atr, stop_price=stop,
            target_price=target, exit_reason=reason,
            gross_pips=gross_price / pip_size, gross_r=gross_price / risk_price,
            holding_minutes=(exit_time - entry_time) / pd.Timedelta(minutes=1),
        ))
        # Signals whose decisions occurred at or before exit cannot be acted on later.
        s = int(np.searchsorted(signal_times, np.datetime64(exit_time), side="right"))

    columns = list(Trade.__dataclass_fields__)
    return pd.DataFrame([asdict(t) for t in records], columns=columns)


def add_costs(trades: pd.DataFrame, round_trip_cost_pips: float, pip_size: float = 0.0001) -> pd.DataFrame:
    """Deduct one round-trip cost from each completed trade."""
    result = trades.copy()
    result["cost_pips"] = float(round_trip_cost_pips)
    result["net_pips"] = result["gross_pips"] - result["cost_pips"]
    risk_pips = (result["entry_price"] - result["stop_price"]).abs() / pip_size
    result["net_r"] = result["gross_r"] - result["cost_pips"] / risk_pips
    return result


def summarize(trades: pd.DataFrame, value_col: str = "gross_r") -> dict[str, float | int]:
    """Trade-level metrics; daily portfolio metrics are produced by the runner."""
    x = trades[value_col].astype(float)
    wins = x[x > 0].sum()
    losses = -x[x < 0].sum()
    return {
        "trades": int(len(x)),
        "mean": float(x.mean()) if len(x) else np.nan,
        "median": float(x.median()) if len(x) else np.nan,
        "win_rate": float((x > 0).mean()) if len(x) else np.nan,
        "profit_factor": float(wins / losses) if losses > 0 else np.nan,
        "total": float(x.sum()),
    }
