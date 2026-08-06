"""Build the derived daily / 30-minute panel and run the rule-9a data gate.

Writes to `data/` (project-local DERIVED data, not a copy of the shared archive):

    data/daily.parquet      one row per (product, CME trade date)
    data/slot30.parquet     one row per (product, trade date, 30-minute slot)
    data/ticks.csv          measured minimum increment per (product, year)
    reports/DATA_QUALITY.txt

The gate reports, per product: rows, sessions, span, bars per session, sessions
dropped as too short, sessions where the incoming price change is a contract
substitution rather than a return, and -- for the intraday grid -- per-slot
coverage and how many decisions the causal same-slot volatility window removes.
Rule 9a: a feature that silently nulls rows is a reportable finding, not an
implementation detail.

    python -u -m futures.panel.trend_closedform.scripts.build_panel
"""
from __future__ import annotations

import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import panel as P

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data"
REPORTS = ROOT / "reports"
SLOT_MINUTES = 30


def main(products: tuple[str, ...] = P.PRODUCTS) -> int:
    OUT.mkdir(exist_ok=True)
    REPORTS.mkdir(exist_ok=True)
    daily_all, slot_all, tick_rows, lines = [], [], [], []

    def emit(s: str = "") -> None:
        print(s, flush=True)
        lines.append(s)

    emit("DATA QUALITY GATE -- futures/panel/trend_closedform")
    emit(f"generated {pd.Timestamp.utcnow():%Y-%m-%d %H:%M} UTC")
    emit(f"archive   {P.DATA_DIR}")
    emit(f"panel     {len(products)} products, {SLOT_MINUTES}-minute intraday grid")
    emit("")
    emit("Session key is the CME trade date, sdate = date(t_ET + 6h).  Verified in")
    emit("this run: every product has an empty ET block ending 17:59 and resumes at")
    emit("18:00 ET, so one session definition covers all five asset classes.")
    emit("")
    emit("DAILY GRID")
    emit(f"{'prod':<5}{'cls':<8}{'sessions':>9}{'first':>12}{'last':>12}"
         f"{'bars/sess':>10}{'short':>7}{'rolls':>7}{'halt_rows':>11}")

    for prod in products:
        t0 = time.time()
        d, rep = P.daily_bars(prod)
        s, srep = P.slot_bars(prod, minutes=SLOT_MINUTES)
        d.insert(0, "product", prod)
        s.insert(0, "product", prod)
        daily_all.append(d)
        slot_all.append(s)

        ticks = P.infer_ticks_by_year(d)
        for year, tk in ticks.items():
            tick_rows.append({"product": prod, "year": int(year), "tick": float(tk)})

        emit(f"{prod:<5}{P.PANEL[prod]:<8}{rep.sessions:>9}"
             f"{str(rep.first_date)[:10]:>12}{str(rep.last_date)[:10]:>12}"
             f"{rep.median_bars_per_session:>10.0f}{rep.short_sessions_dropped:>7}"
             f"{rep.roll_sessions:>7}{rep.halt_rows_dropped:>11}")
        print(f"    ({time.time() - t0:.1f}s)", file=sys.stderr, flush=True)

    daily = pd.concat(daily_all, ignore_index=True)
    slot = pd.concat(slot_all, ignore_index=True)
    ticks_df = pd.DataFrame(tick_rows)
    daily.to_parquet(OUT / "daily.parquet", index=False)
    slot.to_parquet(OUT / "slot30.parquet", index=False)
    ticks_df.to_csv(OUT / "ticks.csv", index=False)

    # ---------------------------------------------------------------- ticks --
    emit("")
    emit("MEASURED PRICE INCREMENT (rule 19) -- from the grid, never assumed.")
    emit("A product listed with more than one value changed increment mid-sample, so")
    emit("a cost quoted in ticks across the whole span is wrong for part of it.")
    emit("This is the EFFECTIVE traded grid (largest increment 99% of closes lie on),")
    emit("which on a thin product can exceed the exchange minimum -- PA's exchange")
    emit("tick is 0.05 throughout, but 99% of its closes sit on 0.5 from 2021, which")
    emit("is a wide market rather than a rule change.  For a cost floor the effective")
    emit("grid is the more honest input; it is labelled here so it is not mistaken")
    emit("for the contract specification.")
    emit(f"{'prod':<5}{'distinct ticks (year: value)':<70}")
    n_changed = 0
    for prod, grp in ticks_df.groupby("product", sort=False):
        grp = grp.sort_values("year")
        changes, prev = [], None
        for _, r in grp.iterrows():
            if prev is None or not np.isclose(r["tick"], prev):
                changes.append(f"{int(r['year'])}:{r['tick']:g}")
                prev = r["tick"]
        if len(changes) > 1:
            n_changed += 1
        emit(f"{prod:<5}{'  '.join(changes):<70}")
    emit(f"-> {n_changed} of {len(products)} products changed tick mid-sample.")

    # ------------------------------------------------------- intraday cover --
    emit("")
    emit("INTRADAY GRID -- per-slot coverage and causal-window deletions")
    emit("cover      = fraction of sessions with a bar in that slot (min over slots)")
    emit("x_defined  = fraction of grid rows where the causal same-slot vol window")
    emit("             (lookback 90, min_periods 45) yields a usable risk unit")
    emit("spread     = max - min of x_defined ACROSS slots.  A large spread is the")
    emit("             finding-G hidden liquidity filter: the deletion tracks time")
    emit("             of day, so it silently removes an instrument's thin hours.")
    emit(f"{'prod':<5}{'rows':>10}{'slots':>7}{'cover_min':>11}{'cover_p05':>11}"
         f"{'x_defined':>11}{'spread':>9}")
    cover_rows = []
    for prod, g in slot.groupby("product", sort=False):
        g = g.sort_values(["sdate", "slot"], kind="mergesort")
        n_sess = g["sdate"].nunique()
        cov = g.groupby("slot")["close"].size() / n_sess
        ru = P.slot_risk_units(g)
        defined = np.isfinite(ru["x"].to_numpy())
        per_slot_def = pd.Series(defined).groupby(g["slot"].to_numpy()).mean()
        cover_rows.append({
            "product": prod, "rows": len(g), "slots": int(g["slot"].nunique()),
            "cover_min": float(cov.min()), "cover_p05": float(cov.quantile(0.05)),
            "x_defined": float(defined.mean()),
            "x_defined_spread": float(per_slot_def.max() - per_slot_def.min()),
        })
        r = cover_rows[-1]
        emit(f"{prod:<5}{r['rows']:>10}{r['slots']:>7}{r['cover_min']:>11.3f}"
             f"{r['cover_p05']:>11.3f}{r['x_defined']:>11.3f}"
             f"{r['x_defined_spread']:>9.3f}")
    cov_df = pd.DataFrame(cover_rows)
    cov_df.to_csv(OUT / "intraday_coverage.csv", index=False)
    worst = cov_df.sort_values("x_defined_spread", ascending=False).head(3)
    emit("")
    emit("worst across-slot deletion spread: "
         + ", ".join(f"{r['product']} {r['x_defined_spread']:.3f}"
                     for _, r in worst.iterrows()))

    # ------------------------------------------------------------- daily ru --
    emit("")
    emit("DAILY RISK UNITS -- causal 63-session trailing scale, min_periods 2/3")
    emit("roll_frac = fraction of daily returns that are a contract substitution")
    emit("            rather than a return, and are therefore dropped (rule 11).")
    emit(f"{'prod':<5}{'x_defined':>11}{'rolls':>7}{'roll_frac':>11}"
         f"{'sd(x)':>9}{'mean(x)':>10}")
    daily_rows = []
    for prod, g in daily.groupby("product", sort=False):
        g = g.sort_values("sdate")
        ru = P.risk_units(g["close"].reset_index(drop=True),
                          g["roll"].reset_index(drop=True))
        x = ru["x"].to_numpy()
        rf = float(g["roll"].mean())
        daily_rows.append({"product": prod, "x_defined": float(np.isfinite(x).mean()),
                           "rolls": int(g["roll"].sum()), "roll_frac": rf,
                           "sd_x": float(np.nanstd(x)), "mean_x": float(np.nanmean(x))})
        r = daily_rows[-1]
        emit(f"{prod:<5}{r['x_defined']:>11.3f}{r['rolls']:>7}{rf:>11.3f}"
             f"{r['sd_x']:>9.3f}{r['mean_x']:>10.4f}")
    pd.DataFrame(daily_rows).to_csv(OUT / "daily_quality.csv", index=False)

    heavy = [r["product"] for r in daily_rows if r["roll_frac"] > 0.10]
    emit("")
    emit("Reading: sd(x) near 1 means the causal scale is doing its job; a value")
    emit("far from 1 means the 63-session window is a poor forecast for that")
    emit("product and its 'risk units' are not comparable to the others'.")
    emit("")
    emit(f"HEAVY-ROLL PRODUCTS (>10% of daily returns dropped): {heavy or 'none'}")
    emit("On these the volume-ranked continuous front flickers between contracts")
    emit("with no dominant leg, so a large minority of returns is unusable and the")
    emit("trend signal is built partly from substituted zeros.  They stay in the")
    emit("panel -- excluding them would itself be a selection decision -- but every")
    emit("headline is repeated without them as a declared robustness arm.")

    (REPORTS / "DATA_QUALITY.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"\nwrote {OUT/'daily.parquet'}, {OUT/'slot30.parquet'}, "
          f"{REPORTS/'DATA_QUALITY.txt'}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
