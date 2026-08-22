"""HYP-0039 mechanism gate: does first-30-min realized dispersion forecast
rest-of-session realized vol, out-of-sample, ADDING over prior-session vol?

This is the GATE that precedes any sizing P&L (kill test 1 + directional placebo
3). No engine change, no trades — just causal per-session vol features and OOS
regressions.

Per session d (RTH, mfo = minutes from the 09:30 open):
  r_k          = log(close_k / close_{k-1})                     (1-min log return)
  early_rv[d]  = sqrt( sum_{1<=k<=29} r_k^2 )   -- known at END of mfo 29 (causal)
  rest_rv[d]   = sqrt( sum_{k>=30}    r_k^2 )   -- the sizing TARGET (future)
  prior_rv[d]  = full-session rv of the PRIOR session (strictly shifted)  [baseline]
  rest_ret[d]  = log(close_last / close_{mfo29})  -- signed, directional placebo

Log returns make early_rv scale-free across the 2011->2026 price-level change, so
no extra normaliser is needed for the FORECAST regression (the scale-free per-slot
z only matters for the later fixed-threshold SIZING step, LEARNINGS #1).

Forecast (HAR-style, in logs):
  baseline:  log(rest_rv) ~ 1 + log(prior_rv)
  full:      log(rest_rv) ~ 1 + log(prior_rv) + log(early_rv)
Fit on TRAIN, score OOS R^2 on TEST. GATE: early_rv ADDS OOS R^2 over prior_rv,
and its incremental coefficient is HAC(Newey-West)-significant on TRAIN.
PLACEBO: log(early_rv) must NOT predict rest_ret sign (leak check).

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0039_vol_gate NQ
  python -u -m futures.nq.noise_vwap.scripts.hyp_0039_vol_gate ES
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from .hyp_0036_confirm_depth import split_dates

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "HYP-0039-gate"
EARLY_END = 30   # first 30 min = mfo 0..29; boundary return at mfo 30 -> rest


def session_features(inst: str) -> pd.DataFrame:
    """One row per trade-date: early_rv, rest_rv, prior_rv, rest_ret, n_bars."""
    bars = S.load_session(inst, "RTH").sort_values(["sdate", "mfo"]).reset_index(drop=True)
    lc = np.log(bars["close"].to_numpy())
    r = np.empty(len(bars)); r[:] = np.nan
    same = bars["sdate"].to_numpy()
    r[1:] = np.where(same[1:] == same[:-1], lc[1:] - lc[:-1], np.nan)  # intra-session only
    bars = bars.assign(r=r, r2=r * r)

    def per_day(g):
        early = g.loc[(g["mfo"] >= 1) & (g["mfo"] <= EARLY_END - 1), "r2"].sum()
        rest = g.loc[g["mfo"] >= EARLY_END, "r2"].sum()
        c29 = g.loc[g["mfo"] == EARLY_END - 1, "close"]
        clast = g["close"].iloc[-1]
        full = g["r2"].sum()
        rest_ret = np.log(clast / c29.iloc[0]) if len(c29) else np.nan
        return pd.Series({"early_rv": np.sqrt(early), "rest_rv": np.sqrt(rest),
                          "full_rv": np.sqrt(full), "rest_ret": rest_ret,
                          "n_bars": len(g)})

    feat = bars.groupby("sdate", sort=True).apply(per_day, include_groups=False)
    feat["prior_rv"] = feat["full_rv"].shift(1)          # strictly-prior session
    feat = feat.dropna(subset=["early_rv", "rest_rv", "prior_rv", "rest_ret"])
    feat = feat[(feat["early_rv"] > 0) & (feat["rest_rv"] > 0) & (feat["prior_rv"] > 0)]
    return feat.reset_index()


def ols(X: np.ndarray, y: np.ndarray):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta


def hac_se(X: np.ndarray, y: np.ndarray, beta: np.ndarray, lag: int = 5):
    """Newey-West HAC standard errors (Bartlett kernel)."""
    n, k = X.shape
    resid = y - X @ beta
    XtX_inv = np.linalg.inv(X.T @ X)
    S0 = (X * resid[:, None]).T @ (X * resid[:, None])
    S = S0.copy()
    for L in range(1, lag + 1):
        w = 1.0 - L / (lag + 1.0)
        Xu = X * resid[:, None]
        G = Xu[L:].T @ Xu[:-L]
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    return np.sqrt(np.diag(cov))


def oos_r2(Xtr, ytr, Xte, yte):
    beta = ols(Xtr, ytr)
    pred = Xte @ beta
    ss_res = np.sum((yte - pred) ** 2)
    ss_tot = np.sum((yte - yte.mean()) ** 2)
    return 1.0 - ss_res / ss_tot, beta


def main(inst: str):
    OUT.mkdir(parents=True, exist_ok=True)
    feat = session_features(inst)
    dates = feat["sdate"].to_numpy()
    train_d, test_d = split_dates(dates)
    train_d, test_d = set(train_d), set(test_d)
    tr = feat[feat["sdate"].isin(train_d)]
    te = feat[feat["sdate"].isin(test_d)]

    y_tr = np.log(tr["rest_rv"].to_numpy());  y_te = np.log(te["rest_rv"].to_numpy())
    lp_tr = np.log(tr["prior_rv"].to_numpy()); lp_te = np.log(te["prior_rv"].to_numpy())
    le_tr = np.log(tr["early_rv"].to_numpy()); le_te = np.log(te["early_rv"].to_numpy())
    one_tr = np.ones(len(tr));  one_te = np.ones(len(te))

    Xb_tr = np.column_stack([one_tr, lp_tr]);        Xb_te = np.column_stack([one_te, lp_te])
    Xf_tr = np.column_stack([one_tr, lp_tr, le_tr]); Xf_te = np.column_stack([one_te, lp_te, le_te])

    r2_base, _ = oos_r2(Xb_tr, y_tr, Xb_te, y_te)
    r2_full, beta_f = oos_r2(Xf_tr, y_tr, Xf_te, y_te)

    # in-sample HAC significance of the early_rv coefficient (TRAIN)
    beta_tr = ols(Xf_tr, y_tr)
    se = hac_se(Xf_tr, y_tr, beta_tr, lag=5)
    t_early = beta_tr[2] / se[2]

    # directional placebo: does early_rv predict rest-of-session SIGNED return?
    # regress rest_ret on standardized log(early_rv), OOS + TRAIN HAC t.
    def z(a, ref): return (a - ref.mean()) / ref.std()
    ze_tr = z(le_tr, le_tr); ze_te = z(le_te, le_tr)
    Xd_tr = np.column_stack([one_tr, ze_tr]); Xd_te = np.column_stack([one_te, ze_te])
    rr_tr = tr["rest_ret"].to_numpy(); rr_te = te["rest_ret"].to_numpy()
    beta_d = ols(Xd_tr, rr_tr)
    se_d = hac_se(Xd_tr, rr_tr, beta_d, lag=5)
    t_dir_tr = beta_d[1] / se_d[1]
    # OOS: does early_rv have any linear directional predictive corr on TEST?
    corr_dir_te = float(np.corrcoef(ze_te, rr_te)[0, 1])

    add_oos = r2_full - r2_base
    gate1 = (add_oos > 0) and (t_early > 2.0)
    placebo_ok = abs(t_dir_tr) < 2.0 and abs(corr_dir_te) < 0.10

    res = {
        "inst": inst, "n_train": int(len(tr)), "n_test": int(len(te)),
        "train_span": [str(pd.Timestamp(min(train_d)).date()), str(pd.Timestamp(max(train_d)).date())],
        "test_span": [str(pd.Timestamp(min(test_d)).date()), str(pd.Timestamp(max(test_d)).date())],
        "oos_r2_baseline_priorvol": float(r2_base),
        "oos_r2_full_plus_earlyrv": float(r2_full),
        "oos_r2_added_by_earlyrv": float(add_oos),
        "train_coef_earlyrv": float(beta_tr[2]),
        "train_hac_t_earlyrv": float(t_early),
        "GATE1_earlyrv_adds_and_significant": bool(gate1),
        "placebo_train_hac_t_direction": float(t_dir_tr),
        "placebo_oos_corr_direction": corr_dir_te,
        "PLACEBO3_no_directional_leak": bool(placebo_ok),
    }
    print(f"\n### HYP-0039 vol-forecast gate — {inst} ###")
    print(f"TRAIN n={res['n_train']} {res['train_span'][0]}->{res['train_span'][1]} | "
          f"TEST n={res['n_test']} {res['test_span'][0]}->{res['test_span'][1]}")
    print(f"OOS R^2  prior_vol only            : {r2_base:+.4f}")
    print(f"OOS R^2  prior_vol + early_rv       : {r2_full:+.4f}")
    print(f"OOS R^2  ADDED by early_rv          : {add_oos:+.4f}")
    print(f"TRAIN early_rv coef {beta_tr[2]:+.4f}  HAC t = {t_early:+.2f}")
    print(f"GATE 1 (adds OOS R^2 AND HAC t>2)   : {'PASS' if gate1 else 'FAIL'}")
    print(f"PLACEBO dir: TRAIN HAC t={t_dir_tr:+.2f}  OOS corr={corr_dir_te:+.4f}"
          f"  -> {'clean (no leak)' if placebo_ok else 'LEAK — investigate'}")
    feat.to_csv(OUT / f"features_{inst}.csv", index=False)
    json.dump(res, open(OUT / f"gate_{inst}.json", "w"), indent=2)
    print(f"wrote {OUT / f'gate_{inst}.json'}")
    return res


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
