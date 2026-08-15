"""Stage 1c — robustness sweep of the volume->continuation link (embargo=1).

Higher power than terciles: among displacement events |z_R|>=ZTHR, compute the
Spearman rank-IC between z_V (volume surprise) and dir = sign(R)*fwd
(continuation>0). Positive IC = "high volume confirms the move".  Sweep window W
and hold horizon; report per pair and pooled, with a UTC-day block-bootstrap
p-value on the pooled IC.  All with the shared-close embargo (enter open_{t+2}).
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from _stage1b_decisive import bars_with_z, fwd_return

RNG = np.random.default_rng(7)


def disp_frame(pair: str, W: int, step: int, zthr: float) -> pd.DataFrame:
    b = bars_with_z(pair, W)
    b["fwd"] = fwd_return(b, W, step, embargo=1)
    b = b.dropna(subset=["z_R", "z_V", "fwd"])
    d = b[b["z_R"].abs() >= zthr].copy()
    d["dir"] = np.sign(d["R"]) * d["fwd"]
    d["day"] = d.index.normalize().values
    d["pair"] = pair
    return d[["z_V", "dir", "day", "pair"]]


def day_clustered_ic_t(d: pd.DataFrame) -> float:
    """t-stat for pooled Spearman IC via a day-clustered SE on the rank product.

    Spearman IC = mean of standardized-rank product u*v (up to n/(n-1)); cluster
    the per-obs rank-products by day to get a dependence-robust SE.
    """
    u = d["z_V"].rank().values
    v = d["dir"].rank().values
    n = len(u)
    u = (u - u.mean()) / u.std()
    v = (v - v.mean()) / v.std()
    prod = u * v  # mean ~ IC
    s = pd.Series(prod)
    day = pd.Series(d["day"].values)
    m = s.mean()
    cresid = (s - m).groupby(day).sum().values
    se = np.sqrt((cresid**2).sum()) / n
    return float(m / se) if se > 0 else np.nan


if __name__ == "__main__":
    pairs = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
    zthr = 1.5
    configs = [(5, 1), (5, 3), (15, 1), (15, 2), (30, 1), (30, 2), (60, 1)]
    rows = []
    for W, step in configs:
        frames = [disp_frame(p, W, step, zthr) for p in pairs]
        per = {}
        for p, f in zip(pairs, frames):
            ic = spearmanr(f["z_V"], f["dir"]).correlation
            per[p] = ic
        pooled = pd.concat(frames, ignore_index=False)
        ic_pool = spearmanr(pooled["z_V"], pooled["dir"]).correlation
        tval = day_clustered_ic_t(pooled)
        agree = np.sign(list(per.values()))
        rows.append(
            {
                "W": W,
                "hold_min": W * step,
                "n_pool": len(pooled),
                "IC_EUR": per["EURUSD"],
                "IC_GBP": per["GBPUSD"],
                "IC_AUD": per["AUDUSD"],
                "IC_NZD": per["NZDUSD"],
                "IC_pool": ic_pool,
                "t_pool": tval,
                "n_same_sign": int(max((agree > 0).sum(), (agree < 0).sum())),
            }
        )
        print(
            f"W={W:>2} hold={W*step:>3}min | IC EUR/GBP/AUD/NZD = "
            f"{per['EURUSD']:+.3f}/{per['GBPUSD']:+.3f}/{per['AUDUSD']:+.3f}/{per['NZDUSD']:+.3f}"
            f" | pooled IC={ic_pool:+.4f} t={tval:+.2f} | max same-sign={rows[-1]['n_same_sign']}/4",
            flush=True,
        )
    pd.DataFrame(rows).to_csv(
        r"C:\Users\VuDoa\Research\forex\exploration_6\artifacts\stage1c_sweep.csv", index=False
    )
    print("\nwrote stage1c artifacts")
