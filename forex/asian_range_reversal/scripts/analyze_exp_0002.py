"""Uncertainty and sizing diagnostics for frozen EXP-0002 outputs."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]


def block_ratio_interval(daily, value_col, count_col, draws=5000, block=20, seed=20260803):
    rng = np.random.default_rng(seed)
    values = daily[value_col].to_numpy(float)
    counts = daily[count_col].to_numpy(float)
    n = len(daily)
    results = []
    blocks_needed = int(np.ceil(n / block))
    for _ in range(draws):
        starts = rng.integers(0, n, blocks_needed)
        idx = np.concatenate([(np.arange(s, s + block) % n) for s in starts])[:n]
        denominator = counts[idx].sum()
        results.append(values[idx].sum() / denominator if denominator else np.nan)
    arr = np.asarray(results)
    return np.nanquantile(arr, [0.025, 0.975])


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", default="EXP-0002")
    args = parser.parse_args()
    run = PROJECT / "artifacts" / "runs" / args.experiment_id
    trades = pd.read_csv(run / "trades.csv", parse_dates=["trading_date"])
    audit = pd.read_csv(run / "daily_audit.csv", parse_dates=["trading_date"])
    rows, risk_rows = [], []
    for pair in sorted(trades.pair.unique()):
        dates = audit.loc[audit.pair.eq(pair), ["trading_date"]].drop_duplicates().sort_values("trading_date")
        for side in ["all", "long", "short"]:
            g = trades.loc[trades.pair.eq(pair) & ((trades.direction.eq(side)) if side != "all" else True)].copy()
            g["net"] = g.gross_pips - 0.5
            by_day = g.groupby("trading_date").agg(net=("net","sum"), count=("net","size"))
            daily = dates.merge(by_day, on="trading_date", how="left").fillna({"net":0.0,"count":0})
            lo, hi = block_ratio_interval(daily, "net", "count")
            mean = g.net.mean()
            rows.append({"pair":pair,"direction":side,"trades":len(g),"net_0p5_mean":mean,
                         "block20_ci_low":lo,"block20_ci_high":hi,
                         "positive_ci":bool(lo > 0)})
            net_r = g.gross_r - 0.5 / g.initial_risk_pips
            risk_rows.append({"pair":pair,"direction":side,"trades":len(g),
                              "gross_r_mean":g.gross_r.mean(),"net_0p5_r_mean":net_r.mean(),
                              "break_even_cost_pips":g.gross_pips.mean()})
    uncertainty = pd.DataFrame(rows)
    risk = pd.DataFrame(risk_rows)

    eligible = audit[["pair","trading_date"]].drop_duplicates()
    daily_trade = trades.assign(net=trades.gross_pips-0.5).groupby(["pair","trading_date"]).net.sum().reset_index()
    panel = eligible.merge(daily_trade, on=["pair","trading_date"], how="left").fillna({"net":0.0})
    portfolio = panel.groupby("trading_date").net.sum().sort_index()
    portfolio_summary = pd.DataFrame([{
        "days":len(portfolio),"mean_daily_net_pips":portfolio.mean(),
        "daily_sharpe":np.sqrt(252)*portfolio.mean()/portfolio.std(ddof=1),
        "max_drawdown_pips":float((portfolio.cumsum()-portfolio.cumsum().cummax().clip(lower=0)).min()),
    }])
    uncertainty.to_csv(run / "uncertainty.csv", index=False)
    risk.to_csv(run / "equal_risk.csv", index=False)
    portfolio_summary.to_csv(run / "two_pair_portfolio.csv", index=False)
    text = ["FROZEN-RESULT DIAGNOSTICS — NO PARAMETER SEARCH", "", "20-DAY MOVING-BLOCK INTERVALS",
            uncertainty.to_string(index=False), "", "EQUAL-RISK AND BREAK-EVEN COST",
            risk.to_string(index=False), "", "TWO-PAIR ONE-UNIT PORTFOLIO",
            portfolio_summary.to_string(index=False)]
    (run / "diagnostics.txt").write_text("\n".join(text), encoding="utf-8")
    print("\n".join(text))


if __name__ == "__main__":
    main()
