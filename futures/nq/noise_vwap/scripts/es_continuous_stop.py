"""
ES continuous-stop check (companion to the NQ studies.py continuous-stop result).

studies.py hardcodes INST="NQ", so the every-bar stop was only ever measured on NQ.
This runs the SAME single-variable comparison (exit_check "decision" -> "every_bar",
entries/flips/bands/fills held at baseline) on ES, with NQ printed for reference.

Usage: python -m futures.nq.noise_vwap.scripts.es_continuous_stop
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run
from ..core.metrics import summarize, fmt


def loser_stats(trades: pd.DataFrame, inst: str, cost_pt: float) -> str:
    t = trades.copy()
    t["net_pts"] = t["points"] - 2.0 * cost_pt
    pv = POINT_VALUE[inst]
    losers = t[t["net_pts"] < 0]["net_pts"]
    lm = losers.mean() * pv if len(losers) else float("nan")
    return (f"reasons={t['reason'].value_counts().to_dict()} "
            f"stop_frac={(t['reason']=='stop').mean():.3f} "
            f"worst_pt={t['points'].min():+.2f} loser_mean=${lm:+.1f}")


def run_inst(inst: str, lookback: int = 90):
    fees_pt = 2.25 / POINT_VALUE[inst]
    tick = TICK[inst]
    # paper-like primary cost = 0.25 tick/side (matches studies.py COST_025)
    cost = fees_pt + 0.25 * tick
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    variants = {
        "decision (baseline)": run(bars, bands, exit_check="decision"),
        "every_bar (continuous)": run(bars, bands, exit_check="every_bar"),
    }
    print(f"\n=== {inst} lookback={lookback} @0.25tick/side "
          f"({bars['date'].nunique()} sessions "
          f"{bars['date'].min().date()}->{bars['date'].max().date()}) ===")
    S = {}
    for name, tr in variants.items():
        same = (tr["entry_tod"] == tr["exit_tod"]).sum()
        assert same == 0, f"{inst} {name}: {same} same-bar fills!"
        s = summarize(tr, inst, cost, "")
        sg = summarize(tr, inst, 0.0, "")
        S[name] = (s, sg)
        print(f"  {name:<24s} " + fmt(s) + f"  [gross pt={sg['gross_pts_per_trade']:+.4f}]")
    (sd, gd), (se, ge) = S["decision (baseline)"], S["every_bar (continuous)"]
    print(f"  DELTA every_bar-decision: net Sharpe {sd['sharpe_net_daily']:+.3f}"
          f"->{se['sharpe_net_daily']:+.3f} ({se['sharpe_net_daily']-sd['sharpe_net_daily']:+.3f}) "
          f"| net t {sd['day_net_t']:+.2f}->{se['day_net_t']:+.2f} "
          f"| gross pt {gd['gross_pts_per_trade']:+.4f}->{ge['gross_pts_per_trade']:+.4f}")
    for name, tr in variants.items():
        print(f"    {name}: " + loser_stats(tr, inst, cost))


def main():
    for inst in ("ES", "NQ"):
        run_inst(inst)


if __name__ == "__main__":
    main()
