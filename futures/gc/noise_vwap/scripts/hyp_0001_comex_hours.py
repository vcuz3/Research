"""
HYP-0001: does the gold-native COMEX pit session (08:20-13:30 ET) beat the
inherited equity-RTH window (09:30-16:00 ET) for the Noise Area + VWAP strategy?

Same machinery for both windows (core/session_hours.py generalizes core/data.py):
same 90-session noise lookback, Concretum 30-min clock from the window open, VWAP
reset at open, next-open honest fills, forced flatten at the window's last bar.
Only [start,end) changes. Reports per-trade/day metrics for each window and runs a
claim-matched Null-C (path-preserving return shuffle) through the full pipeline for
each, so a window's gross edge is measured against its own noise.

Usage: python -m futures.gc.noise_vwap.scripts.hyp_0001_comex_hours GC 90 20 0.50
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.session_hours import load_window, noise_bands_window, decision_tods
from ..core.data import POINT_VALUE, TICK
from ..core.engine import run
from ..core.nulls import null_c_returns, diffusivity
from ..core.metrics import summarize

WINDOWS = {
    "equity_0930_1600": (570, 960),   # inherited baseline
    "comex_0820_1330": (500, 810),    # gold-native COMEX pit session
}


def day_net_series(trades, inst, cost_pts, all_dates):
    if trades.empty:
        return pd.Series(0.0, index=all_dates, dtype=float)
    net = trades["points"] - 2.0 * cost_pts
    day = net.groupby(trades["date"]).sum() * POINT_VALUE[inst]
    return day.reindex(all_dates, fill_value=0.0)


def eval_window(inst, name, start, end, lookback, n_null, cost):
    bars = load_window(inst, start, end)
    bands = noise_bands_window(bars, lookback, start)
    dtods = decision_tods(start, end)
    all_dates = pd.Index(np.sort(bands["date"].unique()))
    real = run(bars, bands, decision_tods=dtods)
    s = summarize(real, inst, cost)
    real_day = day_net_series(real, inst, cost, all_dates)
    real_mean = real_day.mean()

    print(f"\n=== {name}  window ET tod=[{start},{end})  sessions={bars['date'].nunique()} "
          f"decisions={dtods[0]}..{dtods[-1]} ===")
    print(f"REAL: n={s['n_trades']} ({s['trades_per_day']:.2f}/day) "
          f"gross={s['gross_pts_per_trade']:+.3f}pt net={s['net_pts_per_trade']:+.3f}pt "
          f"hit={s['hit_rate']:.3f} day$net={s['day_net_mean_usd']:+.1f} "
          f"t={s['day_net_t']:+.2f} netSh={s['sharpe_net_daily']:.2f} "
          f"grossSh={summarize(real, inst, 0.0)['sharpe_net_daily']:.2f}")
    print(f"      diffusivity |next_open-close| median = {diffusivity(bars):.4f} pt")

    # Null-C on this window
    null_means, null_gross, null_diff = [], [], []
    for k in range(n_null):
        nb = null_c_returns(bars, seed=2000 + k)
        nbands = noise_bands_window(nb, lookback, start)
        nt = run(nb, nbands, decision_tods=dtods)
        null_means.append(day_net_series(nt, inst, cost, all_dates).mean())
        null_gross.append(nt["points"].mean() if not nt.empty else 0.0)
        null_diff.append(diffusivity(nb))
    nm = np.array(null_means)
    z = (real_mean - nm.mean()) / nm.std() if nm.std() > 0 else np.inf
    p = (1.0 + float((nm >= real_mean).sum())) / (len(nm) + 1.0)
    frac = (nm.mean() / real_mean) if real_mean != 0 else np.nan
    print(f"  NULL-C x{n_null}: diff real={diffusivity(bars):.4f} null={np.median(null_diff):.4f} | "
          f"null day$net mean={nm.mean():+.2f} std={nm.std():.2f} | real={real_mean:+.2f}")
    print(f"  -> real beats null z={z:+.2f}  upper-tail p={p:.4f}  "
          f"null captures {frac*100:.0f}% (want <~60%)  "
          f"gross real={s['gross_pts_per_trade']:+.3f} null={np.mean(null_gross):+.3f}")
    return dict(name=name, netSh=s['sharpe_net_daily'], net_t=s['day_net_t'],
                gross=s['gross_pts_per_trade'], z=z, p=p, real_mean=real_mean)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "GC"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    n_null = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    slip_ticks = float(sys.argv[4]) if len(sys.argv) > 4 else 0.50
    cost = 2.25 / POINT_VALUE[inst] + slip_ticks * TICK[inst]
    print(f"HYP-0001 {inst} lookback={lookback} Null-C x{n_null} "
          f"cost={cost:.4f}pt/side ({slip_ticks:.2f}tick+fees)")

    res = []
    for name, (start, end) in WINDOWS.items():
        res.append(eval_window(inst, name, start, end, lookback, n_null, cost))

    base = res[0]; comex = res[1]
    print("\n================ VERDICT ================")
    print(f"equity  netSh={base['netSh']:.2f} t={base['net_t']:+.2f} "
          f"gross={base['gross']:+.3f} Null-C z={base['z']:+.2f} p={base['p']:.3f}")
    print(f"comex   netSh={comex['netSh']:.2f} t={comex['net_t']:+.2f} "
          f"gross={comex['gross']:+.3f} Null-C z={comex['z']:+.2f} p={comex['p']:.3f}")
    dSh = comex['netSh'] - base['netSh']
    print(f"COMEX - equity net Sharpe delta = {dSh:+.3f}")
    print("HYP-0001 supported only if COMEX materially beats equity net Sharpe AND "
          "COMEX gross beats its Null-C (z high, p low).")


if __name__ == "__main__":
    main()
