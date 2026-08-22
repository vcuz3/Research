"""Decompose the NQ recent-era fade into its components, FULL history (not just
TEST). The entry-delay sweep ruled out entry-location crowding as the cause, so
the fade must live in signal follow-through. Attribute daily Sharpe to:
  - signal frequency   : trades / session
  - hit rate           : win% (points>0)
  - win magnitude       : mean gross points on winners
  - loss magnitude      : mean gross points on losers
  - net edge/trade      : net R/trade
and print daily mean/std/Sharpe + ATR context. Both NQ and ES for contrast.

Baseline = deployed continuous-stop book (entry_mode=clock, stop_ref=both,
every_bar exit, next_open fills). Reads are causal; ATR is per-session.

Usage: python -u -m futures.nq.noise_vwap.scripts.diag_nonstationarity
"""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core import engine2 as E
from .hyp_0035_exit_overlay import load
from .hyp_0012_diffusion_cone import round_trip_cost_points


def run_base(bars, bands, dm):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", stop_ref="both", entry_mode="clock")


for inst in ("NQ", "ES"):
    bars, bands, dm, dates = load(inst)
    idx = pd.Index(pd.to_datetime(dates))
    t = run_base(bars, bands, dm)
    t = t[t["date"].isin(idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    t["gross_r"] = t["points"] / t["atr"]
    t["net_r"] = (t["points"] - rt) / t["atr"]
    t["yr"] = pd.to_datetime(t["date"]).dt.year
    day_atr = bars.groupby("sdate")["atr"].first()
    day_atr.index = pd.to_datetime(day_atr.index)

    print(f"\n===== {inst} non-stationarity decomposition (FULL history) =====")
    print(f"{'yr':>5} {'sess':>5} {'trd':>5} {'trd/s':>6} {'win%':>5} "
          f"{'winPt':>6} {'lossPt':>7} {'grPt/t':>7} {'netR/t':>7} "
          f"{'dMean':>8} {'dStd':>6} {'Sharpe':>7} {'ATR':>7}")
    for yr, g in t.groupby("yr"):
        ydates = idx[idx.year == yr]
        day = g.groupby("date")["net_r"].sum().reindex(ydates, fill_value=0.0)
        sd = day.std(ddof=1)
        shp = day.mean() / sd * np.sqrt(252) if sd > 0 else 0.0
        wins = g[g["points"] > 0]["points"]
        losses = g[g["points"] <= 0]["points"]
        win_pct = len(wins) / len(g) * 100 if len(g) else 0.0
        win_pt = wins.mean() if len(wins) else 0.0
        loss_pt = losses.mean() if len(losses) else 0.0
        matr = day_atr[day_atr.index.year == yr].mean()
        print(f"{yr:>5} {len(ydates):>5} {len(g):>5} {len(g)/max(len(ydates),1):>6.2f} "
              f"{win_pct:>5.1f} {win_pt:>6.2f} {loss_pt:>7.2f} {g['points'].mean():>7.3f} "
              f"{g['net_r'].mean():>+7.4f} {day.mean():>+8.4f} {sd:>6.3f} {shp:>7.3f} {matr:>7.2f}")
