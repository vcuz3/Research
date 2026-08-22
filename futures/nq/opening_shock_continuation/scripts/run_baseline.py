"""Run the preregistered Gao et al. paper-rule futures transfer."""

from __future__ import annotations

import argparse
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import norm

from ..backtest_engine.data import INSTRUMENT_SPECS, execution_sessions
from ..backtest_engine.engine import CostProfile, run_fixed_schedule
from ..backtest_engine.metrics import hac_t, summarize
from ..strategy.signals import baseline_feature_frame, baseline_signals
from ..validation.baseline import (
    injected_positive_control,
    primary_cost_mde,
    year_conditioned_circular_null,
)
from .common import BASELINE_CONFIG, cost_profile, load_json, write_json


def _period(dates: pd.Series) -> pd.Series:
    dates = pd.to_datetime(dates)
    return pd.Series(
        np.select(
            [
                dates.le("2013-12-31"),
                dates.between("2014-01-01", "2018-12-31"),
                dates.between("2019-01-01", "2022-12-31"),
                dates.ge("2023-01-01"),
            ],
            [
                "partial_overlap_2011_2013",
                "after_paper_sample_2014_2018",
                "post_jfe_2019_2022",
                "recent_2023_2026",
            ],
            default="outside",
        ),
        index=dates.index,
    )


def _execute(
    features: pd.DataFrame,
    side: pd.Series,
    *,
    instrument: str,
    entry_column: str,
    exit_column: str,
    costs: CostProfile,
    name: str,
    entry_time: str,
    exit_time: str,
    decision_time: str,
) -> pd.DataFrame:
    return run_fixed_schedule(
        features,
        side,
        instrument=instrument,
        entry_column=entry_column,
        exit_column=exit_column,
        costs=costs,
        decision_time_et=decision_time,
        entry_time_et=entry_time,
        exit_time_et=exit_time,
        strategy_name=name,
        extra_symbol_columns=("sym1500", "sym1529"),
    )


def _frozen_scope(frame: pd.DataFrame, config: dict[str, object]) -> pd.DataFrame:
    mask = pd.to_datetime(frame["date"]).between(
        str(config["paper_overlap_start"]),
        str(config["persistence_end"]),
        inclusive="both",
    )
    scoped = frame.loc[mask].reset_index(drop=True)
    if scoped.empty:
        raise ValueError("frozen paper-transfer scope contains no eligible sessions")
    return scoped


def _baseline_verdict(
    *,
    gross_mean: float,
    net_mean: float,
    nw_pvalue: float,
    paired_mean: float,
    circular_pvalue: float,
    machinery_valid: bool,
    alpha: float,
) -> str:
    """Apply the frozen hierarchy without letting machinery mask economics."""
    values = np.asarray(
        [gross_mean, net_mean, nw_pvalue, paired_mean, circular_pvalue, alpha],
        dtype=float,
    )
    if not np.isfinite(values).all() or not 0.0 < alpha < 1.0:
        raise ValueError("baseline verdict inputs must be finite and alpha must be in (0, 1)")
    observed_pass = bool(
        gross_mean > 0.0
        and net_mean > 0.0
        and nw_pvalue <= alpha
        and paired_mean > 0.0
    )
    if not observed_pass:
        return "REJECT"
    if not isinstance(machinery_valid, (bool, np.bool_)):
        raise TypeError("machinery_valid must be boolean")
    if not machinery_valid:
        return "INCONCLUSIVE"
    return "SUPPORTED" if circular_pvalue <= alpha else "REJECT"


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output-dir", required=True, type=Path)
    args = parser.parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    config = load_json(BASELINE_CONFIG)
    hac_lags = int(config["hac_lags"])

    summary_rows: list[dict[str, object]] = []
    yearly_rows: list[dict[str, object]] = []
    daily_rows: list[pd.DataFrame] = []
    primary_trades: pd.DataFrame | None = None
    primary_always: pd.DataFrame | None = None
    primary_sessions: pd.DataFrame | None = None
    zero_counts: dict[str, int] = {}

    for instrument in config["instruments"]:
        r1_sessions = _frozen_scope(
            execution_sessions(instrument, (config["r1_entry_column"], config["exit_column"])),
            config,
        )
        r1_features = baseline_feature_frame(r1_sessions)
        r1_signals = baseline_signals(r1_features)
        joint_sessions = _frozen_scope(
            execution_sessions(
                instrument, (config["r1_r12_entry_column"], config["exit_column"])
            ),
            config,
        )
        joint_features = baseline_feature_frame(joint_sessions)
        joint_signals = baseline_signals(joint_features)
        zero_counts[instrument] = int(r1_features["paper_r1_log"].eq(0).sum())
        arms = {
            "paper_r1": (r1_sessions, r1_features, r1_signals["paper_r1"], config["r1_entry_column"], config["r1_entry_order_active_time_et"], config["r1_signal_available_time_et"]),
            "paper_r1_r12_agree": (joint_sessions, joint_features, joint_signals["paper_r1_r12_agree"], config["r1_r12_entry_column"], config["r1_r12_entry_order_active_time_et"], config["r1_r12_signal_available_time_et"]),
            "always_long": (r1_sessions, r1_features, pd.Series(1, index=r1_sessions.index, dtype="int8"), config["r1_entry_column"], config["r1_entry_order_active_time_et"], "09:30:00"),
        }
        cost_profiles = {"gross": CostProfile(0.0, 0.0)}
        for ticks in config["cost_stress_ticks_per_side"]:
            label = f"{ticks:g}_ticks_per_side"
            cost_profiles[label] = cost_profile(config, float(ticks))

        for arm, (arm_sessions, arm_features, side, entry_column, entry_time, decision_time) in arms.items():
            labels = _period(arm_sessions["date"])
            for cost_label, costs in cost_profiles.items():
                trades = _execute(
                    arm_sessions,
                    side,
                    instrument=instrument,
                    entry_column=entry_column,
                    exit_column=config["exit_column"],
                    costs=costs,
                    name=arm,
                    entry_time=entry_time,
                    exit_time=config["scheduled_exit_order_active_time_et"],
                    decision_time=decision_time,
                )
                trades["period"] = labels.to_numpy()
                trades["cost_profile"] = cost_label
                if cost_label in {"gross", "1_ticks_per_side"}:
                    daily_rows.append(trades)
                masks = {
                    "full": np.ones(len(trades), dtype=bool),
                    "post_paper_sample_2014_2026": pd.to_datetime(trades["date"]).between(
                        config["persistence_start"], config["persistence_end"], inclusive="both"
                    ),
                    **{label: labels.eq(label).to_numpy() for label in sorted(labels.unique())},
                }
                for period_name, mask in masks.items():
                    stats = summarize(trades.loc[mask].reset_index(drop=True), hac_lags=hac_lags)
                    summary_rows.append(
                        {
                            "instrument": instrument,
                            "arm": arm,
                            "cost_profile": cost_label,
                            "period": period_name,
                            **stats,
                        }
                    )
                years = pd.to_datetime(trades["date"]).dt.year
                for year in sorted(years.unique()):
                    year_mask = years.eq(year).to_numpy()
                    yearly_rows.append(
                        {
                            "instrument": instrument,
                            "arm": arm,
                            "cost_profile": cost_label,
                            "calendar_year": int(year),
                            **summarize(
                                trades.loc[year_mask].reset_index(drop=True),
                                hac_lags=hac_lags,
                            ),
                        }
                    )
                if instrument == "ES" and arm == "paper_r1" and cost_label == "1_ticks_per_side":
                    primary_trades = trades.copy()
                    primary_sessions = arm_sessions.copy()
                if instrument == "ES" and arm == "always_long" and cost_label == "1_ticks_per_side":
                    primary_always = trades.copy()

        # Adjacent-second scheduled-exit sensitivities at primary costs.
        for exit_column, exit_time in (("exit_155958", "15:59:58"), ("exit_160000", "16:00:00")):
            sensitivity_sessions = _frozen_scope(
                execution_sessions(instrument, (config["r1_entry_column"], exit_column)),
                config,
            )
            sensitivity_features = baseline_feature_frame(sensitivity_sessions)
            sensitivity_signal = baseline_signals(sensitivity_features)["paper_r1"]
            trades = _execute(
                sensitivity_sessions,
                sensitivity_signal,
                instrument=instrument,
                entry_column=config["r1_entry_column"],
                exit_column=exit_column,
                costs=cost_profile(config),
                name="paper_r1",
                entry_time=config["r1_entry_order_active_time_et"],
                exit_time=exit_time,
                decision_time="10:00:00",
            )
            mask = pd.to_datetime(trades["date"]).between(
                config["persistence_start"], config["persistence_end"], inclusive="both"
            )
            summary_rows.append(
                {
                    "instrument": instrument,
                    "arm": f"paper_r1_exit_{exit_time}",
                    "cost_profile": "1_ticks_per_side",
                    "period": "post_paper_sample_2014_2026",
                    **summarize(trades.loc[mask].reset_index(drop=True), hac_lags=hac_lags),
                }
            )

    if primary_trades is None or primary_always is None or primary_sessions is None:
        raise AssertionError("ES primary baseline was not produced")
    post = pd.to_datetime(primary_trades["date"]).between(
        config["persistence_start"], config["persistence_end"], inclusive="both"
    ).to_numpy()
    primary_post = primary_trades.loc[post].reset_index(drop=True)
    always_post = primary_always.loc[post].reset_index(drop=True)
    post_sessions = primary_sessions.loc[post].reset_index(drop=True)
    if not primary_post["date"].equals(always_post["date"]) or not primary_post["date"].equals(
        post_sessions["date"]
    ):
        raise AssertionError("ES primary, always-long, and executable-session dates differ")

    alpha = float(config["test_alpha"])
    paired = primary_post["net_dollars"].to_numpy() - always_post["net_dollars"].to_numpy()
    primary_t = hac_t(primary_post["net_dollars"].to_numpy(), max_lag=hac_lags)
    paired_t = hac_t(paired, max_lag=hac_lags)

    # The primary null shifts unsigned, causally executable returns within year,
    # then reapplies the frozen ES r1 side and primary costs.  The statistic is
    # the preregistered zero-filled primary-cost HAC t, not Sharpe.
    side = primary_post["side"].to_numpy(dtype=int)
    if not np.isin(side, [-1, 1]).all():
        raise AssertionError("the ES r1 arm must trade exactly one side on every eligible day")
    outcome_points = (
        post_sessions[config["exit_column"]].to_numpy(dtype=float)
        - post_sessions[config["r1_entry_column"]].to_numpy(dtype=float)
    )
    spec = INSTRUMENT_SPECS["ES"]
    primary_cost = cost_profile(config)
    cost_dollars = (
        2.0 * primary_cost.slippage_ticks_per_side * spec.tick_size * spec.multiplier
        + primary_cost.round_trip_fees_usd
    )
    reconstructed_net = side * outcome_points * spec.multiplier - cost_dollars
    if not np.allclose(
        reconstructed_net,
        primary_post["net_dollars"].to_numpy(dtype=float),
        rtol=1e-12,
        atol=1e-8,
    ):
        raise AssertionError("baseline null PnL does not reconcile to the audited engine")

    mde = primary_cost_mde(
        primary_post,
        instrument="ES",
        hac_lags=hac_lags,
        multiplier=float(config["mde_multiplier"]),
    )
    positive_control = injected_positive_control(
        outcome_points,
        side,
        post_sessions["date"],
        multiplier=spec.multiplier,
        round_trip_cost_dollars=cost_dollars,
        target_zero_filled_net_sharpe=float(
            config["positive_control_target_zero_filled_net_sharpe"]
        ),
        hac_lags=hac_lags,
        draws=int(config["null_draws"]),
        seed=int(config["positive_control_null_seed"]),
    )
    # Do not interpret the real null unless the identical machinery detects the
    # preregistered known-real Sharpe-0.50 injection.
    baseline_null = year_conditioned_circular_null(
        outcome_points,
        side,
        post_sessions["date"],
        multiplier=spec.multiplier,
        round_trip_cost_dollars=cost_dollars,
        hac_lags=hac_lags,
        draws=int(config["null_draws"]),
        seed=int(config["null_seed"]),
    )
    if not np.isclose(primary_t, baseline_null.observed_hac_t, rtol=1e-12, atol=1e-12):
        raise AssertionError("reported primary HAC t differs from the null's observed statistic")

    summary_table = pd.DataFrame(summary_rows)
    summary_table.to_csv(args.output_dir / "baseline_summary.csv", index=False)
    pd.DataFrame(yearly_rows).to_csv(args.output_dir / "baseline_yearly.csv", index=False)
    pd.concat(daily_rows, ignore_index=True).to_csv(
        args.output_dir / "baseline_daily.csv.gz", index=False, compression="gzip"
    )
    pd.DataFrame({"null_hac_t": baseline_null.null_hac_t}).to_csv(
        args.output_dir / "baseline_null.csv.gz", index=False, compression="gzip"
    )
    pd.DataFrame({"null_hac_t": positive_control.null.null_hac_t}).to_csv(
        args.output_dir / "baseline_positive_control_null.csv.gz",
        index=False,
        compression="gzip",
    )

    primary_summary = summarize(primary_post, hac_lags=hac_lags)
    gross_mean = float(primary_post["gross_dollars"].mean())
    net_mean = float(primary_post["net_dollars"].mean())
    nw_pvalue = float(norm.sf(primary_t))
    paired_mean = float(paired.mean())
    machinery_valid = bool(positive_control.null.pvalue <= alpha)
    verdict = _baseline_verdict(
        gross_mean=gross_mean,
        net_mean=net_mean,
        nw_pvalue=nw_pvalue,
        paired_mean=paired_mean,
        circular_pvalue=baseline_null.pvalue,
        machinery_valid=machinery_valid,
        alpha=alpha,
    )
    supported = verdict == "SUPPORTED"
    write_json(
        args.output_dir / "baseline_verdict.json",
        {
            "scope": "partial-overlap futures transfer; not a SPY replication",
            "primary_instrument": "ES",
            "primary_arm": "paper_r1",
            "joint_arm_role": "secondary diagnostic; cannot rescue an ES r1 failure",
            "period": f'{config["persistence_start"]} through {config["persistence_end"]}',
            "primary_statistic": config["null_statistic"],
            "primary_summary": primary_summary,
            "gross_mean_daily_dollars": gross_mean,
            "net_mean_daily_dollars": net_mean,
            "nw_hac_lags": hac_lags,
            "nw_hac_t": primary_t,
            "nw_one_sided_p_normal": nw_pvalue,
            "paired_signal_minus_always_long_mean_dollars": paired_mean,
            "paired_nw_hac_t": paired_t,
            "year_conditioned_circular_null": {
                "draws": int(config["null_draws"]),
                "seed": int(config["null_seed"]),
                "invalid_draws": 0,
                "observed_hac_t": baseline_null.observed_hac_t,
                "null_mean_hac_t": float(np.mean(baseline_null.null_hac_t)),
                "null_sd_hac_t": float(np.std(baseline_null.null_hac_t, ddof=1)),
                "exceedances": baseline_null.exceedances,
                "p": baseline_null.pvalue,
                "clopper_pearson_interval": baseline_null.monte_carlo_interval,
            },
            "minimum_detectable_effect": mde,
            "positive_control": {
                "demeaning": "calendar year x r1 side",
                "draws": int(config["null_draws"]),
                "seed": int(config["positive_control_null_seed"]),
                "invalid_draws": 0,
                "target_zero_filled_net_sharpe": positive_control.target_zero_filled_net_sharpe,
                "achieved_zero_filled_net_sharpe": positive_control.achieved_zero_filled_net_sharpe,
                "injected_effect_points_per_trade": positive_control.injected_effect_points_per_trade,
                "injected_effect_dollars_per_trade": positive_control.injected_effect_dollars_per_trade,
                "observed_hac_t": positive_control.null.observed_hac_t,
                "exceedances": positive_control.null.exceedances,
                "p": positive_control.null.pvalue,
                "clopper_pearson_interval": positive_control.null.monte_carlo_interval,
                "required_p": alpha,
                "passed": machinery_valid,
            },
            "zero_r1_sessions": zero_counts,
            "machinery_valid": machinery_valid,
            "persistence_supported": supported,
            "verdict": verdict,
        },
    )


if __name__ == "__main__":
    main()
