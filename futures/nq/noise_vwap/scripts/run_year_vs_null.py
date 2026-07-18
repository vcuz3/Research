"""
Per-YEAR real vs Null-C. The aggregate z~2.9 could be a few high-vol trending
years (2018/2020/2022) beating the drift null while calm years are pure drift.
This decomposes the excess-over-drift by year.

For each year: real day$net mean, null day$net mean (avg over N nulls), and the
excess (real - null) with a z vs the across-null spread of that year's statistic.

Usage: python -m futures.nq.noise_vwap.scripts.run_year_vs_null NQ 90 15
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run
from ..core.nulls import null_c_returns


def year_day_net(trades: pd.DataFrame, inst: str, cost: float) -> pd.Series:
    """Mean day$net per year (day = sum of that day's trades)."""
    if trades.empty:
        return pd.Series(dtype=float)
    t = trades.copy()
    t["net"] = t["points"] - 2.0 * cost
    t["year"] = pd.to_datetime(t["date"]).dt.year
    day = t.groupby(["year", "date"])["net"].sum() * POINT_VALUE[inst]
    return day.groupby(level="year").mean()


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    n_null = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    cost = 2.25 / POINT_VALUE[inst] + 0.50 * TICK[inst]

    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    real = year_day_net(run(bars, bands), inst, cost)

    null_rows = []
    for s in range(n_null):
        nb = null_c_returns(bars, seed=3000 + s)
        nbands = noise_bands(nb, lookback)
        null_rows.append(year_day_net(run(nb, nbands), inst, cost))
    null_df = pd.DataFrame(null_rows)          # rows=nulls, cols=years
    null_mean = null_df.mean(axis=0)
    null_std = null_df.std(axis=0)

    print(f"=== {inst} lookback={lookback}: per-year real vs Null-C (x{n_null}) ===")
    print(f"{'yr':>4} {'real$':>8} {'null$':>8} {'excess':>8} {'null_sd':>8} {'z':>6}")
    for yr in real.index:
        r = real[yr]
        nm = null_mean.get(yr, np.nan)
        sd = null_std.get(yr, np.nan)
        ex = r - nm
        z = ex / sd if sd and sd > 0 else np.nan
        print(f"{yr:>4} {r:>+8.1f} {nm:>+8.1f} {ex:>+8.1f} {sd:>8.1f} {z:>+6.2f}")


if __name__ == "__main__":
    main()
