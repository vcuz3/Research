"""Run the frozen opening-gap agreement strategy and required economic controls."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest_engine.engine import CostProfile, run_fixed_schedule
from ..backtest_engine.metrics import summarize
from ..strategy.signals import (
    discovery_family_signals,
    fit_rate_matched_thresholds,
    opening_signals,
)
from .common import (
    MAIN_CONFIG,
    common_session_feature_frames,
    cost_profile,
    date_mask,
    fit_discovery_family,
    independent_session_feature_frames,
    load_json,
    write_json,
)


def _period_masks(frame: pd.DataFrame, config: dict[str, object]) -> dict[str, pd.Series]:
    dates = pd.to_datetime(frame["date"])
    return {
        "discovery_2011_2018": dates.between(config["discovery_start"], config["discovery_end"]),
        "validation_2019_2022": dates.between(config["validation_start"], config["validation_end"]),
        "validation_b_2023_2026": dates.between(config["validation_b_start"], config["validation_b_end"]),
        "historical_validation_2019_2026": dates.between(config["validation_start"], config["validation_b_end"]),
        "full_2011_2026": pd.Series(True, index=frame.index),
    }


def _run(
    frame: pd.DataFrame,
    side: pd.Series | np.ndarray,
    config: dict[str, object],
    *,
    instrument: str,
    name: str,
    entry_column: str | None = None,
    exit_column: str | None = None,
    entry_time: str | None = None,
    exit_time: str | None = None,
    costs: CostProfile | None = None,
    allow_zero_latency: bool = False,
) -> pd.DataFrame:
    return run_fixed_schedule(
        frame,
        side,
        instrument=instrument,
        entry_column=entry_column or str(config["entry_column"]),
        exit_column=exit_column or str(config["exit_column"]),
        costs=costs or cost_profile(config),
        decision_time_et=str(config["signal_available_time_et"]),
        entry_time_et=entry_time or str(config["entry_order_active_time_et"]),
        exit_time_et=exit_time or str(config["scheduled_exit_order_active_time_et"]),
        strategy_name=name,
        allow_zero_latency=allow_zero_latency,
    )


def _summary_row(
    trades: pd.DataFrame,
    mask: pd.Series | np.ndarray,
    *,
    instrument: str,
    strategy: str,
    cost_label: str,
    period: str,
    hac_lags: int,
) -> dict[str, object]:
    subset = trades.loc[np.asarray(mask)].reset_index(drop=True)
    stats = summarize(subset, hac_lags=hac_lags)
    trade_rows = subset.loc[subset["trade"]]
    total_cost = float((trade_rows["slippage_dollars"] + trade_rows["fees_dollars"]).sum())
    gross_total = float(trade_rows["gross_dollars"].sum())
    return {
        "instrument": instrument,
        "strategy": strategy,
        "cost_profile": cost_label,
        "period": period,
        **stats,
        "gross_mean_trade_points": float(trade_rows["gross_points"].mean()) if len(trade_rows) else None,
        "gross_mean_trade_ticks": float(trade_rows["gross_points"].mean() / 0.25) if len(trade_rows) else None,
        "gross_to_cost_ratio": float(gross_total / total_cost) if total_cost > 0 else None,
    }


def _exact_count_signal(
    frame: pd.DataFrame,
    score_column: str,
    target_mask: pd.Series,
    target_count: int,
) -> pd.Series:
    signal = pd.Series(0, index=frame.index, dtype="int8")
    eligible = pd.DataFrame(
        {
            "index": frame.index[target_mask],
            "date": pd.to_datetime(frame.loc[target_mask, "date"]).to_numpy(),
            "score": pd.to_numeric(frame.loc[target_mask, score_column], errors="coerce").to_numpy(),
        }
    ).dropna(subset=["score"])
    chosen = eligible.sort_values(["score", "date"], ascending=[False, True]).head(target_count)["index"]
    signal.loc[chosen] = frame.loc[chosen, "opening_sign"].astype("int8")
    if int(signal.loc[target_mask].ne(0).sum()) != target_count:
        raise AssertionError("diagnostic matched-count control could not match trade count")
    return signal


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(MAIN_CONFIG)
    sessions, features = independent_session_feature_frames(config)
    nq_sessions, es_sessions = sessions["NQ"], sessions["ES"]
    nq, es = features["NQ"], features["ES"]
    nq_base, es_base = opening_signals(nq), opening_signals(es)
    masks = _period_masks(nq, config)
    es_masks = _period_masks(es, config)
    discovery = masks["discovery_2011_2018"]
    thresholds = fit_rate_matched_thresholds(
        nq.loc[discovery].reset_index(drop=True),
        nq_base.loc[discovery, "confirmed_gap"].reset_index(drop=True),
    )
    family = discovery_family_signals(nq, thresholds)
    hac_lags = int(config["hac_lags"])

    nq_signals: dict[str, pd.Series] = {
        "confirmed_gap": nq_base["confirmed_gap"],
        "opening_ungated": nq_base["opening_ungated"],
        "total_r1_direction": nq["paper_r1_sign"].astype("int8"),
        "overnight_only": nq_base["overnight_only"],
        "mirror_gap_opposition": nq_base["mirror_gap_opposition"],
        "selected_day_always_long": nq_base["selected_day_always_long"],
        "opening_magnitude_deployable": family["opening_magnitude_gate"],
        "total_r1_magnitude_deployable": family["total_r1_magnitude_gate"],
        "min_component_deployable": family["min_component_gate"],
        "confirmed_gap_long_only": nq_base["confirmed_gap"].where(nq_base["confirmed_gap"].gt(0), 0),
        "confirmed_gap_short_only": nq_base["confirmed_gap"].where(nq_base["confirmed_gap"].lt(0), 0),
    }

    # Nondeployable, exact-count validation-era diagnostics.
    matched_columns = {
        "opening_magnitude": "magnitude_rel",
        "total_r1_magnitude": "total_r1_magnitude_rel",
        "min_component": "min_component_rel",
    }
    for label, column in matched_columns.items():
        combined = pd.Series(0, index=nq.index, dtype="int8")
        for era in ("validation_2019_2022", "validation_b_2023_2026"):
            target_count = int(nq_base.loc[masks[era], "confirmed_gap"].ne(0).sum())
            era_signal = _exact_count_signal(nq, column, masks[era], target_count)
            combined.loc[masks[era]] = era_signal.loc[masks[era]]
        nq_signals[f"{label}_exact_count_diagnostic"] = combined

    summary_rows: list[dict[str, object]] = []
    control_daily: list[pd.DataFrame] = []
    primary_daily: dict[str, pd.DataFrame] = {}

    # Primary-cost controls.
    for name, side in nq_signals.items():
        trades = _run(nq_sessions, side, config, instrument="NQ", name=name)
        if name == "confirmed_gap":
            primary_daily["NQ"] = trades
        control_daily.append(trades)
        for period, mask in masks.items():
            summary_rows.append(
                _summary_row(
                    trades,
                    mask,
                    instrument="NQ",
                    strategy=name,
                    cost_label="1_tick_per_side",
                    period=period,
                    hac_lags=hac_lags,
                )
            )

    # ES sibling: identical parameter-free rule and opposition control.
    for name in ("confirmed_gap", "mirror_gap_opposition"):
        trades = _run(es_sessions, es_base[name], config, instrument="ES", name=name)
        if name == "confirmed_gap":
            primary_daily["ES"] = trades
        control_daily.append(trades)
        for period, mask in es_masks.items():
            summary_rows.append(
                _summary_row(
                    trades,
                    mask,
                    instrument="ES",
                    strategy=name,
                    cost_label="1_tick_per_side",
                    period=period,
                    hac_lags=hac_lags,
                )
            )

    # Cost ladder, including a truly gross arm with neither fees nor slippage.
    cost_ladder = {"gross": CostProfile(0.0, 0.0)}
    for ticks in config["cost_stress_ticks_per_side"]:
        cost_ladder[f"{float(ticks):g}_ticks_per_side"] = cost_profile(config, float(ticks))
    for label, costs in cost_ladder.items():
        trades = _run(nq_sessions, nq_base["confirmed_gap"], config, instrument="NQ", name="confirmed_gap", costs=costs)
        summary_rows.append(
            _summary_row(
                trades,
                masks["historical_validation_2019_2026"],
                instrument="NQ",
                strategy="confirmed_gap",
                cost_label=label,
                period="historical_validation_2019_2026",
                hac_lags=hac_lags,
            )
        )

    # One-second entry/exit activation sweep.
    entry_sweep = config["entry_sensitivities"]
    for clock, column in entry_sweep.items():
        trades = _run(
            nq_sessions,
            nq_base["confirmed_gap"],
            config,
            instrument="NQ",
            name=f"confirmed_gap_entry_{clock}",
            entry_column=column,
            entry_time=clock,
            allow_zero_latency=clock == "10:00:00",
        )
        summary_rows.append(
            _summary_row(
                trades,
                masks["historical_validation_2019_2026"],
                instrument="NQ",
                strategy=f"confirmed_gap_entry_{clock}",
                cost_label="1_tick_per_side",
                period="historical_validation_2019_2026",
                hac_lags=hac_lags,
            )
        )
    for clock, column in config["exit_sensitivities"].items():
        trades = _run(
            nq_sessions,
            nq_base["confirmed_gap"],
            config,
            instrument="NQ",
            name=f"confirmed_gap_exit_{clock}",
            exit_column=column,
            exit_time=clock,
        )
        summary_rows.append(
            _summary_row(
                trades,
                masks["historical_validation_2019_2026"],
                instrument="NQ",
                strategy=f"confirmed_gap_exit_{clock}",
                cost_label="1_tick_per_side",
                period="historical_validation_2019_2026",
                hac_lags=hac_lags,
            )
        )

    # Cohort sensitivities cannot replace the independently eligible primary NQ panel.
    strict_sessions, strict_features = independent_session_feature_frames(
        config, strict_full_session=True
    )
    strict_signal = opening_signals(strict_features["NQ"])["confirmed_gap"]
    strict_masks = _period_masks(strict_features["NQ"], config)
    strict_trades = _run(
        strict_sessions["NQ"], strict_signal, config, instrument="NQ", name="confirmed_gap_strict_390"
    )
    summary_rows.append(
        _summary_row(
            strict_trades,
            strict_masks["historical_validation_2019_2026"],
            instrument="NQ",
            strategy="confirmed_gap_strict_390",
            cost_label="1_tick_per_side",
            period="historical_validation_2019_2026",
            hac_lags=hac_lags,
        )
    )
    common_sessions, common_features = common_session_feature_frames(config)
    common_signal = opening_signals(common_features["NQ"])["confirmed_gap"]
    common_masks = _period_masks(common_features["NQ"], config)
    common_trades = _run(
        common_sessions["NQ"], common_signal, config, instrument="NQ", name="confirmed_gap_common_panel"
    )
    summary_rows.append(
        _summary_row(
            common_trades,
            common_masks["historical_validation_2019_2026"],
            instrument="NQ",
            strategy="confirmed_gap_common_panel",
            cost_label="1_tick_per_side",
            period="historical_validation_2019_2026",
            hac_lags=hac_lags,
        )
    )
    common_es_signals = opening_signals(common_features["ES"])
    for name in ("confirmed_gap", "mirror_gap_opposition"):
        strategy_name = f"{name}_common_panel"
        trades = _run(
            common_sessions["ES"],
            common_es_signals[name],
            config,
            instrument="ES",
            name=strategy_name,
        )
        control_daily.append(trades)
        summary_rows.append(
            _summary_row(
                trades,
                common_masks["historical_validation_2019_2026"],
                instrument="ES",
                strategy=strategy_name,
                cost_label="1_tick_per_side",
                period="historical_validation_2019_2026",
                hac_lags=hac_lags,
            )
        )

    summary_table = pd.DataFrame(summary_rows)
    summary_table.to_csv(args.output_dir / "experiment_summary.csv", index=False)
    pd.concat(control_daily, ignore_index=True).to_csv(
        args.output_dir / "control_daily.csv.gz", index=False, compression="gzip"
    )
    for instrument, trades in primary_daily.items():
        trades.to_csv(args.output_dir / f"primary_{instrument.lower()}_daily.csv.gz", index=False, compression="gzip")

    # Primary year table uses every eligible day, including zeros.
    year_rows = []
    for instrument, trades in primary_daily.items():
        years = pd.to_datetime(trades["date"]).dt.year
        for year, subset in trades.groupby(years):
            year_rows.append({"instrument": instrument, "year": int(year), **summarize(subset.reset_index(drop=True))})
    pd.DataFrame(year_rows).to_csv(args.output_dir / "year_summary.csv", index=False)

    def row(strategy: str, cost_label: str = "1_tick_per_side", instrument: str = "NQ", period: str = "historical_validation_2019_2026") -> dict[str, object]:
        selected = summary_table.loc[
            summary_table["instrument"].eq(instrument)
            & summary_table["strategy"].eq(strategy)
            & summary_table["cost_profile"].eq(cost_label)
            & summary_table["period"].eq(period)
        ]
        if len(selected) != 1:
            raise AssertionError(f"summary lookup not unique: {instrument} {strategy} {cost_label} {period}")
        return selected.iloc[0].to_dict()

    primary = row("confirmed_gap")
    era_a = row("confirmed_gap", period="validation_2019_2022")
    era_b = row("confirmed_gap", period="validation_b_2023_2026")
    two_ticks = row("confirmed_gap", cost_label="2_ticks_per_side")
    delayed = row("confirmed_gap_entry_10:01:00")
    long_only = row("confirmed_gap_long_only")
    short_only = row("confirmed_gap_short_only")
    es_primary = row("confirmed_gap", instrument="ES")
    es_opp = row("mirror_gap_opposition", instrument="ES")
    preliminary_gates = {
        "net_sharpe_at_least_0_50": float(primary["daily_sharpe_net"]) >= 0.50,
        "era_a_net_mean_positive": float(era_a["net_mean_daily_dollars"]) > 0,
        "era_b_net_mean_positive": float(era_b["net_mean_daily_dollars"]) > 0,
        "two_tick_net_mean_positive": float(two_ticks["net_mean_daily_dollars"]) > 0,
        "ten_oh_one_net_mean_positive": float(delayed["net_mean_daily_dollars"]) > 0,
        "nq_long_gross_mean_positive": float(long_only["gross_mean_daily_dollars"]) > 0,
        "nq_short_gross_mean_positive": float(short_only["gross_mean_daily_dollars"]) > 0,
        "es_gross_mean_positive": float(es_primary["gross_mean_daily_dollars"]) > 0,
        "es_agreement_minus_opposition_positive": float(es_primary["gross_mean_daily_dollars"]) > float(es_opp["gross_mean_daily_dollars"]),
    }
    write_json(
        args.output_dir / "experiment_result.json",
        {
            "strategy": "opening-gap agreement continuation",
            "primary_instrument": "NQ",
            "historical_status": "globally consumed; future-only confirmation required",
            "thresholds": thresholds.as_dict(),
            "primary_summary_2019_2026": primary,
            "preliminary_economic_gates": preliminary_gates,
            "preliminary_pass": all(preliminary_gates.values()),
            "final_status": "PENDING_SELECTIVE_NULL_AND_BOOTSTRAP_VALIDATION",
        },
    )
    write_json(args.output_dir / "frozen_thresholds.json", thresholds.as_dict())


if __name__ == "__main__":
    main()
