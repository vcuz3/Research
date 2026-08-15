"""Rule 9a data-quality gate for the weekend-gap study.

Reports, per pair: span, row count, duplicate/out-of-order timestamps, the
distribution of detected weekend breaks, how many weekends survive the causal
sigma warm-up, entry/exit availability at each delay and horizon, and the
reopen-minute distribution (a DST/holiday sanity check).

Nothing here reads a forward return, so it is safe to run before the
preregistration is frozen.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent))
from _gap_lib import (CALENDAR_REF, PAIRS, build_events, load_pair,  # noqa: E402
                      session_calendar, weekend_breaks)

HORIZONS = [15, 60, 240, 1440, 2880, 7200]
DELAYS = [1, 5, 15, 60]
OUT = Path(__file__).resolve().parent / "artifacts" / "runs" / "EXP-0001"


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    cal = session_calendar(load_pair(CALENDAR_REF).index)
    cal.to_csv(OUT / "session_calendar.csv", index=False)
    print(f"canonical calendar from {CALENDAR_REF}: {len(cal)} weekends "
          f"{cal['week_close'].min()} .. {cal['week_close'].max()}")

    rows = []
    reopen_hours = {}
    all_ev = []
    for pair in PAIRS:
        df = load_pair(pair)
        idx = df.index
        ev = build_events(pair, df, HORIZONS, DELAYS, cal)
        all_ev.append(ev)

        br = weekend_breaks(idx)
        # weekend bars that should not exist in spot FX (padded vintages)
        sat_bars = int((idx.dayofweek == 5).sum())
        cov = {}
        for d in DELAYS:
            cov[f"entry_{d}_ok"] = float(ev[f"entry_{d}"].notna().mean())
        for h in HORIZONS:
            cov[f"exit_{h}_ok"] = float(ev[f"exit_{h}"].notna().mean())

        in_span = ev[(ev["t_open"] >= idx[0]) & (ev["t_fri"] <= idx[-1])]
        rows.append({
            "pair": pair,
            "start": str(idx[0]), "end": str(idx[-1]),
            "rows": len(df),
            "dupes": int(idx.duplicated().sum()),
            "monotonic": bool(idx.is_monotonic_increasing),
            "nan_ohlc": int(df.isna().any(axis=1).sum()),
            "nonpos_px": int((df[["open", "high", "low", "close"]] <= 0).any(axis=1).sum()),
            "saturday_bars": sat_bars,
            "own_breaks": len(br),
            "cal_weekends_in_span": len(in_span),
            "boundary_ok": int(in_span["boundary_ok"].sum()),
            "boundary_ok_frac": round(float(in_span["boundary_ok"].mean()), 4),
            "max_abs_lag_close": round(float(in_span.loc[in_span["boundary_ok"], "lag_close_min"].abs().max()), 2),
            "max_abs_lag_open": round(float(in_span.loc[in_span["boundary_ok"], "lag_open_min"].abs().max()), 2),
            "sigma_available": int(ev["sigma_ret"].notna().sum()),
            "median_gap_pips": round(float(ev["gap_pips"].abs().median()), 2),
            **{k: round(v, 4) for k, v in cov.items()},
        })
        reopen_hours[pair] = (
            ev["t_open"].dt.hour.value_counts().sort_index().to_dict()
        )
        print(f"  {pair}: {len(df):,} rows, {len(br)} weekends", flush=True)

    rep = pd.DataFrame(rows)
    ev_all = pd.concat(all_ev, ignore_index=True)
    ev_all.to_parquet(OUT / "events.parquet", index=False)
    rep.to_csv(OUT / "data_quality.csv", index=False)

    # weekend alignment across pairs: do the pairs see the same weekends?
    wk = ev_all.pivot_table(index="weekend", columns="pair", values="gap_ret",
                            aggfunc="first")
    align = {
        "distinct_weekends": int(len(wk)),
        "weekends_all_9_pairs": int(wk.notna().all(axis=1).sum()),
        "weekends_ge_4_pairs": int((wk.notna().sum(axis=1) >= 4).sum()),
    }
    (OUT / "reopen_hours.json").write_text(
        json.dumps({"reopen_hour_utc": reopen_hours, "alignment": align}, indent=2,
                   default=str))

    pd.set_option("display.width", 250, "display.max_columns", 100)
    print("\n=== DATA QUALITY ===")
    print(rep[["pair", "start", "end", "rows", "dupes", "nan_ohlc",
               "saturday_bars", "own_breaks", "cal_weekends_in_span",
               "boundary_ok", "boundary_ok_frac", "max_abs_lag_close",
               "max_abs_lag_open", "sigma_available",
               "median_gap_pips"]].to_string(index=False))
    print("\n=== ENTRY/EXIT COVERAGE (fraction of weekends) ===")
    print(rep[["pair"] + [c for c in rep.columns if c.endswith("_ok")]].to_string(index=False))
    print("\n=== ALIGNMENT ===")
    print(align)
    print("\n=== REOPEN HOUR (UTC) ===")
    print(pd.DataFrame(reopen_hours).fillna(0).astype(int).to_string())


if __name__ == "__main__":
    main()
