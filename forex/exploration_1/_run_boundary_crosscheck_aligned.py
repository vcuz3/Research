"""Aligned re-run of the minute-of-hour reversal check across all four sources.

The first cross-check compared apples to oranges. On the IBKR archive every bar
satisfies open(t) == close(t-1) exactly, so its open-to-open return over
[t, t+1] IS the close-to-close return ending at close(t) - the series is shifted
one minute relative to a close-to-close series built the same way on a vendor
whose bars do NOT satisfy that identity (LSE, where a minute's open is the first
tick inside it). Labelling differences of one minute are fatal when the whole
claim is about two specific minutes.

This script fixes the convention: r_m = P(m) - P(m-1), where P(m) is the LAST
observed price in minute m, and the return is labelled by its ENDING minute.
ac1(m) = corr(r_{m-1}, r_m). One definition, all four sources.

It also adds the control the first pass lacked: CME trade prints carry bid-ask
bounce (ac1 about -0.35 everywhere), and bounce scales inversely with activity,
which is itself strongly minute-of-hour patterned (volume at :00 is about 2x the
median minute). So the raw CME ac1 profile is partly a liquidity profile. Arm Y3
regresses ac1 on log activity across the 60 minutes and reads the residual.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

import importlib.util

_spec = importlib.util.spec_from_file_location(
    "xc", Path(__file__).resolve().parent / "_run_boundary_crosscheck.py"
)
xc = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(xc)

_spec2 = importlib.util.spec_from_file_location(
    "decomp", Path(__file__).resolve().parent / "_run_rsi_clock_decomposition.py"
)
decomp = importlib.util.module_from_spec(_spec2)
_spec2.loader.exec_module(decomp)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "boundary_crosscheck_aligned_results.json"


def load_ibkr_minutes(pair: str) -> pd.DataFrame:
    raw, _ = decomp.load_pre_holdout(pair)
    raw = raw.loc[raw.time >= decomp.EXPLORATION_START]
    return pd.DataFrame(
        {
            "time": raw.time.values,
            "open": raw.open.astype(float).values,
            "close": raw.close.astype(float).values,
            "activity": 1.0,
        }
    )


def load_lse(key: str) -> pd.DataFrame:
    f = xc.load_lse_minutes(key)
    return pd.DataFrame({"time": f.time, "open": f.open, "close": f.close, "activity": f.ticks})


def load_cme(key: str) -> pd.DataFrame:
    f = xc.load_cme_minutes(key)
    return pd.DataFrame(
        {"time": f.time, "open": f.open, "close": f.close, "activity": f.ticks, "symbol": f.symbol}
    )


def aligned_ac1(frame: pd.DataFrame, price_col: str, pip: float) -> pd.DataFrame:
    """r_m = P(m) - P(m-1), labelled by its ending minute m."""
    t = frame.time
    prev_ok = np.array(t.diff().eq(pd.Timedelta(minutes=1)).to_numpy(), copy=True)
    if "symbol" in frame:
        prev_ok &= np.asarray(frame.symbol.eq(frame.symbol.shift(1)).to_numpy())
    px = frame[price_col].to_numpy(dtype=float)
    r = np.full(len(px), np.nan)
    r[1:] = (px[1:] - px[:-1]) / pip
    r[~prev_ok] = np.nan
    r_prev = np.r_[np.nan, r[:-1]]
    r_prev[np.r_[False, ~prev_ok[:-1]]] = np.nan
    d = pd.DataFrame(
        {
            "min_of_hour": ((t.dt.hour * 60 + t.dt.minute) % 60).to_numpy(),
            "r": r,
            "r_prev": r_prev,
            "activity": frame.activity.to_numpy(dtype=float),
        }
    )
    rows = []
    for m, cell in d.groupby("min_of_hour"):
        z = cell[["r_prev", "r"]].dropna()
        rows.append(
            {
                "min_of_hour": int(m),
                "n": int(len(z)),
                "ac1": float(z.r_prev.corr(z.r)),
                "activity": float(cell.activity.mean()),
            }
        )
    return pd.DataFrame(rows).set_index("min_of_hour").sort_index()


def report(tab: pd.DataFrame, label: str, control_activity: bool) -> dict:
    med = float(tab.ac1.median())
    rank = tab.ac1.rank(method="min")
    print(f"    median ac1 = {med:+.5f}   n/minute ~ {int(tab.n.median())}")
    out = {"label": label, "median_ac1": med}
    for m in [0, 30]:
        exc = tab.loc[m, "ac1"] - med
        z = exc * np.sqrt(tab.loc[m, "n"])
        print(f"      minute :{m:02d}  ac1={tab.loc[m,'ac1']:+.5f}  excess={exc:+.5f}  "
              f"z={z:+.2f}  rank={int(rank.loc[m])}/60")
        out[f"minute_{m:02d}"] = {"ac1": float(tab.loc[m, "ac1"]), "excess": float(exc),
                                  "z": float(z), "rank": int(rank.loc[m])}
    print(f"      six most negative: {tab.ac1.sort_values().index.tolist()[:6]}")
    out["six_most_negative"] = [int(x) for x in tab.ac1.sort_values().index.tolist()[:6]]

    if control_activity and tab.activity.gt(0).all():
        x = np.log(tab.activity.to_numpy())
        y = tab.ac1.to_numpy()
        beta = np.polyfit(x, y, 1)
        resid = y - np.polyval(beta, x)
        rtab = pd.Series(resid, index=tab.index)
        rrank = rtab.rank(method="min")
        corr = float(np.corrcoef(x, y)[0, 1])
        print(f"    activity control: corr(ac1, log activity) across the 60 minutes = {corr:+.3f}")
        print(f"      residual ac1  :00 {rtab.loc[0]:+.5f} rank {int(rrank.loc[0])}/60"
              f"   :30 {rtab.loc[30]:+.5f} rank {int(rrank.loc[30])}/60")
        print(f"      six most negative residuals: {rtab.sort_values().index.tolist()[:6]}")
        out["activity_control"] = {
            "corr_ac1_logactivity": corr,
            "resid_00": float(rtab.loc[0]), "rank_00": int(rrank.loc[0]),
            "resid_30": float(rtab.loc[30]), "rank_30": int(rrank.loc[30]),
            "six_most_negative_resid": [int(v) for v in rtab.sort_values().index.tolist()[:6]],
        }
    out["table"] = tab.reset_index().to_dict("records")
    return out


def main() -> None:
    jobs = [
        ("IBKR/EURUSD", lambda: load_ibkr_minutes("EURUSD"), 1e-4, False),
        ("IBKR/GBPUSD", lambda: load_ibkr_minutes("GBPUSD"), 1e-4, False),
        ("LSE/EURUSD", lambda: load_lse("EURUSD"), 1e-4, True),
        ("LSE/GBPUSD", lambda: load_lse("GBPUSD"), 1e-4, True),
        ("CME/6E", lambda: load_cme("6E"), 1e-4, True),
        ("CME/6B", lambda: load_cme("6B"), 1e-4, True),
    ]
    results = {}
    for name, loader, pip, ctrl in jobs:
        print(f"\n================ {name} ================", flush=True)
        frame = loader()
        print(f"  rows={len(frame)}  {frame.time.min()} -> {frame.time.max()}")
        rec = {}
        print("\n  [Y1] ALIGNED close-to-close, r_m labelled by its ending minute")
        rec["Y1_close"] = report(aligned_ac1(frame, "close", pip), f"{name}/close", ctrl)
        print("\n  [Y2] same convention on the minute OPEN price (bar-construction probe)")
        rec["Y2_open"] = report(aligned_ac1(frame, "open", pip), f"{name}/open", False)
        results[name] = rec
        del frame

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
