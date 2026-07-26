"""EXP-0032 Phase 1: intraday-ATR stop buffer vs the close-confirmation wick filter.

Three parts, one 1s scan for the sweep (+ one for the matched-width control):
  0. CALIBRATION  - from the close-confirmed holds, how deep (in ATR_N units) are
     the wicks close-confirmation tolerates vs the real breakdowns? Predicts k*.
  1. SWEEP        - first-touch on 1s against stop = band - k*ATR_N; N x k grid.
  2. MATCHED WIDTH- a fixed-point buffer of the best cell's median width, to test
     whether the volatility SCALING (not just extra width) is load-bearing.

Anchors: k=0 = EXP-0031 first-touch (0.883); the close-confirmed continuous stop
(0.923) is the incumbent to beat. No Null C here (gated on Phase 1 clearing).
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.atr_buffer import ONE_SECOND_PATH, run_streaming_atr, intraday_atr
from .forensic import sizing


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0032"
FEES_PT = 2.25 / POINT_VALUE["NQ"]
SLIP = 0.5
NS = [5, 10, 14, 20, 30]
KS = [0.0, 0.25, 0.5, 0.75, 1.0, 1.5, 2.0]
CAL_NS = [5, 14, 30]


def daily(trades, eligible_dates, bars_e):
    cost_side = FEES_PT + SLIP * TICK["NQ"]
    dates = pd.Index(pd.to_datetime(eligible_dates), name="date")
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    gross = t.groupby("date")["points"].sum().reindex(dates, fill_value=0.0)
    counts = t.groupby("date").size().reindex(dates, fill_value=0)
    usd = (gross - counts * 2.0 * cost_side) * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    m = sizing("NQ", bars_e, t, cost_side)
    return {
        "n_trades": len(t), "stop_exits": int((t["reason"] == "touch").sum()),
        "gross_pt": float(t["points"].mean()),
        "net_pt": float((t["points"] - 2 * cost_side).mean()),
        "worst_pt": float(t["points"].min()),
        "daily_usd": float(usd.mean()),
        "daily_sharpe": float(usd.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "daily_t": float(usd.mean() / (sd / np.sqrt(len(usd)))) if sd > 0 else 0.0,
        "voltgt_sharpe": m["sharpe"], "voltgt_maxdd": m["maxdd"],
    }


def calibrate(bars_e, bands, one_min_trades):
    """Wick depth (band-to-low, in ATR_N units) during close-confirmed holds."""
    bx = intraday_atr(bars_e, CAL_NS)
    bd = bands[["date", "tod", "upper", "lower"]]
    x = bx.merge(bd, on=["date", "tod"], how="left")
    x["stop_long"] = np.maximum(x["upper"], x["vwap"])
    x["stop_short"] = np.minimum(x["lower"], x["vwap"])
    key = {(d, int(t)): i for i, (d, t) in enumerate(zip(x["date"], x["tod"]))}
    low = x["low"].to_numpy(); high = x["high"].to_numpy(); close = x["close"].to_numpy()
    sl = x["stop_long"].to_numpy(); ss = x["stop_short"].to_numpy()
    atr = {N: x[f"atr_{N}"].to_numpy() for N in CAL_NS}
    tod_by_date = {d: np.sort(g["tod"].astype(int).to_numpy())
                   for d, g in x.groupby("date", sort=False)}

    tol = {N: [] for N in CAL_NS}   # tolerated-wick depths (survived the hold)
    brk = {N: [] for N in CAL_NS}   # real-break depths (the stop-trigger bar)
    tt = one_min_trades
    for r in tt.itertuples(index=False):
        d = pd.Timestamp(r.date).to_datetime64() if not isinstance(r.date, np.datetime64) else r.date
        # normalize date key to match x['date'] dtype
        dk = r.date
        tods = tod_by_date.get(dk)
        if tods is None:
            continue
        held = tods[(tods >= int(r.entry_tod)) & (tods < int(r.exit_tod))]
        for tdd in held:
            i = key.get((dk, int(tdd)))
            if i is None:
                continue
            for N in CAL_NS:
                a = atr[N][i]
                if not np.isfinite(a) or a <= 0:
                    continue
                if r.side == 1:
                    depth = sl[i] - low[i]
                else:
                    depth = high[i] - ss[i]
                if depth > 0:
                    tol[N].append(depth / a)
        if r.reason == "stop":
            trig = tods[tods < int(r.exit_tod)]
            if trig.size:
                i = key.get((dk, int(trig[-1])))
                if i is not None:
                    for N in CAL_NS:
                        a = atr[N][i]
                        if np.isfinite(a) and a > 0:
                            depth = (sl[i] - close[i]) if r.side == 1 else (close[i] - ss[i])
                            if depth > 0:
                                brk[N].append(depth / a)
    rep = {}
    for N in CAL_NS:
        tv = np.array(tol[N]); bv = np.array(brk[N])
        rep[f"N{N}"] = {
            "tolerated_wick_atr_p50": float(np.median(tv)) if tv.size else None,
            "tolerated_wick_atr_p90": float(np.percentile(tv, 90)) if tv.size else None,
            "tolerated_wick_atr_p95": float(np.percentile(tv, 95)) if tv.size else None,
            "real_break_atr_p50": float(np.median(bv)) if bv.size else None,
            "n_tolerated": int(tv.size), "n_breaks": int(bv.size),
            "atr_pts_median": float(np.nanmedian(atr[N])),
        }
    return rep


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()

    one_min = run_1m(bars_e, bands, exit_check="every_bar")   # close-confirmed anchor
    cal = calibrate(bars_e, bands, one_min)
    print("CALIBRATION (wick depth in ATR_N units, from close-confirmed holds)")
    print(json.dumps(cal, indent=2))

    specs = [(f"N{N}_k{k}", N, k) for N in NS for k in KS if k > 0]
    specs.append(("k0_first_touch", NS[0], 0.0))   # k=0 anchor (N irrelevant)
    print(f"\nScanning 1s once for {len(specs)} buffered variants ...")
    trades, audit = run_streaming_atr(ONE_SECOND_PATH, bars_e, bands, specs)
    common = np.asarray(audit.pop("covered_dates"), dtype="datetime64[ns]")

    rows = {"close_confirmed": daily(one_min, common, bars_e)}
    for nm, _, _ in specs:
        rows[nm] = daily(trades[nm], common, bars_e)
    tab = pd.DataFrame(rows).T
    tab.to_csv(OUT / "sweep.csv")

    # Best ATR cell by daily Sharpe (exclude the k=0 anchor and close-confirmed).
    grid = tab.loc[[nm for nm, _, _ in specs if not nm.startswith("k0")]]
    best_name = grid["daily_sharpe"].idxmax()
    bN = int(best_name.split("_")[0][1:]); bk = float(best_name.split("k")[1])

    # Matched-width fixed-point buffer: c points = bk * median intraday ATR_bN.
    bx = intraday_atr(bars_e, [bN])
    c = float(bk * np.nanmedian(bx[f"atr_{bN}"].to_numpy()))
    print(f"\nBest ATR cell: {best_name} (N={bN}, k={bk}); matched fixed buffer c={c:.3f} pts")
    fx_trades, _ = run_streaming_atr(ONE_SECOND_PATH, bars_e, bands,
                                     [("fixed_matched", "const1", c)])
    rows_fx = {"fixed_matched_c": daily(fx_trades["fixed_matched"], common, bars_e)}
    fx = pd.DataFrame(rows_fx).T
    full = pd.concat([tab, fx])
    full.to_csv(OUT / "sweep.csv")

    report = {
        "calibration": cal,
        "best_cell": {"name": best_name, "N": bN, "k": bk,
                      "daily_sharpe": float(grid.loc[best_name, "daily_sharpe"])},
        "anchors": {
            "close_confirmed_sharpe": float(tab.loc["close_confirmed", "daily_sharpe"]),
            "k0_first_touch_sharpe": float(tab.loc["k0_first_touch", "daily_sharpe"]),
        },
        "matched_width": {
            "fixed_c_pts": c,
            "fixed_sharpe": float(fx.loc["fixed_matched_c", "daily_sharpe"]),
            "atr_scaled_sharpe": float(grid.loc[best_name, "daily_sharpe"]),
            "scaling_uplift_vs_fixed": float(grid.loc[best_name, "daily_sharpe"]
                                             - fx.loc["fixed_matched_c", "daily_sharpe"]),
        },
        "covered_sessions": int(len(common)),
    }
    (OUT / "report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")

    pd.set_option("display.width", 220, "display.max_columns", 20)
    print("\nSWEEP (0.5 tick/side, common sample)")
    cols = ["n_trades", "stop_exits", "gross_pt", "net_pt", "worst_pt",
            "daily_usd", "daily_sharpe", "voltgt_sharpe", "voltgt_maxdd"]
    print(full[cols].round(4).to_string())
    print("\nHEADLINE")
    print(json.dumps(report["best_cell"] | report["anchors"] | report["matched_width"], indent=2))


if __name__ == "__main__":
    main()
