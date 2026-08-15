"""Stage 1b — decisive volume-confirmation test with the shared-close embargo.

For W-min bars, among displacement events |z_R| >= ZTHR:
  dir = sign(R_t) * fwd    (continuation > 0, reversal < 0)
  fwd (embargo e) = close_{t+1+e+step-1... } measured as:
       enter at open of bar (t+1+e), hold `step` bars.
     e=0 : enter next bar (shares close_t as anchor -> artifact-prone)
     e=1 : skip one bar, enter at open_{t+2}=close_{t+1} (artifact removed)

Report dir-return by z_V tercile, the (Vhigh - Vlow) spread, and a UTC-day
cluster-robust t on that spread, per pair and pooled.  If the "volume confirms
the move" story is real it should (a) survive the e=1 embargo, (b) agree in sign
across pairs, (c) be stable across W/H.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from _data import load_pair

PIP = 1e-4


def bars_with_z(pair: str, W: int) -> pd.DataFrame:
    df = load_pair(pair).set_index("ts_utc").sort_index()
    o = df["open"].resample(f"{W}min", label="left", closed="left").first()
    c = df["close"].resample(f"{W}min", label="left", closed="left").last()
    vsum = df["volume"].resample(f"{W}min", label="left", closed="left").sum(min_count=1)
    vcount = df["volume"].notna().resample(f"{W}min", label="left", closed="left").sum()
    n = df["close"].notna().resample(f"{W}min", label="left", closed="left").sum()
    b = pd.DataFrame({"open": o, "close": c, "V": vsum, "vcount": vcount, "n": n}).dropna(
        subset=["open", "close"]
    )
    b = b[(b["n"] == W) & (b["vcount"] == W) & (b["V"] > 0)].copy()
    b["R"] = (b["close"] - b["open"]) / PIP
    b["slot"] = b.index.hour * 100 + (b.index.minute // W) * W
    g = b.groupby("slot")
    b["z_R"] = g["R"].transform(lambda x: (x - x.mean()) / x.std())
    logv = np.log(b["V"])
    b["z_V"] = logv.groupby(b["slot"]).transform(lambda x: (x - x.mean()) / x.std())
    return b


def fwd_return(b: pd.DataFrame, W: int, step: int, embargo: int) -> pd.Series:
    """Enter at open of bar (index + (1+embargo) bars); hold `step` bars."""
    idx = b.index.to_series()
    enter_open = b["open"].shift(-(1 + embargo))
    exit_close = b["close"].shift(-(1 + embargo) - (step - 1))
    # contiguity: entry bar and exit bar exactly where expected
    d_enter = idx.shift(-(1 + embargo)) - idx
    d_exit = idx.shift(-(1 + embargo) - (step - 1)) - idx
    ok = (d_enter == pd.Timedelta(minutes=W * (1 + embargo))) & (
        d_exit == pd.Timedelta(minutes=W * ((1 + embargo) + (step - 1)))
    )
    return ((exit_close - enter_open) / PIP).where(ok.values)


def clustered_t(values: np.ndarray, days: np.ndarray) -> float:
    """t-stat of the mean, clustering by day."""
    s = pd.Series(values)
    day = pd.Series(days)
    m = s.mean()
    # cluster-robust SE of the mean: sum within-cluster, then var across clusters
    grp = s.groupby(day)
    csum = grp.sum().values
    cn = grp.size().values
    n = len(s)
    # SE of mean via clustered variance of (x - m)
    resid = s - m
    cresid = resid.groupby(day).sum().values
    var = (cresid**2).sum() / (n**2)
    se = np.sqrt(var)
    return float(m / se) if se > 0 else np.nan


def analyze(pair: str, W: int, step: int, zthr: float, embargo: int) -> dict:
    b = bars_with_z(pair, W)
    b["fwd"] = fwd_return(b, W, step, embargo)
    b = b.dropna(subset=["z_R", "z_V", "fwd"])
    disp = b[b["z_R"].abs() >= zthr].copy()
    disp["dir"] = np.sign(disp["R"]) * disp["fwd"]
    disp["day"] = disp.index.normalize().values
    terc = pd.qcut(disp["z_V"], 3, labels=["lo", "mid", "hi"])
    out = {"pair": pair, "W": W, "step": step, "embargo": embargo, "n": int(len(disp))}
    for lab in ["lo", "mid", "hi"]:
        out[f"dir_{lab}"] = float(disp.loc[terc == lab, "dir"].mean())
    hi = disp[terc == "hi"]
    lo = disp[terc == "lo"]
    spread = hi["dir"].mean() - lo["dir"].mean()
    out["spread_hi_lo"] = float(spread)
    # cluster t on spread: build a contrast series (+ for hi, - for lo), day-clustered
    contrast = pd.concat([hi["dir"] - hi["dir"].mean() + spread, lo["dir"] - lo["dir"].mean()])
    # simpler: two-sample day-clustered via stacking with sign
    stack = pd.DataFrame(
        {
            "v": np.r_[hi["dir"].values, -lo["dir"].values],
            "day": np.r_[hi["day"], lo["day"]],
        }
    )
    out["t_spread"] = clustered_t(stack["v"].values, stack["day"].values)
    return out


if __name__ == "__main__":
    pairs = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
    W, step, zthr = 15, 2, 2.0  # 15-min bars, hold 2 bars (30 min), |z_R|>=2
    rows = []
    for embargo in [0, 1]:
        print(f"\n########## embargo={embargo}  (W={W}, hold={step*W}min, |z_R|>={zthr}) ##########")
        pooled_dir_lo, pooled_dir_hi, pooled_days_lo, pooled_days_hi = [], [], [], []
        for p in pairs:
            r = analyze(p, W, step, zthr, embargo)
            rows.append(r)
            print(
                f"{p}: n={r['n']:>6,}  dir lo/mid/hi = "
                f"{r['dir_lo']:+.3f} / {r['dir_mid']:+.3f} / {r['dir_hi']:+.3f}   "
                f"spread(hi-lo)={r['spread_hi_lo']:+.3f}  t={r['t_spread']:+.2f}"
            )
    pd.DataFrame(rows).to_csv(
        r"C:\Users\VuDoa\Research\forex\exploration_6\artifacts\stage1b_embargo.csv", index=False
    )
    print("\nwrote stage1b artifacts")
