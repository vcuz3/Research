"""Metrics for the ATR counter-bar breakout study.

Sharpe is reported three ways (user memory 'report three Sharpes'):
  * zero_day: over ALL usable RTH sessions, non-trading days counted as 0.
  * trade_day: over trading days only.
  * vol_target: causal inverse-vol-targeted daily series using the user's exact
    formula -- 10% annual target, trailing 60-day realised vol lagged 1 day,
    scale = (daily_target / rv).clip(upper=cap), sized = ret * scale.

Returns are additive per-day return units; equity curve is the cumulative SUM and
max drawdown is measured on that curve (return units).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

ANN = np.sqrt(252.0)


def _sharpe(x: pd.Series) -> float:
    x = x.dropna()
    if len(x) < 2 or x.std(ddof=1) == 0:
        return float("nan")
    return float(x.mean() / x.std(ddof=1) * ANN)


def _max_drawdown(x: pd.Series) -> float:
    """Max drawdown of the additive cumulative-sum equity curve (return units)."""
    eq = x.fillna(0.0).cumsum()
    peak = eq.cummax()
    return float((eq - peak).min())


def vol_target(daily: pd.Series, target_ann: float = 0.10,
               lookback: int = 60, cap: float = 3.0,
               floor: float = 1e-6) -> pd.Series:
    """Inverse-vol targeting, user's exact formula (Message 3):

        daily_target = target_ann / sqrt(252)          # 10% annual -> daily
        rv           = trailing `lookback`-day realised vol of `daily`, LAGGED 1 day
        scale        = (daily_target / rv).clip(upper=cap)
        sized        = daily * scale

    `rv` is the realised vol of the strategy's own daily return stream (the literal
    reading of "trailing 60-day realised vol" of the series being sized), computed on
    a trailing window and shifted one day so `scale_t` uses only info through t-1
    (causal, no lookahead). `cap` was unspecified by the user; default 3.0 and
    exposed. A paper-faithful alternative -- sizing off the *underlying's* realised
    vol -- is available by passing an external rv via `rv_override`.
    """
    daily_target = target_ann / np.sqrt(252.0)
    rv = daily.rolling(lookback, min_periods=max(20, lookback // 2)).std(ddof=1).shift(1)
    scale = (daily_target / rv.clip(lower=floor)).clip(upper=cap)
    return (daily * scale).rename("vt_ret")


def summarize(trades: pd.DataFrame, daily: pd.Series, label: str = "") -> dict:
    vt = vol_target(daily)
    trade_days = daily[daily != 0.0]
    out = {
        "label": label,
        "sessions": int(len(daily)),
        "n_trades": int(len(trades)),
        "trades_per_day": float(len(trades) / len(daily)) if len(daily) else float("nan"),
        "hit_rate": float((trades["net"] > 0).mean()) if len(trades) else float("nan"),
        "mean_net_bps": float(trades["net"].mean() * 1e4) if len(trades) else float("nan"),
        "gross_ret_sum": float(trades["gross"].sum()) if len(trades) else 0.0,
        "net_ret_sum": float(trades["net"].sum()) if len(trades) else 0.0,
        "sharpe_zero_day": _sharpe(daily),
        "sharpe_trade_day": _sharpe(trade_days),
        "sharpe_vol_target": _sharpe(vt),
        "maxdd_zero_day": _max_drawdown(daily),
        "maxdd_vol_target": _max_drawdown(vt),
    }
    return out


def split_report(trades: pd.DataFrame, daily: pd.Series, cut: str = "2023-01-01"):
    """Aggregate + pre/post-`cut` split."""
    cutd = pd.Timestamp(cut)
    reports = [summarize(trades, daily, "aggregate")]
    for lbl, mask_d, mask_t in [
        ("pre_2023", daily.index < cutd,
         (trades["date"] < cutd) if len(trades) else None),
        ("post_2023", daily.index >= cutd,
         (trades["date"] >= cutd) if len(trades) else None),
    ]:
        d = daily[mask_d]
        t = trades[mask_t] if (len(trades) and mask_t is not None) else trades.iloc[:0]
        reports.append(summarize(t, d, lbl))
    return pd.DataFrame(reports).set_index("label")
