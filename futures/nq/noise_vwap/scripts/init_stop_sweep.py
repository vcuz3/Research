"""
INITIAL-stop optimisation for CFD / fixed-%-risk deployment of the NQ noise_vwap
tp0.75_67 operating point.

Frame (rule 12/19/21/22): on a CFD you size continuously, so risk PER TRADE is a
fixed fraction of the account. Commit that fraction to a stop at `k*ATR` adverse of
the fill. Then size = risk_$/(k*ATR*pointvalue) and the trade's account result is
    R = net_points / (k*ATR)
in units of the fixed risk fraction. Everything is measured in R (vol-scaled by the
causal prior-14-session ATR -- this IS the volatility scaling: bigger ATR -> wider
stop -> smaller size). Daily R = sum of trade R that day (flat/zero-trade days kept).

The initial stop is a hard CAP layered on the existing every-bar band/VWAP trail
(engine2 init_stop_atr): the effective stop is the tighter of the two, so a wide k
only binds on a fast adverse move the (already ~0.07-ATR-tight) band trail has not
caught -- i.e. it caps the gap/next-open loss tail. A tight k instead clips into the
band trail itself.

What to read:
  * Sharpe is ~SCALE-INVARIANT to k wherever the cap does NOT bind (constant-% sizing
    scales daily R by 1/k uniformly -> mean/std ratio unchanged). Sharpe only moves
    where k reshapes the trade outcomes (binding: clips winners early / caps losers).
  * bind% = share of trades exited by the initial cap (reason 'istop'). Near 0 => the
    cap is inert (pure tail insurance); rising => it is changing the strategy.
  * maxDD_R / Calmar / avgL_R are the deployable levers: a wider cap under-uses risk
    (small R magnitude, gentle DD); a tighter cap risks the known variance-reduction
    trap (memory: MAE/MFE loser side == noise; "do not tighten the stop").

Any Sharpe UPLIFT from tightening must clear a claim-matched Null C before it is
banked (standing rule + gate-nullc). This script is a sizing/geometry screen, not an
edge test.

Run:
  python -m futures.nq.noise_vwap.scripts.init_stop_sweep
  python -m futures.nq.noise_vwap.scripts.init_stop_sweep save   # + write EXP-0023 report
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import session as S
from ..core import engine2 as E

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0023"
LOOKBACK = 90
POINT_VALUE_NQ = 20.0
TICK = 0.25
FEE_USD_PER_SIDE = 2.25
RT_COST_BT = 2.0 * (FEE_USD_PER_SIDE / POINT_VALUE_NQ + 0.25 * TICK)  # ~0.35 pt
RECENT_CUT = pd.Timestamp("2025-01-01")

# tp0.75_67 primary operating point (STUDIES.md); vary ONLY the initial stop.
BASE_CFG = dict(fill_mode="next_open", require_vwap=True, exit_check="every_bar",
                tp_atr=0.75, tp_frac=0.67)
K_GRID = [0.10, 0.15, 0.20, 0.25, 0.30, 0.40, 0.50, 0.75, 1.00, 1.50, 5.00]


def daily_R_metrics(tr: pd.DataFrame, k: float, dates: pd.Index) -> dict:
    """R = net_pts / (k*ATR); constant-% sizing => account result is R units."""
    t = tr[tr["date"].isin(dates)].copy()
    risk = k * t["atr"]
    t["R"] = t["net_pts"] / risk
    win = t["net_pts"] > 0
    aw = t.loc[win, "R"].mean()
    al = t.loc[~win, "R"].mean()
    day = t.groupby("date")["R"].sum().reindex(dates, fill_value=0.0)
    sd = day.std(ddof=1)
    curve = day.cumsum()
    maxdd = float((curve.cummax() - curve).max())
    sumR = float(day.sum())
    sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else np.nan
    return dict(n=len(t), bind=float((t["reason"] == "istop").mean()),
                win=float(win.mean()), aw=float(aw), al=float(al),
                rr=float(aw / abs(al)) if al else np.nan,
                sharpe=sharpe, sumR=sumR, maxdd=maxdd,
                calmar=(sumR / maxdd) if maxdd > 0 else np.nan)


def main(save=False):
    bars = S.load_session("NQ", "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    atr_by_date = bars.groupby("sdate")["atr"].first()
    all_dates = pd.Index(pd.to_datetime(np.sort(bands["sdate"].unique())))
    recent = all_dates[all_dates >= RECENT_CUT]

    L = []
    L.append("=" * 118)
    L.append("INITIAL-STOP SWEEP -- NQ tp0.75_67, constant-% CFD sizing, R = net_pts/(k*ATR)")
    L.append(f"(RT cost {RT_COST_BT:.3f} pt, lookback 90; k=5.0 ~ no cap = baseline tape).")
    L.append("=" * 118)
    L.append(f"{'k(ATR)':>7} | {'era':<6} {'n':>5} {'bind%':>6} {'win%':>5} "
             f"{'avgW_R':>7} {'avgL_R':>7} {'RR':>5} {'Sharpe':>7} {'sumR':>8} "
             f"{'maxDD_R':>8} {'Calmar':>7}")
    rows = []
    for k in K_GRID:
        tr = E.run(bars, bands, dm, init_stop_atr=k, **BASE_CFG)
        tr["date"] = pd.to_datetime(tr["date"])
        tr["atr"] = tr["date"].map(atr_by_date)
        tr = tr[np.isfinite(tr["atr"]) & (tr["atr"] > 0)].copy()
        tr["net_pts"] = tr["points"] - RT_COST_BT
        L.append("-" * 118)
        for era, dates in (("full", all_dates), ("2025+", recent)):
            m = daily_R_metrics(tr, k, dates)
            L.append(f"{k:>7.2f} | {era:<6} {m['n']:>5} {m['bind']*100:>5.1f}% "
                     f"{m['win']*100:>4.1f}% {m['aw']:>+6.2f}R {m['al']:>+6.2f}R "
                     f"{m['rr']:>5.2f} {m['sharpe']:>7.2f} {m['sumR']:>+8.1f} "
                     f"{m['maxdd']:>8.1f} {m['calmar']:>7.2f}")
            rows.append(dict(k=k, era=era, **m))

    report = "\n".join(L)
    print(report)
    if save:
        OUT.mkdir(parents=True, exist_ok=True)
        (OUT / "init_stop_sweep.txt").write_text(report + "\n")
        pd.DataFrame(rows).to_csv(OUT / "init_stop_sweep.csv", index=False)
        print(f"\nsaved -> {OUT / 'init_stop_sweep.txt'}")


if __name__ == "__main__":
    main(save=(len(sys.argv) > 1 and sys.argv[1] == "save"))
