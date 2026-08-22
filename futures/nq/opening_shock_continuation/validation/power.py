"""Synthetic power utilities for the frozen opening-shock validation plan.

The functions in this module operate only on already-aligned daily records.
They never load market data.  This keeps minimum-detectable-effect arithmetic,
paired demeaning, effect injection, and outer-bootstrap construction auditable
with deterministic synthetic fixtures before any historical result is read.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from scipy.optimize import brentq

from ..backtest_engine.metrics import hac_mean_se
from .baseline import zero_filled_sharpe
from .bootstrap import stationary_bootstrap_indices


POWER_ERAS = ("discovery", "A", "B")


def _chronological_dates(values: pd.Series | pd.Index, *, name: str) -> pd.DatetimeIndex:
    dates = pd.DatetimeIndex(pd.to_datetime(values, errors="coerce"))
    if dates.hasnans or dates.has_duplicates or not dates.is_monotonic_increasing:
        raise ValueError(f"{name} must be finite, unique, and chronological")
    return dates


def _aligned_numeric_series(
    values: pd.Series,
    index: pd.DatetimeIndex,
    *,
    name: str,
) -> pd.Series:
    if not isinstance(values, pd.Series):
        raise TypeError(f"{name} must be a pandas Series indexed by date")
    if not values.index.equals(index):
        raise ValueError(f"{name} must preserve exact date/index alignment")
    numeric = pd.to_numeric(values, errors="coerce")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        raise ValueError(f"{name} must contain only finite values")
    return numeric.astype(float)


def _aligned_sides(
    values: pd.Series,
    index: pd.DatetimeIndex,
    *,
    name: str,
) -> pd.Series:
    numeric = _aligned_numeric_series(values, index, name=name)
    if not numeric.isin([-1, 0, 1]).all():
        raise ValueError(f"{name} must contain exact values -1, 0, or 1")
    return numeric.astype("int8")


def minimum_detectable_effect(
    daily: pd.DataFrame,
    *,
    point_value_dollars: float,
    hac_lags: int = 5,
    mde_multiplier: float = 2.49,
    tick_size_points: float = 0.25,
) -> dict[str, object]:
    """Compute the frozen one-sided MDE for a zero-filled daily net book.

    ``net_points`` is optional because an after-fee point result is exactly
    ``net_dollars / point_value_dollars``.  When supplied, it must reconcile to
    that identity.  Flat eligible dates must be present as explicit zero rows in
    every net unit; a traded-day-only frame is rejected by its trade flags.
    """

    required = {"date", "side", "trade", "net_dollars", "net_bps"}
    missing = sorted(required - set(daily.columns))
    if missing:
        raise ValueError(f"MDE input is missing columns: {missing}")
    if len(daily) < 2:
        raise ValueError("MDE requires at least two eligible daily rows")
    if (
        not np.isfinite(point_value_dollars)
        or point_value_dollars <= 0
        or not np.isfinite(tick_size_points)
        or tick_size_points <= 0
        or not np.isfinite(mde_multiplier)
        or mde_multiplier <= 0
    ):
        raise ValueError("point value, tick size, and MDE multiplier must be finite and positive")
    if (
        not isinstance(hac_lags, (int, np.integer))
        or isinstance(hac_lags, (bool, np.bool_))
        or hac_lags < 0
    ):
        raise ValueError("HAC lags must be a non-negative integer")

    dates = _chronological_dates(daily["date"], name="MDE dates")
    if not isinstance(daily["trade"].dtype, pd.BooleanDtype) and daily["trade"].dtype != bool:
        raise ValueError("MDE trade flags must be explicit booleans")
    if daily["trade"].isna().any():
        raise ValueError("MDE trade flags must be explicit booleans without missing values")
    trade = daily["trade"].astype(bool).reset_index(drop=True)
    side_values = pd.to_numeric(daily["side"], errors="coerce").reset_index(drop=True)
    if not np.isfinite(side_values.to_numpy(dtype=float)).all() or not side_values.isin([-1, 0, 1]).all():
        raise ValueError("MDE sides must be finite exact values -1, 0, or 1")
    if not trade.eq(side_values.ne(0)).all():
        raise ValueError("MDE trade flags must exactly equal side != 0")

    dollars = pd.to_numeric(daily["net_dollars"], errors="coerce").reset_index(drop=True)
    bps = pd.to_numeric(daily["net_bps"], errors="coerce").reset_index(drop=True)
    points_from_dollars = dollars / float(point_value_dollars)
    if "net_points" in daily:
        points = pd.to_numeric(daily["net_points"], errors="coerce").reset_index(drop=True)
        if not np.isfinite(points.to_numpy(dtype=float)).all():
            raise ValueError("MDE net points must be finite")
        if not np.allclose(
            points.to_numpy(dtype=float),
            points_from_dollars.to_numpy(dtype=float),
            rtol=1e-12,
            atol=1e-12,
        ):
            raise ValueError("MDE net points must reconcile to net dollars / point value")
    else:
        points = points_from_dollars
    values = {
        "dollars": dollars.to_numpy(dtype=float),
        "points": points.to_numpy(dtype=float),
        "bps": bps.to_numpy(dtype=float),
    }
    if not all(np.isfinite(array).all() for array in values.values()):
        raise ValueError("MDE daily net dollars, points, and bps must all be finite")
    flat = ~trade.to_numpy()
    if any(not np.equal(array[flat], 0.0).all() for array in values.values()):
        raise ValueError("every eligible no-trade day must be an explicit zero in every net unit")

    trade_rate = float(trade.mean())
    if not trade_rate > 0:
        raise ValueError("per-trade MDE is undefined when the observed trade rate is zero")
    hac_se_daily: dict[str, float] = {}
    mde_daily: dict[str, float] = {}
    mde_per_trade: dict[str, float] = {}
    for unit, array in values.items():
        standard_error = float(hac_mean_se(array, max_lag=int(hac_lags)))
        if not np.isfinite(standard_error) or standard_error <= 0:
            raise ValueError(f"MDE HAC standard error is invalid for {unit}")
        hac_se_daily[unit] = standard_error
        mde_daily[unit] = float(mde_multiplier * standard_error)
        mde_per_trade[unit] = float(mde_daily[unit] / trade_rate)
    hac_se_daily["ticks"] = hac_se_daily["points"] / float(tick_size_points)
    mde_daily["ticks"] = mde_daily["points"] / float(tick_size_points)
    mde_per_trade["ticks"] = mde_per_trade["points"] / float(tick_size_points)

    # ``dates`` is deliberately constructed even though only its invariants are
    # returned: chronological zero-day rows are part of the estimand contract.
    return {
        "definition": (
            f"one-sided MDE = {float(mde_multiplier):g} x HAC standard error "
            "of the zero-filled daily mean"
        ),
        "eligible_sessions": int(len(dates)),
        "trades": int(trade.sum()),
        "trade_rate": trade_rate,
        "hac_lags": int(hac_lags),
        "mde_multiplier": float(mde_multiplier),
        "point_value_dollars": float(point_value_dollars),
        "tick_size_points": float(tick_size_points),
        "hac_standard_error_daily": hac_se_daily,
        "mde_daily": mde_daily,
        "mde_per_trade": mde_per_trade,
    }


def demean_paired_outcomes(
    nq_unsigned_points: pd.Series,
    es_unsigned_points: pd.Series,
    nq_opening_side: pd.Series,
    es_opening_side: pd.Series,
) -> pd.DataFrame:
    """Demean paired unsigned outcomes within year x joint-opening-side.

    "Unsigned" means the raw forward point change has not been multiplied by a
    strategy side; values may therefore be positive or negative.  Both markets
    keep the exact input date index and are demeaned against their own mean in
    the same joint stratum.
    """

    if not isinstance(nq_unsigned_points, pd.Series):
        raise TypeError("NQ unsigned outcomes must be a pandas Series indexed by date")
    if not isinstance(nq_unsigned_points.index, pd.DatetimeIndex):
        raise TypeError("paired outcomes must use a DatetimeIndex")
    dates = _chronological_dates(nq_unsigned_points.index, name="paired outcome dates")
    nq = _aligned_numeric_series(nq_unsigned_points, dates, name="NQ unsigned outcomes")
    es = _aligned_numeric_series(es_unsigned_points, dates, name="ES unsigned outcomes")
    nq_side = _aligned_sides(nq_opening_side, dates, name="NQ opening side")
    es_side = _aligned_sides(es_opening_side, dates, name="ES opening side")

    keys = pd.DataFrame(
        {
            "year": dates.year,
            "nq_opening_side": nq_side.to_numpy(),
            "es_opening_side": es_side.to_numpy(),
        },
        index=dates,
    )
    nq_mean = nq.groupby(
        [keys["year"], keys["nq_opening_side"], keys["es_opening_side"]], sort=False
    ).transform("mean")
    es_mean = es.groupby(
        [keys["year"], keys["nq_opening_side"], keys["es_opening_side"]], sort=False
    ).transform("mean")
    result = pd.DataFrame(
        {
            "nq_demeaned_points": nq.to_numpy() - nq_mean.to_numpy(),
            "es_demeaned_points": es.to_numpy() - es_mean.to_numpy(),
        },
        index=dates,
    )
    result.index.name = nq_unsigned_points.index.name
    if not result.index.equals(nq_unsigned_points.index):
        raise AssertionError("paired demeaning changed date/row alignment")
    if not np.isfinite(result.to_numpy(dtype=float)).all():
        raise AssertionError("paired demeaning produced nonfinite outcomes")

    audit = result.assign(
        year=keys["year"].to_numpy(),
        nq_opening_side=nq_side.to_numpy(),
        es_opening_side=es_side.to_numpy(),
    )
    group_means = audit.groupby(
        ["year", "nq_opening_side", "es_opening_side"], sort=False
    )[["nq_demeaned_points", "es_demeaned_points"]].mean()
    if not np.allclose(group_means.to_numpy(dtype=float), 0.0, rtol=0.0, atol=1e-12):
        raise AssertionError("paired within-stratum demeaning failed")
    return result


@dataclass(frozen=True)
class InjectionSolution:
    """Checked constant favorable effect injected into unsigned NQ outcomes."""

    injection_points_per_selected_day: float
    target_validation_sharpe: float
    achieved_validation_sharpe: float
    validation_sessions: int
    validation_trades: int
    injected_unsigned_points: pd.Series
    zero_filled_net_dollars: pd.Series


def _validated_power_eras(eras: pd.Series, dates: pd.DatetimeIndex) -> pd.Series:
    if not isinstance(eras, pd.Series):
        raise TypeError("power eras must be a pandas Series indexed by date")
    if not eras.index.equals(dates):
        raise ValueError("power eras must preserve exact date/index alignment")
    if eras.isna().any():
        raise ValueError("power eras must be finite discovery/A/B labels")
    labels = eras.astype(str)
    if set(labels) != set(POWER_ERAS):
        raise ValueError("power eras must contain exactly discovery, A, and B")
    return labels


def solve_side_aligned_injection(
    nq_demeaned_points: pd.Series,
    selected_side: pd.Series,
    eras: pd.Series,
    *,
    point_value_dollars: float,
    round_trip_cost_dollars: float,
    target_validation_sharpe: float = 0.50,
    initial_bracket_points: float = 0.25,
    max_injection_points: float = 1_000_000.0,
    sharpe_tolerance: float = 1e-10,
) -> InjectionSolution:
    """Solve one nonnegative side-aligned effect for validation Sharpe 0.50.

    The same point delta is injected into unsigned NQ outcomes in discovery,
    validation A, and validation B.  Calibration itself uses the zero-filled
    combined A+B selected-day primary-cost book.
    """

    if not isinstance(nq_demeaned_points, pd.Series):
        raise TypeError("demeaned NQ outcomes must be a pandas Series indexed by date")
    if not isinstance(nq_demeaned_points.index, pd.DatetimeIndex):
        raise TypeError("injection outcomes must use a DatetimeIndex")
    dates = _chronological_dates(nq_demeaned_points.index, name="injection dates")
    outcomes = _aligned_numeric_series(
        nq_demeaned_points, dates, name="demeaned NQ outcomes"
    )
    side = _aligned_sides(selected_side, dates, name="selected NQ side")
    era = _validated_power_eras(eras, dates)
    parameters = [
        point_value_dollars,
        round_trip_cost_dollars,
        target_validation_sharpe,
        initial_bracket_points,
        max_injection_points,
        sharpe_tolerance,
    ]
    if not np.isfinite(parameters).all():
        raise ValueError("injection parameters must all be finite")
    if point_value_dollars <= 0:
        raise ValueError("point value must be positive")
    if round_trip_cost_dollars < 0:
        raise ValueError("round-trip cost must be non-negative")
    if target_validation_sharpe <= 0:
        raise ValueError("target validation Sharpe must be positive")
    if initial_bracket_points <= 0 or max_injection_points < initial_bracket_points:
        raise ValueError("injection bracket bounds must be positive and ordered")
    if sharpe_tolerance <= 0:
        raise ValueError("Sharpe tolerance must be positive")

    validation = era.isin(["A", "B"]).to_numpy()
    if not validation.any() or not era.eq("A").any() or not era.eq("B").any():
        raise ValueError("injection calibration requires observations in both A and B")
    traded = side.ne(0).to_numpy()
    if not traded[validation].any():
        raise ValueError("injection calibration is impossible without validation trades")
    side_values = side.to_numpy(dtype=float)
    outcome_values = outcomes.to_numpy(dtype=float)

    def full_net(delta: float) -> np.ndarray:
        injected = outcome_values + side_values * float(delta)
        pnl = np.where(
            traded,
            side_values * injected * float(point_value_dollars)
            - float(round_trip_cost_dollars),
            0.0,
        )
        if not np.isfinite(pnl).all() or not np.equal(pnl[~traded], 0.0).all():
            raise ValueError("injected primary-cost book is not finite and zero-filled")
        return pnl

    def objective(delta: float) -> float:
        return float(zero_filled_sharpe(full_net(delta)[validation]) - target_validation_sharpe)

    # Sharpe of ``base + delta * trade`` has at most one interior extremum.
    # Include that point in an exponential grid so a valid nonnegative root is
    # not missed when the uninjected Sharpe starts above the target but first
    # falls below it, or starts below and briefly rises above it.
    validation_base = full_net(0.0)[validation]
    validation_slope = (
        traded.astype(float) * float(point_value_dollars)
    )[validation]
    base_centered = validation_base - validation_base.mean()
    slope_centered = validation_slope - validation_slope.mean()
    variance_base = float(np.dot(base_centered, base_centered) / (len(validation_base) - 1))
    covariance = float(np.dot(base_centered, slope_centered) / (len(validation_base) - 1))
    variance_slope = float(np.dot(slope_centered, slope_centered) / (len(validation_base) - 1))
    derivative_intercept = float(
        validation_slope.mean() * variance_base
        - validation_base.mean() * covariance
    )
    derivative_slope = float(
        validation_slope.mean() * covariance
        - validation_base.mean() * variance_slope
    )
    critical = (
        -derivative_intercept / derivative_slope
        if derivative_slope != 0.0
        else float("nan")
    )

    grid = [0.0, float(max_injection_points)]
    upper = float(initial_bracket_points)
    while upper < float(max_injection_points):
        grid.append(upper)
        upper *= 2.0
    if np.isfinite(critical) and 0.0 < critical < float(max_injection_points):
        grid.append(float(critical))
    grid = sorted(set(grid))
    evaluations: list[tuple[float, float]] = []
    for delta in grid:
        try:
            value = objective(delta)
        except ValueError:
            continue
        if np.isfinite(value):
            evaluations.append((delta, value))

    exact = [delta for delta, value in evaluations if abs(value) <= sharpe_tolerance]
    roots = exact.copy()
    for (left, left_value), (right, right_value) in zip(
        evaluations[:-1], evaluations[1:], strict=True
    ):
        if left_value * right_value >= 0.0:
            continue
        try:
            roots.append(
                float(
                    brentq(
                        objective,
                        left,
                        right,
                        xtol=min(1e-12, sharpe_tolerance / 10.0),
                        rtol=4.0 * np.finfo(float).eps,
                        maxiter=250,
                    )
                )
            )
        except (ValueError, RuntimeError):
            continue
    if not roots:
        raise ValueError(
            "no nonnegative injection can reach the target Sharpe within the checked bracket"
        )
    root = float(min(roots))

    if not np.isfinite(root) or root < 0:
        raise AssertionError("injection root must be finite and nonnegative")
    injected_values = outcome_values + side_values * root
    net_values = full_net(root)
    achieved = float(zero_filled_sharpe(net_values[validation]))
    if not np.isclose(
        achieved,
        target_validation_sharpe,
        rtol=0.0,
        atol=sharpe_tolerance,
    ):
        raise AssertionError(
            f"checked injection root missed target Sharpe: {achieved} vs {target_validation_sharpe}"
        )
    injected = pd.Series(
        injected_values,
        index=dates,
        name="nq_injected_unsigned_points",
    )
    net = pd.Series(net_values, index=dates, name="nq_injected_net_dollars")
    if not injected.index.equals(nq_demeaned_points.index) or not net.index.equals(
        nq_demeaned_points.index
    ):
        raise AssertionError("injection changed date/row alignment")
    return InjectionSolution(
        injection_points_per_selected_day=root,
        target_validation_sharpe=float(target_validation_sharpe),
        achieved_validation_sharpe=achieved,
        validation_sessions=int(validation.sum()),
        validation_trades=int((traded & validation).sum()),
        injected_unsigned_points=injected,
        zero_filled_net_dollars=net,
    )


def paired_stationary_bootstrap_donor_map(
    eras: pd.Series,
    *,
    expected_block: float,
    rng: np.random.Generator,
) -> pd.DataFrame:
    """Return one joint donor map sampled independently inside each power era.

    Mapping rows stay in unique chronological target-date order. Donor dates may
    repeat, as required by a bootstrap, but every target receives a donor from
    its own discovery/A/B era.  Apply this one map to the entire paired record
    frame rather than sampling NQ and ES separately.
    """

    if not isinstance(eras, pd.Series):
        raise TypeError("bootstrap eras must be a pandas Series indexed by target date")
    if not isinstance(eras.index, pd.DatetimeIndex):
        raise TypeError("bootstrap eras must use a DatetimeIndex")
    dates = _chronological_dates(eras.index, name="bootstrap target dates")
    labels = _validated_power_eras(eras, dates)
    if not np.isfinite(expected_block) or expected_block < 1:
        raise ValueError("expected block length must be finite and at least one")
    if not isinstance(rng, np.random.Generator):
        raise TypeError("rng must be a numpy Generator")

    donor_positions = np.empty(len(labels), dtype=int)
    era_values = labels.to_numpy()
    for label in POWER_ERAS:
        target_positions = np.flatnonzero(era_values == label)
        local_donors = stationary_bootstrap_indices(
            len(target_positions),
            expected_block=float(expected_block),
            rng=rng,
        )
        donor_positions[target_positions] = target_positions[local_donors]
    donor_dates = dates.take(donor_positions)
    mapping = pd.DataFrame(
        {
            "target_position": np.arange(len(dates), dtype=int),
            "era": era_values,
            "donor_position": donor_positions,
            "donor_date": donor_dates,
        },
        index=dates,
    )
    mapping.index.name = "target_date"
    if mapping.index.has_duplicates or not mapping.index.is_monotonic_increasing:
        raise AssertionError("bootstrap mapping lost unique chronological target order")
    if not np.array_equal(mapping["target_position"].to_numpy(), np.arange(len(mapping))):
        raise AssertionError("bootstrap target positions changed order")
    donor_eras = era_values[donor_positions]
    if not np.array_equal(donor_eras, era_values):
        raise AssertionError("stationary bootstrap crossed a discovery/A/B boundary")
    return mapping


def apply_paired_donor_map(
    paired_records: pd.DataFrame,
    donor_map: pd.DataFrame,
) -> pd.DataFrame:
    """Apply one audited donor map jointly to all columns of a paired panel."""

    if not isinstance(paired_records, pd.DataFrame) or not isinstance(donor_map, pd.DataFrame):
        raise TypeError("paired records and donor map must be pandas objects")
    dates = _chronological_dates(paired_records.index, name="paired record dates")
    required = {"target_position", "era", "donor_position", "donor_date"}
    missing = sorted(required - set(donor_map.columns))
    if missing:
        raise ValueError(f"donor map is missing columns: {missing}")
    if not donor_map.index.equals(dates):
        raise ValueError("donor map and paired records must share exact target-date alignment")
    target_positions = pd.to_numeric(donor_map["target_position"], errors="coerce").to_numpy()
    donor_positions_raw = pd.to_numeric(donor_map["donor_position"], errors="coerce").to_numpy()
    if (
        not np.isfinite(target_positions).all()
        or not np.isfinite(donor_positions_raw).all()
        or not np.equal(donor_positions_raw, np.floor(donor_positions_raw)).all()
        or not np.array_equal(target_positions, np.arange(len(dates)))
    ):
        raise ValueError("donor map positions must be finite integer target-order positions")
    donor_positions = donor_positions_raw.astype(int)
    if (donor_positions < 0).any() or (donor_positions >= len(dates)).any():
        raise ValueError("donor map contains an out-of-range donor position")
    if donor_map["era"].isna().any():
        raise ValueError("donor map eras must be finite discovery/A/B labels")
    era_values = donor_map["era"].astype(str).to_numpy()
    if set(era_values.tolist()) != set(POWER_ERAS):
        raise ValueError("donor map eras must contain exactly discovery, A, and B")
    if not np.array_equal(era_values[donor_positions], era_values):
        raise ValueError("donor map crosses a discovery/A/B boundary")
    declared_donor_dates = pd.DatetimeIndex(
        pd.to_datetime(donor_map["donor_date"], errors="coerce")
    )
    if declared_donor_dates.hasnans or not declared_donor_dates.equals(dates.take(donor_positions)):
        raise ValueError("donor dates do not reconcile to donor positions")

    sampled = paired_records.iloc[donor_positions].copy()
    sampled.index = dates
    sampled.index.name = paired_records.index.name
    if not sampled.index.is_unique or not sampled.index.is_monotonic_increasing:
        raise AssertionError("joint bootstrap sample lost chronological target order")
    return sampled
