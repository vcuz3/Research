"""EXP-0002 -- Is the article's T = -10.96 a signal statistic or a cost statistic?

A t-stat computed on NET P&L after a fixed per-trade charge has two parts: the
directional content of the signal, and the charge itself multiplied by sqrt(N)/sd.
This run separates them, and calibrates the second part with a control that has
provably ZERO directional information: the same firing bars, the same fills, the same
charge, but a COIN-FLIP direction.

If a coin flip also prints t ~ -11, then -10.96 says nothing about the signal.

Reproduce:  python futures\nq\asia_expansion\scripts\run_exp0002.py
Writes:     artifacts/runs/EXP-0002/
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[4]
sys.path.insert(0, str(ROOT))

from futures.nq.asia_expansion.strategy import data as D, signal as S
from futures.nq.asia_expansion.backtest_engine import stats as ST

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0002"
OUT.mkdir(parents=True, exist_ok=True)

ARTICLE_LO, ARTICLE_HI = pd.Timestamp("2021-12-01"), pd.Timestamp("2025-08-31")
CHARGE = 2.0
SEEDS = 400


def arm(sig, label, charge=CHARGE):
    g = sig["gross_pts"]
    mg, tg = ST.cluster_t(g, sig["trade_date"])
    mn, tn = ST.cluster_t(g - charge, sig["trade_date"])
    return {"arm": label, "n": len(sig), "gross_pts": mg, "gross_t": tg,
            "net_pts": mn, "net_t": tn}


def main():
    pd.set_option("display.width", 220)
    bars = D.build_asia_5m("18-03")
    full = S.signals(bars, k=1.5, n=20, hold=3, direction="continuation")
    art = full[full["trade_date"].between(ARTICLE_LO, ARTICLE_HI)].reset_index(drop=True)

    results = {}
    for name, sig in (("article_window", art), ("full_archive", full)):
        # the raw move on the firing bars, independent of any direction choice
        raw = (sig["exit"] - sig["entry"]).to_numpy()
        d = sig["dir"].to_numpy()

        rows = [arm(sig, "continuation (the article's rule)"),
                arm(sig.assign(gross_pts=-sig["gross_pts"]), "fade (mirror)")]

        # coin-flip control: zero directional information by construction
        rng = np.random.default_rng(20260826)
        tg_null, tn_null, mg_null = [], [], []
        for _ in range(SEEDS):
            s = rng.choice([-1.0, 1.0], size=len(sig))
            g = pd.Series(s * raw)
            m0, t0 = ST.cluster_t(g, sig["trade_date"])
            m1, t1 = ST.cluster_t(g - CHARGE, sig["trade_date"])
            mg_null.append(m0); tg_null.append(t0); tn_null.append(t1)
        tn_null = np.array(tn_null); tg_null = np.array(tg_null)

        # the fully degenerate case: a strategy with EXACTLY zero gross edge
        zero_t = ST.cluster_t(pd.Series(np.zeros(len(sig)) - CHARGE), sig["trade_date"])[1]

        res = {
            "n_signals": int(len(sig)),
            "sessions": int(sig["trade_date"].nunique()),
            "arms": rows,
            "coinflip_gross_t": {"mean": float(tg_null.mean()), "p05": float(np.percentile(tg_null, 5)),
                                 "p95": float(np.percentile(tg_null, 95))},
            "coinflip_net_t_at_2pt": {"mean": float(tn_null.mean()),
                                      "p05": float(np.percentile(tn_null, 5)),
                                      "p95": float(np.percentile(tn_null, 95)),
                                      "min": float(tn_null.min()), "max": float(tn_null.max())},
            "zero_edge_net_t_at_2pt": float(zero_t),
            "article_reported_T": -10.96,
            "article_T_inside_coinflip_95ci": bool(
                np.percentile(tn_null, 2.5) <= -10.96 <= np.percentile(tn_null, 97.5)),
            "breakeven_gross_needed_pts": {k: v for k, v in ST.COST_LADDER.items() if k != "gross"},
        }
        results[name] = res
        print(f"\n########## {name}  (n={len(sig)}, sessions={sig['trade_date'].nunique()}) ##########")
        print(pd.DataFrame(rows).to_string(index=False,
              float_format=lambda v: f"{v:9.4f}"))
        print(f"  coin-flip direction, gross t          : mean {tg_null.mean():+.2f}  "
              f"[{np.percentile(tg_null,5):+.2f}, {np.percentile(tg_null,95):+.2f}]")
        print(f"  coin-flip direction, net t at 2.0 pt  : mean {tn_null.mean():+.2f}  "
              f"[{np.percentile(tn_null,5):+.2f}, {np.percentile(tn_null,95):+.2f}]")
        print(f"  exactly-zero-edge strategy, net t     : {zero_t:+.2f}")
        print(f"  article's reported T                  : -10.96")

    (OUT / "cost_decomposition.json").write_text(json.dumps(results, indent=2))
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
