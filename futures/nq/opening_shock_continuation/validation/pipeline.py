"""Bounded discovery-selection pipeline used identically on real and null data."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

import numpy as np
import pandas as pd

from ..backtest_engine.data import INSTRUMENT_SPECS
from ..strategy.signals import (
    FrozenThresholds,
    discovery_family_signals,
    fit_rate_matched_thresholds,
    opening_signals,
    replace_gap_features,
)
from .nulls import conditional_paired_gap_permutation, era_paired_circular_shift


@dataclass(frozen=True)
class SelectionResult:
    candidate_id: str
    candidate: str
    discovery_statistic: float
    discovery_trades: int
    validation_statistic: float
    validation_trades: int
    thresholds: FrozenThresholds


def zero_filled_sharpe(pnl: np.ndarray) -> float:
    values = np.asarray(pnl, dtype=float)
    if len(values) < 2 or not np.isfinite(values).all():
        return float("nan")
    scale = float(np.std(values, ddof=1))
    return float(np.sqrt(252.0) * np.mean(values) / scale) if scale > 0 else float("nan")


def _validated_mask(mask: np.ndarray, n: int, name: str) -> np.ndarray:
    values = np.asarray(mask)
    if values.ndim != 1 or len(values) != n or values.dtype != np.dtype(bool):
        raise ValueError(f"{name} mask must be one aligned boolean value per session")
    if not values.any():
        raise ValueError(f"{name} mask must select at least one session")
    return values


def _validate_selection_alignment(
    sessions: pd.DataFrame,
    nq_features: pd.DataFrame,
    es_features: pd.DataFrame,
) -> None:
    if not (len(sessions) == len(nq_features) == len(es_features)):
        raise ValueError("selection frames must align")
    if not sessions.index.equals(nq_features.index) or not sessions.index.equals(es_features.index):
        raise ValueError("selection frame indexes must exactly align")
    if any("date" not in frame for frame in (sessions, nq_features, es_features)):
        raise ValueError("every selection frame must contain a date column")
    dates = [pd.to_datetime(frame["date"], errors="coerce") for frame in (sessions, nq_features, es_features)]
    if any(series.isna().any() for series in dates):
        raise ValueError("selection dates must be finite")
    if any(series.duplicated().any() or not series.is_monotonic_increasing for series in dates):
        raise ValueError("selection dates must be unique and chronological")
    if not dates[0].equals(dates[1]) or not dates[0].equals(dates[2]):
        raise ValueError("NQ sessions and paired NQ/ES features must use identical dates")


def candidate_net_pnl(
    sessions: pd.DataFrame,
    signals: pd.DataFrame,
    *,
    instrument: str,
    entry_column: str,
    exit_column: str,
    slippage_ticks_per_side: float,
    round_trip_fees_usd: float,
) -> np.ndarray:
    if len(sessions) != len(signals) or not sessions.index.equals(signals.index):
        raise ValueError("candidate signals must exactly align with sessions")
    sides = signals.to_numpy(dtype=float)
    if not np.isfinite(sides).all() or not np.isin(sides, [-1, 0, 1]).all():
        raise ValueError("candidate signals must contain finite -1, 0, or 1")
    entry = pd.to_numeric(sessions[entry_column], errors="coerce").to_numpy(dtype=float)
    exit_price = pd.to_numeric(sessions[exit_column], errors="coerce").to_numpy(dtype=float)
    if not np.isfinite(entry).all() or not np.isfinite(exit_price).all():
        raise ValueError("pipeline execution prices must be finite")
    spec = INSTRUMENT_SPECS[instrument]
    point_move = exit_price - entry
    round_trip_cost = (
        2.0 * slippage_ticks_per_side * spec.tick_size * spec.multiplier
        + round_trip_fees_usd
    )
    return sides * point_move[:, None] * spec.multiplier - (sides != 0) * round_trip_cost


def _thresholds_and_family(
    nq_features: pd.DataFrame,
    es_features: pd.DataFrame,
    discovery_mask: np.ndarray,
) -> tuple[FrozenThresholds, pd.DataFrame]:
    target = opening_signals(nq_features)["confirmed_gap"]
    thresholds = fit_rate_matched_thresholds(
        nq_features.loc[discovery_mask].reset_index(drop=True),
        target.loc[discovery_mask].reset_index(drop=True),
    )
    family = discovery_family_signals(
        nq_features,
        thresholds,
        es_opening_sign=es_features["opening_sign"],
    )
    return thresholds, family


def select_and_score(
    sessions: pd.DataFrame,
    nq_features: pd.DataFrame,
    es_features: pd.DataFrame,
    discovery_mask: np.ndarray,
    validation_mask: np.ndarray,
    candidate_ids: dict[str, str],
    *,
    entry_column: str,
    exit_column: str,
    slippage_ticks_per_side: float,
    round_trip_fees_usd: float,
) -> SelectionResult:
    _validate_selection_alignment(sessions, nq_features, es_features)
    discovery_mask = _validated_mask(discovery_mask, len(sessions), "discovery")
    validation_mask = _validated_mask(validation_mask, len(sessions), "validation")
    if np.any(discovery_mask & validation_mask):
        raise ValueError("discovery and validation masks must not overlap")
    if len(candidate_ids) != 23 or len(set(candidate_ids.values())) != 23:
        raise ValueError("frozen selection requires 23 candidates with unique IDs")
    thresholds, family = _thresholds_and_family(nq_features, es_features, discovery_mask)
    if set(family.columns) != set(candidate_ids):
        raise ValueError("runtime candidate family differs from frozen manifest")
    family = family[list(candidate_ids)]
    pnl = candidate_net_pnl(
        sessions,
        family,
        instrument="NQ",
        entry_column=entry_column,
        exit_column=exit_column,
        slippage_ticks_per_side=slippage_ticks_per_side,
        round_trip_fees_usd=round_trip_fees_usd,
    )
    candidates = []
    for column, name in enumerate(family.columns):
        train = pnl[discovery_mask, column]
        statistic = zero_filled_sharpe(train)
        trades = int(family.loc[discovery_mask, name].ne(0).sum())
        candidates.append(
            {
                "candidate_id": candidate_ids[name],
                "candidate": name,
                "statistic": statistic if np.isfinite(statistic) else -np.inf,
                "trades": trades,
                "column": column,
            }
        )
    ranking = sorted(
        candidates,
        key=lambda item: (-float(item["statistic"]), int(item["trades"]), str(item["candidate_id"])),
    )
    selected = ranking[0]
    if not np.isfinite(float(selected["statistic"])):
        raise ValueError("all discovery candidates are invalid")
    validation_pnl = pnl[validation_mask, int(selected["column"])]
    validation_statistic = zero_filled_sharpe(validation_pnl)
    if not np.isfinite(validation_statistic):
        raise ValueError("selected candidate has invalid validation statistic")
    validation_trades = int(
        family.loc[validation_mask, str(selected["candidate"])].ne(0).sum()
    )
    return SelectionResult(
        candidate_id=str(selected["candidate_id"]),
        candidate=str(selected["candidate"]),
        discovery_statistic=float(selected["statistic"]),
        discovery_trades=int(selected["trades"]),
        validation_statistic=float(validation_statistic),
        validation_trades=validation_trades,
        thresholds=thresholds,
    )


def _agreement_count_table(features: pd.DataFrame) -> pd.DataFrame:
    signals = opening_signals(features)["confirmed_gap"]
    years = pd.to_datetime(features["date"]).dt.year
    return pd.DataFrame(
        {
            "trades": signals.ne(0).groupby(years).sum(),
            "longs": signals.gt(0).groupby(years).sum(),
            "shorts": signals.lt(0).groupby(years).sum(),
        }
    )


def null_draw(
    kind: Literal["conditional", "circular"],
    sessions: pd.DataFrame,
    nq_features: pd.DataFrame,
    es_features: pd.DataFrame,
    discovery_mask: np.ndarray,
    validation_mask: np.ndarray,
    candidate_ids: dict[str, str],
    rng: np.random.Generator,
    *,
    entry_column: str,
    exit_column: str,
    slippage_ticks_per_side: float,
    round_trip_fees_usd: float,
    rolling_window: int,
    rolling_min_periods: int,
) -> tuple[SelectionResult, np.ndarray]:
    dates = pd.to_datetime(nq_features["date"])
    if not dates.equals(pd.to_datetime(es_features["date"])):
        raise ValueError("paired null requires identical NQ/ES dates")
    nq_gap = nq_features["gap_log"].to_numpy()
    es_gap = es_features["gap_log"].to_numpy()
    if not np.isfinite(nq_gap).all() or not np.isfinite(es_gap).all():
        raise ValueError("paired null gaps must be finite")
    for name, sides in {
        "NQ": nq_features["opening_sign"].to_numpy(),
        "ES": es_features["opening_sign"].to_numpy(),
    }.items():
        if not np.isfinite(sides).all() or not np.isin(sides, [-1, 0, 1]).all():
            raise ValueError(f"{name} opening sides must be finite -1, 0, or 1")
    if kind == "conditional":
        nq_null, es_null, donor = conditional_paired_gap_permutation(
            nq_gap,
            es_gap,
            nq_features["opening_sign"].to_numpy(),
            es_features["opening_sign"].to_numpy(),
            dates,
            rng,
        )
        original_strata = np.column_stack(
            [dates.dt.year.to_numpy(), nq_features["opening_sign"], es_features["opening_sign"]]
        )
        if not np.array_equal(original_strata, original_strata[donor]):
            raise AssertionError("conditional donor crossed a frozen stratum")
    elif kind == "circular":
        years = dates.dt.year.to_numpy()
        nq_null, es_null, donor = era_paired_circular_shift(
            nq_gap,
            es_gap,
            years,
            rng,
            dates=dates,
        )
        if not np.array_equal(years, years[donor]):
            raise AssertionError("circular donor crossed a frozen calendar year")
    else:
        raise KeyError(kind)
    if np.array_equal(donor, np.arange(len(donor))):
        raise ValueError("null donor mapping is identity")
    if not np.array_equal(np.sort(donor), np.arange(len(donor))):
        raise AssertionError("null donor mapping must be a complete permutation")
    # A single donor map must preserve exact NQ/ES gap vectors.
    if not np.array_equal(nq_null, nq_gap[donor]) or not np.array_equal(es_null, es_gap[donor]):
        raise AssertionError("paired gap donor mapping was not preserved")

    nq_replaced = replace_gap_features(
        nq_features,
        nq_null,
        rolling_window=rolling_window,
        rolling_min_periods=rolling_min_periods,
    )
    es_replaced = replace_gap_features(
        es_features,
        es_null,
        rolling_window=rolling_window,
        rolling_min_periods=rolling_min_periods,
    )
    if kind == "conditional":
        pd.testing.assert_frame_equal(
            _agreement_count_table(nq_features), _agreement_count_table(nq_replaced)
        )
        pd.testing.assert_frame_equal(
            _agreement_count_table(es_features), _agreement_count_table(es_replaced)
        )
    result = select_and_score(
        sessions,
        nq_replaced,
        es_replaced,
        discovery_mask,
        validation_mask,
        candidate_ids,
        entry_column=entry_column,
        exit_column=exit_column,
        slippage_ticks_per_side=slippage_ticks_per_side,
        round_trip_fees_usd=round_trip_fees_usd,
    )
    return result, donor
