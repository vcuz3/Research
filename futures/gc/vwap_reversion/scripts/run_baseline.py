"""
Baseline run for the GC VWAP-band mean-reversion (fade) strategy.

Establishes the per-trade / per-day edge with HONEST fills (rule A) and reports
gross AND net (rule 20) at a cost grid, plus the metrics requested: trade count,
Sharpe, Calmar, win rate, RR/payoff, net $ P&L, and the reason/same-bar mix.

It also runs two fill-sensitivity variants that target the two optimistic
assumptions of a limit-fade baseline:
  * strict trade-THROUGH entry (queue guard, rule 4): require the extreme to
    pierce the band by 1 tick before the limit is deemed filled;
  * same-bar TARGET allowed (path-optimistic, rule 3): credit a same-entry-bar
    reversion win. If the edge only appears here, it is an intrabar-path artifact.

Usage: python -m futures.gc.vwap_reversion.scripts.run_baseline GC [1m|1s]
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, load_rth_1s, TICK, POINT_VALUE
from ..core.engine import run
from ..core.metrics import summarize, fmt


def assert_fills(bars: pd.DataFrame, trades: pd.DataFrame):
    """Every credited fill must have been attainable within its bar (rule 1/3)."""
    if trades.empty:
        return
    # entry: short filled at a level the entry bar's HIGH reached; long at LOW.
    ent = trades.merge(bars[["date", "tsec", "high", "low"]],
                       left_on=["date", "entry_tsec"], right_on=["date", "tsec"],
                       how="left", suffixes=("", "_e"))
    bad_short = ((ent.side == -1) & (ent.entry_px > ent.high + 1e-9)).sum()
    bad_long = ((ent.side == 1) & (ent.entry_px < ent.low - 1e-9)).sum()
    assert bad_short == 0 and bad_long == 0, \
        f"unattainable entry: {bad_short} short above high, {bad_long} long below low"
    # exit: stop/target fill must be inside the exit bar's range (eod exempt).
    ex = trades[trades.reason != "eod"].merge(
        bars[["date", "tsec", "high", "low"]],
        left_on=["date", "exit_tsec"], right_on=["date", "tsec"], how="left")
    bad_x = ((ex.exit_px > ex.high + 1e-9) | (ex.exit_px < ex.low - 1e-9)).sum()
    assert bad_x == 0, f"unattainable exit fill on {bad_x} trades"


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "GC"
    res = sys.argv[2] if len(sys.argv) > 2 else "1s"
    loader = load_rth_1s if res == "1s" else load_rth
    fees_pt = 2.25 / POINT_VALUE[inst]
    tick = TICK[inst]
    cost_grid = {
        "0.25tick": fees_pt + 0.25 * tick,
        "0.50tick": fees_pt + 0.50 * tick,
        "1.0tick": fees_pt + 1.0 * tick,
    }

    print(f"=== {inst} VWAP-band fade baseline [{res}] (kb=2, ks=3 -> fixed 2RR) ===")
    bars = loader(inst)
    all_dates = bars["date"].drop_duplicates()
    print(f"sessions={all_dates.nunique()} "
          f"{bars['date'].min().date()}->{bars['date'].max().date()} "
          f"bars={len(bars):,}")

    trades = run(bars)   # conservative defaults: touch-fill, no same-bar target
    assert_fills(bars, trades)

    outdir = os.path.join(os.path.dirname(__file__), "..", "outputs")
    os.makedirs(outdir, exist_ok=True)
    trades.to_parquet(os.path.join(outdir, f"trades_{inst}_{res}.parquet"))

    sb = int(trades["same_bar"].sum())
    print(f"\ntotal trades={len(trades)} same-bar(entry==exit)={sb} "
          f"({sb/max(1,len(trades)):.1%}) reasons={trades['reason'].value_counts().to_dict()}")
    print(f"long={int((trades.side==1).sum())} short={int((trades.side==-1).sum())}")
    print("fill-feasibility: OK (all entry/exit fills attainable within their bar)")

    print("\n--- BASELINE (conservative: touch-fill entry, adverse same-bar) ---")
    for name, c in cost_grid.items():
        print(fmt(summarize(trades, all_dates, inst, c, f"net {name}")))
    # gross line (cost 0)
    g = summarize(trades, all_dates, inst, 0.0, "gross")
    print(fmt(g))

    print("\n--- SENSITIVITY: strict trade-through entry (+1 tick pierce, queue guard) ---")
    tr_strict = run(bars, touch_buf_pt=tick)
    assert_fills(bars, tr_strict)
    for name, c in cost_grid.items():
        print(fmt(summarize(tr_strict, all_dates, inst, c, f"strict {name}")))

    print("\n--- SENSITIVITY: same-bar TARGET allowed (path-optimistic, rule 3) ---")
    tr_opt = run(bars, entry_bar_target=True)
    for name, c in cost_grid.items():
        print(fmt(summarize(tr_opt, all_dates, inst, c, f"opt {name}")))
    sbo = int(tr_opt["same_bar"].sum())
    print(f"(optimistic same-bar trades={sbo}, of which target-wins="
          f"{int(((tr_opt.same_bar) & (tr_opt.reason=='target')).sum())})")


if __name__ == "__main__":
    main()
