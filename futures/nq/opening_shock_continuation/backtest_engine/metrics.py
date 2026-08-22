"""Portfolio summaries that include every eligible, zero-trade session."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd


def _safe_float(value: float) -> float | None:
    return None if not np.isfinite(value) else float(value)


def _sharpe(values: np.ndarray) -> float:
    if len(values) < 2:
        return float("nan")
    scale = np.std(values, ddof=1)
    return float(np.sqrt(252.0) * np.mean(values) / scale) if scale > 0 else float("nan")


def _iid_t(values: np.ndarray) -> float:
    if len(values) < 2:
        return float("nan")
    scale = np.std(values, ddof=1)
    return float(np.mean(values) / (scale / np.sqrt(len(values)))) if scale > 0 else float("nan")


def hac_mean_se(values: np.ndarray, max_lag: int = 5) -> float:
    """Newey-West standard error for the unconditional daily mean."""
    n = len(values)
    if n < 2:
        return float("nan")
    centered = values - np.mean(values)
    lrv = float(np.dot(centered, centered) / n)
    for lag in range(1, min(max_lag, n - 1) + 1):
        gamma = float(np.dot(centered[lag:], centered[:-lag]) / n)
        lrv += 2.0 * (1.0 - lag / (max_lag + 1.0)) * gamma
    variance_mean = lrv / n
    return float(np.sqrt(variance_mean)) if variance_mean > 0 else float("nan")


def hac_t(values: np.ndarray, max_lag: int = 5) -> float:
    """Newey-West t-statistic for the unconditional daily mean."""

    standard_error = hac_mean_se(np.asarray(values, dtype=float), max_lag=max_lag)
    return float(np.mean(values) / standard_error) if standard_error > 0 else float("nan")


def summarize(trades: pd.DataFrame, *, hac_lags: int = 5) -> dict[str, int | float | None]:
    required = {"date", "side", "trade", "gross_dollars", "net_dollars", "gross_bps", "net_bps", "slippage_dollars", "fees_dollars"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"missing trade columns: {missing}")
    if pd.to_datetime(trades["date"]).duplicated().any():
        raise ValueError("daily strategy output must have one row per eligible session")
    dates = pd.to_datetime(trades["date"])
    if not dates.is_monotonic_increasing:
        raise ValueError("daily strategy output must be chronological")
    numeric_columns = [
        "side",
        "gross_dollars",
        "net_dollars",
        "gross_bps",
        "net_bps",
        "slippage_dollars",
        "fees_dollars",
    ]
    numeric = trades[numeric_columns].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError("daily PnL, side, and cost fields must be finite")
    if trades["trade"].dtype != bool:
        raise ValueError("trade must be an explicit boolean field")
    if not numeric["side"].isin([-1, 0, 1]).all():
        raise ValueError("side must be -1, 0, or 1")
    if not trades["trade"].eq(numeric["side"].ne(0)).all():
        raise ValueError("trade flag must equal side != 0")
    if not np.allclose(
        numeric["net_dollars"],
        numeric["gross_dollars"] - numeric["slippage_dollars"] - numeric["fees_dollars"],
        rtol=1e-10,
        atol=1e-8,
    ):
        raise ValueError("net PnL must reconcile to gross minus slippage and fees")
    flat = ~trades["trade"]
    if not numeric.loc[flat, ["gross_dollars", "net_dollars", "slippage_dollars", "fees_dollars"]].eq(0).all().all():
        raise ValueError("flat eligible sessions must carry explicit zero PnL and cost")

    frame = trades.sort_values("date").reset_index(drop=True)
    net = frame["net_dollars"].to_numpy(dtype=float)
    gross = frame["gross_dollars"].to_numpy(dtype=float)
    net_bps = frame["net_bps"].to_numpy(dtype=float)
    traded = frame["trade"].astype(bool).to_numpy()
    equity = np.cumsum(net)
    # The explicit leading zero makes pre-profit losses visible to max drawdown.
    if len(equity):
        running_peak = np.maximum.accumulate(np.r_[0.0, equity])
        max_drawdown = float(np.min(np.r_[0.0, equity] - running_peak))
    else:
        max_drawdown = float("nan")

    trade_net = net[traded]
    winners = trade_net[trade_net > 0].sum() if len(trade_net) else 0.0
    losers = -trade_net[trade_net < 0].sum() if len(trade_net) else 0.0
    result: dict[str, int | float | None] = {
        "eligible_sessions": int(len(frame)),
        "trades": int(traded.sum()),
        "long_trades": int((frame["side"] > 0).sum()),
        "short_trades": int((frame["side"] < 0).sum()),
        "trade_rate": _safe_float(float(traded.mean())) if len(frame) else None,
        "gross_total_dollars": _safe_float(float(gross.sum())),
        "slippage_total_dollars": _safe_float(float(frame["slippage_dollars"].sum())),
        "fees_total_dollars": _safe_float(float(frame["fees_dollars"].sum())),
        "net_total_dollars": _safe_float(float(net.sum())),
        "gross_mean_daily_dollars": _safe_float(float(gross.mean())) if len(frame) else None,
        "net_mean_daily_dollars": _safe_float(float(net.mean())) if len(frame) else None,
        "net_mean_trade_dollars": _safe_float(float(trade_net.mean())) if len(trade_net) else None,
        "gross_mean_daily_bps": _safe_float(float(frame["gross_bps"].mean())) if len(frame) else None,
        "net_mean_daily_bps": _safe_float(float(net_bps.mean())) if len(frame) else None,
        "annualized_net_dollars": _safe_float(float(net.mean() * 252.0)) if len(frame) else None,
        "annualized_volatility_dollars": _safe_float(float(np.std(net, ddof=1) * math.sqrt(252.0))) if len(frame) > 1 else None,
        "daily_sharpe_net": _safe_float(_sharpe(net)),
        "daily_sharpe_gross": _safe_float(_sharpe(gross)),
        "iid_t_net": _safe_float(_iid_t(net)),
        "hac_t_net_lag5": _safe_float(hac_t(net, max_lag=hac_lags)),
        "trade_hit_rate": _safe_float(float((trade_net > 0).mean())) if len(trade_net) else None,
        "profit_factor": _safe_float(float(winners / losers)) if losers > 0 else None,
        "max_drawdown_dollars": _safe_float(max_drawdown),
    }
    return result


def grouped_summaries(trades: pd.DataFrame, group: pd.Series) -> pd.DataFrame:
    if len(trades) != len(group):
        raise ValueError("group labels must align with trades")
    if isinstance(group, pd.Series) and not group.index.equals(trades.index):
        raise ValueError("group Series index must exactly match trade index")
    rows = []
    labels = pd.Series(np.asarray(group), index=trades.index)
    for label, subset in trades.groupby(labels, sort=True):
        row = {"group": str(label)}
        row.update(summarize(subset))
        rows.append(row)
    return pd.DataFrame(rows)


def era_label(dates: pd.Series) -> pd.Series:
    dates = pd.to_datetime(dates)
    return pd.Series(
        np.select(
            [dates.between("2011-01-01", "2018-12-31"), dates.between("2019-01-01", "2022-12-31"), dates.between("2023-01-01", "2026-07-14")],
            ["discovery_2011_2018", "validation_2019_2022", "validation_b_2023_2026"],
            default="outside_scope",
        ),
        index=dates.index,
    )
