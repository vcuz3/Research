"""Pure validation machinery for the Gao-rule futures-transfer baseline.

This module accepts already-causal executable outcomes.  It never loads market
data, which keeps the null, MDE, and injected-positive-control logic directly
testable with small synthetic arrays before any historical result is opened.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

from ..backtest_engine.data import INSTRUMENT_SPECS
from ..backtest_engine.metrics import hac_mean_se, hac_t
from .nulls import clopper_pearson_interval, empirical_pvalue


@dataclass(frozen=True)
class BaselineNullResult:
    """A complete fixed-draw null result with no silently discarded draws."""

    observed_hac_t: float
    null_hac_t: np.ndarray
    exceedances: int
    pvalue: float
    monte_carlo_interval: tuple[float, float]


@dataclass(frozen=True)
class PositiveControlResult:
    """Injected known-real case evaluated through the identical baseline null."""

    target_zero_filled_net_sharpe: float
    achieved_zero_filled_net_sharpe: float
    injected_effect_points_per_trade: float
    injected_effect_dollars_per_trade: float
    null: BaselineNullResult


def _validated_arrays(
    outcome_points: np.ndarray,
    side: np.ndarray,
    dates: pd.Series | np.ndarray,
) -> tuple[np.ndarray, np.ndarray, pd.Series]:
    outcomes = np.asarray(outcome_points, dtype=float)
    sides = np.asarray(side, dtype=float)
    date_series = pd.Series(pd.to_datetime(np.asarray(dates))).reset_index(drop=True)
    if not (len(outcomes) == len(sides) == len(date_series)) or len(outcomes) < 2:
        raise ValueError("baseline outcome, side, and date arrays must align and contain at least two rows")
    if not np.isfinite(outcomes).all():
        raise ValueError("baseline executable outcomes must be finite")
    if not np.isfinite(sides).all() or not np.isin(sides, [-1, 0, 1]).all():
        raise ValueError("baseline sides must be finite exact values -1, 0, or 1")
    if date_series.isna().any() or date_series.duplicated().any() or not date_series.is_monotonic_increasing:
        raise ValueError("baseline dates must be finite, unique, and chronological")
    return outcomes, sides.astype("int8"), date_series


def _year_groups(dates: pd.Series) -> list[np.ndarray]:
    years = dates.dt.year.to_numpy()
    groups = [np.flatnonzero(years == year) for year in np.unique(years)]
    if not any(len(group) > 1 for group in groups):
        raise ValueError("year-conditioned null requires at least one non-singleton year")
    return groups


def _net_dollars(
    outcome_points: np.ndarray,
    side: np.ndarray,
    *,
    multiplier: float,
    round_trip_cost_dollars: float,
) -> np.ndarray:
    traded = side != 0
    return (
        side * outcome_points * multiplier
        - traded.astype(float) * round_trip_cost_dollars
    )


def zero_filled_sharpe(values: np.ndarray) -> float:
    """Annualized Sharpe of the complete daily series, including flat zeros."""

    data = np.asarray(values, dtype=float)
    if len(data) < 2 or not np.isfinite(data).all():
        raise ValueError("zero-filled Sharpe requires at least two finite daily observations")
    scale = float(np.std(data, ddof=1))
    if not scale > 0:
        raise ValueError("zero-filled Sharpe requires positive daily variance")
    return float(np.sqrt(252.0) * np.mean(data) / scale)


def year_conditioned_circular_null(
    outcome_points: np.ndarray,
    side: np.ndarray,
    dates: pd.Series | np.ndarray,
    *,
    multiplier: float,
    round_trip_cost_dollars: float,
    hac_lags: int,
    draws: int,
    seed: int,
) -> BaselineNullResult:
    """Shift unsigned executable outcomes within year and score HAC t-statistics.

    Each calendar year receives an independently sampled nonzero circular
    offset.  Signals, eligible dates, execution costs, and each year's outcome
    path/multiset are preserved; only the signal/outcome date pairing is broken.
    """

    outcomes, sides, date_series = _validated_arrays(outcome_points, side, dates)
    if draws < 2:
        raise ValueError("null draw count must be at least two")
    if hac_lags < 0:
        raise ValueError("HAC lag count must be non-negative")
    if multiplier <= 0 or round_trip_cost_dollars < 0:
        raise ValueError("contract multiplier must be positive and costs non-negative")

    observed_pnl = _net_dollars(
        outcomes,
        sides,
        multiplier=multiplier,
        round_trip_cost_dollars=round_trip_cost_dollars,
    )
    observed = hac_t(observed_pnl, max_lag=hac_lags)
    if not np.isfinite(observed):
        raise ValueError("observed baseline HAC t-statistic is invalid")

    groups = _year_groups(date_series)
    rng = np.random.default_rng(int(seed))
    null_statistics = np.empty(int(draws), dtype=float)
    shifted = np.empty_like(outcomes)
    for draw in range(int(draws)):
        for group in groups:
            if len(group) <= 1:
                shifted[group] = outcomes[group]
                continue
            offset = int(rng.integers(1, len(group)))
            shifted[group] = np.roll(outcomes[group], offset)
        null_pnl = _net_dollars(
            shifted,
            sides,
            multiplier=multiplier,
            round_trip_cost_dollars=round_trip_cost_dollars,
        )
        statistic = hac_t(null_pnl, max_lag=hac_lags)
        if not np.isfinite(statistic):
            raise ValueError(f"invalid preregistered null draw at index {draw}")
        null_statistics[draw] = statistic

    if not float(np.std(null_statistics, ddof=1)) > 0:
        raise ValueError("baseline null statistic has zero variance")
    pvalue = empirical_pvalue(float(observed), null_statistics)
    exceedances = int(np.sum(null_statistics >= observed))
    return BaselineNullResult(
        observed_hac_t=float(observed),
        null_hac_t=null_statistics,
        exceedances=exceedances,
        pvalue=float(pvalue),
        monte_carlo_interval=clopper_pearson_interval(exceedances, int(draws)),
    )


def primary_cost_mde(
    trades: pd.DataFrame,
    *,
    instrument: str,
    hac_lags: int,
    multiplier: float = 2.49,
) -> dict[str, object]:
    """Return one-sided 80%-power MDEs for the zero-filled primary-cost book."""

    required = {"trade", "side", "net_dollars", "net_bps"}
    missing = sorted(required - set(trades.columns))
    if missing:
        raise ValueError(f"MDE input is missing columns: {missing}")
    if len(trades) < 2 or multiplier <= 0:
        raise ValueError("MDE requires at least two rows and a positive multiplier")
    numeric_side = pd.to_numeric(trades["side"], errors="coerce")
    if not np.isfinite(numeric_side.to_numpy(dtype=float)).all() or not numeric_side.isin([-1, 0, 1]).all():
        raise ValueError("MDE sides must be finite exact values -1, 0, or 1")
    if trades["trade"].dtype != bool or not trades["trade"].eq(numeric_side.ne(0)).all():
        raise ValueError("MDE trade flags must exactly equal side != 0")
    instrument = instrument.upper()
    if instrument not in INSTRUMENT_SPECS:
        raise KeyError(f"unsupported instrument: {instrument}")
    spec = INSTRUMENT_SPECS[instrument]
    net_dollars = pd.to_numeric(trades["net_dollars"], errors="coerce").to_numpy(dtype=float)
    net_bps = pd.to_numeric(trades["net_bps"], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(net_dollars).all() or not np.isfinite(net_bps).all():
        raise ValueError("MDE daily series must be finite")
    trade_rate = float(trades["trade"].mean())
    if not trade_rate > 0:
        raise ValueError("per-trade MDE is undefined with no trades")

    series = {
        "points": net_dollars / spec.multiplier,
        "dollars": net_dollars,
        "bps": net_bps,
    }
    standard_errors: dict[str, float] = {}
    daily: dict[str, float] = {}
    per_trade: dict[str, float] = {}
    for unit, values in series.items():
        standard_error = hac_mean_se(values, max_lag=hac_lags)
        if not np.isfinite(standard_error) or not standard_error > 0:
            raise ValueError(f"MDE HAC standard error is invalid for {unit}")
        standard_errors[unit] = float(standard_error)
        daily[unit] = float(multiplier * standard_error)
        per_trade[unit] = float(daily[unit] / trade_rate)
    standard_errors["ticks"] = standard_errors["points"] / spec.tick_size
    daily["ticks"] = daily["points"] / spec.tick_size
    per_trade["ticks"] = per_trade["points"] / spec.tick_size
    return {
        "definition": f"one-sided 80%-power MDE = {multiplier:g} x HAC standard error",
        "hac_lags": int(hac_lags),
        "mde_multiplier": float(multiplier),
        "trade_rate": trade_rate,
        "hac_standard_error_daily": standard_errors,
        "mde_daily": daily,
        "mde_per_trade": per_trade,
    }


def injected_positive_control(
    outcome_points: np.ndarray,
    side: np.ndarray,
    dates: pd.Series | np.ndarray,
    *,
    multiplier: float,
    round_trip_cost_dollars: float,
    target_zero_filled_net_sharpe: float,
    hac_lags: int,
    draws: int,
    seed: int,
) -> PositiveControlResult:
    """Inject a calibrated side-linked effect into year/side-demeaned outcomes."""

    outcomes, sides, date_series = _validated_arrays(outcome_points, side, dates)
    if np.any(sides == 0):
        raise ValueError("the r1 positive control requires an always-invested +/-1 signal")
    if multiplier <= 0 or round_trip_cost_dollars < 0:
        raise ValueError("contract multiplier must be positive and costs non-negative")
    if not target_zero_filled_net_sharpe > 0:
        raise ValueError("positive-control target Sharpe must be positive")

    frame = pd.DataFrame(
        {
            "year": date_series.dt.year.to_numpy(),
            "side": sides,
            "outcome_points": outcomes,
        }
    )
    stratum_mean = frame.groupby(["year", "side"], sort=False)["outcome_points"].transform("mean")
    centered_outcomes = outcomes - stratum_mean.to_numpy(dtype=float)
    base_net = _net_dollars(
        centered_outcomes,
        sides,
        multiplier=multiplier,
        round_trip_cost_dollars=round_trip_cost_dollars,
    )
    scale = float(np.std(base_net, ddof=1))
    if not scale > 0:
        raise ValueError("positive-control demeaned outcome variance must be positive")
    target_mean = float(target_zero_filled_net_sharpe * scale / np.sqrt(252.0))
    effect_dollars = float(target_mean - np.mean(base_net))
    if not effect_dollars > 0:
        raise ValueError("positive-control calibration did not require a positive injected effect")
    effect_points = effect_dollars / multiplier
    injected_outcomes = centered_outcomes + sides * effect_points
    injected_net = _net_dollars(
        injected_outcomes,
        sides,
        multiplier=multiplier,
        round_trip_cost_dollars=round_trip_cost_dollars,
    )
    achieved = zero_filled_sharpe(injected_net)
    if not np.isclose(achieved, target_zero_filled_net_sharpe, rtol=0.0, atol=1e-12):
        raise AssertionError("positive-control Sharpe calibration failed")

    null_result = year_conditioned_circular_null(
        injected_outcomes,
        sides,
        date_series,
        multiplier=multiplier,
        round_trip_cost_dollars=round_trip_cost_dollars,
        hac_lags=hac_lags,
        draws=draws,
        seed=seed,
    )
    return PositiveControlResult(
        target_zero_filled_net_sharpe=float(target_zero_filled_net_sharpe),
        achieved_zero_filled_net_sharpe=float(achieved),
        injected_effect_points_per_trade=float(effect_points),
        injected_effect_dollars_per_trade=float(effect_dollars),
        null=null_result,
    )
