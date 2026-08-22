"""Run the ATR counter-bar breakout backtest on NQ and ES and write artifacts.

    python -m futures.nq.atr_breakout_explore.run
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

from .core import engine, metrics

OUT = Path(__file__).resolve().parent / "artifacts"
OUT.mkdir(exist_ok=True)


def main(fill_mode: str = "next_open", cap_ticks: float = 2.0):
    all_summaries = {}
    for inst in ("NQ", "ES"):
        trades, daily = engine.backtest(inst, fill_mode=fill_mode, cap_ticks=cap_ticks)
        rep = metrics.split_report(trades, daily)
        trades.to_parquet(OUT / f"trades_{inst}_{fill_mode}_cap{cap_ticks:g}.parquet")
        daily.to_frame().to_parquet(OUT / f"daily_{inst}_{fill_mode}_cap{cap_ticks:g}.parquet")
        rep.to_csv(OUT / f"report_{inst}_{fill_mode}_cap{cap_ticks:g}.csv")
        all_summaries[inst] = rep
        print(f"\n===== {inst}  fill={fill_mode}  cap={cap_ticks} ticks/side =====")
        cols = ["sessions", "n_trades", "trades_per_day", "hit_rate",
                "mean_net_bps", "sharpe_zero_day", "sharpe_trade_day",
                "sharpe_vol_target", "maxdd_zero_day", "maxdd_vol_target"]
        with pd.option_context("display.width", 200,
                               "display.float_format", lambda v: f"{v:.4f}"):
            print(rep[cols].T)
    return all_summaries


if __name__ == "__main__":
    import sys
    fm = sys.argv[1] if len(sys.argv) > 1 else "next_open"
    cap = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0
    main(fm, cap)
