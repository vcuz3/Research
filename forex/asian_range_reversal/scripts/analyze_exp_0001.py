"""Post-hoc decomposition of EXP-0001 discovery trades; does not resimulate."""

import argparse
from pathlib import Path

import numpy as np
import pandas as pd


PROJECT = Path(__file__).resolve().parents[1]


def summarize(g):
    daily = g.assign(net_0p5=g.gross_pips - 0.5).groupby("trading_date").agg(
        gross=("gross_pips","sum"), net=("net_0p5","sum"), trades=("gross_pips","size"))
    return pd.Series({
        "trades":len(g), "days":g.trading_date.nunique(), "gross_mean":g.gross_pips.mean(),
        "net_0p5_mean":g.gross_pips.mean()-0.5, "gross_r_mean":g.gross_r.mean(),
        "target_rate":g.exit_reason.isin(["target","target_gap"]).mean(),
        "stop_rate":g.exit_reason.str.startswith("stop").mean(),
        "eod_rate":g.exit_reason.eq("eod").mean(), "daily_gross_mean":daily.gross.mean(),
        "daily_net_0p5_mean":daily.net.mean(),
    })


def qcut_by_pair(frame, column, labels=5):
    pieces = []
    for _, g in frame.groupby(["target","pair"]):
        z = g.copy()
        z[f"{column}_q"] = pd.qcut(z[column].rank(method="first"), labels,
                                    labels=[f"Q{i}" for i in range(1,labels+1)])
        pieces.append(z)
    return pd.concat(pieces, ignore_index=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--experiment-id", default="EXP-0001")
    args = parser.parse_args()
    run = PROJECT / "artifacts" / "runs" / args.experiment_id
    trades = pd.read_csv(run / "trades.csv", parse_dates=["trading_date"])
    audit = pd.read_csv(run / "daily_audit.csv", parse_dates=["trading_date"])
    trades["year"] = trades.trading_date.dt.year
    trades["month"] = trades.trading_date.dt.month
    trades["entry_session"] = pd.cut(trades.entry_slot, [419,779,1139,1439],
                                      labels=["London","NY_AM","NY_PM"])
    trades["holding_min"] = trades.exit_slot - trades.entry_slot + 1
    trades["sequence"] = trades.groupby(["target","pair","trading_date"]).cumcount() + 1
    trades["sequence_bucket"] = np.where(trades.sequence >= 4, "4+", trades.sequence.astype(str))
    trades["rsi_extremity"] = np.where(trades.direction.eq("short"), trades.signal_rsi-70, 30-trades.signal_rsi)
    trades["target_distance_pips"] = abs(trades.target_price-trades.entry_price) / np.where(
        trades.pair.eq("EURUSD"), 0.0001, 0.0001)
    trades["planned_reward_risk"] = trades.target_distance_pips / trades.initial_risk_pips
    midpoint = trades.target.eq("midpoint")
    boundary = np.where(trades.direction.eq("short"),
                        trades.target_price + trades.asian_range_pips*0.0001/2,
                        trades.target_price - trades.asian_range_pips*0.0001/2)
    trades["entry_extension_pips"] = np.where(
        midpoint & trades.direction.eq("short"), (trades.entry_price-boundary)/0.0001,
        np.where(midpoint, (boundary-trades.entry_price)/0.0001, np.nan))
    trades["entry_extension_atr"] = trades.entry_extension_pips / trades.signal_atr_pips

    core = trades.groupby(["target","pair","direction"], observed=True).apply(summarize, include_groups=False).reset_index()
    yearly = trades.groupby(["target","pair","direction","year"], observed=True).apply(summarize, include_groups=False).reset_index()
    session = trades.groupby(["target","pair","direction","entry_session"], observed=True).apply(summarize, include_groups=False).reset_index()
    sequence = trades.groupby(["target","pair","direction","sequence_bucket"], observed=True).apply(summarize, include_groups=False).reset_index()

    temp = qcut_by_pair(trades, "asian_range_pips")
    range_q = temp.groupby(["target","pair","direction","asian_range_pips_q"], observed=True).apply(summarize, include_groups=False).reset_index()
    temp = qcut_by_pair(trades, "signal_atr_pips")
    atr_q = temp.groupby(["target","pair","direction","signal_atr_pips_q"], observed=True).apply(summarize, include_groups=False).reset_index()
    temp = qcut_by_pair(trades, "rsi_extremity")
    rsi_q = temp.groupby(["target","pair","direction","rsi_extremity_q"], observed=True).apply(summarize, include_groups=False).reset_index()
    mid = trades.loc[midpoint & trades.entry_extension_atr.notna()].copy()
    temp = qcut_by_pair(mid, "entry_extension_atr")
    extension_q = temp.groupby(["target","pair","direction","entry_extension_atr_q"], observed=True).apply(summarize, include_groups=False).reset_index()

    state = audit.groupby(["target","pair"])[["entries","ignored_signals","ambiguous_signals","invalid_geometry"]].sum().reset_index()
    daily = trades.groupby(["target","pair","trading_date"]).gross_pips.sum().reset_index()
    concentration = []
    for (target,pair), g in daily.groupby(["target","pair"]):
        ordered = g.gross_pips.sort_values()
        total_abs = ordered.abs().sum()
        concentration.append({"target":target,"pair":pair,"days":len(g),
                              "gross_total":ordered.sum(), "worst_day":ordered.iloc[0],
                              "best_day":ordered.iloc[-1],
                              "worst_20_days":ordered.head(20).sum(),
                              "best_20_days":ordered.tail(20).sum(),
                              "top20_abs_share":ordered.abs().nlargest(20).sum()/total_abs})
    concentration = pd.DataFrame(concentration)

    tables = {"posthoc_core":core,"posthoc_yearly":yearly,"posthoc_session":session,
              "posthoc_sequence":sequence,"posthoc_range_quintile":range_q,
              "posthoc_atr_quintile":atr_q,"posthoc_rsi_quintile":rsi_q,
              "posthoc_extension_quintile":extension_q,"posthoc_state":state,
              "posthoc_concentration":concentration}
    for name, table in tables.items():
        table.to_csv(run / f"{name}.csv", index=False)

    focus = ["POST-HOC DISCOVERY ANALYSIS — NOT A VALIDATED FILTER", "", "CORE", core.to_string(index=False),
             "", "BY ENTRY SESSION", session.to_string(index=False), "", "BY TRADE SEQUENCE",
             sequence.to_string(index=False), "", "BY RSI EXTREMITY QUINTILE", rsi_q.to_string(index=False),
             "", "BY ASIAN RANGE QUINTILE", range_q.to_string(index=False), "", "BY ATR QUINTILE",
             atr_q.to_string(index=False), "", "BY ENTRY EXTENSION / ATR (MIDPOINT)", extension_q.to_string(index=False),
             "", "YEARLY", yearly.to_string(index=False), "", "STATE AUDIT", state.to_string(index=False),
             "", "CONCENTRATION", concentration.to_string(index=False)]
    (run / "posthoc_analysis.txt").write_text("\n".join(focus), encoding="utf-8")
    print(f"Wrote post-hoc tables and {run / 'posthoc_analysis.txt'}")


if __name__ == "__main__":
    main()
