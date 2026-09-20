"""EXP-0001 -- Asia session range expansion 1.5x, continuation, NQ 5-min.

Reproduce:  python futures\nq\asia_expansion\scripts\run_exp0001.py
Writes:     artifacts/runs/EXP-0001/
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

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0001"
OUT.mkdir(parents=True, exist_ok=True)

PRIMARY = dict(window="18-03", k=1.5, n=20, hold=3, direction="continuation")
ARTICLE_LO, ARTICLE_HI = pd.Timestamp("2021-12-01"), pd.Timestamp("2025-08-31")


def main():
    pd.set_option("display.width", 250)
    rep = {}

    # ---- 1. data quality (Rule 9a) -------------------------------------------
    dq = {}
    bars_by_window = {}
    for w in D.WINDOWS:
        b = D.build_asia_5m(w)
        bars_by_window[w] = b
        dq[w] = D.data_quality(b, w)
    (OUT / "data_quality.json").write_text(json.dumps(dq, indent=2))
    bars = bars_by_window[PRIMARY["window"]]

    # ---- 2. fire-rate selector diagnostic (LEARNINGS #1) ---------------------
    fr = S.fire_rate_by_slot(bars, k=PRIMARY["k"], n=PRIMARY["n"])
    fr.to_csv(OUT / "fire_rate_by_slot.csv")
    d = fr[fr["defined_frac"] > 0.5]["fire_rate_defined"]
    rep["fire_rate"] = {"slots": int(len(d)), "mean": float(d.mean()),
                        "cv": float(d.std() / d.mean()), "min": float(d.min()),
                        "max": float(d.max()), "max_over_min": float(d.max() / d.min()),
                        "feature_undefined_frac": float(1 - fr["defined_frac"].mean())}

    # ---- 3. primary cell -----------------------------------------------------
    sig = S.signals(bars, k=PRIMARY["k"], n=PRIMARY["n"], hold=PRIMARY["hold"],
                    direction=PRIMARY["direction"])
    sig.to_parquet(OUT / "signals_primary.parquet")
    rows = [ST.score(sig, "PRIMARY 18-03 k1.5 n20 H3 cont")]

    art = sig[(sig["trade_date"] >= ARTICLE_LO) & (sig["trade_date"] <= ARTICLE_HI)]
    rows.append(ST.score(art, "  article window 2021-12..2025-08"))
    rows.append(ST.score(sig[~sig["trade_date"].between(ARTICLE_LO, ARTICLE_HI)],
                         "  outside article window"))
    primary = pd.DataFrame(rows)

    # ---- 4. horizon curve ----------------------------------------------------
    hz = [ST.score(S.signals(bars, k=PRIMARY["k"], n=PRIMARY["n"], hold=h),
                   f"H={h:>2} bars ({5*h:>3} min)") for h in (1, 2, 3, 6, 12, 18, 24)]
    horizon = pd.DataFrame(hz)

    # ---- 5. threshold sweep --------------------------------------------------
    ks = [ST.score(S.signals(bars, k=kk, n=PRIMARY["n"], hold=PRIMARY["hold"]),
                   f"k={kk}") for kk in (1.25, 1.5, 2.0, 2.5)]
    ksweep = pd.DataFrame(ks)

    # ---- 6. lookback sweep ---------------------------------------------------
    ns = [ST.score(S.signals(bars, k=PRIMARY["k"], n=nn, hold=PRIMARY["hold"]),
                   f"N={nn}") for nn in (12, 20, 50)]
    nsweep = pd.DataFrame(ns)

    # ---- 7. window sweep -----------------------------------------------------
    ws = [ST.score(S.signals(bars_by_window[w], k=PRIMARY["k"], n=PRIMARY["n"],
                             hold=PRIMARY["hold"]), f"window {w}") for w in D.WINDOWS]
    wsweep = pd.DataFrame(ws)

    # ---- 8. year table -------------------------------------------------------
    years = ST.by_year(sig)

    # ---- 9. slot decomposition: is it just the Tokyo/Europe opens? -----------
    hh = sig["slot"].str.slice(0, 2).astype(int)
    bucket = np.where(hh.isin([20]), "20:00-20:59 Tokyo open",
             np.where(hh.isin([2]), "02:00-02:59 Europe open", "all other Asia slots"))
    slots = pd.DataFrame([ST.score(sig[bucket == b], b) for b in sorted(set(bucket))])

    # ---- 10. no-overlap arm (tradable estimand) ------------------------------
    s = sig.sort_values(["trade_date", "bar_i"]).copy()
    keep, busy_until, cur = [], -1, None
    for tdate, bi, held in zip(s["trade_date"], s["bar_i"], s["held"]):
        if tdate != cur:
            cur, busy_until = tdate, -1
        if bi >= busy_until:
            keep.append(True)
            busy_until = bi + 1 + held
        else:
            keep.append(False)
    nooverlap = pd.DataFrame([ST.score(s[np.array(keep)], "no-overlap (one position)")])

    # ---- write ---------------------------------------------------------------
    tables = {"primary": primary, "horizon": horizon, "k_sweep": ksweep,
              "n_sweep": nsweep, "window_sweep": wsweep, "slot_buckets": slots,
              "no_overlap": nooverlap}
    for name, t in tables.items():
        t.to_csv(OUT / f"{name}.csv", index=False)
    years.to_csv(OUT / "by_year.csv")

    cols = ["label", "n", "sig_per_session", "hit_rate", "gross_pts", "gross_t",
            "net_nq_spread1", "net_mnq_spread1", "net_mnq_spread2", "net_article",
            "t_mnq_spread2"]
    with pd.option_context("display.float_format", lambda v: f"{v:9.4f}"):
        for name, t in tables.items():
            print(f"\n===== {name} =====")
            print(t[[c for c in cols if c in t.columns]].to_string(index=False))
        print("\n===== by year (gross) =====")
        print(years.to_string())
    print("\n===== fire-rate selector diagnostic =====")
    print(json.dumps(rep["fire_rate"], indent=2))
    print("\n===== data quality (primary window) =====")
    print(json.dumps(dq[PRIMARY["window"]], indent=2))

    (OUT / "summary.json").write_text(json.dumps(rep, indent=2))
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
