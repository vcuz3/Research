"""EXP-0031: 1s first-touch continuous stop with conservative execution latency.

Extends EXP-0009.  The continuous-stop (every-minute-refreshed) one-second
first-touch exit is re-run with an execution-time-slippage model: the stop-market
order is triggered at the first one-second touch but does not fill until
``latency`` seconds later, at that later second's open, capped so the fill is
never better than the stop.  ``latency == 0`` reproduces the EXP-0009
`1s_touch_every_bar_refresh` result bit-exactly.  We sweep latency at the primary
0.5 tick/side slippage and report the 0.25/0.5/1.0 tick cost sensitivity at a
conservative fixed latency.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.first_touch import ONE_SECOND_PATH, run_streaming_latencies
from .forensic import sizing


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0031"
FEES_PT = 2.25 / POINT_VALUE["NQ"]
LATENCIES = [0, 1, 2, 3, 5]          # seconds of execution delay
COST_TICKS = [0.25, 0.5, 1.0]        # per-side slippage sensitivity


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

    print("Scanning one-second NQ once; every latency evaluated in the same pass.")
    touch, scan_audit = run_streaming_latencies(
        ONE_SECOND_PATH, bars_e, bands, LATENCIES, refresh_every_bar=True)
    common_dates = np.asarray(scan_audit.pop("covered_dates"), dtype="datetime64[ns]")

    # Reference frames: current 1m continuous stop and the 1s instant-touch (L=0).
    one_min_cont = run_1m(bars_e, bands, exit_check="every_bar")
    frames = {"1m_continuous_next_open": one_min_cont}
    for lat in LATENCIES:
        frames[f"1s_touch_latency_{lat}s"] = touch[lat]

    # Zero-day daily metrics: latency sweep at every cost, references included.
    summaries = []
    for slip in COST_TICKS:
        for label, trades in frames.items():
            summaries.append(zero_day_summary(trades, common_dates, slip, label))
    summary = pd.DataFrame(summaries)

    # Vol-targeted headline for the same frames.
    headline = []
    for slip in COST_TICKS:
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

    for lat in LATENCIES:
        touch[lat].to_parquet(OUT / f"trades_1s_touch_latency_{lat}s.parquet", index=False)
    summary.to_csv(OUT / "zero_day_summary.csv", index=False)
    headline.to_csv(OUT / "vol_target_summary.csv", index=False)
    audit = {
        "source": str(ONE_SECOND_PATH),
        "parquet_rows": 142481276,
        "scan": scan_audit,
        "latencies_seconds": LATENCIES,
        "cost_ticks_per_side": COST_TICKS,
        "common_first": str(pd.Timestamp(common_dates.min()).date()),
        "common_last": str(pd.Timestamp(common_dates.max()).date()),
        "common_sessions": int(len(common_dates)),
    }
    (OUT / "data_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    prim = summary[summary["slippage_ticks_per_side"] == 0.5]
    prim_h = headline[headline["slippage_ticks_per_side"] == 0.5]
    print("\nPRIMARY: 0.5 tick/side + $2.25/side, zero-day daily metrics (latency sweep)")
    print(prim.to_string(index=False))
    print("\nVOL-TARGETED HEADLINE (0.5 tick/side)")
    print(prim_h.to_string(index=False))
    print("\nCOST SENSITIVITY at latency 2s (conservative)")
    lat2 = summary[summary["label"] == "1s_touch_latency_2s"]
    print(lat2.to_string(index=False))
    print("\nAUDIT")
    print(json.dumps(audit, indent=2))


if __name__ == "__main__":
    main()
