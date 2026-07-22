"""Executable Rule-9a data and feature coverage report."""
from __future__ import annotations

import json
from pathlib import Path
import numpy as np
import pandas as pd

from ..core.data import N_BARS, PATH_1M, WARMUP_BARS, load_15m, load_1s_index
from ..strategy.signals import add_signals, condition_funnel


def build_report(bars: pd.DataFrame, s1s: dict) -> dict:
    sizes = bars.groupby("date").size()
    dates15 = set(pd.to_datetime(bars["date"]).to_numpy(dtype="datetime64[ns]"))
    dates1s = set(np.datetime64(k, "ns") for k in s1s)
    by_slot = bars.groupby("sess_bar").agg(rows=("close", "size"),
                                             sessions=("date", "nunique"))
    feature_cols = ["ema200", "ema50", "ema20", "atr14", "volma20", "vwap"]
    nan_counts = {c: int(bars[c].isna().sum()) for c in feature_cols}
    year = pd.to_datetime(bars["date"]).dt.year
    feature_missing_by_year = {
        str(int(y)): {c: int(g[c].isna().sum()) for c in feature_cols}
        for y, g in bars.groupby(year)
    }
    coverage_by_year = {}
    for y, g in bars.groupby(year):
        ds = set(pd.to_datetime(g["date"]).to_numpy(dtype="datetime64[ns]"))
        gs = g.groupby("date").size()
        coverage_by_year[str(int(y))] = {
            "rows_15m": int(len(g)), "sessions": int(len(ds)),
            "incomplete_sessions": int((gs < N_BARS).sum()),
            "missing_15m_bars": int((N_BARS - gs.clip(upper=N_BARS)).sum()),
            "sessions_without_1s": int(len(ds - dates1s)),
        }
    return {
        "rows_15m": int(len(bars)), "sessions_15m": int(bars.date.nunique()),
        "date_min": str(pd.to_datetime(bars.date.min()).date()),
        "date_max": str(pd.to_datetime(bars.date.max()).date()),
        "duplicate_date_tsec": int(bars.duplicated(["date", "tsec"]).sum()),
        "out_of_order": int(not pd.MultiIndex.from_frame(
            bars[["date", "tsec"]]).is_monotonic_increasing),
        "incomplete_sessions": int((sizes < N_BARS).sum()),
        "missing_15m_bars": int((N_BARS - sizes.clip(upper=N_BARS)).sum()),
        "min_bars_session": int(sizes.min()), "median_bars_session": float(sizes.median()),
        "sessions_spanning_symbols": int((bars.groupby("date").symbol.nunique() > 1).sum()),
        "sessions_1s_total": int(len(dates1s)),
        "sessions_1s_overlap": int(len(dates15 & dates1s)),
        "sessions_15m_without_1s": int(len(dates15 - dates1s)),
        "slot_coverage": {str(int(i)): {k: int(v) for k, v in row.items()}
                          for i, row in by_slot.to_dict("index").items()},
        "feature_nan_counts": nan_counts,
        "feature_missing_by_year": feature_missing_by_year,
        "coverage_by_year": coverage_by_year,
        "warmup_bars_explicitly_excluded": int(min(WARMUP_BARS, len(bars))),
    }


def main(output: str | None = None) -> None:
    raw = pd.read_parquet(PATH_1M, columns=["ts_utc", "symbol"])
    raw_dup = int(raw["ts_utc"].duplicated().sum())
    raw_ooo = int((pd.to_datetime(raw["ts_utc"]).diff().dropna() < pd.Timedelta(0)).sum())
    bars = add_signals(load_15m()); s1s = load_1s_index()
    report = build_report(bars, s1s)
    report["raw_1m_rows"] = int(len(raw)); report["raw_1m_duplicate_ts"] = raw_dup
    report["raw_1m_out_of_order"] = raw_ooo
    funnel = condition_funnel(bars[pd.to_datetime(bars.date).dt.year.eq(2024)])
    report["funnel_2024"] = funnel.to_dict("records")
    text = json.dumps(report, indent=2)
    print(text)
    if output:
        Path(output).write_text(text + "\n", encoding="utf-8")


if __name__ == "__main__":
    import sys
    main(sys.argv[1] if len(sys.argv) > 1 else None)
