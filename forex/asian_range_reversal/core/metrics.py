import numpy as np
import pandas as pd


def max_drawdown(values):
    curve = np.cumsum(np.asarray(values, dtype=float))
    if not len(curve):
        return np.nan
    peaks = np.maximum.accumulate(np.r_[0.0, curve])[1:]
    return float(np.min(curve - peaks))


def summarize(trades, audit, costs=(0.0, 0.5, 1.0)):
    rows = []
    keys = ["target", "pair"]
    slices = [("all", trades)]
    for direction, g in trades.groupby("direction"):
        slices.append((direction, g))
    for slice_name, frame in slices:
        for (target, pair), g in frame.groupby(keys):
            eligible_dates = audit.loc[(audit.target == target) & (audit.pair == pair), "trading_date"].drop_duplicates()
            for cost in costs:
                net = g.gross_pips - cost
                by_day = g.assign(net=net).groupby("trading_date").net.sum().reindex(eligible_dates, fill_value=0.0)
                sd = by_day.std(ddof=1)
                rows.append({
                    "slice":slice_name, "target":target, "pair":pair, "cost_pips":cost,
                    "trades":len(g), "trading_days":len(eligible_dates),
                    "trades_per_day":len(g)/len(eligible_dates),
                    "mean_gross_pips":g.gross_pips.mean(), "mean_net_pips":net.mean(),
                    "median_net_pips":net.median(), "win_rate_net":float((net > 0).mean()),
                    "mean_gross_r":g.gross_r.mean(),
                    "daily_mean_pips":by_day.mean(),
                    "daily_sharpe":np.sqrt(252)*by_day.mean()/sd if sd > 0 else np.nan,
                    "max_drawdown_pips":max_drawdown(by_day.to_numpy()),
                })
    return pd.DataFrame(rows)


def exit_mix(trades):
    return (trades.groupby(["target","pair","direction","exit_reason"], observed=True)
            .size().rename("trades").reset_index())
