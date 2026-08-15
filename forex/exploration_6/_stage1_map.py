"""Stage 1 (descriptive) — does the volume<->move relationship predict fwd return?

Resample to W-minute bars (full-coverage rule: keep a bar only if all W minutes
have matched non-null volume, so V is a real sum, not a partial one).  For each
bar compute:
  R   : signed bar return (pips)
  V   : total futures volume in the bar
Standardize per time-of-day slot (hour, minute//W) over the FULL sample -- this
is a two-sided, DESCRIPTIVE normalization used only to see whether a pattern
exists; Stage 2 redoes any survivor with a causal trailing same-slot z.
  z_R : signed-move z within slot
  z_V : volume-surprise z within slot (on log V)

Forward return: entry at the NEXT bar's open, held H minutes (fwd = close after
H minutes - open of next bar).  We read the map two ways:
  - unconditional E[fwd | bins]
  - directional dir = sign(R) * fwd  (continuation>0, reversal<0), the
    volume-confirmation reading.

Headline: within displacement events |z_R|>=2, is dir-return different across
z_V terciles?  (volume-confirmed vs unconfirmed moves.)
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from _data import load_pair

PIP = 1e-4


def resample_bars(pair: str, W: int) -> pd.DataFrame:
    df = load_pair(pair).set_index("ts_utc").sort_index()
    o = df["open"].resample(f"{W}min", label="left", closed="left").first()
    c = df["close"].resample(f"{W}min", label="left", closed="left").last()
    vsum = df["volume"].resample(f"{W}min", label="left", closed="left").sum(min_count=1)
    vcount = df["volume"].notna().resample(f"{W}min", label="left", closed="left").sum()
    n = df["close"].notna().resample(f"{W}min", label="left", closed="left").sum()
    bars = pd.DataFrame({"open": o, "close": c, "V": vsum, "vcount": vcount, "n": n}).dropna(
        subset=["open", "close"]
    )
    # causal full-coverage rule: every minute in the bar present AND volume-matched
    bars = bars[(bars["n"] == W) & (bars["vcount"] == W) & (bars["V"] > 0)].copy()
    bars["R"] = (bars["close"] - bars["open"]) / PIP
    bars["slot"] = bars.index.hour * 100 + (bars.index.minute // W) * W
    return bars


def add_z_and_fwd(bars: pd.DataFrame, H: int, W: int) -> pd.DataFrame:
    b = bars.copy()
    # per-slot standardization (descriptive, two-sided)
    g = b.groupby("slot")
    b["z_R"] = g["R"].transform(lambda x: (x - x.mean()) / x.std())
    logv = np.log(b["V"])
    b["z_V"] = logv.groupby(b["slot"]).transform(lambda x: (x - x.mean()) / x.std())
    # forward return: entry at next bar open, hold H minutes.
    # next bar open at index+W min; exit close at index + W + H min.
    step = H // W  # number of W-bars in the horizon
    nxt_open = b["open"].shift(-1)  # open of the immediately following bar
    exit_close = b["close"].shift(-step)  # close H minutes after that open's bar start
    # require the following bar to be contiguous (next timestamp == idx + W min)
    idx = b.index
    contig1 = (idx.to_series().shift(-1) - idx.to_series()) == pd.Timedelta(minutes=W)
    contig2 = (idx.to_series().shift(-step) - idx.to_series()) == pd.Timedelta(minutes=W * step)
    b["fwd"] = ((exit_close - nxt_open) / PIP).where(contig1.values & contig2.values)
    b["dir"] = np.sign(b["R"]) * b["fwd"]
    return b


def summarize(pair: str, W: int, H: int) -> dict:
    bars = resample_bars(pair, W)
    b = add_z_and_fwd(bars, H, W).dropna(subset=["z_R", "z_V", "fwd"])
    # displacement events
    disp = b[b["z_R"].abs() >= 2.0].copy()
    terc = pd.qcut(disp["z_V"], 3, labels=["Vlow", "Vmid", "Vhigh"])
    grp = disp.groupby(terc, observed=True)["dir"].agg(["mean", "sem", "size"])
    # session-cluster-robust-ish: cluster by UTC day
    disp["day"] = disp.index.normalize()
    return {
        "pair": pair,
        "W": W,
        "H": H,
        "n_bars": int(len(b)),
        "n_disp": int(len(disp)),
        "dir_Vlow": float(grp.loc["Vlow", "mean"]),
        "dir_Vmid": float(grp.loc["Vmid", "mean"]),
        "dir_Vhigh": float(grp.loc["Vhigh", "mean"]),
        "sem_Vlow": float(grp.loc["Vlow", "sem"]),
        "sem_Vhigh": float(grp.loc["Vhigh", "sem"]),
        "n_Vhigh": int(grp.loc["Vhigh", "size"]),
        "_bars": b,
        "_disp": disp,
    }


def print_map(b: pd.DataFrame, pair: str, W: int, H: int):
    zr_bins = pd.cut(b["z_R"], [-np.inf, -2, -1, -0.33, 0.33, 1, 2, np.inf])
    zv_bins = pd.cut(b["z_V"], [-np.inf, -0.5, 0.5, np.inf], labels=["Vlo", "Vmd", "Vhi"])
    piv = b.pivot_table(index=zr_bins, columns=zv_bins, values="fwd", aggfunc="mean", observed=True)
    cnt = b.pivot_table(index=zr_bins, columns=zv_bins, values="fwd", aggfunc="size", observed=True)
    print(f"\n--- {pair} W={W} H={H}: E[fwd pips] by (signed-move z rows) x (vol-surprise z cols) ---")
    print(piv.round(3).to_string())
    print("counts:")
    print(cnt.to_string())


if __name__ == "__main__":
    import sys

    pairs = sys.argv[1:] or ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
    W, H = 15, 30
    rows = []
    for p in pairs:
        r = summarize(p, W, H)
        print(
            f"\n===== {p} W={W} H={H}  bars={r['n_bars']:,} disp(|z_R|>=2)={r['n_disp']:,} ====="
        )
        print(
            f"dir-return (sign(move)*fwd, pips) by volume tercile among displacements:\n"
            f"  Vlow ={r['dir_Vlow']:+.3f} (sem {r['sem_Vlow']:.3f})\n"
            f"  Vmid ={r['dir_Vmid']:+.3f}\n"
            f"  Vhigh={r['dir_Vhigh']:+.3f} (sem {r['sem_Vhigh']:.3f}, n={r['n_Vhigh']:,})"
        )
        print_map(r["_bars"], p, W, H)
        rows.append({k: v for k, v in r.items() if not k.startswith("_")})
    pd.DataFrame(rows).to_csv(
        r"C:\Users\VuDoa\Research\forex\exploration_6\artifacts\stage1_disp_terciles.csv",
        index=False,
    )
    print("\nwrote stage1 artifacts")
