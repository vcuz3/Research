"""News blackout as a TAIL-RISK deployment constraint (NOT an alpha lever).

Adopted per user (2026-08-07): trades very close to a high-impact release are to be
VETOED outright, for three reasons that need no alpha model -- (1) fading a data
surprise is structurally a bad idea, (2) spread/slippage blow out around the
release, (3) genuine adverse selection. Item 18 already showed near-news
dislocations revert worst; this script does NOT re-argue that. It only QUANTIFIES
the tail-risk reduction so we can pick a sensible veto window and document it.

Two veto forms are measured because the baseline hold is 240 min (4h):
  entry-proximity : veto entries within +-W min of the nearest High-impact release
                    (the "very close to news" the user described).
  holding-overlap : veto entries whose 240-min hold would SPAN a High-impact release
                    (a calm entry 3h before a surprise still holds through it -- the
                    same tail).

Reported at the k=2.5 and k=3.0 operating points, time exit, d0: trades/yr, mean R,
hit rate, and the TAIL metrics that matter for a prop account -- worst single trade,
worst-5% mean, worst DAY (sum of per-bet R by session), and stop rate.

Causal (release timings scheduled/known ahead). Consumed history; 2024+ sealed.

Reproduce:  python -u _run_rsi_news_blackout.py
"""

from __future__ import annotations

import json

import numpy as np
import pandas as pd

from _rsi_stop_engine import (
    build_features, extract, ohlc_arrays, select_events, shift_paths, simulate,
    years_of,
)
from _run_rsi_exit_horizon import EXTRA, HORIZON, SCALE, SLIPPAGE, STOP_K
from _run_rsi_twap_anchor import add_twap_z
from _run_rsi_axis6_calendar import high_impact_times
from _run_rsi_broad_regime_sweep import PAIRS, ROOT

OUT = ROOT / "rsi_news_blackout_results.json"
KS = [2.5, 3.0]
WINDOWS = [15, 30, 60]           # +-min entry-proximity veto windows


def nearest_and_holdspan(entry_times, ev):
    """For each entry time: minutes to nearest High event (either side), and whether a
    High event falls in (entry, entry + HORIZON min]."""
    et = entry_times.astype("datetime64[m]")
    if len(ev) == 0:
        return np.full(len(et), np.inf), np.zeros(len(et), bool)
    pos = np.searchsorted(ev, et, side="left")
    to_next = np.where(pos < len(ev),
                       (ev[np.clip(pos, 0, len(ev) - 1)] - et) / np.timedelta64(1, "m"),
                       np.inf)
    since = np.where(pos > 0,
                     (et - ev[np.clip(pos - 1, 0, len(ev) - 1)]) / np.timedelta64(1, "m"),
                     np.inf)
    nearest = np.minimum(np.abs(to_next), np.abs(since))
    holds = (to_next > 0) & (to_next <= HORIZON)      # a release within the hold window
    return nearest, holds


def tail(pnl_R, sdate, years, stopped):
    ok = np.isfinite(pnl_R)
    x = pnl_R[ok]
    if len(x) < 50:
        return None
    n = len(x)
    order = np.sort(x)
    w5 = order[:max(1, int(0.05 * n))].mean()
    day = pd.Series(x).groupby(pd.Series(sdate[ok])).sum()
    return {"n_per_year": n / years, "mean_R": float(x.mean()),
            "hit": float((x > 0).mean()), "worst_trade_R": float(x.min()),
            "worst5pct_R": float(w5), "worst_day_R": float(day.min()),
            "stop_rate": float(stopped[ok].mean())}


def analyse(pair):
    f = add_twap_z(build_features(pair))
    ev = high_impact_times(pair)
    arrays = ohlc_arrays(f)
    z = f.z_twap
    res = {}
    for k in KS:
        cond = (z.le(-k) | z.ge(k)).fillna(False).to_numpy()
        side_all = np.where(z.le(-k).fillna(False), 1.0,
                            np.where(z.ge(k).fillna(False), -1.0, 0.0))
        idx = select_events(f, cond, horizon=HORIZON)
        if len(idx) < 100:
            continue
        d, paths = extract(f, arrays, idx, horizon=HORIZON, extra_bars=EXTRA)
        side = side_all[idx]
        years = years_of(d)
        pp = shift_paths(paths, 0, horizon=HORIZON)
        entry = pp["open"][:, 0]
        sgH = f.rv_30m.to_numpy()[idx] * SCALE * 1e4 * entry
        stop = STOP_K * sgH
        pnl, stopped, _ = simulate(pp, side, stop, HORIZON, SLIPPAGE)
        pnl_R = pnl / sgH

        entry_t = f.time.to_numpy()[idx]
        nearest, holds = nearest_and_holdspan(entry_t, ev)
        sd = d.sdate.values

        cells = {"base": tail(pnl_R, sd, years, stopped)}
        for w in WINDOWS:
            keep = nearest >= w
            cells[f"veto_prox_{w}"] = tail(np.where(keep, pnl_R, np.nan), sd, years, stopped)
        keep_h = ~holds
        cells["veto_holdspan"] = tail(np.where(keep_h, pnl_R, np.nan), sd, years, stopped)
        # combined: the deployable constraint (veto if very-close OR holds through)
        keep_c = (nearest >= 30) & (~holds)
        cells["veto_prox30_AND_holdspan"] = tail(np.where(keep_c, pnl_R, np.nan),
                                                 sd, years, stopped)
        res[f"{k}"] = cells
    return {"pair": pair, "by_k": res}


def main():
    rows = [analyse(p) for p in PAIRS]

    order = ["base", "veto_prox_15", "veto_prox_30", "veto_prox_60",
             "veto_holdspan", "veto_prox30_AND_holdspan"]
    for k in KS:
        print(f"\n================= k={k} (time exit, d0) =================")
        hdr = (f"{'variant':26s} {'n/yr':>6s} {'meanR':>7s} {'hit':>5s} "
               f"{'wTrade':>7s} {'w5%':>7s} {'wDay':>7s} {'stop%':>6s}")
        for r in rows:
            c = r["by_k"].get(str(k))
            if not c:
                continue
            print(f"\n--- {r['pair']} ---")
            print(hdr)
            for v in order:
                m = c.get(v)
                if not m:
                    continue
                print(f"{v:26s} {m['n_per_year']:6.0f} {m['mean_R']:+7.4f} "
                      f"{m['hit']:5.2f} {m['worst_trade_R']:+7.2f} {m['worst5pct_R']:+7.3f} "
                      f"{m['worst_day_R']:+7.2f} {m['stop_rate']:6.2f}")
        # median across pairs
        print(f"\n--- MEDIAN across pairs (k={k}) ---")
        print(hdr)
        for v in order:
            vals = [r["by_k"][str(k)][v] for r in rows
                    if str(k) in r["by_k"] and r["by_k"][str(k)].get(v)]
            if not vals:
                continue
            med = {kk: float(np.median([x[kk] for x in vals])) for kk in vals[0]}
            print(f"{v:26s} {med['n_per_year']:6.0f} {med['mean_R']:+7.4f} "
                  f"{med['hit']:5.2f} {med['worst_trade_R']:+7.2f} {med['worst5pct_R']:+7.3f} "
                  f"{med['worst_day_R']:+7.2f} {med['stop_rate']:6.2f}")

    OUT.write_text(json.dumps({
        "metadata": {"generated_at": pd.Timestamp.now(tz="UTC").isoformat(),
                     "note": "News blackout = tail-risk deployment constraint, not alpha. "
                             "High-impact release timings, entry-proximity + holding-overlap vetoes.",
                     "ks": KS, "windows_min": WINDOWS, "hold_min": HORIZON},
        "pairs": rows}, indent=2, default=float), encoding="utf-8")
    print(f"\nSaved {OUT}")


if __name__ == "__main__":
    main()
