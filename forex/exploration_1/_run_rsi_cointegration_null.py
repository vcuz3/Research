"""Step-2 confirmatory test of the cross-pair DIVERGENCE conditioner survivor.

The cointegration screen (RSI_COINTEGRATION_GATE_REPORT via RSI_COINTEGRATION_GATE_SPEC.md)
found `diverge_hi` SUPPORTED: fading P reverts better when the partner DIVERGES (does not
confirm the move). The direction and keep were selected, so this run applies:

  1. SELECTION-CORRECTED CLAIM-MATCHED DONOR NULL. Re-pair `z_partner` among |z|>=1.5
     SIGNAL rows within each (session minute, era) cell. This destroys the contemporaneous
     link between THIS decision and the partner's state while preserving: P's price paths
     and every trade's P&L given entry; the |z| trigger; the event clock, non-overlap,
     stop, slippage; and the partner's signal-row marginal within every cell (hence each
     gate's firing rate). Because the direction and keep were selected over the whole
     diverge/partner search, compare the REAL MAX excess against the NULL MAX (rule 17).

  2. REDUNDANCY vs the confirmed volatility gate. The feature is built from the partner
     only, so it should be near-orthogonal to P's own vol/directional state -- tested via
     correlation, a within-vol conditional split, and whether divergence STACKS on the vol
     gate.

Reproduce with:
    python -u _run_rsi_cointegration_null.py
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
from _efficiency_features import add_efficiency_features
from _run_rsi_z_regime_matrix import Z_GRID, add_extra_features, early_cut
from _run_rsi_cointegration_gate import PARTNER, build_arms, pair_z, sig_cut
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_cointegration_null_results.json"
CSV = ROOT / "rsi_cointegration_null_draws.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
VOL_KEEP = 0.40
DIV_KEEP = 0.10          # the primary survivor: diverge_hi 10
DRAWS = 100
SEED = 20260805


def set_cross_features(f):
    """(re)compute xalign and partner_absz from the current z_partner column."""
    long_sig, short_sig = f.z.le(-BASE_K), f.z.ge(BASE_K)
    f["xalign"] = np.where(long_sig, f.z_partner,
                           np.where(short_sig, -f.z_partner, np.nan))
    f["partner_absz"] = f.z_partner.abs().to_numpy()


def build_frame(pair, zbank):
    f = add_efficiency_features(add_extra_features(build_features(pair)))
    f["z_partner"] = f["time"].map(zbank[PARTNER[pair]])
    set_cross_features(f)
    return f


def frontier_of(f, arrays, delay):
    xs, ys = [], []
    for k in Z_GRID:
        zl, zs = f.z.le(-k), f.z.ge(k)
        cond = (zl | zs).fillna(False).to_numpy()
        side = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
        idx = select_events(f, cond)
        d, paths = extract(f, arrays, idx)
        pp = shift_paths(paths, delay)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
        pnl, st, _ = simulate(pp, side[idx], STOP_K * sg, HORIZON, SLIPPAGE)
        m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
        xs.append(np.log(m["signals_per_year"]))
        ys.append(m["mean_R"])
    o = np.argsort(xs)
    return np.asarray(xs)[o], np.asarray(ys)[o]


def evaluate(f, arrays, cond, side_all, delay, fx, fy):
    idx = select_events(f, cond)
    if len(idx) < 300:
        return None
    d, paths = extract(f, arrays, idx)
    pp = shift_paths(paths, delay)
    sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()
    pnl, st, _ = simulate(pp, side_all[idx], STOP_K * sg, HORIZON, SLIPPAGE)
    m = metrics(pnl, sg, d.sdate.values, years_of(d), st)
    if "mean_R" not in m:
        return None
    m["excess_R"] = m["mean_R"] - float(np.interp(np.log(m["signals_per_year"]), fx, fy))
    return m


def mask_arm(f, mask):
    zl, zs = f.z.le(-BASE_K) & mask, f.z.ge(BASE_K) & mask
    cond = (zl | zs).fillna(False).to_numpy()
    side = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
    return cond, side


def search_arms(f):
    return [(lab, fam, cond, side) for lab, fam, cond, side in build_arms(f)
            if fam != "frontier |z|"]


def signal_groups(f):
    """|z|>=1.5 signal-row indices grouped by (session minute, era, SIDE).

    Splitting by side is essential: xalign = side * z_partner, so permuting z_partner
    only among SAME-SIDE signals preserves the xalign marginal and the gate firing rate
    exactly, while still destroying the pairing between this P signal and the partner's
    state. Mixing sides scrambles the rate (rule 17 invariant).
    """
    sig = f.z.abs().ge(BASE_K).fillna(False).to_numpy()
    sig_idx = np.flatnonzero(sig)
    slot = f.session_minute.to_numpy()[sig_idx].astype(np.int64)
    late = f.era.eq("late").to_numpy()[sig_idx].astype(np.int64)
    side = (f.z.to_numpy()[sig_idx] >= 0).astype(np.int64)   # short=1, long=0
    key = slot * 4 + late * 2 + side
    order = np.argsort(key, kind="stable")
    si, ks = sig_idx[order], key[order]
    bounds = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1], True])
    return [si[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


def analyse(pair, zbank, rng):
    f = build_frame(pair, zbank)
    arrays = ohlc_arrays(f)
    fx1, fy1 = frontier_of(f, arrays, 1)

    # ---- real search: excess for every diverge/partner arm, real MAX ----
    real = {}
    for lab, fam, cond, side in search_arms(f):
        m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
        real[lab] = {"family": fam, **(m or {"excess_R": np.nan})}
    real_ex = {k: v["excess_R"] for k, v in real.items()}
    real_best = max((k for k in real_ex if np.isfinite(real_ex[k])), key=lambda k: real_ex[k])
    real_max = real_ex[real_best]

    # ---- redundancy vs the confirmed vol gate ----
    vei_cut = early_cut(f, "vei_atr_z", VOL_KEEP)
    rv_cut = early_cut(f, "rv30_pct", VOL_KEEP)
    div_cut = sig_cut(f, "xalign", DIV_KEEP, hi=True)
    vol_gate = f.vei_atr_z.ge(vei_cut) & f.rv30_pct.ge(rv_cut)
    diverge = f.xalign.ge(div_cut)

    red = {}
    for lab, mask in [("vol_gate", vol_gate), ("diverge_hi10", diverge),
                      ("vol_gate AND diverge_hi10", vol_gate & diverge)]:
        cond, side = mask_arm(f, mask)
        red[lab] = evaluate(f, arrays, cond, side, 1, fx1, fy1)

    # within-vol conditional split by xalign at its early-era median among vol signals
    zsig = f.z.abs().ge(BASE_K)
    pop = zsig & vol_gate
    thr = float(f.loc[f.era.eq("early") & pop, "xalign"].median())
    within = {}
    for lab, mask in [("vol&div_hi", pop & f.xalign.ge(thr)),
                      ("vol&div_lo", pop & f.xalign.lt(thr))]:
        cond, side = mask_arm(f, mask)
        within[lab] = evaluate(f, arrays, cond, side, 1, fx1, fy1)

    zrows = f.loc[zsig.fillna(False)]
    corr = {c: float(zrows.xalign.corr(zrows[c], method="spearman"))
            for c in ["vei_atr_z", "rv30_pct", "adx_z"]}
    corr["P_diverge_given_vol"] = float(diverge[pop].mean())
    corr["P_diverge_marginal"] = float(diverge[zsig.fillna(False)].mean())

    # ---- null draws: permute z_partner among signal rows within (slot, era) ----
    groups = signal_groups(f)
    base_zp = f.z_partner.to_numpy().copy()
    sig = f.z.abs().ge(BASE_K).fillna(False).to_numpy()
    fin = lambda a: np.sort(a[np.isfinite(a)])
    marg_ref = fin(base_zp[sig])
    n_ztrig = int(sig.sum())
    rate_ref = float(diverge[zsig.fillna(False)].mean())

    rows, checks = [], None
    for t in range(DRAWS):
        zp = base_zp.copy()
        for g in groups:
            if len(g) > 1:
                zp[g] = base_zp[g][rng.permutation(len(g))]
        f["z_partner"] = zp
        set_cross_features(f)

        if checks is None:
            checks = {
                "partner signal-row marginal preserved": bool(
                    np.array_equal(marg_ref, fin(f.z_partner.to_numpy()[sig]))),
                "z trigger untouched": bool(int(f.z.abs().ge(BASE_K).sum()) == n_ztrig),
                "diverge firing rate preserved <0.5pp": bool(
                    abs(float(f.xalign.ge(div_cut)[zsig.fillna(False)].mean()) - rate_ref) < 0.005),
            }

        vals = []
        for lab, fam, cond, side in search_arms(f):
            m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
            vals.append(m["excess_R"] if m else np.nan)
        rows.append({"pair": pair, "draw": t, "MAX": float(np.nanmax(vals))})
        if (t + 1) % 25 == 0:
            print(f"   {pair} draw {t + 1}/{DRAWS}", flush=True)

    f["z_partner"] = base_zp
    set_cross_features(f)
    return dict(pair=pair, real=real, real_best=real_best, real_max=real_max,
                red=red, within=within, corr=corr, thr=thr,
                cuts={"vei": vei_cut, "rv30": rv_cut, "div": div_cut},
                checks=checks, draws=rows)


def _g(m, *keys):
    return tuple(np.nan if m is None else m.get(k, np.nan) for k in keys)


def main():
    rng = np.random.default_rng(SEED)
    print("Pre-building partner z-banks ...", flush=True)
    zbank = {p: pair_z(p) for p in PAIRS}

    res, draws = {}, []
    for pair in PAIRS:
        print(f"Building {pair} (partner {PARTNER[pair]}) ...", flush=True)
        res[pair] = analyse(pair, zbank, rng)
        draws.extend(res[pair]["draws"])
    df = pd.DataFrame(draws)

    print("\n=== 0. Null invariant checks ===")
    for pair in PAIRS:
        for k, ok in res[pair]["checks"].items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {pair}: {k}")

    print("\n=== 1. Redundancy: is divergence just the volatility gate? ===")
    for pair in PAIRS:
        c = res[pair]["corr"]
        print(f"   {pair}: xalign~vei_atr_z {c['vei_atr_z']:+.3f}  ~rv30_pct {c['rv30_pct']:+.3f}  "
              f"~adx_z {c['adx_z']:+.3f}  | P(diverge|vol) {c['P_diverge_given_vol']:.3f} vs "
              f"marginal {c['P_diverge_marginal']:.3f}")

    print("\n=== 2. STACK: does divergence add on top of the vol gate? (delay 1) ===")
    n_stack = 0
    for pair in PAIRS:
        r = res[pair]["red"]
        vg, dv, st = _g(r["vol_gate"], "excess_R")[0], _g(r["diverge_hi10"], "excess_R")[0], \
            _g(r["vol_gate AND diverge_hi10"], "excess_R")[0]
        d_vs_vol = st - vg
        n_stack += int(d_vs_vol > 0)
        print(f"   {pair}: vol {vg:+.4f} ({_g(r['vol_gate'],'signals_per_year')[0]:.0f}/yr)  "
              f"diverge {dv:+.4f} ({_g(r['diverge_hi10'],'signals_per_year')[0]:.0f}/yr)  "
              f"AND {st:+.4f} ({_g(r['vol_gate AND diverge_hi10'],'signals_per_year')[0]:.0f}/yr)  "
              f"| stack-vs-vol {d_vs_vol:+.4f}")
    print(f"   stack beats vol gate on {n_stack}/4 pairs (need >=3)")

    print("\n=== 3. WITHIN-VOL conditional: diverge vs confirm among vol-gate signals ===")
    n_within = 0
    for pair in PAIRS:
        w = res[pair]["within"]
        hiR, hiP, hiU = _g(w["vol&div_hi"], "mean_R", "mean_pips", "implied_risk_unit_pips")
        loR, loP, loU = _g(w["vol&div_lo"], "mean_R", "mean_pips", "implied_risk_unit_pips")
        n_within += int(hiR - loR > 0)
        print(f"   {pair}: diverge meanR {hiR:+.4f} pips {hiP:+.3f} unit {hiU:.2f}  |  "
              f"confirm meanR {loR:+.4f} pips {loP:+.3f} unit {loU:.2f}  |  hi-lo {hiR - loR:+.4f} R")
    print(f"   diverge half out-reverts confirm half on {n_within}/4 pairs (need >=3)")

    print("\n=== 4. SELECTION-CORRECTED NULL: real MAX vs null MAX ===")
    verdict = {}
    for pair in PAIRS:
        nd = df.loc[df.pair.eq(pair), "MAX"].dropna()
        rmax = res[pair]["real_max"]
        frac = float((nd >= rmax).mean())
        verdict[pair] = {"real_max_excess": rmax, "real_argmax": res[pair]["real_best"],
                         "null_max_mean": float(nd.mean()), "null_max_sd": float(nd.std(ddof=1)),
                         "null_max_p95": float(nd.quantile(0.95)),
                         "frac_null_max_ge_real": frac, "passes_p05": bool(frac <= 0.05)}
        print(f"   {pair}: real max {rmax:+.4f} ({res[pair]['real_best']}) | "
              f"null max mean {nd.mean():+.4f} sd {nd.std(ddof=1):.4f} p95 {nd.quantile(0.95):+.4f} "
              f"| frac >= real {frac:.3f}  [{'PASS' if frac <= 0.05 else 'FAIL'}]")
    n_null = sum(v["passes_p05"] for v in verdict.values())

    null_pass, stack_pass = n_null >= 3, (n_stack >= 3 and n_within >= 3)
    print("\n=== 5. VERDICT ===")
    print(f"   (1) selection-corrected null: {n_null}/4  [{'PASS' if null_pass else 'FAIL'}]")
    print(f"   (2) independent of vol gate: stack {n_stack}/4 AND within-vol {n_within}/4  "
          f"[{'PASS' if stack_pass else 'FAIL'}]")
    if null_pass and stack_pass:
        overall = "REAL & INDEPENDENT cross-pair conditioner (economics still to be checked)"
    elif null_pass:
        overall = "REAL but REDUNDANT with the vol gate"
    else:
        overall = "NOT distinguishable from a selectivity dial -> NO-GO"
    print(f"   OVERALL: {overall}")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "spec": "RSI_COINTEGRATION_GATE_SPEC.md (step 2)",
                     "pairs": PAIRS, "partner": PARTNER, "draws": DRAWS, "seed": SEED,
                     "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
                     "vol_keep": VOL_KEEP, "div_keep": DIV_KEEP},
        "invariant_checks": {p: res[p]["checks"] for p in PAIRS},
        "correlations": {p: res[p]["corr"] for p in PAIRS},
        "redundancy": {p: {k: v for k, v in res[p]["red"].items()} for p in PAIRS},
        "within_vol": {p: res[p]["within"] for p in PAIRS},
        "real_search": {p: res[p]["real"] for p in PAIRS},
        "null_verdicts": verdict,
        "summary": {"null_pass_pairs": n_null, "stack_pairs": n_stack,
                    "within_pairs": n_within, "overall": overall},
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
