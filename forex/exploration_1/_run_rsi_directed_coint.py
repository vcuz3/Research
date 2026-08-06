"""DIRECTED follower-reverts-to-anchor cointegration test.

Frozen in RSI_DIRECTED_COINT_SPEC.md. Assigns the FOLLOWER leg of each cointegrated block
a-priori from the early-era error-correction loading (price levels only, never the fade
P&L), then tests whether `diverge_hi` clears its donor null on the follower legs. The null
is the within-(slot, era, SIDE) donor re-pairing of z_partner (the fix from the symmetric
run), with the firing-rate invariant asserted. Direction+form are pre-specified, so keep is
the only searched dimension.

Reproduce:
    python -u _run_rsi_directed_coint.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    BASE_K,
    ERA_SPLIT,
    HORIZON,
    build_features,
    exact_roll,
    extract,
    load_minutes,
    metrics,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_z_regime_matrix import Z_GRID
from _run_rsi_cointegration_gate import PARTNER, pair_z, sig_cut
from _run_rsi_cointegration_null import set_cross_features, signal_groups
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_directed_coint_results.json"
CSV = ROOT / "rsi_directed_coint_draws.csv"

STOP_K = 2.0
SLIPPAGE = 1.0
KEEPS = (0.10, 0.20)
DRAWS = 200
SEED = 20260806
DEV_WIN = 120
BLOCKS = [("EURUSD", "GBPUSD"), ("AUDUSD", "NZDUSD")]
# a-priori liquidity anchor (exogenous): more liquid leg = anchor
LIQ_ANCHOR = {"EURUSD-GBPUSD": "EURUSD", "AUDUSD-NZDUSD": "AUDUSD"}


def error_correction_betas(a, b, win=DEV_WIN):
    """Early-era OLS slope of each leg's forward-30m log change on the cross deviation."""
    ra, rb = load_minutes(a)[["time", "close"]], load_minutes(b)[["time", "close"]]
    m = ra.merge(rb, on="time", suffixes=("_a", "_b")).sort_values("time")
    time = m.time
    la, lb = np.log(m.close_a.astype(float)), np.log(m.close_b.astype(float))
    c = pd.Series((la - lb).to_numpy(), index=m.index)
    mean_c = c.rolling(win, min_periods=win).mean()
    contig_back = time.shift(win).eq(time - pd.Timedelta(minutes=win)).to_numpy()
    dev = (c - mean_c).where(pd.Series(contig_back, index=m.index))

    fwd_ok = time.shift(-HORIZON).eq(time + pd.Timedelta(minutes=HORIZON)).to_numpy()
    fa = pd.Series((la.shift(-HORIZON) - la).to_numpy(), index=m.index).where(
        pd.Series(fwd_ok, index=m.index))
    fb = pd.Series((lb.shift(-HORIZON) - lb).to_numpy(), index=m.index).where(
        pd.Series(fwd_ok, index=m.index))
    early = time.lt(ERA_SPLIT).to_numpy()

    def beta(fwd):
        sel = early & dev.notna().to_numpy() & fwd.notna().to_numpy()
        x, y = dev.to_numpy()[sel], fwd.to_numpy()[sel]
        return float(np.cov(x, y, ddof=1)[0, 1] / np.var(x, ddof=1)), int(sel.sum())

    ba, na = beta(fa)
    bb, nb = beta(fb)
    follower = a if abs(ba) > abs(bb) else b
    return {"block": f"{a}-{b}", "beta_a": ba, "beta_b": bb, "n": na,
            "leg_a": a, "leg_b": b, "beta_follower": follower,
            "liq_anchor": LIQ_ANCHOR[f"{a}-{b}"],
            "liq_follower": b if LIQ_ANCHOR[f"{a}-{b}"] == a else a}


def light_frame(pair, zbank):
    f = build_features(pair)
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


def diverge_arms(f):
    zl, zs = f.z.le(-BASE_K), f.z.ge(BASE_K)
    out = []
    for keep in KEEPS:
        ah = f["xalign"].ge(sig_cut(f, "xalign", keep, hi=True))
        long_c, short_c = zl & ah, zs & ah
        cond = (long_c | short_c).fillna(False).to_numpy()
        side = np.where(long_c.fillna(False), 1.0,
                        np.where(short_c.fillna(False), -1.0, 0.0))
        out.append((f"diverge_hi {int(keep*100)}", cond, side))
    return out


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


def analyse_leg(pair, zbank, rng):
    f = light_frame(pair, zbank)
    arrays = ohlc_arrays(f)
    fx1, fy1 = frontier_of(f, arrays, 1)

    real = {}
    for lab, cond, side in diverge_arms(f):
        m = evaluate(f, arrays, cond, side, 1, fx1, fy1)
        real[lab] = m
    real_ex = {k: (v["excess_R"] if v else np.nan) for k, v in real.items()}
    real_max = float(np.nanmax(list(real_ex.values())))

    groups = signal_groups(f)
    base_zp = f.z_partner.to_numpy().copy()
    zsig = f.z.abs().ge(BASE_K)
    sig = zsig.fillna(False).to_numpy()
    div_cut10 = sig_cut(f, "xalign", 0.10, hi=True)
    rate_ref = float(f.xalign.ge(div_cut10)[zsig.fillna(False)].mean())
    n_ztrig = int(sig.sum())
    fin = lambda a: np.sort(a[np.isfinite(a)])
    marg_ref = fin(base_zp[sig])

    maxes, checks = [], None
    for t in range(DRAWS):
        zp = base_zp.copy()
        for g in groups:
            if len(g) > 1:
                zp[g] = base_zp[g][rng.permutation(len(g))]
        f["z_partner"] = zp
        set_cross_features(f)
        if checks is None:
            checks = {
                "partner marginal preserved": bool(np.array_equal(
                    marg_ref, fin(f.z_partner.to_numpy()[sig]))),
                "z trigger untouched": bool(int(f.z.abs().ge(BASE_K).sum()) == n_ztrig),
                "diverge rate preserved <0.5pp": bool(abs(float(
                    f.xalign.ge(div_cut10)[zsig.fillna(False)].mean()) - rate_ref) < 0.005),
            }
        vals = [evaluate(f, arrays, cond, side, 1, fx1, fy1) for _, cond, side in diverge_arms(f)]
        maxes.append(float(np.nanmax([m["excess_R"] if m else np.nan for m in vals])))
        if (t + 1) % 50 == 0:
            print(f"   {pair} draw {t + 1}/{DRAWS}", flush=True)

    f["z_partner"] = base_zp
    set_cross_features(f)
    nd = np.asarray(maxes)
    frac = float((nd >= real_max).mean())
    return {"pair": pair, "real": real, "real_max": real_max,
            "null_max_mean": float(nd.mean()), "null_max_sd": float(nd.std(ddof=1)),
            "null_max_p95": float(np.quantile(nd, 0.95)),
            "frac_null_ge_real": frac, "passes_p05": bool(frac <= 0.05),
            "checks": checks, "maxes": maxes}


def main():
    rng = np.random.default_rng(SEED)
    print("=== Follower assignment (early-era error-correction; liquidity cross-check) ===")
    betas = [error_correction_betas(a, b) for a, b in BLOCKS]
    beta_followers = set()
    for bt in betas:
        beta_followers.add(bt["beta_follower"])
        print(f"   {bt['block']}: beta_{bt['leg_a']}={bt['beta_a']:+.4f}  "
              f"beta_{bt['leg_b']}={bt['beta_b']:+.4f}  (n={bt['n']}) -> "
              f"ERROR-CORRECTING follower = {bt['beta_follower']}  | "
              f"liquidity follower = {bt['liq_follower']}")

    print("\nPre-building partner z-banks ...", flush=True)
    zbank = {p: pair_z(p) for p in PAIRS}

    res = {}
    for pair in PAIRS:
        print(f"Testing {pair} (partner {PARTNER[pair]}) ...", flush=True)
        res[pair] = analyse_leg(pair, zbank, rng)

    print("\n=== Null invariant checks ===")
    for pair in PAIRS:
        for k, ok in res[pair]["checks"].items():
            print(f"   [{'PASS' if ok else 'FAIL'}] {pair}: {k}")

    print("\n=== Directed null: diverge_hi on each leg (real MAX over keeps{10,20} vs null MAX) ===")
    for pair in PAIRS:
        r = res[pair]
        role = []
        for bt in betas:
            if pair == bt["beta_follower"]:
                role.append("BETA-follower")
            if pair == bt["liq_follower"]:
                role.append("liq-follower")
        tag = "/".join(role) if role else "anchor"
        print(f"   {pair:7s} [{tag:24s}]: real max {r['real_max']:+.4f} | "
              f"null mean {r['null_max_mean']:+.4f} sd {r['null_max_sd']:.4f} "
              f"p95 {r['null_max_p95']:+.4f} | frac>=real {r['frac_null_ge_real']:.3f}  "
              f"[{'PASS' if r['passes_p05'] else 'FAIL'}]")

    print("\n=== VERDICT ===")
    followers = sorted(beta_followers)
    fol_pass = {p: res[p]["passes_p05"] for p in followers}
    n_fol_pass = sum(fol_pass.values())
    symmetric_passers = {"EURUSD", "NZDUSD"}
    matches = beta_followers == symmetric_passers
    print(f"   Beta-followers: {followers}")
    print(f"   Beta-followers matching the symmetric passers (EURUSD,NZDUSD): {matches}")
    print(f"   Beta-followers clearing the directed null: "
          f"{[p for p in followers if fol_pass[p]]}  ({n_fol_pass}/{len(followers)})")
    directed_pass = n_fol_pass == len(followers)
    print(f"   DIRECTED HYPOTHESIS {'SUPPORTED' if directed_pass else 'NOT SUPPORTED'} "
          f"(both beta-followers must clear the null)")

    draws = pd.DataFrame([{"pair": p, "draw": i, "MAX": v}
                          for p in PAIRS for i, v in enumerate(res[p]["maxes"])])
    draws.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "spec": "RSI_DIRECTED_COINT_SPEC.md", "pairs": PAIRS,
                     "partner": PARTNER, "blocks": BLOCKS, "draws": DRAWS, "seed": SEED,
                     "keeps": list(KEEPS), "stop_R": STOP_K, "slippage_pips": SLIPPAGE},
        "follower_assignment": betas,
        "legs": {p: {k: v for k, v in res[p].items() if k != "maxes"} for p in PAIRS},
        "verdict": {"beta_followers": followers,
                    "matches_symmetric_passers": bool(matches),
                    "beta_followers_pass": {p: bool(fol_pass[p]) for p in followers},
                    "directed_supported": bool(directed_pass)},
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
