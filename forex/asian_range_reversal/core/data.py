from pathlib import Path

import numpy as np
import pandas as pd


SESSION_BOUNDS = {
    "Asian": (0, 420),
    "London": (420, 780),
    "NY_AM": (780, 1140),
    "NY_PM": (1140, 1440),
}


def load_discovery_minutes(path: Path, start: pd.Timestamp, end: pd.Timestamp, chunksize=750_000):
    """Retain only [start, end); stop at the first CSV chunk reaching end."""
    dtype = {c: "float32" for c in ["open", "high", "low", "close", "volume"]}
    kept, reached = [], False
    source_duplicates = source_out_of_order = 0
    previous = None
    for chunk in pd.read_csv(path, dtype=dtype, parse_dates=["time"], chunksize=chunksize):
        chunk["time"] = (chunk.time.dt.tz_localize("UTC") if chunk.time.dt.tz is None
                         else chunk.time.dt.tz_convert("UTC"))
        source_duplicates += int(chunk.time.duplicated().sum())
        source_out_of_order += int((chunk.time.diff().dropna() <= pd.Timedelta(0)).sum())
        if previous is not None and len(chunk) and chunk.time.iloc[0] <= previous:
            source_out_of_order += 1
        if len(chunk):
            previous = chunk.time.iloc[-1]
        part = chunk.loc[(chunk.time >= start) & (chunk.time < end)].copy()
        if len(part):
            kept.append(part)
        if chunk.time.ge(end).any():
            reached = True
            break
    raw = pd.concat(kept, ignore_index=True).sort_values("time", kind="stable").reset_index(drop=True)
    assert len(raw) and raw.time.min() >= start and raw.time.max() < end
    assert source_duplicates == 0 and source_out_of_order == 0

    ny = raw.time.dt.tz_convert("America/New_York")
    naive = ny.dt.tz_localize(None)
    minute_et = ny.dt.hour * 60 + ny.dt.minute
    raw["trading_date"] = naive.dt.normalize() + pd.to_timedelta((minute_et >= 1020).astype(int), unit="D")
    raw["slot"] = ((minute_et - 1020) % 1440).astype("int16")
    return raw, reached


def quality_report(raw, path: Path, reached):
    dt = raw.time.diff()
    bad = ((raw.high < raw[["open", "close", "low"]].max(axis=1)) |
           (raw.low > raw[["open", "close", "high"]].min(axis=1)))
    by_session = []
    for name, (lo, hi) in SESSION_BOUNDS.items():
        counts = raw.loc[raw.slot.between(lo, hi - 1)].groupby("trading_date").size()
        by_session.append({
            "session": name, "expected_bars": hi - lo,
            "median_bars": float(counts.median()), "min_bars": int(counts.min()),
            "days_95pct": int(counts.ge(0.95 * (hi - lo)).sum()),
        })
    slot_days = raw.groupby("slot").trading_date.nunique()
    total_days = raw.trading_date.nunique()
    return {
        "file": str(path), "file_bytes": path.stat().st_size,
        "rows": len(raw), "first": str(raw.time.min()), "last": str(raw.time.max()),
        "trading_days": total_days, "boundary_reached": bool(reached),
        "duplicates": int(raw.time.duplicated().sum()),
        "out_of_order": int((dt.dropna() <= pd.Timedelta(0)).sum()),
        "gaps_gt_1m": int(dt.gt(pd.Timedelta(minutes=1)).sum()),
        "largest_gap_min": float(dt.dt.total_seconds().div(60).max()),
        "ohlc_failures": int(bad.sum()),
        "nonpositive_prices": int((raw[["open","high","low","close"]] <= 0).any(axis=1).sum()),
        "volume_minus_one_share": float(raw.volume.eq(-1).mean()),
        "slot_0_day_share": float(slot_days.get(0, 0) / total_days),
        "slot_15_day_share": float(slot_days.get(15, 0) / total_days),
        "session_coverage": by_session,
    }


def _wilder_rsi(values, length):
    out = np.full(len(values), np.nan)
    if len(values) <= length:
        return out
    delta = np.diff(values.astype(float))
    gain = np.maximum(delta, 0.0)
    loss = np.maximum(-delta, 0.0)
    avg_gain, avg_loss = gain[:length].mean(), loss[:length].mean()
    out[length] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    for i in range(length + 1, len(values)):
        avg_gain = ((length - 1) * avg_gain + gain[i - 1]) / length
        avg_loss = ((length - 1) * avg_loss + loss[i - 1]) / length
        out[i] = 100.0 if avg_loss == 0 else 100.0 - 100.0 / (1.0 + avg_gain / avg_loss)
    return out


def _wilder_atr(high, low, close, length):
    out = np.full(len(close), np.nan)
    if len(close) < length:
        return out
    prev = np.r_[np.nan, close[:-1]]
    tr = np.maximum(high - low, np.maximum(np.abs(high - prev), np.abs(low - prev)))
    tr[0] = high[0] - low[0]
    atr = tr[:length].mean()
    out[length - 1] = atr
    for i in range(length, len(close)):
        atr = ((length - 1) * atr + tr[i]) / length
        out[i] = atr
    return out


def build_five_minute(raw, rsi_length=14, atr_length=14):
    work = raw.copy()
    work["bucket"] = (work.slot // 5).astype("int16")
    grouped = work.groupby(["trading_date", "bucket"], sort=True)
    bars = grouped.agg(
        time=("time", "first"), slot_start=("slot", "min"), slot_end=("slot", "max"),
        minute_count=("slot", "size"), open=("open", "first"), high=("high", "max"),
        low=("low", "min"), close=("close", "last"),
    ).reset_index()
    bars = bars.loc[(bars.minute_count == 5) & (bars.slot_end == bars.slot_start + 4) &
                    (bars.slot_start == bars.bucket * 5)].copy()
    bars = bars.sort_values("time").reset_index(drop=True)
    new_segment = bars.time.diff().ne(pd.Timedelta(minutes=5))
    bars["segment"] = new_segment.cumsum()
    bars["rsi"] = np.nan
    bars["atr"] = np.nan
    for _, idx in bars.groupby("segment").groups.items():
        ii = np.asarray(idx)
        bars.loc[ii, "rsi"] = _wilder_rsi(bars.loc[ii, "close"].to_numpy(), rsi_length)
        bars.loc[ii, "atr"] = _wilder_atr(
            bars.loc[ii, "high"].to_numpy(float), bars.loc[ii, "low"].to_numpy(float),
            bars.loc[ii, "close"].to_numpy(float), atr_length)
    return bars


def eligible_days(raw, minimum=0.95):
    counts = raw.groupby(["trading_date", pd.cut(raw.slot, [-1,419,779,1139,1439],
                         labels=list(SESSION_BOUNDS), ordered=True)], observed=True).size().unstack(fill_value=0)
    mask = np.ones(len(counts), dtype=bool)
    for name, (lo, hi) in SESSION_BOUNDS.items():
        mask &= counts[name].to_numpy() >= minimum * (hi - lo)
    last = raw.groupby("trading_date").slot.max().reindex(counts.index)
    mask &= last.to_numpy() == 1439
    return set(counts.index[mask]), counts
