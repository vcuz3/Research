"""Auditable helpers for the FX Bollinger breakout exploration notebook.

Feature construction is vectorised with pandas/NumPy.  The position path is
stateful by definition, so it is simulated in a compiled Numba loop.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from numba import njit


PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")
HOLDOUT_START = pd.Timestamp("2024-01-01", tz="UTC")
NY_TZ = "America/New_York"
BREAKOUT_ENGINE_VERSION = "2026-08-04-continuous-observed-bb-v2"


@dataclass(frozen=True)
class StrategyConfig:
    name: str = "baseline"
    bb_length: int = 200
    entry_sigma: float = 1.5
    stop_sigma: float = 0.75
    rv30_min_pct: float | None = None
    acceleration_min_pct: float | None = None
    vei_fast: int | None = None
    vei_slow: int | None = None
    vei_min_pct: float | None = None
    trend_kind: str | None = None
    trend_hours: int | None = None
    trend_mode: str = "any"  # any, aligned, counter
    trend_strength_min: float | None = None
    round_trip_cost_pips: float = 0.0
    stop_slippage_pips: float = 0.0


def _as_utc(series: pd.Series) -> pd.Series:
    out = pd.to_datetime(series)
    if out.dt.tz is None:
        return out.dt.tz_localize("UTC")
    return out.dt.tz_convert("UTC")


def load_five_minute_bars(
    pair: str,
    data_dir: str | Path,
    holdout_start: pd.Timestamp = HOLDOUT_START,
    allow_holdout: bool = False,
) -> tuple[pd.DataFrame, pd.Series]:
    """Load one-minute OHLC and aggregate to left-labelled five-minute bars.

    The default parquet filter prevents 2024+ rows from entering memory.  A
    five-minute bar remains in the frame if it has at least one source minute;
    ``complete_5m`` makes partial bars explicit and the strategy excludes them.
    """
    pair = pair.upper()
    if pair not in PAIRS:
        raise ValueError(f"Unsupported pair {pair!r}")
    path = Path(data_dir) / f"{pair}_1m_clean.parquet"
    if not path.exists():
        raise FileNotFoundError(path)
    filters = None if allow_holdout else [("ts_utc", "<", holdout_start.tz_localize(None))]
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"], filters=filters)
    raw["ts_utc"] = _as_utc(raw["ts_utc"])
    raw = raw.sort_values("ts_utc", kind="stable").reset_index(drop=True)

    dt = raw.ts_utc.diff()
    invalid = (
        raw[["open", "high", "low", "close"]].le(0).any(axis=1)
        | raw.low.gt(raw[["open", "close"]].min(axis=1))
        | raw.high.lt(raw[["open", "close"]].max(axis=1))
        | raw.high.lt(raw.low)
    )
    quality = pd.Series(
        {
            "pair": pair,
            "source_rows": len(raw),
            "first_utc": raw.ts_utc.min(),
            "last_utc": raw.ts_utc.max(),
            "duplicate_timestamps": int(raw.ts_utc.duplicated().sum()),
            "out_of_order_timestamps": int(dt.dropna().le(pd.Timedelta(0)).sum()),
            "missing_one_minute_links": int(dt.gt(pd.Timedelta(minutes=1)).sum()),
            "largest_gap_minutes": float(dt.dt.total_seconds().div(60).max()),
            "invalid_ohlc_rows": int(invalid.sum()),
            "holdout_rows_loaded": int(raw.ts_utc.ge(holdout_start).sum()),
        }
    )
    if quality.duplicate_timestamps or quality.out_of_order_timestamps or quality.invalid_ohlc_rows:
        raise AssertionError(f"Raw quality gate failed:\n{quality}")
    if not allow_holdout and quality.holdout_rows_loaded:
        raise AssertionError("Holdout seal failed")

    bars = (
        raw.set_index("ts_utc")
        .resample("5min", label="left", closed="left")
        .agg(open=("open", "first"), high=("high", "max"), low=("low", "min"),
             close=("close", "last"), source_minutes=("close", "size"))
        .dropna(subset=["open", "high", "low", "close"])
        .reset_index()
        .rename(columns={"ts_utc": "bar_open"})
    )
    bars["bar_close"] = bars.bar_open + pd.Timedelta(minutes=5)
    bars["complete_5m"] = bars.source_minutes.eq(5)
    bars["contiguous"] = bars.bar_open.diff().eq(pd.Timedelta(minutes=5)) & bars.complete_5m & bars.complete_5m.shift(fill_value=False)
    bars["segment"] = (~bars.contiguous).cumsum().astype("int32")

    ny_open = bars.bar_open.dt.tz_convert(NY_TZ)
    ny_close = bars.bar_close.dt.tz_convert(NY_TZ)
    minute = ny_open.dt.hour * 60 + ny_open.dt.minute
    local_date = ny_open.dt.tz_localize(None).dt.normalize()
    bars["session_date"] = local_date + pd.to_timedelta(minute.ge(17 * 60).astype(int), unit="D")
    bars["session_slot"] = (((minute - 17 * 60) % 1440) // 5).astype("int16")
    bars["session_id"] = pd.factorize(bars.session_date, sort=True)[0].astype("int32")
    bars["force_friday_close"] = (
        ny_close.dt.weekday.eq(4) & ny_close.dt.hour.eq(17) & ny_close.dt.minute.eq(0)
    )
    # If the exact boundary is absent, the final pre-weekend bar is still closed.
    next_gap = bars.bar_open.shift(-1) - bars.bar_open
    bars.loc[ny_open.dt.weekday.eq(4) & next_gap.gt(pd.Timedelta(days=1)), "force_friday_close"] = True

    quality["five_minute_bars"] = len(bars)
    quality["partial_five_minute_bars"] = int((~bars.complete_5m).sum())
    quality["partial_five_minute_share"] = float((~bars.complete_5m).mean())
    quality["five_minute_gaps"] = int((bars.bar_open.diff() > pd.Timedelta(minutes=5)).sum())
    quality["friday_close_markers"] = int(bars.force_friday_close.sum())
    return bars, quality


def _rolling_grouped(series: pd.Series, segment: pd.Series, window: int, op: str) -> pd.Series:
    grouped = series.groupby(segment, sort=False)
    if op == "mean":
        return grouped.rolling(window, min_periods=window).mean().reset_index(level=0, drop=True)
    if op == "std0":
        return grouped.rolling(window, min_periods=window).std(ddof=0).reset_index(level=0, drop=True)
    if op == "sum":
        return grouped.rolling(window, min_periods=window).sum().reset_index(level=0, drop=True)
    raise ValueError(op)


def observed_bar_rolling(series: pd.Series, valid: pd.Series, window: int, op: str) -> pd.Series:
    """Roll over valid observed bars without resetting at wall-clock closures."""
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


@njit(cache=True)
def _causal_slot_percentile(values, sessions, lookback_sessions, min_obs):
    out = np.full(values.size, np.nan)
    for i in range(values.size):
        if not np.isfinite(values[i]):
            continue
        count = 0
        leq = 0
        j = i - 1
        lower = sessions[i] - lookback_sessions
        while j >= 0 and sessions[j] >= lower:
            if sessions[j] < sessions[i] and np.isfinite(values[j]):
                count += 1
                if values[j] <= values[i]:
                    leq += 1
            j -= 1
        if count >= min_obs:
            out[i] = leq / count
    return out


def causal_same_slot_percentile(
    values: pd.Series,
    slots: pd.Series,
    sessions: pd.Series,
    lookback_sessions: int = 90,
    min_fraction: float = 2 / 3,
) -> pd.Series:
    """Percentile versus prior sessions at the same NY-session five-minute slot."""
    out = np.full(len(values), np.nan)
    min_obs = int(np.ceil(lookback_sessions * min_fraction))
    for _, indices in slots.groupby(slots, sort=False).groups.items():
        idx = np.asarray(indices, dtype=np.int64)
        order = np.argsort(sessions.iloc[idx].to_numpy(), kind="stable")
        idx = idx[order]
        out[idx] = _causal_slot_percentile(
            values.iloc[idx].to_numpy(dtype=np.float64),
            sessions.iloc[idx].to_numpy(dtype=np.int64),
            lookback_sessions,
            min_obs,
        )
    return pd.Series(out, index=values.index)


def build_feature_frame(
    bars: pd.DataFrame,
    bb_lengths: Iterable[int],
    vei_pairs: Iterable[tuple[int, int]],
    trend_specs: Iterable[tuple[str, int]],
    slot_lookback_sessions: int = 90,
    slot_min_fraction: float = 2 / 3,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build causal bands and regime features; return frame and coverage report."""
    f = bars.copy()
    f.loc[~f.complete_5m, ["open", "high", "low", "close"]] = np.nan
    valid = f.complete_5m & f[["open", "high", "low", "close"]].notna().all(axis=1)
    f["valid_bar"] = valid
    f["gap_before"] = f.bar_open.diff().gt(pd.Timedelta(minutes=5))
    f["gap_minutes_before"] = f.bar_open.diff().dt.total_seconds().div(60)
    f["bars_since_gap"] = _bars_since(f.gap_before.to_numpy(bool))
    f["bars_to_next_gap"] = _bars_since(f.gap_before.iloc[::-1].to_numpy(bool))[::-1]
    seg = f.segment
    log_close = np.log(f.close)
    log_ret = log_close.diff().where(f.contiguous)
    f["log_return"] = log_ret
    f["rv5"] = log_ret.abs()
    f["rv30"] = np.sqrt(_rolling_grouped(log_ret.pow(2), seg, 6, "sum"))
    rms30 = f.rv30 / np.sqrt(6.0)
    f["rv_acceleration"] = np.log(f.rv5.clip(lower=1e-12) / rms30.clip(lower=1e-12))

    prev_close = f.close.shift().where(f.contiguous)
    tr = pd.concat(
        [(f.high - f.low), (f.high - prev_close).abs(), (f.low - prev_close).abs()], axis=1
    ).max(axis=1).where(f.complete_5m)
    f["true_range"] = tr

    for length in sorted(set(int(x) for x in bb_lengths)):
        # A chart-style moving average uses the last observed valid closes. Scheduled
        # rollover/weekend closures are not observations and do not reset its memory.
        f[f"bb_mid_{length}"] = observed_bar_rolling(f.close, valid, length, "mean")
        f[f"bb_sd_{length}"] = observed_bar_rolling(f.close, valid, length, "std0")

    for fast, slow in sorted(set((int(a), int(b)) for a, b in vei_pairs)):
        fast_atr = _rolling_grouped(tr, seg, fast, "mean")
        slow_atr = _rolling_grouped(tr, seg, slow, "mean")
        key = f"vei_{fast}_{slow}"
        ratio = fast_atr / slow_atr.replace(0, np.nan)
        f[key] = np.log(ratio.where(ratio > 0))

    pct_sources = ["rv30", "rv_acceleration"] + [f"vei_{a}_{b}" for a, b in sorted(set(vei_pairs))]
    for col in pct_sources:
        f[f"{col}_pct"] = causal_same_slot_percentile(
            f[col], f.session_slot, f.session_id, slot_lookback_sessions, slot_min_fraction
        )

    hourly = f.set_index("bar_close").close.resample("1h", label="right", closed="right").last()
    for kind, hours in sorted(set((str(k).lower(), int(h)) for k, h in trend_specs)):
        if kind == "sma":
            ma = hourly.rolling(hours, min_periods=hours).mean()
        elif kind == "ema":
            ma = hourly.ewm(span=hours, adjust=False, min_periods=hours).mean()
        else:
            raise ValueError(f"Unknown trend kind {kind}")
        aligned = ma.reindex(pd.DatetimeIndex(f.bar_close), method="ffill").to_numpy()
        prefix = f"trend_{kind}_{hours}h"
        f[f"{prefix}_ma"] = aligned
        displacement = np.log(f.close / f[f"{prefix}_ma"])
        f[f"{prefix}_direction"] = np.sign(displacement).astype("float32")
        f[f"{prefix}_strength"] = displacement.abs() / f.rv30.replace(0, np.nan)

    period = pd.cut(
        f.bar_open,
        bins=[pd.Timestamp("1900-01-01", tz="UTC"), pd.Timestamp("2021-01-01", tz="UTC"), HOLDOUT_START],
        labels=["development_pre2021", "evaluation_2021_2023"], right=False,
    )
    coverage_rows = []
    feature_cols = [c for c in f.columns if c.startswith(("bb_", "rv", "vei_", "trend_"))]
    for sample in period.cat.categories:
        mask = period.eq(sample)
        for col in feature_cols:
            coverage_rows.append(
                {"sample": sample, "feature": col, "rows": int(mask.sum()),
                 "defined": int(f.loc[mask, col].notna().sum()),
                 "missing": int(f.loc[mask, col].isna().sum()),
                 "coverage": float(f.loc[mask, col].notna().mean()) if mask.any() else np.nan}
            )
    return f, pd.DataFrame(coverage_rows)


@njit(cache=True)
def _simulate(open_, high, low, close, signal, stop_band_long, stop_band_short,
              segment, force_close, stop_slippage):
    n = len(open_)
    entry_i = np.empty(n, np.int64)
    exit_i = np.empty(n, np.int64)
    side_o = np.empty(n, np.int8)
    entry_px = np.empty(n, np.float64)
    exit_px = np.empty(n, np.float64)
    initial_stop = np.empty(n, np.float64)
    reason = np.empty(n, np.int8)  # 1 stop, 2 Friday, 3 sample end
    gap_stop = np.empty(n, np.int8)
    marketable_stop = np.empty(n, np.int8)
    k = 0
    side = 0
    ep = np.nan
    st = np.nan
    init_st = np.nan
    ei = -1

    for i in range(1, n):
        same_segment = segment[i] == segment[i - 1]
        was_flat = side == 0
        if was_flat and same_segment and signal[i - 1] != 0 and np.isfinite(open_[i]):
            side = signal[i - 1]
            ep = open_[i]
            ei = i
            st = stop_band_long[i - 1] if side == 1 else stop_band_short[i - 1]
            init_st = st
            if not np.isfinite(st):
                side = 0
                continue

        if side == 0:
            continue

        # A stop based on the previous completed bar ratchets before this open.
        if i > ei and same_segment:
            candidate = stop_band_long[i - 1] if side == 1 else stop_band_short[i - 1]
            if np.isfinite(candidate):
                if side == 1 and candidate > st:
                    st = candidate
                elif side == -1 and candidate < st:
                    st = candidate

        exit_now = False
        px = np.nan
        rsn = 0
        is_gap = 0
        is_marketable = 0
        if side == 1:
            if open_[i] <= st:
                px = open_[i] - stop_slippage
                exit_now, rsn, is_gap = True, 1, 1
                if i == ei:
                    is_marketable = 1
            elif low[i] <= st:
                px = st - stop_slippage
                exit_now, rsn = True, 1
        else:
            if open_[i] >= st:
                px = open_[i] + stop_slippage
                exit_now, rsn, is_gap = True, 1, 1
                if i == ei:
                    is_marketable = 1
            elif high[i] >= st:
                px = st + stop_slippage
                exit_now, rsn = True, 1

        if not exit_now and force_close[i]:
            px = close[i]
            exit_now, rsn = True, 2

        if exit_now:
            entry_i[k], exit_i[k], side_o[k] = ei, i, side
            entry_px[k], exit_px[k], initial_stop[k] = ep, px, init_st
            reason[k], gap_stop[k], marketable_stop[k] = rsn, is_gap, is_marketable
            k += 1
            side = 0

    if side != 0:
        i = n - 1
        entry_i[k], exit_i[k], side_o[k] = ei, i, side
        entry_px[k], exit_px[k], initial_stop[k] = ep, close[i], init_st
        reason[k], gap_stop[k], marketable_stop[k] = 3, 0, 0
        k += 1
    return (entry_i[:k], exit_i[:k], side_o[:k], entry_px[:k], exit_px[:k],
            initial_stop[:k], reason[:k], gap_stop[:k], marketable_stop[:k])


def run_config(frame: pd.DataFrame, pair: str, config: StrategyConfig) -> pd.DataFrame:
    mid = frame[f"bb_mid_{config.bb_length}"].to_numpy(float)
    sd = frame[f"bb_sd_{config.bb_length}"].to_numpy(float)
    close = frame.close.to_numpy(float)
    signal = np.where(close > mid + config.entry_sigma * sd, 1,
                      np.where(close < mid - config.entry_sigma * sd, -1, 0)).astype(np.int8)
    gate = frame.complete_5m.to_numpy(bool) & np.isfinite(mid) & np.isfinite(sd) & (sd > 0)
    if config.rv30_min_pct is not None:
        gate &= frame.rv30_pct.to_numpy(float) >= config.rv30_min_pct
    if config.acceleration_min_pct is not None:
        gate &= frame.rv_acceleration_pct.to_numpy(float) >= config.acceleration_min_pct
    if config.vei_min_pct is not None:
        col = f"vei_{config.vei_fast}_{config.vei_slow}_pct"
        gate &= frame[col].to_numpy(float) >= config.vei_min_pct
    if config.trend_kind is not None:
        prefix = f"trend_{config.trend_kind}_{config.trend_hours}h"
        direction = frame[f"{prefix}_direction"].to_numpy(float)
        strength = frame[f"{prefix}_strength"].to_numpy(float)
        gate &= np.isfinite(direction) & np.isfinite(strength)
        if config.trend_mode == "aligned":
            gate &= signal * direction > 0
        elif config.trend_mode == "counter":
            gate &= signal * direction < 0
        elif config.trend_mode != "any":
            raise ValueError(config.trend_mode)
        if config.trend_strength_min is not None:
            gate &= strength >= config.trend_strength_min
    signal = np.where(gate, signal, 0).astype(np.int8)

    pip_size = 0.01 if pair.endswith("JPY") else 0.0001
    arrays = _simulate(
        frame.open.to_numpy(float), frame.high.to_numpy(float), frame.low.to_numpy(float),
        close, signal, mid + config.stop_sigma * sd, mid - config.stop_sigma * sd,
        frame.segment.to_numpy(np.int64), frame.force_friday_close.to_numpy(bool),
        config.stop_slippage_pips * pip_size,
    )
    ei, xi, side, ep, xp, initial_stop, rsn, gap, marketable = arrays
    if not len(ei):
        return pd.DataFrame()
    risk = np.abs(ep - initial_stop)
    gross_price = side * (xp - ep)
    cost_price = config.round_trip_cost_pips * pip_size
    valid_risk = risk > 0
    gross_r = np.divide(gross_price, risk, out=np.full_like(risk, np.nan), where=valid_risk)
    net_r = np.divide(gross_price - cost_price, risk, out=np.full_like(risk, np.nan), where=valid_risk)
    reasons = np.array(["", "stop", "friday_close", "sample_end"], dtype=object)[rsn]
    out = pd.DataFrame(
        {
            "pair": pair, "config": config.name, "entry_index": ei, "exit_index": xi,
            "entry_time": frame.bar_open.iloc[ei].to_numpy(),
            "exit_time": frame.bar_close.iloc[xi].to_numpy(),
            "session_date": frame.session_date.iloc[xi].to_numpy(),
            "side": side, "entry_price": ep, "exit_price": xp, "initial_stop": initial_stop,
            "risk_price": risk, "gross_pips": gross_price / pip_size,
            "net_pips": (gross_price - cost_price) / pip_size,
            "gross_r": gross_r, "net_r": net_r, "exit_reason": reasons,
            "gap_stop": gap.astype(bool), "entry_stop_marketable": marketable.astype(bool),
            "holding_bars": xi - ei + 1,
        }
    )
    entry_ts = pd.to_datetime(out.entry_time, utc=True)
    out["year"] = entry_ts.dt.year
    out["sample"] = np.where(out.year < 2021, "development_pre2021",
                             np.where(out.year < 2024, "evaluation_2021_2023", "holdout_2024_plus"))
    for col in ["rv30_pct", "rv_acceleration_pct"]:
        out[col] = frame[col].iloc[np.maximum(ei - 1, 0)].to_numpy()
    signal_idx = np.maximum(ei - 1, 0)
    out["bars_since_gap"] = frame.bars_since_gap.iloc[signal_idx].to_numpy()
    out["bars_to_next_gap"] = frame.bars_to_next_gap.iloc[signal_idx].to_numpy()
    out["gap_minutes_before"] = frame.gap_minutes_before.iloc[signal_idx].to_numpy()
    if config.vei_fast is not None:
        col = f"vei_{config.vei_fast}_{config.vei_slow}_pct"
        out[col] = frame[col].iloc[np.maximum(ei - 1, 0)].to_numpy()
    if config.trend_kind is not None:
        prefix = f"trend_{config.trend_kind}_{config.trend_hours}h"
        out[f"{prefix}_strength"] = frame[f"{prefix}_strength"].iloc[np.maximum(ei - 1, 0)].to_numpy()
        out[f"{prefix}_alignment"] = side * frame[f"{prefix}_direction"].iloc[np.maximum(ei - 1, 0)].to_numpy()
    return out


def session_returns(trades: pd.DataFrame, r_col: str = "net_r") -> pd.Series:
    """Deployable session P&L: sum concurrent trade R, never mean trade R."""
    if trades.empty:
        return pd.Series(dtype=float)
    return trades.groupby(pd.to_datetime(trades.session_date), sort=True)[r_col].sum()


def performance_stats(trades: pd.DataFrame, r_col: str = "net_r") -> pd.Series:
    x = trades[r_col].dropna() if not trades.empty else pd.Series(dtype=float)
    sessions = session_returns(trades.loc[x.index], r_col) if len(x) else pd.Series(dtype=float)
    sd = sessions.std(ddof=1)
    downside_dev = np.sqrt(np.mean(np.square(np.minimum(sessions, 0.0)))) if len(sessions) else np.nan
    sharpe = np.sqrt(252) * sessions.mean() / sd if len(sessions) > 1 and sd > 0 else np.nan
    sortino = np.sqrt(252) * sessions.mean() / downside_dev if downside_dev and downside_dev > 0 else np.nan
    wins = x[x > 0]
    losses = x[x < 0]
    return pd.Series(
        {
            "trades": len(x), "active_sessions": len(sessions), "win_rate": float(x.gt(0).mean()) if len(x) else np.nan,
            "average_r": x.mean(), "median_r": x.median(), "average_win_r": wins.mean(),
            "average_loss_r": losses.mean(), "profit_factor": wins.sum() / -losses.sum() if losses.sum() < 0 else np.nan,
            "session_pooled_sharpe_active_only": sharpe, "session_pooled_sortino_active_only": sortino,
            "worst_session_r": sessions.min() if len(sessions) else np.nan,
        }
    )


def portfolio_equity(
    trades: pd.DataFrame,
    starting_balance: float = 10_000.0,
    risk_fraction: float = 0.01,
    r_col: str = "net_r",
) -> tuple[pd.DataFrame, pd.Series]:
    """Realised-equity simulation sizing each trade at entry-time equity.

    Open trades do not mark to market. Concurrent entries each risk ``risk_fraction``
    of the then-realised account equity; no portfolio leverage cap is imposed.
    """
    if trades.empty:
        return pd.DataFrame(columns=["time", "equity", "drawdown"]), pd.Series(dtype=float)
    t = trades.reset_index(drop=True).copy()
    events = []
    for i, row in t.iterrows():
        events.append((pd.Timestamp(row.entry_time), 0, i))
        events.append((pd.Timestamp(row.exit_time), 1, i))
    events.sort(key=lambda z: (z[0], z[1]))
    equity = float(starting_balance)
    risk_cash = {}
    rows = [{"time": events[0][0], "equity": equity}]
    for when, kind, i in events:
        if kind == 0:
            risk_cash[i] = equity * risk_fraction
        else:
            equity += risk_cash.pop(i) * float(t.loc[i, r_col])
            rows.append({"time": when, "equity": equity})
    curve = pd.DataFrame(rows).groupby("time", as_index=False).last().sort_values("time")
    curve["peak"] = curve.equity.cummax()
    curve["drawdown"] = curve.equity / curve.peak - 1.0
    elapsed_years = max((curve.time.iloc[-1] - curve.time.iloc[0]).total_seconds() / (365.2425 * 86400), 1 / 365.2425)
    cagr = (curve.equity.iloc[-1] / starting_balance) ** (1 / elapsed_years) - 1
    max_dd = -curve.drawdown.min()
    summary = pd.Series(
        {"starting_balance": starting_balance, "ending_balance": curve.equity.iloc[-1],
         "cagr": cagr, "max_drawdown": max_dd, "calmar": cagr / max_dd if max_dd > 0 else np.nan,
         "risk_fraction_per_trade": risk_fraction}
    )
    return curve, summary


def sharpe_by_group(trades: pd.DataFrame, groups: list[str], r_col: str = "net_r") -> pd.DataFrame:
    rows = []
    for keys, g in trades.groupby(groups, observed=True, dropna=False):
        keys = keys if isinstance(keys, tuple) else (keys,)
        row = dict(zip(groups, keys))
        row.update(performance_stats(g, r_col).to_dict())
        rows.append(row)
    return pd.DataFrame(rows)
