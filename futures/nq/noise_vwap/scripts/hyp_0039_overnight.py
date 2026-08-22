"""HYP-0039 addendum — does OVERNIGHT volatility genuinely uplift a causal
forecast of rest-of-session realized vol, ON TOP of the daily HAR and the
intraday first-30-min read (early_rv)?

This is a GENERAL vol-forecasting question for future position sizing, NOT tied to
the noise-VWAP book's P&L. Target = log(rest_rv), rest_rv = sqrt(sum r^2) over RTH
minutes >= 30 (same target as the gate). All predictors strictly causal (known
before the RTH open, or before minute 30):

  Daily (from full RTH rv):
    yday, ma5, ma22          -> HAR {yday, ma5, ma22}         (Corsi HAR-RV)
  Intraday:
    early_rv                  = sqrt(sum r^2) over RTH mfo 1..29   (known @ 09:29)
  Overnight (from the ETH/Globex session, 18:00 ET .. 09:29 ET):
    overnight_rv              = sqrt(sum r^2) over ETH mfo 1..929  (known @ 09:29)
    gap_abs                   = |log(rth_open / prior_rth_close)|

r_k = log(close_k / close_{k-1}), computed only WITHIN a session (no boundary
leak). Log returns keep every rv scale-free across the 2011->2026 price level.

Nested OOS horse-race (fit on TRAIN, score OOS R^2 on TEST) isolates each block's
MARGINAL contribution; the decisive number is whether overnight_rv / gap_abs add
OOS R^2 on top of HAR+early_rv, with a TRAIN HAC(Newey-West) t on the increment.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0039_overnight NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0039_overnight ES
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from .hyp_0039_vol_gate import session_features, ols, hac_se, oos_r2, OUT
from .hyp_0036_confirm_depth import split_dates

RTH_OPEN_MFO = 930  # ETH: 18:00 ET open -> 09:30 ET RTH open is 930 min later


def overnight_features(inst: str) -> pd.DataFrame:
    """One row per trade-date: overnight_rv (18:00..09:29), gap_abs (into RTH)."""
    eth = S.load_session(inst, "ETH").sort_values(["sdate", "mfo"]).reset_index(drop=True)
    lc = np.log(eth["close"].to_numpy())
    same = eth["sdate"].to_numpy()
    r = np.empty(len(eth)); r[:] = np.nan
    r[1:] = np.where(same[1:] == same[:-1], lc[1:] - lc[:-1], np.nan)  # intra-session only
    eth = eth.assign(r2=r * r)

    on = eth[(eth["mfo"] >= 1) & (eth["mfo"] < RTH_OPEN_MFO)]
    overnight_rv = np.sqrt(on.groupby("sdate")["r2"].sum())

    # gap = first RTH bar open (mfo 930) vs the prior overnight close just before it
    rth_open = (eth[eth["mfo"] == RTH_OPEN_MFO].groupby("sdate")["open"].first())
    pre_open_close = (eth[eth["mfo"] < RTH_OPEN_MFO].sort_values("mfo")
                      .groupby("sdate")["close"].last())
    gap = np.log(rth_open / pre_open_close)

    out = pd.DataFrame({"overnight_rv": overnight_rv, "gap_abs": gap.abs()}).reset_index()
    out = out[(out["overnight_rv"] > 0)].dropna()
    return out


def main(inst: str):
    OUT.mkdir(parents=True, exist_ok=True)
    rth = session_features(inst).sort_values("sdate").reset_index(drop=True)
    f = rth["full_rv"]
    rth["yday"] = f.shift(1)
    rth["ma5"] = f.shift(1).rolling(5, min_periods=5).mean()
    rth["ma22"] = f.shift(1).rolling(22, min_periods=22).mean()
    on = overnight_features(inst)

    feat = rth.merge(on, on="sdate", how="inner")
    feat = feat.dropna(subset=["rest_rv", "early_rv", "yday", "ma5", "ma22",
                               "overnight_rv", "gap_abs"])
    feat = feat[(feat["rest_rv"] > 0) & (feat["gap_abs"] > 0)]

    dates = feat["sdate"].to_numpy()
    train_d, test_d = split_dates(dates)
    train_d, test_d = set(train_d), set(test_d)
    tr, te = feat[feat["sdate"].isin(train_d)], feat[feat["sdate"].isin(test_d)]
    y_tr, y_te = np.log(tr["rest_rv"].to_numpy()), np.log(te["rest_rv"].to_numpy())
    o_tr, o_te = np.ones(len(tr)), np.ones(len(te))

    def col(df, name): return np.log(df[name].to_numpy())

    def design(df, cols, o):
        return np.column_stack([o] + [col(df, c) for c in cols])

    def r2(cols, label=None):
        Xtr, Xte = design(tr, cols, o_tr), design(te, cols, o_te)
        val, _ = oos_r2(Xtr, y_tr, Xte, y_te)
        if label:
            print(f"  {label:36s} OOS R^2 = {val:+.4f}")
        return val

    def hac_t_last(cols):
        """TRAIN HAC t of the LAST regressor in cols (the added block)."""
        Xtr = design(tr, cols, o_tr)
        beta = ols(Xtr, y_tr)
        se = hac_se(Xtr, y_tr, beta, lag=5)
        return float(beta[-1] / se[-1])

    print(f"\n### HYP-0039 overnight-vol uplift — {inst} ###")
    print(f"target = log(rest_rv); OOS on TEST  (n_tr={len(tr)} n_te={len(te)}, "
          f"merged on ETH+RTH coverage)")

    print("\n-- single predictors (OOS R^2 predicting log rest_rv) --")
    r_yday = r2(["yday"], "yday (yesterday full rv)")
    r_on = r2(["overnight_rv"], "overnight_rv alone")
    r_early = r2(["early_rv"], "early_rv alone (first 30m)")
    r2(["gap_abs"], "gap_abs alone")

    print("\n-- nested build-up --")
    r_har = r2(["yday", "ma5", "ma22"], "HAR {yday,ma5,ma22}")
    r_har_on = r2(["yday", "ma5", "ma22", "overnight_rv"], "HAR + overnight_rv")
    r_har_e = r2(["yday", "ma5", "ma22", "early_rv"], "HAR + early_rv")
    r_har_e_on = r2(["yday", "ma5", "ma22", "early_rv", "overnight_rv"],
                    "HAR + early_rv + overnight_rv")
    r_full = r2(["yday", "ma5", "ma22", "early_rv", "overnight_rv", "gap_abs"],
                "HAR + early_rv + overnight_rv + gap_abs")

    print("\n-- MARGINAL OOS R^2 (what each block adds) --")
    add_on_over_har = r_har_on - r_har
    add_early_over_har = r_har_e - r_har
    add_on_over_hare = r_har_e_on - r_har_e
    add_gap_over_hare_on = r_full - r_har_e_on
    print(f"  overnight_rv over HAR            : {add_on_over_har:+.4f}")
    print(f"  early_rv     over HAR            : {add_early_over_har:+.4f}")
    print(f"  overnight_rv over HAR+early_rv   : {add_on_over_hare:+.4f}   <-- key")
    print(f"  gap_abs      over HAR+early+on   : {add_gap_over_hare_on:+.4f}")

    print("\n-- TRAIN HAC t of the ADDED block --")
    t_on_over_hare = hac_t_last(["yday", "ma5", "ma22", "early_rv", "overnight_rv"])
    t_early_over_har = hac_t_last(["yday", "ma5", "ma22", "early_rv"])
    print(f"  overnight_rv | HAR+early_rv  HAC t = {t_on_over_hare:+.2f}")
    print(f"  early_rv     | HAR           HAC t = {t_early_over_har:+.2f}")

    res = {
        "inst": inst, "n_train": int(len(tr)), "n_test": int(len(te)),
        "oos_r2": {
            "yday": r_yday, "overnight_rv": r_on, "early_rv": r_early,
            "HAR": r_har, "HAR+overnight": r_har_on, "HAR+early": r_har_e,
            "HAR+early+overnight": r_har_e_on, "full+gap": r_full,
        },
        "marginal_oos_r2": {
            "overnight_over_HAR": add_on_over_har,
            "early_over_HAR": add_early_over_har,
            "overnight_over_HAR_early": add_on_over_hare,
            "gap_over_HAR_early_on": add_gap_over_hare_on,
        },
        "train_hac_t": {
            "overnight_given_HAR_early": t_on_over_hare,
            "early_given_HAR": t_early_over_har,
        },
    }
    json.dump(res, open(OUT / f"overnight_{inst}.json", "w"), indent=2)
    print(f"\nwrote {OUT / f'overnight_{inst}.json'}")
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
