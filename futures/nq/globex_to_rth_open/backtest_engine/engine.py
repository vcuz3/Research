"""Auditable fixed-horizon execution and portfolio accounting."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class CostModel:
    multiplier: float = 20.0
    tick_size: float = 0.25
    slippage_ticks_per_side: float = 1.0
    commission_per_side: float = 2.50

    @property
    def round_trip_dollars_per_contract(self) -> float:
        slippage = 2 * self.slippage_ticks_per_side * self.tick_size * self.multiplier
        commission = 2 * self.commission_per_side
        return slippage + commission


SIZING_COLUMNS = {
    "equal_contract": None,
    "inverse_atr14": ("atr14_ref", "atr14"),
    "inverse_vix": ("vix_daily_vol_ref", "vix_daily_vol_points"),
    "inverse_prev_atr": ("prev_day_tr_ref", "prev_day_tr"),
}


def position_units(
    trades: pd.DataFrame,
    mode: str,
    minimum: float,
    maximum: float,
    integer_contracts: bool,
) -> pd.Series:
    """Return causal units; inverse-vol arms target one contract at prior median vol."""
    if mode not in SIZING_COLUMNS:
        raise ValueError(f"unknown sizing mode: {mode}")
    columns = SIZING_COLUMNS[mode]
    if columns is None:
        units = pd.Series(1.0, index=trades.index)
    else:
        reference, current = columns
        units = trades[reference] / trades[current]
        units = units.where((trades[reference] > 0) & (trades[current] > 0))
        units = units.clip(lower=minimum, upper=maximum)
    if integer_contracts:
        units = np.floor(units + 0.5)
    return units.astype(float)


def _hac_tstat(values: np.ndarray, lags: int = 5) -> float:
    values = values[np.isfinite(values)]
    n = len(values)
    if n < 3:
        return float("nan")
    demeaned = values - values.mean()
    long_run_var = float(np.dot(demeaned, demeaned) / n)
    for lag in range(1, min(lags, n - 1) + 1):
        gamma = float(np.dot(demeaned[lag:], demeaned[:-lag]) / n)
        long_run_var += 2.0 * (1.0 - lag / (lags + 1.0)) * gamma
    variance_of_mean = long_run_var / n
    return float(values.mean() / np.sqrt(variance_of_mean)) if variance_of_mean > 0 else float("nan")


def _max_drawdown(pnl: np.ndarray) -> float:
    equity = np.concatenate([[0.0], np.cumsum(pnl)])
    drawdown = equity - np.maximum.accumulate(equity)
    return float(drawdown.min())


def summarize_pnl(trades: pd.DataFrame, cost: CostModel) -> dict[str, Any]:
    if trades.empty:
        return {
            "trades": 0, "first_trade": None, "last_trade": None,
            "mean_gross_points_per_contract": np.nan, "mean_net_dollars": np.nan,
            "normalized_obs": 0, "mean_gross_atr14_units": np.nan,
            "mean_net_atr14_units": np.nan,
            "total_net_dollars": 0.0, "net_sharpe": np.nan, "net_hac5_t": np.nan,
            "hit_rate_net": np.nan, "max_drawdown_dollars": 0.0,
            "average_units": np.nan, "max_units": np.nan, "turnover_contracts": 0.0,
        }
    net = trades["net_dollars"].to_numpy(dtype=float)
    std = float(np.std(net, ddof=1)) if len(net) > 1 else float("nan")
    return {
        "trades": len(trades),
        "first_trade": str(trades["trade_date"].min().date()),
        "last_trade": str(trades["trade_date"].max().date()),
        "mean_gross_points_per_contract": float(trades["gross_points_per_contract"].mean()),
        "normalized_obs": int(trades["net_atr14_units_per_contract"].notna().sum()),
        "mean_gross_atr14_units": float(trades["gross_atr14_units_per_contract"].mean()),
        "mean_net_atr14_units": float(trades["net_atr14_units_per_contract"].mean()),
        "mean_gross_dollars": float(trades["gross_dollars"].mean()),
        "mean_net_dollars": float(trades["net_dollars"].mean()),
        "total_gross_dollars": float(trades["gross_dollars"].sum()),
        "total_cost_dollars": float(trades["cost_dollars"].sum()),
        "total_net_dollars": float(trades["net_dollars"].sum()),
        "net_sharpe": float(np.sqrt(252.0) * np.mean(net) / std) if std > 0 else np.nan,
        "net_hac5_t": _hac_tstat(net, lags=5),
        "hit_rate_net": float((trades["net_dollars"] > 0).mean()),
        "max_drawdown_dollars": _max_drawdown(net),
        "average_units": float(trades["units"].mean()),
        "max_units": float(trades["units"].max()),
        "turnover_contracts": float(2.0 * trades["units"].abs().sum()),
        "round_trip_cost_per_contract": cost.round_trip_dollars_per_contract,
    }


def run_one(
    candidates: pd.DataFrame,
    gate: pd.Series,
    sizing_mode: str,
    cost: CostModel,
    minimum_units: float,
    maximum_units: float,
    integer_contracts: bool,
) -> tuple[dict[str, Any], pd.DataFrame]:
    selected = candidates.loc[gate.fillna(False)].copy()
    selected["units"] = position_units(
        selected, sizing_mode, minimum_units, maximum_units, integer_contracts)
    selected = selected.loc[selected["units"].notna() & (selected["units"] > 0)].copy()
    selected["gross_dollars"] = (
        selected["gross_points_per_contract"] * cost.multiplier * selected["units"])
    selected["cost_dollars"] = cost.round_trip_dollars_per_contract * selected["units"].abs()
    selected["net_dollars"] = selected["gross_dollars"] - selected["cost_dollars"]
    if "atr14" in selected:
        selected["gross_atr14_units_per_contract"] = (
            selected["gross_points_per_contract"] / selected["atr14"])
        net_points_per_contract = (
            selected["gross_points_per_contract"]
            - cost.round_trip_dollars_per_contract / cost.multiplier)
        selected["net_atr14_units_per_contract"] = net_points_per_contract / selected["atr14"]
    else:
        selected["gross_atr14_units_per_contract"] = np.nan
        selected["net_atr14_units_per_contract"] = np.nan
    return summarize_pnl(selected, cost), selected


def variant_gates(
    trades: pd.DataFrame,
    ma_windows: Iterable[int],
    vix_lower_bounds: Iterable[float],
    vix_upper_bounds: Iterable[float | None],
) -> list[tuple[str, str, dict[str, Any], pd.Series]]:
    gates: list[tuple[str, str, dict[str, Any], pd.Series]] = [
        ("baseline", "all", {}, pd.Series(True, index=trades.index))]
    for window in sorted(set(int(x) for x in ma_windows)):
        gates.append(("moving_average", f"price_above_sma_{window}", {"days": window},
                      trades["entry_price"] > trades[f"sma_{window}"]))
    for lower in sorted(set(float(x) for x in vix_lower_bounds)):
        for raw_upper in vix_upper_bounds:
            upper = None if raw_upper is None else float(raw_upper)
            if upper is not None and lower >= upper:
                continue
            gate = trades["vix_close"].ge(lower)
            if upper is not None:
                gate &= trades["vix_close"].lt(upper)
            upper_label = "inf" if upper is None else f"{upper:g}"
            name = f"vix_{lower:g}_to_{upper_label}"
            gates.append(("vix_range", name, {"lower": lower, "upper": upper}, gate))
    return gates


def run_study(
    trades: pd.DataFrame,
    ma_windows: Iterable[int],
    vix_lower_bounds: Iterable[float],
    vix_upper_bounds: Iterable[float | None],
    sizing_modes: Iterable[str],
    cost: CostModel,
    minimum_units: float,
    maximum_units: float,
    integer_contracts: bool,
) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    for family, variant, parameters, gate in variant_gates(
            trades, ma_windows, vix_lower_bounds, vix_upper_bounds):
        eligible_before_sizing = int(gate.fillna(False).sum())
        for sizing in sizing_modes:
            summary, _ = run_one(trades, gate, sizing, cost, minimum_units,
                                 maximum_units, integer_contracts)
            rows.append({
                "family": family, "variant": variant, "parameters": str(parameters),
                "sizing": sizing, "eligible_before_sizing": eligible_before_sizing,
                **summary,
            })
    return pd.DataFrame(rows)
