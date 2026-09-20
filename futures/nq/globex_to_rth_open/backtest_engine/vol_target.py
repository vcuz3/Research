"""Causal volatility targeting for the fixed 18:00-to-09:30 return leg."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np
import pandas as pd


@dataclass(frozen=True)
class VolTargetSpec:
    target_annual_vol: float = 0.10
    lookback_days: int = 60
    annualization_days: int = 252
    lag_days: int = 1
    leverage_cap: float = 3.0
    cost_bps_per_side: float = 0.5
    cost_cap_points_per_side: float = 0.25

    def validate(self) -> None:
        if not 0 < self.target_annual_vol < 1:
            raise ValueError("target annual volatility must be between zero and one")
        if self.lookback_days < 2 or self.lag_days < 1:
            raise ValueError("lookback must be >=2 and lag must be >=1")
        if self.leverage_cap <= 0:
            raise ValueError("leverage cap must be positive")
        if self.cost_bps_per_side < 0 or self.cost_cap_points_per_side < 0:
            raise ValueError("cost inputs cannot be negative")


def build_vol_targeted_leg(
    candidates: pd.DataFrame,
    spec: VolTargetSpec,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """Size each leg from strictly prior gross leg returns and apply capped costs.

    Return is measured on entry notional: `(exit - entry) / entry`. The rolling
    standard deviation is computed over prior valid legs, annualized by sqrt(252),
    and does not contain the current trade. Costs are adverse price moves at each
    endpoint, scaled by leverage with the position.
    """
    spec.validate()
    required = {"trade_date", "entry_price", "exit_price", "entry_ts", "exit_ts"}
    missing = required.difference(candidates.columns)
    if missing:
        raise ValueError(f"candidate frame missing columns: {sorted(missing)}")
    frame = candidates.sort_values("trade_date", kind="stable").copy().reset_index(drop=True)
    if frame["trade_date"].duplicated().any():
        raise ValueError("vol-target leg requires at most one trade per date")

    frame["gross_leg_return"] = frame["exit_price"] / frame["entry_price"] - 1.0
    shifted = frame["gross_leg_return"].shift(spec.lag_days)
    frame["realized_vol_60d"] = shifted.rolling(
        spec.lookback_days, min_periods=spec.lookback_days).std(ddof=1)
    frame["annualized_vol_estimate"] = (
        frame["realized_vol_60d"] * np.sqrt(spec.annualization_days))
    frame["leverage_uncapped"] = spec.target_annual_vol / frame["annualized_vol_estimate"]
    frame["leverage"] = frame["leverage_uncapped"].clip(lower=0.0, upper=spec.leverage_cap)

    bps_decimal = spec.cost_bps_per_side * 1e-4
    frame["entry_cost_points"] = np.minimum(
        frame["entry_price"] * bps_decimal, spec.cost_cap_points_per_side)
    frame["exit_cost_points"] = np.minimum(
        frame["exit_price"] * bps_decimal, spec.cost_cap_points_per_side)
    frame["round_trip_cost_points"] = frame["entry_cost_points"] + frame["exit_cost_points"]
    frame["unlevered_cost_return"] = frame["round_trip_cost_points"] / frame["entry_price"]
    frame["net_leg_return"] = frame["gross_leg_return"] - frame["unlevered_cost_return"]
    frame["gross_strategy_return"] = frame["leverage"] * frame["gross_leg_return"]
    frame["net_strategy_return"] = frame["leverage"] * frame["net_leg_return"]
    frame["strategy_cost_return"] = frame["leverage"] * frame["unlevered_cost_return"]

    warmup = int(frame["leverage"].isna().sum())
    valid = frame.loc[frame["leverage"].notna()].copy().reset_index(drop=True)
    if (valid["net_strategy_return"] <= -1).any():
        raise AssertionError("a daily strategy return is <= -100%; wealth accounting invalid")
    if not bool((valid["leverage"] <= spec.leverage_cap + 1e-12).all()):
        raise AssertionError("leverage cap violated")
    quality = {
        "input_trades": len(frame),
        "output_trades": len(valid),
        "warmup_removed": warmup,
        "first_sized_trade": str(valid["trade_date"].min().date()),
        "last_sized_trade": str(valid["trade_date"].max().date()),
        "vol_window": (
            f"gross leg returns shift({spec.lag_days}).rolling({spec.lookback_days}, "
            f"min_periods={spec.lookback_days}).std(ddof=1)*sqrt({spec.annualization_days})"
        ),
        "cap_bind_count": int((valid["leverage_uncapped"] > spec.leverage_cap).sum()),
        "entry_cost_tick_cap_count": int(
            np.isclose(valid["entry_cost_points"], spec.cost_cap_points_per_side).sum()),
        "exit_cost_tick_cap_count": int(
            np.isclose(valid["exit_cost_points"], spec.cost_cap_points_per_side).sum()),
        "spec": asdict(spec),
    }
    return valid, quality


def _compound_return(values: pd.Series) -> float:
    return float((1.0 + values).prod() - 1.0)


def _compound_drawdown(values: pd.Series) -> float:
    wealth = (1.0 + values).cumprod()
    wealth_with_start = pd.concat([pd.Series([1.0]), wealth], ignore_index=True)
    return float((wealth_with_start / wealth_with_start.cummax() - 1.0).min())


def summarize_return_period(frame: pd.DataFrame, annualization_days: int = 252) -> dict[str, Any]:
    if frame.empty:
        return {"trades": 0}
    net = frame["net_strategy_return"]
    gross = frame["gross_strategy_return"]
    active = frame["active"].astype(bool) if "active" in frame else pd.Series(True, index=frame.index)
    active_frame = frame.loc[active]
    net_std = float(net.std(ddof=1))
    gross_compound = _compound_return(gross)
    net_compound = _compound_return(net)
    return {
        "observations": len(frame),
        "trades": int(active.sum()),
        "first_trade": str(frame["trade_date"].min().date()),
        "last_trade": str(frame["trade_date"].max().date()),
        "gross_compound_return": gross_compound,
        "net_compound_return": net_compound,
        "compound_cost_drag": gross_compound - net_compound,
        "annualized_net_vol": net_std * np.sqrt(annualization_days),
        "net_sharpe": (
            float(net.mean() / net_std * np.sqrt(annualization_days)) if net_std > 0 else np.nan),
        "max_drawdown": _compound_drawdown(net),
        "hit_rate_net": float((active_frame["net_strategy_return"] > 0).mean()),
        "average_leverage": float(active_frame["leverage"].mean()),
        "median_leverage": float(active_frame["leverage"].median()),
        "maximum_leverage": float(active_frame["leverage"].max()),
        "average_portfolio_leverage": float(
            frame["effective_leverage"].mean() if "effective_leverage" in frame
            else frame["leverage"].mean()),
        "cap_bind_days": int(np.isclose(active_frame["leverage"], 3.0).sum()),
        "average_annualized_vol_estimate": float(frame["annualized_vol_estimate"].mean()),
        "worst_day": float(net.min()),
        "best_day": float(net.max()),
    }


def yearly_performance(frame: pd.DataFrame, annualization_days: int = 252) -> pd.DataFrame:
    rows = []
    for year, group in frame.groupby(frame["trade_date"].dt.year, sort=True):
        rows.append({"year": int(year), **summarize_return_period(group, annualization_days)})
    return pd.DataFrame(rows)
