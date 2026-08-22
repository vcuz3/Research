"""Ad-hoc: sweep the BLIND fixed stop-exit delay 1..N bars on NQ/ES TEST era,
report Sharpe / netR / maxDD / recent, and by-year Sharpe & sumR. Answers whether
the blind-delay Sharpe peaks at ~4 bars and whether that transfers to ES / holds
across years. Not a registered experiment — diagnostic for the POST_STOP question."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core import session as S
from .hyp_0035_exit_overlay import load, split_dates, run_ov
from .hyp_0012_diffusion_cone import score_candidate, round_trip_cost_points

MAXD = 8

def year_table(trades, bars, dates, inst):
    idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    t["atr"] = t["date"].map(atr); t = t[np.isfinite(t["atr"]) & (t["atr"]>0)].copy()
    t["net_r"] = (t["points"]-rt)/t["atr"]
    t["yr"] = pd.to_datetime(t["date"]).dt.year
    out = {}
    for yr, g in t.groupby("yr"):
        # daily aggregation within the year over that year's TEST dates
        ydates = idx[(idx.year==yr)]
        day = g.groupby("date")["net_r"].sum().reindex(ydates, fill_value=0.0)
        sd = day.std(ddof=1)
        out[yr] = (day.sum(), day.mean()/sd*np.sqrt(252) if sd>0 else 0.0)
    return out

for inst in ("NQ","ES"):
    bars, bands, dm, dates = load(inst)
    _, test = split_dates(dates)
    base_tr = run_ov(bars, bands, dm, fast_overlay=False)
    base = score_candidate(base_tr, bars, test, inst, "base")
    print(f"\n===== {inst}  TEST  (n_base={base.trades}) =====")
    print(f"{'delay':>5} {'n':>5} {'sumR':>8} {'dSumR':>7} {'Sharpe':>7} {'dSharpe':>8} {'maxDD':>7} {'recent':>7}")
    print(f"{'base':>5} {base.trades:>5} {base.net_r:>8.2f} {'':>7} {base.sharpe:>7.4f} {'':>8} {base.max_dd:>7.2f} {base.recent_sharpe:>7.4f}")
    rows={}
    trades_by_delay={}
    for d in range(1, MAXD+1):
        tr = run_ov(bars, bands, dm, fast_overlay=True, fast_release="fixed", fast_horizon=2, fast_fixed_delay=d)
        sc = score_candidate(tr, bars, test, inst, f"d{d}")
        trades_by_delay[d]=tr
        print(f"{d:>5} {sc.trades:>5} {sc.net_r:>8.2f} {sc.net_r-base.net_r:>+7.2f} {sc.sharpe:>7.4f} {sc.sharpe-base.sharpe:>+8.4f} {sc.max_dd:>7.2f} {sc.recent_sharpe:>7.4f}")
    # by-year Sharpe for a few key delays
    print(f"  by-year Sharpe (base vs d2 vs d4 vs d6):")
    yb = year_table(base_tr, bars, test, inst)
    yd = {d: year_table(trades_by_delay[d], bars, test, inst) for d in (2,4,6)}
    yrs = sorted(yb)
    print(f"    {'yr':>5} {'base':>7} {'d2':>7} {'d4':>7} {'d6':>7}   (sumR: {'base':>6} {'d4':>6})")
    for yr in yrs:
        b=yb[yr][1]; s2=yd[2].get(yr,(0,0))[1]; s4=yd[4].get(yr,(0,0))[1]; s6=yd[6].get(yr,(0,0))[1]
        print(f"    {yr:>5} {b:>7.3f} {s2:>7.3f} {s4:>7.3f} {s6:>7.3f}   {yb[yr][0]:>6.2f} {yd[4].get(yr,(0,0))[0]:>6.2f}")
