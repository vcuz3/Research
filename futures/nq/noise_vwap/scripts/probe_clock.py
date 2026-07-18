"""
Is the decision-clock effect robust or overfit to a lucky minute? The concretum
clock is essentially the hh30 grid shifted 1 minute earlier (its 15:59 decision
can't fill, so its actionable set is 09:59..15:29). If a 1-minute shift really
swings Sharpe 1.08->1.31, then nearby offsets should be noisy by a similar amount
-- which would mean the "clock" is noise, not a real implementation gain.

Tests every within-half-hour minute offset o in -3..+3 applied to the :00/:30 grid,
plus the true concretum grid. NQ + ES, lb90, 0.25tick, 3%/8x, vwap gate ON.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run
from .forensic import sizing, per_trade_t, fees_pt


def grid(offset):
    return [h * 60 + m + offset for h in range(10, 16) for m in (0, 30)]


def main():
    for inst in ("NQ", "ES"):
        bars = load_rth(inst); b90 = noise_bands(bars, 90)
        cost = fees_pt(inst) + 0.25 * TICK[inst]
        print(f"\n{inst}  (lb90, 0.25tick, 3%/8x, vwap ON)")
        print(f"  {'clock':>16} {'n':>5} {'net_pt':>7} {'day$t':>6} {'CAGR':>7} {'Sharpe':>7} {'DD':>7}")
        for off in (-3, -2, -1, 0, 1, 2, 3):
            tods = grid(off)
            tr = run(bars, b90, decision_tods=tods, require_vwap=True)
            m = sizing(inst, bars, tr, cost)
            _, tt = per_trade_t(inst, tr, cost)
            print(f"  {'hh30'+f'{off:+d}min':>16} {m['n_trades']:>5} "
                  f"{m['pt_net']:>+7.3f} {tt:>+6.2f} {m['cagr']:>+7.1%} "
                  f"{m['sharpe']:>7.2f} {m['maxdd']:>+7.1%}")
        # true concretum
        conc = [570 + k - 1 for k in range(30, 391, 30)]
        tr = run(bars, b90, decision_tods=conc, require_vwap=True)
        m = sizing(inst, bars, tr, cost); _, tt = per_trade_t(inst, tr, cost)
        print(f"  {'concretum':>16} {m['n_trades']:>5} {m['pt_net']:>+7.3f} "
              f"{tt:>+6.2f} {m['cagr']:>+7.1%} {m['sharpe']:>7.2f} {m['maxdd']:>+7.1%}")


if __name__ == "__main__":
    main()
