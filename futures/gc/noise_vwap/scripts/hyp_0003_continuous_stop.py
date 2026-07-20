"""
HYP-0003 / EXP-0004 — Continuous (every-bar) stop transfer test on GC.

Single-variable change vs the frozen baseline: the band/VWAP stop is checked on
EVERY 1-min bar (`exit_check="every_bar"`) instead of only on the 30-min Concretum
decision clock (`exit_check="decision"`). Entries, flips, VWAP gate, bands,
lookback, next-open fills: all held at the baseline. This is the NQ GO variant
(Sharpe 1.16->1.30 at same gross, Null-C z5.20) ported verbatim.

The claim being tested (NQ): same gross, higher net Sharpe via cutting losers
sooner. So we report gross AND net (rule 20) and the loser tail — a gross JUMP
would mean the every-bar stop is manufacturing fills, not reducing variance.

Usage: python -m futures.gc.noise_vwap.scripts.hyp_0003_continuous_stop GC 90
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, TICK, POINT_VALUE
from ..core.engine import run
from ..core.metrics import summarize, fmt


def loser_stats(trades: pd.DataFrame, inst: str, cost_pt: float) -> dict:
    """Left-tail / stop diagnostics: the every-bar claim is a shorter loser tail."""
    t = trades.copy()
    t["net_pts"] = t["points"] - 2.0 * cost_pt
    pv = POINT_VALUE[inst]
    losers = t[t["net_pts"] < 0]["net_pts"]
    return dict(
        n=len(t),
        stop_frac=float((t["reason"] == "stop").mean()),
        reasons=t["reason"].value_counts().to_dict(),
        worst_pt=float(t["points"].min()),
        p05_net_pt=float(t["net_pts"].quantile(0.05)),
        loser_mean_pt=float(losers.mean()) if len(losers) else float("nan"),
        loser_mean_usd=float(losers.mean() * pv) if len(losers) else float("nan"),
    )


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "GC"
    lookback = int(sys.argv[2]) if len(sys.argv) > 2 else 90

    fees_pt = 2.25 / POINT_VALUE[inst]
    tick = TICK[inst]
    cost_grid = {
        "0.25tick": fees_pt + 0.25 * tick,
        "0.50tick": fees_pt + 0.50 * tick,
        "1.0tick": fees_pt + 1.0 * tick,
    }
    primary = "0.50tick"

    print(f"=== {inst} lookback={lookback} — HYP-0003 continuous-stop transfer ===")
    bars = load_rth(inst)
    bands = noise_bands(bars, lookback)
    print(f"sessions={bars['date'].nunique()} "
          f"{bars['date'].min().date()}->{bars['date'].max().date()}")

    variants = {
        "decision (baseline)": run(bars, bands, exit_check="decision"),
        "every_bar (continuous)": run(bars, bands, exit_check="every_bar"),
    }

    # fill-feasibility assert on both (rule A1/2): no same-bar fills.
    for name, tr in variants.items():
        same = (tr["entry_tod"] == tr["exit_tod"]).sum()
        assert same == 0, f"{name}: {same} same-bar fills — fill artifact!"
    print("fill-feasibility: 0 same-bar fills in both variants OK\n")

    # ---- net at the cost grid, both variants side by side ----
    for cost_name, c in cost_grid.items():
        print(f"--- NET @ {cost_name} ---")
        for name, tr in variants.items():
            print(f"  {name:<24s} " + fmt(summarize(tr, inst, c, "")))
        print()

    # ---- gross (rule 20): the NQ claim is SAME gross, higher net Sharpe ----
    print("--- GROSS (no cost) ---")
    gr= {}
    for name, tr in variants.items():
        s = summarize(tr, inst, 0.0, "")
        gr[name] = s
        print(f"  {name:<24s} " + fmt(s))
    print()

    # ---- headline delta at the primary cost ----
    c = cost_grid[primary]
    sd = summarize(variants["decision (baseline)"], inst, c, "")
    se = summarize(variants["every_bar (continuous)"], inst, c, "")
    print(f"=== HEADLINE DELTA (every_bar - decision) @ {primary} ===")
    print(f"  net daily Sharpe : {sd['sharpe_net_daily']:+.3f} -> {se['sharpe_net_daily']:+.3f} "
          f"(delta {se['sharpe_net_daily'] - sd['sharpe_net_daily']:+.3f})")
    print(f"  net day-$ t      : {sd['day_net_t']:+.3f} -> {se['day_net_t']:+.3f} "
          f"(delta {se['day_net_t'] - sd['day_net_t']:+.3f})")
    print(f"  net pt/trade     : {sd['net_pts_per_trade']:+.4f} -> {se['net_pts_per_trade']:+.4f}")
    g_dec = gr['decision (baseline)']['gross_pts_per_trade']
    g_eb = gr['every_bar (continuous)']['gross_pts_per_trade']
    print(f"  GROSS pt/trade   : {g_dec:+.4f} -> {g_eb:+.4f}  (delta {g_eb - g_dec:+.4f})")
    print(f"  n_trades         : {sd['n_trades']} -> {se['n_trades']}")
    print()

    # ---- loser tail / reason codes: the mechanism check ----
    print("--- LOSER TAIL / REASON CODES @ 0.50tick ---")
    for name, tr in variants.items():
        ls = loser_stats(tr, inst, c)
        print(f"  {name}")
        print(f"    reasons={ls['reasons']}")
        print(f"    stop_frac={ls['stop_frac']:.3f}  worst_pt={ls['worst_pt']:+.2f}  "
              f"p05_net_pt={ls['p05_net_pt']:+.3f}  loser_mean=${ls['loser_mean_usd']:+.1f}")

    # persist both trade sets for review / null
    import os
    outdir = "futures/gc/noise_vwap/artifacts/runs/EXP-0004"
    os.makedirs(outdir, exist_ok=True)
    variants["decision (baseline)"].to_parquet(f"{outdir}/trades_decision.parquet")
    variants["every_bar (continuous)"].to_parquet(f"{outdir}/trades_everybar.parquet")
    print(f"\ntrades written to {outdir}/")


if __name__ == "__main__":
    main()
