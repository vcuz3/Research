"""Causal direct and hysteresis state rules for HYP-0001."""
from __future__ import annotations

import numpy as np
import pandas as pd

from .features import causal_sign_split_rank


def direct_state(scores: pd.DataFrame, threshold: float) -> pd.DataFrame:
    out = scores[["date", "tod"]].copy()
    long = scores["score_long"].ge(threshold)
    short = scores["score_short"].ge(threshold)
    desired = np.where(long & ~short, 1, np.where(short & ~long, -1, 0))
    both = long & short
    desired = np.where(
        both,
        np.where(scores["score_long"].fillna(-np.inf) >= scores["score_short"].fillna(-np.inf), 1, -1),
        desired,
    )
    out["desired"] = desired.astype(int)
    return out


def hysteresis_state(scores: pd.DataFrame, entry: float, exit: float) -> pd.DataFrame:
    if exit >= entry:
        raise ValueError("hysteresis exit must be below entry")
    ordered = scores.sort_values(["date", "tod"])
    states = np.zeros(len(ordered), dtype=np.int8)
    cursor = 0
    for _, group in ordered.groupby("date", sort=False):
        position = 0
        for row in group.itertuples(index=False):
            long_score = getattr(row, "score_long")
            short_score = getattr(row, "score_short")
            long_entry = np.isfinite(long_score) and long_score >= entry
            short_entry = np.isfinite(short_score) and short_score >= entry
            if position == 0:
                if long_entry or short_entry:
                    position = 1 if long_entry and (not short_entry or long_score >= short_score) else -1
            elif position == 1:
                if short_entry:
                    position = -1
                elif not np.isfinite(long_score) or long_score < exit:
                    position = 0
            else:
                if long_entry:
                    position = 1
                elif not np.isfinite(short_score) or short_score < exit:
                    position = 0
            states[cursor] = position
            cursor += 1
    out = ordered[["date", "tod"]].copy()
    out["desired"] = states
    return out


def rank_model_readout(
    predictions: pd.DataFrame, window: int, minimum_fraction: float
) -> pd.DataFrame:
    """Same-slot, same-sign causal rank of a model's signed return readout."""
    ordered = predictions.sort_values(["date", "tod"]).copy()
    dates = pd.Index(ordered["date"].drop_duplicates().sort_values())
    rank = pd.Series(np.nan, index=ordered.index, dtype=float)
    for tod, group in ordered.groupby("tod", sort=False):
        aligned = group.set_index("date")["readout"].reindex(dates)
        got = causal_sign_split_rank(aligned.to_numpy(), window, minimum_fraction)
        mapping = pd.Series(got["rank"], index=dates)
        rank.loc[group.index] = group["date"].map(mapping).to_numpy()
    ordered["score_long"] = np.where(ordered["readout"] > 0, rank, 0.0)
    ordered["score_short"] = np.where(ordered["readout"] < 0, rank, 0.0)
    ordered.loc[rank.isna(), ["score_long", "score_short"]] = np.nan
    return ordered
