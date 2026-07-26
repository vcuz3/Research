"""EXP-0031 (decomposition): separate the 1s exit gap into WICK vs LATENCY.

The 1m "continuous" stop is CLOSE-CONFIRMED (core/engine.py line ~158: a 1-min bar
must CLOSE beyond the band to exit, then fills next open).  The EXP-0009 1s engine
exits on the first intrabar TOUCH -- a different rule that fires on 1-second wicks
the close-confirmed stop deliberately holds through.  This script isolates the two
effects on one Parquet scan:

  A  1m continuous            close-confirmed, next-1m-open fill   (core/engine.py)
  B  1s close-confirmed L0    close-confirmed, first-1s-open fill  (trigger=1)
  C  1s first-touch    L0     touch, 1s fill                       (trigger=0)
  C1 1s first-touch    L1     touch, 1s fill + 1s latency
  C2 1s first-touch    L2     touch, 1s fill + 2s latency

Reads:
  * B - A  ~ 0            => resolution / fill-timing is neutral (same rule, finer data)
  * C - B  = wick cost    => premature exits the close-confirmation was filtering out
  * C1 - C = latency      => execution slippage, secondary to the wick cost
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.first_touch import ONE_SECOND_PATH, run_streaming_specs
from .forensic import sizing


OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0031"
FEES_PT = 2.25 / POINT_VALUE["NQ"]
SLIP = 0.5  # primary tick/side


def daily(trades, eligible_dates, slip_ticks=SLIP):
    cost_side = FEES_PT + slip_ticks * TICK["NQ"]
    dates = pd.Index(pd.to_datetime(eligible_dates), name="date")
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    gross = t.groupby("date")["points"].sum().reindex(dates, fill_value=0.0)
    counts = t.groupby("date").size().reindex(dates, fill_value=0)
    usd = (gross - counts * 2.0 * cost_side) * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    stops = int((t["reason"] == "touch").sum())
    return {
        "n_trades": len(t), "stop_exits": stops,
        "gross_pt_per_trade": float(t["points"].mean()),
        "net_pt_per_trade": float((t["points"] - 2 * cost_side).mean()),
        "daily_net_usd": float(usd.mean()),
        "daily_sharpe": float(usd.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0,
        "daily_t": float(usd.mean() / (sd / np.sqrt(len(usd)))) if sd > 0 else 0.0,
    }


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()

    specs = [
        ("1s_close_confirmed_L0", 1, 0),
        ("1s_first_touch_L0", 0, 0),
        ("1s_first_touch_L1", 0, 1),
        ("1s_first_touch_L2", 0, 2),
    ]
    print("One scan of the 1s file; close-confirmed + first-touch + latency together.")
    touch, audit = run_streaming_specs(ONE_SECOND_PATH, bars_e, bands, specs,
                                       refresh_every_bar=True)
    common = np.asarray(audit.pop("covered_dates"), dtype="datetime64[ns]")

    one_min = run_1m(bars_e, bands, exit_check="every_bar")
    frames = {"1m_continuous_A": one_min}
    frames.update({f"{nm}": touch[nm] for nm, _, _ in specs})

    rows = []
    for label, tr in frames.items():
        d = daily(tr, common)
        d["label"] = label
        m = sizing("NQ", bars_e, tr, FEES_PT + SLIP * TICK["NQ"])
        d["voltarget_sharpe"] = m["sharpe"]
        d["voltarget_maxdd"] = m["maxdd"]
        rows.append(d)
    tab = pd.DataFrame(rows).set_index("label")[
        ["n_trades", "stop_exits", "gross_pt_per_trade", "net_pt_per_trade",
         "daily_net_usd", "daily_sharpe", "daily_t", "voltarget_sharpe",
         "voltarget_maxdd"]]
    tab.to_csv(OUT / "decomposition.csv")

    A = tab.loc["1m_continuous_A"]
    B = tab.loc["1s_close_confirmed_L0"]
    C = tab.loc["1s_first_touch_L0"]
    C1 = tab.loc["1s_first_touch_L1"]
    decomp = {
        "resolution_B_minus_A": {
            "d_daily_sharpe": float(B.daily_sharpe - A.daily_sharpe),
            "d_gross_pt": float(B.gross_pt_per_trade - A.gross_pt_per_trade),
            "d_trades": int(B.n_trades - A.n_trades),
        },
        "wick_C_minus_B": {
            "d_daily_sharpe": float(C.daily_sharpe - B.daily_sharpe),
            "d_gross_pt": float(C.gross_pt_per_trade - B.gross_pt_per_trade),
            "d_stop_exits": int(C.stop_exits - B.stop_exits),
            "d_trades": int(C.n_trades - B.n_trades),
        },
        "latency_C1_minus_C": {
            "d_daily_sharpe": float(C1.daily_sharpe - C.daily_sharpe),
            "d_gross_pt": float(C1.gross_pt_per_trade - C.gross_pt_per_trade),
        },
    }
    audit["decomposition"] = decomp
    (OUT / "decomposition_audit.json").write_text(json.dumps(audit, indent=2), encoding="utf-8")

    pd.set_option("display.width", 200, "display.max_columns", 20)
    print("\nDECOMPOSITION (0.5 tick/side + fees, common 3628 sessions)")
    print(tab.round(4).to_string())
    print("\nEFFECT SIZES")
    print(json.dumps(decomp, indent=2))


if __name__ == "__main__":
    main()
