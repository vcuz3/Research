"""Inference + the cost ladder. Points are MNQ index points throughout."""
from __future__ import annotations

import numpy as np
import pandas as pd

# Round-trip charge in INDEX POINTS. See paper/PAPER_SPEC.md section 3.
#   MNQ = $2/pt, NQ = $20/pt, tick = 0.25 pt, fees taken at $1.70 round trip.
COST_LADDER = {
    "gross":        0.000,
    "nq_spread1":   0.25 + 1.70 / 20.0,    # 0.335  full contract, 1-tick spread
    "mnq_spread1":  0.25 + 1.70 / 2.0,     # 1.100  micro, 1-tick spread
    "mnq_spread2":  0.50 + 1.70 / 2.0,     # 1.350  micro, 2-tick spread (Asia hours)
    "article":      2.000,                  # the article's own charge
}


def cluster_t(x: pd.Series, cluster: pd.Series) -> tuple[float, float]:
    """Mean and cluster-robust t of a per-signal series, clustered on trade date.

    SE^2 = sum_g (sum_i (x_i - xbar))^2 / n^2, with the standard finite-sample
    correction G/(G-1). Rule 12: signals inside one session are dependent.
    """
    x = np.asarray(x, float)
    n = len(x)
    if n < 2:
        return float("nan"), float("nan")
    xbar = x.mean()
    dev = x - xbar
    g = pd.Series(dev).groupby(np.asarray(cluster)).sum().to_numpy()
    G = len(g)
    if G < 2:
        return float(xbar), float("nan")
    var = (g ** 2).sum() * (G / (G - 1.0)) / (n ** 2)
    se = np.sqrt(var)
    return float(xbar), float(xbar / se) if se > 0 else float("nan")


def score(sig: pd.DataFrame, label: str = "") -> dict:
    """One row of results for a signal set: gross, the cost ladder, and inference."""
    if sig is None or not len(sig):
        return {"label": label, "n": 0}
    g = sig["gross_pts"]
    mean, t = cluster_t(g, sig["trade_date"])
    row = {
        "label": label,
        "n": int(len(sig)),
        "sessions": int(sig["trade_date"].nunique()),
        "sig_per_session": float(len(sig) / sig["trade_date"].nunique()),
        "hit_rate": float((g > 0).mean()),
        "gross_pts": mean,
        "gross_t": t,
        "gross_sd": float(g.std(ddof=1)),
        "truncated_frac": float(sig["truncated"].mean()),
    }
    for name, c in COST_LADDER.items():
        if name == "gross":
            continue
        net = g - c
        m, tt = cluster_t(net, sig["trade_date"])
        row[f"net_{name}"] = m
        row[f"t_{name}"] = tt
    return row


def by_year(sig: pd.DataFrame) -> pd.DataFrame:
    if not len(sig):
        return pd.DataFrame()
    yr = sig["trade_date"].dt.year
    rows = []
    for y, s in sig.groupby(yr):
        m, t = cluster_t(s["gross_pts"], s["trade_date"])
        rows.append({"year": int(y), "n": len(s), "gross_pts": m, "gross_t": t,
                     "net_mnq_spread2": m - COST_LADDER["mnq_spread2"]})
    return pd.DataFrame(rows).set_index("year")
