"""Per-trade / per-day metrics with day-clustered inference (CLAUDE.md rule 12/13)."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import POINT_VALUE


def _cluster_t(day_pnl: pd.Series) -> tuple[float, float]:
    """Mean and t-stat of a per-day P&L series (the day IS the risk unit, rule 22)."""
    x = day_pnl.to_numpy(dtype=float)
    n = len(x)
    if n < 2:
        return float(np.mean(x)) if n else 0.0, 0.0
    m = x.mean()
    se = x.std(ddof=1) / np.sqrt(n)
    return m, (m / se if se > 0 else 0.0)


def summarize(trades: pd.DataFrame, inst: str, cost_pts_per_side: float,
              label: str = "") -> dict:
    """
    trades: columns date, side, points (gross, before costs).
    Costs applied as 2 * cost_pts_per_side per round-trip trade.
    Effect size = per-trade equal-weighted mean; P&L series = per-DAY SUM (rule 13).
    """
    if trades.empty:
        return dict(label=label, inst=inst, n_trades=0)
    t = trades.copy()
    rt_cost = 2.0 * cost_pts_per_side
    t["net_pts"] = t["points"] - rt_cost
    pv = POINT_VALUE[inst]

    # per-day summed P&L (dollars, 1 contract)
    day_gross = t.groupby("date")["points"].sum() * pv
    day_net = t.groupby("date")["net_pts"].sum() * pv
    # reindex to all traded days (already are); days with no trade contribute 0 —
    # but here we only have traded days, which is correct for per-trade-day P&L.

    m_g, tg = _cluster_t(day_gross)
    m_n, tn = _cluster_t(day_net)

    ann = 252.0
    sharpe_net = (day_net.mean() / day_net.std(ddof=1) * np.sqrt(ann)
                  if day_net.std(ddof=1) > 0 else 0.0)

    long_m = t[t.side == 1]["net_pts"].mean() if (t.side == 1).any() else np.nan
    short_m = t[t.side == -1]["net_pts"].mean() if (t.side == -1).any() else np.nan

    return dict(
        label=label, inst=inst, cost_pts=cost_pts_per_side,
        n_trades=int(len(t)), n_days=int(t["date"].nunique()),
        trades_per_day=len(t) / t["date"].nunique(),
        gross_pts_per_trade=float(t["points"].mean()),
        net_pts_per_trade=float(t["net_pts"].mean()),
        hit_rate=float((t["net_pts"] > 0).mean()),
        day_net_mean_usd=float(day_net.mean()),
        day_net_t=float(tn),
        day_gross_mean_usd=float(day_gross.mean()),
        day_gross_t=float(tg),
        sharpe_net_daily=float(sharpe_net),
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        long_net_pts=float(long_m), short_net_pts=float(short_m),
        long_total_usd=float(t[t.side == 1]["net_pts"].sum() * pv),
        short_total_usd=float(t[t.side == -1]["net_pts"].sum() * pv),
    )


def fmt(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label','')}: NO TRADES"
    return (
        f"{s['label']:<22s} n={s['n_trades']:>5d} ({s['trades_per_day']:.2f}/day) "
        f"gross={s['gross_pts_per_trade']:+.3f}pt net={s['net_pts_per_trade']:+.3f}pt "
        f"hit={s['hit_rate']:.3f} | day$net={s['day_net_mean_usd']:+.1f} "
        f"t={s['day_net_t']:+.2f} Sh={s['sharpe_net_daily']:.2f} | "
        f"L={s['long_net_pts']:+.3f}({s['n_long']}) S={s['short_net_pts']:+.3f}({s['n_short']})"
    )
