"""Frozen gap/RVOL position sizing schedule with paired Null-C validation.

All entry and exit state is unchanged. A causal weight is fixed at the signal
bar close and scales the complete trade, including round-trip costs.

Run: python -u -m futures.nq.noise_vwap.scripts.hyp_0009_gap_rvol_sizing [30]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd

from ..core import engine2 as E
from ..core import session as S
from ..core.data import POINT_VALUE
from .studies import COST_025, get_session, _null_c_frame
from .wfo_data import LOOKBACK

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "artifacts" / "runs" / "EXP-0017"
CONFIG = ROOT / "experiments" / "configs" / "hyp_0009_gap_rvol_sizing.json"
ERA_CUT = pd.Timestamp("2023-01-01")
RT_COST = 2.0 * COST_025


def signal_features(bars: pd.DataFrame, bands: pd.DataFrame) -> pd.DataFrame:
    b = bars.sort_values(["sdate", "mfo"]).copy()
    b["vol_base_90"] = b.groupby("mfo", sort=False)["volume"].transform(
        lambda x: x.shift(1).rolling(LOOKBACK, min_periods=LOOKBACK).mean()
    )
    b["rvol_90"] = b["volume"] / b["vol_base_90"]
    daily = bands.groupby("sdate", as_index=False)[["rth_open", "prior_close"]].first()
    b = b.merge(daily, on="sdate", how="left")
    b["open_gap"] = b["rth_open"] / b["prior_close"] - 1.0
    return b[["sdate", "mfo", "rvol_90", "open_gap"]]


def add_weights(trades: pd.DataFrame, features: pd.DataFrame) -> pd.DataFrame:
    t = trades.copy()
    t["signal_mfo"] = t["entry_mfo"].astype(int) - 1
    f = features.rename(columns={"sdate": "date", "mfo": "signal_mfo"})
    t = t.merge(f, on=["date", "signal_mfo"], how="left", validate="many_to_one")
    t["aligned_gap"] = t["side"] * t["open_gap"]
    against = t["aligned_gap"] < 0.0
    rv = t["rvol_90"]
    t["weight"] = np.select(
        [against & (rv < 1.0),
         against & (rv >= 1.0) & (rv < 1.5),
         (~against) & (rv > 1.5)],
        [0.5, 0.75, 1.25], default=1.0,
    )
    t["atr_pts"] = t["date"].map(t.groupby("date")["atr_pts"].first()) \
        if "atr_pts" in t else np.nan
    t["gross_points"] = t["points"]
    t["net_points"] = t["points"] - RT_COST
    t["baseline_net_atr"] = t["net_points"] / t["atr_pts"]
    t["weighted_gross_atr"] = t["weight"] * t["gross_points"] / t["atr_pts"]
    t["weighted_cost_atr"] = t["weight"] * RT_COST / t["atr_pts"]
    t["weighted_net_atr"] = t["weight"] * t["net_points"] / t["atr_pts"]
    return t


def run_tape(bars: pd.DataFrame) -> tuple[pd.DataFrame, pd.DatetimeIndex]:
    bands = S.noise_bands(bars, LOOKBACK)
    dm = S.decision_mfos(30, int(bars["mfo"].max()))
    trades = E.run(bars, bands, dm, exit_check="every_bar")
    atr = bars.groupby("sdate")["atr"].first()
    trades["atr_pts"] = trades["date"].map(atr)
    weighted = add_weights(trades, signal_features(bars, bands))
    eligible = pd.DatetimeIndex(pd.to_datetime(bands["sdate"].unique())).sort_values()
    return weighted, eligible


def portfolio_stats(t: pd.DataFrame, eligible: pd.DatetimeIndex, arm: str) -> dict:
    col = "baseline_net_atr" if arm == "baseline" else "weighted_net_atr"
    gross_col = None if arm == "baseline" else "weighted_gross_atr"
    dates = pd.to_datetime(t["date"])
    use = t.assign(date=dates)
    daily = use.groupby("date")[col].sum().reindex(eligible, fill_value=0.0)
    mean, sd = float(daily.mean()), float(daily.std(ddof=1))
    equity = daily.cumsum()
    maxdd = float((equity.cummax() - equity).max())
    if arm == "baseline":
        gross = float((use["gross_points"] / use["atr_pts"]).sum())
        cost = float((RT_COST / use["atr_pts"]).sum())
        mean_weight = 1.0
        net_points = float(use["net_points"].sum())
    else:
        gross = float(use[gross_col].sum())
        cost = float(use["weighted_cost_atr"].sum())
        mean_weight = float(use["weight"].mean())
        net_points = float((use["weight"] * use["net_points"]).sum())
    return {
        "arm": arm, "n_trades": int(len(use)), "n_eligible_days": int(len(daily)),
        "sum_net_R": float(daily.sum()), "sum_gross_R": gross,
        "sum_cost_R": cost, "daily_mean_R": mean,
        "daily_sharpe": mean / sd * np.sqrt(252) if sd > 0 else 0.0,
        "max_drawdown_R": maxdd, "worst_day_R": float(daily.min()),
        "mean_trade_weight": mean_weight, "net_points": net_points,
        "net_usd_per_base_contract": net_points * POINT_VALUE["NQ"],
    }


def slice_era(t: pd.DataFrame, eligible: pd.DatetimeIndex, era: str):
    if era == "pre2023":
        return t[pd.to_datetime(t["date"]) < ERA_CUT], eligible[eligible < ERA_CUT]
    if era == "2023plus":
        return t[pd.to_datetime(t["date"]) >= ERA_CUT], eligible[eligible >= ERA_CUT]
    return t, eligible


def summaries(t: pd.DataFrame, eligible: pd.DatetimeIndex) -> pd.DataFrame:
    rows = []
    for era in ("full", "pre2023", "2023plus"):
        te, de = slice_era(t, eligible, era)
        for arm in ("baseline", "sized"):
            rows.append({"era": era, **portfolio_stats(te, de, arm)})
    return pd.DataFrame(rows)


def main(ndraw: int = 30) -> None:
    cfg = json.loads(CONFIG.read_text())
    bars = get_session("RTH")
    real_trades, eligible = run_tape(bars)
    real = summaries(real_trades, eligible)
    full = real[real["era"] == "full"].set_index("arm")
    d_sh = float(full.loc["sized", "daily_sharpe"] - full.loc["baseline", "daily_sharpe"])
    d_r = float(full.loc["sized", "sum_net_R"] - full.loc["baseline", "sum_net_R"])
    d_dd = float(full.loc["baseline", "max_drawdown_R"] - full.loc["sized", "max_drawdown_R"])

    null_rows = []
    for draw in range(ndraw):
        seed = int(cfg["null_seed_start"]) + draw
        nt, ne = run_tape(_null_c_frame(bars, seed=seed))
        ns = summaries(nt, ne)
        nf = ns[ns["era"] == "full"].set_index("arm")
        null_rows.append({
            "draw": draw + 1, "seed": seed,
            "delta_sharpe": nf.loc["sized", "daily_sharpe"] - nf.loc["baseline", "daily_sharpe"],
            "delta_net_R": nf.loc["sized", "sum_net_R"] - nf.loc["baseline", "sum_net_R"],
            "drawdown_improvement_R": nf.loc["baseline", "max_drawdown_R"] - nf.loc["sized", "max_drawdown_R"],
            "mean_trade_weight": nf.loc["sized", "mean_trade_weight"],
        })
        print(f"Null-C draw {draw + 1}/{ndraw}", end="\r")
    print()
    null = pd.DataFrame(null_rows)
    null_mean = float(null["delta_sharpe"].mean())
    null_sd = float(null["delta_sharpe"].std(ddof=1))
    z = (d_sh - null_mean) / null_sd if null_sd > 0 else np.nan
    p_upper = float((null["delta_sharpe"] >= d_sh).mean())
    era = real.pivot(index="era", columns="arm", values="sum_net_R")
    era_delta = (era["sized"] - era["baseline"]).to_dict()
    passed = bool(d_sh > 0 and d_r >= 0 and d_dd > 0 and z >= 2.0)
    weakened = not (era_delta["pre2023"] > 0 and era_delta["2023plus"] > 0)
    verdict = {
        "real_delta_sharpe": d_sh, "real_delta_net_R": d_r,
        "real_drawdown_improvement_R": d_dd,
        "mean_trade_weight": float(full.loc["sized", "mean_trade_weight"]),
        "null_delta_sharpe_mean": null_mean, "null_delta_sharpe_sd": null_sd,
        "null_z": z, "null_upper_tail_fraction": p_upper,
        "era_delta_net_R": era_delta, "kill_test_passed": passed,
        "era_stability_weakened": weakened,
    }
    OUT.mkdir(parents=True, exist_ok=True)
    real.to_csv(OUT / "real_summary.csv", index=False)
    null.to_csv(OUT / "null_c_paired.csv", index=False)
    real_trades.to_parquet(OUT / "weighted_trades.parquet", index=False)
    (OUT / "verdict.json").write_text(json.dumps(verdict, indent=2) + "\n")
    review = [
        "# EXP-0017 Gap/RVOL Dynamic Sizing\n",
        "Historical status: consumed discovery sample; future shadow is the only clean holdout.\n",
        "Frozen weights: 0.5x gap-against/RVOL<1; 0.75x gap-against/RVOL 1-1.5; 1.25x gap-aligned/RVOL>1.5; otherwise 1x.\n",
        f"Real: delta Sharpe {d_sh:+.3f}, delta net R {d_r:+.3f}, drawdown improvement {d_dd:+.3f}R, mean weight {verdict['mean_trade_weight']:.3f}x.\n",
        f"Paired Null-C ({ndraw}): delta Sharpe mean {null_mean:+.3f} +/- {null_sd:.3f}; z={z:+.2f}, upper-tail fraction={p_upper:.3f}.\n",
        f"Era delta net R: pre-2023 {era_delta['pre2023']:+.3f}; 2023+ {era_delta['2023plus']:+.3f}.\n",
        f"Kill test: {'PASS' if passed else 'REJECT'}; era weakener: {'TRIGGERED' if weakened else 'not triggered'}.\n",
        "Weights are risk units. Fractional NQ sizing requires a multi-contract account, MNQ mapping, or causal rounding policy before deployment.\n",
    ]
    (OUT / "review.md").write_text("\n".join(review))
    print(json.dumps(verdict, indent=2))


if __name__ == "__main__":
    main(int(sys.argv[1]) if len(sys.argv) > 1 else 30)
