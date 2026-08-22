"""HYP-0039 kill test 2: causal vol-target SIZING of the deployed clock book.

Sizes each session's contract multiplier inversely to a causal forecast of that
session's realised vol, and asks whether adding the just-observed first-30-min
realised vol (early_rv) to the forecast improves DRAWDOWN-AWARE risk-adjusted
return over a daily-only (HAR) forecast.

Sizers (per trade-date d), each a per-session multiplier m_d applied to that
day's summed net-R P&L:
  flat      : m_d = 1
  daily HAR : m_d = c / volhat_daily_d      volhat from HAR {yday,ma5,ma22}
  intraday  : m_d = c / volhat_intraday_d   volhat from HAR + early_rv

volhat_* = exp(TRAIN-fit OLS prediction of log(rest_rv)). early_rv is known at the
close of mfo 29, before the earliest entry (mfo 30 open) -> causal for all trades.
c set so mean(m_d)=1 over TRAIN dates (matched exposure; Sharpe & Calmar are
scale-free so this only affects raw total-R and vol-of-P&L reporting).

Decisive comparison = intraday vs DAILY-HAR (identical machinery, differ only by
early_rv = the LEARNINGS #3 degenerate control). flat is context. Primary metric =
TEST Calmar (sum net R / maxDD) and vol-of-daily-P&L at matched exposure; also
report the three Sharpes.

Usage: python -u -m futures.nq.noise_vwap.scripts.hyp_0039_sizing NQ
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from .hyp_0036_confirm_depth import run_gated, split_dates
from .hyp_0012_diffusion_cone import (
    common_dates, round_trip_cost_points, LOOKBACK, PERIOD,
)
from .hyp_0039_vol_gate import session_features, ols

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "HYP-0039-sizing"


def daily_netr(inst, bars):
    """Per-date summed net-R of the deployed clock book (over all common dates)."""
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    t = run_gated(bars, bands, dm, None)
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    t = t.copy()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)]
    t["net_r"] = (t["points"] - rt) / t["atr"]
    return t.groupby("date")["net_r"].sum()


def volhat(feat, train_mask, cols):
    """TRAIN-fit OLS of log(rest_rv) on cols; return volhat = exp(pred) per row."""
    y = np.log(feat["rest_rv"].to_numpy())
    X = np.column_stack([np.ones(len(feat))] + [np.log(feat[c].to_numpy()) for c in cols])
    beta = ols(X[train_mask], y[train_mask])
    return np.exp(X @ beta)


def metrics(dayR):
    """dayR: pd.Series indexed by date (zero-trade days included as 0.0)."""
    sd = float(dayR.std(ddof=1))
    sharpe = float(dayR.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    eq = dayR.cumsum()
    maxdd = float((eq.cummax() - eq).max())
    total = float(dayR.sum())
    calmar = total / maxdd if maxdd > 0 else np.nan
    trade_days = dayR[dayR != 0]
    tsd = float(trade_days.std(ddof=1))
    tsharpe = float(trade_days.mean() / tsd * np.sqrt(252)) if tsd > 0 else 0.0
    return {"total_R": total, "sharpe_zeroday": sharpe, "sharpe_tradeday": tsharpe,
            "vol_dailyR": sd, "maxDD_R": maxdd, "calmar": calmar}


def main(inst):
    OUT.mkdir(parents=True, exist_ok=True)
    bars = S.load_session(inst, "RTH")
    dR = daily_netr(inst, bars)

    feat = session_features(inst).sort_values("sdate").reset_index(drop=True)
    f = feat["full_rv"]
    feat["yday"] = f.shift(1)
    feat["ma5"] = f.shift(1).rolling(5, min_periods=5).mean()
    feat["ma22"] = f.shift(1).rolling(22, min_periods=22).mean()
    feat = feat.dropna(subset=["yday", "ma5", "ma22", "rest_rv", "early_rv"]).reset_index(drop=True)

    # evaluation universe: common (post-lookback) dates that also have a vol forecast
    common = set(pd.to_datetime(common_dates(bars)))
    feat = feat[feat["sdate"].isin(common)].reset_index(drop=True)
    dates = feat["sdate"].to_numpy()
    train_d, test_d = split_dates(dates)
    train_set, test_set = set(train_d), set(test_d)
    train_mask = feat["sdate"].isin(train_set).to_numpy()
    test_mask = feat["sdate"].isin(test_set).to_numpy()

    vh_daily = volhat(feat, train_mask, ["yday", "ma5", "ma22"])
    vh_intra = volhat(feat, train_mask, ["yday", "ma5", "ma22", "early_rv"])

    def scale(m):  # unit-mean multiplier over TRAIN dates
        return m / m[train_mask].mean()

    m_daily = scale(1.0 / vh_daily)
    m_intra = scale(1.0 / vh_intra)
    m_flat = np.ones(len(feat))

    idx = pd.DatetimeIndex(feat["sdate"])
    base_dayR = pd.Series(dR).reindex(idx, fill_value=0.0).to_numpy()

    rows = []
    exposures = {}
    for name, m in [("flat", m_flat), ("daily_HAR", m_daily), ("intraday", m_intra)]:
        sizedR = pd.Series(m * base_dayR, index=idx)
        for seg, mask in [("TRAIN", train_mask), ("TEST", test_mask)]:
            mt = metrics(sizedR[mask])
            mt.update({"sizer": name, "seg": seg,
                       "mean_exposure": float(m[mask].mean())})
            rows.append(mt)
        exposures[name] = (float(m[train_mask].mean()), float(m[test_mask].mean()))
    res = pd.DataFrame(rows)

    print(f"\n### HYP-0039 vol-target sizing — {inst} ###")
    print(f"eval dates n={len(feat)}  TRAIN={int(train_mask.sum())} TEST={int(test_mask.sum())}")
    for seg in ("TRAIN", "TEST"):
        print(f"\n-- {seg} --")
        sub = res[res["seg"] == seg].set_index("sizer")
        cols = ["mean_exposure", "total_R", "sharpe_zeroday", "sharpe_tradeday",
                "vol_dailyR", "maxDD_R", "calmar"]
        print(sub[cols].to_string(float_format=lambda v: f"{v:+.4f}"))

    def get(seg, sizer, k):
        return float(res[(res.seg == seg) & (res.sizer == sizer)][k].iloc[0])

    print("\n-- decisive: intraday vs daily-HAR (TEST) --")
    for k in ["calmar", "sharpe_zeroday", "vol_dailyR", "maxDD_R", "total_R"]:
        d = get("TEST", "intraday", k)
        b = get("TEST", "daily_HAR", k)
        print(f"  {k:16s} intraday {d:+.4f}  daily_HAR {b:+.4f}  delta {d - b:+.4f}")

    verdict = {
        "inst": inst,
        "TEST_calmar_intraday": get("TEST", "intraday", "calmar"),
        "TEST_calmar_dailyHAR": get("TEST", "daily_HAR", "calmar"),
        "TEST_calmar_flat": get("TEST", "flat", "calmar"),
        "TEST_calmar_delta_intraday_vs_daily": get("TEST", "intraday", "calmar") - get("TEST", "daily_HAR", "calmar"),
        "TEST_vol_intraday": get("TEST", "intraday", "vol_dailyR"),
        "TEST_vol_dailyHAR": get("TEST", "daily_HAR", "vol_dailyR"),
        "TEST_sharpe_intraday": get("TEST", "intraday", "sharpe_zeroday"),
        "TEST_sharpe_dailyHAR": get("TEST", "daily_HAR", "sharpe_zeroday"),
    }
    res.to_csv(OUT / f"sizing_{inst}.csv", index=False)
    json.dump(verdict, open(OUT / f"verdict_{inst}.json", "w"), indent=2)
    print(f"\nwrote {OUT / f'verdict_{inst}.json'}")
    return verdict


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "NQ")
