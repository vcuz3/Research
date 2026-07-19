"""
Null-C gauntlet (CLAUDE.md rule 17). Re-run the IDENTICAL pipeline -- same noise
bands, same VWAP, same engine, same fills, same costs -- on return-shuffled
sessions. The real per-day net P&L must beat the null net by a margin that is
significant under day-clustered SEs, or the timing signal is drift/machinery.

Usage: python -m futures.nq.noise_vwap.scripts.run_nulls NQ 90 30 0.25
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run
from ..core.nulls import null_c_returns, diffusivity
from ..core.metrics import summarize


def day_net_series(trades: pd.DataFrame, inst: str, cost_pts: float,
                   all_dates: pd.Index) -> pd.Series:
    """Daily one-contract P&L with zero-trade eligible sessions retained."""
    if trades.empty:
        return pd.Series(0.0, index=all_dates, dtype=float)
    net = trades["points"] - 2.0 * cost_pts
    day = net.groupby(trades["date"]).sum() * POINT_VALUE[inst]
    return day.reindex(all_dates, fill_value=0.0)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    n_null = int(sys.argv[3]) if len(sys.argv) > 3 else 20
    slip_ticks = float(sys.argv[4]) if len(sys.argv) > 4 else 0.25
    cost = 2.25 / POINT_VALUE[inst] + slip_ticks * TICK[inst]

    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    all_dates = pd.Index(np.sort(bands["date"].unique()))
    real = run(bars, bands)
    real_day = day_net_series(real, inst, cost, all_dates)
    real_mean = real_day.mean()
    real_gross = real["points"].mean()

    print(f"=== {inst} lookback={lookback} Null-C x{n_null} "
          f"(slippage={slip_ticks:.2f}tick + fees, cost={cost:.4f}pt/side) ===")
    print(f"REAL diffusivity |next_open-close| median = {diffusivity(bars):.4f} pt")
    print(f"REAL: n={len(real)} gross={real_gross:+.3f}pt/trade "
          f"day$net={real_mean:+.1f} (t={summarize(real, inst, cost)['day_net_t']:+.2f})")

    null_means, null_gross, null_diff, null_n = [], [], [], []
    for s in range(n_null):
        nb = null_c_returns(bars, seed=1000 + s)
        nbands = noise_bands(nb, lookback)
        nt = run(nb, nbands)
        null_means.append(day_net_series(nt, inst, cost, all_dates).mean())
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
    p = (1.0 + float((nm >= real_mean).sum())) / (len(nm) + 1.0)
    frac = (nm.mean() / real_mean) if real_mean != 0 else np.nan
    print(f"real beats null by z={z:+.2f} sigma of the null spread; "
          f"upper-tail p={p:.4f}")
    print(f"null captures {frac*100:.1f}% of the real day$net "
          f"(machinery share; want < ~60%)")
    print(f"gross: real={real_gross:+.3f} null mean={np.mean(null_gross):+.3f}")


if __name__ == "__main__":
    main()
