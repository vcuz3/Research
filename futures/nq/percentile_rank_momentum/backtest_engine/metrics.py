"""Audited-engine metrics plus the HYP-0001 reporting contract."""
from __future__ import annotations

import numpy as np
import pandas as pd
import statsmodels.api as sm

from futures.nq.noise_vwap.core import metrics as audited_metrics
from futures.nq.noise_vwap.core.data import POINT_VALUE, TICK
from futures.nq.noise_vwap.scripts.export_trades import vol_target_equity


def cost_points_per_side(
    instrument: str, slippage_ticks: float = 0.5, fee_usd: float = 2.25
) -> float:
    inst = instrument.upper()
    return float(slippage_ticks * TICK[inst] + fee_usd / POINT_VALUE[inst])


def cluster_t(values: pd.Series, groups: pd.Series) -> float:
    good = values.notna() & groups.notna()
    y = values[good].to_numpy(float)
    g = groups[good].to_numpy()
    if len(y) < 2 or len(np.unique(g)) < 2:
        return np.nan
    fit = sm.OLS(y, np.ones((len(y), 1))).fit(
        cov_type="cluster", cov_kwds={"groups": g, "use_correction": True}
    )
    return float(fit.tvalues[0])


def _sharpe(values: pd.Series) -> float:
    sd = values.std(ddof=1)
    return float(values.mean() / sd * np.sqrt(252.0)) if sd > 0 else 0.0


def summarize(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    instrument: str,
    label: str,
    cost_per_side: float,
    eligible_dates: pd.Index | None = None,
) -> dict:
    inst = instrument.upper()
    dates = pd.Index(
        eligible_dates if eligible_dates is not None else bars["date"].drop_duplicates().sort_values()
    )
    if trades.empty:
        return {"label": label, "inst": inst, "n_trades": 0}
    t = trades.copy()
    rt_cost = 2.0 * cost_per_side
    t["net_points"] = t["points"] - rt_cost
    t["gross_ticks"] = t["points"] / TICK[inst]
    t["net_ticks"] = t["net_points"] / TICK[inst]
    base = audited_metrics.summarize(t, inst, cost_per_side, label)
    daily = (
        t.groupby("date")["net_points"].sum().reindex(dates).fillna(0.0) * POINT_VALUE[inst]
    )
    trade_dates = pd.Index(t["date"].drop_duplicates())
    trade_daily = daily.reindex(dates.intersection(trade_dates))
    vt = vol_target_equity(bars, t, cost_per_side) if inst == "NQ" else None
    equity = pd.concat([pd.Series([0.0]), daily.cumsum().reset_index(drop=True)], ignore_index=True)
    drawdown = equity - equity.cummax()
    years = max(len(dates) / 252.0, 1.0 / 252.0)
    base.update({
        "gross_ticks_per_trade": float(t["gross_ticks"].mean()),
        "net_ticks_per_trade": float(t["net_ticks"].mean()),
        "net_ticks_cluster_t": cluster_t(t["net_ticks"], t["date"]),
        "zero_day_sharpe": _sharpe(daily),
        "trade_day_sharpe": _sharpe(trade_daily),
        "vol_targeted_sharpe": _sharpe(vt["ret"]) if vt is not None else np.nan,
        "trades_per_year": float(len(t) / years),
        "turnover_round_trips": int(len(t)),
        "exposure_fraction": float(
            (t["exit_tod"] - t["entry_tod"]).clip(lower=0).sum() / (len(dates) * 390.0)
        ),
        "max_drawdown_usd_1_contract": float(drawdown.min()),
        "total_net_usd_1_contract": float(t["net_points"].sum() * POINT_VALUE[inst]),
        "cost_points_round_trip": rt_cost,
        "cost_ticks_round_trip": rt_cost / TICK[inst],
        "eligible_sessions": int(len(dates)),
    })
    return base
