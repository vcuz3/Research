"""
DELAYED RATCHET TRAILING STOP for the continuous_stop NQ momentum baseline.

User's spec: once in a position and the PEAK favourable move has run 1R or 2R,
trail the stop 1R at a time (stop sits 1R behind the highest whole-R milestone),
combined with the existing band/VWAP stop (the stop can only tighten). R = ATR
(the project's vol-scaled risk unit, rule 19). Two activation thresholds:
  * trail1_s1 : R-step 1, activate at +1R  (breakeven at the first rung)
  * trail1_s2 : R-step 1, activate at +2R  (delayed: first rung locks +1R)

User's HYPOTHESIS: this cuts CAGR but improves variance (lower DD). So we report
the full risk/return picture, not just Sharpe: mean/sum R, daily-R std, Sharpe,
max drawdown (R), return/DD (Calmar proxy).

KILL-TEST (rule 24/17): a trailing stop mechanically reduces variance on ANY path,
including noise. It is a real RISK-ADJUSTED edge only if its Sharpe / return-DD
uplift over baseline BEATS its own Null-C twin (z>=2). If the null reproduces the
improvement, the trailing stop is a legitimate risk-preference DIAL (relevant to the
trailing-DD prop challenge) but NOT alpha -- same category as the WFO Design-C
variance-reduction (z+0.2, NO-GO as edge).

Fills honest: peak is close-based, exits fill next-open, ratchet only tightens
(rule 1/2/3) -> the next_open-vs-signal_close artifact is ~0 (verified in the table).

Run:  python -u -m futures.nq.noise_vwap.scripts.trail_stop real
      python -u -m futures.nq.noise_vwap.scripts.trail_stop null 30 trail1_s1 trail1_s2
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

RT_COST = 2.0 * COST_025

# label -> extra exit kwargs on top of the continuous_stop baseline
CFGS = {
    "baseline":   dict(),
    "trail1_s1":  dict(trail_step_atr=1.0, trail_start_atr=1.0),
    "trail1_s2":  dict(trail_step_atr=1.0, trail_start_atr=2.0),
    "be_1.0":     dict(be_atr=1.0),          # reference: pure breakeven latch
    "tp1.0_50":   dict(tp_atr=1.0, tp_frac=0.5),  # reference: the validated partial TP
}


def _run(bars, bands, dm, kw, fill_mode="next_open"):
    return E.run(bars, bands, dm, exit_check="every_bar", fill_mode=fill_mode, **kw)


def max_dd_R(dayR: pd.Series) -> float:
    eq = dayR.cumsum()
    return float((eq.cummax() - eq).max())


def score_full(tr: pd.DataFrame, all_dates: np.ndarray) -> dict:
    """Risk/return from a trade df carrying net_atr & net_points. Sharpe/DD include
    zero-trade days (capacity-honest). R is the unit (rule 19); day is the risk unit."""
    if tr.empty:
        return dict(n=0, win=np.nan, Rpt=0.0, sumR=0.0, stdR=0.0, sharpe=0.0,
                    maxDD=0.0, retDD=np.nan, dayt=0.0)
    dayR = tr.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)
    n = len(dayR); m = dayR.mean(); sd = dayR.std(ddof=1)
    dd = max_dd_R(dayR)
    return dict(
        n=int(len(tr)), win=float((tr["net_points"] > 0).mean()),
        Rpt=float(tr["net_atr"].mean()), sumR=float(dayR.sum()), stdR=float(sd),
        sharpe=float(m / sd * np.sqrt(252)) if sd > 0 else 0.0,
        maxDD=dd, retDD=float(dayR.sum() / dd) if dd > 0 else np.nan,
        dayt=float(m / (sd / np.sqrt(n))) if sd > 0 else 0.0)


def run_real():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    all_dates = np.sort(bands["sdate"].unique())
    atr = bars.groupby("sdate")["atr"].first()

    print("=== DELAYED RATCHET TRAILING STOP (continuous_stop baseline, RTH NQ) ===")
    print(f"identical 30m+VWAP entries; only the EXIT differs. R=ATR. cost={RT_COST:.3f}pt RT; "
          f"Sharpe/DD INCLUDE zero-trade days ({len(all_dates)} sessions)\n")
    hdr = (f"{'config':<11s} {'n':>5s} {'win%':>5s} {'Rpt':>8s} {'sumR':>7s} "
           f"{'stdR':>6s} {'Sharpe':>7s} {'maxDD':>7s} {'ret/DD':>7s} {'dayt':>6s} "
           f"{'fillArt':>8s}")
    print(hdr); print("-" * len(hdr))
    rows = {}
    for lab, kw in CFGS.items():
        tr = add_pnl(_run(bars, bands, dm, kw), atr)
        rows[lab] = tr
        sc = score_full(tr, all_dates)
        # fill artifact (rule 1/2): next_open vs signal_close mean points, want ~0
        no = _run(bars, bands, dm, kw, "next_open")
        scl = _run(bars, bands, dm, kw, "signal_close")
        art = float(scl["points"].mean() - no["points"].mean()) if not no.empty else np.nan
        print(f"{lab:<11s} {sc['n']:>5d} {sc['win']*100:>4.1f} {sc['Rpt']:>+8.4f} "
              f"{sc['sumR']:>+7.1f} {sc['stdR']:>6.3f} {sc['sharpe']:>7.2f} "
              f"{sc['maxDD']:>7.1f} {sc['retDD']:>7.2f} {sc['dayt']:>+6.2f} {art:>+8.3f}")

    b = score_full(rows["baseline"], all_dates)
    print("\nvs baseline (hypothesis: sumR DOWN, stdR DOWN, maxDD DOWN; Sharpe/retDD = the test):")
    for lab in CFGS:
        sc = score_full(rows[lab], all_dates)
        print(f"  {lab:<11s} dSumR={sc['sumR']-b['sumR']:+6.1f}  "
              f"dStdR={sc['stdR']-b['stdR']:+.3f}  dSharpe={sc['sharpe']-b['sharpe']:+.3f}  "
              f"dMaxDD={sc['maxDD']-b['maxDD']:+6.1f}  dRetDD={ (sc['retDD']-b['retDD']) if np.isfinite(sc['retDD']) and np.isfinite(b['retDD']) else np.nan:+.2f}")
    print("\nNull-C ONLY on configs showing a Sharpe/ret-DD uplift (rule 17/24):")
    print("  python -u -m futures.nq.noise_vwap.scripts.trail_stop null 30 <cfg> ...")


def _score(bars, bands, dm, all_dates, atr, kw):
    return score_full(add_pnl(_run(bars, bands, dm, kw), atr), all_dates)


def run_null(ndraw, labels):
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    all_dates = np.sort(bands["sdate"].unique())
    atr = bars.groupby("sdate")["atr"].first()

    def uplift(bars_, bands_, atr_):
        b = _score(bars_, bands_, dm, all_dates, atr_, {})
        out = {}
        for lab in labels:
            s = _score(bars_, bands_, dm, all_dates, atr_, CFGS[lab])
            out[lab] = dict(sharpe=s["sharpe"] - b["sharpe"],
                            retDD=(s["retDD"] - b["retDD"]) if np.isfinite(s["retDD"]) and np.isfinite(b["retDD"]) else np.nan,
                            sumR=s["sumR"] - b["sumR"])
        return out

    real = uplift(bars, bands, atr)
    print(f"=== TRAILING-STOP Null-C twin ({ndraw} draws) — configs {labels} ===")
    print("null preserves daily drift, destroys intraday follow-through (rule 17).")
    print("REAL uplift vs baseline: " + "  ".join(
        f"{lab}: dSh={real[lab]['sharpe']:+.3f} dRetDD={real[lab]['retDD']:+.2f} dSumR={real[lab]['sumR']:+.1f}"
        for lab in labels))

    nul = {lab: {"sharpe": [], "retDD": [], "sumR": []} for lab in labels}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=6000 + k)
        nbd = S.noise_bands(nb, LOOKBACK)
        natr = nb.groupby("sdate")["atr"].first()
        u = uplift(nb, nbd, natr)
        for lab in labels:
            for key in ("sharpe", "retDD", "sumR"):
                nul[lab][key].append(u[lab][key])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    for lab in labels:
        for key, nm in [("sharpe", "dSharpe"), ("retDD", "dRetDD "), ("sumR", "dSumR  ")]:
            a = np.array(nul[lab][key], dtype=float); a = a[np.isfinite(a)]
            sd = a.std(ddof=1) if len(a) > 1 else np.nan
            rv = real[lab][key]
            z = (rv - a.mean()) / sd if sd and sd > 0 else np.nan
            print(f"{lab:<11s} {nm} real={rv:+7.3f} null={a.mean():+7.3f}+/-{sd:5.3f} "
                  f"z={z:+5.2f} null>=real={float((a >= rv).mean()):.2f}")
    print("\nVERDICT: real risk-adjusted edge only if a Sharpe OR ret/DD uplift has z>=2. "
          "A variance/DD improvement the null reproduces = a risk DIAL, not alpha.")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        nd = int(sys.argv[2]) if len(sys.argv) > 2 else 30
        labs = sys.argv[3:] if len(sys.argv) > 3 else ["trail1_s1", "trail1_s2"]
        run_null(nd, labs)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
