"""Numerator levers on the abs_sigma pocket: longer HORIZON, and a vol-sized BRACKET.

The regime-pocket run showed the edge fraction is stuck at ~0.03 R (~0.3 pip gross)
from the ENTRY side, so gross can only rise by changing the EXIT. Two exit changes,
both on the best pocket (abs_sigma top10, event clock, non-overlap, delay 1):

  Part 1 -- longer fixed HOLDING HORIZON (30/60/120/240 min) with the single-barrier
  3R stop. A longer hold books more pips per trade against the FIXED commission (cost
  amortisation), at the price of fewer, more-spaced trades (cooldown scales with the
  hold).

  Part 2 -- a vol-sized TP/SL BRACKET (`_bracket_engine.simulate_bracket`, adverse
  intrabar resolution, tested) instead of a fixed-horizon exit. Target k_tp*sigma,
  stop k_sl*sigma, timeout at MAX_HOLD.

Everything is scored net of the modelled cost (`_cost_model.py`), mean R beside mean
pips, per pair and median. Consumed history; 2024+ sealed.

Reproduce:
    python -u _run_horizon_bracket.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _bracket_engine import simulate_bracket
from _cost_model import CostParams, commission_pips, round_trip_pips
from _rsi_stop_engine import (
    BASE_K,
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
)
from _run_regime_pocket_economics import add_pocket_features, early_cut
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "horizon_bracket_results.json"
CSV_H = ROOT / "horizon_sweep.csv"
CSV_B = ROOT / "bracket_grid.csv"

STOP_K = 3.0
SLIPPAGE = 1.0
POCKET_KEEP = 0.10           # abs_sigma top10 (best pocket)
HORIZONS = [30, 60, 120, 240]
MAX_HOLD = 120               # bracket timeout
TP_GRID = [1.0, 1.5, 2.0, 3.0]
SL_GRID = [1.0, 1.5, 2.0, 3.0]
BASE = CostParams(scenario="base")
OPT = CostParams(scenario="optimistic")
NOCOMM = CostParams(scenario="base", include_commission=False)


def pocket(f):
    cut = early_cut(f, "rv30_pips", POCKET_KEEP)
    zl, zs = f.z.le(-BASE_K), f.z.ge(BASE_K)
    g = f.rv30_pips.ge(cut)
    long_s, short_s = zl & g, zs & g
    cond = (long_s | short_s).fillna(False).to_numpy()
    side = np.where(long_s.fillna(False), 1.0, np.where(short_s.fillna(False), -1.0, 0.0))
    return cond, side


def cost_of(pair, d, pp, sg, delay, params):
    hour = (d.time + pd.to_timedelta(1 + delay, unit="m")).dt.tz_convert("UTC").dt.hour.to_numpy()
    era = d.era.to_numpy()
    vr = sg / np.median(sg)
    return np.asarray(round_trip_pips(pair, hour, era, vr, params), float)


def summarise(pair, tag, d, sg, pnl, delay, years, extra=None):
    m = metrics(pnl, sg, d.sdate.values, years)
    if "mean_pips" not in m:
        return None
    row = {"pair": pair, "delay": delay, "signals_per_year": m["signals_per_year"],
           "gross_pips": m["mean_pips"], "gross_R": m["mean_R"],
           "risk_unit_pips": m["implied_risk_unit_pips"], "gross_t": m["cluster_t"],
           "hit_rate": m["hit_rate"], "commission_pips": commission_pips(pair)}
    for name, params in [("base", BASE), ("opt", OPT), ("nocomm", NOCOMM)]:
        c = cost_of(pair, d, None, sg, delay, params)
        nm = metrics(pnl - c, sg, d.sdate.values, years)
        row[f"cost_{name}"] = float(np.mean(c[np.isfinite(pnl)]))
        row[f"net_{name}_pips"] = nm.get("mean_pips", np.nan)
        row[f"net_{name}_R"] = nm.get("mean_R", np.nan)
        row[f"net_{name}_t"] = nm.get("cluster_t", np.nan)
    if extra:
        row.update(extra)
    return row


def analyse(pair):
    f = add_pocket_features(build_features(pair))
    arrays = ohlc_arrays(f)
    cond, side_all = pocket(f)
    hrows, brows = [], []

    # Part 1 -- horizon sweep (single-barrier stop, fixed-horizon exit)
    for H in HORIZONS:
        idx = select_events(f, cond, horizon=H)
        if len(idx) < 150:
            continue
        d, paths = extract(f, arrays, idx, horizon=H)
        side = side_all[idx]
        years = d.sdate.nunique() / 252
        for delay in (0, 1):
            pp = shift_paths(paths, delay, horizon=H)
            sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
            pnl, st, _ = simulate(pp, side, STOP_K * sg, H, SLIPPAGE)
            r = summarise(pair, f"H{H}", d, sg, pnl, delay, years,
                          extra={"horizon": H, "stopped_frac": float(np.asarray(st, bool).mean())})
            if r:
                hrows.append(r)

    # Part 2 -- vol-sized bracket (timeout at MAX_HOLD)
    idx = select_events(f, cond, horizon=MAX_HOLD)
    if len(idx) >= 150:
        d, paths = extract(f, arrays, idx, horizon=MAX_HOLD)
        side = side_all[idx]
        years = d.sdate.nunique() / 252
        for delay in (0, 1):
            pp = shift_paths(paths, delay, horizon=MAX_HOLD)
            sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
            for tp in TP_GRID:
                for sl in SL_GRID:
                    pnl, kind = simulate_bracket(pp, side, tp * sg, sl * sg, MAX_HOLD, SLIPPAGE)
                    r = summarise(pair, f"tp{tp}sl{sl}", d, sg, pnl, delay, years,
                                  extra={"tp": tp, "sl": sl,
                                         "target_frac": float((kind == 1).mean()),
                                         "stop_frac": float((kind == -1).mean()),
                                         "timeout_frac": float((kind == 0).mean())})
                    if r:
                        brows.append(r)
    return hrows, brows


def main():
    hrows, brows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        h, b = analyse(pair)
        hrows.extend(h)
        brows.extend(b)
    H = pd.DataFrame(hrows)
    B = pd.DataFrame(brows)

    print("\n=== PART 1: longer holding horizon, abs_sigma pocket, delay 1 (median across pairs) ===")
    print("   commission floor ~0.70 pip")
    h1 = H[H.delay == 1]
    print(h1.groupby("horizon").agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_pips", "median"), gross_R=("gross_R", "median"),
        risk_unit=("risk_unit_pips", "median"), stopped=("stopped_frac", "median"),
        cost_base=("cost_base", "median"),
        net_base_pips=("net_base_pips", "median"), net_base_R=("net_base_R", "median"),
        net_nocomm_pips=("net_nocomm_pips", "median"),
    ).round(3).to_string())

    print("\n   Gross pips by horizon per pair (delay 1):")
    print(h1.pivot_table(index="horizon", columns="pair", values="gross_pips").round(3).to_string())

    print("\n=== PART 2: vol-sized bracket, timeout 120 min, delay 1 (median across pairs) ===")
    b1 = B[B.delay == 1]
    tab = b1.groupby(["tp", "sl"]).agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_pips", "median"), gross_R=("gross_R", "median"),
        target_frac=("target_frac", "median"), timeout_frac=("timeout_frac", "median"),
        cost_base=("cost_base", "median"),
        net_base_pips=("net_base_pips", "median"), net_base_R=("net_base_R", "median"),
        net_nocomm_pips=("net_nocomm_pips", "median"),
    ).round(3)
    print(tab.to_string())

    print("\n=== Net-POSITIVE configs (base cost, delay 1, median across pairs) ===")
    found = False
    hpos = h1.groupby("horizon").net_base_pips.median()
    bpos = b1.groupby(["tp", "sl"]).net_base_pips.median()
    for k, v in hpos.items():
        if v > 0:
            found = True
            print(f"   horizon {k}: net {v:+.3f} pip (base)")
    for k, v in bpos.items():
        if v > 0:
            found = True
            print(f"   bracket tp{k[0]}/sl{k[1]}: net {v:+.3f} pip (base)")
    if not found:
        print("   NONE at base cost. Best (least negative):")
        print(f"   horizon: {hpos.idxmax()} at {hpos.max():+.3f} pip")
        print(f"   bracket: tp{bpos.idxmax()[0]}/sl{bpos.idxmax()[1]} at {bpos.max():+.3f} pip")
        # also the commission-free best (the honest ceiling without commission)
        hnc = h1.groupby("horizon").net_nocomm_pips.median()
        bnc = b1.groupby(["tp", "sl"]).net_nocomm_pips.median()
        print(f"   commission-free best -- horizon {hnc.idxmax()}: {hnc.max():+.3f} pip; "
              f"bracket tp{bnc.idxmax()[0]}/sl{bnc.idxmax()[1]}: {bnc.max():+.3f} pip")

    H.to_csv(CSV_H, index=False)
    B.to_csv(CSV_B, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "pocket_keep": POCKET_KEEP, "horizons": HORIZONS, "max_hold": MAX_HOLD,
            "tp_grid": TP_GRID, "sl_grid": SL_GRID,
            "commission_floor_pips": float(H.commission_pips.median()),
        },
        "horizon": json.loads(H.to_json(orient="records")),
        "bracket": json.loads(B.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
