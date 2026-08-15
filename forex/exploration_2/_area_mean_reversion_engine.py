"""Causal same-slot area bands and fixed-horizon mean-reversion entries."""

from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import deque
from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class AreaConfig:
    window: str = "90D"
    min_observations: int = 40
    upper_quantile: float = 0.90
    lower_quantile: float = 0.10
    holding_minutes: int = 60
    checkpoint_minutes: int = 30
    spread_pips: float = 0.0
    slippage_per_side_pips: float = 0.0
    commission_round_trip_pips: float = 0.0
    pip_size: float = 0.0001

    @property
    def total_cost_pips(self) -> float:
        return (
            self.spread_pips
            + 2 * self.slippage_per_side_pips
            + self.commission_round_trip_pips
        )


TRADE_COLUMNS = [
    "variant", "session_date", "breach", "direction", "signal_bar_open",
    "decision_time", "entry_time", "exit_time", "entry_price", "exit_price",
    "gross_log_return", "gross_pips", "net_pips", "holding_minutes",
]


def build_area_bands(bars: pd.DataFrame, config: AreaConfig) -> pd.DataFrame:
    """Build causal same-session-slot signed-quantile bands.

    ``bars`` is the output of ``_bollinger_engine.load_five_minute_bars``.
    Every OHLC row is retained. Band values remain NaN until enough prior
    observations exist at that exact New-York FX-session slot.
    """
    required = {
        "bar_open", "open", "high", "low", "close", "complete_5m",
        "session_date", "session_id", "session_slot",
    }
    missing = required.difference(bars.columns)
    if missing:
        raise ValueError(f"Missing bar columns: {sorted(missing)}")
    if not 0 < config.lower_quantile < config.upper_quantile < 1:
        raise ValueError("Require 0 < lower_quantile < upper_quantile < 1")

    f = bars.copy().sort_values("bar_open", kind="stable").reset_index(drop=True)
    valid = f.complete_5m & f[["open", "high", "low", "close"]].notna().all(axis=1)
    f["valid_bar"] = valid
    f["session_open_price"] = (
        f.open.where(valid).groupby(f.session_id, sort=False).transform("first")
    )
    f["cum_log_ret"] = np.log(f.close / f.session_open_price).where(valid)

    upper = np.full(len(f), np.nan)
    lower = np.full(len(f), np.nan)
    abs_percentile = np.full(len(f), np.nan)
    observations = np.zeros(len(f), dtype=np.int16)
    window = pd.Timedelta(config.window)
    window_ns = int(window.value)
    bar_open_ns = pd.DatetimeIndex(f.bar_open).asi8
    cum_values = f.cum_log_ret.to_numpy(float)

    for indices in f.groupby("session_slot", sort=False).groups.values():
        positions = np.asarray(indices, dtype=np.int64)
        slot = pd.Series(
            f.cum_log_ret.iloc[positions].to_numpy(float),
            index=pd.DatetimeIndex(f.bar_open.iloc[positions]),
        )
        rolling = slot.rolling(
            window, min_periods=config.min_observations, closed="left"
        )
        upper[positions] = rolling.quantile(config.upper_quantile).to_numpy()
        lower[positions] = rolling.quantile(config.lower_quantile).to_numpy()
        observations[positions] = (
            slot.rolling(window, min_periods=1, closed="left").count()
            .fillna(0).clip(upper=np.iinfo(np.int16).max).to_numpy(np.int16)
        )

        # Percentile of the current absolute move versus only the prior 90D
        # same-slot history. This supports a simple symmetric large-move control
        # without recomputing many rolling quantile bands.
        history: deque[tuple[int, float]] = deque()
        sorted_values: list[float] = []
        for position in positions:
            timestamp = int(bar_open_ns[position])
            cutoff = timestamp - window_ns
            while history and history[0][0] <= cutoff:
                _, old_value = history.popleft()
                old_at = bisect_left(sorted_values, old_value)
                sorted_values.pop(old_at)
            current = cum_values[position]
            if np.isfinite(current) and len(sorted_values) >= config.min_observations:
                abs_percentile[position] = bisect_right(sorted_values, abs(current)) / len(sorted_values)
            if np.isfinite(current):
                current_abs = abs(float(current))
                history.append((timestamp, current_abs))
                insort(sorted_values, current_abs)

    f["upper_log_band"] = upper
    f["lower_log_band"] = lower
    f["band_observations"] = observations
    f["abs_move_percentile"] = abs_percentile
    f["upper_band"] = f.session_open_price * np.exp(f.upper_log_band)
    f["lower_band"] = f.session_open_price * np.exp(f.lower_log_band)
    f["band_ready"] = valid & f[["upper_band", "lower_band"]].notna().all(axis=1)
    f["breach_side"] = np.select(
        [f.band_ready & f.close.gt(f.upper_band), f.band_ready & f.close.lt(f.lower_band)],
        [1, -1], default=0,
    ).astype("int8")
    return f


def _trade_from_signal(
    frame: pd.DataFrame,
    signal_index: int,
    variant: str,
    config: AreaConfig,
    timestamp_to_index: dict[pd.Timestamp, int],
    breach_side: int | None = None,
) -> dict | None:
    signal = frame.iloc[signal_index]
    decision_time = signal.bar_open + pd.Timedelta(minutes=5)
    entry_index = timestamp_to_index.get(decision_time)
    if entry_index is None or not bool(frame.complete_5m.iloc[entry_index]):
        return None
    exit_time = decision_time + pd.Timedelta(minutes=config.holding_minutes)
    exit_index = timestamp_to_index.get(exit_time)
    if exit_index is None or not bool(frame.complete_5m.iloc[exit_index]):
        return None

    entry_price = float(frame.open.iloc[entry_index])
    exit_price = float(frame.open.iloc[exit_index])
    breach_side = int(signal.breach_side if breach_side is None else breach_side)
    direction = -breach_side               # fade: short upper, long lower
    gross_log_return = direction * float(np.log(exit_price / entry_price))
    gross_pips = gross_log_return / config.pip_size
    return {
        "variant": variant,
        "session_date": signal.session_date,
        "breach": "upper" if breach_side == 1 else "lower",
        "direction": "short" if direction == -1 else "long",
        "signal_bar_open": signal.bar_open,
        "decision_time": decision_time,
        "entry_time": frame.bar_open.iloc[entry_index],
        "exit_time": frame.bar_open.iloc[exit_index],
        "entry_price": entry_price,
        "exit_price": exit_price,
        "gross_log_return": gross_log_return,
        "gross_pips": gross_pips,
        "net_pips": gross_pips - config.total_cost_pips,
        "holding_minutes": config.holding_minutes,
    }


def _trades_frame(records: list[dict]) -> pd.DataFrame:
    out = pd.DataFrame.from_records(records, columns=TRADE_COLUMNS)
    if not out.empty:
        out = out.sort_values("entry_time", kind="stable").reset_index(drop=True)
        out["year"] = pd.to_datetime(out.session_date).dt.year
    return out


def first_cross_per_session(
    frame: pd.DataFrame,
    config: AreaConfig,
    side_column: str = "breach_side",
    ready_column: str = "band_ready",
    variant: str = "first_cross",
) -> pd.DataFrame:
    """Take the first inside-to-outside crossing that produces a valid trade per session."""
    f = frame.reset_index(drop=True)
    prior_inside = f[ready_column].shift(fill_value=False) & f[side_column].shift().eq(0)
    same_session = f.session_id.eq(f.session_id.shift())
    consecutive = f.bar_open.diff().eq(pd.Timedelta(minutes=5))
    candidates = np.flatnonzero(
        f[side_column].ne(0).to_numpy() & f[ready_column].to_numpy() & prior_inside.to_numpy()
        & same_session.to_numpy() & consecutive.to_numpy()
    )
    lookup = {timestamp: i for i, timestamp in enumerate(f.bar_open)}
    used_sessions: set[int] = set()
    records: list[dict] = []
    for i in candidates:
        session_id = int(f.session_id.iloc[i])
        if session_id in used_sessions:
            continue
        trade = _trade_from_signal(
            f, i, variant, config, lookup, breach_side=int(f[side_column].iloc[i])
        )
        if trade is not None:
            records.append(trade)
            used_sessions.add(session_id)
    return _trades_frame(records)


def checkpoint_while_flat(frame: pd.DataFrame, config: AreaConfig) -> pd.DataFrame:
    """Check completed bars every N minutes and enter only while flat.

    A checkpoint is based on the completed bar close at ``decision_time``. Entry
    is the open at that same boundary. A position exiting at the checkpoint open
    is considered flat and may be replaced by a new trade.
    """
    if config.checkpoint_minutes <= 0 or 60 % config.checkpoint_minutes:
        raise ValueError("checkpoint_minutes must be a positive divisor of 60")
    f = frame.reset_index(drop=True)
    ny_decision = (f.bar_open + pd.Timedelta(minutes=5)).dt.tz_convert("America/New_York")
    checkpoint = ny_decision.dt.minute.mod(config.checkpoint_minutes).eq(0)
    candidates = np.flatnonzero(checkpoint.to_numpy() & f.breach_side.ne(0).to_numpy())
    lookup = {timestamp: i for i, timestamp in enumerate(f.bar_open)}
    open_until: pd.Timestamp | None = None
    records: list[dict] = []
    for i in candidates:
        decision_time = f.bar_open.iloc[i] + pd.Timedelta(minutes=5)
        if open_until is not None and decision_time < open_until:
            continue
        trade = _trade_from_signal(f, i, "checkpoint_30m", config, lookup)
        if trade is not None:
            records.append(trade)
            open_until = trade["exit_time"]
    return _trades_frame(records)


def matched_large_move_control(
    frame: pd.DataFrame,
    config: AreaConfig,
    target_trades: int,
) -> tuple[pd.DataFrame, float]:
    """Symmetric same-slot magnitude control matched to primary trade count.

    Matching uses signal count only, never P&L. The control preserves the causal
    same-slot history and destroys only upper/lower distributional asymmetry.
    """
    f = frame.copy()
    f["control_ready"] = f.valid_bar & f.abs_move_percentile.notna()
    complete_times = set(f.loc[f.complete_5m, "bar_open"])
    decision = f.bar_open + pd.Timedelta(minutes=5)
    executable = decision.isin(complete_times) & (
        decision + pd.Timedelta(minutes=config.holding_minutes)
    ).isin(complete_times)
    session_max = (
        f.loc[f.control_ready & executable]
        .groupby("session_id", sort=False).abs_move_percentile.max()
        .sort_values(ascending=False)
    )
    if session_max.empty:
        return pd.DataFrame(columns=TRADE_COLUMNS), np.nan
    desired_rank = min(max(target_trades, 1), len(session_max))
    best_trades = pd.DataFrame(columns=TRADE_COLUMNS)
    best_threshold = np.nan
    best_difference = np.inf
    # A session maximum can begin outside rather than cross from inside. Adjust
    # the rank for that small shortfall; four count-only iterations normally
    # match exactly or within the percentile ties.
    for _ in range(4):
        rank = min(max(desired_rank, 1), len(session_max)) - 1
        threshold = float(session_max.iloc[rank])
        f["control_side"] = np.select(
            [
                f.control_ready & f.abs_move_percentile.ge(threshold) & f.cum_log_ret.gt(0),
                f.control_ready & f.abs_move_percentile.ge(threshold) & f.cum_log_ret.lt(0),
            ],
            [1, -1], default=0,
        ).astype("int8")
        trades = first_cross_per_session(
            f, config, side_column="control_side", ready_column="control_ready",
            variant="large_move_control",
        )
        difference = abs(len(trades) - target_trades)
        if difference < best_difference:
            best_trades, best_threshold, best_difference = trades, threshold, difference
        if difference == 0:
            break
        desired_rank += target_trades - len(trades)
    best_trades["control_percentile_threshold"] = best_threshold
    return best_trades, float(best_threshold)


def add_forward_horizons(
    frame: pd.DataFrame,
    trades: pd.DataFrame,
    config: AreaConfig,
    horizons: tuple[int, ...] = (15, 30, 60, 120),
) -> pd.DataFrame:
    """Attach exact open-to-open direction-adjusted returns for each horizon."""
    out = trades.copy()
    price_at = frame.set_index("bar_open").open.to_dict()
    direction = out.direction.map({"long": 1.0, "short": -1.0})
    for horizon in horizons:
        exit_times = out.entry_time + pd.Timedelta(minutes=horizon)
        exit_prices = exit_times.map(price_at)
        gross = direction * np.log(exit_prices / out.entry_price) / config.pip_size
        out[f"exit_price_{horizon}m"] = exit_prices
        out[f"gross_pips_{horizon}m"] = gross
        out[f"net_pips_{horizon}m"] = gross - config.total_cost_pips
    return out


def run_variants(
    frame: pd.DataFrame,
    config: AreaConfig,
    horizons: tuple[int, ...] = (15, 30, 60, 120),
) -> pd.DataFrame:
    primary = first_cross_per_session(frame, config)
    checkpoint = checkpoint_while_flat(frame, config)
    control, threshold = matched_large_move_control(frame, config, len(primary))
    out = pd.concat([primary, checkpoint, control], ignore_index=True)
    out = out.sort_values(["variant", "entry_time"], kind="stable").reset_index(drop=True)
    out = add_forward_horizons(frame, out, config, horizons)
    out.attrs["control_percentile_threshold"] = threshold
    out.attrs["primary_trade_count"] = len(primary)
    out.attrs["control_trade_count"] = len(control)
    return out


def trade_summary(trades: pd.DataFrame) -> pd.DataFrame:
    """Trade-level description plus implementable daily P&L aggregation."""
    rows = []
    for keys, group in trades.groupby(["variant", "breach"], sort=False):
        daily = group.groupby("session_date", sort=False).net_pips.sum()
        rows.append({
            "variant": keys[0], "breach": keys[1], "trades": len(group),
            "sessions": group.session_date.nunique(),
            "gross_mean_pips": group.gross_pips.mean(),
            "net_mean_pips": group.net_pips.mean(),
            "win_rate_net": group.net_pips.gt(0).mean(),
            "daily_mean_net_pips": daily.mean(),
            "daily_std_net_pips": daily.std(ddof=1),
        })
    return pd.DataFrame(rows)
