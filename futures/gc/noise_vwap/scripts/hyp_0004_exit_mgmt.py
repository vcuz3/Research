"""
HYP-0004 / EXP-0006 — Exit-system transfer to GC: partial-TP + looser clock.

Single-variable EXIT changes on top of the frozen EXP-0005 baseline (RTH, VWAP
gate, lookback=90, k=1.0, 30-min Concretum decision clock, decision-clock band/VWAP
stop, honest next-open fills). Entries are IDENTICAL across every variant, so this
is a clean apples-to-apples exit comparison (rule 23: tp_atr=0 + 30m clock +
decision stop reproduces the baseline to the digit).

Variants:
  * PARTIAL-TP + RUNNER (30m clock): once price runs tp_atr ATR in favour, bank
    tp_frac of the position at the NEXT open; the runner keeps the baseline
    decision-clock band/VWAP stop. Grid tp_atr x tp_frac.
  * LOOSE CLOCK: 60-min decision/stop clock, no TP (EXP-0004's looseness lesson,
    tested toward the loose side).
  * COMBINED: the best-screening TP config on the 60-min clock.

Why (HYP-0004): GC has NO intraday drift and is noise-dominated; the NQ partial-TP
survivor monetizes intraday MEAN-REVERSION after a ~1-ATR extension (Null-C sign
flips vs noise), which gold should hand back at least as readily as NQ. This is the
mechanistic inverse of EXP-0004's continuous-stop inversion (that tightened the
runner and clipped winners; this TAKES the give-back).

Fills honest (rule 1/2/3): the partial is a momentum-confirmed close beyond +tp_atr,
filled at the NEXT open (conservative vs an intrabar limit); reported as the
next_open-vs-signal_close artifact per TP config. Cost: metrics.summarize charges
2*cost/side per trade row; a partial trade transacts enter(1)+partial(f)+runner(1-f)
= 2 sides of contract volume, i.e. the SAME per-contract cost as a normal round trip
(fractional lots are realised on MGC micros, per project convention).

Primary metric: per-day-clustered NET daily Sharpe @0.50 tick/side (+ net day-$ t);
gross reported alongside (rule 20). A variant clears the screen only if it beats the
frozen baseline net Sharpe by >= +0.05 WITHOUT inflating gross. Null-C is gated on a
positive real pass (gate-nullc-on-success-metric).

Usage:
  python -m futures.gc.noise_vwap.scripts.hyp_0004_exit_mgmt real
  python -m futures.gc.noise_vwap.scripts.hyp_0004_exit_mgmt null 30 <cfg> [<cfg> ...]
"""
from __future__ import annotations

import os
import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core import engine as E1
from ..core import nulls_session as NS
from ..core.metrics import summarize, fmt
from ..core.data import load_rth as load_rth_core, noise_bands as noise_bands_core

INST = "GC"
LOOKBACK = 90
FEES_PT = 2.25 / S.POINT_VALUE[INST]
TICK = S.TICK[INST]
COST_GRID = {
    "0.25tick": FEES_PT + 0.25 * TICK,
    "0.50tick": FEES_PT + 0.50 * TICK,
    "1.0tick": FEES_PT + 1.0 * TICK,
}
PRIMARY = "0.50tick"
ANN = 252.0
OUTDIR = "futures/gc/noise_vwap/artifacts/runs/EXP-0006"

# label -> (clock period minutes, exit kwargs on top of the decision-clock baseline)
CFGS = {
    "baseline_30":   (30, dict()),
    "tp0.75_50":     (30, dict(tp_atr=0.75, tp_frac=0.50)),
    "tp0.75_67":     (30, dict(tp_atr=0.75, tp_frac=0.67)),
    "tp1.0_50":      (30, dict(tp_atr=1.00, tp_frac=0.50)),
    "tp1.0_67":      (30, dict(tp_atr=1.00, tp_frac=0.67)),
    "tp1.25_50":     (30, dict(tp_atr=1.25, tp_frac=0.50)),
    "tp1.5_50":      (30, dict(tp_atr=1.50, tp_frac=0.50)),
    "clock_60":      (60, dict()),
}


def load_frame():
    """RTH frame (rth anchor) + k=1 bands + per-session ATR for the whole run."""
    bars = S.load_rth(INST, vwap_anchor="rth", atr_lb=14)
    bands = S.noise_bands(bars, LOOKBACK, k=1.0)
    return bars, bands


def _run(bars, bands, period, kw):
    dm = S.decision_mfos(period, int(bars["mfo"].max()))
    return E.run(bars, bands, dm, exit_check="decision", require_vwap=True,
                 fill_mode="next_open", **kw)


def parity_check(bars, bands):
    """Rule 23: engine2 (decision clock 30m, decision stop, no TP) must reproduce the
    audited core.engine baseline to the digit."""
    core_bars = load_rth_core(INST)
    core_bands = noise_bands_core(core_bars, LOOKBACK)
    base_core = E1.run(core_bars, core_bands)                    # audited baseline
    base_e2 = _run(bars, bands, 30, {})
    n1, n2 = len(base_core), len(base_e2)
    g1 = float(base_core["points"].sum())
    g2 = float(base_e2["points"].sum())
    ok = (n1 == n2) and abs(g1 - g2) < 1e-6
    print(f"PARITY core.engine vs engine2 @30m/decision/noTP: "
          f"n {n1} vs {n2}, gross_pt {g1:.4f} vs {g2:.4f} -> {'OK' if ok else 'MISMATCH'}")
    assert ok, "engine2 does not reproduce the audited baseline — fix before trusting variants"
    return base_e2


def day_ret(trades, cost, dates):
    """Per-session summed NET RETURN (net_pts/entry_px), reindexed (0 if no trade).
    entry_px normalization = era-neutral (matches grid_wfo)."""
    if trades.empty:
        return pd.Series(0.0, index=dates, dtype=float)
    net = trades["points"] - 2.0 * cost
    ret = net / trades["entry_px"]
    return ret.groupby(trades["date"]).sum().reindex(dates, fill_value=0.0)


def sharpe_of(series):
    x = series.to_numpy(); sd = x.std(ddof=1)
    return (x.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0


def tail_stats(trades):
    """winner top-decile retention proxy + loser mean (pt), for the variance-vs-edge read."""
    if trades.empty:
        return dict(win=0.0, avg_loser_pt=np.nan, top_sumR=0.0)
    pts = trades["points"]
    losers = pts[pts < 0]
    top = pts[pts >= pts.quantile(0.9)]
    return dict(win=float((pts > 0).mean()),
                avg_loser_pt=float(losers.mean()) if len(losers) else np.nan,
                top_sumR=float(top.sum()))


def run_real():
    bars, bands = load_frame()
    all_dates = pd.Index(np.sort(bands["sdate"].unique()))
    base_e2 = parity_check(bars, bands)
    c = COST_GRID[PRIMARY]

    print(f"\n=== HYP-0004 EXIT variants (frozen EXP-0005 baseline, GC RTH) ===")
    print(f"identical 30m+VWAP entries; only the EXIT differs. primary cost={c:.4f}pt/side; "
          f"Sharpe INCLUDES zero-trade days ({len(all_dates)} sessions)\n")

    rows = {}
    base_tail = None
    hdr = (f"{'config':<12s} {'n':>5s} {'win%':>5s} {'grossPt':>8s} {'netPt':>8s} "
           f"{'netSh':>6s} {'dayt':>6s} {'avgLos':>7s} {'topRet':>6s} {'fillArt':>8s}")
    print(hdr); print("-" * len(hdr))
    for lab, (period, kw) in CFGS.items():
        tr = _run(bars, bands, period, kw)
        # fill feasibility (rule 1/2): no same-bar fills
        same = int((tr["entry_mfo"] == tr["exit_mfo"]).sum()) if not tr.empty else 0
        assert same == 0, f"{lab}: {same} same-bar fills — fill artifact!"
        rows[lab] = tr
        s = summarize(tr, INST, c, lab)
        ts = tail_stats(tr)
        if lab == "baseline_30":
            base_tail = ts["top_sumR"]
        ret = ts["top_sumR"] / base_tail if base_tail else np.nan
        # fill artifact only where a TP fires (else exits are all next-open by construction)
        if kw.get("tp_atr", 0) > 0:
            no = _run(bars, bands, period, kw)
            scl = E.run(bars, bands, S.decision_mfos(period, int(bars["mfo"].max())),
                        exit_check="decision", require_vwap=True,
                        fill_mode="signal_close", **kw)
            art = float(scl["points"].mean() - no["points"].mean())
        else:
            art = 0.0
        print(f"{lab:<12s} {s['n_trades']:>5d} {s['hit_rate']*100:>4.1f} "
              f"{s['gross_pts_per_trade']:>+8.4f} {s['net_pts_per_trade']:>+8.4f} "
              f"{s['sharpe_net_daily']:>+6.2f} {s['day_net_t']:>+6.2f} "
              f"{ts['avg_loser_pt']:>+7.3f} {ret:>5.0%} {art:>+8.4f}")

    # ---- headline deltas vs baseline at every cost ----
    print(f"\n--- net daily Sharpe & day-$ t vs baseline, by cost (primary={PRIMARY}) ---")
    bcfg = CFGS["baseline_30"]
    for cost_name, cc in COST_GRID.items():
        bsum = summarize(rows["baseline_30"], INST, cc, "")
        print(f"  [{cost_name}] baseline netSh={bsum['sharpe_net_daily']:+.3f} "
              f"t={bsum['day_net_t']:+.2f}")
        for lab in CFGS:
            if lab == "baseline_30":
                continue
            s = summarize(rows[lab], INST, cc, "")
            print(f"      {lab:<12s} netSh={s['sharpe_net_daily']:+.3f} "
                  f"(d{s['sharpe_net_daily']-bsum['sharpe_net_daily']:+.3f})  "
                  f"t={s['day_net_t']:+.2f}  grossPt={s['gross_pts_per_trade']:+.4f}")

    os.makedirs(OUTDIR, exist_ok=True)
    for lab, tr in rows.items():
        tr.to_parquet(f"{OUTDIR}/trades_{lab}.parquet")
    print(f"\ntrades -> {OUTDIR}/")
    print("\nSCREEN GATE: a variant advances to Null-C only if net Sharpe beats baseline")
    print("by >=+0.05 at 0.50tick WITHOUT inflating gross pt/trade (gate-nullc-on-success-metric).")


def _uplift(bars, bands, dates, cost, labels):
    """(variant - baseline) net-daily-Sharpe and sumNet$ uplift for each label."""
    b = _run(bars, bands, *CFGS["baseline_30"])
    b_sh = sharpe_of(day_ret(b, cost, dates))
    b_usd = float(((b["points"] - 2.0 * cost).groupby(b["date"]).sum()
                   * S.POINT_VALUE[INST]).reindex(dates, fill_value=0.0).sum()) if not b.empty else 0.0
    out = {}
    for lab in labels:
        v = _run(bars, bands, *CFGS[lab])
        v_sh = sharpe_of(day_ret(v, cost, dates))
        v_usd = float(((v["points"] - 2.0 * cost).groupby(v["date"]).sum()
                       * S.POINT_VALUE[INST]).reindex(dates, fill_value=0.0).sum()) if not v.empty else 0.0
        out[lab] = (v_sh - b_sh, v_usd - b_usd)
    return out


def run_null(ndraw, labels):
    bars, bands = load_frame()
    dates = pd.Index(np.sort(bands["sdate"].unique()))
    c = COST_GRID[PRIMARY]
    real = _uplift(bars, bands, dates, c, labels)
    print(f"=== HYP-0004 EXIT Null-C twin ({ndraw} draws) — configs {labels} ===")
    print(f"paired: real (variant - baseline) uplift vs the same on return-shuffled tape.")
    print(f"REAL diffusivity={NS.diffusivity(bars):.4f}pt   cost={c:.4f}pt/side")
    print("REAL uplift vs baseline: " + "  ".join(
        f"{lab}: dSh={real[lab][0]:+.3f} dNet$={real[lab][1]:+.0f}" for lab in labels))
    nul = {lab: {"sh": [], "usd": []} for lab in labels}
    for k in range(ndraw):
        nb = NS.null_c_returns(bars, seed=6000 + k)
        nbd = S.noise_bands(nb, LOOKBACK, k=1.0)
        ndates = pd.Index(np.sort(nbd["sdate"].unique()))
        u = _uplift(nb, nbd, ndates, c, labels)
        for lab in labels:
            nul[lab]["sh"].append(u[lab][0]); nul[lab]["usd"].append(u[lab][1])
        print(f"  draw {k+1}/{ndraw} diff={NS.diffusivity(nb):.4f}", end="\r", flush=True)
    print()
    for lab in labels:
        for key, nm in [("sh", "netSharpe"), ("usd", "sumNet$  ")]:
            a = np.array(nul[lab][key]); sd = a.std(ddof=1)
            rv = real[lab][0] if key == "sh" else real[lab][1]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            print(f"{lab:<12s} {nm} real={rv:+9.3f} null={a.mean():+9.3f}+/-{sd:8.3f} "
                  f"z={z:+5.2f} null>=real={float((a >= rv).mean()):.2f}")
    print("\nVERDICT: real risk-adjusted edge only if netSharpe uplift z>=2 (not noise-reproduced).")
    os.makedirs(OUTDIR, exist_ok=True)
    with open(f"{OUTDIR}/nullc.txt", "a") as f:
        f.write(f"labels={labels} ndraw={ndraw}\n")
        for lab in labels:
            a = np.array(nul[lab]["sh"])
            z = (real[lab][0] - a.mean()) / a.std(ddof=1) if a.std(ddof=1) > 0 else np.nan
            f.write(f"  {lab}: real dSh={real[lab][0]:+.3f} null {a.mean():+.3f}+/-{a.std(ddof=1):.3f} z={z:+.2f}\n")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        nd = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        labs = sys.argv[3:] if len(sys.argv) > 3 else ["tp0.75_67", "tp1.0_50"]
        run_null(nd, labs)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
