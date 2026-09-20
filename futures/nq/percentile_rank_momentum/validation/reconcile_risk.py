"""Reconcile daily/weekly risk from immutable trade files with a start-zero curve."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..backtest_engine.metrics import cost_points_per_side
from ..strategy.features import load_canonical_rth_5m
from futures.nq.noise_vwap.core.data import POINT_VALUE


PROJECT = Path(__file__).resolve().parents[1]


def run(experiment_id: str) -> pd.DataFrame:
    artifact = PROJECT / "artifacts" / "runs" / experiment_id
    result = json.loads((artifact / "result.json").read_text(encoding="utf-8"))
    rows = []
    for inst in ("NQ", "ES"):
        bars, _ = load_canonical_rth_5m(inst)
        start = pd.Timestamp(result[inst]["common_start"])
        dates = pd.Index(bars.loc[bars["date"] >= start, "date"].drop_duplicates().sort_values())
        costs = result["config"]["costs"]
        cost = 2.0 * cost_points_per_side(
            inst, costs["slippage_ticks_per_side"], costs["fee_usd_per_side"]
        )
        for arm in ("B0", "B1", "B2", "B3", "B4", "B1_matched"):
            trades = pd.read_parquet(artifact / f"trades_{inst}_{arm}.parquet")
            daily = (
                (trades.assign(net_points=trades["points"] - cost)
                 .groupby("date")["net_points"].sum())
                .reindex(dates).fillna(0.0) * POINT_VALUE[inst]
            )
            curve = pd.concat(
                [pd.Series([0.0]), daily.cumsum().reset_index(drop=True)], ignore_index=True
            )
            drawdown = curve - curve.cummax()
            weekly = daily.groupby(pd.DatetimeIndex(daily.index).to_period("W-FRI")).sum()
            positive_total = daily[daily > 0].sum()
            top5_share = (
                float(daily.nlargest(5).sum() / positive_total) if positive_total > 0 else np.nan
            )
            rows.append({
                "instrument": inst,
                "arm": arm,
                "sessions": int(len(dates)),
                "trades": int(len(trades)),
                "worst_day_usd": float(daily.min()),
                "daily_p01_usd": float(daily.quantile(0.01)),
                "worst_week_usd": float(weekly.min()),
                "max_drawdown_usd_start_zero": float(drawdown.min()),
                "top5_positive_day_share": top5_share,
            })
    output = pd.DataFrame(rows)
    output.to_csv(artifact / "risk_reconciliation.csv", index=False)
    print(output.to_string(index=False))
    return output


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--experiment-id", default="EXP-0002")
    args = parser.parse_args()
    run(args.experiment_id)


if __name__ == "__main__":
    main()
