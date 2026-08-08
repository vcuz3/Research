"""Causal execution, accounting, and metrics for the TWAP/SMA Z-band study."""

from __future__ import annotations

from dataclasses import asdict

import numpy as np
import pandas as pd
from numba import njit

from strategy.twap_zband import PIP_SIZE, StrategyConfig, active_arrays, sample_name


EXIT_REASON = {1: "target", 2: "stop", 3: "end_of_data"}


@njit(cache=True)
def _find_exit(
    start_i: int,
    raw_open: np.ndarray,
    raw_high: np.ndarray,
    raw_low: np.ndarray,
    raw_close: np.ndarray,
    side: int,
    stop: float,
    target: float,
) -> tuple[int, float, int, int, int]:
    """Replay a frozen bracket on one-minute bars with adverse ambiguity."""

    n = raw_open.size
    for j in range(start_i, n):
        op = raw_open[j]
        if side == 1:
            if op <= stop:
                return j, op, 2, 0, 1
            if op >= target:
                return j, op, 1, 0, 1
            hit_stop = raw_low[j] <= stop
            hit_target = raw_high[j] >= target
        else:
            if op >= stop:
                return j, op, 2, 0, 1
            if op <= target:
                return j, op, 1, 0, 1
            hit_stop = raw_high[j] >= stop
            hit_target = raw_low[j] <= target

        if hit_stop and hit_target:
            return j, stop, 2, 1, 0
        if hit_stop:
            return j, stop, 2, 0, 0
        if hit_target:
            return j, target, 1, 0, 0
    return n - 1, raw_close[n - 1], 3, 0, 0


@njit(cache=True)
def _simulate_strategy(
    bar_high: np.ndarray,
    bar_low: np.ndarray,
    bar_close: np.ndarray,
    bar_start_i: np.ndarray,
    bar_end_i: np.ndarray,
    baseline: np.ndarray,
    stdev: np.ndarray,
    atr: np.ndarray,
    raw_open: np.ndarray,
    raw_high: np.ndarray,
    raw_low: np.ndarray,
    raw_close: np.ndarray,
    arm_z: float,
    max_arm_bars: int,
    atr_stop_mult: float,
    target_r: float,
):
    """Run the close-confirmed state machine and next-observed-bar execution."""

    n = bar_close.size
    signal_i = np.empty(n, np.int64)
    entry_i = np.empty(n, np.int64)
    exit_i = np.empty(n, np.int64)
    sides = np.empty(n, np.int8)
    entry_px = np.empty(n, np.float64)
    exit_px = np.empty(n, np.float64)
    stop_px = np.empty(n, np.float64)
    target_px = np.empty(n, np.float64)
    risk_px = np.empty(n, np.float64)
    signal_z = np.empty(n, np.float64)
    reason = np.empty(n, np.int8)
    ambiguous = np.empty(n, np.int8)
    gap_exit = np.empty(n, np.int8)
    entry_gap_bars = np.empty(n, np.int32)

    armed_long = False
    armed_short = False
    armed_long_i = -1
    armed_short_i = -1
    active_exit_i = -1
    k = 0

    for i in range(n - 1):
        # An exit anywhere inside this completed signal bar is known by its close.
        if active_exit_i > bar_end_i[i]:
            armed_long = False
            armed_short = False
            continue

        if not (np.isfinite(baseline[i]) and np.isfinite(stdev[i]) and stdev[i] > 0.0):
            continue

        lower = baseline[i] - arm_z * stdev[i]
        upper = baseline[i] + arm_z * stdev[i]

        if bar_close[i] < lower:
            if not armed_long:
                armed_long = True
                armed_long_i = i
        if bar_close[i] > upper:
            if not armed_short:
                armed_short = True
                armed_short_i = i

        # Match Pine's order: disarm tests happen before the re-entry signal.
        if armed_long and (i - armed_long_i > max_arm_bars or bar_close[i] >= baseline[i]):
            armed_long = False
        if armed_short and (i - armed_short_i > max_arm_bars or bar_close[i] <= baseline[i]):
            armed_short = False

        side = 0
        if armed_long and bar_close[i] > lower:
            side = 1
        elif armed_short and bar_close[i] < upper:
            side = -1

        if side == 0 or not np.isfinite(atr[i]) or atr[i] <= 0.0:
            continue

        # A completed close at bar i can first trade at the next observed complete
        # signal bar's open.  The one-minute archive supplies that executable open.
        ei = bar_start_i[i + 1]
        ep = raw_open[ei]
        risk = atr[i] * atr_stop_mult
        if not np.isfinite(ep) or not np.isfinite(risk) or risk <= 0.0:
            continue
        if side == 1:
            stop = ep - risk
            target = ep + risk * target_r
        else:
            stop = ep + risk
            target = ep - risk * target_r

        xi, xp, rsn, both, gap = _find_exit(
            ei, raw_open, raw_high, raw_low, raw_close, side, stop, target
        )

        signal_i[k] = i
        entry_i[k] = ei
        exit_i[k] = xi
        sides[k] = side
        entry_px[k] = ep
        exit_px[k] = xp
        stop_px[k] = stop
        target_px[k] = target
        risk_px[k] = risk
        signal_z[k] = (bar_close[i] - baseline[i]) / stdev[i]
        reason[k] = rsn
        ambiguous[k] = both
        gap_exit[k] = gap
        expected_next = bar_end_i[i] + 1
        entry_gap_bars[k] = max(0, ei - expected_next)
        k += 1

        active_exit_i = xi
        armed_long = False
        armed_short = False

    return (
        signal_i[:k], entry_i[:k], exit_i[:k], sides[:k], entry_px[:k],
        exit_px[:k], stop_px[:k], target_px[:k], risk_px[:k], signal_z[:k],
        reason[:k], ambiguous[:k], gap_exit[:k], entry_gap_bars[:k],
    )


def run_config(
    bars: pd.DataFrame,
    raw: pd.DataFrame,
    pair: str,
    config: StrategyConfig,
) -> pd.DataFrame:
    """Execute one configuration and return a complete auditable trade table."""

    baseline, stdev, atr = active_arrays(bars, config)
    out = _simulate_strategy(
        bars.high.to_numpy(float),
        bars.low.to_numpy(float),
        bars.close.to_numpy(float),
        bars.raw_start_i.to_numpy(np.int64),
        bars.raw_end_i.to_numpy(np.int64),
        baseline,
        stdev,
        atr,
        raw.open.to_numpy(float),
        raw.high.to_numpy(float),
        raw.low.to_numpy(float),
        raw.close.to_numpy(float),
        config.arm_z,
        config.max_arm_bars,
        config.atr_stop_mult,
        config.target_r,
    )
    if len(out[0]) == 0:
        return pd.DataFrame()

    signal_idx, entry_idx, exit_idx, side = out[0], out[1], out[2], out[3]
    entry_px, exit_px, stop_px, target_px, risk_px = out[4:9]
    gross_pips = side * (exit_px - entry_px) / PIP_SIZE
    risk_pips = risk_px / PIP_SIZE
    gross_r = gross_pips / risk_pips
    net_pips = gross_pips - config.round_trip_cost_pips
    net_r = net_pips / risk_pips

    trades = pd.DataFrame(
        {
            "pair": pair,
            "config": config.name,
            "signal_time": bars.bar_open.iloc[signal_idx].to_numpy() + pd.Timedelta(minutes=config.bar_minutes),
            "entry_time": raw.ts_utc.iloc[entry_idx].to_numpy(),
            "exit_time": raw.ts_utc.iloc[exit_idx].to_numpy(),
            "entry_session": bars.session_id.iloc[signal_idx].to_numpy(),
            "side": np.where(side == 1, "long", "short"),
            "entry_price": entry_px,
            "exit_price": exit_px,
            "stop_price": stop_px,
            "target_price": target_px,
            "risk_pips": risk_pips,
            "signal_z": out[9],
            "gross_pips": gross_pips,
            "cost_pips": config.round_trip_cost_pips,
            "net_pips": net_pips,
            "gross_r": gross_r,
            "net_r": net_r,
            "exit_reason": [EXIT_REASON[int(x)] for x in out[10]],
            "ambiguous_1m": out[11].astype(bool),
            "gap_exit": out[12].astype(bool),
            "entry_gap_observed_minutes": out[13].astype(float),
        }
    )
    trades["hold_minutes"] = (
        pd.to_datetime(trades.exit_time) - pd.to_datetime(trades.entry_time)
    ).dt.total_seconds().div(60)
    trades["entry_gap_minutes"] = (
        pd.to_datetime(trades.entry_time) - pd.to_datetime(trades.signal_time)
    ).dt.total_seconds().div(60)
    trades["sample"] = sample_name(trades.entry_time)
    return trades


def clustered_mean_t(values: pd.Series, clusters: pd.Series) -> tuple[float, float]:
    """One-way session-clustered SE and t-stat for the per-trade mean."""

    frame = pd.DataFrame({"x": values.astype(float), "g": clusters}).dropna()
    n = len(frame)
    g = frame.g.nunique()
    mean = frame.x.mean() if n else np.nan
    if n < 2 or g < 2:
        return np.nan, np.nan
    scores = (frame.x - mean).groupby(frame.g).sum()
    variance = (g / (g - 1)) * scores.pow(2).sum() / (n * n)
    se = float(np.sqrt(variance))
    return se, float(mean / se) if se > 0 else np.nan


def daily_portfolio(trades: pd.DataFrame, sessions: Iterable[str], value_col: str = "net_pips") -> pd.Series:
    """Daily fixed-quantity portfolio P&L; never average same-session trades."""

    index = pd.Index(sorted(set(str(x) for x in sessions)), name="entry_session")
    if trades.empty:
        return pd.Series(0.0, index=index, name=value_col)
    daily = trades.groupby("entry_session", observed=True)[value_col].sum()
    return daily.reindex(index, fill_value=0.0).astype(float)


def max_drawdown(values: pd.Series) -> float:
    equity = values.cumsum()
    return float((equity - equity.cummax()).min()) if len(equity) else np.nan


def summarize_trades(trades: pd.DataFrame, sessions: Iterable[str]) -> dict:
    """Gross/net trade metrics plus deployable fixed-quantity daily risk."""

    if trades.empty:
        return {"trades": 0}
    se, t_stat = clustered_mean_t(trades.net_r, trades.entry_session)
    daily = daily_portfolio(trades, sessions, "net_pips")
    daily_std = daily.std(ddof=1)
    sharpe = np.sqrt(252.0) * daily.mean() / daily_std if daily_std > 0 else np.nan
    positive = trades.loc[trades.net_pips > 0, "net_pips"].sum()
    negative = -trades.loc[trades.net_pips < 0, "net_pips"].sum()
    return {
        "trades": int(len(trades)),
        "sessions": int(len(daily)),
        "trades_per_session": float(len(trades) / max(len(daily), 1)),
        "win_rate_net": float((trades.net_pips > 0).mean()),
        "gross_mean_pips": float(trades.gross_pips.mean()),
        "net_mean_pips": float(trades.net_pips.mean()),
        "gross_total_pips": float(trades.gross_pips.sum()),
        "cost_total_pips": float(trades.cost_pips.sum()),
        "net_total_pips": float(trades.net_pips.sum()),
        "gross_mean_r": float(trades.gross_r.mean()),
        "net_mean_r": float(trades.net_r.mean()),
        "net_r_cluster_se": se,
        "net_r_cluster_t": t_stat,
        "net_profit_factor": float(positive / negative) if negative > 0 else np.inf,
        "daily_sharpe_net_pips": float(sharpe),
        "daily_worst_pips": float(daily.min()),
        "daily_max_drawdown_pips": max_drawdown(daily),
        "median_risk_pips": float(trades.risk_pips.median()),
        "median_hold_minutes": float(trades.hold_minutes.median()),
        "ambiguous_1m_share": float(trades.ambiguous_1m.mean()),
        "gap_exit_share": float(trades.gap_exit.mean()),
    }


def config_dict(config: StrategyConfig) -> dict:
    return asdict(config)
