"""EXP-0009: rerun the NQ GO strategy with causal one-second touch exits."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.first_touch import ONE_SECOND_PATH, run_streaming_both
from .forensic import sizing


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0009"
FEES_PT = 2.25 / POINT_VALUE["NQ"]


def zero_day_summary(trades, eligible_dates, slip_ticks, label):
    cost_side = FEES_PT + slip_ticks * TICK["NQ"]
    dates = pd.Index(pd.to_datetime(eligible_dates), name="date")
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    gross = t.groupby("date")["points"].sum().reindex(dates, fill_value=0.0)
    counts = t.groupby("date").size().reindex(dates, fill_value=0)
    net = gross - counts * 2.0 * cost_side
    usd = net * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    sharpe = usd.mean() / sd * np.sqrt(252) if sd > 0 else 0.0
    tstat = usd.mean() / (sd / np.sqrt(len(usd))) if sd > 0 else 0.0
    return {
        "label": label, "slippage_ticks_per_side": slip_ticks,
        "eligible_days": len(dates), "n_trades": len(t),
        "gross_pts_per_trade": float(t["points"].mean()),
        "net_pts_per_trade": float((t["points"] - 2 * cost_side).mean()),
        "daily_net_mean_usd": float(usd.mean()), "daily_net_t": float(tstat),
        "daily_net_sharpe_zero_days": float(sharpe),
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()

    print("Scanning one-second NQ once; both modes use a compiled kernel, no row iteration.")
    touch, scan_audit = run_streaming_both(ONE_SECOND_PATH, bars_e, bands)
    touch_decision = touch["decision"]
    touch_continuous = touch["every_bar"]
    common_dates = np.asarray(scan_audit.pop("covered_dates"), dtype="datetime64[ns]")

    one_min_base = run_1m(bars_e, bands, exit_check="decision")
    one_min_cont = run_1m(bars_e, bands, exit_check="every_bar")
    frames = {
        "1m_baseline_next_open": one_min_base,
        "1m_continuous_next_open": one_min_cont,
        "1s_touch_decision_refresh": touch_decision,
        "1s_touch_every_bar_refresh": touch_continuous,
    }
    summaries = []
    for slip in (0.25, 0.5, 1.0):
        for label, trades in frames.items():
            summaries.append(zero_day_summary(trades, common_dates, slip, label))
    summary = pd.DataFrame(summaries)

    # Preserve the project's headline vol-targeted metric for direct comparison.
    headline = []
    for slip in (0.25, 0.5, 1.0):
        cost = FEES_PT + slip * TICK["NQ"]
        for label, trades in frames.items():
            m = sizing("NQ", bars_e, trades, cost)
            headline.append({
                "label": label, "slippage_ticks_per_side": slip,
                "cagr": m["cagr"], "sharpe": m["sharpe"],
                "max_drawdown": m["maxdd"], "annual_vol": m["annvol"],
                "n_trades": m["n_trades"], "net_pts_per_trade": m["pt_net"],
            })
    headline = pd.DataFrame(headline)

    for name, frame in frames.items():
        frame.to_parquet(OUT / f"trades_{name}.parquet", index=False)
    summary.to_csv(OUT / "zero_day_summary.csv", index=False)
    headline.to_csv(OUT / "vol_target_summary.csv", index=False)
    audit = {
        "source": str(ONE_SECOND_PATH),
        "parquet_rows": 142481276,
        "scan": scan_audit,
        "common_first": str(pd.Timestamp(common_dates.min()).date()),
        "common_last": str(pd.Timestamp(common_dates.max()).date()),
        "common_sessions": int(len(common_dates)),
    }
    (OUT / "data_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    primary = summary[summary["slippage_ticks_per_side"] == 0.5]
    primary_h = headline[headline["slippage_ticks_per_side"] == 0.5]
    print("\nPRIMARY: 0.5 tick/side + $2.25/side, zero-day daily metrics")
    print(primary.to_string(index=False))
    print("\nVOL-TARGETED HEADLINE")
    print(primary_h.to_string(index=False))
    print("\nAUDIT")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
