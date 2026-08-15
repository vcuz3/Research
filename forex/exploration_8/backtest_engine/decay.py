"""Paired minute-delay measurement for a frozen triangular signal set."""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np
import pandas as pd

from .engine import cluster_t_mean


def paired_minute_decay(
    minute_panel: pd.DataFrame,
    signals: pd.DataFrame,
    delays_minutes: Iterable[int],
    holding_minutes: int,
    round_trip_cost_bps_per_leg: float,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Measure fixed-horizon returns after several delays on identical signals.

    A signal timestamp is the close of its decision bar. Delay zero enters at the
    open of the one-minute bar beginning at that timestamp. Every arm holds for
    exactly ``holding_minutes`` one-minute bars and exits at the last bar's close.
    The returned sample is the intersection of valid signal timestamps across all
    delays, making every comparison paired.
    """
    delays = tuple(sorted(set(int(value) for value in delays_minutes)))
    if not delays or delays[0] < 0:
        raise ValueError("delays must be nonempty nonnegative minute counts")
    if holding_minutes < 1 or round_trip_cost_bps_per_leg < 0:
        raise ValueError("holding_minutes must be positive and cost nonnegative")
    required = {
        "audusd_open", "audusd_close", "audjpy_open", "audjpy_close",
        "usdjpy_open", "usdjpy_close",
    }
    if not required.issubset(minute_panel.columns):
        raise ValueError(f"minute_panel missing {sorted(required - set(minute_panel.columns))}")
    if not minute_panel.index.is_unique or not minute_panel.index.is_monotonic_increasing:
        raise ValueError("minute_panel index must be unique and increasing")
    if not {"decision_ts", "direction", "zscore"}.issubset(signals.columns):
        raise ValueError("signals require decision_ts, direction, and zscore")

    index = minute_panel.index
    one_minute = pd.Timedelta(minutes=1)
    arm_records: dict[int, list[dict[str, object]]] = {}
    coverage_rows: list[dict[str, object]] = []

    for delay in delays:
        records: list[dict[str, object]] = []
        missing_entry = missing_exit = noncontiguous = 0
        for signal in signals.itertuples(index=False):
            decision_ts = pd.Timestamp(signal.decision_ts)
            entry_ts = decision_ts + pd.Timedelta(minutes=delay)
            exit_minute_ts = entry_ts + pd.Timedelta(minutes=holding_minutes - 1)
            entry_pos = int(index.searchsorted(entry_ts))
            if entry_pos >= len(index) or index[entry_pos] != entry_ts:
                missing_entry += 1
                continue
            exit_pos = entry_pos + holding_minutes - 1
            if exit_pos >= len(index):
                missing_exit += 1
                continue
            if index[exit_pos] != exit_minute_ts:
                noncontiguous += 1
                continue
            entry = minute_panel.iloc[entry_pos]
            exit_ = minute_panel.iloc[exit_pos]
            leg_returns = {
                pair: float(np.log(float(exit_[f"{pair}_close"]) / float(entry[f"{pair}_open"])))
                for pair in ("audusd", "audjpy", "usdjpy")
            }
            side = int(signal.direction)
            audusd_gross = side * leg_returns["audusd"]
            residual_gross = side * (leg_returns["audusd"] - leg_returns["audjpy"] + leg_returns["usdjpy"])
            cost = round_trip_cost_bps_per_leg * 1e-4
            records.append(
                {
                    "decision_ts": decision_ts,
                    "delay_minutes": delay,
                    "entry_ts": entry_ts,
                    "exit_ts": exit_minute_ts + one_minute,
                    "direction": side,
                    "signal_z": float(signal.zscore),
                    "audusd_gross": audusd_gross,
                    "audusd_net": audusd_gross - cost,
                    "residual_gross": residual_gross,
                    "residual_net": residual_gross - 3 * cost,
                }
            )
        arm_records[delay] = records
        coverage_rows.append(
            {
                "delay_minutes": delay,
                "candidate_signals": len(signals),
                "valid_before_pairing": len(records),
                "missing_entry": missing_entry,
                "missing_exit": missing_exit,
                "noncontiguous_window": noncontiguous,
            }
        )

    valid_sets = [{record["decision_ts"] for record in records} for records in arm_records.values()]
    common = set.intersection(*valid_sets) if valid_sets else set()
    paired_records = [record for delay in delays for record in arm_records[delay] if record["decision_ts"] in common]
    event_columns = [
        "decision_ts", "delay_minutes", "entry_ts", "exit_ts", "direction", "signal_z",
        "audusd_gross", "audusd_net", "residual_gross", "residual_net",
    ]
    events = pd.DataFrame.from_records(paired_records, columns=event_columns)
    if not events.empty:
        events = events.sort_values(["delay_minutes", "decision_ts"]).reset_index(drop=True)
    coverage = pd.DataFrame(coverage_rows)
    coverage["paired_signals"] = len(common)
    if not events.empty and not events.groupby("delay_minutes").size().eq(len(common)).all():
        raise AssertionError("Decay arms are not paired")
    return events, coverage


def summarize_decay(events: pd.DataFrame, observed_days: pd.DatetimeIndex) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Return arm metrics and paired deterioration relative to delay zero."""
    rows: list[dict[str, object]] = []
    for delay, arm in events.groupby("delay_minutes", observed=True):
        day = pd.to_datetime(arm["decision_ts"]).dt.floor("D")
        for model in ("audusd", "residual"):
            for accounting in ("gross", "net"):
                column = f"{model}_{accounting}"
                values = arm[column]
                daily = values.groupby(day).sum().reindex(observed_days, fill_value=0.0)
                rows.append(
                    {
                        "delay_minutes": int(delay),
                        "model": model,
                        "accounting": accounting,
                        "signals": len(values),
                        "mean_bps": values.mean() * 10_000,
                        "median_bps": values.median() * 10_000,
                        "hit_rate": values.gt(0).mean(),
                        "day_cluster_t": cluster_t_mean(values, day),
                        "all_observed_day_sharpe": (
                            np.sqrt(252) * daily.mean() / daily.std(ddof=1) if daily.std(ddof=1) > 0 else np.nan
                        ),
                    }
                )
    summary = pd.DataFrame(rows)

    pivot = events.pivot(index="decision_ts", columns="delay_minutes", values=["audusd_gross", "residual_gross"])
    zero = pivot.xs(0, axis=1, level="delay_minutes")
    decay_rows: list[dict[str, object]] = []
    clusters = pd.Series(pivot.index.floor("D"), index=pivot.index)
    for delay in sorted(events["delay_minutes"].unique()):
        arm = pivot.xs(delay, axis=1, level="delay_minutes")
        for model in ("audusd", "residual"):
            column = f"{model}_gross"
            difference = arm[column] - zero[column]
            decay_rows.append(
                {
                    "delay_minutes": int(delay),
                    "model": model,
                    "mean_change_vs_0_bps": difference.mean() * 10_000,
                    "paired_day_cluster_t": cluster_t_mean(difference, clusters),
                }
            )
    return summary, pd.DataFrame(decay_rows)
