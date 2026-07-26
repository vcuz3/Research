"""Causal momentum-in-VEI-regime strategy simulator (HYP-0001 / EXP-0004).

At each 30-min RTH decision bar m (close), if the VEI gate holds, take
side = sign(trailing `past_win`-min return); FILL at the next bar open (m+1); EXIT at
the open `horizon` minutes later (flat at the session close). Bets are non-overlapping
single positions (decision period == hold), so daily P&L is a plain sum of per-bet net
R (rule 12/13, no concurrency). Fills are next-open only (rule 1/2); costs are an
explicit conservative per-interval round trip (rule 6/20).

Gate modes: 'high' (VEI>T), 'low' (VEI<=T), 'all' (ignore VEI). Nothing here uses any
information after the decision bar to DECIDE; the exit is a fixed causal horizon.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
TICK = {"NQ": 0.25, "ES": 0.25}
FEE_USD_PER_SIDE = 2.25


def round_trip_cost_points(inst: str) -> float:
    per_side = FEE_USD_PER_SIDE / POINT_VALUE[inst] + 0.25 * TICK[inst]
    return 2.0 * per_side


def simulate(bars: pd.DataFrame, dm, vei: np.ndarray, *, mode: str, thr: float,
             horizon: int, cost_pts: float, past_win: int = 30,
             gate_keys: set | None = None,
             allow_overlap: bool = False) -> pd.DataFrame:
    """Run the momentum strategy. `vei` is aligned to bars.index (may be all-NaN if
    `mode`=='all'/gate_keys given). `gate_keys` (set of (date,mfo)) overrides the VEI
    gate when supplied (used by the matched-count random null). Returns one row per
    bet: date, mfo, side, entry, exit, points, net.

    `allow_overlap` controls the ESTIMAND (rule 13). The default False enforces the
    single-position book HYP-0001 declares: a decision whose fill would land before
    the previous bet's exit is skipped. Pass True only to model a book that really
    does run concurrent positions — `score()` sums per-bet R per day, so with
    overlap that daily figure is a MULTI-unit book, not the one-unit book the
    non-overlapping cells describe. This bites whenever `horizon` exceeds the
    spacing of `dm` (e.g. a 60-min hold on a 30-min clock runs 2 deep).
    """
    order = bars.sort_values(["sdate", "mfo"]).index
    b = bars.loc[order].reset_index(drop=True)
    v = pd.Series(vei, index=bars.index).loc[order].to_numpy()  # aligned to b rows
    rows = []
    for (sd,), g in b.groupby(["sdate"], sort=False):
        idx = g.index.to_numpy()
        mfo = g["mfo"].to_numpy(int)
        o = g["open"].to_numpy(float)
        c = g["close"].to_numpy(float)
        vv = v[idx]
        n = len(g)
        pos = {int(m): i for i, m in enumerate(mfo)}
        open_until = -1                      # exit index of the bet currently held
        for m in dm:
            i = pos.get(int(m))
            if i is None or i + 1 >= n:
                continue
            entry_idx = i + 1
            exit_idx = min(i + 1 + horizon, n - 1)
            if exit_idx <= entry_idx:
                continue
            if not allow_overlap and entry_idx < open_until:
                continue                     # still in a position -> no new bet
            # gate
            if gate_keys is not None:
                if (sd, int(m)) not in gate_keys:
                    continue
            elif mode == "high":
                if not (np.isfinite(vv[i]) and vv[i] > thr):
                    continue
            elif mode == "low":
                if not (np.isfinite(vv[i]) and vv[i] <= thr):
                    continue
            # else 'all': no gate
            j0 = max(0, i - past_win)
            past_ret = c[i] - c[j0]
            side = 1 if past_ret > 0 else (-1 if past_ret < 0 else 0)
            if side == 0:
                continue
            entry = o[entry_idx]; exit_ = o[exit_idx]
            points = side * (exit_ - entry)
            open_until = exit_idx
            rows.append({"date": sd, "mfo": int(m), "side": side,
                         "entry": entry, "exit": exit_, "points": points,
                         "net": points - cost_pts,
                         "entry_i": entry_idx, "exit_i": exit_idx})
    return pd.DataFrame(rows)


@dataclass(frozen=True)
class Score:
    name: str
    trades: int
    gross_pts: float
    net_pts: float
    net_pt_per_trade: float
    net_r: float
    sharpe: float
    day_t: float
    hit: float
    max_dd: float
    recent_sharpe: float


def score(trades: pd.DataFrame, dates: np.ndarray, daily_atr: pd.Series,
          name: str) -> Score:
    dates_idx = pd.Index(pd.to_datetime(dates))
    if trades.empty:
        return Score(name, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0)
    t = trades.copy()
    t["atr"] = t["date"].map(daily_atr)
    t = t[np.isfinite(t["atr"]) & (t["atr"] > 0)].copy()
    t["net_r"] = t["net"] / t["atr"]
    day = t.groupby("date")["net_r"].sum().reindex(dates_idx, fill_value=0.0)
    sd = float(day.std(ddof=1))
    sharpe = float(day.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    day_t = float(day.mean() / (sd / np.sqrt(len(day)))) if sd > 0 else 0.0
    equity = day.cumsum()
    max_dd = float((equity.cummax() - equity).max())
    recent = dates_idx[dates_idx >= pd.Timestamp("2023-01-01")]
    rday = (t[t["date"] >= pd.Timestamp("2023-01-01")].groupby("date")["net_r"].sum()
            .reindex(recent, fill_value=0.0))
    rsd = float(rday.std(ddof=1))
    recent_sharpe = float(rday.mean() / rsd * np.sqrt(252)) if rsd > 0 else 0.0
    return Score(name, len(t), float(t["points"].sum()), float(t["net"].sum()),
                 float(t["net"].mean()), float(day.sum()), sharpe, day_t,
                 float((t["net"] > 0).mean()), max_dd, recent_sharpe)


def fmt(sc: Score) -> str:
    return (f"{sc.name:>16} n={sc.trades:>5} grossPt={sc.gross_pts:>+9.1f} "
            f"netPt={sc.net_pts:>+9.1f} net/t={sc.net_pt_per_trade:>+.4f} "
            f"netR={sc.net_r:>+8.2f} Sh={sc.sharpe:>+.3f} t={sc.day_t:>+.2f} "
            f"hit={sc.hit:.3f} maxDD={sc.max_dd:>6.2f} 23+Sh={sc.recent_sharpe:>+.3f}")
