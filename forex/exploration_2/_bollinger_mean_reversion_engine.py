"""Causal feature and execution helpers for the Bollinger re-entry fade notebook."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd
from numba import njit

from _bollinger_engine import (
    HOLDOUT_START,
    causal_same_slot_percentile,
    performance_stats,
    portfolio_equity,
)


@dataclass(frozen=True)
class MeanReversionConfig:
    name: str = "reentry_baseline"
    bb_length: int = 200
    outer_sigma: float = 1.5
    max_reentry_bars: int = 6
    target_sigma: float | None = 0.0
    stop_sigma: float | None = 2.5
    sizing_stop_sigma: float = 2.5
    min_risk_sigma: float = 0.5
    timeout_bars: int = 24  # 120 minutes
    rv_gate_mode: str = "none"
    rv_percentile_threshold: float = 0.60
    round_trip_cost_pips: float = 0.0
    stop_slippage_pips: float = 0.0


def observed_bar_rolling(series: pd.Series, valid: pd.Series, window: int, op: str) -> pd.Series:
    """Roll over the last ``window`` valid observed bars, irrespective of wall-clock gaps."""
    clean = series.loc[valid].astype(float)
    if op == "mean":
        rolled = clean.rolling(window, min_periods=window).mean()
    elif op == "std0":
        rolled = clean.rolling(window, min_periods=window).std(ddof=0)
    else:
        raise ValueError(op)
    out = pd.Series(np.nan, index=series.index, dtype=float)
    out.loc[valid] = rolled
    return out


def causal_same_slot_median(
    values: pd.Series,
    slots: pd.Series,
    sessions: pd.Series,
    lookback_sessions: int,
    min_fraction: float = 2 / 3,
) -> pd.Series:
    """Median of prior sessions at the identical NY-session slot.

    The current observation is shifted out before rolling. Missing sessions do
    not become observations; ``min_fraction`` exposes the coverage policy.
    """
    out = np.full(len(values), np.nan)
    min_obs = int(np.ceil(lookback_sessions * min_fraction))
    for _, indices in slots.groupby(slots, sort=False).groups.items():
        idx = np.asarray(indices, dtype=np.int64)
        order = np.argsort(sessions.iloc[idx].to_numpy(), kind="stable")
        idx = idx[order]
        s = pd.Series(values.iloc[idx].to_numpy(float))
        out[idx] = s.shift(1).rolling(lookback_sessions, min_periods=min_obs).median().to_numpy()
    return pd.Series(out, index=values.index)


def _bars_since(mask: np.ndarray) -> np.ndarray:
    out = np.empty(mask.size, dtype=np.int32)
    count = 1_000_000
    for i in range(mask.size):
        if mask[i]:
            count = 0
        else:
            count += 1
        out[i] = count
    return out


def build_mean_reversion_features(
    bars: pd.DataFrame,
    bb_lengths: Iterable[int] = (200,),
    short_rv_memory: int = 90,
    long_rv_memory: int = 252,
    min_fraction: float = 2 / 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build continuous-close Bollinger bands and causal RV regime features."""
    f = bars.copy()
    valid = f.complete_5m & f[["open", "high", "low", "close"]].notna().all(axis=1)
    f["valid_bar"] = valid
    f["gap_before"] = f.bar_open.diff().gt(pd.Timedelta(minutes=5))
    f["gap_minutes_before"] = f.bar_open.diff().dt.total_seconds().div(60)
    f["bars_since_gap"] = _bars_since(f.gap_before.to_numpy(bool))
    f["bars_to_next_gap"] = _bars_since(f.gap_before.iloc[::-1].to_numpy(bool))[::-1]

    # Bollinger uses observed closes, as a chart indicator normally does. Scheduled
    # rollover/weekend closures therefore do not restart the moving average.
    for length in sorted(set(int(x) for x in bb_lengths)):
        f[f"bb_mid_{length}"] = observed_bar_rolling(f.close, valid, length, "mean")
        f[f"bb_sd_{length}"] = observed_bar_rolling(f.close, valid, length, "std0")

    # Short-horizon RV keeps its horizon honest: a wall-clock gap starts a new
    # six-bar window even though the close-based Bollinger indicator carries on.
    contiguous = f.bar_open.diff().eq(pd.Timedelta(minutes=5)) & valid & valid.shift(fill_value=False)
    f["return_segment"] = (~contiguous).cumsum().astype("int32")
    log_ret = np.log(f.close).diff().where(contiguous)
    f["log_return"] = log_ret
    rv30_sq = (
        log_ret.pow(2).groupby(f.return_segment, sort=False)
        .rolling(6, min_periods=6).sum().reset_index(level=0, drop=True)
    )
    f["rv30"] = np.sqrt(rv30_sq)

    for memory in sorted({int(short_rv_memory), int(long_rv_memory)}):
        median_col = f"rv30_slot_median_{memory}"
        pct_col = f"rv30_slot_pct_{memory}"
        f[median_col] = causal_same_slot_median(
            f.rv30, f.session_slot, f.session_id, memory, min_fraction
        )
        f[f"rv30_vs_slot_median_{memory}"] = f.rv30 / f[median_col].replace(0, np.nan)
        f[pct_col] = causal_same_slot_percentile(
            f.rv30, f.session_slot, f.session_id, memory, min_fraction
        )

    period = np.where(f.bar_open < pd.Timestamp("2021-01-01", tz="UTC"),
                      "development_pre2021", "evaluation_2021_2023")
    cols = [c for c in f.columns if c.startswith(("bb_", "rv30"))]
    rows = []
    for sample in ["development_pre2021", "evaluation_2021_2023"]:
        mask = period == sample
        for col in cols:
            rows.append({
                "sample": sample, "feature": col, "rows": int(mask.sum()),
                "defined": int(f.loc[mask, col].notna().sum()),
                "missing": int(f.loc[mask, col].isna().sum()),
                "coverage": float(f.loc[mask, col].notna().mean()),
            })
    return f, pd.DataFrame(rows)


@njit(cache=True)
def reentry_signals(close, upper, lower, valid, max_reentry_bars):
    """Arm on an outside close; signal a fade after a later close back inside."""
    n = len(close)
    signal = np.zeros(n, np.int8)
    age_out = np.full(n, -1, np.int16)
    pending = 0  # +1 future long after lower excursion; -1 future short after upper
    age = 0
    for i in range(n):
        if not valid[i] or not np.isfinite(upper[i]) or not np.isfinite(lower[i]):
            pending = 0
            age = 0
            continue
        if pending == 0:
            if close[i] > upper[i]:
                pending, age = -1, 0
            elif close[i] < lower[i]:
                pending, age = 1, 0
            continue
        age += 1
        if pending == -1 and close[i] <= upper[i]:
            signal[i], age_out[i] = -1, age
            pending, age = 0, 0
        elif pending == 1 and close[i] >= lower[i]:
            signal[i], age_out[i] = 1, age
            pending, age = 0, 0
        elif age >= max_reentry_bars:
            pending, age = 0, 0
    return signal, age_out


@njit(cache=True)
def _simulate_reentry(
    open_, high, low, close, signal, target_long, target_short,
    stop_long, stop_short, sizing_stop_long, sizing_stop_short, min_risk_distance,
    force_friday, timeout_bars, stop_slippage,
):
    n = len(open_)
    entry_i = np.empty(n, np.int64)
    exit_i = np.empty(n, np.int64)
    sides = np.empty(n, np.int8)
    entry_px = np.empty(n, np.float64)
    exit_px = np.empty(n, np.float64)
    risk_px = np.empty(n, np.float64)
    reason = np.empty(n, np.int8)  # 1 target, 2 stop, 3 timeout, 4 Friday, 5 end
    ambiguous = np.empty(n, np.int8)
    gap_exit = np.empty(n, np.int8)
    k = 0
    side = 0
    ei = -1
    ep = target = stop = risk = np.nan

    for i in range(1, n):
        was_flat = side == 0
        if was_flat and signal[i - 1] != 0 and np.isfinite(open_[i]):
            side = signal[i - 1]
            ei, ep = i, open_[i]
            if side == 1:
                target, stop = target_long[i - 1], stop_long[i - 1]
                sizing_stop = sizing_stop_long[i - 1]
            else:
                target, stop = target_short[i - 1], stop_short[i - 1]
                sizing_stop = sizing_stop_short[i - 1]
            risk = abs(ep - sizing_stop)
            if (not np.isfinite(risk) or risk <= 0 or not np.isfinite(min_risk_distance[i - 1])
                    or risk < min_risk_distance[i - 1]):
                side = 0
                continue

        if side == 0:
            continue

        exit_now = False
        px = np.nan
        rsn = 0
        both = 0
        gap = 0

        # Timeout is an open-to-open horizon and acts before this bar's path.
        if i > ei and i - ei >= timeout_bars:
            px, rsn, exit_now = open_[i], 3, True
        elif side == 1:
            if np.isfinite(stop) and open_[i] <= stop:
                px, rsn, exit_now, gap = open_[i] - stop_slippage, 2, True, 1
            elif np.isfinite(target) and open_[i] >= target:
                px, rsn, exit_now, gap = open_[i], 1, True, 1
            else:
                hit_stop = np.isfinite(stop) and low[i] <= stop
                hit_target = np.isfinite(target) and high[i] >= target
                if hit_stop and hit_target:
                    px, rsn, exit_now, both = stop - stop_slippage, 2, True, 1
                elif hit_stop:
                    px, rsn, exit_now = stop - stop_slippage, 2, True
                elif hit_target:
                    px, rsn, exit_now = target, 1, True
        else:
            if np.isfinite(stop) and open_[i] >= stop:
                px, rsn, exit_now, gap = open_[i] + stop_slippage, 2, True, 1
            elif np.isfinite(target) and open_[i] <= target:
                px, rsn, exit_now, gap = open_[i], 1, True, 1
            else:
                hit_stop = np.isfinite(stop) and high[i] >= stop
                hit_target = np.isfinite(target) and low[i] <= target
                if hit_stop and hit_target:
                    px, rsn, exit_now, both = stop + stop_slippage, 2, True, 1
                elif hit_stop:
                    px, rsn, exit_now = stop + stop_slippage, 2, True
                elif hit_target:
                    px, rsn, exit_now = target, 1, True

        if not exit_now and force_friday[i]:
            px, rsn, exit_now = close[i], 4, True

        if exit_now:
            entry_i[k], exit_i[k], sides[k] = ei, i, side
            entry_px[k], exit_px[k], risk_px[k] = ep, px, risk
            reason[k], ambiguous[k], gap_exit[k] = rsn, both, gap
            k += 1
            side = 0

    if side != 0:
        i = n - 1
        entry_i[k], exit_i[k], sides[k] = ei, i, side
        entry_px[k], exit_px[k], risk_px[k] = ep, close[i], risk
        reason[k], ambiguous[k], gap_exit[k] = 5, 0, 0
        k += 1
    return (entry_i[:k], exit_i[:k], sides[:k], entry_px[:k], exit_px[:k],
            risk_px[:k], reason[:k], ambiguous[:k], gap_exit[:k])


def _rv_gate(frame: pd.DataFrame, config: MeanReversionConfig) -> np.ndarray:
    mode = config.rv_gate_mode
    if mode == "none":
        return np.ones(len(frame), dtype=bool)
    if mode == "above_short_median":
        return frame.rv30_vs_slot_median_90.to_numpy(float) >= 1.0
    if mode == "above_long_median":
        return frame.rv30_vs_slot_median_252.to_numpy(float) >= 1.0
    if mode == "short_percentile":
        return frame.rv30_slot_pct_90.to_numpy(float) >= config.rv_percentile_threshold
    if mode == "long_percentile":
        return frame.rv30_slot_pct_252.to_numpy(float) >= config.rv_percentile_threshold
    if mode == "joint_medians":
        return ((frame.rv30_vs_slot_median_90.to_numpy(float) >= 1.0)
                & (frame.rv30_vs_slot_median_252.to_numpy(float) >= 1.0))
    raise ValueError(f"Unknown RV gate mode {mode!r}")


def run_mean_reversion_config(
    frame: pd.DataFrame,
    pair: str,
    config: MeanReversionConfig,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    mid = frame[f"bb_mid_{config.bb_length}"].to_numpy(float)
    sd = frame[f"bb_sd_{config.bb_length}"].to_numpy(float)
    upper = mid + config.outer_sigma * sd
    lower = mid - config.outer_sigma * sd
    signal, reentry_age = reentry_signals(
        frame.close.to_numpy(float), upper, lower, frame.valid_bar.to_numpy(bool),
        config.max_reentry_bars,
    )
    signal = np.where(_rv_gate(frame, config), signal, 0).astype(np.int8)

    if config.target_sigma is None:
        target_long = target_short = np.full(len(frame), np.nan)
    else:
        target_long = mid - config.target_sigma * sd
        target_short = mid + config.target_sigma * sd
    if config.stop_sigma is None:
        stop_long = stop_short = np.full(len(frame), np.nan)
    else:
        stop_long = mid - config.stop_sigma * sd
        stop_short = mid + config.stop_sigma * sd
    sizing_long = mid - config.sizing_stop_sigma * sd
    sizing_short = mid + config.sizing_stop_sigma * sd
    min_risk_distance = config.min_risk_sigma * sd
    pip_size = 0.01 if pair.endswith("JPY") else 0.0001
    arrays = _simulate_reentry(
        frame.open.to_numpy(float), frame.high.to_numpy(float), frame.low.to_numpy(float),
        frame.close.to_numpy(float), signal, target_long, target_short, stop_long, stop_short,
        sizing_long, sizing_short, min_risk_distance, frame.force_friday_close.to_numpy(bool),
        config.timeout_bars, config.stop_slippage_pips * pip_size,
    )
    ei, xi, side, ep, xp, risk, rsn, ambiguous, gap_exit = arrays
    signal_frame = pd.DataFrame({
        "signal_index": np.flatnonzero(signal),
        "signal_time": frame.bar_close.iloc[np.flatnonzero(signal)].to_numpy(),
        "side": signal[signal != 0],
        "reentry_age_bars": reentry_age[signal != 0],
    })
    signal_idx_all = signal_frame.signal_index.to_numpy(int)
    entry_idx_all = signal_idx_all + 1
    in_range = entry_idx_all < len(frame)
    signal_frame["risk_too_small_at_next_open"] = True
    if in_range.any():
        si = signal_idx_all[in_range]
        en = entry_idx_all[in_range]
        sizing = np.where(signal[si] == 1, sizing_long[si], sizing_short[si])
        actual_risk = np.abs(frame.open.to_numpy(float)[en] - sizing)
        signal_frame.loc[in_range, "risk_too_small_at_next_open"] = actual_risk < min_risk_distance[si]
    if not len(ei):
        return pd.DataFrame(), signal_frame
    gross_price = side * (xp - ep)
    cost_price = config.round_trip_cost_pips * pip_size
    reasons = np.array(["", "target", "stop", "timeout", "friday_close", "sample_end"], dtype=object)[rsn]
    out = pd.DataFrame({
        "pair": pair, "config": config.name, "entry_index": ei, "exit_index": xi,
        "entry_time": frame.bar_open.iloc[ei].to_numpy(),
            "exit_time": np.where(rsn == 3, frame.bar_open.iloc[xi].to_numpy(),
                                  frame.bar_close.iloc[xi].to_numpy()),
        "session_date": frame.session_date.iloc[xi].to_numpy(),
        "side": side, "entry_price": ep, "exit_price": xp, "risk_price": risk,
        "gross_pips": gross_price / pip_size, "net_pips": (gross_price - cost_price) / pip_size,
        "gross_r": gross_price / risk, "net_r": (gross_price - cost_price) / risk,
        "exit_reason": reasons, "ambiguous_bar_adverse_stop": ambiguous.astype(bool),
        "gap_exit": gap_exit.astype(bool), "holding_bars": xi - ei,
    })
    signal_idx = np.maximum(ei - 1, 0)
    out["signal_time"] = frame.bar_close.iloc[signal_idx].to_numpy()
    out["reentry_age_bars"] = reentry_age[signal_idx]
    out["rv30"] = frame.rv30.iloc[signal_idx].to_numpy()
    for memory in [90, 252]:
        out[f"rv30_slot_median_{memory}"] = frame[f"rv30_slot_median_{memory}"].iloc[signal_idx].to_numpy()
        out[f"rv30_vs_slot_median_{memory}"] = frame[f"rv30_vs_slot_median_{memory}"].iloc[signal_idx].to_numpy()
        out[f"rv30_slot_pct_{memory}"] = frame[f"rv30_slot_pct_{memory}"].iloc[signal_idx].to_numpy()
    out["bars_since_gap"] = frame.bars_since_gap.iloc[signal_idx].to_numpy()
    out["bars_to_next_gap"] = frame.bars_to_next_gap.iloc[signal_idx].to_numpy()
    out["gap_minutes_before"] = frame.gap_minutes_before.iloc[signal_idx].to_numpy()
    entry_ts = pd.to_datetime(out.entry_time, utc=True)
    out["year"] = entry_ts.dt.year
    out["sample"] = np.where(out.year < 2021, "development_pre2021",
                             np.where(out.year < 2024, "evaluation_2021_2023", "holdout_2024_plus"))
    return out, signal_frame


__all__ = [
    "MeanReversionConfig", "build_mean_reversion_features", "causal_same_slot_median",
    "observed_bar_rolling", "performance_stats", "portfolio_equity", "reentry_signals",
    "run_mean_reversion_config", "_simulate_reentry",
]
