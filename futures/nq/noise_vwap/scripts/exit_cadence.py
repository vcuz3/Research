"""
Exit-check CADENCE sweep (user request 2026-07-20): the continuous-stop finding
compared the two extremes -- stop checked only on the 30-min decision clock
("decision") vs every 1-min bar ("every_bar"). This fills in the INTERMEDIATE
cadences: check the stop every 5 min and every 15 min.

Single-variable change (only exit_check varies; entries/flips/bands/fills held at
baseline), run through the audited core.engine.run on NQ and ES. 5 and 15 both
divide 30, so the 30-min decision-clock checks are a subset of every cadence and
the sequence is a clean monotone interpolation decision(30) -> 15 -> 5 -> 1.

Usage: python -m futures.nq.noise_vwap.scripts.exit_cadence
"""
from __future__ import annotations

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
    return (f"n={len(t)} stop_frac={(t['reason']=='stop').mean():.3f} "
            f"worst_pt={t['points'].min():+.2f} loser_mean=${lm:+.1f}")


def run_inst(inst: str, lookback: int = 90):
    tick = TICK[inst]
    cost = 2.25 / POINT_VALUE[inst] + 0.25 * tick   # matches es_continuous_stop.py
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    # cadence in minutes; "decision" == 30-min clock, 1 == every_bar
    variants = {
        "decision (30-min)": run(bars, bands, exit_check="decision"),
        "15-min":            run(bars, bands, exit_check=15),
        "5-min":             run(bars, bands, exit_check=5),
        "every_bar (1-min)": run(bars, bands, exit_check="every_bar"),
    }
    print(f"\n=== {inst} lookback={lookback} @0.25tick/side "
          f"({bars['date'].nunique()} sessions "
          f"{bars['date'].min().date()}->{bars['date'].max().date()}) ===")
    base = None
    for name, tr in variants.items():
        same = (tr["entry_tod"] == tr["exit_tod"]).sum()
        assert same == 0, f"{inst} {name}: {same} same-bar fills!"
        s = summarize(tr, inst, cost, "")
        sg = summarize(tr, inst, 0.0, "")
        if base is None:
            base = s
        d = s["sharpe_net_daily"] - base["sharpe_net_daily"]
        print(f"  {name:<20s} " + fmt(s)
              + f"  [gross pt={sg['gross_pts_per_trade']:+.4f} dSh={d:+.3f}]")
        print(f"       {loser_stats(tr, inst, cost)}")


def main():
    for inst in ("NQ", "ES"):
        run_inst(inst)


if __name__ == "__main__":
    main()
