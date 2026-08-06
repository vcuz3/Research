"""Claim-matched null for the combined regime gate (ATR expansion AND RV30 percentile).

The candidate from `RSI_Z_REGIME_MATRIX_REPORT.md` was the MAXIMUM of a five-arm
regime search, so rule 17 requires the null to reproduce the whole search and compare
the real maximum against the null distribution of maxima -- not the single arm against
its own null.

THE NULL: donor re-pairing of the REGIME FEATURES ONLY. Within each
(session minute, era) cell, the triple (vei_atr_z, rv30_pct, rv5_pct) is permuted
JOINTLY across dates, on the full minute grid.

  PRESERVES: every price path and therefore every trade's P&L given its entry; the
  |z| trigger and its depth; the event clock and the non-overlap rule; the compulsory
  stop and slippage; the exact marginal distribution of each regime feature within
  every slot/era cell, hence the gate's firing RATE; the joint dependence between the
  two gates (they move together to a different date); the same-slot seasonal structure.

  DESTROYS: only the contemporaneous link between the regime state and THIS decision's
  forward return -- which is exactly the claim.

All four preservation claims are asserted in code before the draws are interpreted.

Also included, because the report named it as a required control: single gates
TIGHTENED to the combined arm's own signal rate, so "is it the combination or just
that rate?" is answered directly rather than through the frontier.

Reproduce with:
    python -u _run_rsi_gate_null.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    BASE_K,
    HORIZON,
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_z_regime_matrix import Z_GRID, add_extra_features, early_cut
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_gate_null_results.json"
CSV = ROOT / "rsi_gate_null_draws.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
GATE_KEEP = 0.40
DRAWS = 100
SEED = 20260805
FEATS = ["vei_atr_z", "rv30_pct", "rv5_pct"]

# the five-arm regime search the candidate was selected from
SEARCH = [
    ("ATR40", [("vei_atr_z", 0.40)]),
    ("rv30_40", [("rv30_pct", 0.40)]),
    ("rv5_40", [("rv5_pct", 0.40)]),
    ("rv30_20", [("rv30_pct", 0.20)]),
    ("ATR40+rv30_40", [("vei_atr_z", 0.40), ("rv30_pct", 0.40)]),
]


def run_arm(f, arrays, gate_mask, years_all):
    """Event clock on (|z| >= 1.5 AND gate), non-overlap, compulsory stop."""
    zl, zs = f.z.le(-BASE_K), f.z.ge(BASE_K)
    long_c, short_c = zl & gate_mask, zs & gate_mask
    cond = (long_c | short_c).fillna(False).to_numpy()
    side_all = np.where(long_c.fillna(False), 1.0, np.where(short_c.fillna(False), -1.0, 0.0))
    idx = select_events(f, cond)
    if len(idx) < 300:
        return None
    d, paths = extract(f, arrays, idx)
    sg = d.sigma_pips.to_numpy()
    pnl, st, _ = simulate(paths, side_all[idx], STOP_K * sg, HORIZON, SLIPPAGE)
    m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
    return m


def frontier_of(f, arrays):
    """(log signals/year, mean R) for the |z| >= k sweep -- the reference curve."""
    xs, ys = [], []
    for k in Z_GRID:
        zl, zs = f.z.le(-k), f.z.ge(k)
        cond = (zl | zs).fillna(False).to_numpy()
        side_all = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
        idx = select_events(f, cond)
        d, paths = extract(f, arrays, idx)
        sg = d.sigma_pips.to_numpy()
        pnl, st, _ = simulate(paths, side_all[idx], STOP_K * sg, HORIZON, SLIPPAGE)
        m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
        xs.append(np.log(m["signals_per_year"]))
        ys.append(m["mean_R"])
    o = np.argsort(xs)
    return np.asarray(xs)[o], np.asarray(ys)[o]


def excess(m, fx, fy):
    return m["mean_R"] - float(np.interp(np.log(m["signals_per_year"]), fx, fy))


def gate_from(f, spec, cuts):
    g = pd.Series(True, index=f.index)
    for col, keep in spec:
        g &= f[col].ge(cuts[(col, keep)])
    return g


def group_positions(f):
    """Index arrays for the (session minute, era) donor cells."""
    key = f.session_minute.astype(np.int32).to_numpy() * 2 + f.era.eq("late").to_numpy()
    order = np.argsort(key, kind="stable")
    ks = key[order]
    bounds = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1], True])
    return [order[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


def analyse(pair, rng):
    f = add_extra_features(build_features(pair))
    arrays = ohlc_arrays(f)
    years_all = years_of(f)
    fx, fy = frontier_of(f, arrays)

    cuts = {}
    for _lab, spec in SEARCH:
        for col, keep in spec:
            cuts[(col, keep)] = early_cut(f, col, keep)

    # --- real arms ---
    real = {}
    for lab, spec in SEARCH:
        m = run_arm(f, arrays, gate_from(f, spec, cuts), years_all)
        real[lab] = {"excess_R": excess(m, fx, fy), **m}
    real_best = max(real, key=lambda k: real[k]["excess_R"])
    real_max = real[real_best]["excess_R"]
    target_rate = real["ATR40+rv30_40"]["signals_per_year"]

    # --- required control: single gates TIGHTENED to the combined arm's own rate ---
    same_rate = {}
    for col in ["vei_atr_z", "rv30_pct"]:
        best, bestgap = None, np.inf
        for keep in np.arange(0.06, 0.45, 0.02):
            c = early_cut(f, col, float(keep))
            m = run_arm(f, arrays, f[col].ge(c), years_all)
            if m is None:
                continue
            gap = abs(m["signals_per_year"] - target_rate)
            if gap < bestgap:
                best, bestgap = ({"keep": float(keep), "excess_R": excess(m, fx, fy), **m}, gap)
        same_rate[col] = best

    # --- null draws ---
    groups = group_positions(f)
    base_vals = {c: f[c].to_numpy().copy() for c in FEATS}
    n = len(f)
    corr_real = float(pd.Series(base_vals["vei_atr_z"]).corr(
        pd.Series(base_vals["rv30_pct"]), method="spearman"))
    n_ztrig = int((f.z.abs() >= BASE_K).sum())
    rows, checked = [], False
    for t in range(DRAWS):
        perm = np.arange(n)
        for pos in groups:
            if len(pos) > 1:
                perm[pos] = pos[rng.permutation(len(pos))]
        for c in FEATS:
            f[c] = base_vals[c][perm]        # joint: one permutation for all three

        if not checked:
            rate_real = float(np.nanmean(
                (base_vals["vei_atr_z"] >= cuts[("vei_atr_z", 0.40)])
                & (base_vals["rv30_pct"] >= cuts[("rv30_pct", 0.40)])))
            rate_null = float(gate_from(f, SEARCH[4][1], cuts).mean())
            fin = lambda a: np.sort(a[np.isfinite(a)])
            checks = {
                "marginals preserved exactly": bool(all(
                    np.array_equal(fin(base_vals[c]), fin(f[c].to_numpy())) for c in FEATS)),
                "joint feature dependence preserved": bool(abs(float(
                    f.vei_atr_z.corr(f.rv30_pct, method="spearman")) - corr_real) < 1e-9),
                "combined gate firing rate preserved to <0.5pp": bool(
                    abs(rate_null - rate_real) < 0.005),
                "z trigger untouched": bool(
                    int((f.z.abs() >= BASE_K).sum()) == n_ztrig),
            }
            checked = True

        draw = {"pair": pair, "draw": t}
        vals = []
        for lab, spec in SEARCH:
            m = run_arm(f, arrays, gate_from(f, spec, cuts), years_all)
            e = excess(m, fx, fy) if m else np.nan
            draw[lab] = e
            vals.append(e)
        draw["MAX"] = float(np.nanmax(vals))
        rows.append(draw)
        if (t + 1) % 25 == 0:
            print(f"   {pair} draw {t + 1}/{DRAWS}", flush=True)

    for c in FEATS:
        f[c] = base_vals[c]
    return real, real_best, real_max, same_rate, rows, checks, {
        "pair": pair, "target_rate": target_rate, "corr_vei_rv30_spearman": corr_real}


def main():
    rng = np.random.default_rng(SEED)
    reals, draws, diags, sames, checks = {}, [], [], {}, {}
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        real, best, rmax, same_rate, rows, chk, dg = analyse(pair, rng)
        reals[pair] = {"arms": real, "best": best, "max_excess": rmax}
        sames[pair] = same_rate
        draws.extend(rows)
        diags.append(dg)
        checks[pair] = chk

    df = pd.DataFrame(draws)

    print("\n=== 0. Null invariant checks (rule 17: verify what it preserves) ===")
    for pair, chk in checks.items():
        for k, ok in chk.items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {pair}: {k}")

    print("\n=== 1. Real arms, excess over the |z| frontier ===")
    t = pd.DataFrame({p: {k: v["excess_R"] for k, v in reals[p]["arms"].items()}
                      for p in PAIRS}).T
    t["MAX"] = t.max(axis=1)
    t["argmax"] = [reals[p]["best"] for p in PAIRS]
    print(t.round(4).to_string())

    print("\n=== 2. REQUIRED CONTROL: single gates tightened to the combined arm's rate ===")
    for pair in PAIRS:
        c = reals[pair]["arms"]["ATR40+rv30_40"]
        print(f"\n   {pair}: combined = {c['signals_per_year']:.0f}/yr, "
              f"excess {c['excess_R']:+.4f} R, mean R {c['mean_R']:.4f}")
        for col, m in sames[pair].items():
            print(f"      {col:12s} keep {m['keep']:.2f} -> {m['signals_per_year']:.0f}/yr, "
                  f"excess {m['excess_R']:+.4f} R, mean R {m['mean_R']:.4f}")
    comb = pd.Series({p: reals[p]["arms"]["ATR40+rv30_40"]["excess_R"] for p in PAIRS})
    for col in ["vei_atr_z", "rv30_pct"]:
        s = pd.Series({p: sames[p][col]["excess_R"] for p in PAIRS})
        d = comb - s
        print(f"\n   combined minus same-rate {col}: median {d.median():+.4f} R, "
              f"{int((d > 0).sum())}/4 pairs")

    print(f"\n=== 3. NULL, {DRAWS} donor-matched draws: per-arm ===")
    for lab, _ in SEARCH:
        print(f"\n-- {lab} --")
        for pair in PAIRS:
            nd = df.loc[df.pair.eq(pair), lab].dropna()
            rv = reals[pair]["arms"][lab]["excess_R"]
            print(f"   {pair}: real {rv:+.4f} | null mean {nd.mean():+.4f} sd {nd.std(ddof=1):.4f} "
                  f"p95 {nd.quantile(0.95):+.4f} | frac null >= real {float((nd >= rv).mean()):.3f}")

    print("\n=== 4. SELECTION-CORRECTED NULL: real MAX against the null MAX distribution ===")
    verdict = {}
    for pair in PAIRS:
        nd = df.loc[df.pair.eq(pair), "MAX"].dropna()
        rmax = reals[pair]["max_excess"]
        frac = float((nd >= rmax).mean())
        verdict[pair] = {
            "real_max_excess": rmax, "real_argmax": reals[pair]["best"],
            "null_max_mean": float(nd.mean()), "null_max_sd": float(nd.std(ddof=1)),
            "null_max_p95": float(nd.quantile(0.95)),
            "frac_null_max_ge_real": frac, "passes_p05": bool(frac <= 0.05),
        }
        print(f"   {pair}: real max {rmax:+.4f} ({reals[pair]['best']}) | "
              f"null max mean {nd.mean():+.4f} sd {nd.std(ddof=1):.4f} p95 {nd.quantile(0.95):+.4f} "
              f"| frac >= real {frac:.3f}  [{'PASS' if frac <= 0.05 else 'FAIL'}]")
    npass = sum(v["passes_p05"] for v in verdict.values())
    print(f"\n   [{'PASS' if npass >= 3 else 'FAIL'}] selection-corrected null cleared on "
          f"{npass}/4 pairs (need >=3)")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "claim-matched null for RSI_Z_REGIME_MATRIX_REPORT.md",
            "pairs": PAIRS, "draws": DRAWS, "seed": SEED,
            "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "null": ("joint donor re-pairing of (vei_atr_z, rv30_pct, rv5_pct) across "
                     "dates within (session minute, era), on the full minute grid; "
                     "price paths, |z| trigger, event clock, non-overlap, stop and "
                     "feature marginals/joint dependence all preserved"),
            "selection_correction": "real max over the 5-arm regime search vs the null max",
        },
        "invariant_checks": checks,
        "diagnostics": diags,
        "real_arms": {p: {k: {kk: vv for kk, vv in v.items()} for k, v in reals[p]["arms"].items()}
                      for p in PAIRS},
        "same_rate_single_gates": sames,
        "verdicts": verdict,
        "selection_corrected_pass_pairs": npass,
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
