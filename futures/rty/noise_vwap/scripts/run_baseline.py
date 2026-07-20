"""
Baseline replication + first-line hygiene for the Noise Area + VWAP momentum
strategy on RTY (E-mini Russell 2000). Faithful port of the NQ/ES baseline runner. Establishes
the per-trade / per-day edge BEFORE any vol-target sizing (rule 12/21). Prints gross
and net (rule 20), long/short split, and includes the naive always-long drift
control.

Uses the engine's FAITHFUL published defaults (Concretum :59/:29 clock + VWAP entry
gate; see the NQ project FORENSIC.md).

Usage: python -m futures.rty.noise_vwap.scripts.run_baseline RTY 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run, DECISION_TODS
from ..core.metrics import summarize, fmt


def always_long_control(bars: pd.DataFrame) -> pd.DataFrame:
    """Enter long at the FIRST decision bar's next open, hold to RTH close.
    Captures the pure intraday drift — the thing the real edge must beat."""
    first_dt = DECISION_TODS[0]
    out = []
    for d, g in bars.groupby("date", sort=False):
        g = g.sort_values("tod").reset_index(drop=True)
        tod = g["tod"].to_numpy()
        idx = np.where(tod == first_dt)[0]
        if len(idx) == 0 or idx[0] + 1 >= len(g):
            continue
        i = idx[0]
        entry = g["open"].iloc[i + 1]
        exit_ = g["close"].iloc[-1]
        out.append(dict(date=d, side=1, points=exit_ - entry))
    return pd.DataFrame(out)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "RTY"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    # cost grid in POINTS per side. Fees ~$2.25/side -> pts = 2.25 / point_value.
    # slippage expressed in ticks (GC tick = 0.10 pt).
    fees_pt = 2.25 / POINT_VALUE[inst]
    tick = TICK[inst]
    cost_grid = {
        "0.25tick": fees_pt + 0.25 * tick,
        "0.50tick": fees_pt + 0.50 * tick,
        "1.0tick": fees_pt + 1.0 * tick,
    }

    print(f"=== {inst} lookback={lookback} ===")
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    print(f"sessions={bars['date'].nunique()} "
          f"{bars['date'].min().date()}->{bars['date'].max().date()} "
          f"band_rows={len(bands)}")

    trades = run(bars, bands)
    outdir = "futures/rty/noise_vwap/outputs"
    import os
    os.makedirs(outdir, exist_ok=True)
    trades.to_parquet(f"{outdir}/trades_{inst}_{lookback}.parquet")

    print(f"\ntotal trades={len(trades)} "
          f"reasons={trades['reason'].value_counts().to_dict()}")

    # fill-feasibility assert (rule A1/2): every fill is a real later bar open.
    same_bar = (trades["entry_tod"] == trades["exit_tod"]).sum()
    assert same_bar == 0, f"{same_bar} same-bar fills — fill artifact!"
    print("fill-feasibility: 0 same-bar fills (all fills at a later bar open) OK")

    print("\n--- STRATEGY (net at cost grid) ---")
    for name, c in cost_grid.items():
        print(fmt(summarize(trades, inst, c, f"strat {name}")))

    # naive always-long drift control
    al = always_long_control(bars)
    print("\n--- NAIVE ALWAYS-LONG (drift) ---")
    print(fmt(summarize(al, inst, cost_grid["0.50tick"], "always_long")))

    print("\n--- GROSS (no cost) ---")
    print(fmt(summarize(trades, inst, 0.0, "strat gross")))


if __name__ == "__main__":
    main()
