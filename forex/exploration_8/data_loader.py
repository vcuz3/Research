"""Load and align the three local midpoint FX archives used by the notebook."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd


PAIR_PATHS = {
    "audusd": ("clean/AUDUSD_1m_clean.parquet", "ts_utc"),
    "audjpy": ("audjpy_intraday_1min.csv", "time"),
    "usdjpy": ("USDJPY_1m.parquet", "ts"),
}
OHLC = ["open", "high", "low", "close"]


@dataclass(frozen=True)
class TriangleData:
    panel: pd.DataFrame
    audusd_bars: pd.DataFrame
    audusd_1m: pd.DataFrame
    minute_panel: pd.DataFrame | None
    raw_quality: pd.DataFrame
    bar_coverage: pd.DataFrame
    alignment: pd.Series


def _utc_naive(values: pd.Series) -> pd.Series:
    return pd.to_datetime(values, utc=True, errors="raise").dt.tz_convert(None)


def _read_parquet_window(path: Path, timestamp: str, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    columns = [timestamp, *OHLC]
    # Pandas delegates row-group filtering to pyarrow where the archive permits it.
    try:
        frame = pd.read_parquet(
            path,
            columns=columns,
            filters=[(timestamp, ">=", start.to_pydatetime()), (timestamp, "<", end.to_pydatetime())],
        )
    except (TypeError, ValueError):
        frame = pd.read_parquet(path, columns=columns)
    frame[timestamp] = _utc_naive(frame[timestamp])
    return frame.loc[(frame[timestamp] >= start) & (frame[timestamp] < end)].rename(columns={timestamp: "ts"})


def _read_audjpy_window(path: Path, start: pd.Timestamp, end: pd.Timestamp) -> pd.DataFrame:
    pieces: list[pd.DataFrame] = []
    for chunk in pd.read_csv(path, usecols=["time", *OHLC], chunksize=500_000):
        chunk["time"] = _utc_naive(chunk["time"])
        if chunk["time"].max() < start:
            continue
        keep = chunk.loc[(chunk["time"] >= start) & (chunk["time"] < end)]
        if not keep.empty:
            pieces.append(keep)
        if chunk["time"].min() >= end or chunk["time"].max() >= end:
            break
    if not pieces:
        raise ValueError(f"AUDJPY has no rows in [{start}, {end})")
    return pd.concat(pieces, ignore_index=True).rename(columns={"time": "ts"})


def _quality_row(pair: str, frame: pd.DataFrame) -> dict[str, object]:
    ts = frame["ts"]
    delta = ts.diff().dt.total_seconds().div(60)
    invalid_ohlc = (
        frame[OHLC].isna().any(axis=1)
        | (frame[OHLC] <= 0).any(axis=1)
        | (frame["high"] < frame[["open", "close"]].max(axis=1))
        | (frame["low"] > frame[["open", "close"]].min(axis=1))
        | (frame["high"] < frame["low"])
    )
    intra = delta.gt(1) & delta.lt(24 * 60)
    return {
        "pair": pair.upper(),
        "rows": int(len(frame)),
        "first_ts": ts.min(),
        "last_ts": ts.max(),
        "duplicate_ts": int(ts.duplicated().sum()),
        "out_of_order": int(ts.diff().lt(pd.Timedelta(0)).sum()),
        "invalid_ohlc": int(invalid_ohlc.sum()),
        "unexpected_gap_count_lt_24h": int(intra.sum()),
        "missing_minutes_lt_24h": int(np.maximum(delta.loc[intra].to_numpy() - 1, 0).sum()),
        "market_break_count_ge_24h": int(delta.ge(24 * 60).sum()),
        "saturday_rows": int(ts.dt.dayofweek.eq(5).sum()),
    }


def _resample_complete(frame: pd.DataFrame, pair: str, minutes: int) -> tuple[pd.DataFrame, pd.DataFrame]:
    indexed = frame.set_index("ts").sort_index()
    rule = f"{minutes}min"
    resampler = indexed.resample(rule, label="right", closed="left")
    bars = resampler.agg({"open": "first", "high": "max", "low": "min", "close": "last"})
    count = resampler["close"].count().rename("raw_minutes")
    observed = count.gt(0)
    complete = count.eq(minutes)
    quality = pd.DataFrame({"raw_minutes": count.loc[observed], "complete": complete.loc[observed]})
    quality["pair"] = pair.upper()
    quality["year"] = quality.index.year
    quality["utc_hour"] = quality.index.hour
    coverage = (
        quality.groupby(["pair", "year", "utc_hour"], observed=True)
        .agg(observed_intervals=("complete", "size"), complete_bars=("complete", "sum"), raw_minutes=("raw_minutes", "sum"))
        .reset_index()
    )
    bars = bars.loc[complete, OHLC].copy()
    bars.columns = [f"{pair}_{column}" for column in bars.columns]
    return bars, coverage


def load_triangle_data(
    project_root: str | Path,
    start: str | pd.Timestamp,
    end: str | pd.Timestamp,
    timeframe_minutes: int,
    include_minute_panel: bool = False,
) -> TriangleData:
    """Load a half-open UTC date window and retain only synchronous complete bars.

    AUDUSD is the canonical session calendar. The final inner join removes any
    padded rows in another archive and never forward-fills a missing quote.
    """
    if timeframe_minutes not in {1, 5, 15, 30, 60}:
        raise ValueError("timeframe_minutes must be one of 1, 5, 15, 30, or 60")
    project_root = Path(project_root).resolve()
    data_root = project_root.parent / "data"
    start_ts = pd.Timestamp(start)
    end_ts = pd.Timestamp(end)
    if start_ts.tzinfo is not None:
        start_ts = start_ts.tz_convert("UTC").tz_localize(None)
    if end_ts.tzinfo is not None:
        end_ts = end_ts.tz_convert("UTC").tz_localize(None)
    if not start_ts < end_ts:
        raise ValueError("start must be earlier than end")

    raw: dict[str, pd.DataFrame] = {}
    raw["audusd"] = _read_parquet_window(data_root / PAIR_PATHS["audusd"][0], "ts_utc", start_ts, end_ts)
    raw["audjpy"] = _read_audjpy_window(data_root / PAIR_PATHS["audjpy"][0], start_ts, end_ts)
    raw["usdjpy"] = _read_parquet_window(data_root / PAIR_PATHS["usdjpy"][0], "ts", start_ts, end_ts)

    quality_rows: list[dict[str, object]] = []
    bars: dict[str, pd.DataFrame] = {}
    coverage: list[pd.DataFrame] = []
    for pair, frame in raw.items():
        quality_rows.append(_quality_row(pair, frame))
        if quality_rows[-1]["duplicate_ts"] or quality_rows[-1]["out_of_order"] or quality_rows[-1]["invalid_ohlc"]:
            raise ValueError(f"{pair.upper()} failed the raw data-quality gate: {quality_rows[-1]}")
        bars[pair], pair_coverage = _resample_complete(frame, pair, timeframe_minutes)
        coverage.append(pair_coverage)

    canonical = bars["audusd"].index
    panel = bars["audusd"].join(bars["audjpy"], how="inner").join(bars["usdjpy"], how="inner")
    alignment = pd.Series(
        {
            "timeframe_minutes": timeframe_minutes,
            "audusd_complete_bars": len(bars["audusd"]),
            "audjpy_complete_bars": len(bars["audjpy"]),
            "usdjpy_complete_bars": len(bars["usdjpy"]),
            "aligned_complete_bars": len(panel),
            "canonical_audusd_bars_dropped_at_join": int(len(canonical.difference(panel.index))),
            "aligned_first_ts": panel.index.min(),
            "aligned_last_ts": panel.index.max(),
        },
        name="value",
    )
    if panel.empty:
        raise ValueError("No synchronous complete bars remain after alignment")
    minute_panel = None
    if include_minute_panel:
        minute_parts = []
        for pair, frame in raw.items():
            part = frame.set_index("ts")[["open", "close"]].sort_index()
            part.columns = [f"{pair}_{column}" for column in part.columns]
            minute_parts.append(part)
        minute_panel = minute_parts[0].join(minute_parts[1], how="inner").join(minute_parts[2], how="inner")
        if not minute_panel.index.is_unique or not minute_panel.index.is_monotonic_increasing:
            raise ValueError("Aligned one-minute panel failed index invariants")

    return TriangleData(
        panel=panel,
        audusd_bars=bars["audusd"],
        audusd_1m=raw["audusd"].set_index("ts").sort_index(),
        minute_panel=minute_panel,
        raw_quality=pd.DataFrame(quality_rows),
        bar_coverage=pd.concat(coverage, ignore_index=True),
        alignment=alignment,
    )
