"""
Per-trade and per-session metrics with session-clustered inference
(RULES.md rules 12/13/19/21/22).

Units. Everything is reported in PIPS (1e-4 of quote for all four USD-quoted
majors), which is the tradable unit, and additionally in R = net pips / the
causal prior-session ATR(14) in pips, so a result is not flattered by the
volatility era it was measured in (rule 19).

The P&L series is the per-SESSION SUM of trade P&L, never the mean of that
session's trades (rule 13). Sessions with no trade contribute 0 to the
"zero-day" Sharpe, which is the deployable series; the trade-days-only Sharpe is
reported alongside it because they diverge.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .session import PIP, PIP_VALUE

ANN = 252.0


def _cluster_t(x: pd.Series) -> tuple[float, float]:
    v = x.to_numpy(dtype=float)
    if len(v) < 2:
        return (float(v.mean()) if len(v) else 0.0), 0.0
    m = v.mean()
    se = v.std(ddof=1) / np.sqrt(len(v))
    return float(m), float(m / se if se > 0 else 0.0)


def _sharpe(x: pd.Series) -> float:
    s = x.std(ddof=1)
    return float(x.mean() / s * np.sqrt(ANN)) if s > 0 else 0.0


def summarize(trades: pd.DataFrame, cost_pips_per_side: float,
              all_dates: pd.Index | np.ndarray | None = None,
              atr_pips: pd.Series | None = None, label: str = "",
              pair: str = "") -> dict:
    """
    trades: date, side, points (GROSS, in price units).
    all_dates: every tradable session in scope, so no-trade sessions enter the
               daily series as 0 (the deployable series).
    atr_pips: causal prior-session ATR(14) in pips, indexed by session date.
    """
    base = dict(label=label, pair=pair, cost_pips=cost_pips_per_side, n_trades=0)
    if trades is None or trades.empty:
        return base

    t = trades.copy()
    t["gross_pips"] = t["points"] / PIP
    t["net_pips"] = t["gross_pips"] - 2.0 * cost_pips_per_side

    if atr_pips is not None:
        a = t["date"].map(atr_pips)
        t["net_R"] = t["net_pips"] / a
        t["gross_R"] = t["gross_pips"] / a
    else:
        t["net_R"] = np.nan
        t["gross_R"] = np.nan

    day_g = t.groupby("date")["gross_pips"].sum()
    day_n = t.groupby("date")["net_pips"].sum()
    day_R = t.groupby("date")["net_R"].sum()
    if all_dates is not None:
        idx = pd.Index(pd.unique(np.asarray(all_dates))).sort_values()
        day_g0 = day_g.reindex(idx).fillna(0.0)
        day_n0 = day_n.reindex(idx).fillna(0.0)
        day_R0 = day_R.reindex(idx).fillna(0.0)
    else:
        day_g0, day_n0, day_R0 = day_g, day_n, day_R

    m_n, t_n = _cluster_t(day_n0)
    m_g, t_g = _cluster_t(day_g0)
    eq = day_n0.cumsum()
    maxdd = float((eq - eq.cummax()).min())

    return dict(
        label=label, pair=pair, cost_pips=cost_pips_per_side,
        n_trades=int(len(t)), n_sessions=int(len(day_n0)),
        n_trade_sessions=int(len(day_n)),
        trades_per_session=float(len(t) / len(day_n0)),
        gross_pips_per_trade=float(t["gross_pips"].mean()),
        net_pips_per_trade=float(t["net_pips"].mean()),
        hit_rate=float((t["net_pips"] > 0).mean()),
        total_net_pips=float(t["net_pips"].sum()),
        total_net_R=float(t["net_R"].sum()),
        net_R_per_trade=float(t["net_R"].mean()),
        day_net_pips=float(m_n), day_net_t=float(t_n),
        day_gross_pips=float(m_g), day_gross_t=float(t_g),
        sharpe_net_zeroday=_sharpe(day_n0),
        sharpe_net_tradedays=_sharpe(day_n),
        sharpe_gross_zeroday=_sharpe(day_g0),
        sharpe_net_R_zeroday=_sharpe(day_R0),
        maxdd_pips=maxdd,
        day_net_usd_1lot=float(m_n * PIP_VALUE),
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        long_net_pips=float(t.loc[t.side == 1, "net_pips"].mean()) if (t.side == 1).any() else np.nan,
        short_net_pips=float(t.loc[t.side == -1, "net_pips"].mean()) if (t.side == -1).any() else np.nan,
        frac_stop=float((t["reason"] == "stop").mean()) if "reason" in t else np.nan,
        frac_eod=float((t["reason"] == "eod").mean()) if "reason" in t else np.nan,
        frac_flip=float((t["reason"] == "flip").mean()) if "reason" in t else np.nan,
        mean_hold_min=float((t["exit_mfo"] - t["entry_mfo"]).mean()) if "exit_mfo" in t else np.nan,
    )


def fmt(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label',''):<26s} NO TRADES"
    return (f"{s['label']:<26s} n={s['n_trades']:>6d} ({s['trades_per_session']:.2f}/s) "
            f"gross={s['gross_pips_per_trade']:+7.3f}p net={s['net_pips_per_trade']:+7.3f}p "
            f"hit={s['hit_rate']:.3f} | day={s['day_net_pips']:+7.3f}p t={s['day_net_t']:+6.2f} "
            f"Sh0={s['sharpe_net_zeroday']:+6.3f} ShR={s['sharpe_net_R_zeroday']:+6.3f} "
            f"| netR={s['total_net_R']:+8.1f} dd={s['maxdd_pips']:+9.1f}p")


HEADER = (f"{'label':<26s} {'n':>8s} {'per-sess':>9s} {'gross':>9s} {'net':>9s} "
          f"{'hit':>6s} {'day_net':>9s} {'t':>7s} {'Sh0':>7s} {'ShR':>7s} "
          f"{'netR':>9s} {'maxDD':>10s}")
