"""
Per-trade / per-day metrics for the VWAP-band fade, with day-clustered inference
(CLAUDE.md rule 12/13/22). The day is the risk unit; Sharpe and Calmar are built
on the per-SESSION net P&L reindexed over ALL usable sessions (0 on flat days),
because that is the series an account actually experiences (rule 22).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import POINT_VALUE

ANN = 252.0


def _max_drawdown(equity: np.ndarray) -> float:
    """Max peak-to-trough drop of a cumulative $ equity curve (>=0)."""
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def summarize(trades: pd.DataFrame, all_dates: pd.Series, inst: str,
              cost_pts_per_side: float, label: str = "") -> dict:
    """
    trades:    columns date, side, points (gross, pre-cost), risk_pts, reason.
    all_dates: every usable session date (for a flat-day-aware daily series).
    Costs: 2 * cost_pts_per_side per round-trip. Effect size = per-trade mean;
    risk series = per-SESSION summed net $ over all_dates (rule 13/22).
    """
    pv = POINT_VALUE[inst]
    ndays_all = int(pd.Series(all_dates).nunique())
    years = ndays_all / ANN if ndays_all else np.nan

    if trades.empty:
        return dict(label=label, inst=inst, n_trades=0, n_days_all=ndays_all)

    t = trades.copy()
    rt_cost = 2.0 * cost_pts_per_side
    t["net_pts"] = t["points"] - rt_cost
    t["net_usd"] = t["net_pts"] * pv
    t["gross_usd"] = t["points"] * pv
    # realized R (signed) on the frozen 1R risk distance
    t["R"] = np.where(t["risk_pts"] > 0, t["net_pts"] / t["risk_pts"], np.nan)

    win = t["net_pts"] > 0
    wins = t.loc[win, "net_pts"]
    losses = t.loc[~win, "net_pts"]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else np.nan

    # per-session net $ over ALL usable sessions (flat day = 0)
    day_net = t.groupby("date")["net_usd"].sum().reindex(
        pd.Index(pd.Series(all_dates).unique()), fill_value=0.0).sort_index()
    day_gross = t.groupby("date")["gross_usd"].sum().reindex(
        pd.Index(pd.Series(all_dates).unique()), fill_value=0.0).sort_index()

    sd = day_net.std(ddof=1)
    sharpe_net = float(day_net.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0
    sdg = day_gross.std(ddof=1)
    sharpe_gross = float(day_gross.mean() / sdg * np.sqrt(ANN)) if sdg > 0 else 0.0

    # day-clustered t-stat on the (traded-and-flat) daily series
    n = len(day_net)
    se = sd / np.sqrt(n) if n > 1 else 0.0
    day_t = float(day_net.mean() / se) if se > 0 else 0.0

    # equity / drawdown / Calmar (MAR = annual $ profit / max $ drawdown)
    equity = day_net.cumsum().to_numpy()
    total_net = float(t["net_usd"].sum())
    total_gross = float(t["gross_usd"].sum())
    maxdd = _max_drawdown(equity)
    ann_profit = total_net / years if years and years > 0 else np.nan
    calmar = float(ann_profit / maxdd) if maxdd > 0 else np.nan

    reasons = t["reason"].value_counts().to_dict()

    return dict(
        label=label, inst=inst, cost_pts=cost_pts_per_side,
        n_trades=int(len(t)), n_days_traded=int(t["date"].nunique()),
        n_days_all=ndays_all, trades_per_day=len(t) / max(1, t["date"].nunique()),
        same_bar=int(t["same_bar"].sum()) if "same_bar" in t else 0,
        reasons=reasons,
        gross_pts_per_trade=float(t["points"].mean()),
        net_pts_per_trade=float(t["net_pts"].mean()),
        expectancy_R=float(t["R"].mean()),
        win_rate=float(win.mean()),
        avg_win_pts=avg_win, avg_loss_pts=avg_loss, payoff_ratio=payoff,
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        long_net_usd=float(t.loc[t.side == 1, "net_usd"].sum()),
        short_net_usd=float(t.loc[t.side == -1, "net_usd"].sum()),
        total_gross_usd=total_gross, total_net_usd=total_net,
        day_net_mean_usd=float(day_net.mean()), day_net_t=day_t,
        sharpe_net_daily=sharpe_net, sharpe_gross_daily=sharpe_gross,
        max_dd_usd=maxdd, ann_profit_usd=ann_profit, calmar=calmar,
    )


def fmt(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label',''):<18s}: NO TRADES"
    return (
        f"{s['label']:<18s} n={s['n_trades']:>5d} ({s['trades_per_day']:.2f}/day) "
        f"win={s['win_rate']:.3f} payoff={s['payoff_ratio']:.2f} "
        f"expR={s['expectancy_R']:+.3f} | net={s['net_pts_per_trade']:+.3f}pt "
        f"(${s['net_pts_per_trade']*100:+.1f}) tot=${s['total_net_usd']:+,.0f} | "
        f"Sh={s['sharpe_net_daily']:+.2f} t={s['day_net_t']:+.2f} "
        f"Calmar={s['calmar'] if not np.isnan(s['calmar']) else float('nan'):+.2f} "
        f"maxDD=${s['max_dd_usd']:,.0f}"
    )
