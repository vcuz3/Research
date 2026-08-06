"""Is the long-horizon edge REVERSION or DRIFT? Extended horizon sweep + null.

The 240-minute hold on the abs_sigma pocket tripled gross pips. Before trusting it
we must rule out that a 4-hour hold in high-volatility states is simply booking
directional DRIFT rather than the mean-reversion signal. Discriminators, all on the
same honest engine (event clock, non-overlap, 3R stop, delay 1):

  1. Extended horizon sweep (30 .. 480 min) -- is 240 a peak or a monotone ramp
     (a ramp that never stops smells like drift/holding-for-daily-move).
  2. Long/short SYMMETRY -- if both oversold-longs and overbought-shorts pay at
     240m, it is symmetric reversion; if all the P&L is one side, it is a
     one-directional drift the balanced signal happened to straddle.
  3. Side-PERMUTATION null (re-executed on each event's own path, N draws) --
     preserves state selection, timing, path, hold, stop, cost and the long/short
     balance; destroys only the alignment between the signal's direction and the
     forward path. Real >> null => the DIRECTION carries the edge. (With a wide 3R
     stop this is close to a sign permutation, but it is genuinely re-executed on
     real paths, not a P&L sign-multiply -- stated for RULES-16 transparency.)
  4. FOLLOW mirror (opposite side) and ALWAYS-LONG drift control -- reversion vs
     momentum vs unconditional drift. (Follow is near-algebraic at a timeout exit;
     read it with the long/short split, not alone.)

Reproduce:
    python -u _run_horizon_null.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _cost_model import CostParams
from _rsi_stop_engine import (
    build_features,
    extract,
    metrics,
    ohlc_arrays,
    select_events,
    session_cluster_t,
    shift_paths,
    simulate,
)
from _run_horizon_bracket import STOP_K, SLIPPAGE, POCKET_KEEP, pocket, cost_of
from _run_regime_pocket_economics import add_pocket_features
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "horizon_null_results.json"
CSV = ROOT / "horizon_null.csv"

HORIZONS = [30, 60, 120, 180, 240, 300, 360, 480]
NULL_HORIZONS = [240, 360]
NDRAW = 300
SEED = 12345
BASE = CostParams(scenario="base")
NOCOMM = CostParams(scenario="base", include_commission=False)


def mean_R(pnl, sg):
    ok = np.isfinite(pnl)
    if ok.sum() < 100:
        return np.nan
    return float(np.mean(pnl[ok] / sg[ok]))


def analyse(pair):
    f = add_pocket_features(build_features(pair))
    arrays = ohlc_arrays(f)
    cond, side_all = pocket(f)
    rng = np.random.default_rng(SEED)
    sweep, nullrows = [], []

    for H in HORIZONS:
        idx = select_events(f, cond, horizon=H)
        if len(idx) < 150:
            continue
        d, paths = extract(f, arrays, idx, horizon=H)
        side = side_all[idx]
        years = d.sdate.nunique() / 252
        pp = shift_paths(paths, 1, horizon=H)      # delay 1 (honest)
        sg = (d.rv_30m * 1e4 * pp["open"][:, 0]).to_numpy()

        pnl, st, _ = simulate(pp, side, STOP_K * sg, H, SLIPPAGE)
        m = metrics(pnl, sg, d.sdate.values, years, st)
        cost = cost_of(pair, d, None, sg, 1, BASE)
        cost_nc = cost_of(pair, d, None, sg, 1, NOCOMM)
        long_m = side > 0
        row = {
            "pair": pair, "horizon": H, "signals_per_year": m["signals_per_year"],
            "gross_pips": m["mean_pips"], "gross_R": m["mean_R"],
            "risk_unit": m["implied_risk_unit_pips"], "gross_t": m["cluster_t"],
            "stopped_frac": m.get("stopped_frac", np.nan),
            "net_base_R": mean_R(pnl - cost, sg),
            "net_nocomm_R": mean_R(pnl - cost_nc, sg),
            "long_gross": float(np.nanmean(pnl[long_m])) if long_m.any() else np.nan,
            "short_gross": float(np.nanmean(pnl[~long_m])) if (~long_m).any() else np.nan,
            "long_R": mean_R(pnl[long_m], sg[long_m]) if long_m.any() else np.nan,
            "short_R": mean_R(pnl[~long_m], sg[~long_m]) if (~long_m).any() else np.nan,
            "n_long": int(long_m.sum()), "n_short": int((~long_m).sum()),
        }
        sweep.append(row)

        if H in NULL_HORIZONS:
            real_R = mean_R(pnl, sg)
            # side-permutation null: shuffle side across events, re-execute on paths
            draws = np.empty(NDRAW)
            for j in range(NDRAW):
                perm = rng.permutation(side)
                pj, _, _ = simulate(pp, perm, STOP_K * sg, H, SLIPPAGE)
                draws[j] = mean_R(pj, sg)
            frac = float(np.mean(draws >= real_R))
            # follow (opposite side) and always-long drift control, re-executed
            pf, _, _ = simulate(pp, -side, STOP_K * sg, H, SLIPPAGE)
            pl, _, _ = simulate(pp, np.ones_like(side), STOP_K * sg, H, SLIPPAGE)
            nullrows.append({
                "pair": pair, "horizon": H, "real_R": real_R,
                "null_mean_R": float(np.mean(draws)), "null_sd_R": float(np.std(draws)),
                "null_p_ge": frac, "follow_R": mean_R(pf, sg),
                "always_long_R": mean_R(pl, sg),
                "real_cluster_t": float(session_cluster_t(
                    pd.Series(pnl[np.isfinite(pnl)]),
                    pd.Series(d.sdate.values)[np.isfinite(pnl)])),
            })
    return sweep, nullrows


def main():
    sweep, nullrows = [], []
    for pair in PAIRS:
        print(f"Building {pair} ...", flush=True)
        s, n = analyse(pair)
        sweep.extend(s)
        nullrows.extend(n)
    S = pd.DataFrame(sweep)
    N = pd.DataFrame(nullrows)

    print("\n=== Extended horizon sweep, abs_sigma pocket, delay 1 (median across pairs) ===")
    print(S.groupby("horizon").agg(
        per_year=("signals_per_year", "median"),
        gross_pips=("gross_pips", "median"), gross_R=("gross_R", "median"),
        net_base_R=("net_base_R", "median"), net_nocomm_R=("net_nocomm_R", "median"),
        long_R=("long_R", "median"), short_R=("short_R", "median"),
        stopped=("stopped_frac", "median"),
    ).round(4).to_string())

    print("\n=== Gross pips by horizon per pair (delay 1) ===")
    print(S.pivot_table(index="horizon", columns="pair", values="gross_pips").round(3).to_string())

    print("\n=== LONG vs SHORT gross pips at 240m per pair (symmetry = reversion) ===")
    s240 = S[S.horizon == 240]
    print(s240.set_index("pair")[["long_gross", "short_gross", "n_long", "n_short"]].round(3).to_string())

    print("\n=== SIDE-PERMUTATION NULL + follow/drift controls ===")
    print("   reversion real: real_R > 0 AND null_p_ge small AND follow_R < 0")
    for _, r in N.iterrows():
        print(f"   {r.pair} H{int(r.horizon)}: real {r.real_R:+.4f} R (t {r.real_cluster_t:+.2f}) | "
              f"null {r.null_mean_R:+.4f}+/-{r.null_sd_R:.4f} p>={r.null_p_ge:.3f} | "
              f"follow {r.follow_R:+.4f} | always-long {r.always_long_R:+.4f}")
    n240 = N[N.horizon == 240]
    print(f"\n   240m: pairs with real>0 and null p<=0.05: "
          f"{int(((n240.real_R > 0) & (n240.null_p_ge <= 0.05)).sum())}/4; "
          f"pairs with follow_R<0 (reversion direction): {int((n240.follow_R < 0).sum())}/4")

    S.to_csv(CSV, index=False)
    OUT.write_text(json.dumps({
        "metadata": {
            "generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
            "pairs": PAIRS, "stop_R": STOP_K, "slippage_pips": SLIPPAGE,
            "pocket_keep": POCKET_KEEP, "horizons": HORIZONS,
            "null_horizons": NULL_HORIZONS, "ndraw": NDRAW, "seed": SEED,
            "null": "side permutation, re-executed on real paths, preserves L/S balance",
        },
        "sweep": json.loads(S.to_json(orient="records")),
        "null": json.loads(N.to_json(orient="records")),
    }, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
