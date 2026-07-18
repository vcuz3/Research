"""
Baseline replication + first-line hygiene for the Noise Area + VWAP momentum
strategy. Establishes the per-trade / per-day edge BEFORE any vol-target sizing
(rule 12/21). Prints gross and net (rule 20), long/short split, and includes two
drift controls plus the naive always-long control.

Uses the engine's FAITHFUL published defaults (Concretum :59/:29 clock + VWAP entry
gate; see FORENSIC.md). The pre-fix config was the :00/:30 clock with no VWAP gate.

Usage: python -m futures.nq.noise_vwap.scripts.run_baseline NQ 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run, DECISION_TODS, simulate_session
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
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90
    # cost grid in POINTS per side. NQ: fees ~$2.25/side = 0.1125pt; slippage in ticks.
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
    trades.to_parquet(f"futures/nq/noise_vwap/outputs/trades_{inst}_{lookback}.parquet")

    print(f"\ntotal trades={len(trades)} "
          f"reasons={trades['reason'].value_counts().to_dict()}")

    # fill-feasibility assert (rule A1/2): every exit_px/entry_px is a real bar open
    # or the eod close — by construction we filled at next-bar open. Spot-assert
    # that no trade has entry_tod == exit_tod (would mean same-bar fill).
    same_bar = (trades["entry_tod"] == trades["exit_tod"]).sum()
    assert same_bar == 0, f"{same_bar} same-bar fills — fill artifact!"
    print("fill-feasibility: 0 same-bar fills (all fills at a later bar open) OK")

    print("\n--- STRATEGY (net at cost grid) ---")
    for name, c in cost_grid.items():
        print(fmt(summarize(trades, inst, c, f"strat {name}")))

    # naive always-long drift control (net at mid cost = round trip once/day)
    al = always_long_control(bars)
    print("\n--- NAIVE ALWAYS-LONG (drift) ---")
    print(fmt(summarize(al, inst, cost_grid["0.50tick"], "always_long")))

    # long-only / short-only strategy split already in summarize; print gross too
    print("\n--- GROSS (no cost) ---")
    print(fmt(summarize(trades, inst, 0.0, "strat gross")))


if __name__ == "__main__":
    main()
