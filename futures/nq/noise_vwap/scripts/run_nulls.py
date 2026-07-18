"""
Null-C gauntlet (CLAUDE.md rule 17). Re-run the IDENTICAL pipeline -- same noise
bands, same VWAP, same engine, same fills, same costs -- on return-shuffled
sessions. The real per-day net P&L must beat the null net by a margin that is
significant under day-clustered SEs, or the timing signal is drift/machinery.

Usage: python -m futures.nq.noise_vwap.scripts.run_nulls NQ 90 20
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run
from ..core.nulls import null_c_returns, diffusivity
from ..core.metrics import summarize


def day_net_series(trades: pd.DataFrame, inst: str, cost_pts: float) -> pd.Series:
    if trades.empty:
        return pd.Series(dtype=float)
    net = trades["points"] - 2.0 * cost_pts
    return net.groupby(trades["date"]).sum() * POINT_VALUE[inst]


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    n_null = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    cost = 2.25 / POINT_VALUE[inst] + 0.50 * TICK[inst]   # mid of the grid

    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    real = run(bars, bands)
    real_day = day_net_series(real, inst, cost)
    real_mean = real_day.mean()
    real_gross = real["points"].mean()

    print(f"=== {inst} lookback={lookback} Null-C x{n_null} (cost={cost:.4f}pt/side) ===")
    print(f"REAL diffusivity |next_open-close| median = {diffusivity(bars):.4f} pt")
    print(f"REAL: n={len(real)} gross={real_gross:+.3f}pt/trade "
          f"day$net={real_mean:+.1f} (t={summarize(real, inst, cost)['day_net_t']:+.2f})")

    null_means, null_gross, null_diff, null_n = [], [], [], []
    for s in range(n_null):
        nb = null_c_returns(bars, seed=1000 + s)
        nbands = noise_bands(nb, lookback)
        nt = run(nb, nbands)
        null_means.append(day_net_series(nt, inst, cost).mean() if not nt.empty else 0.0)
        null_gross.append(nt["points"].mean() if not nt.empty else 0.0)
        null_n.append(len(nt))
        null_diff.append(diffusivity(nb))
        print(f"  null {s:2d}: diff={null_diff[-1]:.4f} n={null_n[-1]:>5d} "
              f"gross={null_gross[-1]:+.3f} day$net={null_means[-1]:+.1f}")

    nm = np.array(null_means)
    print(f"\n--- NULL-C SUMMARY ---")
    print(f"diffusivity gate: real={diffusivity(bars):.4f} "
          f"null median={np.median(null_diff):.4f} "
          f"(must match within ~1 tick)")
    print(f"null day$net: mean={nm.mean():+.2f} std={nm.std():+.2f} "
          f"[min {nm.min():+.1f}, max {nm.max():+.1f}]")
    print(f"real day$net: {real_mean:+.2f}")
    # z of real vs null distribution
    z = (real_mean - nm.mean()) / nm.std() if nm.std() > 0 else np.inf
    frac = (nm.mean() / real_mean) if real_mean != 0 else np.nan
    print(f"real beats null by z={z:+.2f} sigma of the null spread")
    print(f"null captures {frac*100:.1f}% of the real day$net "
          f"(machinery share; want < ~60%)")
    print(f"gross: real={real_gross:+.3f} null mean={np.mean(null_gross):+.3f}")


if __name__ == "__main__":
    main()
