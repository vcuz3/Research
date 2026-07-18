"""Dump every study config's honest (next-open) trades + outcomes to one parquet.

Columns: config, session, clock_min, entry_mode, buf_atr, exit_check, date, side
(+1 long / -1 short), entry_mfo, exit_mfo, entry_px, exit_px, points (gross),
net_pts (after 2x0.25-tick cost), reason (stop/flip/eod), win (net_pts>0), inst.
"""
from __future__ import annotations
import pandas as pd
from ..core.data import POINT_VALUE
from .studies import run_cfg, COST_025, INST

# (label, session, clock, entry_mode, buf, exit_check)
CONFIGS = [
    ("baseline_RTH_clk30",   "RTH", 30, "clock",     0.0,  "decision"),
    ("clk05",                "RTH",  5, "clock",     0.0,  "decision"),
    ("clk15",                "RTH", 15, "clock",     0.0,  "decision"),
    ("clk60",                "RTH", 60, "clock",     0.0,  "decision"),
    ("ETH_clk30",            "ETH", 30, "clock",     0.0,  "decision"),
    ("continuous_stop",      "RTH", 30, "clock",     0.0,  "every_bar"),  # recommended
    ("thr_atr_0.10",         "RTH", 30, "threshold", 0.10, "every_bar"),
    ("thr_atr_0.15",         "RTH", 30, "threshold", 0.15, "every_bar"),
    ("thr_atr_0.25",         "RTH", 30, "threshold", 0.25, "every_bar"),
    ("thr_atr_0.50",         "RTH", 30, "threshold", 0.50, "every_bar"),
]

def main():
    rt_cost = 2.0 * COST_025
    parts = []
    for label, sess, clk, em, buf, xc in CONFIGS:
        t = run_cfg(sess, clk, entry_mode=em, entry_buf_atr=buf, exit_check=xc,
                    fill_mode="next_open")
        t = t.copy()
        t.insert(0, "config", label)
        t["session"] = sess; t["clock_min"] = clk; t["entry_mode"] = em
        t["buf_atr"] = buf; t["exit_check"] = xc; t["inst"] = INST
        t["net_pts"] = t["points"] - rt_cost
        t["net_usd"] = t["net_pts"] * POINT_VALUE[INST]
        t["win"] = t["net_pts"] > 0
        parts.append(t)
        print(f"{label:<22s} n={len(t):>5d} net/trade={t['net_pts'].mean():+.3f}pt "
              f"hit={t['win'].mean():.3f}")
    out = pd.concat(parts, ignore_index=True)
    cols = ["config", "session", "clock_min", "entry_mode", "buf_atr", "exit_check",
            "inst", "date", "side", "entry_mfo", "exit_mfo", "entry_px", "exit_px",
            "points", "net_pts", "net_usd", "reason", "win"]
    out = out[cols]
    path = "futures/nq/noise_vwap/outputs/study_trades_NQ.parquet"
    out.to_parquet(path)
    print(f"\nwrote {len(out)} trades across {out['config'].nunique()} configs -> {path}")
    # also a CSV for eyeballing
    out.to_csv(path.replace(".parquet", ".csv"), index=False)

if __name__ == "__main__":
    main()
