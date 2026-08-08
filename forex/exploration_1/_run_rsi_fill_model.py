"""Seconds-scale FILL MODEL test. Frozen spec: RSI_FILL_MODEL_SPEC.md.

Measures the sub-second adverse selection between a bar-open-mid fill (the engine's
delay-0 entry) and a real ~1.5 s-latency market order, using the 1-second mid tape.
Base (zonly) first, then the vol-gate cell. Spread is NOT charged here (mid-only data;
it belongs to the cost model). Reproduce: python -u _run_rsi_fill_model.py
"""
from __future__ import annotations

import glob
import json
from pathlib import Path

import numpy as np
import pandas as pd

LSE_FX = Path(__file__).resolve().parent.parent / "data" / "lse" / "fx"

from _rsi_stop_engine import (
    build_features, ohlc_arrays, select_events, extract, expansion_cutpoint,
    metrics as engine_metrics, years_of, BASE_K, PIP,
)

LAT = [0.0, 1.5, 5.0, 15.0, 30.0, 60.0]     # entry latency grid, seconds
STOP_K = 2.0                                 # compulsory stop, in R, for the gate cell
SLIP = 1.0                                   # adverse slippage pips on a stop fill
MAXGAP_S = 120                               # a fill more than this stale => uncovered
PAIRS = ["EURUSD", "GBPUSD", "AUDUSD", "NZDUSD"]
FILEMAP = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD",
           "AUDUSD": "AUD_USD", "NZDUSD": "NZD_USD"}


def load_1s(pair):
    """Concatenated, time-sorted 1-second (ns-int, float32 close) mid tape."""
    files = sorted(glob.glob(str(LSE_FX / f"fx_{FILEMAP[pair]}_1s*.parquet")))
    ts_parts, px_parts = [], []
    for f in files:
        df = pd.read_parquet(f, columns=["ts", "close"])
        ts_parts.append(df.ts.to_numpy().astype("datetime64[ns]").view("int64"))
        px_parts.append(df.close.to_numpy().astype("float32"))
    ts = np.concatenate(ts_parts)
    px = np.concatenate(px_parts)
    if not np.all(np.diff(ts) >= 0):
        order = np.argsort(ts, kind="mergesort")
        ts, px = ts[order], px[order]
    return ts, px


def fill_at(ts, px, target_ns):
    """Last 1s close at-or-before each target; NaN if none within MAXGAP_S."""
    j = np.searchsorted(ts, target_ns, side="right") - 1
    ok = (j >= 0) & ((target_ns - ts[np.clip(j, 0, len(ts) - 1)]) <= MAXGAP_S * 1_000_000_000)
    out = np.where(ok, px[np.clip(j, 0, len(ts) - 1)].astype("float64"), np.nan)
    return out


def cells(f):
    long_s, short_s = f.z.le(-BASE_K), f.z.ge(BASE_K)
    side_all = np.where(long_s, 1.0, np.where(short_s, -1.0, 0.0))
    base = (long_s | short_s).fillna(False).to_numpy()
    cut = expansion_cutpoint(f, 0.40)
    gate = (base
            & f.vei_atr_z.ge(cut).fillna(False).to_numpy()
            & f.vol_pct.ge(0.60).fillna(False).to_numpy())
    return {"base": base, "vol_gate": gate}, side_all, cut


def stop_pnl(entry, side, paths, sigma_pips, stop_k, exit_col=30):
    """2.0R single-barrier stop with a custom entry (the 1s fill), minute path."""
    o, hi, lo = paths["open"], paths["high"], paths["low"]
    n, width = o.shape
    s = np.asarray(side, float)
    dist_px = stop_k * sigma_pips.to_numpy() * PIP          # 2R in price
    level = entry - s * dist_px
    worst = np.where(s[:, None] > 0, lo, hi)
    live = np.arange(width)[None, :] < exit_col
    breach = live & (s[:, None] * worst <= s[:, None] * level[:, None])
    stopped = breach.any(axis=1)
    bar = np.where(stopped, breach.argmax(axis=1), -1)
    rows = np.arange(n)
    open_at = o[rows, np.clip(bar, 0, width - 1)]
    gapped = s * open_at <= s * level
    fill = np.where(gapped, open_at, level) - s * SLIP * PIP
    exit_px = o[rows, exit_col]
    px = np.where(stopped, fill, exit_px)
    return s * (px - entry) / PIP


def summarize(pips, sigma_pips, valid):
    p = np.asarray(pips, float)[valid]
    sig = sigma_pips.to_numpy()[valid]
    r = p / sig
    return dict(n=int(valid.sum()), mean_pips=float(np.mean(p)),
                mean_R=float(np.mean(r)), hit=float((p > 0).mean()))


def run_pair(pair):
    f = build_features(pair)
    arrays = ohlc_arrays(f)
    times_ns = f.time.to_numpy().astype("datetime64[ns]").view("int64")
    masks, side_all, cut = cells(f)
    ts, px = load_1s(pair)
    yrs = years_of(f)
    out = {"pair": pair, "expansion_cut": cut, "years": yrs, "cells": {}}

    for name, cond in masks.items():
        idx = select_events(f, cond)
        if len(idx) < 200:
            out["cells"][name] = {"signals": int(len(idx)), "note": "too few"}
            continue
        d, paths = extract(f, arrays, idx)
        side = side_all[idx]
        open_mid = paths["open"][:, 0]
        exit_px = paths["open"][:, 30]
        sig = d.sigma_pips
        Tns = times_ns[idx + 1]                    # entry-bar minute boundary
        era = d.era.to_numpy()

        # 1s fills across the latency grid
        fills = {L: fill_at(ts, px, Tns + int(L * 1_000_000_000)) for L in LAT}
        px0 = fills[0.0]
        cov = np.isfinite(px0) & np.isfinite(fills[1.5])
        for L in LAT:
            cov &= np.isfinite(fills[L])
        coverage = float(cov.mean())

        cell = {"signals": int(len(idx)), "coverage_1s": coverage,
                "signals_per_year": len(idx) / yrs, "by_L": {}, "era_cov": {}}

        # per-era coverage (rule 9a)
        for e in ("early", "late"):
            m = era == e
            cell["era_cov"][e] = dict(
                signals=int(m.sum()),
                covered=float((cov & m).mean() if m.any() else 0.0),
                covered_n=int((cov & m).sum()))

        # (A) sub-second adverse selection + (B) gross edge vs latency
        for L in LAT:
            fL = fills[L]
            asel = side * (fL - px0) / PIP                     # +cost
            gross = side * (exit_px - fL) / PIP
            v = cov & np.isfinite(fL)
            g = summarize(gross, sig, v)
            g["asel_mean_pips"] = float(np.mean(asel[v]))
            g["asel_median_pips"] = float(np.median(asel[v]))
            cell["by_L"][L] = g

        # (C) Case A/B split at 1.5 s
        ext = (-side) * (fills[1.5] - px0) / PIP               # +extended in extreme dir
        v = cov
        caseA = v & (ext >= 1.0)
        caseB = v & (ext <= -1.0)
        mid = v & (np.abs(ext) < 1.0)
        aselL = side * (fills[1.5] - px0) / PIP
        cell["case_split"] = {
            "A_extend_ge1pip": dict(frac=float(caseA.sum() / v.sum()),
                                    asel_mean=float(np.mean(aselL[caseA])) if caseA.any() else np.nan),
            "B_revert_ge1pip": dict(frac=float(caseB.sum() / v.sum()),
                                    asel_mean=float(np.mean(aselL[caseB])) if caseB.any() else np.nan),
            "mid_lt1pip": dict(frac=float(mid.sum() / v.sum()),
                               asel_mean=float(np.mean(aselL[mid])) if mid.any() else np.nan),
        }

        # 2.0R stop mean_R at L=0 and L=1.5 for the gate cell
        if name == "vol_gate":
            stops = {}
            for L in (0.0, 1.5):
                r = stop_pnl(fills[L], side, paths, sig, STOP_K)
                v = cov & np.isfinite(fills[L])
                stops[L] = dict(mean_R=float(np.mean((r / sig.to_numpy())[v])),
                                mean_pips=float(np.mean(r[v])))
            cell["stop_2R"] = stops

        out["cells"][name] = cell

    del ts, px
    return out


def fmt(out):
    L0 = "L(s) " + "".join(f"{L:>9}" for L in LAT)
    lines = [f"\n===== {out['pair']}  (years {out['years']:.2f}, expansion_cut {out['expansion_cut']:.3f}) ====="]
    for name in ("base", "vol_gate"):
        c = out["cells"].get(name, {})
        if "by_L" not in c:
            lines.append(f"  [{name}] {c}")
            continue
        lines.append(f"\n  [{name}]  signals {c['signals']}  ({c['signals_per_year']:.0f}/yr)  "
                     f"1s-coverage {c['coverage_1s']:.3f}")
        lines.append(f"     era coverage: early {c['era_cov']['early']['covered']:.3f} "
                     f"(n={c['era_cov']['early']['covered_n']}), "
                     f"late {c['era_cov']['late']['covered']:.3f} "
                     f"(n={c['era_cov']['late']['covered_n']})")
        lines.append("     " + L0)
        row = "     asel(pips)" + "".join(f"{c['by_L'][L]['asel_mean_pips']:>9.3f}" for L in LAT)
        lines.append(row)
        lines.append("     grossPip " + "".join(f"{c['by_L'][L]['mean_pips']:>9.3f}" for L in LAT))
        lines.append("     grossR   " + "".join(f"{c['by_L'][L]['mean_R']:>9.4f}" for L in LAT))
        lines.append("     hit      " + "".join(f"{c['by_L'][L]['hit']:>9.3f}" for L in LAT))
        cs = c["case_split"]
        lines.append(f"     case@1.5s: A(extend>=1p) frac {cs['A_extend_ge1pip']['frac']:.3f} "
                     f"asel {cs['A_extend_ge1pip']['asel_mean']:+.3f} | "
                     f"B(revert>=1p) frac {cs['B_revert_ge1pip']['frac']:.3f} "
                     f"asel {cs['B_revert_ge1pip']['asel_mean']:+.3f} | "
                     f"mid frac {cs['mid_lt1pip']['frac']:.3f} asel {cs['mid_lt1pip']['asel_mean']:+.3f}")
        if "stop_2R" in c:
            s = c["stop_2R"]
            lines.append(f"     2.0R-stop mean_R: L=0 {s[0.0]['mean_R']:+.4f}  "
                         f"L=1.5 {s[1.5]['mean_R']:+.4f}  "
                         f"(pips {s[0.0]['mean_pips']:+.3f} -> {s[1.5]['mean_pips']:+.3f})")
    return "\n".join(lines)


def main():
    results = []
    for pair in PAIRS:
        print(f"Loading + testing {pair} ...", flush=True)
        r = run_pair(pair)
        results.append(r)
        print(fmt(r), flush=True)
    with open("rsi_fill_model_results.json", "w") as fh:
        json.dump(results, fh, indent=2, default=float)
    print("\nSaved rsi_fill_model_results.json", flush=True)


if __name__ == "__main__":
    main()
