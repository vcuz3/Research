"""
EVENT-DRIVEN entry vs the arbitrary 30-min clock, for the continuous_stop baseline.

User's predeclared question: can an event-driven entry (same noise-band/VWAP idea,
NO fixed 30-min clock) reduce low-MFE losers while preserving the large-winner tail?
All variants keep the baseline's exit = continuous (every-bar) band/VWAP stop, honest
next-1m-open fills, VWAP entry gate.

Families (all `entry_mode="threshold"`, evaluated every 1-min bar):
  * PERSIST  N=5 / N=15 : require the beyond-band+VWAP condition to hold for N
    CONSECUTIVE 1-min closes before entering (confirmation; a fake break that snaps
    back within N min never qualifies). `entry_persist` in engine2.
  * BUFFER   0.05/0.10/0.15 ATR : require the close beyond the band by X*ATR
    (volatility-scaled, rule 4/19).
  * BAND1.5  : buf=0 on a band widened to k=1.5*sigma (the Design-D multiplier), so
    the trigger itself is a wider, more-extreme break.
Plus EVENT_RAW (buf=0, persist=1, k=1.0) = the un-selective first-close event, the
reference the three selectivity knobs are trying to beat.

FILL FEASIBILITY FIRST (rule 1/2, mandatory even though the user didn't ask): every
config is also run with `signal_close` fills and the next_open-vs-signal_close artifact
is reported. Event-every-bar entries are the classic wick-capture trap; here the trigger
is a *close* beyond band and the fill is the *next* open, so the artifact should be ~0 --
but we verify it, we don't assume it.

Report (per user): net R, Sharpe INCLUDING zero-trade days (capacity-honest), top-decile
winner retention (tail magnitude vs baseline), MFE capture on winners, average loser,
trade count, win rate. R = net_points/ATR (rule 19); the day is the unit (rule 22).

NO Null-C here by request -- only run it later if a config shows a positive effect.

Run:  python -u -m futures.nq.noise_vwap.scripts.event_entry
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E
from ..core.data import POINT_VALUE
import sys

from .studies import get_session, INST, COST_025, _null_c_frame
from .wfo import _scale_bands, add_pnl, score
from .wfo_data import enrich_trades, LOOKBACK

RT_COST = 2.0 * COST_025
PV = POINT_VALUE[INST]


def score_ztd(df: pd.DataFrame, all_dates: np.ndarray) -> dict:
    """Day-summed R with ZERO-TRADE DAYS included (reindex over every active session,
    fill 0) -- the capacity-honest Sharpe the user asked for. Also day-clustered t."""
    if df.empty:
        return dict(n=0, sumR=0.0, Rpt=0.0, sharpe=0.0, dayt=0.0)
    dayR = df.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)
    n = len(dayR); m = dayR.mean(); sd = dayR.std(ddof=1)
    return dict(n=int(len(df)), sumR=float(dayR.sum()), Rpt=float(df["net_atr"].mean()),
                sharpe=float(m / sd * np.sqrt(252)) if sd > 0 else 0.0,
                dayt=float(m / (sd / np.sqrt(n))) if sd > 0 else 0.0)


def tail_and_shape(df: pd.DataFrame) -> dict:
    """Large-winner tail, MFE capture on winners, average loser, win rate."""
    if df.empty:
        return dict(win=np.nan, top_sumR=0.0, top_share=np.nan, top_n=0,
                    win_mfecap=np.nan, avg_loserR=np.nan, avg_loser_pt=np.nan)
    win = df[df["net_points"] > 0]
    los = df[df["net_points"] <= 0]
    cut = df["net_atr"].quantile(0.90)
    top = df[df["net_atr"] >= cut]
    tot = df["net_atr"].sum()
    # gross MFE capture on winners: how much of the max-favourable-excursion the
    # winners actually banked (net/MFE). Low -> giving winners back; high -> clean.
    wc = (win["net_points"] / win["mfe_points"].replace(0, np.nan)).mean() if not win.empty else np.nan
    return dict(win=float((df["net_points"] > 0).mean()),
                top_sumR=float(top["net_atr"].sum()),
                top_share=float(top["net_atr"].sum() / tot) if tot != 0 else np.nan,
                top_n=int(len(top)),
                win_mfecap=float(wc),
                avg_loserR=float(los["net_atr"].mean()) if not los.empty else np.nan,
                avg_loser_pt=float(los["net_points"].mean()) if not los.empty else np.nan)


def run_cfg_enriched(bars, bands, *, entry_mode="clock", period=30, buf=0.0,
                     persist=1, delay=0, fill_mode="next_open"):
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(period, max_mfo)
    tr = E.run(bars, bands, dm, exit_check="every_bar", entry_mode=entry_mode,
               entry_buf_atr=buf, entry_persist=persist, entry_delay=delay,
               fill_mode=fill_mode)
    return enrich_trades(bars, bands, tr)


def fill_artifact(bars, bands, *, entry_mode, period=30, buf=0.0, persist=1):
    """rule 1/2: next_open vs signal_close mean points (want ~0)."""
    max_mfo = int(bars["mfo"].max()); dm = S.decision_mfos(period, max_mfo)
    kw = dict(exit_check="every_bar", entry_mode=entry_mode, entry_buf_atr=buf,
              entry_persist=persist)
    no = E.run(bars, bands, dm, fill_mode="next_open", **kw)
    sc = E.run(bars, bands, dm, fill_mode="signal_close", **kw)
    if no.empty or sc.empty:
        return np.nan
    return float(sc["points"].mean() - no["points"].mean())


def run_real():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    b15 = _scale_bands(bands, 1.5)
    all_dates = np.sort(bands["sdate"].unique())

    # (label, bands, entry_mode, period, buf, persist)
    CFGS = [
        ("baseline_30m", bands, "clock", 30, 0.0, 1),
        ("event_raw",    bands, "threshold", 30, 0.0, 1),
        ("persist_5m",   bands, "threshold", 30, 0.0, 5),
        ("persist_15m",  bands, "threshold", 30, 0.0, 15),
        ("buf_0.05",     bands, "threshold", 30, 0.05, 1),
        ("buf_0.10",     bands, "threshold", 30, 0.10, 1),
        ("buf_0.15",     bands, "threshold", 30, 0.15, 1),
        ("band_1.5",     b15,   "threshold", 30, 0.0, 1),
    ]

    print("=== EVENT-DRIVEN ENTRY vs 30-min clock (continuous_stop exit, RTH NQ) ===")
    print(f"cost={RT_COST:.3f}pt RT; R=net/ATR; Sharpe INCLUDES zero-trade days "
          f"({len(all_dates)} active sessions)\n")
    hdr = (f"{'config':<14s} {'n':>5s} {'t/d':>5s} {'win%':>5s} {'netRpt':>8s} "
           f"{'sumR':>7s} {'Sharpe':>7s} {'dayt':>6s} {'avgLos_pt':>9s} "
           f"{'winMFEcap':>9s} {'topDecR':>8s} {'topShr':>7s} {'fillArt':>8s}")
    print(hdr); print("-" * len(hdr))
    base_top = None
    rows = {}
    for (lab, bd, em, per, buf, per_n) in CFGS:
        df = run_cfg_enriched(bars, bd, entry_mode=em, period=per, buf=buf, persist=per_n)
        rows[lab] = df
        sc = score_ztd(df, all_dates)
        sh = tail_and_shape(df)
        art = fill_artifact(bars, bd, entry_mode=em, period=per, buf=buf, persist=per_n)
        tpd = sc["n"] / len(all_dates)
        if lab == "baseline_30m":
            base_top = sh["top_sumR"]
        ret = (sh["top_sumR"] / base_top) if base_top else np.nan
        print(f"{lab:<14s} {sc['n']:>5d} {tpd:>5.2f} {sh['win']*100:>4.1f} "
              f"{sc['Rpt']:>+8.4f} {sc['sumR']:>+7.1f} {sc['sharpe']:>7.2f} "
              f"{sc['dayt']:>+6.2f} {sh['avg_loser_pt']:>+9.3f} {sh['win_mfecap']:>+9.3f} "
              f"{sh['top_sumR']:>+8.1f} {sh['top_share']:>6.2f} {art:>+8.3f}")

    print("\ntop-decile-winner RETENTION vs baseline (tail sumR / baseline tail sumR):")
    for lab in rows:
        sh = tail_and_shape(rows[lab])
        print(f"  {lab:<14s} tailR={sh['top_sumR']:+7.1f}  "
              f"retention={sh['top_sumR']/base_top:>5.0%}  (n_top={sh['top_n']})")

    print("\nloser reduction (mean losing-trade net pts; less-negative = fewer/softer losers):")
    b = rows["baseline_30m"]
    bl = b[b["net_points"] <= 0]["net_points"].mean()
    for lab in rows:
        d = rows[lab]; los = d[d["net_points"] <= 0]
        n_los = len(los); frac = n_los / max(len(d), 1)
        print(f"  {lab:<14s} avgLoser={los['net_points'].mean():+.3f}pt "
              f"(baseline {bl:+.3f})  losers={n_los} ({frac:.0%} of trades)")

    print("\nNOTE: no Null-C run here (per request). persist_15m / buf_0.15 show a "
          "positive effect -> vet with:  python -u -m ...scripts.event_entry null 30")


# --------------------------------------------------------------------------- #
# Null-C twin -- ONLY for the configs that showed a positive effect (rule 17/24)
# --------------------------------------------------------------------------- #
def _sumR_sharpe(bars_, bands_, all_dates, atr_, *, entry_mode, buf, persist, delay=0):
    max_mfo = int(bars_["mfo"].max()); dm = S.decision_mfos(30, max_mfo)
    tr = add_pnl(E.run(bars_, bands_, dm, exit_check="every_bar", entry_mode=entry_mode,
                       entry_buf_atr=buf, entry_persist=persist, entry_delay=delay), atr_)
    if tr.empty:
        return 0.0, 0.0
    dayR = tr.groupby("date")["net_atr"].sum().reindex(all_dates, fill_value=0.0)
    sd = dayR.std(ddof=1)
    return float(dayR.sum()), float(dayR.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0


# the two positive configs vs the ungated event/clock baseline
NULL_CFGS = [("persist_15m", "threshold", 0.0, 15), ("buf_0.15", "threshold", 0.15, 1)]


def run_null(ndraw=30):
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    all_dates = np.sort(bands["sdate"].unique())
    atr = bars.groupby("sdate")["atr"].first()

    def uplifts(bars_, bands_, atr_):
        b_sr, b_sh = _sumR_sharpe(bars_, bands_, all_dates, atr_,
                                  entry_mode="clock", buf=0.0, persist=1)
        out = {}
        for lab, em, buf, per in NULL_CFGS:
            sr, sh = _sumR_sharpe(bars_, bands_, all_dates, atr_,
                                  entry_mode=em, buf=buf, persist=per)
            out[lab] = (sr - b_sr, sh - b_sh)
        return out, (b_sr, b_sh)

    real, (b_sr, b_sh) = uplifts(bars, bands, atr)
    print(f"=== EVENT-ENTRY Null-C twin ({ndraw} draws) — vet the positive configs ===")
    print("null preserves daily drift, destroys intraday follow-through (rule 17).")
    print(f"baseline_30m real: sumR={b_sr:+.1f} Sharpe(ztd)={b_sh:.2f}")
    print("REAL uplift vs baseline: " + "  ".join(
        f"{lab}: dSumR={real[lab][0]:+.1f} dSh={real[lab][1]:+.3f}" for lab, *_ in NULL_CFGS))

    nul = {lab: {"sr": [], "sh": []} for lab, *_ in NULL_CFGS}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=8000 + k)
        nbd = S.noise_bands(nb, LOOKBACK)
        natr = nb.groupby("sdate")["atr"].first()
        u, _ = uplifts(nb, nbd, natr)
        for lab, *_ in NULL_CFGS:
            nul[lab]["sr"].append(u[lab][0]); nul[lab]["sh"].append(u[lab][1])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    for lab, *_ in NULL_CFGS:
        for key, nm in [("sr", "sumR   "), ("sh", "Sharpe ")]:
            a = np.array(nul[lab][key]); sd = a.std(ddof=1)
            rv = real[lab][0] if key == "sr" else real[lab][1]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            print(f"{lab:<12s} {nm} uplift real={rv:+7.3f} null={a.mean():+7.3f}+/-{sd:5.3f} "
                  f"z={z:+5.2f} null>=real={float((a>=rv).mean()):.2f}")
    print("\nVERDICT: real only if z>=2 on NET R (sumR) AND not a shrinkage-only Sharpe gain.")


# --------------------------------------------------------------------------- #
# DELAYED re-entry (user's corrected 5m/15m spec): signal fires -> wait N min ->
# enter iff STILL beyond band+VWAP at that later bar (endpoint recheck, not the
# stricter N-consecutive-bar persistence). Same continuous-stop exit.
# --------------------------------------------------------------------------- #
DELAY_CFGS = [
    ("baseline_30m", "clock", 0.0, 1, 0),
    ("event_now",    "delay", 0.0, 1, 1),   # ~immediate (arm+next-bar recheck)
    ("delay_5m",     "delay", 0.0, 1, 5),
    ("delay_15m",    "delay", 0.0, 1, 15),
    ("persist_15m",  "threshold", 0.0, 15, 0),  # contrast: the old (stricter) rule
]


def run_delay():
    bars = get_session("RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    all_dates = np.sort(bands["sdate"].unique())
    print("=== DELAYED re-entry (signal -> wait N min -> enter if still beyond) ===")
    print(f"endpoint recheck, NOT N-consecutive persistence. continuous-stop exit; "
          f"Sharpe INCLUDES zero-trade days ({len(all_dates)} sessions)\n")
    hdr = (f"{'config':<13s} {'n':>5s} {'t/d':>5s} {'win%':>5s} {'netRpt':>8s} "
           f"{'sumR':>7s} {'Sharpe':>7s} {'dayt':>6s} {'avgLos_pt':>9s} "
           f"{'winMFEcap':>9s} {'topDecR':>8s} {'reten':>6s}")
    print(hdr); print("-" * len(hdr))
    base_top = None; rows = {}
    for lab, em, buf, per, dly in DELAY_CFGS:
        df = run_cfg_enriched(bars, bands, entry_mode=em, buf=buf, persist=per, delay=dly)
        rows[lab] = df
        sc = score_ztd(df, all_dates); sh = tail_and_shape(df)
        if lab == "baseline_30m":
            base_top = sh["top_sumR"]
        ret = sh["top_sumR"] / base_top if base_top else np.nan
        print(f"{lab:<13s} {sc['n']:>5d} {sc['n']/len(all_dates):>5.2f} {sh['win']*100:>4.1f} "
              f"{sc['Rpt']:>+8.4f} {sc['sumR']:>+7.1f} {sc['sharpe']:>7.2f} {sc['dayt']:>+6.2f} "
              f"{sh['avg_loser_pt']:>+9.3f} {sh['win_mfecap']:>+9.3f} "
              f"{sh['top_sumR']:>+8.1f} {ret:>5.0%}")
    b = score_ztd(rows["baseline_30m"], all_dates)
    print("\nvs baseline (risk-adjusted is the metric):")
    for lab, *_ in DELAY_CFGS:
        sc = score_ztd(rows[lab], all_dates)
        print(f"  {lab:<13s} dSharpe={sc['sharpe']-b['sharpe']:+.3f}  dSumR={sc['sumR']-b['sumR']:+.1f}")
    print("\nNull-C only if a delay config shows Sharpe uplift: "
          "python -u -m ...scripts.event_entry delay_null 30")


def run_delay_null(ndraw=30):
    bars = get_session("RTH"); bands = S.noise_bands(bars, LOOKBACK)
    all_dates = np.sort(bands["sdate"].unique()); atr = bars.groupby("sdate")["atr"].first()
    labs = [("delay_5m", 5), ("delay_15m", 15)]

    def uplifts(bars_, bands_, atr_):
        b_sr, b_sh = _sumR_sharpe(bars_, bands_, all_dates, atr_,
                                  entry_mode="clock", buf=0.0, persist=1)
        out = {}
        for lab, dly in labs:
            sr, sh = _sumR_sharpe(bars_, bands_, all_dates, atr_, entry_mode="delay",
                                  buf=0.0, persist=1, delay=dly)
            out[lab] = (sr - b_sr, sh - b_sh)
        return out

    real = uplifts(bars, bands, atr)
    print(f"=== DELAYED re-entry Null-C twin ({ndraw} draws) ===")
    print("REAL uplift vs baseline: " + "  ".join(
        f"{lab}: dSumR={real[lab][0]:+.1f} dSh={real[lab][1]:+.3f}" for lab, _ in labs))
    nul = {lab: {"sr": [], "sh": []} for lab, _ in labs}
    for k in range(ndraw):
        nb = _null_c_frame(bars, seed=8500 + k)
        nbd = S.noise_bands(nb, LOOKBACK); natr = nb.groupby("sdate")["atr"].first()
        u = uplifts(nb, nbd, natr)
        for lab, _ in labs:
            nul[lab]["sr"].append(u[lab][0]); nul[lab]["sh"].append(u[lab][1])
        print(f"  draw {k+1}/{ndraw} done", end="\r")
    print()
    for lab, _ in labs:
        for key, nm in [("sr", "sumR   "), ("sh", "Sharpe ")]:
            a = np.array(nul[lab][key]); sd = a.std(ddof=1)
            rv = real[lab][0] if key == "sr" else real[lab][1]
            z = (rv - a.mean()) / sd if sd > 0 else np.nan
            print(f"{lab:<10s} {nm} real={rv:+7.3f} null={a.mean():+7.3f}+/-{sd:5.3f} "
                  f"z={z:+5.2f} null>=real={float((a >= rv).mean()):.2f}")
    print("\nVERDICT: real risk-adjusted edge only if Sharpe uplift z>=2 (not noise-reproduced).")


def main():
    cmd = sys.argv[1] if len(sys.argv) > 1 else "real"
    if cmd == "real":
        run_real()
    elif cmd == "null":
        run_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    elif cmd == "delay":
        run_delay()
    elif cmd == "delay_null":
        run_delay_null(int(sys.argv[2]) if len(sys.argv) > 2 else 30)
    else:
        print("unknown", cmd)


if __name__ == "__main__":
    main()
