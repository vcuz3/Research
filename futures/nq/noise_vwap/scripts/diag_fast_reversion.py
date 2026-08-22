"""Diagnostics for the fast-alpha reversion mechanic (user Qs, 2026-08-16).

NOT a confirmatory experiment. Three read-outs on the frozen continuous-stop
baseline, on the correct footing that the exit-delay uplift is +117% MEAN
(post-stop reversion) / -17% variance (EXP-0047 Addendum 2), and the paper's
SIGN-timing cue is the NO-GO (a blind delay captures the same reversion):

Q1  Why does delaying help at EXIT but not ENTRY?  IC of the side-signed trailing
    log return into the decision (entry side) vs per-trade net R, swept over
    horizons; plus the EXIT-side mirror (mean signed forward move AFTER a stop),
    to show the sign flips (entry = momentum/continuation, exit = reversion).

Q2  Is the post-stop reversion capture consistent through the day?  Per-trade
    capture (fixed-delay overlay net R minus baseline net R, matched on entry)
    bucketed by decision slot, with count, win-rate change and left-tail.

Q3  Noise-reduction stop = honor the stop only on a slower cadence / after a fixed
    hold ("if above stop at the checkpoint, stay").  Swept for CLOCK and
    CONTINUOUS (threshold) entry, scored with DRAWDOWN-AWARE metrics (maxDD,
    Calmar = sumR/maxDD) per the EXP-0047 addendum, TRAIN/TEST.  A survivor here
    is a preregistration trigger, NOT a GO.

Usage: python -u -m futures.nq.noise_vwap.scripts.diag_fast_reversion NQ
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

from ..core import engine2 as E
from ..core import session as S
from .hyp_0012_diffusion_cone import (
    score_candidate, common_dates, round_trip_cost_points, LOOKBACK, PERIOD,
)
from .hyp_0035_exit_overlay import split_dates, run_ov

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "DIAG-fast-reversion"
HORIZONS = (1, 2, 3, 5, 10, 15, 20, 30)


def load(inst):
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(PERIOD, int(bars["mfo"].max()))
    dates = common_dates(bars)
    return bars, bands, dm, dates


def close_lookup(bars):
    """(sdate, mfo) -> close, as a dict of per-date arrays for fast trailing/fwd."""
    g = {}
    for sd, sub in bars.groupby("sdate"):
        arr = np.full(int(bars["mfo"].max()) + 1, np.nan)
        arr[sub["mfo"].to_numpy()] = sub["close"].to_numpy()
        g[pd.Timestamp(sd)] = arr
    return g


# --------------------------------------------------------------------------- #
# Q1 - entry trailing-return IC + exit-side mirror
# --------------------------------------------------------------------------- #
def q1_entry_exit_ic(inst, bars, bands, dm, dates):
    tr = run_ov(bars, bands, dm, fast_overlay=False)
    tr = tr[tr["date"].isin(pd.Index(pd.to_datetime(dates)))].copy()
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)
    tr["atr"] = tr["date"].map(atr)
    tr = tr[tr["atr"] > 0].copy()
    tr["net_r"] = (tr["points"] - rt) / tr["atr"]
    clk = close_lookup(bars)

    print("\n===== Q1: entry trailing-return IC vs per-trade net R =====")
    print("(signed by trade side; ENTRY momentum => IC>0 => delaying entry should HURT)")
    print(f"{'x_min':>6} {'IC_spear':>9} {'p':>7} "
          f"{'meanR_lowQ':>10} {'meanR_hiQ':>10} {'hi-lo':>8}")
    rows = []
    for x in HORIZONS:
        vals = np.full(len(tr), np.nan)
        for j, (d, m, side) in enumerate(zip(tr["date"], tr["entry_mfo"], tr["side"])):
            arr = clk.get(pd.Timestamp(d))
            if arr is None:
                continue
            m0 = int(m) - 1              # decision close (fill is next open)
            mp = m0 - x
            if mp < 0 or np.isnan(arr[m0]) or np.isnan(arr[mp]) or arr[mp] <= 0:
                continue
            vals[j] = side * np.log(arr[m0] / arr[mp])
        s = pd.Series(vals, index=tr.index)
        ok = s.notna()
        ic, p = spearmanr(s[ok], tr["net_r"][ok])
        q = pd.qcut(s[ok], 5, labels=False, duplicates="drop")
        lo = tr["net_r"][ok][q == q.min()].mean()
        hi = tr["net_r"][ok][q == q.max()].mean()
        rows.append(dict(x=x, ic=ic, p=p, meanR_loQ=lo, meanR_hiQ=hi, spread=hi - lo,
                         n=int(ok.sum())))
        print(f"{x:>6} {ic:>+9.4f} {p:>7.3f} {lo:>+10.4f} {hi:>+10.4f} {hi-lo:>+8.4f}")

    # exit-side mirror: signed forward move AFTER a stop exit (post-stop reversion)
    st = tr[tr["reason"] == "stop"].copy()
    print("\n----- EXIT mirror: mean signed fwd move AFTER a STOP, next x min "
          f"(n_stop={len(st)}) -----")
    print("(positive => price reverts in trade direction after the stop = what a "
          "delay harvests)")
    print(f"{'x_min':>6} {'meanFwdR':>9} {'%pos':>7} {'n':>7}")
    exrows = []
    for x in HORIZONS:
        fwd = np.full(len(st), np.nan)
        for j, (d, m, side, a) in enumerate(
                zip(st["date"], st["exit_mfo"], st["side"], st["atr"])):
            arr = clk.get(pd.Timestamp(d))
            if arr is None:
                continue
            m0 = int(m)
            mp = m0 + x
            if mp > len(arr) - 1 or np.isnan(arr[m0]) or np.isnan(arr[mp]):
                continue
            fwd[j] = side * (arr[mp] - arr[m0]) / a       # in R units
        f = pd.Series(fwd).dropna()
        exrows.append(dict(x=x, meanFwdR=f.mean(), pct_pos=(f > 0).mean(), n=len(f)))
        print(f"{x:>6} {f.mean():>+9.4f} {(f>0).mean():>7.3f} {len(f):>7}")
    pd.DataFrame(rows).to_csv(OUT / f"q1_entry_ic_{inst}.csv", index=False)
    pd.DataFrame(exrows).to_csv(OUT / f"q1_exit_mirror_{inst}.csv", index=False)


# --------------------------------------------------------------------------- #
# Q2 - post-stop reversion capture by time of day
# --------------------------------------------------------------------------- #
def q2_capture_by_tod(inst, bars, bands, dm, dates, h=4):
    atr = bars.groupby("sdate")["atr"].first()
    rt = round_trip_cost_points(inst)

    def prep(df):
        d = df[df["date"].isin(pd.Index(pd.to_datetime(dates)))].copy()
        d["atr"] = d["date"].map(atr)
        d = d[d["atr"] > 0].copy()
        d["net_r"] = (d["points"] - rt) / d["atr"]
        d["win"] = d["points"] > 0
        return d.set_index(["date", "entry_mfo"])

    base = prep(run_ov(bars, bands, dm, fast_overlay=False))
    ov = prep(run_ov(bars, bands, dm, fast_overlay=True, fast_release="fixed",
                     fast_fixed_delay=h))
    j = base.join(ov[["net_r", "win"]], rsuffix="_ov", how="inner")
    j["d_net_r"] = j["net_r_ov"] - j["net_r"]
    j["slot"] = [m // PERIOD for (_, m) in j.index]   # decision slot index

    print(f"\n===== Q2: post-stop reversion capture by time-of-day (fixed delay h={h}) =====")
    tot = j["d_net_r"].sum()
    print(f"total capture over era = {tot:+.2f} R across n={len(j)} matched trades "
          f"(mean {j['d_net_r'].mean():+.4f} R/trade)")
    print(f"{'slot':>5} {'entry_tod':>9} {'n':>6} {'meandR':>9} {'sharedR':>8} "
          f"{'dwin':>7} {'p01_base':>9} {'p01_ov':>9}")
    g = []
    for slot, sub in j.groupby("slot"):
        share = sub["d_net_r"].sum() / tot if tot != 0 else np.nan
        winbase = sub["win"].mean()
        winov = sub["win_ov"].mean()
        p01b = sub["net_r"].quantile(0.01)
        p01o = sub["net_r_ov"].quantile(0.01)
        tod = int(slot) * PERIOD          # minutes from RTH open
        g.append(dict(slot=int(slot), tod_min=tod, n=len(sub),
                      meandR=sub["d_net_r"].mean(), share=share,
                      dwin=winov - winbase, p01_base=p01b, p01_ov=p01o))
        print(f"{int(slot):>5} {tod:>9} {len(sub):>6} {sub['d_net_r'].mean():>+9.4f} "
              f"{share:>+8.3f} {winov-winbase:>+7.3f} {p01b:>+9.4f} {p01o:>+9.4f}")
    pd.DataFrame(g).to_csv(OUT / f"q2_capture_by_tod_{inst}.csv", index=False)


# --------------------------------------------------------------------------- #
# Q3 - noise-reduction stop (cadence + fixed hold), drawdown-aware, clock & cont.
# --------------------------------------------------------------------------- #
def _calmar(sc):
    return (sc.net_r / sc.max_dd) if sc.max_dd > 0 else np.nan


def q3_row(inst, bars, bands, dm, dates, label, **runkw):
    tr = E.run(bars, bands, dm, fill_mode="next_open", require_vwap=True,
               stop_ref="both", **runkw)
    sc = score_candidate(tr, bars, dates, inst, label)
    return dict(arm=label, n=sc.trades, grossPt=sc.net_pt_per_trade +
                round_trip_cost_points(inst), sumR=sc.net_r, sharpe=sc.sharpe,
                maxDD=sc.max_dd, calmar=_calmar(sc), recent_sh=sc.recent_sharpe)


def q3_noise_reduction(inst, bars, bands, dm, dates):
    train, test = split_dates(dates)
    print("\n===== Q3: noise-reduction stop (cadence & fixed-hold), drawdown-aware =====")
    print("primary is drawdown-aware (maxDD, Calmar=sumR/maxDD), NOT Sharpe alone.")
    # cadence: N-min stop check ('decision' == 30). fixed-hold via fast_exit fixed delay.
    cadences = [("every_bar", dict(exit_check="every_bar")),
                ("cad5", dict(exit_check=5)),
                ("cad15", dict(exit_check=15)),
                ("cad30", dict(exit_check="decision"))]
    holds = [("hold2", dict(exit_check="every_bar", fast_overlay=True,
                            fast_release="fixed", fast_fixed_delay=2, fast_exit=True,
                            fast_entry=False)),
             ("hold4", dict(exit_check="every_bar", fast_overlay=True,
                            fast_release="fixed", fast_fixed_delay=4, fast_exit=True,
                            fast_entry=False)),
             ("hold6", dict(exit_check="every_bar", fast_overlay=True,
                            fast_release="fixed", fast_fixed_delay=6, fast_exit=True,
                            fast_entry=False))]
    for emode in ("clock", "threshold"):
        ekw = {} if emode == "clock" else dict(entry_mode="threshold",
                                               entry_buf_atr=0.0, entry_persist=1)
        for era_name, era in (("TRAIN", train), ("TEST", test)):
            rows = []
            for lbl, kw in cadences + holds:
                rows.append(q3_row(inst, bars, bands, dm, era,
                                   f"{lbl}", **{**ekw, **kw}))
            tab = pd.DataFrame(rows)
            b = tab.iloc[0]
            tab["dSharpe"] = tab["sharpe"] - b["sharpe"]
            tab["dCalmar"] = tab["calmar"] - b["calmar"]
            tab["dMaxDD"] = tab["maxDD"] - b["maxDD"]
            print(f"\n--- entry={emode}  era={era_name} "
                  f"(base: n={int(b['n'])} Sh {b['sharpe']:.3f} "
                  f"maxDD {b['maxDD']:.2f} Calmar {b['calmar']:.2f}) ---")
            print(tab[["arm", "n", "grossPt", "sumR", "sharpe", "dSharpe",
                       "maxDD", "dMaxDD", "calmar", "dCalmar", "recent_sh"]]
                  .to_string(index=False, float_format=lambda v: f"{v:.3f}"))
            tab.to_csv(OUT / f"q3_{emode}_{era_name}_{inst}.csv", index=False)


def main():
    inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
    OUT.mkdir(parents=True, exist_ok=True)
    bars, bands, dm, dates = load(inst)
    tr_, te_ = split_dates(dates)
    print(f"### fast-reversion diagnostics — {inst} ###")
    print(f"sessions={len(dates)}  TRAIN={len(tr_)} "
          f"({pd.Timestamp(tr_[0]).date()}->{pd.Timestamp(tr_[-1]).date()})  "
          f"TEST={len(te_)} ({pd.Timestamp(te_[0]).date()}->{pd.Timestamp(te_[-1]).date()})")
    q1_entry_exit_ic(inst, bars, bands, dm, dates)
    q2_capture_by_tod(inst, bars, bands, dm, dates)
    q3_noise_reduction(inst, bars, bands, dm, dates)
    print(f"\nartifacts -> {OUT}")


if __name__ == "__main__":
    main()
