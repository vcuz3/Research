"""Small fixed-horizon event engine for the triangular-pricing workbench."""

from __future__ import annotations

import numpy as np
import pandas as pd


def build_event_returns(
    panel: pd.DataFrame,
    features: pd.DataFrame,
    horizon_bars: int,
    timeframe_minutes: int,
    entry_delay_bars: int = 1,
    round_trip_cost_bps_per_leg: float = 0.0,
    non_overlapping: bool = True,
) -> pd.DataFrame:
    """Enter at a later bar open and exit after ``horizon_bars`` completed bars.

    The three-leg residual is long AUDUSD, short AUDJPY, long USDJPY. Costs are
    an explicit sensitivity in basis points per round trip per leg; they are not
    measured from these midpoint archives.
    """
    if horizon_bars < 1 or entry_delay_bars < 1:
        raise ValueError("horizon_bars and entry_delay_bars must be positive")
    if round_trip_cost_bps_per_leg < 0:
        raise ValueError("cost cannot be negative")
    if not panel.index.equals(features.index):
        raise ValueError("panel and features indexes must match")

    index = panel.index
    signal_positions = np.flatnonzero(features["direction"].to_numpy() != 0)
    records: list[dict[str, object]] = []
    last_exit = -1
    expected_step = pd.Timedelta(minutes=timeframe_minutes)

    for decision_pos in signal_positions:
        entry_pos = decision_pos + entry_delay_bars
        exit_pos = entry_pos + horizon_bars - 1
        if exit_pos >= len(panel):
            continue
        if non_overlapping and decision_pos <= last_exit:
            continue
        if index[entry_pos] - index[decision_pos] != entry_delay_bars * expected_step:
            continue
        if index[exit_pos] - index[entry_pos] != (horizon_bars - 1) * expected_step:
            continue

        side = int(features["direction"].iat[decision_pos])
        leg_returns: dict[str, float] = {}
        for pair in ("audusd", "audjpy", "usdjpy"):
            entry = float(panel[f"{pair}_open"].iat[entry_pos])
            exit_ = float(panel[f"{pair}_close"].iat[exit_pos])
            leg_returns[pair] = float(np.log(exit_ / entry))
        audusd_gross = side * leg_returns["audusd"]
        residual_gross = side * (leg_returns["audusd"] - leg_returns["audjpy"] + leg_returns["usdjpy"])
        one_leg_cost = round_trip_cost_bps_per_leg * 1e-4
        records.append(
            {
                "decision_ts": index[decision_pos],
                "entry_ts": index[entry_pos] - expected_step,
                "exit_ts": index[exit_pos],
                "side": side,
                "entry_z": float(features["zscore"].iat[decision_pos]),
                "horizon_bars": horizon_bars,
                "entry_delay_bars": entry_delay_bars,
                "audusd_gross": audusd_gross,
                "audusd_net": audusd_gross - one_leg_cost,
                "residual_gross": residual_gross,
                "residual_net": residual_gross - 3 * one_leg_cost,
            }
        )
        if non_overlapping:
            last_exit = exit_pos
    return pd.DataFrame.from_records(records)


def cluster_t_mean(values: pd.Series, clusters: pd.Series) -> float:
    valid = values.notna() & clusters.notna()
    x = values.loc[valid].astype(float)
    group = clusters.loc[valid]
    n = len(x)
    g = group.nunique()
    if n < 2 or g < 2:
        return float("nan")
    centered = x - x.mean()
    cluster_sums = centered.groupby(group).sum()
    variance = (g / (g - 1)) * np.square(cluster_sums).sum() / (n * n)
    return float(x.mean() / np.sqrt(variance)) if variance > 0 else float("nan")


def summarize_events(events: pd.DataFrame) -> pd.DataFrame:
    rows: list[dict[str, object]] = []
    if events.empty:
        return pd.DataFrame()
    day = pd.to_datetime(events["decision_ts"]).dt.floor("D")
    for column in ("audusd_gross", "audusd_net", "residual_gross", "residual_net"):
        values = events[column]
        daily = values.groupby(day).sum()
        daily_sharpe = np.sqrt(252) * daily.mean() / daily.std(ddof=1) if daily.std(ddof=1) > 0 else np.nan
        rows.append(
            {
                "model": column,
                "trades": len(values),
                "mean_bps": values.mean() * 10_000,
                "median_bps": values.median() * 10_000,
                "hit_rate": values.gt(0).mean(),
                "day_cluster_t": cluster_t_mean(values, day),
                "daily_sharpe": daily_sharpe,
            }
        )
    return pd.DataFrame(rows)
