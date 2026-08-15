"""Stateful next-bar translation of the supplied Pine triangular strategy."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd


@dataclass
class Position:
    side: int
    signal_ts: pd.Timestamp
    signal_z: float
    signal_close: float
    atr: float
    stop: float | None
    target: float | None
    entry_ts: pd.Timestamp
    entry_price: float
    entry_cost: float
    entry_bar_number: int


def _order_cost(price: float, quantity: float, commission_percent: float) -> float:
    return abs(quantity) * price * commission_percent / 100.0


def _exit_trade(
    position: Position,
    exit_ts: pd.Timestamp,
    exit_price: float,
    reason: str,
    quantity: float,
    commission_percent: float,
    exit_bar_number: int,
) -> dict[str, object]:
    gross = position.side * quantity * (exit_price - position.entry_price)
    exit_cost = _order_cost(exit_price, quantity, commission_percent)
    total_cost = position.entry_cost + exit_cost
    return {
        "signal_ts": position.signal_ts,
        "entry_ts": position.entry_ts,
        "exit_ts": exit_ts,
        "side": position.side,
        "signal_z": position.signal_z,
        "signal_close": position.signal_close,
        "atr": position.atr,
        "stop": position.stop,
        "target": position.target,
        "entry_price": position.entry_price,
        "exit_price": exit_price,
        "exit_reason": reason,
        "bars_held": exit_bar_number - position.entry_bar_number + 1,
        "gross_pnl_usd": gross,
        "cost_usd": total_cost,
        "net_pnl_usd": gross - total_cost,
        "gross_return_bps": position.side * np.log(exit_price / position.entry_price) * 10_000,
    }


def _bracket_fill(position: Position, minute: pd.Series) -> tuple[float, str] | None:
    if position.stop is None or position.target is None:
        return None
    open_, high, low = float(minute["open"]), float(minute["high"]), float(minute["low"])
    if position.side > 0:
        stop_hit, target_hit = low <= position.stop, high >= position.target
        if stop_hit:  # adverse priority when the one-minute path is ambiguous
            return (open_ if open_ <= position.stop else position.stop, "atr_stop")
        if target_hit:
            return (open_ if open_ >= position.target else position.target, "atr_target")
    else:
        stop_hit, target_hit = high >= position.stop, low <= position.target
        if stop_hit:
            return (open_ if open_ >= position.stop else position.stop, "atr_stop")
        if target_hit:
            return (open_ if open_ <= position.target else position.target, "atr_target")
    return None


def run_pine_strategy(
    audusd_bars: pd.DataFrame,
    audusd_1m: pd.DataFrame,
    features: pd.DataFrame,
    timeframe_minutes: int,
    z_entry: float = 1.5,
    z_exit: float = 0.25,
    use_atr_risk: bool = True,
    atr_stop_mult: float = 2.0,
    atr_target_mult: float = 3.0,
    initial_capital: float = 100_000.0,
    quantity: float = 100_000.0,
    commission_percent: float = 0.0,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, object]]:
    """Run the one-position strategy with Pine-style next-bar market orders.

    ATR levels are frozen from the signal bar close, matching the supplied code.
    Stop/target monitoring starts in the entry bar on underlying one-minute OHLC.
    """
    if z_entry <= 0 or z_exit <= 0 or z_exit >= z_entry:
        raise ValueError("Require 0 < z_exit < z_entry")
    if timeframe_minutes not in {1, 5, 15, 30, 60}:
        raise ValueError("unsupported timeframe")
    if quantity <= 0 or initial_capital <= 0 or commission_percent < 0:
        raise ValueError("capital/quantity must be positive and commission nonnegative")

    bars = audusd_bars.sort_index()
    minute = audusd_1m.sort_index()
    signal_frame = features.reindex(bars.index)
    step = pd.Timedelta(minutes=timeframe_minutes)
    position: Position | None = None
    pending: dict[str, object] | None = None
    trades: list[dict[str, object]] = []
    actions: list[dict[str, object]] = []

    for bar_number, (bar_close_ts, bar) in enumerate(bars.iterrows()):
        bar_start = bar_close_ts - step

        # Market orders generated at the prior close fill at this bar's open.
        if pending is not None:
            if pending["fill_ts"] != bar_start:
                actions.append({"ts": bar_start, "action": "cancel_gap_order", "detail": pending["kind"]})
                pending = None
            elif pending["kind"] == "close" and position is not None:
                exit_price = float(bar["audusd_open"])
                trades.append(
                    _exit_trade(position, bar_start, exit_price, "z_reversion", quantity, commission_percent, bar_number)
                )
                actions.append({"ts": bar_start, "action": "exit", "detail": "z_reversion"})
                position = None
                pending = None
            elif pending["kind"] == "entry" and position is None:
                entry_price = float(bar["audusd_open"])
                position = Position(
                    side=int(pending["side"]),
                    signal_ts=pending["signal_ts"],
                    signal_z=float(pending["signal_z"]),
                    signal_close=float(pending["signal_close"]),
                    atr=float(pending["atr"]),
                    stop=pending["stop"],
                    target=pending["target"],
                    entry_ts=bar_start,
                    entry_price=entry_price,
                    entry_cost=_order_cost(entry_price, quantity, commission_percent),
                    entry_bar_number=bar_number,
                )
                actions.append({"ts": bar_start, "action": "entry", "detail": "long" if position.side > 0 else "short"})
                pending = None

        # Replay the full entry bar and every later bar at one-minute resolution.
        if position is not None and use_atr_risk:
            minute_slice = minute.loc[bar_start : bar_close_ts - pd.Timedelta(minutes=1)]
            for minute_ts, minute_bar in minute_slice.iterrows():
                fill = _bracket_fill(position, minute_bar)
                if fill is not None:
                    exit_price, reason = fill
                    trades.append(
                        _exit_trade(position, minute_ts, exit_price, reason, quantity, commission_percent, bar_number)
                    )
                    actions.append({"ts": minute_ts, "action": "exit", "detail": reason})
                    position = None
                    break

        row = signal_frame.loc[bar_close_ts]
        ready_column = "feature_ready" if use_atr_risk else "z_ready"
        ready_value = row.get(ready_column, row.get("feature_ready", False))
        ready = bool(ready_value) if pd.notna(ready_value) else False
        zscore = float(row["zscore"]) if pd.notna(row.get("zscore", np.nan)) else np.nan

        # Mean-reversion close is evaluated before a new entry, as in the script.
        if position is not None and ready:
            should_close = (position.side > 0 and zscore >= -z_exit) or (position.side < 0 and zscore <= z_exit)
            if should_close:
                pending = {"kind": "close", "fill_ts": bar_close_ts}
                actions.append({"ts": bar_close_ts, "action": "schedule_exit", "detail": "z_reversion"})

        if position is None and pending is None and ready:
            side = 1 if zscore <= -z_entry else -1 if zscore >= z_entry else 0
            if side:
                signal_close = float(row["actual_audusd"])
                atr = float(row["atr"])
                if use_atr_risk:
                    stop = signal_close - side * atr * atr_stop_mult
                    target = signal_close + side * atr * atr_target_mult
                else:
                    stop = target = None
                pending = {
                    "kind": "entry",
                    "fill_ts": bar_close_ts,
                    "side": side,
                    "signal_ts": bar_close_ts,
                    "signal_z": zscore,
                    "signal_close": signal_close,
                    "atr": atr,
                    "stop": stop,
                    "target": target,
                }
                actions.append({"ts": bar_close_ts, "action": "schedule_entry", "detail": "long" if side > 0 else "short"})

    trade_frame = pd.DataFrame.from_records(trades)
    action_frame = pd.DataFrame.from_records(actions)
    if not trade_frame.empty:
        trade_frame["equity"] = initial_capital + trade_frame["net_pnl_usd"].cumsum()
        trade_frame["peak_equity"] = trade_frame["equity"].cummax()
        trade_frame["drawdown_usd"] = trade_frame["equity"] - trade_frame["peak_equity"]
    state = {
        "initial_capital": initial_capital,
        "ending_realized_equity": float(initial_capital + trade_frame["net_pnl_usd"].sum()) if not trade_frame.empty else initial_capital,
        "open_position": position,
        "pending_order": pending,
    }
    return trade_frame, action_frame, state


def summarize_pine_trades(trades: pd.DataFrame, initial_capital: float) -> pd.Series:
    if trades.empty:
        return pd.Series({"trades": 0, "ending_realized_equity": initial_capital})
    wins = trades.loc[trades["net_pnl_usd"] > 0, "net_pnl_usd"].sum()
    losses = -trades.loc[trades["net_pnl_usd"] < 0, "net_pnl_usd"].sum()
    daily = trades.assign(day=pd.to_datetime(trades["exit_ts"]).dt.floor("D")).groupby("day")["net_pnl_usd"].sum()
    return pd.Series(
        {
            "trades": len(trades),
            "gross_pnl_usd": trades["gross_pnl_usd"].sum(),
            "cost_usd": trades["cost_usd"].sum(),
            "net_pnl_usd": trades["net_pnl_usd"].sum(),
            "net_return_on_initial_pct": 100 * trades["net_pnl_usd"].sum() / initial_capital,
            "win_rate": trades["net_pnl_usd"].gt(0).mean(),
            "profit_factor": wins / losses if losses > 0 else np.nan,
            "mean_net_pnl_usd": trades["net_pnl_usd"].mean(),
            "max_trade_equity_drawdown_usd": trades["drawdown_usd"].min(),
            "daily_sharpe": np.sqrt(252) * daily.mean() / daily.std(ddof=1) if daily.std(ddof=1) > 0 else np.nan,
            "ending_realized_equity": initial_capital + trades["net_pnl_usd"].sum(),
        }
    )
