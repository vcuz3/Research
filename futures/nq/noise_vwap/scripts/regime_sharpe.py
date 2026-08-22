"""Sharpe of baseline vs blind fixed-delay across CAUSAL session regimes.
Regimes labeled from info known at session OPEN (no lookahead): trailing-ATR
percentile (vol) and trailing-20-session close efficiency ratio (trend vs chop).
Reports per-cell session count + Sharpe for baseline, delay4, and each inst's
own optimal delay, plus the delay's dSharpe by regime."""
from __future__ import annotations
import numpy as np, pandas as pd
from .hyp_0035_exit_overlay import load, split_dates, run_ov
from .hyp_0012_diffusion_cone import round_trip_cost_points

OPT = {"NQ": 6, "ES": 2}

def sess_regimes(bars):
    g = bars.groupby("sdate")
    close = g["close"].last()
    atr = g["atr"].first()
    idx = pd.to_datetime(close.index)
    close.index = idx; atr.index = idx
    # vol regime: today's ATR vs trailing 250-session 33/67 pct (shifted -> causal)
    lo = atr.rolling(250, min_periods=60).quantile(0.33).shift(1)
    hi = atr.rolling(250, min_periods=60).quantile(0.67).shift(1)
    vol = pd.Series("mid", index=idx)
    vol[atr <= lo] = "loVol"; vol[atr >= hi] = "hiVol"
    # trend regime: trailing-20 close efficiency ratio, using closes up to YESTERDAY
    c = close
    net = (c.shift(1) - c.shift(21)).abs()
    denom = c.diff().abs().rolling(20).sum().shift(1)
    er = net / denom
    tlo = er.rolling(250, min_periods=60).quantile(0.33).shift(1)
    thi = er.rolling(250, min_periods=60).quantile(0.67).shift(1)
    trend = pd.Series("mid", index=idx)
    trend[er <= tlo] = "chop"; trend[er >= thi] = "trend"
    return pd.DataFrame({"vol": vol, "trend": trend})

def daily_r(trades, bars, dates, inst):
    idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    t["atr"]=t["date"].map(atr); t=t[np.isfinite(t["atr"])&(t["atr"]>0)].copy()
    t["net_r"]=(t["points"]-rt)/t["atr"]
    return t.groupby("date")["net_r"].sum().reindex(idx, fill_value=0.0)

def sharpe(day):
    sd = day.std(ddof=1)
    return day.mean()/sd*np.sqrt(252) if sd>0 else np.nan

for inst in ("NQ","ES"):
    bars, bands, dm, dates = load(inst)
    _, test = split_dates(dates)
    reg = sess_regimes(bars)
    idx = pd.Index(pd.to_datetime(test))
    reg = reg.reindex(idx)
    arms = {"base": run_ov(bars,bands,dm,fast_overlay=False),
            "d4": run_ov(bars,bands,dm,fast_overlay=True,fast_release="fixed",fast_horizon=2,fast_fixed_delay=4),
            f"d{OPT[inst]}": run_ov(bars,bands,dm,fast_overlay=True,fast_release="fixed",fast_horizon=2,fast_fixed_delay=OPT[inst])}
    dr = {k: daily_r(v, bars, test, inst) for k,v in arms.items()}
    print(f"\n================ {inst}  TEST (opt delay={OPT[inst]}) ================")
    for axis, order in (("vol",["loVol","mid","hiVol"]),("trend",["chop","mid","trend"])):
        print(f"\n  --- by {axis} regime ---   {'sess':>5} {'base':>7} {'d4':>7} {'dOpt':>7} {'d4-base':>8} {'dOpt-base':>9}")
        for lab in order:
            mask = reg[axis]==lab
            cd = idx[mask.values]
            if len(cd)<20: 
                print(f"    {lab:>7}: n={len(cd)} (skip)"); continue
            b=sharpe(dr["base"][cd]); s4=sharpe(dr["d4"][cd]); so=sharpe(dr[f"d{OPT[inst]}"][cd])
            print(f"    {lab:>7}: {'':>5} {len(cd):>5} {b:>7.3f} {s4:>7.3f} {so:>7.3f} {s4-b:>+8.3f} {so-b:>+9.3f}")
