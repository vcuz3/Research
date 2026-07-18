"""
Forensic replication review. Isolates each implementation choice and measures its
effect on the headline, then reports the closest-faithful replication and residual
gaps vs Quantitativo.

Choices tested:
  1. decision clock:  hh30  = 10:00,10:30,...,15:30  (tod 600..930)
                      concretum = min_from_open%30==0 (09:30=min1) = 09:59,10:29,
                                  ...,15:59  (tod 599,629,...,959)
  2. vwap entry gate: OFF (close vs band only) vs ON (also require close vs VWAP)
  3. cost:            0 / 0.25 / 0.50 / 1.0 tick per SIDE (round trip = 2x)
  4. sizing:          (lookback, target_vol, cap, realized-vol lag, rounding)

All fills are honest next-bar-open. Effect size is per-trade net; the headline is
the vol-target-compounded CAGR/Sharpe/maxDD.
"""
from __future__ import annotations

import itertools
import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, daily_returns, POINT_VALUE, TICK
from ..core.engine import run

CLOCKS = {
    "hh30": [h * 60 + m for h in range(10, 16) for m in (0, 30)],       # 600..930
    "concretum": [570 + k - 1 for k in range(30, 391, 30)],            # 599,629,...,959
}


def fees_pt(inst):
    return 2.25 / POINT_VALUE[inst]


def sizing(inst, bars, trades, cost_pt, target=0.03, cap=8.0,
           vol_lag=1, rounding="floor"):
    """Vol-target compounding. Returns dict of headline metrics + daily return series."""
    pv = POINT_VALUE[inst]
    t = trades.copy()
    t["net"] = t["points"] - 2.0 * cost_pt
    sess = bars["date"].drop_duplicates().sort_values().reset_index(drop=True)
    pts = t.groupby("date")["net"].sum().reindex(sess).fillna(0.0)
    dret = daily_returns(bars).reindex(sess)
    opx = bars[bars["tod"] == 570].set_index("date")["open"].reindex(sess)
    # realized vol from daily returns; vol_lag=1 -> through t-1, =2 -> excludes latest
    realized = dret.shift(vol_lag).rolling(14, min_periods=14).std()
    mult = np.minimum(cap, target / realized)
    equity = 100000.0
    rr = []
    for d in sess:
        m = mult.get(d, np.nan); px = opx.get(d, np.nan)
        if not np.isfinite(m) or not np.isfinite(px) or px <= 0:
            rr.append(0.0); continue
        raw = equity * m / (px * pv)
        c = np.floor(raw) if rounding == "floor" else np.round(raw)
        pnl = c * pts.get(d, 0.0) * pv
        rr.append(pnl / equity if equity > 0 else 0.0); equity += pnl
    rr = pd.Series(rr, index=sess)
    act_mask = realized.reindex(sess).notna()
    act = rr[act_mask]
    n_yr = (sess.iloc[-1] - sess.iloc[0]).days / 365.25
    cagr = (equity / 100000.0) ** (1 / n_yr) - 1 if equity > 0 else -1
    sh = act.mean() / act.std() * np.sqrt(252) if act.std() > 0 else 0.0
    eqc = (1 + rr).cumprod(); mdd = float(((eqc - eqc.cummax()) / eqc.cummax()).min())
    annvol = act.std() * np.sqrt(252)
    return dict(cagr=cagr, sharpe=sh, maxdd=mdd, annvol=annvol,
                n_trades=len(t), pt_net=float(t["net"].mean()), ret=rr)


def per_trade_t(inst, trades, cost_pt):
    t = trades.copy(); t["net"] = t["points"] - 2.0 * cost_pt
    day = t.groupby("date")["net"].sum() * POINT_VALUE[inst]
    m = day.mean(); se = day.std(ddof=1) / np.sqrt(len(day))
    return m, (m / se if se > 0 else 0.0)


def hl(m):
    return f"CAGR={m['cagr']:>+6.1%} Sh={m['sharpe']:>5.2f} DD={m['maxdd']:>+6.1%} n={m['n_trades']:>4d}"


def load_all():
    d = {}
    for inst in ("NQ", "ES"):
        bars = load_rth(inst)
        d[inst] = dict(bars=bars,
                       bands={14: noise_bands(bars, 14), 90: noise_bands(bars, 90)})
    return d


def main():
    D = load_all()

    # ---------- 1+2. ABLATION: clock x vwap-gate (lb90, 0.25tick, 3%/8x) ----------
    print("=" * 78)
    print("ABLATION: decision clock x VWAP-entry-gate  (lb=90, 0.25tick/side, 3%/8x)")
    print("=" * 78)
    for inst in ("NQ", "ES"):
        bars = D[inst]["bars"]; b90 = D[inst]["bands"][90]
        cost = fees_pt(inst) + 0.25 * TICK[inst]
        print(f"\n{inst}:")
        for clock, rv in itertools.product(("hh30", "concretum"), (False, True)):
            tr = run(bars, b90, decision_tods=CLOCKS[clock], require_vwap=rv)
            m = sizing(inst, bars, tr, cost)
            mm, tt = per_trade_t(inst, tr, cost)
            tag = f"{clock:10s} vwap={'ON ' if rv else 'OFF'}"
            print(f"  {tag}  net={m['pt_net']:>+6.3f}pt day$t={tt:>+5.2f}  {hl(m)}")

    # ---------- 3. COST GRID on faithful config (concretum + vwap ON) ----------
    print("\n" + "=" * 78)
    print("COST SENSITIVITY  (faithful: concretum clock + VWAP gate ON, lb90, 3%/8x)")
    print("=" * 78)
    for inst in ("NQ", "ES"):
        bars = D[inst]["bars"]; b90 = D[inst]["bands"][90]
        tr = run(bars, b90, decision_tods=CLOCKS["concretum"], require_vwap=True)
        print(f"\n{inst}:")
        for slip in (0.0, 0.25, 0.50, 1.0):
            cost = fees_pt(inst) + slip * TICK[inst]
            m = sizing(inst, bars, tr, cost)
            mm, tt = per_trade_t(inst, tr, cost)
            print(f"  slip={slip:>4.2f}tick/side (cost={cost:.3f}pt) "
                  f"net={m['pt_net']:>+6.3f}pt day$t={tt:>+5.2f}  {hl(m)}")

    # ---------- 4. SIZING GRID (faithful config, 0.25tick) ----------
    print("\n" + "=" * 78)
    print("SIZING SENSITIVITY  (faithful config, 0.25tick/side)")
    print("=" * 78)
    for inst in ("NQ", "ES"):
        bars = D[inst]["bars"]; cost = fees_pt(inst) + 0.25 * TICK[inst]
        print(f"\n{inst}:")
        for lb, tv, cap in ((14, 0.02, 4.0), (90, 0.03, 8.0)):
            tr = run(bars, D[inst]["bands"][lb],
                     decision_tods=CLOCKS["concretum"], require_vwap=True)
            for lag in (1, 2):
                for rnd in ("floor", "round"):
                    m = sizing(inst, bars, tr, cost, target=tv, cap=cap,
                               vol_lag=lag, rounding=rnd)
                    print(f"  lb={lb:>2d} tv={tv:.0%} cap={cap:.0f}x "
                          f"vlag={lag} {rnd:5s}  {hl(m)}")

    # ---------- 5+6. HEADLINE CASES + PORTFOLIO ----------
    print("\n" + "=" * 78)
    print("HEADLINE CASES vs Quantitativo (faithful config, 0.25tick, floor, vlag=1)")
    print("=" * 78)
    rets = {}
    cases = [("ES", 14, 0.02, 4.0), ("ES", 90, 0.03, 8.0), ("NQ", 90, 0.03, 8.0)]
    for inst, lb, tv, cap in cases:
        bars = D[inst]["bars"]; cost = fees_pt(inst) + 0.25 * TICK[inst]
        tr = run(bars, D[inst]["bands"][lb],
                 decision_tods=CLOCKS["concretum"], require_vwap=True)
        m = sizing(inst, bars, tr, cost, target=tv, cap=cap)
        rets[f"{inst}_{lb}_{int(tv*100)}_{int(cap)}"] = m["ret"]
        print(f"  {inst} lb{lb} tv{tv:.0%} cap{cap:.0f}x   {hl(m)}  annVol={m['annvol']:.1%}")
    print("  Quantitativo:  ES 16.8%/1.25/-21% | NQ 24.3%/1.67/-24% | Port 22.4%/1.57/-15%")

    # Portfolio: 50% NQ strat + 25% ES strat + 25% long NQ
    nq_long = daily_returns(D["NQ"]["bars"])
    nq_s = rets["NQ_90_3_8"]; es_s = rets["ES_90_3_8"]
    idx = nq_s.index.union(es_s.index).union(nq_long.index)
    port = (0.50 * nq_s.reindex(idx).fillna(0) +
            0.25 * es_s.reindex(idx).fillna(0) +
            0.25 * nq_long.reindex(idx).fillna(0))
    # metrics on the common active window (from first ES sizing date)
    start = es_s.index.min()
    p = port[port.index >= start]
    n_yr = (p.index.max() - p.index.min()).days / 365.25
    eqc = (1 + p).cumprod()
    cagr = eqc.iloc[-1] ** (1 / n_yr) - 1
    sh = p.mean() / p.std() * np.sqrt(252)
    mdd = ((eqc - eqc.cummax()) / eqc.cummax()).min()
    print(f"\n  PORTFOLIO 50%NQ+25%ES+25%longNQ: "
          f"CAGR={cagr:+.1%} Sharpe={sh:.2f} maxDD={mdd:+.1%} (vs 22.4%/1.57/-15%)")


if __name__ == "__main__":
    main()
