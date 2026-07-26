"""Study B+C -- volatility's HONEST role: does VEI help FORECAST volatility, and does
low VEI mark a "coiled spring" (contraction -> expansion)?

VEI alone is not a direction predictor, but vol is forecastable (clustering) and drives
sizing/risk in every strategy. Two questions:

  B. INCREMENTAL FORECAST. Target = forward realized abs-variation over the next H min.
     Baseline predictor = the current vol LEVEL (past realized vol). Does the VEI RATIO
     add information over the level? Rank IC of each, and an OLS dR^2 from adding
     log(VEI) to log(past_rv), with a session-block-bootstrap CI on the VEI coefficient.

  C. CONTRACTION -> EXPANSION (user's reading: VEI<1 = consolidating after a wider
     range). Bin VEI into quintiles and report the EXPANSION RATIO = forward realized
     abs-variation / past realized abs-variation. If the coiled-spring reading holds,
     LOW VEI shows expansion ratio > 1 (vol rises) and HIGH VEI shows < 1 (vol mean-
     reverts down). This is a vol-TIMING signal, not a direction signal.

Usage: python -u -m futures.nq.vei_exploration.scripts.s2_vol_forecast {NQ|ES}
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import loaders as L
from ..core import vei as V
from ..core import analysis as A

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "BC_vol_forecast"
PERIOD = 30
DM = [j * PERIOD - 1 for j in range(1, 14)]
HORIZONS = (30, 60)
SEED = 72000
# canonical VEI: Wilder RMA ATR (Study A: far more persistent + predictive than raw SMA)
VEI_KW = dict(short=10, long=50, atr_method="wilder", smooth=0)


def ols_r2(y, X) -> float:
    X = np.c_[np.ones(len(X)), X]
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    resid = y - X @ beta
    ss_res = float((resid ** 2).sum())
    ss_tot = float(((y - y.mean()) ** 2).sum())
    return 1.0 - ss_res / ss_tot, beta


def boot_coef_ci(df, ycol, xcols, rng, nboot=1000):
    """Session-block bootstrap CI on the LAST coefficient in xcols (log VEI)."""
    d = df.dropna(subset=[ycol] + xcols)
    y = d[ycol].to_numpy(float)
    X = d[xcols].to_numpy(float)
    codes, uniq = pd.factorize(d["date"].to_numpy())
    order = np.argsort(codes, kind="stable")
    y = y[order]; X = X[order]
    counts = np.bincount(codes, minlength=len(uniq))
    starts = np.concatenate([[0], np.cumsum(counts)[:-1]])
    sl = [slice(starts[i], starts[i] + counts[i]) for i in range(len(uniq))]
    coefs = np.empty(nboot)
    for b in range(nboot):
        pick = rng.integers(0, len(uniq), size=len(uniq))
        yy = np.concatenate([y[sl[j]] for j in pick])
        XX = np.concatenate([X[sl[j]] for j in pick])
        _, beta = ols_r2(yy, XX)
        coefs[b] = beta[-1]
    return float(np.percentile(coefs, 5)), float(np.percentile(coefs, 95))


def run(inst: str) -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    rng = np.random.default_rng(SEED)
    bars = L.load_1m_rth(inst)
    b = V.add_vei(bars, **VEI_KW)
    feat = b[b["mfo"].isin(DM)][["sdate", "mfo", "vei"]].rename(columns={"sdate": "date"})
    ff = A.forward_features(bars, DM, horizons=HORIZONS, past_win=30)
    d = feat.merge(ff, on=["date", "mfo"])
    d = d[d["mfo"] != DM[0]]   # first slot has no long ATR
    print(f"\n======== Study B+C: VEI vol forecasting — {inst} ========")
    print(f"VEI variant: {VEI_KW}   n_decisions={len(d)}")

    # ---- B. incremental forecast ----
    print("\n--- B. Forecast forward realized abs-variation (rank IC + OLS dR^2) ---")
    brows = []
    for H in HORIZONS:
        y = f"fwd_absvar_{H}"
        ic_lvl, _, _ = A.block_boot_ic(d, "past_rv", y, rng)
        ic_vei, vlo, vhi = A.block_boot_ic(d, "vei", y, rng)
        dd = d.dropna(subset=[y, "past_rv", "vei"]).copy()
        dd = dd[(dd["past_rv"] > 0) & (dd["vei"] > 0)]
        yv = dd[y].to_numpy(float)
        lvl = np.log(dd["past_rv"].to_numpy(float))
        lv = np.log(dd["vei"].to_numpy(float))
        r2_base, _ = ols_r2(yv, lvl.reshape(-1, 1))
        r2_both, _ = ols_r2(yv, np.c_[lvl, lv])
        clo, chi = boot_coef_ci(dd.assign(_y=yv, _lvl=lvl, _lv=lv),
                                "_y", ["_lvl", "_lv"], rng)
        print(f"H={H:>3}m  IC(level)={ic_lvl:+.4f}  IC(VEI)={ic_vei:+.4f} "
              f"[{vlo:+.4f},{vhi:+.4f}]  R2 level={r2_base:.4f} -> +VEI={r2_both:.4f} "
              f"(dR2={r2_both-r2_base:+.4f}; VEI coef CI[{clo:+.3f},{chi:+.3f}])")
        brows.append({"H": H, "ic_level": ic_lvl, "ic_vei": ic_vei,
                      "r2_level": r2_base, "r2_both": r2_both,
                      "dr2": r2_both - r2_base, "vei_coef_lo": clo, "vei_coef_hi": chi})
    pd.DataFrame(brows).to_csv(OUT / f"forecast_{inst}.csv", index=False)

    # ---- C. contraction -> expansion ----
    print("\n--- C. Expansion ratio (fwd abs-var / past abs-var) by VEI quintile ---")
    dd = d.dropna(subset=["vei"]).copy()
    dd["q"] = pd.qcut(dd["vei"], 5, labels=False, duplicates="drop")
    crows = []
    for H in HORIZONS:
        y = f"fwd_absvar_{H}"
        t = dd.dropna(subset=[y]).copy()
        # scale past window (past_win=30) to horizon H so ratio ~1 means "same pace"
        t["exp_ratio"] = (t[y] / (t["past_absvar"] * (H / 30.0))).replace([np.inf], np.nan)
        g = t.groupby("q").agg(vei_lo=("vei", "min"), vei_hi=("vei", "max"),
                               n=("exp_ratio", "size"),
                               exp_ratio=("exp_ratio", "median"),
                               fwd_absvar=(y, "median"),
                               fwd_range=(f"fwd_range_{H}", "median"))
        print(f"\n H={H}m expansion ratio (median) by VEI quintile "
              f"(>1 = vol rises, <1 = vol falls):")
        print(g.to_string(float_format=lambda x: f"{x:.4f}"))
        g["H"] = H
        crows.append(g.reset_index())
    pd.concat(crows).to_csv(OUT / f"expansion_{inst}.csv", index=False)
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    run(sys.argv[1] if len(sys.argv) > 1 else "NQ")
