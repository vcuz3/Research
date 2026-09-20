"""Load and audit the two LSE NQ.F minute tiles and build SMA200 candidates."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Iterable

import numpy as np
import pandas as pd

from .features import (
    EXPECTED_ANCHOR_BARS, EXPECTED_HOLDING_MINUTES, GLOBEX_ENTRY_MINUTE,
    NY_TZ, RTH_OPEN_MINUTE, audit_nq_minutes, build_rth_daily,
)


def load_lse_minutes(paths: Iterable[Path]) -> tuple[pd.DataFrame, dict[str, Any], pd.DataFrame]:
    parts = []
    file_quality = []
    for path in paths:
        raw = pd.read_parquet(path)
        required = {"ts", "symbol", "open", "high", "low", "close", "volume"}
        missing = required.difference(raw.columns)
        if missing:
            raise ValueError(f"{path} missing columns: {sorted(missing)}")
        raw["ts"] = pd.to_datetime(raw["ts"], utc=True).astype("datetime64[ns, UTC]")
        file_quality.append({
            "path": str(path), "rows": len(raw), "first": str(raw["ts"].min()),
            "last": str(raw["ts"].max()), "duplicates": int(raw["ts"].duplicated().sum()),
            "out_of_order": int((raw["ts"].diff().dropna() < pd.Timedelta(0)).sum()),
        })
        parts.append(raw)
    combined = pd.concat(parts, ignore_index=True)
    duplicate_ts = int(combined["ts"].duplicated(keep=False).sum())
    conflict_ts = 0
    if duplicate_ts:
        duplicate_rows = combined.loc[combined["ts"].duplicated(keep=False)]
        conflicts = duplicate_rows.groupby("ts")[["open", "high", "low", "close"]].nunique()
        conflict_ts = int((conflicts.max(axis=1) > 1).sum())
    combined = combined.sort_values("ts", kind="stable").drop_duplicates("ts", keep="last")
    combined = combined.rename(columns={"ts": "ts_utc"}).reset_index(drop=True)
    combined["is_roll"] = False  # Source provides no underlying contract identifier.
    local = combined["ts_utc"].dt.tz_convert(NY_TZ)
    combined["local_date"] = local.dt.tz_localize(None).dt.normalize()
    combined["local_minute"] = local.dt.hour * 60 + local.dt.minute
    minute_quality, coverage = audit_nq_minutes(combined)
    price_link = combined["open"] / combined["close"].shift(1) - 1.0
    quality = {
        "files": file_quality,
        "combined_duplicate_rows": duplicate_ts,
        "conflicting_duplicate_timestamps": conflict_ts,
        "rows_after_deduplication": len(combined),
        "large_open_to_prior_close_links_gt_5pct": int((price_link.abs() > 0.05).sum()),
        "largest_abs_open_to_prior_close_link": float(price_link.abs().max()),
        "roll_identifiers_available": False,
        "minute_audit": minute_quality,
    }
    return combined, quality, coverage


def build_lse_sma_candidates(
    frame: pd.DataFrame,
    sma_days: int = 200,
    max_feature_staleness_days: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Create exact-clock candidates and attach only completed daily SMA state."""
    daily, daily_quality = build_rth_daily(
        frame, [sma_days], reference_lookback=252, reference_min_obs=60)
    daily["rth_close_return"] = daily["rth_close"].pct_change(fill_method=None)
    daily["sma_gate_close"] = daily["rth_close"] > daily[f"sma_{sma_days}"]

    entry = frame.loc[frame["local_minute"] == GLOBEX_ENTRY_MINUTE, [
        "ts_utc", "local_date", "open"]].rename(columns={
            "ts_utc": "entry_ts", "local_date": "entry_date", "open": "entry_price"})
    entry["trade_date"] = entry["entry_date"] + pd.Timedelta(days=1)
    exit_frame = frame.loc[frame["local_minute"] == RTH_OPEN_MINUTE, [
        "ts_utc", "local_date", "open"]].rename(columns={
            "ts_utc": "exit_ts", "local_date": "trade_date", "open": "exit_price"})
    if entry["entry_date"].duplicated().any() or exit_frame["trade_date"].duplicated().any():
        raise ValueError("duplicate exact-clock anchor on a local date")
    candidates = entry.merge(exit_frame, on="trade_date", how="inner", validate="one_to_one")

    feature_cols = ["feature_date", "rth_close", f"sma_{sma_days}", "sma_gate_close",
                    "rth_close_return", "rth_rows"]
    candidates = pd.merge_asof(
        candidates.sort_values("entry_date"), daily[feature_cols].sort_values("feature_date"),
        left_on="entry_date", right_on="feature_date", direction="backward",
        tolerance=pd.Timedelta(days=max_feature_staleness_days))
    candidates["feature_stale_days"] = (
        candidates["entry_date"] - candidates["feature_date"]).dt.days
    candidates["sma_available"] = candidates[f"sma_{sma_days}"].notna()
    candidates["sma_gate_entry"] = (
        candidates["entry_price"] > candidates[f"sma_{sma_days}"])
    candidates["gross_points_per_contract"] = (
        candidates["exit_price"] - candidates["entry_price"])
    candidates["holding_hours"] = (
        candidates["exit_ts"] - candidates["entry_ts"]).dt.total_seconds() / 3600.0

    overnight = frame.loc[
        (frame["local_minute"] >= GLOBEX_ENTRY_MINUTE)
        | (frame["local_minute"] <= RTH_OPEN_MINUTE), ["local_date", "local_minute"]].copy()
    overnight["trade_date"] = overnight["local_date"] + pd.to_timedelta(
        (overnight["local_minute"] >= GLOBEX_ENTRY_MINUTE).astype(int), unit="D")
    counts = overnight.groupby("trade_date").size().rename("holding_window_rows")
    candidates = candidates.merge(counts, on="trade_date", how="left")
    candidates["holding_window_missing_rows"] = (
        EXPECTED_ANCHOR_BARS - candidates["holding_window_rows"])

    valid = candidates["holding_hours"].eq(EXPECTED_HOLDING_MINUTES / 60)
    quality = {
        "entry_anchors": len(entry), "exit_anchors": len(exit_frame),
        "matched_candidates": len(candidates),
        "wrong_holding_duration": int((~valid).sum()),
        "valid_candidates": int(valid.sum()),
        "sma_warmup_unavailable": int(candidates.loc[valid, "sma_available"].eq(False).sum()),
        "sma_available_candidates": int(candidates.loc[valid, "sma_available"].sum()),
        "sma_gate_entry_active": int(candidates.loc[valid & candidates["sma_available"], "sma_gate_entry"].sum()),
        "sma_gate_close_active": int(candidates.loc[valid & candidates["sma_available"], "sma_gate_close"].sum()),
        "pairs_with_internal_missing_minutes": int(
            (candidates.loc[valid, "holding_window_missing_rows"] > 0).sum()),
        "median_holding_window_rows": float(candidates.loc[valid, "holding_window_rows"].median()),
        "feature_staleness_counts": {
            str(k): int(v) for k, v in candidates.loc[valid, "feature_stale_days"].value_counts(
                dropna=False).items()},
        "roll_exclusion": "unavailable: LSE source carries only constant symbol NQ.F",
        "daily_quality": daily_quality,
    }
    return candidates.loc[valid].sort_values("trade_date").reset_index(drop=True), daily, quality

