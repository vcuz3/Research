"""
Per-year era breakdown + sigma-in-ticks context (CLAUDE.md rule 19). An edge
quoted over 2011-2026 is flattered by the recent high-price era; check whether it
survives year by year and whether the per-trade points are meaningful vs the
period's typical bar size.

Usage: python -m futures.nq.noise_vwap.scripts.run_eras NQ 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run
from ..core.metrics import _cluster_t


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    cost = 2.25 / POINT_VALUE[inst] + 0.50 * TICK[inst]
    pv = POINT_VALUE[inst]

    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    tr = run(bars, bands)
    tr["net"] = tr["points"] - 2.0 * cost
    tr["year"] = pd.to_datetime(tr["date"]).dt.year

    # typical RTH bar range per year (context for "is +4pt meaningful")
    bars["year"] = pd.to_datetime(bars["date"]).dt.year
    bar_rng = (bars["high"] - bars["low"]).groupby(bars["year"]).median()

    print(f"=== {inst} lookback={lookback} per-year (cost={cost:.3f}pt/side) ===")
    print(f"{'yr':>4} {'n':>5} {'gross':>7} {'net':>7} {'hit':>5} "
          f"{'day$net':>8} {'t':>6} {'net_tick':>8} {'barRng':>7}")
    for yr, g in tr.groupby("year"):
        day = g.groupby("date")["net"].sum() * pv
        m, t = _cluster_t(day)
        net_ticks = g["net"].mean() / TICK[inst]
        print(f"{yr:>4} {len(g):>5} {g['points'].mean():>+7.2f} "
              f"{g['net'].mean():>+7.2f} {(g['net']>0).mean():>5.2f} "
              f"{m:>+8.1f} {t:>+6.2f} {net_ticks:>+8.1f} {bar_rng.get(yr, np.nan):>7.2f}")

    # long vs short by year
    print(f"\n{'yr':>4} {'L_net':>7} {'nL':>5} {'S_net':>7} {'nS':>5}")
    for yr, g in tr.groupby("year"):
        L = g[g.side == 1]["net"]
        S = g[g.side == -1]["net"]
        print(f"{yr:>4} {L.mean():>+7.2f} {len(L):>5} {S.mean():>+7.2f} {len(S):>5}")


if __name__ == "__main__":
    main()
