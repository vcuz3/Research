"""
Chase the residual standalone-Sharpe gap (faithful config gives NQ 1.31/ES 0.87
vs published 1.67/1.25) after ruling out fills, cost, stop-frequency, Sharpe-
frequency. Two remaining levers:

  A. Sample period  -- is the gap partly recent decay (2025 drag)? Report the
     faithful-config Sharpe on expanding end-dates.
  B. Vol-target basis -- I scale leverage by the INSTRUMENT's daily-return vol
     (per the plan). If the strategy's own vol isn't proportional to it, that
     adds leverage-timing noise and lowers Sharpe. Test sizing by the STRATEGY's
     OWN trailing realized vol instead.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run
from .forensic import sizing, fees_pt

CONC = [570 + k - 1 for k in range(30, 391, 30)]


def sizing_own_vol(inst, bars, trades, cost_pt, target=0.03, cap=8.0):
    """Vol-target using the STRATEGY's own trailing 14-day realized daily return."""
    pv = POINT_VALUE[inst]
    t = trades.copy(); t["net"] = t["points"] - 2.0 * cost_pt
    sess = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    pts = t.groupby("date")["net"].sum().reindex(sess).fillna(0.0)
    opx = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sess)
    # strategy 1-lot return proxy = day points * pv / (1-contract notional)
    strat_ret_1lot = (pts * pv) / (opx * pv)          # = pts / opx
    realized = strat_ret_1lot.shift(1).rolling(14, min_periods=14).std()
    mult = np.minimum(cap, target / realized).replace([np.inf, -np.inf], np.nan)
    equity = 100000.0; rr = []
    for d in sess:
        m = mult.get(d, np.nan); px = opx.get(d, np.nan)
        if not np.isfinite(m) or not np.isfinite(px) or px <= 0:
            rr.append(0.0); continue
        c = np.floor(equity * m / (px * pv))
        pnl = c * pts.get(d, 0.0) * pv
        rr.append(pnl / equity if equity > 0 else 0.0); equity += pnl
    rr = pd.Series(rr, index=sess)
    act = rr[realized.reindex(sess).notna()]
    n_yr = (sess.iloc[-1] - sess.iloc[0]).days / 365.25
    cagr = (equity / 100000.0) ** (1 / n_yr) - 1 if equity > 0 else -1
    sh = act.mean() / act.std() * np.sqrt(252) if act.std() > 0 else 0.0
    eqc = (1 + rr).cumprod(); mdd = float(((eqc - eqc.cummax()) / eqc.cummax()).min())
    return dict(cagr=cagr, sharpe=sh, maxdd=mdd, ret=rr, annvol=act.std()*np.sqrt(252))


def sharpe_through(ret, end_year):
    r = ret[ret.index.year <= end_year]
    r = r[r.index >= r[r != 0].index.min()]
    return r.mean() / r.std() * np.sqrt(252) if r.std() > 0 else 0.0


def main():
    for inst, tv, cap in (("NQ", 0.03, 8.0), ("ES", 0.03, 8.0)):
        bars = load_rth(inst); b90 = noise_bands(bars, 90)
        cost = fees_pt(inst) + 0.25 * TICK[inst]
        tr = run(bars, b90, decision_tods=CONC, require_vwap=True)
        m_inst = sizing(inst, bars, tr, cost, target=tv, cap=cap)
        m_own = sizing_own_vol(inst, bars, tr, cost, target=tv, cap=cap)
        print(f"\n{inst} (faithful, 0.25tick, {tv:.0%}/{cap:.0f}x)")
        print(f"  vol-basis=INSTRUMENT: CAGR={m_inst['cagr']:+.1%} "
              f"Sh={m_inst['sharpe']:.2f} DD={m_inst['maxdd']:+.1%} annVol={m_inst['annvol']:.1%}")
        print(f"  vol-basis=STRATEGY  : CAGR={m_own['cagr']:+.1%} "
              f"Sh={m_own['sharpe']:.2f} DD={m_own['maxdd']:+.1%} annVol={m_own['annvol']:.1%}")
        print(f"  Sharpe by end-year (INSTRUMENT-vol sizing):")
        for ey in (2018, 2019, 2021, 2023, 2024, 2025, 2026):
            print(f"    thru {ey}: {sharpe_through(m_inst['ret'], ey):.2f}")


if __name__ == "__main__":
    main()
