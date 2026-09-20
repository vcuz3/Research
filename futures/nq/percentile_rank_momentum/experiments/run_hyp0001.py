"""Run the HYP-0001 B0-B4 ladder after the Rule-9a gate passes."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest_engine.adapter import always_long_rth, run_desired_positions
from ..backtest_engine.metrics import cost_points_per_side, summarize
from ..strategy.features import build_same_slot_features, load_canonical_rth_5m
from ..strategy.model import (
    add_forward_target,
    prepare_model_frame,
    walk_forward_predictions,
)
from ..strategy.signal import direct_state, hysteresis_state, rank_model_readout


PROJECT = Path(__file__).resolve().parents[1]
WORKSPACE = PROJECT.parents[2]
DEFAULT_CONFIG = PROJECT / "experiments" / "configs" / "hyp_0001.json"


def era_name(date: pd.Timestamp) -> str:
    year = date.year
    if year <= 2014:
        return "2011-2014"
    if year <= 2019:
        return "2015-2019"
    if year <= 2022:
        return "2020-2022"
    return "2023+"


def run_arm(
    bars: pd.DataFrame,
    desired: pd.DataFrame,
    instrument: str,
    label: str,
    cost_side: float,
    eligible_dates: pd.Index,
) -> tuple[pd.DataFrame, dict]:
    trades = run_desired_positions(bars, desired)
    score = summarize(trades, bars, instrument, label, cost_side, eligible_dates)
    return trades, score


def score_eras(
    trades: pd.DataFrame,
    bars: pd.DataFrame,
    instrument: str,
    arm: str,
    cost_side: float,
    dates: pd.Index,
) -> list[dict]:
    output = []
    date_frame = pd.DataFrame({"date": dates})
    date_frame["era"] = date_frame["date"].map(era_name)
    for era, group in date_frame.groupby("era", sort=False):
        era_dates = pd.Index(group["date"])
        era_bars = bars[bars["date"].isin(era_dates)]
        era_trades = trades[trades["date"].isin(era_dates)]
        if era_trades.empty:
            continue
        row = summarize(era_trades, era_bars, instrument, arm, cost_side, era_dates)
        row["era"] = era
        output.append(row)
    return output


def instrument_ladder(
    instrument: str,
    config: dict,
    artifact: Path,
    save_prefix: str,
) -> dict:
    horizons = tuple(config["momentum_horizons_minutes"])
    weights = tuple(config["horizon_weights"])
    window = int(config["primary_rank_window_sessions"])
    alpha = float(config["primary_vol_blend_alpha"])
    floor = float(config["same_sign_coverage_fraction"])
    qe, qx = float(config["entry_threshold"]), float(config["exit_threshold"])
    bars, audit = load_canonical_rth_5m(
        instrument, config["minimum_1m_bars_per_session"]
    )
    features = build_same_slot_features(bars, window, floor, alpha, horizons, weights)
    cost_side = cost_points_per_side(
        instrument,
        config["costs"]["slippage_ticks_per_side"],
        config["costs"]["fee_usd_per_side"],
    )
    all_dates = pd.Index(bars["date"].drop_duplicates().sort_values())

    b0_full = always_long_rth(bars)
    b0_full_score = summarize(b0_full, bars, instrument, f"{instrument}_B0_full", cost_side, all_dates)
    b1_full, b1_full_score = run_arm(
        bars, direct_state(features, qe), instrument, f"{instrument}_B1_full_q{qe:.2f}", cost_side, all_dates
    )
    b2_full, b2_full_score = run_arm(
        bars, hysteresis_state(features, qe, qx), instrument,
        f"{instrument}_B2_full_qe{qe:.2f}_qx{qx:.2f}", cost_side, all_dates
    )

    model_frame = prepare_model_frame(
        add_forward_target(features, bars, int(config["forward_horizon_minutes"])), horizons
    )
    predictions, folds = walk_forward_predictions(
        model_frame,
        horizons,
        bins=int(config["forward_bin_count"]),
        trailing_years=int(config["model"]["trailing_training_years"]),
        minimum_training_rows=int(config["model"]["minimum_training_rows"]),
        regularization_c=float(config["model"]["regularization_c"]),
        random_state=int(config["model"]["random_state"]),
    )
    if predictions.empty:
        raise RuntimeError(f"no walk-forward predictions for {instrument}")
    argmax_scores = rank_model_readout(
        predictions.rename(columns={"argmax_readout": "readout"})[
            ["date", "tod", "forward_points", "fold_year", "readout"]
        ],
        window,
        floor,
    )
    expected_scores = rank_model_readout(
        predictions.rename(columns={"expected_readout": "readout"})[
            ["date", "tod", "forward_points", "fold_year", "readout"]
        ],
        window,
        floor,
    )
    model_valid = expected_scores[["score_long", "score_short"]].notna().any(axis=1)
    common_start = expected_scores.loc[model_valid, "date"].min()
    common_dates = all_dates[all_dates >= common_start]
    common_bars = bars[bars["date"].isin(common_dates)]
    common_features = features[features["date"].isin(common_dates)]
    argmax_scores = argmax_scores[argmax_scores["date"].isin(common_dates)]
    expected_scores = expected_scores[expected_scores["date"].isin(common_dates)]

    b0 = always_long_rth(common_bars)
    b0_score = summarize(b0, common_bars, instrument, f"{instrument}_B0", cost_side, common_dates)
    b1, b1_score = run_arm(
        common_bars, direct_state(common_features, qe), instrument,
        f"{instrument}_B1_q{qe:.2f}", cost_side, common_dates
    )
    b2, b2_score = run_arm(
        common_bars, hysteresis_state(common_features, qe, qx), instrument,
        f"{instrument}_B2_qe{qe:.2f}_qx{qx:.2f}", cost_side, common_dates
    )
    b3, b3_score = run_arm(
        common_bars, hysteresis_state(argmax_scores, qe, qx), instrument,
        f"{instrument}_B3_argmax", cost_side, common_dates
    )
    b4, b4_score = run_arm(
        common_bars, hysteresis_state(expected_scores, qe, qx), instrument,
        f"{instrument}_B4_expected_value", cost_side, common_dates
    )

    threshold_rows = []
    target_count = len(b4)
    threshold_cfg = config["matched_count_threshold_grid"]
    for threshold in np.round(
        np.arange(
            threshold_cfg["start"],
            threshold_cfg["stop_inclusive"] + threshold_cfg["step"] / 2.0,
            threshold_cfg["step"],
        ),
        2,
    ):
        candidate = run_desired_positions(common_bars, direct_state(common_features, float(threshold)))
        threshold_rows.append({
            "threshold": float(threshold),
            "n_trades": int(len(candidate)),
            "absolute_count_gap": int(abs(len(candidate) - target_count)),
        })
    match_table = pd.DataFrame(threshold_rows).sort_values(
        ["absolute_count_gap", "threshold"], ascending=[True, False]
    )
    matched_threshold = float(match_table.iloc[0]["threshold"])
    b1_matched, b1_matched_score = run_arm(
        common_bars,
        direct_state(common_features, matched_threshold),
        instrument,
        f"{instrument}_B1_matched_q{matched_threshold:.2f}",
        cost_side,
        common_dates,
    )

    scores = [
        b0_full_score, b1_full_score, b2_full_score,
        b0_score, b1_score, b2_score, b3_score, b4_score, b1_matched_score,
    ]
    trades_by_arm = {
        "B0": b0,
        "B1": b1,
        "B2": b2,
        "B3": b3,
        "B4": b4,
        "B1_matched": b1_matched,
    }
    for arm, trades in trades_by_arm.items():
        trades.to_parquet(artifact / f"trades_{save_prefix}_{arm}.parquet", index=False)
    pd.DataFrame(scores).to_csv(artifact / f"ladder_{save_prefix}.csv", index=False)
    folds.to_csv(artifact / f"model_folds_{save_prefix}.csv", index=False)
    match_table.to_csv(artifact / f"matched_count_grid_{save_prefix}.csv", index=False)
    predictions.to_parquet(artifact / f"model_predictions_{save_prefix}.parquet", index=False)
    era_rows = []
    for arm, trades in trades_by_arm.items():
        era_rows.extend(score_eras(trades, common_bars, instrument, arm, cost_side, common_dates))
    pd.DataFrame(era_rows).to_csv(artifact / f"era_metrics_{save_prefix}.csv", index=False)
    return {
        "instrument": instrument,
        "data_audit": audit,
        "common_start": str(common_start.date()),
        "common_sessions": int(len(common_dates)),
        "matched_threshold": matched_threshold,
        "matched_count_gap": int(abs(len(b1_matched) - len(b4))),
        "scores": {row["label"]: row for row in scores},
        "headline": {
            "B1_matched": b1_matched_score,
            "B4": b4_score,
            "B4_minus_B1_matched_net_ticks": float(
                b4_score["net_ticks_per_trade"] - b1_matched_score["net_ticks_per_trade"]
            ),
            "gross_gate_pass": bool(b4_score["gross_ticks_per_trade"] > 0),
            "ml_value_gate_pass": bool(
                b4_score["net_ticks_per_trade"] > b1_matched_score["net_ticks_per_trade"]
            ),
        },
    }


def stability_surface(config: dict, artifact: Path) -> pd.DataFrame:
    bars, _ = load_canonical_rth_5m("NQ", config["minimum_1m_bars_per_session"])
    dates = pd.Index(bars["date"].drop_duplicates().sort_values())
    cost_side = cost_points_per_side(
        "NQ",
        config["costs"]["slippage_ticks_per_side"],
        config["costs"]["fee_usd_per_side"],
    )
    rows = []
    for alpha in config["vol_blend_alphas"]:
        for window in config["rank_windows_sessions"]:
            features = build_same_slot_features(
                bars,
                int(window),
                float(config["same_sign_coverage_fraction"]),
                float(alpha),
                tuple(config["momentum_horizons_minutes"]),
                tuple(config["horizon_weights"]),
            )
            for arm, desired in (
                ("B1", direct_state(features, config["entry_threshold"])),
                ("B2", hysteresis_state(features, config["entry_threshold"], config["exit_threshold"])),
            ):
                trades, score = run_arm(
                    bars, desired, "NQ", arm, cost_side, dates
                )
                rows.append({
                    "alpha": float(alpha),
                    "window": int(window),
                    "arm": arm,
                    "eligible_decisions": int(
                        (features["long_eligible"] | features["short_eligible"]).sum()
                    ),
                    "n_trades": int(len(trades)),
                    "gross_ticks_per_trade": score["gross_ticks_per_trade"],
                    "net_ticks_per_trade": score["net_ticks_per_trade"],
                    "zero_day_sharpe": score["zero_day_sharpe"],
                    "net_ticks_cluster_t": score["net_ticks_cluster_t"],
                })
    surface = pd.DataFrame(rows)
    surface.to_csv(artifact / "stability_surface_nq.csv", index=False)
    return surface


def sanitize(value):
    if isinstance(value, dict):
        return {key: sanitize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [sanitize(item) for item in value]
    if isinstance(value, (np.floating, float)) and not np.isfinite(value):
        return None
    if isinstance(value, (np.integer,)):
        return int(value)
    return value


def run(config_path: Path, experiment_id: str) -> dict:
    config = json.loads(config_path.read_text(encoding="utf-8"))
    artifact = PROJECT / "artifacts" / "runs" / experiment_id
    if not artifact.exists():
        raise FileNotFoundError(f"register {experiment_id} first")
    nq = instrument_ladder("NQ", config, artifact, "NQ")
    surface = stability_surface(config, artifact)
    es = instrument_ladder("ES", config, artifact, "ES")
    nq_head, es_head = nq["headline"], es["headline"]
    gates = {
        "gross_gate_pass": nq_head["gross_gate_pass"],
        "ml_value_gate_pass": nq_head["ml_value_gate_pass"],
        "sibling_sign_gate_pass": bool(
            np.sign(nq_head["B4"]["gross_ticks_per_trade"])
            == np.sign(es_head["B4"]["gross_ticks_per_trade"])
        ),
    }
    gates["null_c_required"] = bool(gates["gross_gate_pass"] and gates["ml_value_gate_pass"])
    result = {
        "experiment_id": experiment_id,
        "config": config,
        "NQ": nq,
        "ES": es,
        "gates": gates,
        "null_c_status": "required-not-yet-run" if gates["null_c_required"] else "not-spent-real-gates-failed",
        "surface_cells": int(len(surface)),
    }
    result = sanitize(result)
    (artifact / "result.json").write_text(json.dumps(result, indent=2) + "\n", encoding="utf-8")
    print(pd.read_csv(artifact / "ladder_NQ.csv")[
        ["label", "n_trades", "gross_ticks_per_trade", "net_ticks_per_trade", "net_ticks_cluster_t", "zero_day_sharpe", "trade_day_sharpe", "vol_targeted_sharpe"]
    ].to_string(index=False))
    print(json.dumps(result["gates"], indent=2))
    return result


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--experiment-id", default="EXP-0002")
    args = parser.parse_args()
    run(args.config.resolve(), args.experiment_id)


if __name__ == "__main__":
    main()
