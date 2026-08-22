"""HYP-0039 baseline horse-race: which CAUSAL daily-vol forecaster of
rest-of-session vol is strongest, and does early_rv still add over the BEST one?

Compares (all strictly-prior, causal), predicting log(rest_rv) OOS on TEST:
  yday      : yesterday's full-session rv (prior_rv, the naive 1-day baseline)
  ma5,ma22  : trailing N-session mean of full rv
  ewma      : EWMA of full rv (halflife 10 sessions)
  HAR       : {yday, ma5, ma22} together (Corsi HAR-RV)
then the marginal of early_rv over yday and over the best trailing baseline.

Usage: python -u -m futures.nq.noise_vwap.scripts.hyp_0039_vol_baselines NQ
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from .hyp_0039_vol_gate import session_features, oos_r2, OUT
from .hyp_0036_confirm_depth import split_dates


def main(inst: str):
    feat = session_features(inst).sort_values("sdate").reset_index(drop=True)
    f = feat["full_rv"]
    feat["yday"] = f.shift(1)
    feat["ma5"] = f.shift(1).rolling(5, min_periods=5).mean()
    feat["ma22"] = f.shift(1).rolling(22, min_periods=22).mean()
    feat["ewma"] = f.shift(1).ewm(halflife=10, min_periods=10).mean()
    feat = feat.dropna(subset=["yday", "ma5", "ma22", "ewma", "rest_rv", "early_rv"])
    feat = feat[feat["rest_rv"] > 0]

    dates = feat["sdate"].to_numpy()
    train_d, test_d = split_dates(dates)
    train_d, test_d = set(train_d), set(test_d)
    tr, te = feat[feat["sdate"].isin(train_d)], feat[feat["sdate"].isin(test_d)]
    y_tr, y_te = np.log(tr["rest_rv"].to_numpy()), np.log(te["rest_rv"].to_numpy())
    o_tr, o_te = np.ones(len(tr)), np.ones(len(te))

    def col(df, name): return np.log(df[name].to_numpy())

    def fit_report(cols, label):
        Xtr = np.column_stack([o_tr] + [col(tr, c) for c in cols])
        Xte = np.column_stack([o_te] + [col(te, c) for c in cols])
        r2, _ = oos_r2(Xtr, y_tr, Xte, y_te)
        print(f"  {label:32s} OOS R^2 = {r2:+.4f}")
        return r2

    print(f"\n### HYP-0039 daily-vol baseline horse-race — {inst} ###")
    print(f"predicting log(rest_rv), OOS on TEST (n_tr={len(tr)} n_te={len(te)})")
    r = {"inst": inst}
    r["yday"] = fit_report(["yday"], "yday (yesterday only)")
    r["ma5"] = fit_report(["ma5"], "ma5")
    r["ma22"] = fit_report(["ma22"], "ma22")
    r["ewma"] = fit_report(["ewma"], "ewma(hl=10)")
    r["HAR"] = fit_report(["yday", "ma5", "ma22"], "HAR {yday,ma5,ma22}")
    best_name = max(["yday", "ma5", "ma22", "ewma", "HAR"], key=lambda k: r[k])
    print(f"  --> best daily-vol baseline: {best_name} ({r[best_name]:+.4f})")
    print("  marginal value of intraday early_rv:")
    r["yday_plus_early"] = fit_report(["yday", "early_rv"], "yday + early_rv")
    best_cols = ["yday", "ma5", "ma22"] if best_name == "HAR" else [best_name]
    r["best_plus_early"] = fit_report(best_cols + ["early_rv"], f"{best_name} + early_rv")
    r["best_name"] = best_name
    r["early_adds_over_yday"] = r["yday_plus_early"] - r["yday"]
    r["early_adds_over_best"] = r["best_plus_early"] - r[best_name]
    print(f"  early_rv adds over yday : {r['early_adds_over_yday']:+.4f}")
    print(f"  early_rv adds over {best_name:4s}: {r['early_adds_over_best']:+.4f}")
    OUT.mkdir(parents=True, exist_ok=True)
    json.dump(r, open(OUT / f"baselines_{inst}.json", "w"), indent=2)
    print(f"wrote {OUT / f'baselines_{inst}.json'}")
    return r


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
