"""
Quantify the fill artifact (CLAUDE.md rule 2). Same pipeline, two fill modes:
  next_open    -- honest (fill at next bar open)
  signal_close -- aggressive same-bar (fill at the signal bar's own close)
Reports per-trade net + vol-targeted Sharpe/CAGR/DD for each, at the paper's
0.25-tick cost, so the headline's dependence on the fill is explicit.

Usage: python -m futures.nq.noise_vwap.scripts.run_fillcompare NQ 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run
from ..core.metrics import summarize


def voltarget(bars, tr, inst, cost, target=0.03, cap=8.0):
    pv = POINT_VALUE[inst]
    tr = tr.copy(); tr["net"] = tr["points"] - 2.0 * cost
    sess = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    pts = tr.groupby("date")["net"].sum().reindex(sess).fillna(0.0)
    dret = daily_returns(bars).reindex(sess)
    opx = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sess)
    realized = dret.shift(1).rolling(14, min_periods=14).std()
    mult = np.minimum(cap, target / realized)
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
    cagr = (equity / 100000.0) ** (1 / n_yr) - 1
    sharpe = act.mean() / act.std() * np.sqrt(252) if act.std() > 0 else 0.0
    eqc = (1 + rr).cumprod(); mdd = ((eqc - eqc.cummax()) / eqc.cummax()).min()
    return cagr, sharpe, float(mdd)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    cost = 2.25 / POINT_VALUE[inst] + 0.25 * TICK[inst]   # paper's 0.25 tick
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)

    print(f"=== {inst} lb={lookback} fill comparison (cost={cost:.3f}pt/side, paper 0.25tick) ===")
    for mode in ("next_open", "signal_close"):
        tr = run(bars, bands, fill_mode=mode)
        s = summarize(tr, inst, cost, mode)
        cagr, sh, mdd = voltarget(bars, tr, inst, cost)
        same_bar = int((tr["entry_tod"] == tr["exit_tod"]).sum())
        print(f"\n[{mode}]  ({same_bar} same-bar-tod trades)")
        print(f"  per-trade: gross={s['gross_pts_per_trade']:+.3f} "
              f"net={s['net_pts_per_trade']:+.3f}pt  hit={s['hit_rate']:.3f}  "
              f"day$net={s['day_net_mean_usd']:+.1f} t={s['day_net_t']:+.2f}")
        print(f"  vol-target(3%,8x): CAGR={cagr:+.1%} Sharpe={sh:.2f} maxDD={mdd:.1%}")


if __name__ == "__main__":
    main()
