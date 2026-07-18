"""
EXIT-SYSTEM variants for the continuous_stop NQ momentum baseline.

User's final test: does a smarter EXIT beat the plain every-bar band/VWAP stop?
  * PARTIAL TP + RUNNER : once price runs `tp_atr` ATR in favour, bank `tp_frac`
    (=50%) at the next open; the runner keeps trailing the band/VWAP stop.
  * BREAK-EVEN STOP     : once price runs `be_atr` ATR in favour, latch the trailing
    stop up to entry (can't give the trade back to a loss).

ENTRIES ARE IDENTICAL to the baseline (30-min clock + VWAP gate), so this is a clean
apples-to-apples exit comparison (rule 23: tp_atr=be_atr=0 reproduces the baseline to
the digit). The break-even trigger is in **ATR** (rule 19), NOT %-of-price: NQ ran
2.6k→20k with ATR 34→383 pts, so a fixed "1%" would be ~1 ATR now and ~10 ATR in 2012.

Fills stay honest (rule 1/2/3): the partial is momentum-confirmed (a close beyond
+tp_atr) and filled at the NEXT open — conservative vs an intrabar limit; the BE stop
only ever TIGHTENS, so it introduces no optimistic fill. Both verified with the
next_open-vs-signal_close artifact.

Report (same battery as the entry studies): net R, Sharpe INCLUDING zero-trade days,
top-decile-winner retention, MFE capture on winners, average loser, trade count, win
rate. R = net_points/ATR (rule 19); the day is the unit (rule 22).

Null-C ONLY on a config that shows uplift (per request):
  python -u -m futures.nq.noise_vwap.scripts.exit_mgmt real
  python -u -m futures.nq.noise_vwap.scripts.exit_mgmt null 30 be_0.5 tp1.0_50
"""
from __future__ import annotations

import sys
import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo import add_pnl
from .wfo_data import enrich_trades, LOOKBACK
from .event_entry import score_ztd, tail_and_shape

RT_COST = 2.0 * COST_025

# label -> exit kwargs on top of the continuous_stop baseline (clock 30m, every-bar)
CFGS = {
    "baseline":     dict(),
    "be_0.5":       dict(be_atr=0.5),
    "be_1.0":       dict(be_atr=1.0),
    "tp1.0_50":     dict(tp_atr=1.0, tp_frac=0.5),
    "tp1.5_50":     dict(tp_atr=1.5, tp_frac=0.5),
    "tp1.0_50+be":  dict(tp_atr=1.0, tp_frac=0.5, be_atr=0.5),
}


def _run(bars, bands, dm, kw, fill_mode="next_open"):
    return E.run(bars, bands, dm, exit_check="every_bar", fill_mode=fill_mode, **kw)


def run_real():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    all_dates = np.sort(bands["sdate"].unique())

    print("=== EXIT-SYSTEM variants (continuous_stop baseline, RTH NQ) ===")
    print(f"identical 30m+VWAP entries; only the EXIT differs. cost={RT_COST:.3f}pt RT; "
          f"Sharpe INCLUDES zero-trade days ({len(all_dates)} sessions)\n")
    hdr = (f"{'config':<13s} {'n':>5s} {'win%':>5s} {'netRpt':>8s} {'sumR':>7s} "
           f"{'Sharpe':>7s} {'dayt':>6s} {'avgLos_pt':>9s} {'winMFEcap':>9s} "
           f"{'topDecR':>8s} {'reten':>6s} {'fillArt':>8s}")
    print(hdr); print("-" * len(hdr))
    base_top = None
    rows = {}
    for lab, kw in CFGS.items():
        df = enrich_trades(bars, bands, _run(bars, bands, dm, kw))
        rows[lab] = df
        sc = score_ztd(df, all_dates)
        sh = tail_and_shape(df)
        # fill artifact only where a TP exists (BE-only never fills intrabar)
        if kw.get("tp_atr", 0) > 0:
            no = _run(bars, bands, dm, kw, "next_open")
            scl = _run(bars, bands, dm, kw, "signal_close")
            art = float(scl["points"].mean() - no["points"].mean())
        else:
            art = 0.0
        if lab == "baseline":
            base_top = sh["top_sumR"]
        ret = sh["top_sumR"] / base_top if base_top else np.nan
        print(f"{lab:<13s} {sc['n']:>5d} {sh['win']*100:>4.1f} {sc['Rpt']:>+8.4f} "
              f"{sc['sumR']:>+7.1f} {sc['sharpe']:>7.2f} {sc['dayt']:>+6.2f} "
              f"{sh['avg_loser_pt']:>+9.3f} {sh['win_mfecap']:>+9.3f} "
              f"{sh['top_sumR']:>+8.1f} {ret:>5.0%} {art:>+8.3f}")

    print("\nvs baseline (Sharpe/return-to-DD is the user's metric; net R secondary):")
    b = score_ztd(rows["baseline"], all_dates)
    for lab in CFGS:
        sc = score_ztd(rows[lab], all_dates)
        print(f"  {lab:<13s} dSharpe={sc['sharpe']-b['sharpe']:+.3f}  "
              f"dSumR={sc['sumR']-b['sumR']:+.1f}  dWin={ (tail_and_shape(rows[lab])['win']-tail_and_shape(rows['baseline'])['win'])*100:+.1f}pp")
    print("\nNull-C ONLY on configs showing uplift (per request):")
    print("  python -u -m futures.nq.noise_vwap.scripts.exit_mgmt null 30 <cfg> [<cfg> ...]")


def _sumR_sharpe(bars, bands, dm, all_dates, atr, kw):
    tr = add_pnl(_run(bars, bands, dm, kw), atr)
    if tr.empty:
        return 0.0, 0.0
    dayR = tr.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)
    sd = dayR.std(ddof=1)
    return float(dayR.sum()), (float(dayR.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0)


def run_null(ndraw, labels):
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    all_dates = np.sort(bands["sdate"].unique())
    atr = bars.groupby("sdate")["atr"].first()

    def uplift(bars_, bands_, atr_):
        b_sr, b_sh = _sumR_sharpe(bars_, bands_, dm, all_dates, atr_, {})
        out = {}
        for lab in labels:
            sr, sh = _sumR_sharpe(bars_, bands_, dm, all_dates, atr_, CFGS[lab])
            out[lab] = (sr - b_sr, sh - b_sh)
        return out

    real = uplift(bars, bands, atr)
    print(f"=== EXIT-SYSTEM Null-C twin ({ndraw} draws) — configs {labels} ===")
    print("null preserves daily drift, destroys intraday follow-through (rule 17).")
    print("REAL uplift vs baseline: " + "  ".join(
        f"{lab}: dSumR={real[lab][0]:+.1f} dSh={real[lab][1]:+.3f}" for lab in labels))
    nul = {lab: {"sr": [], "sh": []} for lab in labels}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=9000 + k)
        nbd = S.noise_bands(nb, LOOKBACK)
        natr = nb.groupby("sdate")["atr"].first()
        u = uplift(nb, nbd, natr)
        for lab in labels:
            nul[lab]["sr"].append(u[lab][0]); nul[lab]["sh"].append(u[lab][1])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    for lab in labels:
        for key, nm in [("sr", "sumR   "), ("sh", "Sharpe ")]:
            a = np.array(nul[lab][key]); sd = a.std(ddof=1)
            rv = real[lab][0] if key == "sr" else real[lab][1]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            print(f"{lab:<13s} {nm} real={rv:+7.3f} null={a.mean():+7.3f}+/-{sd:5.3f} "
                  f"z={z:+5.2f} null>=real={float((a >= rv).mean()):.2f}")
    print("\nVERDICT: real risk-adjusted edge only if Sharpe uplift z>=2 (not noise-reproduced).")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        nd = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        labs = sys.argv[3:] if len(sys.argv) > 3 else ["be_0.5", "tp1.0_50"]
        run_null(nd, labs)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
