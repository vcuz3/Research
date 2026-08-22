"""Blind FIXED ENTRY-delay sweep (mirror of sweep_fixed_delay.py for exits).
Delays the breakout ENTRY fill by d bars (fast_entry=True, fast_exit=False,
release=fixed). Tests the crowding hypothesis: if entering AT the breakout is
arbitraged away, waiting d bars should hurt less (or help) in the RECENT era.
Scored on TRAIN (early 2011-2020) and TEST (recent 2020-2026) from one run each."""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core import engine2 as E
from .hyp_0035_exit_overlay import load, split_dates
from .hyp_0012_diffusion_cone import score_candidate

MAXD = 6

def run_entry(bars, bands, dm, d=None):
    kw = dict(fill_mode="next_open", require_vwap=True, exit_check="every_bar",
              stop_ref="both")
    if d is None:
        return E.run(bars, bands, dm, **kw)
    return E.run(bars, bands, dm, fast_overlay=True, fast_release="fixed",
                 fast_horizon=2, fast_entry=True, fast_exit=False,
                 fast_fixed_delay=d, **kw)

for inst in ("NQ","ES"):
    bars, bands, dm, dates = load(inst)
    train, test = split_dates(dates)
    base = run_entry(bars, bands, dm, None)
    bT = score_candidate(base, bars, train, inst, "b"); bE = score_candidate(base, bars, test, inst, "b")
    print(f"\n===== {inst}  ENTRY-delay sweep =====")
    print(f"  baseline: TRAIN Sharpe {bT.sharpe:+.3f} (n={bT.trades}, netR {bT.net_r:+.1f}) | "
          f"TEST Sharpe {bE.sharpe:+.3f} (n={bE.trades}, netR {bE.net_r:+.1f})")
    print(f"  {'delay':>5} | {'TRAIN dSh':>9} {'TRAIN nR':>8} {'grPt/t':>7} | {'TEST dSh':>9} {'TEST nR':>8} {'grPt/t':>7}")
    for d in range(1, MAXD+1):
        tr = run_entry(bars, bands, dm, d)
        sT = score_candidate(tr, bars, train, inst, f"d{d}")
        sE = score_candidate(tr, bars, test, inst, f"d{d}")
        print(f"  {d:>5} | {sT.sharpe-bT.sharpe:>+9.3f} {sT.net_r:>8.1f} {sT.net_pt_per_trade+ (0):>7.3f} | "
              f"{sE.sharpe-bE.sharpe:>+9.3f} {sE.net_r:>8.1f} {sE.net_pt_per_trade:>7.3f}")
