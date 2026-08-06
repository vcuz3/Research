"""Confirmatory test of the reversed high-ADX conditioner (post-hoc direction).

Frozen in RSI_ADX_REVERSAL_SPEC.md. Two tests decide whether the reversed high-ADX
signal from RSI_EFFICIENCY_GATE_REPORT.md is a real, independent lever:

  1. SELECTION-CORRECTED CLAIM-MATCHED NULL. The direction (HIGH not LOW) and the arm
     (adx not ker) were BOTH selected, so the search space is the whole efficiency
     screen. Joint donor re-pairing of (ker, ker_z, adx, adx_z, htf_slope) within each
     (session minute, era) cell destroys only the contemporaneous link between the
     efficiency state and this decision's forward return; paths, |z| trigger, event
     clock, non-overlap, stop, and every feature marginal/joint-dependence are preserved
     (all asserted in code). Compare the REAL MAX excess over the search against the NULL
     MAX distribution (rule 17).

  2. REDUNDANCY vs the confirmed volatility gate. ADX is built from True Range, so
     "high ADX reverts better" may be "high volatility reverts better", which the project
     already has (+0.0137 R). Tested three ways: correlation of adx_z with the vol-gate
     features; whether high-ADX STACKS on the vol gate (frontier-excess of the AND arm
     minus the vol gate alone); and a within-vol conditional split (among vol-gate
     signals, does the high-adx half out-revert the low-adx half?).

Reproduce with:
    python -u _run_rsi_adx_reversal.py
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
from _run_rsi_efficiency_gate import build_arms, high_cut, low_cut
from _run_rsi_z_regime_matrix import Z_GRID, add_extra_features, early_cut
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_adx_reversal_results.json"
CSV = ROOT / "rsi_adx_reversal_draws.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
VOL_KEEP = 0.40
ADX_KEEP = 0.20
DRAWS = 100
SEED = 20260805
FEATS = ["ker", "ker_z", "adx", "adx_z", "htf_slope"]


def build_frame(pair):
    """build_features + RV percentiles (vol gate) + efficiency features, one frame."""
    return add_efficiency_features(add_extra_features(build_features(pair)))


def frontier_of(f, arrays, delay):
    """(log signals/year, mean R) for the |z| >= k sweep at a given entry delay."""
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
    """Event-clock arm -> metrics dict with frontier excess, or None if too thin."""
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
    """A |z| >= 1.5 fade restricted to `mask` -> (cond, side)."""
    zl, zs = f.z.le(-BASE_K) & mask, f.z.ge(BASE_K) & mask
    cond = (zl | zs).fillna(False).to_numpy()
    side = np.where(zl.fillna(False), 1.0, np.where(zs.fillna(False), -1.0, 0.0))
    return cond, side


def search_arms(f):
    """Non-frontier efficiency arms only (the search the argmax was drawn from)."""
    return [(lab, fam, cond, side) for lab, fam, cond, side in build_arms(f)
            if fam != "frontier |z|"]


def group_positions(f):
    """Index arrays for the (session minute, era) donor cells."""
    key = f.session_minute.astype(np.int32).to_numpy() * 2 + f.era.eq("late").to_numpy()
    order = np.argsort(key, kind="stable")
    ks = key[order]
    bounds = np.flatnonzero(np.r_[True, ks[1:] != ks[:-1], True])
    return [order[bounds[i]:bounds[i + 1]] for i in range(len(bounds) - 1)]


def analyse(pair, rng):
    f = build_frame(pair)
    arrays = ohlc_arrays(f)
    fx1, fy1 = frontier_of(f, arrays, 1)
    fx0, fy0 = frontier_of(f, arrays, 0)

    # ---- real efficiency search: excess for every non-frontier arm, real MAX ----
    real = {}
    for lab, fam, cond, side in search_arms(f):
        m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
        real[lab] = {"family": fam, **m} if m else {"family": fam, "excess_R": np.nan}
    real_ex = {k: v["excess_R"] for k, v in real.items()}
    real_best = max((k for k in real_ex if np.isfinite(real_ex[k])),
                    key=lambda k: real_ex[k])
    real_max = real_ex[real_best]

    # ---- redundancy vs the confirmed volatility gate ----
    vei_cut = early_cut(f, "vei_atr_z", VOL_KEEP)
    rv_cut = early_cut(f, "rv30_pct", VOL_KEEP)
    adx_cut = high_cut(f, "adx_z", ADX_KEEP)
    vol_gate = f.vei_atr_z.ge(vei_cut) & f.rv30_pct.ge(rv_cut)
    high_adx = f.adx_z.ge(adx_cut)

    red = {}
    for lab, mask in [("vol_gate", vol_gate),
                      ("high_adx20", high_adx),
                      ("vol_gate AND high_adx20", vol_gate & high_adx)]:
        cond, side = mask_arm(f, mask)
        for delay, fx, fy in [(1, fx1, fy1), (0, fx0, fy0)]:
            m = evaluate(f, arrays, cond, side, delay, fx, fy)
            red[(lab, delay)] = m

    # within-vol conditional split: high vs low adx_z among vol-gate z1.5 signals,
    # split at the EARLY-era median of adx_z in that population (causal)
    zsig = f.z.abs().ge(BASE_K)
    pop = zsig & vol_gate
    thr = float(f.loc[f.era.eq("early") & pop, "adx_z"].median())
    within = {}
    for lab, mask in [("vol&adx_hi", pop & f.adx_z.ge(thr)),
                      ("vol&adx_lo", pop & f.adx_z.lt(thr))]:
        cond, side = mask_arm(f, mask)
        m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
        within[lab] = m

    # feature correlations among the traded (z1.5) population
    zrows = f.loc[zsig.fillna(False)]
    corr = {
        "adx_z_vs_vei_atr_z": float(zrows.adx_z.corr(zrows.vei_atr_z, method="spearman")),
        "adx_z_vs_rv30_pct": float(zrows.adx_z.corr(zrows.rv30_pct, method="spearman")),
        "adx_z_vs_ker_z": float(zrows.adx_z.corr(zrows.ker_z, method="spearman")),
        "P_high_adx_given_vol": float(high_adx[pop].mean()),
        "P_high_adx_marginal": float(high_adx[zsig.fillna(False)].mean()),
    }

    # ---- coverage among base signals (rule 9a) ----
    idx0 = select_events(f, zsig.fillna(False).to_numpy())
    dd = f.iloc[idx0]
    cov = {era: {"n": int(dd.era.eq(era).sum()),
                 "adx_defined": float(dd.loc[dd.era.eq(era), "adx_z"].notna().mean())}
           for era in ["early", "late"]}

    # ---- null draws ----
    groups = group_positions(f)
    base_vals = {c: f[c].to_numpy().copy() for c in FEATS}
    n = len(f)
    corr_ref = float(pd.Series(base_vals["adx_z"]).corr(
        pd.Series(base_vals["ker_z"]), method="spearman"))
    n_ztrig = int(zsig.sum())
    rate_real = float(high_adx.mean())
    rows, checks = [], None
    for t in range(DRAWS):
        perm = np.arange(n)
        for pos in groups:
            if len(pos) > 1:
                perm[pos] = pos[rng.permutation(len(pos))]
        for c in FEATS:
            f[c] = base_vals[c][perm]          # one joint permutation for all five

        if checks is None:
            fin = lambda a: np.sort(a[np.isfinite(a)])
            checks = {
                "marginals preserved exactly": bool(all(
                    np.array_equal(fin(base_vals[c]), fin(f[c].to_numpy())) for c in FEATS)),
                "joint dependence (adx_z,ker_z) preserved": bool(abs(float(
                    f.adx_z.corr(f.ker_z, method="spearman")) - corr_ref) < 1e-9),
                "high_adx firing rate preserved to <0.5pp": bool(
                    abs(float(f.adx_z.ge(adx_cut).mean()) - rate_real) < 0.005),
                "z trigger untouched": bool(int(f.z.abs().ge(BASE_K).sum()) == n_ztrig),
            }

        vals = []
        for lab, fam, cond, side in search_arms(f):
            m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
            vals.append(m["excess_R"] if m else np.nan)
        rows.append({"pair": pair, "draw": t, "MAX": float(np.nanmax(vals))})
        if (t + 1) % 25 == 0:
            print(f"   {pair} draw {t + 1}/{DRAWS}", flush=True)

    for c in FEATS:
        f[c] = base_vals[c]
    return dict(pair=pair, real=real, real_best=real_best, real_max=real_max,
                red=red, within=within, corr=corr, cov=cov, thr=thr,
                cuts={"vei": vei_cut, "rv30": rv_cut, "adx_hi": adx_cut},
                checks=checks, draws=rows)


def _r(m, *keys):
    return tuple(np.nan if m is None else m.get(k, np.nan) for k in keys)


def main():
    rng = np.random.default_rng(SEED)
    res = {}
    draws = []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        res[pair] = analyse(pair, rng)
        draws.extend(res[pair]["draws"])
    df = pd.DataFrame(draws)

    print("\n=== 0. Null invariant checks (rule 17) ===")
    for pair in PAIRS:
        for k, ok in res[pair]["checks"].items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {pair}: {k}")

    print("\n=== 0b. Feature coverage among base |z|>=1.5 signals (rule 9a) ===")
    for pair in PAIRS:
        for era, c in res[pair]["cov"].items():
            print(f"   {pair} {era:5s}: n={c['n']:6d}  adx_z defined {c['adx_defined']:.3f}")

    print("\n=== 1. Redundancy: is high-ADX just the volatility gate? ===")
    print("   Spearman among traded |z|>=1.5 rows, and firing overlap:")
    for pair in PAIRS:
        c = res[pair]["corr"]
        print(f"   {pair}: adx_z~vei_atr_z {c['adx_z_vs_vei_atr_z']:+.3f}  "
              f"adx_z~rv30_pct {c['adx_z_vs_rv30_pct']:+.3f}  "
              f"adx_z~ker_z {c['adx_z_vs_ker_z']:+.3f}  | "
              f"P(high_adx|vol) {c['P_high_adx_given_vol']:.3f} vs "
              f"marginal {c['P_high_adx_marginal']:.3f}")

    print("\n=== 2. STACK: does high-ADX add on top of the vol gate? (delay 1) ===")
    stack_ok = {}
    for pair in PAIRS:
        r = res[pair]["red"]
        vg = r[("vol_gate", 1)]
        ha = r[("high_adx20", 1)]
        st = r[("vol_gate AND high_adx20", 1)]
        vg_e, ha_e, st_e = _r(vg, "excess_R")[0], _r(ha, "excess_R")[0], _r(st, "excess_R")[0]
        d_vs_vol = st_e - vg_e
        d_vs_adx = st_e - ha_e
        stack_ok[pair] = d_vs_vol
        print(f"   {pair}: vol_gate {vg_e:+.4f} ({_r(vg,'signals_per_year')[0]:.0f}/yr)  "
              f"high_adx {ha_e:+.4f} ({_r(ha,'signals_per_year')[0]:.0f}/yr)  "
              f"AND {st_e:+.4f} ({_r(st,'signals_per_year')[0]:.0f}/yr)  "
              f"| stack-vs-vol {d_vs_vol:+.4f}  stack-vs-adx {d_vs_adx:+.4f}")
    n_stack = int(sum(v > 0 for v in stack_ok.values()))
    print(f"   stack beats vol gate on {n_stack}/4 pairs (need >=3)")

    print("\n=== 3. WITHIN-VOL conditional: high vs low ADX among vol-gate signals ===")
    within_ok = {}
    for pair in PAIRS:
        w = res[pair]["within"]
        hi, lo = w["vol&adx_hi"], w["vol&adx_lo"]
        hiR, hiP, hiU = _r(hi, "mean_R", "mean_pips", "implied_risk_unit_pips")
        loR, loP, loU = _r(lo, "mean_R", "mean_pips", "implied_risk_unit_pips")
        within_ok[pair] = hiR - loR
        print(f"   {pair}: adx_hi meanR {hiR:+.4f} pips {hiP:+.3f} unit {hiU:.2f}  |  "
              f"adx_lo meanR {loR:+.4f} pips {loP:+.3f} unit {loU:.2f}  |  "
              f"hi-lo {hiR - loR:+.4f} R")
    n_within = int(sum(v > 0 for v in within_ok.values()))
    print(f"   high-ADX half out-reverts low-ADX half on {n_within}/4 pairs (need >=3)")

    print("\n=== 4. SELECTION-CORRECTED NULL: real MAX vs null MAX (whole search) ===")
    verdict = {}
    for pair in PAIRS:
        nd = df.loc[df.pair.eq(pair), "MAX"].dropna()
        rmax = res[pair]["real_max"]
        frac = float((nd >= rmax).mean())
        verdict[pair] = {
            "real_max_excess": rmax, "real_argmax": res[pair]["real_best"],
            "null_max_mean": float(nd.mean()), "null_max_sd": float(nd.std(ddof=1)),
            "null_max_p95": float(nd.quantile(0.95)),
            "frac_null_max_ge_real": frac, "passes_p05": bool(frac <= 0.05),
        }
        print(f"   {pair}: real max {rmax:+.4f} ({res[pair]['real_best']}) | "
              f"null max mean {nd.mean():+.4f} sd {nd.std(ddof=1):.4f} p95 {nd.quantile(0.95):+.4f} "
              f"| frac >= real {frac:.3f}  [{'PASS' if frac <= 0.05 else 'FAIL'}]")
    n_null = sum(v["passes_p05"] for v in verdict.values())

    null_pass = n_null >= 3
    stack_pass = (n_stack >= 3) and (n_within >= 3)
    print("\n=== 5. VERDICT ===")
    print(f"   (1) selection-corrected null: {n_null}/4 pairs  "
          f"[{'PASS' if null_pass else 'FAIL'}]")
    print(f"   (2) not redundant with vol gate: stack {n_stack}/4 AND within-vol "
          f"{n_within}/4  [{'PASS' if stack_pass else 'FAIL'}]")
    if null_pass and stack_pass:
        overall = "REAL & INDEPENDENT -> preregister a single candidate (economics still weak)"
    elif null_pass and not stack_pass:
        overall = "REAL but REDUNDANT with the volatility gate -> do not adopt as a separate lever"
    else:
        overall = "NOT distinguishable from a selectivity dial -> NO-GO"
    print(f"   OVERALL: {overall}")

    df.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "spec": "RSI_ADX_REVERSAL_SPEC.md",
            "pairs": PAIRS, "draws": DRAWS, "seed": SEED,
            "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "vol_keep": VOL_KEEP, "adx_keep": ADX_KEEP,
            "provenance": "post-hoc direction from RSI_EFFICIENCY_GATE_REPORT.md (rule 26)",
        },
        "invariant_checks": {p: res[p]["checks"] for p in PAIRS},
        "coverage": {p: res[p]["cov"] for p in PAIRS},
        "correlations": {p: res[p]["corr"] for p in PAIRS},
        "cutpoints": {p: res[p]["cuts"] for p in PAIRS},
        "redundancy": {p: {f"{lab}|d{dl}": (None if m is None else m)
                           for (lab, dl), m in res[p]["red"].items()} for p in PAIRS},
        "within_vol": {p: res[p]["within"] for p in PAIRS},
        "real_search": {p: res[p]["real"] for p in PAIRS},
        "null_verdicts": verdict,
        "summary": {"null_pass_pairs": n_null, "stack_pairs": n_stack,
                    "within_pairs": n_within, "overall": overall},
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
