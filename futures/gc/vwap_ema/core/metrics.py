"""
Metrics for the VWAP-EMA bracket.

Two views, both day-clustered (the day is the risk unit; rule 13/22):

  summarize_contract : fixed 1-contract $ P&L -- the honest per-trade edge read
      (gross AND net, rule 20), day-clustered Sharpe / t-stat / maxDD / Calmar.
  summarize_compound : the user's deployment model -- risk 1% of current equity
      per trade, compounded via LOG returns. Per trade the fractional P&L is
      risk_frac * R_net (R_net = net points / frozen 1R). Reports total compounded
      return, annualised Sharpe on the daily log-return series (flat day = 0), and
      fractional max drawdown. This is the metric comparable to the paper's
      headline (Sharpe 3.99, +102% return, maxDD 5.1%).

Costs are applied as 2*cost_pts_per_side per round trip and swept by the caller.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import POINT_VALUE

ANN = 252.0


def _max_dd_abs(equity: np.ndarray) -> float:
    if equity.size == 0:
        return 0.0
    peak = np.maximum.accumulate(equity)
    return float(np.max(peak - equity))


def _net_R(trades: pd.DataFrame, cost_R: float) -> pd.DataFrame:
    t = trades.copy()
    gross_R = (t["gross_R"] if "gross_R" in t else
               np.where(t["risk_pts"] > 0, t["points"] / t["risk_pts"], np.nan))
    t["gross_R"] = gross_R
    t["R"] = t["gross_R"] - cost_R
    t["net_pts"] = t["R"] * t["risk_pts"]
    return t


def summarize_contract(trades: pd.DataFrame, all_dates, cost_R: float,
                       label: str = "") -> dict:
    ndays = int(pd.Series(all_dates).nunique())
    years = ndays / ANN if ndays else np.nan
    if trades.empty:
        return dict(label=label, n_trades=0, n_days_all=ndays)
    t = _net_R(trades, cost_R)
    t["net_usd"] = t["net_pts"] * POINT_VALUE
    t["gross_usd"] = t["points"] * POINT_VALUE
    win = t["net_pts"] > 0
    wins = t.loc[win, "net_pts"]; losses = t.loc[~win, "net_pts"]
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    payoff = (avg_win / abs(avg_loss)) if avg_loss < 0 else np.nan
    gross_win = t["gross_R"] > 0
    gross_pf_den = -float(t.loc[~gross_win, "gross_R"].sum())
    net_pf_den = -float(t.loc[~win, "R"].sum())
    idx = pd.Index(pd.Series(all_dates).unique())
    day_net = t.groupby("date")["net_usd"].sum().reindex(idx, fill_value=0.0).sort_index()
    day_gross = t.groupby("date")["gross_usd"].sum().reindex(idx, fill_value=0.0).sort_index()
    sd = day_net.std(ddof=1); sdg = day_gross.std(ddof=1)
    sharpe_net = float(day_net.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0
    sharpe_gross = float(day_gross.mean() / sdg * np.sqrt(ANN)) if sdg > 0 else 0.0
    n = len(day_net); se = sd / np.sqrt(n) if n > 1 else 0.0
    day_t = float(day_net.mean() / se) if se > 0 else 0.0
    equity = day_net.cumsum().to_numpy()
    total_net = float(t["net_usd"].sum()); total_gross = float(t["gross_usd"].sum())
    maxdd = _max_dd_abs(equity)
    ann_profit = total_net / years if years and years > 0 else np.nan
    calmar = float(ann_profit / maxdd) if maxdd > 0 else np.nan
    return dict(
        label=label, cost_R=cost_R, n_trades=int(len(t)),
        n_days_traded=int(t["date"].nunique()), n_days_all=ndays,
        trades_per_day=len(t) / max(1, t["date"].nunique()),
        reasons=t["reason"].value_counts().to_dict(),
        gross_pts_per_trade=float(t["points"].mean()),
        net_pts_per_trade=float(t["net_pts"].mean()),
        gross_expectancy_R=float(t["gross_R"].mean()),
        expectancy_R=float(t["R"].mean()), win_rate=float(win.mean()),
        gross_profit_factor=(float(t.loc[gross_win, "gross_R"].sum()) / gross_pf_den
                             if gross_pf_den > 0 else np.nan),
        net_profit_factor=(float(t.loc[win, "R"].sum()) / net_pf_den
                           if net_pf_den > 0 else np.nan),
        avg_win_pts=avg_win, avg_loss_pts=avg_loss, payoff_ratio=payoff,
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        total_gross_usd=total_gross, total_net_usd=total_net,
        sharpe_net_daily=sharpe_net, sharpe_gross_daily=sharpe_gross,
        day_net_t=day_t, max_dd_usd=maxdd, calmar=calmar,
        intrabar_exit_1s_frac=float(t["used_1s"].mean()) if "used_1s" in t else np.nan,
    )


def summarize_compound(trades: pd.DataFrame, all_dates, cost_R: float,
                       risk_frac: float = 0.01, e0: float = 10000.0,
                       label: str = "") -> dict:
    """1%-risk-per-trade, log-return-compounded equity. daily log-return over ALL
    usable sessions (flat = 0); Sharpe on that series."""
    ndays = int(pd.Series(all_dates).nunique())
    if trades.empty:
        return dict(label=label, n_trades=0)
    t = _net_R(trades, cost_R).sort_values(["date", "exit_tsec"])
    f = risk_frac * t["R"].to_numpy()                 # fractional P&L per trade
    f = np.clip(f, -0.999, None)                       # guard log domain
    logret = np.log1p(f)
    t = t.assign(logret=logret)
    idx = pd.Index(pd.Series(all_dates).unique())
    day_lr = t.groupby("date")["logret"].sum().reindex(idx, fill_value=0.0).sort_index()
    equity = e0 * np.exp(day_lr.cumsum().to_numpy())
    peak = np.maximum.accumulate(equity)
    max_dd_frac = float(np.max((peak - equity) / peak)) if equity.size else 0.0
    sd = day_lr.std(ddof=1)
    sharpe = float(day_lr.mean() / sd * np.sqrt(ANN)) if sd > 0 else 0.0
    total_ret = float(np.expm1(day_lr.sum()))
    years = ndays / ANN if ndays else np.nan
    cagr = float((equity[-1] / e0) ** (1.0 / years) - 1.0) if years and years > 0 else np.nan
    calmar = float(cagr / max_dd_frac) if max_dd_frac > 0 else np.nan
    return dict(
        label=label, cost_R=cost_R, n_trades=int(len(t)),
        total_return=total_ret, cagr=cagr, sharpe_daily=sharpe,
        max_dd_frac=max_dd_frac, calmar=calmar,
        final_equity=float(equity[-1]) if equity.size else e0,
        expectancy_R=float(t["R"].mean()),
    )


def fmt_contract(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label',''):<16s}: NO TRADES"
    cal = s['calmar'] if not (isinstance(s['calmar'], float) and np.isnan(s['calmar'])) else float('nan')
    return (f"{s['label']:<16s} n={s['n_trades']:>4d} ({s['trades_per_day']:.2f}/d) "
            f"win={s['win_rate']:.3f} pay={s['payoff_ratio']:.2f} expR={s['expectancy_R']:+.3f} | "
            f"gross={s['gross_pts_per_trade']:+.3f} net={s['net_pts_per_trade']:+.3f}pt | "
            f"ShN={s['sharpe_net_daily']:+.2f} ShG={s['sharpe_gross_daily']:+.2f} "
            f"t={s['day_net_t']:+.2f} Cal={cal:+.2f} "
            f"intrabarExit1s={s.get('intrabar_exit_1s_frac',float('nan')):.2f}")


def fmt_compound(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label',''):<16s}: NO TRADES"
    return (f"{s['label']:<16s} 1%-risk: totRet={s['total_return']:+.1%} "
            f"CAGR={s['cagr']:+.2%} Sharpe={s['sharpe_daily']:+.2f} "
            f"maxDD={s['max_dd_frac']:.1%} Calmar={s['calmar']:+.2f} "
            f"finalEq=${s['final_equity']:,.0f}")
