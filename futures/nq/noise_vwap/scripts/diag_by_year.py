"""Per-year baseline diagnostics on TEST era: sessions, trades, gross/net sumR,
daily mean/std, Sharpe, win rate, mean ATR (vol regime), avg gross points/trade.
Diagnose why NQ degrades 2024->2026 vs ES holding up."""
from __future__ import annotations
import numpy as np, pandas as pd
from .hyp_0035_exit_overlay import load, split_dates, run_ov
from .hyp_0012_diffusion_cone import round_trip_cost_points

for inst in ("NQ","ES"):
    bars, bands, dm, dates = load(inst)
    _, test = split_dates(dates)
    idx = pd.Index(pd.to_datetime(test))
    tr = run_ov(bars, bands, dm, fast_overlay=False)
    t = tr[tr["date"].isin(idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    t["atr"]=t["date"].map(atr); t=t[np.isfinite(t["atr"])&(t["atr"]>0)].copy()
    t["gross_r"]=t["points"]/t["atr"]; t["net_r"]=(t["points"]-rt)/t["atr"]
    t["yr"]=pd.to_datetime(t["date"]).dt.year
    # per-day ATR for vol regime
    day_atr = bars.groupby("sdate")["atr"].first()
    day_atr.index = pd.to_datetime(day_atr.index)
    print(f"\n===== {inst} baseline by year (TEST) =====")
    print(f"{'yr':>5} {'sess':>5} {'trd':>5} {'grossR':>7} {'netR':>7} {'dMean':>7} {'dStd':>6} {'Sharpe':>7} {'win%':>5} {'grPt/t':>7} {'ATR':>7}")
    for yr,g in t.groupby("yr"):
        ydates=idx[idx.year==yr]
        day=g.groupby("date")["net_r"].sum().reindex(ydates,fill_value=0.0)
        sd=day.std(ddof=1); shp=day.mean()/sd*np.sqrt(252) if sd>0 else 0
        win=(g["points"]>0).mean()*100
        matr=day_atr[day_atr.index.year==yr].mean()
        print(f"{yr:>5} {len(ydates):>5} {len(g):>5} {g['gross_r'].sum():>7.2f} {g['net_r'].sum():>7.2f} "
              f"{day.mean():>+7.4f} {sd:>6.3f} {shp:>7.3f} {win:>5.1f} {(g['points']).mean():>7.3f} {matr:>7.2f}")
