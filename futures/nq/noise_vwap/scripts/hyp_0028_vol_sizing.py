"""EXP-0040 / HYP-0028 — Causal volatility-regime position sizing + Null C.

Overlay a CAUSAL vol-regime weight on the deployed continuous-stop baseline and ask
whether it improves risk-adjusted return net of drawdown, and whether the drift-
preserving Null C reproduces the uplift (EXP-0017 machinery signature) or not.

The null preserves daily returns EXACTLY (EXP-0039), so the causal weights w_d are
identical real-vs-null; the null isolates the intraday-P&L content. We compute w_d
ONCE from the real path and apply it to both real and null daily P&L.

Usage:
  python -u -m futures.nq.noise_vwap.scripts.hyp_0028_vol_sizing real
  python -u -m futures.nq.noise_vwap.scripts.hyp_0028_vol_sizing null 40
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK, daily_returns
from ..core.engine import run as run_1m
from ..core.nulls import null_c_returns, diffusivity
from ..core import session as S
from .regime_coverage import build_regimes, daily_net_usd, sharpe_ann, LOOKBACK, RT_COST
from .forensic import sizing as voltarget_sizing

INST = "NQ"
OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0040"
MIN_HIST = 252          # causal expanding-percentile warmup
NDRAW_DEFAULT = 40

SCHEDULES = {
    "high_boost": lambda q: np.where(q < 0.75, 1.0, 1.5),   # PRIMARY
    "vol_linear": lambda q: 0.5 + 1.0 * q,                  # secondary ramp
    "vol_down":   lambda q: 1.5 - 1.0 * q,                  # mirror control
}


# --------------------------------------------------------------------------- #
def causal_percentile(rv: np.ndarray) -> np.ndarray:
    """q_d = fraction of STRICTLY-PRIOR rv <= rv_d (expanding, causal). NaN until
    MIN_HIST prior obs exist."""
    n = len(rv)
    q = np.full(n, np.nan)
    for i in range(MIN_HIST, n):
        prior = rv[:i]
        q[i] = np.mean(prior <= rv[i])
    return q


def causal_weight(q: np.ndarray, schedule) -> np.ndarray:
    """Raw schedule weight, then normalise by the causal expanding PRIOR mean so
    average exposure ~= 1 (EXP-0017). Neutral (1.0) where q is NaN (warmup)."""
    raw = np.where(np.isfinite(q), schedule(np.nan_to_num(q, nan=0.5)), 1.0)
    w = np.ones_like(raw)
    csum = 0.0
    cnt = 0
    for i in range(len(raw)):
        w[i] = raw[i] / (csum / cnt) if cnt > 0 else 1.0
        if np.isfinite(q[i]):
            csum += raw[i]
            cnt += 1
    return w


def build_weights(bars: pd.DataFrame, reg: pd.DataFrame) -> pd.DataFrame:
    """One weight column per schedule, aligned to reg.index (labelled sessions)."""
    rv = reg["rv_ann"].to_numpy()
    q = causal_percentile(rv)
    out = pd.DataFrame(index=reg.index)
    out["q"] = q
    for name, sch in SCHEDULES.items():
        out[name] = causal_weight(q, sch)
    return out


# --------------------------------------------------------------------------- #
def max_dd_usd(x: np.ndarray) -> float:
    """Max peak-to-trough of the cumulative $ path (negative = drawdown)."""
    cum = np.cumsum(x)
    peak = np.maximum.accumulate(cum)
    return float((cum - peak).min())


def cvar5(x: np.ndarray) -> float:
    """Mean of the worst 5% daily-$ outcomes."""
    k = max(1, int(0.05 * len(x)))
    return float(np.sort(x)[:k].mean())


def frame_a_metrics(pnl: np.ndarray, w: np.ndarray) -> dict:
    s = w * pnl
    return {
        "sharpe": sharpe_ann(s),
        "mean_usd": float(s.mean()),
        "maxdd_usd": max_dd_usd(s),
        "cvar5_usd": cvar5(s),
        "mean_w": float(w.mean()),
    }


def frame_a(pnl: np.ndarray, weights: pd.DataFrame) -> dict:
    base = frame_a_metrics(pnl, np.ones_like(pnl))
    out = {"unsized": base}
    for name in SCHEDULES:
        m = frame_a_metrics(pnl, weights[name].to_numpy())
        m["d_sharpe"] = m["sharpe"] - base["sharpe"]
        m["d_maxdd"] = m["maxdd_usd"] - base["maxdd_usd"]      # +ve = shallower (better)
        m["d_cvar5"] = m["cvar5_usd"] - base["cvar5_usd"]      # +ve = better
        out[name] = m
    return out


# --------------------------------------------------------------------------- #
def setup():
    bars = load_rth(INST)
    bands = noise_bands(bars, LOOKBACK)
    elig_rth = set(pd.to_datetime(bands["date"].unique()))
    sbars = S.load_session(INST, "RTH")
    sbands = S.noise_bands(sbars, LOOKBACK)
    eligible = np.array(sorted(elig_rth & set(pd.to_datetime(sbands["sdate"].unique()))),
                        dtype="datetime64[ns]")
    reg = build_regimes(bars, eligible)
    weights = build_weights(bars, reg)
    return bars, bands, eligible, reg, weights


def baseline_pnl(bars, bands, reg):
    tr = run_1m(bars, bands, exit_check="every_bar")
    usd = daily_net_usd(tr, np.array(reg.index.values, dtype="datetime64[ns]"))
    return usd.reindex(reg.index).to_numpy()


def run_real():
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, eligible, reg, weights = setup()
    pnl = baseline_pnl(bars, bands, reg)
    fa = frame_a(pnl, weights)

    print("=== HYP-0028 vol-regime sizing (Frame A, continuous-stop baseline) ===")
    print(f"labelled sessions={len(reg)} cost={RT_COST:.3f}pt RT | prior-mean-1 overlay")
    base = fa["unsized"]
    print(f"\nUNSIZED baseline: Sharpe {base['sharpe']:+.3f}  mean${base['mean_usd']:+.1f}"
          f"  maxDD ${base['maxdd_usd']:,.0f}  CVaR5 ${base['cvar5_usd']:+.1f}")
    hdr = f"{'schedule':<11s} {'mean_w':>6s} {'Sharpe':>7s} {'dSharpe':>8s} {'mean$':>7s} {'maxDD$':>10s} {'dMaxDD$':>9s} {'CVaR5$':>8s} {'dCVaR$':>8s}"
    print("\n" + hdr); print("-" * len(hdr))
    for name in SCHEDULES:
        m = fa[name]
        print(f"{name:<11s} {m['mean_w']:>6.3f} {m['sharpe']:>+7.3f} {m['d_sharpe']:>+8.3f} "
              f"{m['mean_usd']:>+7.1f} {m['maxdd_usd']:>10,.0f} {m['d_maxdd']:>+9,.0f} "
              f"{m['cvar5_usd']:>+8.1f} {m['d_cvar5']:>+8.1f}")

    # Frame B: vol-target interaction (descriptive, real-only)
    print("\n=== Frame B: regime tilt x vol-target book (descriptive) ===")
    fb = frame_b(bars, bands, reg, weights)
    print(f"{'schedule':<11s} {'Sharpe':>7s} {'dSharpe':>8s} {'maxDD':>8s} {'dMaxDD':>8s} {'CAGR':>7s}")
    for name in ["unsized"] + list(SCHEDULES):
        m = fb[name]
        print(f"{name:<11s} {m['sharpe']:>+7.3f} {m.get('d_sharpe',0):>+8.3f} "
              f"{m['maxdd']:>+8.1%} {m.get('d_maxdd',0):>+8.1%} {m['cagr']:>+7.1%}")

    json.dump({"frame_a": fa, "frame_b": {k: {kk: vv for kk, vv in v.items() if kk != 'ret'}
                                          for k, v in fb.items()}},
              open(OUT / "real.json", "w"), indent=2, default=float)
    print("\nNull-C the deployable Frame-A overlay:  "
          "python -u -m futures.nq.noise_vwap.scripts.hyp_0028_vol_sizing null 40")


def frame_b(bars, bands, reg, weights):
    """Vol-target contract count x regime weight, compounded (forensic.sizing style)."""
    cost = 2.25 / POINT_VALUE[INST] / 2 + 0.25 * TICK[INST]  # per side 0.25tick
    tr = run_1m(bars, bands, exit_check="every_bar")
    base = voltarget_sizing(INST, bars, tr, cost)  # daily return series in base['ret']
    sess = base["ret"].index
    wmap = {name: weights[name].reindex(pd.to_datetime(sess)).fillna(1.0).to_numpy()
            for name in SCHEDULES}
    out = {"unsized": {"sharpe": base["sharpe"], "maxdd": base["maxdd"], "cagr": base["cagr"]}}
    r0 = base["ret"].to_numpy()
    for name in SCHEDULES:
        r = r0 * wmap[name]
        eqc = pd.Series(1 + r, index=sess).cumprod()
        mdd = float(((eqc - eqc.cummax()) / eqc.cummax()).min())
        act = r[r0 != 0.0]
        sh = act.mean() / act.std() * np.sqrt(252) if act.std() > 0 else 0.0
        cagr = float(eqc.iloc[-1]) ** (365.25 / (sess[-1] - sess[0]).days) - 1
        out[name] = {"sharpe": sh, "maxdd": mdd, "cagr": cagr,
                     "d_sharpe": sh - base["sharpe"], "d_maxdd": mdd - base["maxdd"]}
    return out


def run_null(ndraw):
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, eligible, reg, weights = setup()
    pnl_real = baseline_pnl(bars, bands, reg)
    real = frame_a(pnl_real, weights)
    real_diff = diffusivity(bars)

    # assert daily returns preserved on draw 0 -> weights valid for null
    nb0 = null_c_returns(bars, 777)
    r0 = daily_returns(bars).reindex(pd.Index(eligible, name="date"))
    r1 = daily_returns(nb0).reindex(pd.Index(eligible, name="date"))
    assert float((r0 - r1).abs().max()) < 1e-9, "null altered daily returns!"

    print(f"=== HYP-0028 Frame-A Null C ({ndraw} draws) — EXP-0040 ===")
    print(f"labelled={len(reg)} real diffusivity={real_diff:.4f} "
          f"(weights identical real/null: daily returns preserved, asserted)")
    print("REAL Frame-A uplift: " + "  ".join(
        f"{n}: dSharpe={real[n]['d_sharpe']:+.3f} dMaxDD=${real[n]['d_maxdd']:+,.0f}"
        for n in SCHEDULES))

    nul = {n: {"d_sharpe": [], "d_maxdd": [], "d_cvar5": []} for n in SCHEDULES}
    diffs = []
    for i in range(ndraw):
        nb = null_c_returns(bars, 3000 + i)
        bn = noise_bands(nb, LOOKBACK)
        pnl_n = baseline_pnl(nb, bn, reg)
        fa_n = frame_a(pnl_n, weights)
        for n in SCHEDULES:
            nul[n]["d_sharpe"].append(fa_n[n]["d_sharpe"])
            nul[n]["d_maxdd"].append(fa_n[n]["d_maxdd"])
            nul[n]["d_cvar5"].append(fa_n[n]["d_cvar5"])
        diffs.append(diffusivity(nb))
        print(f"  draw {i+1}/{ndraw} done", flush=True)
    print(f"null diffusivity median={np.median(diffs):.4f} (gate ~{real_diff:.4f})")

    rows = []
    for n in SCHEDULES:
        for key in ("d_sharpe", "d_maxdd", "d_cvar5"):
            a = np.array(nul[n][key]); sd = a.std(ddof=1)
            rv = real[n][key]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            frac = float((a >= rv).mean())
            rows.append({"schedule": n, "metric": key, "real": round(float(rv), 3),
                         "null_mean": round(float(a.mean()), 3),
                         "null_sd": round(float(sd), 3), "z": round(float(z), 2),
                         "frac_null_ge_real": round(frac, 3)})
    tab = pd.DataFrame(rows)
    tab.to_csv(OUT / "nullc.csv", index=False)
    pd.set_option("display.width", 200)
    print("\n" + tab.to_string(index=False))

    prim = tab[(tab["schedule"] == "high_boost")]
    sh = prim[prim["metric"] == "d_sharpe"].iloc[0]
    dd = prim[prim["metric"] == "d_maxdd"].iloc[0]
    print(f"\nPRIMARY high_boost: Sharpe-uplift real {sh['real']:+.3f} vs null "
          f"{sh['null_mean']:+.3f} (z {sh['z']:+.2f}, frac {sh['frac_null_ge_real']:.3f}); "
          f"dMaxDD real ${dd['real']:+,.0f}")
    json.dump({"ndraw": ndraw, "real_diffusivity": real_diff,
               "null_diffusivity_median": float(np.median(diffs)),
               "real_frame_a": {n: {k: real[n][k] for k in ("d_sharpe", "d_maxdd", "d_cvar5", "sharpe", "maxdd_usd")}
                                for n in SCHEDULES},
               "table": rows}, open(OUT / "summary.json", "w"), indent=2, default=float)
    print(f"\nwrote artifacts to {OUT}")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        run_null(int(sys.argv[2]) if len(sys.argv) > 2 else NDRAW_DEFAULT)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
