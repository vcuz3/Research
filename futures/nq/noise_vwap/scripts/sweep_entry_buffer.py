"""Anticipatory-entry (front-running) test — the OTHER form of the crowding
hypothesis the blind entry-DELAY sweep could not see.

The deployed strategy enters at the 30-min clock once price closes BEYOND the
noise band. "Everyone enters at the same location" (the band break). If crowding
had pushed the edge EARLIER (faster players front-run the break), then entering
before the band clears should help -- and should help MORE in the recent era.

Lever: threshold-mode entry with a band buffer in ATR units.
  entry_buf_atr < 0  -> enter when close > up - |b|*ATR  (ANTICIPATORY / earlier)
  entry_buf_atr = 0  -> enter at the band boundary        (the crowd's location)
  entry_buf_atr > 0  -> require a deeper break            (later / confirmation)
All arms use the SAME first-crossing threshold clock, so the buffer gradient and
its TRAIN-vs-TEST comparison are clean (the threshold-vs-clock difference is held
constant across the sweep). Fills stay next-open; reads are close-based (causal).

Reference within-mechanism arm is buf=0 (threshold entry at the band); the clock
baseline is printed for context. Read: is argmax buf NEGATIVE, and is the
anticipatory advantage LARGER in TEST than TRAIN? If yes -> edge moved earlier
(crowding). If the optimum is buf>=0 and anticipation hurts -> the break itself
is still the right entry, no front-running erosion.

Usage: python -u -m futures.nq.noise_vwap.scripts.sweep_entry_buffer
"""
from __future__ import annotations
import numpy as np, pandas as pd
from ..core import engine2 as E
from .hyp_0035_exit_overlay import load, split_dates
from .hyp_0012_diffusion_cone import score_candidate

BUFS = [-0.50, -0.40, -0.30, -0.20, -0.10, 0.0, 0.10, 0.20, 0.30]


def run_thresh(bars, bands, dm, buf):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", stop_ref="both",
                 entry_mode="threshold", entry_buf_atr=buf, entry_persist=1)


def run_clock(bars, bands, dm):
    return E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
                 exit_check="every_bar", stop_ref="both", entry_mode="clock")


def score(trades, bars, dates, inst, name):
    t = trades[trades["date"].isin(pd.Index(pd.to_datetime(dates)))].copy() \
        if "date" in trades.columns else trades
    return score_candidate(trades, bars, list(dates), inst, name)


for inst in ("NQ", "ES"):
    bars, bands, dm, dates = load(inst)
    train, test = split_dates(dates)
    clk = run_clock(bars, bands, dm)
    cb_tr = score_candidate(clk, bars, list(train), inst, "clk_train")
    cb_te = score_candidate(clk, bars, list(test), inst, "clk_test")
    print(f"\n===== {inst} anticipatory-entry (threshold) buffer sweep =====")
    print(f"clock baseline : TRAIN Sharpe {cb_tr.sharpe:+.3f} (n={cb_tr.trades}, netR {cb_tr.net_r:+.1f}) "
          f"| TEST Sharpe {cb_te.sharpe:+.3f} (n={cb_te.trades}, netR {cb_te.net_r:+.1f})")
    # threshold buf=0 reference
    ref = {}
    rows = []
    for b in BUFS:
        tr = run_thresh(bars, bands, dm, b)
        s_tr = score_candidate(tr, bars, list(train), inst, f"tr{b}")
        s_te = score_candidate(tr, bars, list(test), inst, f"te{b}")
        rows.append((b, s_tr, s_te))
        if b == 0.0:
            ref = {"tr": s_tr, "te": s_te}
    print(f"{'buf(ATR)':>9} | {'trTrd':>6} {'trShrp':>7} {'trNetPt':>7} {'trdSh':>6} "
          f"| {'teTrd':>6} {'teShrp':>7} {'teNetPt':>7} {'tedSh':>6}")
    for b, s_tr, s_te in rows:
        d_tr = s_tr.sharpe - ref["tr"].sharpe
        d_te = s_te.sharpe - ref["te"].sharpe
        gp_tr = s_tr.net_pt_per_trade
        gp_te = s_te.net_pt_per_trade
        tag = "  <- band break" if b == 0.0 else ("  (earlier)" if b < 0 else "  (deeper)")
        print(f"{b:>+9.2f} | {s_tr.trades:>6} {s_tr.sharpe:>+7.3f} {gp_tr:>7.3f} "
              f"{d_tr:>+6.3f} | {s_te.trades:>6} {s_te.sharpe:>+7.3f} {gp_te:>7.3f} "
              f"{d_te:>+6.3f}{tag}")
