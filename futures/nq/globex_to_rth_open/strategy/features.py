"""Build causal daily features and exact-clock NQ overnight trade candidates."""
from __future__ import annotations

from hashlib import sha256
from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

NY_TZ = "America/New_York"
RTH_OPEN_MINUTE = 9 * 60 + 30
RTH_END_MINUTE = 16 * 60
GLOBEX_ENTRY_MINUTE = 18 * 60
EXPECTED_HOLDING_MINUTES = 15 * 60 + 30
EXPECTED_ANCHOR_BARS = EXPECTED_HOLDING_MINUTES + 1


def file_sha256(path: Path, chunk_size: int = 1 << 20) -> str:
    digest = sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(chunk_size), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _json_value(value: Any) -> Any:
    if isinstance(value, (pd.Timestamp, np.datetime64)):
        return str(value)
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        return float(value)
    return value


def load_nq_minutes(path: Path) -> pd.DataFrame:
    """Load the clean continuous-contract minute file without altering prices."""
    columns = ["ts_utc", "symbol", "open", "high", "low", "close", "volume", "is_roll"]
    frame = pd.read_parquet(path, columns=columns)
    frame["ts_utc"] = pd.to_datetime(frame["ts_utc"], utc=True)
    frame = frame.sort_values("ts_utc", kind="stable").reset_index(drop=True)
    local = frame["ts_utc"].dt.tz_convert(NY_TZ)
    frame["local_date"] = local.dt.tz_localize(None).dt.normalize()
    frame["local_minute"] = local.dt.hour * 60 + local.dt.minute
    return frame


def audit_nq_minutes(frame: pd.DataFrame) -> tuple[dict[str, Any], pd.DataFrame]:
    """Executable rule-9a audit for the minute source and clock coverage."""
    raw_ts = frame["ts_utc"]
    gaps = raw_ts.diff().dt.total_seconds().div(60)
    invalid_ohlc = (
        (frame["high"] < frame[["open", "close", "low"]].max(axis=1))
        | (frame["low"] > frame[["open", "close", "high"]].min(axis=1))
        | (frame[["open", "high", "low", "close"]] <= 0).any(axis=1)
    )
    by_minute = (
        frame.groupby("local_minute", sort=True)
        .agg(rows=("ts_utc", "size"), dates=("local_date", "nunique"),
             first=("local_date", "min"), last=("local_date", "max"))
        .reindex(range(1440), fill_value=0)
        .reset_index()
    )
    by_year = frame.groupby(frame["local_date"].dt.year).size()
    quality = {
        "rows": len(frame),
        "first_ts_utc": str(raw_ts.min()),
        "last_ts_utc": str(raw_ts.max()),
        "duplicate_timestamps": int(raw_ts.duplicated().sum()),
        "out_of_order_timestamps": int((raw_ts.diff().dropna() < pd.Timedelta(0)).sum()),
        "gaps_over_one_minute": int((gaps > 1).sum()),
        "largest_gap_minutes": float(gaps.max()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "roll_boundaries": int(frame["is_roll"].sum()),
        "contracts": int(frame["symbol"].nunique()),
        "rows_by_year": {str(k): int(v) for k, v in by_year.items()},
        "entry_clock_rows": int((frame["local_minute"] == GLOBEX_ENTRY_MINUTE).sum()),
        "exit_clock_rows": int((frame["local_minute"] == RTH_OPEN_MINUTE).sum()),
    }
    return quality, by_minute


def load_vix_daily(path: Path, reference_lookback: int, reference_min_obs: int) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Load the named daily VIX export; each date's close is available by 18:00 ET."""
    raw = pd.read_csv(path, usecols=["time", "open", "high", "low", "close"])
    raw["vix_date"] = (
        pd.to_datetime(raw["time"], errors="raise").dt.normalize().astype("datetime64[ns]")
    )
    duplicate_dates = int(raw["vix_date"].duplicated().sum())
    out_of_order = int((raw["vix_date"].diff().dropna() < pd.Timedelta(0)).sum())
    vix = raw.sort_values("vix_date", kind="stable").drop_duplicates("vix_date", keep="last")
    vix = vix.rename(columns={"close": "vix_close", "open": "vix_open",
                              "high": "vix_high", "low": "vix_low"})
    vix = vix[["vix_date", "vix_open", "vix_high", "vix_low", "vix_close"]].reset_index(drop=True)
    vix["vix_ref"] = vix["vix_close"].shift(1).rolling(
        reference_lookback, min_periods=reference_min_obs).median()
    invalid_ohlc = (
        (vix["vix_high"] < vix[["vix_open", "vix_close", "vix_low"]].max(axis=1))
        | (vix["vix_low"] > vix[["vix_open", "vix_close", "vix_high"]].min(axis=1))
        | (vix[["vix_open", "vix_high", "vix_low", "vix_close"]] <= 0).any(axis=1)
    )
    quality = {
        "rows_raw": len(raw),
        "rows": len(vix),
        "first_date": str(vix["vix_date"].min().date()),
        "last_date": str(vix["vix_date"].max().date()),
        "duplicate_dates": duplicate_dates,
        "out_of_order_dates": out_of_order,
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "nonpositive_close": int((vix["vix_close"] <= 0).sum()),
        "reference_underpopulated": int(vix["vix_ref"].isna().sum()),
        "reference_policy": f"shift(1), rolling median {reference_lookback}, min_obs {reference_min_obs}",
    }
    return vix, quality


def build_rth_daily(
    frame: pd.DataFrame,
    ma_windows: Iterable[int],
    reference_lookback: int,
    reference_min_obs: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Aggregate completed 09:30-15:59 ET sessions and build causal features."""
    rth = frame.loc[frame["local_minute"].between(RTH_OPEN_MINUTE, RTH_END_MINUTE - 1)].copy()
    daily = (
        rth.groupby("local_date", sort=True)
        .agg(
            rth_open=("open", "first"), rth_high=("high", "max"),
            rth_low=("low", "min"), rth_close=("close", "last"),
            rth_rows=("ts_utc", "size"), first_minute=("local_minute", "min"),
            last_minute=("local_minute", "max"), first_symbol=("symbol", "first"),
            last_symbol=("symbol", "last"), roll_rows=("is_roll", "sum"),
        )
        .reset_index()
        .rename(columns={"local_date": "feature_date"})
    )
    prior_close = daily["rth_close"].shift(1)
    daily["prev_day_tr"] = np.maximum.reduce([
        (daily["rth_high"] - daily["rth_low"]).to_numpy(),
        (daily["rth_high"] - prior_close).abs().to_numpy(),
        (daily["rth_low"] - prior_close).abs().to_numpy(),
    ])
    daily.loc[prior_close.isna(), "prev_day_tr"] = np.nan
    daily["atr14"] = daily["prev_day_tr"].rolling(14, min_periods=14).mean()
    for window in sorted(set(int(x) for x in ma_windows)):
        daily[f"sma_{window}"] = daily["rth_close"].rolling(window, min_periods=window).mean()
    for proxy in ("atr14", "prev_day_tr"):
        daily[f"{proxy}_ref"] = daily[proxy].shift(1).rolling(
            reference_lookback, min_periods=reference_min_obs).median()

    quality = {
        "sessions": len(daily),
        "first_session": str(daily["feature_date"].min().date()),
        "last_session": str(daily["feature_date"].max().date()),
        "median_rth_rows": float(daily["rth_rows"].median()),
        "sessions_missing_0930": int((daily["first_minute"] != RTH_OPEN_MINUTE).sum()),
        "sessions_missing_1559": int((daily["last_minute"] != RTH_END_MINUTE - 1).sum()),
        "sessions_under_390_rows": int((daily["rth_rows"] < 390).sum()),
        "sessions_with_rth_roll": int((daily["roll_rows"] > 0).sum()),
        "underpopulated_windows": {
            "atr14": int(daily["atr14"].isna().sum()),
            "atr14_ref": int(daily["atr14_ref"].isna().sum()),
            "prev_day_tr_ref": int(daily["prev_day_tr_ref"].isna().sum()),
            **{f"sma_{w}": int(daily[f"sma_{w}"].isna().sum()) for w in sorted(set(ma_windows))},
        },
        "window_policy": "strict full lookback for indicators; sizing reference is shifted one session",
    }
    return daily, quality


def _rolls_inside(frame: pd.DataFrame, entries: pd.Series, exits: pd.Series) -> np.ndarray:
    roll_ns = frame.loc[frame["is_roll"], "ts_utc"].astype("int64").to_numpy()
    entry_ns = entries.astype("int64").to_numpy()
    exit_ns = exits.astype("int64").to_numpy()
    # A roll on the entry bar is already reflected in its tradable open; only later
    # substitutions are forbidden inside the holding interval.
    return np.searchsorted(roll_ns, exit_ns, side="right") - np.searchsorted(
        roll_ns, entry_ns, side="right")


def build_trade_candidates(
    frame: pd.DataFrame,
    daily: pd.DataFrame,
    vix: pd.DataFrame,
    ma_windows: Iterable[int],
    max_feature_staleness_days: int,
    reference_lookback: int,
    reference_min_obs: int,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Pair exact 18:00 ET entries with exact next-date 09:30 ET exits."""
    entry = frame.loc[frame["local_minute"] == GLOBEX_ENTRY_MINUTE, [
        "ts_utc", "local_date", "open", "symbol", "is_roll"]].copy()
    entry = entry.rename(columns={"ts_utc": "entry_ts", "local_date": "entry_date",
                                  "open": "entry_price", "symbol": "entry_symbol",
                                  "is_roll": "entry_is_roll"})
    entry["trade_date"] = entry["entry_date"] + pd.Timedelta(days=1)

    exit_frame = frame.loc[frame["local_minute"] == RTH_OPEN_MINUTE, [
        "ts_utc", "local_date", "open", "symbol"]].copy()
    exit_frame = exit_frame.rename(columns={"ts_utc": "exit_ts", "local_date": "trade_date",
                                            "open": "exit_price", "symbol": "exit_symbol"})
    if entry["entry_date"].duplicated().any() or exit_frame["trade_date"].duplicated().any():
        raise ValueError("duplicate exact-clock anchor on a local date")
    trades = entry.merge(exit_frame, on="trade_date", how="inner", validate="one_to_one")
    trades["same_contract"] = trades["entry_symbol"].eq(trades["exit_symbol"])
    trades["rolls_inside"] = _rolls_inside(frame, trades["entry_ts"], trades["exit_ts"])

    # Report missing traded-minute bars inside each holding window. Fixed-clock P&L
    # only needs the two anchors, so internal sparsity is reported but not imputed.
    overnight = frame.loc[
        (frame["local_minute"] >= GLOBEX_ENTRY_MINUTE)
        | (frame["local_minute"] <= RTH_OPEN_MINUTE), ["local_date", "local_minute"]].copy()
    overnight["trade_date"] = overnight["local_date"] + pd.to_timedelta(
        (overnight["local_minute"] >= GLOBEX_ENTRY_MINUTE).astype(int), unit="D")
    counts = overnight.groupby("trade_date").size().rename("holding_window_rows")
    trades = trades.merge(counts, on="trade_date", how="left")
    trades["holding_window_missing_rows"] = EXPECTED_ANCHOR_BARS - trades["holding_window_rows"]

    feature_columns = [
        "feature_date", "rth_close", "prev_day_tr", "atr14",
        "prev_day_tr_ref", "atr14_ref", "rth_rows",
        *[f"sma_{int(w)}" for w in sorted(set(ma_windows))],
    ]
    trades = pd.merge_asof(
        trades.sort_values("entry_date"), daily[feature_columns].sort_values("feature_date"),
        left_on="entry_date", right_on="feature_date", direction="backward",
        tolerance=pd.Timedelta(days=max_feature_staleness_days),
    )
    trades["feature_stale_days"] = (trades["entry_date"] - trades["feature_date"]).dt.days

    trades = pd.merge_asof(
        trades.sort_values("entry_date"), vix.sort_values("vix_date"),
        left_on="entry_date", right_on="vix_date", direction="backward",
        tolerance=pd.Timedelta(days=max_feature_staleness_days),
    )
    trades["vix_stale_days"] = (trades["entry_date"] - trades["vix_date"]).dt.days
    if not bool((trades["feature_date"].dropna() <= trades.loc[trades["feature_date"].notna(), "entry_date"]).all()):
        raise AssertionError("future NQ daily feature joined to entry")
    if not bool((trades["vix_date"].dropna() <= trades.loc[trades["vix_date"].notna(), "entry_date"]).all()):
        raise AssertionError("future VIX close joined to entry")

    trades["vix_daily_vol_points"] = (
        trades["rth_close"] * trades["vix_close"] / 100.0 / np.sqrt(252.0))
    trades["vix_daily_vol_ref"] = trades["vix_daily_vol_points"].shift(1).rolling(
        reference_lookback, min_periods=reference_min_obs).median()
    trades["gross_points_per_contract"] = trades["exit_price"] - trades["entry_price"]
    trades["holding_hours"] = (
        trades["exit_ts"] - trades["entry_ts"]).dt.total_seconds() / 3600.0

    valid_execution = trades["same_contract"] & trades["rolls_inside"].eq(0)
    valid_execution &= trades["holding_hours"].eq(EXPECTED_HOLDING_MINUTES / 60)
    quality = {
        "entry_anchors": len(entry),
        "exit_anchors": len(exit_frame),
        "matched_anchor_pairs": len(trades),
        "same_contract_pairs": int(trades["same_contract"].sum()),
        "pairs_with_roll_inside": int((trades["rolls_inside"] > 0).sum()),
        "pairs_wrong_holding_hours": int((trades["holding_hours"] != EXPECTED_HOLDING_MINUTES / 60).sum()),
        "pairs_missing_nq_daily_feature": int(trades["feature_date"].isna().sum()),
        "pairs_missing_vix": int(trades["vix_date"].isna().sum()),
        "pairs_with_internal_missing_minutes": int((trades["holding_window_missing_rows"] > 0).sum()),
        "median_holding_window_rows": float(trades["holding_window_rows"].median()),
        "max_internal_missing_minutes": int(trades["holding_window_missing_rows"].clip(lower=0).max()),
        "valid_execution_pairs": int(valid_execution.sum()),
        "excluded_execution_pairs": int((~valid_execution).sum()),
        "feature_staleness_counts": {
            str(_json_value(k)): int(v) for k, v in trades["feature_stale_days"].value_counts(dropna=False).items()},
        "vix_staleness_counts": {
            str(_json_value(k)): int(v) for k, v in trades["vix_stale_days"].value_counts(dropna=False).items()},
    }
    trades = trades.loc[valid_execution].sort_values("entry_ts").reset_index(drop=True)
    return trades, quality
