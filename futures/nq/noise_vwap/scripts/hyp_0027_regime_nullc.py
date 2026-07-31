"""EXP-0039 / HYP-0027 — Null C for the EXP-0038 volatility-regime P&L profile.

Does the high-vol Sharpe concentration (and the elevated-vol dip) survive the
drift-preserving return shuffle, or is it vol-geometry the null reproduces?

The null (`core/nulls.py::null_c_returns`) pins each session's opening atom and
preserves its NET move, so daily close-to-close returns -- hence the vol/trend
regime LABELS -- are preserved EXACTLY, while intraday continuation is destroyed.
We therefore stratify the null draws by the SAME (real) regime labels and ask,
per cell, whether the real per-cell Sharpe beats the null's.

Three variants on their own audited null pipelines, one shared seed sequence:
  baseline   core.engine every_bar on null_c_returns(load_rth)
  atr_buffer run_1m_atr N20_k1.5   on null_c_returns(load_rth)   [EXP-0033/0037 path]
  partial_tp engine2 every_bar+tp1.0_50 on _null_c_frame(load_session) [exit_mgmt path]

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0027_regime_nullc validate
  python -u -m futures.nq.noise_vwap.scripts.hyp_0027_regime_nullc null 40
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.atr_buffer import run_1m_atr
from ..core.nulls import null_c_returns, diffusivity
from ..core import session as S
from ..core import engine2 as E
from .studies import _null_c_frame
from .regime_coverage import (
    build_regimes, daily_net_usd, sharpe_ann, VOL_LABELS, TREND_LABELS,
    COST_SIDE, RT_COST, LOOKBACK, N_MIN, SR_MIN,
)

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0039"
INST = "NQ"


# --------------------------------------------------------------------------- #
def variant_trades(bars_rth, bands_rth, sbars, sbands, dm):
    """Real trades for the three variants (shared entries, different exits)."""
    return {
        "baseline": run_1m(bars_rth, bands_rth, exit_check="every_bar"),
        "atr_buffer": run_1m_atr(bars_rth, bands_rth, [("N20_k1.5", 20, 1.5)])["N20_k1.5"],
        "partial_tp": E.run(sbars, sbands, dm, exit_check="every_bar",
                            tp_atr=1.0, tp_frac=0.5),
    }


def null_trades(seed, bars, sbars, dm):
    """One null draw: shuffle both pipelines with the same seed, return trades."""
    nb = null_c_returns(bars, seed)                    # 'date'/'tod' frame
    bn = noise_bands(nb, LOOKBACK)
    base = run_1m(nb, bn, exit_check="every_bar")
    atr = run_1m_atr(nb, bn, [("N20_k1.5", 20, 1.5)])["N20_k1.5"]
    nsb = _null_c_frame(sbars, seed)                   # 'sdate'/'mfo' frame
    nsbands = S.noise_bands(nsb, LOOKBACK)
    tp = E.run(nsb, nsbands, dm, exit_check="every_bar", tp_atr=1.0, tp_frac=0.5)
    return {"baseline": base, "atr_buffer": atr, "partial_tp": tp}, diffusivity(nb)


def cell_sharpes(trades, eligible, reg):
    """Zero-day daily-$ Sharpe for every cell + marginal + aggregate."""
    usd = daily_net_usd(trades, eligible)
    df = reg.copy()
    df["net_usd"] = usd.reindex(df.index).to_numpy()
    out = {"AGG": sharpe_ann(df["net_usd"].to_numpy())}
    for lab, g in df.groupby("vol_regime", observed=True):
        out[f"vol:{lab}"] = sharpe_ann(g["net_usd"].to_numpy())
    for lab, g in df.groupby("trend_regime", observed=True):
        out[f"trend:{lab}"] = sharpe_ann(g["net_usd"].to_numpy())
    for key, g in df.groupby(["vol_regime", "trend_regime"], observed=True):
        out[f"{key[0]} x {key[1]}"] = sharpe_ann(g["net_usd"].to_numpy())
    return out


# --------------------------------------------------------------------------- #
def setup():
    bars = load_rth(INST)
    bands = noise_bands(bars, LOOKBACK)
    elig_rth = set(pd.to_datetime(bands["date"].unique()))
    sbars = S.load_session(INST, "RTH")
    sbands = S.noise_bands(sbars, LOOKBACK)
    elig_sess = set(pd.to_datetime(sbands["sdate"].unique()))
    eligible = np.array(sorted(elig_rth & elig_sess), dtype="datetime64[ns]")
    reg = build_regimes(bars, eligible)
    dm = S.decision_mfos(30, int(sbars["mfo"].max()))
    return bars, bands, sbars, sbands, dm, eligible, reg


def validate():
    """Draw-0 sanity: null preserves daily closes -> identical regime labels;
    null diffusivity matches real (rule 17-bis)."""
    bars, bands, sbars, sbands, dm, eligible, reg = setup()
    real_diff = diffusivity(bars)
    nb = null_c_returns(bars, 12345)
    reg_n = build_regimes(nb, eligible)
    same_labels = reg["cell"].reindex(reg_n.index).eq(reg_n["cell"]).mean()
    # daily close-to-close preservation
    def dret(b):
        last = b.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
        return np.log(last / last.shift(1)).reindex(pd.Index(eligible, name="date"))
    r0, r1 = dret(bars), dret(nb)
    max_ret_err = float((r0 - r1).abs().max())
    print("=== VALIDATE (draw seed 12345) ===")
    print(f"eligible={len(eligible)} labelled={len(reg)}")
    print(f"regime-label agreement real-vs-null: {same_labels:.4f} (expect 1.0)")
    print(f"max |daily-return real-null|: {max_ret_err:.2e} (expect ~0)")
    print(f"diffusivity real={real_diff:.4f} null={diffusivity(nb):.4f} "
          f"(rule 17-bis gate: match)")
    ok = same_labels > 0.999 and max_ret_err < 1e-9
    print("PASS:", ok)
    return ok


def run_null(ndraw):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, sbars, sbands, dm, eligible, reg = setup()
    variants = ["baseline", "atr_buffer", "partial_tp"]

    real_tr = variant_trades(bars, bands, sbars, sbands, dm)
    real = {v: cell_sharpes(real_tr[v], eligible, reg) for v in variants}
    keys = list(real["baseline"].keys())

    real_diff = diffusivity(bars)
    print(f"=== Regime Null C ({ndraw} draws) — HYP-0027/EXP-0039 ===")
    print(f"eligible={len(eligible)} labelled={len(reg)} cost={RT_COST:.3f}pt RT "
          f"real diffusivity={real_diff:.4f}")

    nulls = {v: {k: [] for k in keys} for v in variants}
    diffs = []
    for i in range(ndraw):
        ntr, dfu = null_trades(1000 + i, bars, sbars, dm)
        diffs.append(dfu)
        for v in variants:
            cs = cell_sharpes(ntr[v], eligible, reg)
            for k in keys:
                nulls[v][k].append(cs[k])
        print(f"  draw {i+1}/{ndraw} done (diff={dfu:.4f})", flush=True)
    print()
    print(f"null diffusivity median={np.median(diffs):.4f} (gate: ~{real_diff:.4f})")

    # assemble per-variant tables
    counts = (reg.groupby(["vol_regime", "trend_regime"], observed=True).size())
    rows_out = {}
    for v in variants:
        rows = []
        for k in keys:
            a = np.array(nulls[v][k]); sd = a.std(ddof=1)
            rv = real[v][k]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            frac = float((a >= rv).mean())
            n_days = (int(counts.get(tuple(k.split(" x ")), np.nan))
                      if " x " in k else "")
            rows.append({"cell": k, "n_days": n_days, "real_sharpe": round(rv, 3),
                         "null_mean": round(float(a.mean()), 3),
                         "null_sd": round(float(sd), 3), "z": round(float(z), 2),
                         "frac_null_ge_real": round(frac, 3)})
        tab = pd.DataFrame(rows)
        tab.to_csv(OUT / f"regime_nullc_{v}.csv", index=False)
        rows_out[v] = tab

    pd.set_option("display.width", 200, "display.max_columns", 20)
    for v in variants:
        print(f"\n################## {v.upper()} ##################")
        print(rows_out[v].to_string(index=False))
        hv = rows_out[v][rows_out[v]["cell"].str.startswith("high x")]
        print(f"  high-vol cells: frac(null>=real) = "
              f"{dict(zip(hv['cell'], hv['frac_null_ge_real']))}")

    summary = {
        "ndraw": ndraw, "eligible": int(len(eligible)), "labelled": int(len(reg)),
        "real_diffusivity": real_diff, "null_diffusivity_median": float(np.median(diffs)),
        "cost_pt_rt": RT_COST,
        "variants": {v: {
            "agg_real": real[v]["AGG"],
            "agg_null_mean": float(np.mean(nulls[v]["AGG"])),
            "agg_frac_null_ge_real": float((np.array(nulls[v]["AGG"]) >= real[v]["AGG"]).mean()),
            "highvol_cells": {k: {"real": real[v][k],
                                  "null_mean": float(np.mean(nulls[v][k])),
                                  "frac_null_ge_real": float((np.array(nulls[v][k]) >= real[v][k]).mean())}
                              for k in keys if k.startswith("high x") or k == "vol:high"},
        } for v in variants},
    }
    (OUT / "summary.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    print(f"\nwrote artifacts to {OUT}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "validate"
    if cmd == "validate":
        validate()
    elif cmd == "null":
        run_null(int(sys.argv[2]) if len(sys.argv) > 2 else 40)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
