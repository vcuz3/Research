"""Causal features for HYP-0001.

The primary source named by the hypothesis is a five-minute file, but its
timestamp is timezone-naive despite the frozen contract saying UTC.  The loader
below therefore derives diagnostic five-minute bars from the audited,
timezone-aware one-minute Databento source used by ``nq.noise_vwap``.  This is a
data-quality fallback, not permission to reinterpret the frozen data contract;
the validation report records the mismatch and blocks P&L.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from collections import deque
from pathlib import Path

import numpy as np
import pandas as pd


NQ_ROOT = Path(__file__).resolve().parents[2]
DATA_ROOT = NQ_ROOT / "data"
RTH_START = 9 * 60 + 30
RTH_END = 16 * 60
DECISION_START = 10 * 60
EXPECTED_5M_SLOTS = np.arange(RTH_START, RTH_END, 5, dtype=int)


def load_canonical_rth_5m(
    instrument: str = "NQ", minimum_1m_bars: int = 350
) -> tuple[pd.DataFrame, dict]:
    """Build causal RTH five-minute bars from the audited clean one-minute file."""
    inst = instrument.upper()
    path = DATA_ROOT / f"{inst}_1m_clean.parquet"
    raw = pd.read_parquet(path)
    ts = pd.to_datetime(raw["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    frame = raw.copy()
    frame["et"] = et
    frame["date"] = et.dt.tz_localize(None).dt.normalize()
    frame["tod"] = et.dt.hour * 60 + et.dt.minute

    raw_duplicate_ts = int(ts.duplicated().sum())
    raw_out_of_order = int((ts.diff().dropna() < pd.Timedelta(0)).sum())
    rth = frame[(frame["tod"] >= RTH_START) & (frame["tod"] < RTH_END)].copy()
    session_counts = rth.groupby("date", sort=True).size()
    eligible_dates = session_counts[session_counts >= minimum_1m_bars].index
    excluded_sessions = int((session_counts < minimum_1m_bars).sum())
    rth = rth[rth["date"].isin(eligible_dates)].sort_values("et")

    multi_symbol_sessions = int((rth.groupby("date")["symbol"].nunique() > 1).sum())
    rth_roll_rows = int(rth["is_roll"].astype(bool).sum())
    one_minute_gaps = int(
        rth.groupby("date")["et"]
        .diff()
        .gt(pd.Timedelta(minutes=1))
        .sum()
    )

    aggregations = {
        "symbol": "last",
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "is_roll": "max",
    }
    bars = (
        rth.set_index("et")
        .groupby("date", group_keys=False)
        .resample("5min")
        .agg(aggregations)
        .dropna(subset=["open", "close"])
        .reset_index()
    )
    bars["date"] = bars["et"].dt.tz_localize(None).dt.normalize()
    bars["tod"] = bars["et"].dt.hour * 60 + bars["et"].dt.minute
    bars = bars[(bars["tod"] >= RTH_START) & (bars["tod"] < RTH_END)]
    bars = bars.sort_values(["date", "tod"]).reset_index(drop=True)

    observed = bars.groupby("date")["tod"].apply(set)
    expected = set(EXPECTED_5M_SLOTS.tolist())
    missing_5m = int(sum(len(expected - slots) for slots in observed))
    duplicate_5m = int(bars.duplicated(["date", "tod"]).sum())
    out_of_order_5m = int(
        (bars["et"].diff().dropna() < pd.Timedelta(0)).sum()
    )
    audit = {
        "instrument": inst,
        "source_path": path.as_posix(),
        "source_timestamp_dtype": str(raw["ts_utc"].dtype),
        "source_timezone_aware": bool(getattr(raw["ts_utc"].dt, "tz", None) is not None),
        "raw_rows": int(len(raw)),
        "raw_duplicate_timestamps": raw_duplicate_ts,
        "raw_out_of_order_transitions": raw_out_of_order,
        "rth_sessions_before_completeness_filter": int(len(session_counts)),
        "rth_sessions_excluded_below_minimum": excluded_sessions,
        "minimum_1m_bars_per_session": int(minimum_1m_bars),
        "eligible_sessions": int(bars["date"].nunique()),
        "eligible_start": str(bars["date"].min().date()),
        "eligible_end": str(bars["date"].max().date()),
        "rth_one_minute_gap_transitions": one_minute_gaps,
        "rth_roll_rows": rth_roll_rows,
        "rth_multi_symbol_sessions": multi_symbol_sessions,
        "five_minute_rows": int(len(bars)),
        "five_minute_duplicate_date_slots": duplicate_5m,
        "five_minute_out_of_order_transitions": out_of_order_5m,
        "five_minute_missing_expected_slots": missing_5m,
        "five_minute_min_bars_per_session": int(bars.groupby("date").size().min()),
        "five_minute_max_bars_per_session": int(bars.groupby("date").size().max()),
    }
    return bars, audit


def add_vol_normalized_momentum(
    bars: pd.DataFrame,
    alpha: float = 0.5,
    horizons_minutes: tuple[int, ...] = (15, 30, 60),
) -> pd.DataFrame:
    """Add the entry-causal day-vol scalar and normalized horizon returns.

    The first five-minute return is bar close / bar open, giving the six opening
    returns specified for 09:30--10:00.  Later returns are close-to-close.
    """
    if not 0.0 <= alpha <= 1.0:
        raise ValueError("alpha must be in [0, 1]")
    out = bars.sort_values(["date", "tod"]).copy()
    prior_close = out.groupby("date", sort=False)["close"].shift(1)
    denominator = prior_close.fillna(out["open"])
    out["log_return_5m"] = np.log(out["close"] / denominator)
    daily_rv = out.groupby("date", sort=True)["log_return_5m"].apply(
        lambda values: float(np.square(values).sum())
    )
    opening_rv = (
        out[out["tod"] < DECISION_START]
        .groupby("date", sort=True)["log_return_5m"]
        .apply(lambda values: float(np.square(values).sum()))
    )
    sigma = np.sqrt(alpha * daily_rv.shift(1) + (1.0 - alpha) * opening_rv)
    out["sigma_day"] = out["date"].map(sigma)
    for minutes in horizons_minutes:
        if minutes % 5:
            raise ValueError(f"horizon must be a multiple of five minutes: {minutes}")
        bars_back = minutes // 5
        raw = out.groupby("date", sort=False)["close"].transform(
            lambda values: np.log(values).diff(bars_back)
        )
        out[f"momentum_{minutes}m"] = raw
        out[f"normalized_{minutes}m"] = raw / out["sigma_day"]
    return out


def causal_sign_split_rank(
    values: np.ndarray, window: int, minimum_fraction: float
) -> dict[str, np.ndarray]:
    """Rank current magnitude against same-sign values in prior *sessions*.

    NaNs remain in the session-counted window, so missing slots do not silently
    lengthen a W-session reference into W observed values.  Ties use the stated
    ``<=`` empirical-CDF convention.
    """
    if window <= 0:
        raise ValueError("window must be positive")
    if not 0.0 <= minimum_fraction <= 1.0:
        raise ValueError("minimum_fraction must be in [0, 1]")
    n = len(values)
    rank = np.full(n, np.nan)
    positive_count = np.zeros(n, dtype=np.int32)
    negative_count = np.zeros(n, dtype=np.int32)
    history_count = np.zeros(n, dtype=np.int32)
    positive: list[float] = []
    negative: list[float] = []
    history: deque[float] = deque()
    required = int(np.ceil(window * minimum_fraction))

    for i, raw in enumerate(np.asarray(values, dtype=float)):
        history_count[i] = len(history)
        positive_count[i] = len(positive)
        negative_count[i] = len(negative)
        if len(history) == window and np.isfinite(raw) and raw != 0.0:
            reference = positive if raw > 0.0 else negative
            if len(reference) >= required:
                rank[i] = bisect_right(reference, abs(float(raw))) / len(reference)

        history.append(raw)
        if np.isfinite(raw) and raw != 0.0:
            insort(positive if raw > 0.0 else negative, abs(float(raw)))
        if len(history) > window:
            old = history.popleft()
            if np.isfinite(old) and old != 0.0:
                reference = positive if old > 0.0 else negative
                location = bisect_left(reference, abs(float(old)))
                del reference[location]

    return {
        "rank": rank,
        "positive_count": positive_count,
        "negative_count": negative_count,
        "history_count": history_count,
        "required_sign_count": np.full(n, required, dtype=np.int32),
    }


def build_same_slot_features(
    bars: pd.DataFrame,
    window: int,
    minimum_fraction: float,
    alpha: float = 0.5,
    horizons_minutes: tuple[int, ...] = (15, 30, 60),
    weights: tuple[float, ...] = (0.5, 0.3, 0.2),
) -> pd.DataFrame:
    """Build the frozen same-slot feature panel for one W/alpha cell."""
    if len(horizons_minutes) != len(weights) or not np.isclose(sum(weights), 1.0):
        raise ValueError("horizons and convex weights must align and sum to one")
    enriched = add_vol_normalized_momentum(bars, alpha, horizons_minutes)
    dates = pd.Index(enriched["date"].drop_duplicates().sort_values())
    decisions = enriched[enriched["tod"] >= DECISION_START].copy()
    decisions = decisions.set_index(["date", "tod"], drop=False)

    long_valid_parts: list[np.ndarray] = []
    short_valid_parts: list[np.ndarray] = []
    long_score_parts: list[np.ndarray] = []
    short_score_parts: list[np.ndarray] = []
    for minutes, weight in zip(horizons_minutes, weights):
        z_col = f"normalized_{minutes}m"
        decisions[f"rank_{minutes}m"] = np.nan
        decisions[f"positive_count_{minutes}m"] = 0
        decisions[f"negative_count_{minutes}m"] = 0
        decisions[f"history_count_{minutes}m"] = 0
        for tod in sorted(decisions["tod"].unique()):
            aligned = (
                enriched[enriched["tod"] == tod]
                .set_index("date")[z_col]
                .reindex(dates)
            )
            result = causal_sign_split_rank(aligned.to_numpy(), window, minimum_fraction)
            keys = pd.MultiIndex.from_arrays(
                [dates, np.full(len(dates), int(tod))], names=["date", "tod"]
            )
            present = keys.isin(decisions.index)
            present_keys = keys[present]
            decisions.loc[present_keys, f"rank_{minutes}m"] = result["rank"][present]
            decisions.loc[present_keys, f"positive_count_{minutes}m"] = result[
                "positive_count"
            ][present]
            decisions.loc[present_keys, f"negative_count_{minutes}m"] = result[
                "negative_count"
            ][present]
            decisions.loc[present_keys, f"history_count_{minutes}m"] = result[
                "history_count"
            ][present]

        values = decisions[z_col].to_numpy(float)
        ranks = decisions[f"rank_{minutes}m"].to_numpy(float)
        required = int(np.ceil(window * minimum_fraction))
        positive_ok = (
            decisions[f"history_count_{minutes}m"].to_numpy() == window
        ) & (decisions[f"positive_count_{minutes}m"].to_numpy() >= required)
        negative_ok = (
            decisions[f"history_count_{minutes}m"].to_numpy() == window
        ) & (decisions[f"negative_count_{minutes}m"].to_numpy() >= required)
        long_valid_parts.append(positive_ok)
        short_valid_parts.append(negative_ok)
        long_score_parts.append(weight * np.where(values > 0.0, ranks, 0.0))
        short_score_parts.append(weight * np.where(values < 0.0, ranks, 0.0))

    long_eligible = np.logical_and.reduce(long_valid_parts)
    short_eligible = np.logical_and.reduce(short_valid_parts)
    long_score = np.nansum(np.column_stack(long_score_parts), axis=1)
    short_score = np.nansum(np.column_stack(short_score_parts), axis=1)
    long_score[~long_eligible] = np.nan
    short_score[~short_eligible] = np.nan
    decisions["long_eligible"] = long_eligible
    decisions["short_eligible"] = short_eligible
    decisions["score_long"] = long_score
    decisions["score_short"] = short_score
    decisions["rank_window"] = int(window)
    decisions["required_sign_count"] = int(np.ceil(window * minimum_fraction))
    decisions["alpha"] = float(alpha)
    return decisions.reset_index(drop=True)
