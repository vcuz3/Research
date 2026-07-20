"""Ad-hoc: win rate and realized reward:risk (payoff ratio) for the champion,
the early-flat forward-shadow candidate, the partial-TP survivor, and the
early-flat + partial-TP combination. NQ, net of costs, common post-lb90 sample.

Not a registered experiment -- descriptive breakdown requested to read win/RR of
configs already evaluated in EXP-0013 (early-flat) and the exit study (tp1.0_50).

  python -m futures.nq.noise_vwap.scripts.winrate_rr
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S

LOOKBACK = 90
POINT_VALUE = {"NQ": 20.0}
TICK = {"NQ": 0.25}
FEE_USD_PER_SIDE = 2.25


def rt_cost(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def common_dates(bars):
    return np.sort(S.noise_bands(bars, LOOKBACK)["sdate"].unique())


def score(trades, bars, dates, inst, label):
    idx = pd.Index(pd.to_datetime(dates))
    t = trades[trades["date"].isin(idx)].copy()
    atr = bars.groupby("sdate")["atr"].first()
    t["atr"] = t["date"].map(atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    c = rt_cost(inst)
    t["net_pts"] = t["points"] - c
    t["net_r"] = t["net_pts"] / t["atr"]

    n = len(t)
    wins = t[t["net_pts"] > 0]
    losses = t[t["net_pts"] <= 0]
    win_rate = len(wins) / n
    # payoff ratio in net R and in net points
    mean_win_r = wins["net_r"].mean() if len(wins) else 0.0
    mean_loss_r = losses["net_r"].mean() if len(losses) else 0.0
    rr_r = mean_win_r / abs(mean_loss_r) if mean_loss_r != 0 else float("nan")
    mean_win_pt = wins["net_pts"].mean() if len(wins) else 0.0
    mean_loss_pt = losses["net_pts"].mean() if len(losses) else 0.0
    rr_pt = mean_win_pt / abs(mean_loss_pt) if mean_loss_pt != 0 else float("nan")
    # daily Sharpe (zero-trade days included) for context
    day = t.groupby("date")["net_r"].sum().reindex(idx, fill_value=0.0)
    sd = day.std(ddof=1)
    sharpe = day.mean() / sd * np.sqrt(252) if sd > 0 else 0.0
    expectancy_r = t["net_r"].mean()

    print(f"{label:<28} n={n:>5}  win%={win_rate*100:5.1f}  "
          f"RR(R)={rr_r:4.2f}  RR(pt)={rr_pt:4.2f}  "
          f"avgW={mean_win_r:+.3f}R avgL={mean_loss_r:+.3f}R  "
          f"exp={expectancy_r:+.4f}R  netR={t['net_r'].sum():+7.1f}  Sh={sharpe:4.2f}")


def main():
    inst = "NQ"
    bars = S.load_session(inst, "RTH")
    bands = S.noise_bands(bars, LOOKBACK)
    dec = S.decision_mfos(30, int(bars["mfo"].max()))
    dates = common_dates(bars)

    def run(**kw):
        return E.run(bars, bands, dec, fill_mode="next_open", require_vwap=True,
                     exit_check="every_bar", **kw)

    print(f"NQ  RT cost={rt_cost(inst):.3f} pt  common post-lb90; 30m clock; VWAP gate; "
          f"every-bar stop; next-open. Win = net P&L > 0. RR = meanWin/|meanLoss|.")
    print("-" * 118)
    score(run(), bars, dates, inst, "champion (cutoff0)")
    score(run(flat_before_close=45), bars, dates, inst, "early-flat 45 (candidate)")
    score(run(tp_atr=1.0, tp_frac=0.5), bars, dates, inst, "partial-TP tp1.0_50")
    score(run(flat_before_close=45, tp_atr=1.0, tp_frac=0.5), bars, dates, inst,
          "early-flat45 + tp1.0_50")


if __name__ == "__main__":
    main()
