"""Causal daily features and frozen signal definitions.

All decisions use information available no later than the completed 09:59 ET
bar.  Rolling normalizers are shifted by one session, so today's observation
can never enter its own threshold.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping

import numpy as np
import pandas as pd


def signed(values: pd.Series) -> pd.Series:
    """Return an integer {-1, 0, 1} sign with non-finite values mapped to 0."""

    numeric = pd.to_numeric(values, errors="coerce")
    result = np.sign(numeric).where(np.isfinite(numeric), 0)
    return result.fillna(0).astype("int8")


def _past_median(series: pd.Series, window: int, min_periods: int) -> pd.Series:
    return series.rolling(window=window, min_periods=min_periods).median().shift(1)


def add_features(
    sessions: pd.DataFrame,
    *,
    rolling_window: int = 60,
    rolling_min_periods: int = 40,
) -> pd.DataFrame:
    """Add opening, paper-baseline, and causal activity features."""

    required = {
        "date",
        "prev_close",
        "o0930",
        "c0959",
        "o1000",
        "o1001",
        "o1500",
        "c1529",
        "o1530",
        "c1559",
        "high30",
        "low30",
        "volume30",
        "rv30",
        "path30",
    }
    missing = sorted(required - set(sessions.columns))
    if missing:
        raise ValueError(f"missing session columns: {missing}")

    dates = pd.to_datetime(sessions["date"])
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("sessions must have unique chronological dates")
    if "instrument" in sessions and sessions["instrument"].nunique(dropna=False) != 1:
        raise ValueError("feature construction requires one instrument")
    out = sessions.reset_index(drop=True).copy()
    positive = (
        out[["prev_close", "o0930", "c0959", "o1000", "o1001", "o1500", "c1529", "o1530", "c1559"]]
        > 0
    ).all(axis=1)
    if not positive.all():
        raise ValueError("feature prices must be strictly positive")

    out["gap_log"] = np.log(out["o0930"] / out["prev_close"])
    out["opening_log"] = np.log(out["c0959"] / out["o0930"])
    out["paper_r1_log"] = np.log(out["c0959"] / out["prev_close"])
    out["paper_r12_log"] = np.log(out["c1529"] / out["o1500"])
    out["paper_r13_log"] = np.log(out["c1559"] / out["o1530"])
    out["rest_points_1000"] = out["c1559"] - out["o1000"]
    out["rest_points_1001"] = out["c1559"] - out["o1001"]

    out["gap_sign"] = signed(out["gap_log"])
    out["opening_sign"] = signed(out["opening_log"])
    out["paper_r1_sign"] = signed(out["paper_r1_log"])
    out["paper_r12_sign"] = signed(out["paper_r12_log"])

    open_range = out["high30"] - out["low30"]
    close_from_low = (out["c0959"] - out["low30"]) / open_range.replace(0, np.nan)
    out["directional_clv"] = np.where(
        out["opening_sign"].gt(0),
        close_from_low,
        np.where(out["opening_sign"].lt(0), 1.0 - close_from_low, np.nan),
    )
    out["path_efficiency"] = out["opening_log"].abs() / out["path30"].replace(0, np.nan)
    out["opening_abs"] = out["opening_log"].abs()
    out["gap_abs"] = out["gap_log"].abs()
    out["total_r1_abs"] = out["paper_r1_log"].abs()
    out["min_component_abs"] = np.minimum(out["gap_abs"], out["opening_abs"])

    normalizers = {
        "magnitude_rel": "opening_abs",
        "gap_magnitude_rel": "gap_abs",
        "total_r1_magnitude_rel": "total_r1_abs",
        "min_component_rel": "min_component_abs",
        "rv_rel": "rv30",
        "volume_rel": "volume30",
        "efficiency_rel": "path_efficiency",
        "clv_rel": "directional_clv",
    }
    for output, source in normalizers.items():
        denominator = _past_median(out[source], rolling_window, rolling_min_periods)
        out[output] = out[source] / denominator.replace(0, np.nan)

    return out


def base_signals(features: pd.DataFrame) -> pd.DataFrame:
    """Return parameter-free paper, primary, and placebo signals."""

    opening = features["opening_sign"].astype("int8")
    gap = features["gap_sign"].astype("int8")
    paper = features["paper_r1_sign"].astype("int8")
    paper_r12 = features["paper_r12_sign"].astype("int8")
    agree = opening.ne(0) & opening.eq(gap)
    oppose = opening.ne(0) & gap.ne(0) & opening.eq(-gap)

    signals = pd.DataFrame(index=features.index)
    paper_rule = pd.Series(np.where(features["paper_r1_log"].gt(0), 1, -1), index=features.index, dtype="int8")
    paper_r12_rule = pd.Series(np.where(features["paper_r12_log"].gt(0), 1, -1), index=features.index, dtype="int8")
    signals["paper_r1"] = paper_rule
    signals["paper_r1_r12_agree"] = paper_rule.where(paper_rule.eq(paper_r12_rule), 0).astype("int8")
    signals["opening_ungated"] = opening
    signals["confirmed_gap"] = opening.where(agree, 0).astype("int8")
    signals["mirror_gap_opposition"] = opening.where(oppose, 0).astype("int8")
    signals["overnight_only"] = gap
    signals["selected_day_always_long"] = agree.astype("int8")
    return signals


OPENING_FEATURE_COLUMNS = [
    "date",
    "instrument",
    "gap_log",
    "opening_log",
    "paper_r1_log",
    "gap_sign",
    "opening_sign",
    "paper_r1_sign",
    "directional_clv",
    "path_efficiency",
    "opening_abs",
    "gap_abs",
    "total_r1_abs",
    "min_component_abs",
    "magnitude_rel",
    "gap_magnitude_rel",
    "total_r1_magnitude_rel",
    "min_component_rel",
    "rv_rel",
    "volume_rel",
    "efficiency_rel",
    "clv_rel",
]


BASELINE_FEATURE_COLUMNS = [
    "date",
    "instrument",
    "paper_r1_log",
    "paper_r12_log",
    "paper_r1_sign",
    "paper_r12_sign",
]


def opening_feature_frame(
    sessions: pd.DataFrame,
    *,
    rolling_window: int = 60,
    rolling_min_periods: int = 40,
) -> pd.DataFrame:
    """Expose only information available when the clock reaches 10:00 ET."""

    required = {
        "date",
        "prev_close",
        "o0930",
        "c0959",
        "high30",
        "low30",
        "volume30",
        "rv30",
        "path30",
    }
    missing = sorted(required - set(sessions.columns))
    if missing:
        raise ValueError(f"missing opening feature columns: {missing}")
    dates = pd.to_datetime(sessions["date"])
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("sessions must have unique chronological dates")
    if "instrument" in sessions and sessions["instrument"].nunique(dropna=False) != 1:
        raise ValueError("feature construction requires one instrument")
    prices = sessions[["prev_close", "o0930", "c0959"]].apply(pd.to_numeric, errors="coerce")
    if not np.isfinite(prices.to_numpy()).all() or not prices.gt(0).all().all():
        raise ValueError("opening feature prices must be finite and strictly positive")
    result = pd.DataFrame({"date": dates.to_numpy()}, index=sessions.index)
    if "instrument" in sessions:
        result["instrument"] = sessions["instrument"].to_numpy()
    result["gap_log"] = np.log(prices["o0930"] / prices["prev_close"])
    result["opening_log"] = np.log(prices["c0959"] / prices["o0930"])
    result["paper_r1_log"] = result["gap_log"] + result["opening_log"]
    result["gap_sign"] = signed(result["gap_log"])
    result["opening_sign"] = signed(result["opening_log"])
    result["paper_r1_sign"] = signed(result["paper_r1_log"])
    open_range = pd.to_numeric(sessions["high30"]) - pd.to_numeric(sessions["low30"])
    close_from_low = (prices["c0959"] - pd.to_numeric(sessions["low30"])) / open_range.replace(0, np.nan)
    result["directional_clv"] = np.where(
        result["opening_sign"].gt(0),
        close_from_low,
        np.where(result["opening_sign"].lt(0), 1.0 - close_from_low, np.nan),
    )
    result["path_efficiency"] = result["opening_log"].abs() / pd.to_numeric(sessions["path30"]).replace(0, np.nan)
    result["opening_abs"] = result["opening_log"].abs()
    result["gap_abs"] = result["gap_log"].abs()
    result["total_r1_abs"] = result["paper_r1_log"].abs()
    result["min_component_abs"] = np.minimum(result["gap_abs"], result["opening_abs"])
    raw_sources = {
        "magnitude_rel": result["opening_abs"],
        "gap_magnitude_rel": result["gap_abs"],
        "total_r1_magnitude_rel": result["total_r1_abs"],
        "min_component_rel": result["min_component_abs"],
        "rv_rel": pd.to_numeric(sessions["rv30"], errors="coerce"),
        "volume_rel": pd.to_numeric(sessions["volume30"], errors="coerce"),
        "efficiency_rel": result["path_efficiency"],
        "clv_rel": result["directional_clv"],
    }
    for name, source in raw_sources.items():
        denominator = _past_median(source, rolling_window, rolling_min_periods)
        result[name] = source / denominator.replace(0, np.nan)
    result.attrs["information_available_et"] = "10:00:00"
    return result.reset_index(drop=True)


def baseline_feature_frame(sessions: pd.DataFrame) -> pd.DataFrame:
    """Expose only Gao-rule information available at the 15:30 decision."""

    required = {"date", "prev_close", "o0930", "c0959", "o1500", "c1529"}
    missing = sorted(required - set(sessions.columns))
    if missing:
        raise ValueError(f"missing baseline feature columns: {missing}")
    dates = pd.to_datetime(sessions["date"])
    if dates.duplicated().any() or not dates.is_monotonic_increasing:
        raise ValueError("sessions must have unique chronological dates")
    prices = sessions[["prev_close", "o0930", "c0959", "o1500", "c1529"]].apply(
        pd.to_numeric, errors="coerce"
    )
    if not np.isfinite(prices.to_numpy()).all() or not prices.gt(0).all().all():
        raise ValueError("baseline feature prices must be finite and strictly positive")
    result = pd.DataFrame({"date": dates.to_numpy()}, index=sessions.index)
    if "instrument" in sessions:
        result["instrument"] = sessions["instrument"].to_numpy()
    result["paper_r1_log"] = np.log(prices["c0959"] / prices["prev_close"])
    result["paper_r12_log"] = np.log(prices["c1529"] / prices["o1500"])
    result["paper_r1_sign"] = signed(result["paper_r1_log"])
    result["paper_r12_sign"] = signed(result["paper_r12_log"])
    result.attrs["information_available_et"] = "15:30:00"
    return result.reset_index(drop=True)


def opening_signals(features: pd.DataFrame) -> pd.DataFrame:
    required = {"gap_sign", "opening_sign", "paper_r1_sign"}
    missing = sorted(required - set(features.columns))
    if missing:
        raise ValueError(f"missing causal opening features: {missing}")
    opening = features["opening_sign"].astype("int8")
    gap = features["gap_sign"].astype("int8")
    agree = opening.ne(0) & opening.eq(gap)
    oppose = opening.ne(0) & gap.ne(0) & opening.eq(-gap)
    return pd.DataFrame(
        {
            "opening_ungated": opening,
            "total_r1_direction": features["paper_r1_sign"].astype("int8"),
            "confirmed_gap": opening.where(agree, 0).astype("int8"),
            "mirror_gap_opposition": opening.where(oppose, 0).astype("int8"),
            "overnight_only": gap,
            "selected_day_always_long": agree.astype("int8"),
        },
        index=features.index,
    )


def baseline_signals(features: pd.DataFrame) -> pd.DataFrame:
    required = {"paper_r1_log", "paper_r12_log"}
    missing = sorted(required - set(features.columns))
    if missing:
        raise ValueError(f"missing baseline features: {missing}")
    paper_rule = pd.Series(
        np.where(features["paper_r1_log"].gt(0), 1, -1), index=features.index, dtype="int8"
    )
    paper_r12_rule = pd.Series(
        np.where(features["paper_r12_log"].gt(0), 1, -1), index=features.index, dtype="int8"
    )
    return pd.DataFrame(
        {
            "paper_r1": paper_rule,
            "paper_r1_r12_agree": paper_rule.where(paper_rule.eq(paper_r12_rule), 0).astype("int8"),
        },
        index=features.index,
    )


def rate_matched_threshold(
    feature: pd.Series,
    target_trades: int,
) -> float:
    """Fit a deterministic upper-tail threshold with approximately target count."""

    valid = pd.to_numeric(feature, errors="coerce").dropna().sort_values(ascending=False)
    if target_trades <= 0 or valid.empty:
        return float("inf")
    rank = min(int(target_trades), len(valid)) - 1
    return float(valid.iloc[rank])


@dataclass(frozen=True)
class FrozenThresholds:
    magnitude_rel: float
    gap_magnitude_rel: float
    total_r1_magnitude_rel: float
    min_component_rel: float
    rv_rel: float
    volume_rel: float
    efficiency_rel: float
    clv_rel: float

    def as_dict(self) -> dict[str, float]:
        return {
            "magnitude_rel": self.magnitude_rel,
            "gap_magnitude_rel": self.gap_magnitude_rel,
            "total_r1_magnitude_rel": self.total_r1_magnitude_rel,
            "min_component_rel": self.min_component_rel,
            "rv_rel": self.rv_rel,
            "volume_rel": self.volume_rel,
            "efficiency_rel": self.efficiency_rel,
            "clv_rel": self.clv_rel,
        }


def fit_rate_matched_thresholds(
    discovery_features: pd.DataFrame,
    target_signal: pd.Series,
) -> FrozenThresholds:
    target_trades = int(pd.Series(target_signal).ne(0).sum())
    names = [
        "magnitude_rel",
        "gap_magnitude_rel",
        "total_r1_magnitude_rel",
        "min_component_rel",
        "rv_rel",
        "volume_rel",
        "efficiency_rel",
        "clv_rel",
    ]
    values = {
        name: rate_matched_threshold(discovery_features[name], target_trades)
        for name in names
    }
    return FrozenThresholds(**values)


def discovery_family_signals(
    features: pd.DataFrame,
    thresholds: FrozenThresholds | Mapping[str, float],
    *,
    es_opening_sign: pd.Series | None = None,
) -> pd.DataFrame:
    """Reproduce the declared opening-signal discovery family.

    Thresholds must be fitted on the discovery period and then passed unchanged
    to later periods. Each complete null draw refits them on that draw's own
    reconstructed discovery segment before validation is scored.
    """

    values = thresholds.as_dict() if isinstance(thresholds, FrozenThresholds) else dict(thresholds)
    base = opening_signals(features)
    opening = features["opening_sign"].astype("int8")
    confirmed = base["confirmed_gap"]
    output = pd.DataFrame(
        {
            "opening_ungated": base["opening_ungated"],
            "total_r1_direction": features["paper_r1_sign"].astype("int8"),
            "overnight_only": base["overnight_only"],
            "confirmed_gap": confirmed,
            "mirror_gap_opposition": base["mirror_gap_opposition"],
        },
        index=features.index,
    )
    gate_map = {
        "opening_magnitude": "magnitude_rel",
        "gap_magnitude": "gap_magnitude_rel",
        "total_r1_magnitude": "total_r1_magnitude_rel",
        "min_component": "min_component_rel",
        "rv": "rv_rel",
        "volume": "volume_rel",
        "efficiency": "efficiency_rel",
        "clv": "clv_rel",
    }
    for label, column in gate_map.items():
        gate = features[column].ge(float(values[column]))
        output[f"{label}_gate"] = opening.where(gate, 0).astype("int8")
        output[f"gap_plus_{label}"] = confirmed.where(gate, 0).astype("int8")

    if es_opening_sign is not None:
        if isinstance(es_opening_sign, pd.Series):
            if not es_opening_sign.index.equals(features.index):
                raise ValueError("ES opening signal index must exactly match NQ features")
            aligned_es = es_opening_sign.copy()
        else:
            if len(es_opening_sign) != len(features):
                raise ValueError("ES opening signal must align with NQ features")
            aligned_es = pd.Series(np.asarray(es_opening_sign), index=features.index)
        if aligned_es.isna().any() or not aligned_es.isin([-1, 0, 1]).all():
            raise ValueError("ES opening signal must contain finite -1, 0, or 1")
        aligned_es = aligned_es.astype("int8")
        output["es_opening_confirmation"] = opening.where(opening.eq(aligned_es) & opening.ne(0), 0).astype("int8")
        output["gap_plus_es_confirmation"] = confirmed.where(confirmed.eq(aligned_es), 0).astype("int8")
    return output


def replace_gap_features(
    features: pd.DataFrame,
    gap_log: pd.Series | np.ndarray,
    *,
    rolling_window: int = 60,
    rolling_min_periods: int = 40,
) -> pd.DataFrame:
    """Recompute every gap-dependent feature for a null donor mapping."""

    if len(features) != len(gap_log):
        raise ValueError("replacement gap must align with features")
    out = features.copy()
    replacement = pd.Series(np.asarray(gap_log, dtype=float), index=out.index)
    out["gap_log"] = replacement
    out["gap_abs"] = replacement.abs()
    out["gap_sign"] = signed(replacement)
    out["paper_r1_log"] = out["gap_log"] + out["opening_log"]
    out["paper_r1_sign"] = signed(out["paper_r1_log"])
    out["total_r1_abs"] = out["paper_r1_log"].abs()
    out["min_component_abs"] = np.minimum(out["gap_abs"], out["opening_abs"])
    for output, source in {
        "gap_magnitude_rel": "gap_abs",
        "total_r1_magnitude_rel": "total_r1_abs",
        "min_component_rel": "min_component_abs",
    }.items():
        denominator = _past_median(out[source], rolling_window, rolling_min_periods)
        out[output] = out[source] / denominator.replace(0, np.nan)
    return out
