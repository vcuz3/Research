"""Causal signal-bar features for the anchored TWAP/SMA Z-band strategy.

The strategy consumes completed coarse bars.  Execution is deliberately kept in
``backtest_engine/engine.py`` so feature construction cannot accidentally decide
fills with future information.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable

import numpy as np
import pandas as pd
from numba import njit


PAIRS = ("AUDUSD", "EURUSD", "GBPUSD", "NZDUSD")
PIP_SIZE = 0.0001
TRAIN_END = pd.Timestamp("2020-01-01")
OOS_START = pd.Timestamp("2021-01-01")
HOLDOUT_START = pd.Timestamp("2024-01-01")


@dataclass(frozen=True)
class StrategyConfig:
    """Frozen strategy and execution inputs.

    User-confirmed baseline parameters are ``arm_z=2.5`` and
    ``atr_stop_mult=2.0``.  The bar-close signal enters at the next observed
    complete signal bar's open.  Costs are an explicit research overlay because
    the midpoint OHLC archive has no bid/ask quotes.
    """

    name: str = "session_twap"
    anchor_mode: str = "session"  # session | sma
    sma_length: int = 20
    bar_minutes: int = 15
    arm_z: float = 2.5
    max_arm_bars: int = 10
    atr_length: int = 14
    atr_stop_mult: float = 2.0
    target_r: float = 1.0
    price_source: str = "hlc3"
    session_timezone: str = "America/New_York"
    session_start_hour: int = 17
    round_trip_cost_pips: float = 1.0

    def validate(self) -> None:
        if self.anchor_mode not in {"session", "sma"}:
            raise ValueError(f"Unknown anchor_mode={self.anchor_mode!r}")
        if self.price_source not in {"close", "hlc3", "ohlc4"}:
            raise ValueError(f"Unknown price_source={self.price_source!r}")
        for field in ("sma_length", "bar_minutes", "max_arm_bars", "atr_length"):
            if getattr(self, field) < 1:
                raise ValueError(f"{field} must be positive")
        for field in ("arm_z", "atr_stop_mult", "target_r"):
            if getattr(self, field) <= 0:
                raise ValueError(f"{field} must be positive")
        if self.round_trip_cost_pips < 0:
            raise ValueError("round_trip_cost_pips cannot be negative")


def baseline_candidates() -> list[StrategyConfig]:
    """Small, prespecified training search that keeps the user's risk rules fixed."""

    base = StrategyConfig()
    out = [base]
    out.extend(
        replace(base, name=f"sma_{length}", anchor_mode="sma", sma_length=length)
        for length in (10, 20, 40, 80)
    )
    return out


def sample_name(ts: pd.Series | pd.DatetimeIndex) -> np.ndarray:
    """Label the requested windows; calendar 2020 is an unused embargo."""

    values = pd.DatetimeIndex(ts)
    return np.select(
        [
            values < TRAIN_END,
            (values >= TRAIN_END) & (values < OOS_START),
            (values >= OOS_START) & (values < HOLDOUT_START),
            values >= HOLDOUT_START,
        ],
        ["train_pre2020", "embargo_2020_unused", "oos_2021_2023", "holdout_2024_latest"],
        default="outside",
    )


def load_raw_minutes(pair: str, data_dir: Path, end: pd.Timestamp | None = None) -> pd.DataFrame:
    """Load one clean midpoint OHLC file without silently sorting bad timestamps."""

    if pair not in PAIRS:
        raise ValueError(f"pair must be one of {PAIRS}")
    path = Path(data_dir) / f"{pair}_1m_clean.parquet"
    raw = pd.read_parquet(path, columns=["ts_utc", "open", "high", "low", "close"])
    if end is not None:
        raw = raw.loc[raw.ts_utc < pd.Timestamp(end)].copy()
    raw.reset_index(drop=True, inplace=True)
    raw["raw_i"] = np.arange(len(raw), dtype=np.int64)
    return raw


def raw_data_quality(raw: pd.DataFrame, pair: str) -> pd.DataFrame:
    """Executable core-load quality gate, reported by requested sample."""

    ts = raw.ts_utc
    delta = ts.diff().dt.total_seconds().div(60)
    invalid_ohlc = (
        raw[["open", "high", "low", "close"]].isna().any(axis=1)
        | (raw.high < raw[["open", "close"]].max(axis=1))
        | (raw.low > raw[["open", "close"]].min(axis=1))
        | (raw.high < raw.low)
    )
    labels = sample_name(ts)
    rows: list[dict] = []
    for sample in np.unique(labels):
        mask = labels == sample
        d = delta.loc[mask]
        rows.append(
            {
                "pair": pair,
                "sample": sample,
                "first_ts": ts.loc[mask].min(),
                "last_ts": ts.loc[mask].max(),
                "minute_rows": int(mask.sum()),
                "duplicate_ts": int(ts.loc[mask].duplicated().sum()),
                "out_of_order": int((d <= 0).sum()),
                "invalid_ohlc": int(invalid_ohlc.loc[mask].sum()),
                "gaps_gt_1m": int((d > 1).sum()),
                "short_gap_missing_minutes_le180": int(np.maximum(d[(d > 1) & (d <= 180)] - 1, 0).sum()),
                "long_closure_gaps_gt180": int((d > 180).sum()),
                "max_gap_minutes": float(d.max()) if d.notna().any() else np.nan,
                "roll_boundaries": 0,
                "roll_policy": "not_applicable_spot_fx",
            }
        )
    return pd.DataFrame(rows)


@njit(cache=True)
def _wilder_rma(values: np.ndarray, length: int) -> np.ndarray:
    """TradingView-style Wilder average seeded by the first length-value SMA."""

    out = np.full(values.size, np.nan)
    if values.size < length:
        return out
    start = -1
    for i in range(length - 1, values.size):
        ok = True
        total = 0.0
        for j in range(i - length + 1, i + 1):
            if not np.isfinite(values[j]):
                ok = False
                break
            total += values[j]
        if ok:
            out[i] = total / length
            start = i
            break
    if start < 0:
        return out
    alpha = 1.0 / length
    for i in range(start + 1, values.size):
        if np.isfinite(values[i]):
            out[i] = out[i - 1] + alpha * (values[i] - out[i - 1])
        else:
            out[i] = out[i - 1]
    return out


def _source_price(bars: pd.DataFrame, source: str) -> pd.Series:
    if source == "close":
        return bars.close
    if source == "hlc3":
        return (bars.high + bars.low + bars.close) / 3.0
    if source == "ohlc4":
        return (bars.open + bars.high + bars.low + bars.close) / 4.0
    raise ValueError(source)


def build_signal_bars(
    raw: pd.DataFrame,
    configs: Iterable[StrategyConfig],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Aggregate complete signal bars and build all causal candidate features."""

    configs = list(configs)
    if not configs:
        raise ValueError("At least one config is required")
    for cfg in configs:
        cfg.validate()
    bar_minutes = configs[0].bar_minutes
    if any(c.bar_minutes != bar_minutes for c in configs):
        raise ValueError("All configs in one feature frame must share bar_minutes")

    indexed = raw.set_index("ts_utc", drop=False)
    rule = f"{bar_minutes}min"
    bars_all = indexed.resample(rule, origin="epoch", label="left", closed="left").agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        minute_count=("close", "count"),
        raw_start_i=("raw_i", "first"),
        raw_end_i=("raw_i", "last"),
    )
    bars_all.index.name = "bar_open"
    bars_all.reset_index(inplace=True)
    bars_all["complete_bar"] = bars_all.minute_count.eq(bar_minutes)

    coverage = bars_all.loc[bars_all.minute_count.gt(0), ["bar_open", "minute_count", "complete_bar"]].copy()
    coverage["sample"] = sample_name(coverage.bar_open)
    coverage["utc_hour"] = coverage.bar_open.dt.hour
    coverage_report = (
        coverage.groupby(["sample", "utc_hour"], observed=True)
        .agg(observed_intervals=("minute_count", "size"), complete_bars=("complete_bar", "sum"), raw_minutes=("minute_count", "sum"))
        .reset_index()
    )
    coverage_report["complete_share"] = coverage_report.complete_bars / coverage_report.observed_intervals

    bars = bars_all.loc[bars_all.complete_bar].copy().reset_index(drop=True)
    bars[["raw_start_i", "raw_end_i", "minute_count"]] = bars[["raw_start_i", "raw_end_i", "minute_count"]].astype("int64")

    first = configs[0]
    local = bars.bar_open.dt.tz_localize("UTC").dt.tz_convert(first.session_timezone)
    shifted = local - pd.Timedelta(hours=first.session_start_hour)
    bars["session_id"] = shifted.dt.strftime("%Y-%m-%d")
    bars["session_slot"] = ((local.dt.hour - first.session_start_hour) % 24) * 60 + local.dt.minute
    bars["sample"] = sample_name(bars.bar_open)
    bars["utc_hour"] = bars.bar_open.dt.hour.astype("int8")

    source = _source_price(bars, first.price_source)
    bars["source_price"] = source
    grouped = source.groupby(bars.session_id, sort=False)
    count = grouped.cumcount() + 1
    bars["session_twap"] = grouped.cumsum() / count
    residual = source - bars.session_twap
    bars["session_std"] = np.sqrt(residual.pow(2).groupby(bars.session_id, sort=False).cumsum() / count)
    bars.loc[count.eq(1), "session_std"] = np.nan

    for length in sorted({c.sma_length for c in configs if c.anchor_mode == "sma"}):
        bars[f"sma_{length}"] = source.rolling(length, min_periods=length).mean()
        bars[f"sma_std_{length}"] = source.rolling(length, min_periods=length).std(ddof=0)

    prev_close = bars.close.shift(1)
    true_range = pd.concat(
        [
            bars.high - bars.low,
            (bars.high - prev_close).abs(),
            (bars.low - prev_close).abs(),
        ],
        axis=1,
    ).max(axis=1)
    true_range.iloc[0] = bars.high.iloc[0] - bars.low.iloc[0]
    for length in sorted({c.atr_length for c in configs}):
        bars[f"atr_{length}"] = _wilder_rma(true_range.to_numpy(float), length)

    return bars, coverage_report


def active_arrays(bars: pd.DataFrame, config: StrategyConfig) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Return the selected baseline, dispersion, and ATR arrays."""

    config.validate()
    if config.anchor_mode == "session":
        baseline = bars.session_twap.to_numpy(float)
        stdev = bars.session_std.to_numpy(float)
    else:
        baseline = bars[f"sma_{config.sma_length}"].to_numpy(float)
        stdev = bars[f"sma_std_{config.sma_length}"].to_numpy(float)
    atr = bars[f"atr_{config.atr_length}"].to_numpy(float)
    return baseline, stdev, atr

