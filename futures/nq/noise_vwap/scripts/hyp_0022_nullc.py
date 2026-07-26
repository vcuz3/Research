"""EXP-0032 Phase 2: Null C + ES for the intraday-ATR stop buffer.

Runs at 1-minute resolution (the null shuffles 1m bars; ES has no 1s history; the
1m buffered engine reproduces the 1s uplift to <0.003 Sharpe). Two uplifts:
  * uplift_vs_cc  = Sharpe(N20_k1.5) - Sharpe(close-confirmed)      (+0.132 real)
  * uplift_scaling= Sharpe(N20_k1.5) - Sharpe(fixed matched width)  (+0.085 real)

The DECISIVE test is uplift_scaling: a looser stop beats a tighter one on noise
too (so uplift_vs_cc is expected to have a positive null center — that is why the
matched-width fixed buffer exists). If the vol-scaling is real path structure, the
fixed buffer should match the scaled one on a return-shuffled (Null C) tape, so
uplift_scaling should center at ~0 on the null and the real +0.085 should sit in
its tail. Read the null CENTER sign, not just the tail.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.nulls import null_c_returns, diffusivity
from ..core.atr_buffer import run_1m_atr, intraday_atr

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0032"
N, K = 20, 1.5


def _sharpe(trades, elig, inst):
    cost = 2.25 / POINT_VALUE[inst] + 0.5 * TICK[inst]
    d = pd.to_datetime(pd.Index(elig, name="date"))
    t = trades.copy(); t["date"] = pd.to_datetime(t["date"])
    g = t.groupby("date")["points"].sum().reindex(d, fill_value=0.0)
    n = t.groupby("date").size().reindex(d, fill_value=0)
    u = (g - n * 2 * cost) * POINT_VALUE[inst]
    sd = u.std(ddof=1)
    return float(u.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


def uplifts(bars, bands, inst):
    elig = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    be = bars[bars["date"].isin(elig)].copy()
    c = float(K * np.nanmedian(intraday_atr(be, [N])[f"atr_{N}"].to_numpy()))
    cc = run_1m(be, bands, exit_check="every_bar")
    res = run_1m_atr(be, bands, [("scaled", N, float(K)), ("fixed", "const1", c)])
    s_cc = _sharpe(cc, elig, inst)
    s_sc = _sharpe(res["scaled"], elig, inst)
    s_fx = _sharpe(res["fixed"], elig, inst)
    return {"cc": s_cc, "scaled": s_sc, "fixed": s_fx,
            "uplift_vs_cc": s_sc - s_cc, "uplift_scaling": s_sc - s_fx, "fixed_c": c}


def run_real():
    out = {}
    for inst in ("NQ", "ES"):
        bars = load_rth(inst); bands = noise_bands(bars, 90)
        out[inst] = uplifts(bars, bands, inst)
        print(f"{inst}: cc={out[inst]['cc']:.3f} scaled={out[inst]['scaled']:.3f} "
              f"fixed={out[inst]['fixed']:.3f} | uplift_vs_cc={out[inst]['uplift_vs_cc']:+.3f} "
              f"uplift_scaling={out[inst]['uplift_scaling']:+.3f} (c={out[inst]['fixed_c']:.2f})")
    return out


def run_null(draws):
    bars = load_rth("NQ"); bands = noise_bands(bars, 90)
    real = uplifts(bars, bands, "NQ")
    print(f"REAL NQ: uplift_vs_cc={real['uplift_vs_cc']:+.3f}, "
          f"uplift_scaling={real['uplift_scaling']:+.3f}")
    print(f"Real diffusivity={diffusivity(bars):.6f}")
    rec = []
    for i in range(draws):
        nbars = null_c_returns(bars, seed=7_100_000 + i)
        nbands = noise_bands(nbars, 90)
        u = uplifts(nbars, nbands, "NQ")
        u["diffusivity"] = diffusivity(nbars)
        rec.append(u)
        if i == 0:
            print(f"Null draw 1 diffusivity={u['diffusivity']:.6f}")
        print(f"draw {i+1}/{draws}: vs_cc={u['uplift_vs_cc']:+.3f} "
              f"scaling={u['uplift_scaling']:+.3f}", end="\r", flush=True)
    print()
    df = pd.DataFrame(rec)
    df.to_csv(OUT / "nullc_draws.csv", index=False)

    def summ(col, real_val):
        a = df[col].to_numpy()
        p = (1.0 + float((a >= real_val).sum())) / (len(a) + 1.0)
        z = float((real_val - a.mean()) / a.std(ddof=1)) if a.std(ddof=1) > 0 else float("nan")
        return {"real": float(real_val), "null_center": float(a.mean()),
                "null_sd": float(a.std(ddof=1)), "z": z, "frac_null_ge_real": p}

    report = {
        "draws": draws,
        "real_diffusivity": diffusivity(bars),
        "null_diffusivity_mean": float(df["diffusivity"].mean()),
        "uplift_vs_cc": summ("uplift_vs_cc", real["uplift_vs_cc"]),
        "uplift_scaling": summ("uplift_scaling", real["uplift_scaling"]),
    }
    (OUT / "nullc_report.json").write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("\nNULL C RESULT")
    print(json.dumps(report, indent=2))
    sc = report["uplift_scaling"]
    print("\nDECISIVE (vol-scaling vs matched-width fixed buffer):")
    print(f"  real +{sc['real']:.3f} | null center {sc['null_center']:+.3f} "
          f"(sd {sc['null_sd']:.3f}) | z {sc['z']:+.2f} | frac(null>=real) {sc['frac_null_ge_real']:.3f}")
    verdict = ("REAL (scaling survives)" if sc["null_center"] <= 0.02 and sc["frac_null_ge_real"] <= 0.05
               else "MACHINERY (null reproduces the scaling uplift)")
    print(f"  -> {verdict}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("mode", choices=("real", "null"))
    ap.add_argument("draws", type=int, nargs="?", default=30)
    a = ap.parse_args()
    if a.mode == "real":
        run_real()
    else:
        if a.draws < 20:
            raise SystemExit("Use at least 20 null draws; 30+ recommended.")
        run_null(a.draws)


if __name__ == "__main__":
    main()
