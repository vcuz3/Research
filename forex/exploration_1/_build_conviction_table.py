"""Shared per-trade table for the conviction-score (item 21) and supervised
(item 22) studies.

One row per SELECTED FADE on the promoted session-TWAP baseline:
  entry = first crossing of |z_twap| >= 1.5 (event clock, non-overlap 240m),
  outcome = per-bet R under the 240-min time exit + horizon-scaled 3R stop +
            1-pip adverse slippage, at delay 0 AND delay 1 (audited engine).

Attached to each trade are the DECISION-TIME conditioner features assembled this
session, one representative-rich set spanning every axis the project has probed:

  depth axis        absz_twap  (= |z_twap|, the baseline's own conviction lever
                    and the reference frontier everything must beat)
  vol-regime axis   rv30_pct, rv5_pct, vei_atr_z, abs_sigma_pips   (axis 2)
  cross-pair axis   xdiv (= side * partner z_twap; hi = partner did NOT confirm)  (axis 3)
  strength axis     zvel5, thrust5, decel5                          (axis 1)
  calendar axis     prox_hi (min to nearest High-impact release)    (axis 6-18)
  risk axis         vix_z   (trailing-standardized VIX)             (axis 6-20)

plus the news-blackout deployment flags (nearest High-impact release, whether the
240-min hold spans one) so both studies can be evaluated on the deployable book,
and identity columns (pair, sdate, era, session_minute, entry time).

Also writes the per-pair |z_twap| DEPTH FRONTIER (mean R vs signals/year over the
z-grid) that both studies score their selections against -- the deployment bar is
"beat deepening z at the same trade rate", not "beat zero" (LEARNINGS 2026-08-04).

Everything is causal / decision-time; the outcome is produced only by the audited
`_rsi_stop_engine`. Consumed history only; 2024+ stays sealed.

Reproduce:  python -u _build_conviction_table.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features,
    extract,
    ohlc_arrays,
    select_events,
    shift_paths,
    simulate,
    years_of,
)
from _run_rsi_exit_horizon import EXTRA, HORIZON, SCALE, SLIPPAGE, STOP_K, Z_GRID
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis2_volregime import add_vol_features
from _run_rsi_axis1_conviction import add_axis1_features
from _run_rsi_axis6_calendar import add_calendar, high_impact_times
from _run_rsi_axis6_risk import add_vix, load_vix_daily
from _run_rsi_news_blackout import nearest_and_holdspan
from _run_rsi_xpair_divergence import PARTNER
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

TRADES = ROOT / "rsi_conviction_trades.parquet"
FRONTIER = ROOT / "rsi_conviction_frontier.json"

BASE_K = 1.5
FEATURES = [
    "absz_twap", "rv30_pct", "rv5_pct", "vei_atr_z", "abs_sigma_pips",
    "xdiv", "zvel5", "thrust5", "decel5", "prox_hi", "vix_z",
]


def frontier_points(f, arrays, zt):
    """Per-pair depth frontier: (signals/year, mean_R) over |z_twap| >= k, d0 time exit."""
    rv30 = f.rv_30m.to_numpy()
    pts = []
    for k in Z_GRID:
        long_s, short_s = zt <= -k, zt >= k
        cond = (long_s | short_s)
        side_all = np.where(long_s, 1.0, np.where(short_s, -1.0, 0.0))
        idx = select_events(f, cond, horizon=HORIZON)
        if len(idx) < 200:
            continue
        d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
        pp = shift_paths(paths, 0, horizon=HORIZON)
        entry = pp["open"][:, 0]
        sgH = rv30[idx] * SCALE * 1e4 * entry
        pnl, _, _ = simulate(pp, side_all[idx], STOP_K * sgH, HORIZON, SLIPPAGE)
        r = pnl / sgH
        ok = np.isfinite(r)
        pts.append({"k": k, "signals_per_year": int(ok.sum()) / years_of(d),
                    "mean_R": float(np.nanmean(r))})
    return pts


def build_pair(pair, ztwap_by_time, ev, vix_close):
    f = add_vix(
        add_calendar(
            add_axis1_features(
                add_vol_features(add_twap_z(build_features(pair)))),
            ev),
        vix_close)
    # cross-pair divergence needs the partner's z_twap at the same timestamp
    zt = f.z_twap.to_numpy()
    side_full = -np.sign(zt)
    zp = ztwap_by_time[PARTNER[pair]].reindex(f.time.to_numpy()).to_numpy()
    f["xdiv"] = side_full * zp
    f["absz_twap"] = np.abs(zt)

    arrays = ohlc_arrays(f)
    long_s, short_s = zt <= -BASE_K, zt >= BASE_K
    cond = long_s | short_s
    side_all = np.where(long_s, 1.0, np.where(short_s, -1.0, 0.0))
    idx = select_events(f, cond, horizon=HORIZON)

    d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
    side = side_all[idx]
    rv_at = f.rv_30m.to_numpy()[idx]

    out = {"pair": pair, "time": f.time.to_numpy()[idx], "sdate": d.sdate.values,
           "era": d.era.values, "session_minute": d.session_minute.values,
           "side": side}
    for delay in (0, 1):
        pp = shift_paths(paths, delay, horizon=HORIZON)
        entry = pp["open"][:, 0]
        sgH = rv_at * SCALE * 1e4 * entry
        pnl, stopped, _ = simulate(pp, side, STOP_K * sgH, HORIZON, SLIPPAGE)
        out[f"R_d{delay}"] = pnl / sgH
        out[f"stopped_d{delay}"] = stopped
    # decision-time features at the entry index
    for col in FEATURES:
        out[col] = f[col].to_numpy()[idx]
    # news-blackout deployment flags
    nearest, holds = nearest_and_holdspan(f.time.to_numpy()[idx], ev)
    out["news_nearest_min"] = nearest
    out["news_holdspan"] = holds

    tbl = pd.DataFrame(out)
    fr = frontier_points(f, arrays, zt)
    return tbl, fr


def main():
    print("Pass 1: session-TWAP z per pair (cross-pair join) ...", flush=True)
    ztwap = {}
    for p in PAIRS:
        f = add_twap_z(build_features(p))
        ztwap[p] = pd.Series(f.z_twap.to_numpy(), index=f.time.to_numpy(), name=p)
        print(f"   {p}: {len(f):,} minutes", flush=True)

    vix_close = load_vix_daily()
    print(f"VIX daily closes: {len(vix_close):,}  "
          f"{vix_close.index.min()} .. {vix_close.index.max()}", flush=True)

    print("Pass 2: per-trade tables ...", flush=True)
    parts, frontier = [], {}
    for p in PAIRS:
        tbl, fr = build_pair(p, ztwap, high_impact_times(p), vix_close)
        parts.append(tbl)
        frontier[p] = fr
        cov = tbl[FEATURES].notna().mean().round(3).to_dict()
        print(f"   {p}: {len(tbl):,} trades | R_d0 {tbl.R_d0.mean():+.4f} "
              f"| feature coverage min {min(cov.values()):.3f}", flush=True)

    df = pd.concat(parts, ignore_index=True)
    df["pair"] = df["pair"].astype("category")
    df.to_parquet(TRADES, index=False)
    FRONTIER.write_text(json.dumps(frontier, indent=2, default=float))

    print(f"\nSaved {TRADES}  ({len(df):,} trades, {df.shape[1]} cols)")
    print(f"Saved {FRONTIER}")
    print("\n=== feature coverage (%) over all trades ===")
    print((df[FEATURES].notna().mean() * 100).round(1).to_string())
    print("\n=== per-pair trade counts / mean R_d0 / mean R_d1 ===")
    print(df.groupby("pair", observed=True).agg(
        n=("R_d0", "size"), meanR_d0=("R_d0", "mean"), meanR_d1=("R_d1", "mean"),
    ).round(4).to_string())


if __name__ == "__main__":
    main()
