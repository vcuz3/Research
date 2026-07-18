"""
Faithful-config headline (CAGR / Sharpe / maxDD) for samples ENDING at successive
year-ends, on the rebuilt Databento data. The published backtest predates the weak
2025-26 tape, so the fair comparison to the paper truncates there. Reuses the exact
forensic sizing machinery.

Run:  python -m futures.nq.noise_vwap.scripts.probe_thruyear
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run
from .forensic import sizing, per_trade_t, CLOCKS, fees_pt


def main():
    cutoffs = [pd.Timestamp(f"{y}-12-31") for y in (2018, 2021, 2023, 2024, 2025)]
    cutoffs.append(pd.Timestamp("2026-12-31"))  # full
    for inst in ("NQ", "ES"):
        bars = load_rth(inst)
        b90 = noise_bands(bars, 90)
        cost = fees_pt(inst) + 0.25 * TICK[inst]
        tr = run(bars, b90, decision_tods=CLOCKS["concretum"], require_vwap=True)
        print(f"\n=== {inst} faithful (concretum+VWAP, lb90, 0.25tick, 3%/8x) by end-year ===")
        for cut in cutoffs:
            bcut = bars[bars["date"] <= cut]
            tcut = tr[pd.to_datetime(tr["date"]) <= cut]
            if tcut.empty:
                continue
            m = sizing(inst, bcut, tcut, cost)
            mm, tt = per_trade_t(inst, tcut, cost)
            lab = "FULL " if cut.year == 2026 else f"{cut.year}"
            print(f"  thru {lab}: CAGR={m['cagr']:>+6.1%} Sh={m['sharpe']:>5.2f} "
                  f"DD={m['maxdd']:>+6.1%} n={m['n_trades']:>4d} net={m['pt_net']:+.3f}pt day$t={tt:+.2f}")
    print("\n  (Published: NQ 24.3%/1.67, ES 16.8%/1.25 — backtest ~thru 2024)")


if __name__ == "__main__":
    main()
