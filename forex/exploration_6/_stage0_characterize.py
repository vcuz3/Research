"""Stage 0 — data quality + seasonality characterization (Rule 9a).

Questions:
  1. Coverage: matched-volume fraction by year and UTC hour (reproduce manifest).
  2. Seasonality: how strongly do futures volume AND |1-min return| vary by UTC
     hour?  (If both do, a raw |r|/v ratio threshold is a time-of-day selector.)
  3. Contemporaneous link: corr(log v, log|r|) overall and *within* UTC hour.
  4. Demonstrate the trap: a fixed cut on raw |r|/v vs. on a same-hour z has very
     different per-hour fire rates.  We report the selection-rate CV of each.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from _data import load_pair

PIP = 1e-4  # all four pairs quote in 0.0001


def prep(pair: str) -> pd.DataFrame:
    df = load_pair(pair)
    df = df.sort_values("ts_utc").reset_index(drop=True)
    dt = df["ts_utc"].diff().dt.total_seconds()
    contiguous = dt.eq(60.0)
    ret_pips = (df["close"].diff()) / PIP
    out = pd.DataFrame(
        {
            "ts": df["ts_utc"],
            "hour": df["ts_utc"].dt.hour,
            "year": df["ts_utc"].dt.year,
            "ret": ret_pips.where(contiguous),
            "absret": ret_pips.abs().where(contiguous),
            "vol": df["volume"],
        }
    )
    # a usable minute: contiguous return AND matched volume > 0
    out["ok"] = out["ret"].notna() & out["vol"].notna() & (out["vol"] > 0)
    return out


def characterize(pair: str) -> dict:
    d = prep(pair)
    u = d[d["ok"]].copy()
    u["logv"] = np.log(u["vol"])
    u["logar"] = np.log(u["absret"].clip(lower=1e-6))

    # by-hour seasonality
    by_hour = u.groupby("hour").agg(
        n=("ret", "size"),
        vol_med=("vol", "median"),
        vol_mean=("vol", "mean"),
        absret_mean=("absret", "mean"),
        absret_med=("absret", "median"),
    )
    by_hour["ratio_med"] = by_hour["absret_med"] / by_hour["vol_med"]

    # contemporaneous corr overall and within-hour (avg)
    corr_all = np.corrcoef(u["logv"], u["logar"])[0, 1]
    within = u.groupby("hour").apply(
        lambda g: np.corrcoef(g["logv"], g["logar"])[0, 1] if len(g) > 100 else np.nan,
        include_groups=False,
    )
    corr_within = float(within.mean())

    # trap demo: fixed cut on raw ratio vs same-hour z of ratio; match ~ top 5%
    u["ratio"] = u["absret"] / u["vol"]
    thr_raw = u["ratio"].quantile(0.95)
    fire_raw = u.assign(f=(u["ratio"] >= thr_raw)).groupby("hour")["f"].mean()
    # same-hour z of log ratio (global per-hour standardization for the demo)
    u["lr"] = np.log(u["ratio"].clip(lower=1e-12))
    hz = u.groupby("hour")["lr"].transform(lambda x: (x - x.mean()) / x.std())
    thr_z = hz.quantile(0.95)
    fire_z = u.assign(f=(hz >= thr_z)).groupby("hour")["f"].mean()

    def cv(s):
        return float(s.std() / s.mean())

    return {
        "pair": pair,
        "n_usable": int(len(u)),
        "corr_logv_logabsret_all": float(corr_all),
        "corr_within_hour_avg": corr_within,
        "vol_med_hour_min": float(by_hour["vol_med"].min()),
        "vol_med_hour_max": float(by_hour["vol_med"].max()),
        "absret_mean_hour_min": float(by_hour["absret_mean"].min()),
        "absret_mean_hour_max": float(by_hour["absret_mean"].max()),
        "fire_cv_raw_ratio": cv(fire_raw),
        "fire_cv_hour_z": cv(fire_z),
        "by_hour": by_hour,
    }


if __name__ == "__main__":
    import sys

    pairs = sys.argv[1:] or ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
    rows = []
    for p in pairs:
        r = characterize(p)
        print(f"\n===== {p} (usable minutes: {r['n_usable']:,}) =====")
        print(
            f"corr(log v, log|r|): all={r['corr_logv_logabsret_all']:+.3f}  "
            f"within-hour avg={r['corr_within_hour_avg']:+.3f}"
        )
        print(
            f"volume median by hour: {r['vol_med_hour_min']:.0f} .. {r['vol_med_hour_max']:.0f} "
            f"({r['vol_med_hour_max']/r['vol_med_hour_min']:.1f}x)"
        )
        print(
            f"|ret| mean by hour (pips): {r['absret_mean_hour_min']:.3f} .. "
            f"{r['absret_mean_hour_max']:.3f} "
            f"({r['absret_mean_hour_max']/r['absret_mean_hour_min']:.1f}x)"
        )
        print(
            f"fire-rate CV @ top5%: raw |r|/v ratio = {r['fire_cv_raw_ratio']:.3f}  "
            f"| same-hour z = {r['fire_cv_hour_z']:.3f}"
        )
        rows.append({k: v for k, v in r.items() if k != "by_hour"})
        r["by_hour"].to_csv(
            rf"C:\Users\VuDoa\Research\forex\exploration_6\artifacts\stage0_by_hour_{p}.csv"
        )
    pd.DataFrame(rows).to_csv(
        r"C:\Users\VuDoa\Research\forex\exploration_6\artifacts\stage0_summary.csv", index=False
    )
    print("\nwrote stage0 artifacts")
