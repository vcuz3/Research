"""Is the :29 phase advantage the SAME phenomenon on CME futures as on spot FX?

On IBKR spot the phase-:29 excess was concentrated in the first traded minute
(entirely so on GBPUSD). The aligned cross-check then found the proposed
mechanism - a one-minute reversal spike at :00/:30 - replicates on a second spot
vendor but NOT on CME futures, even though the :29 phase advantage itself
replicates on CME at rank 1/30.

So either the CME phase effect has a different shape, or the reversal spike was
never the mechanism. This arm measures the shape directly: sweep the RSI 30/70
signed P&L across all 30 phases and split each phase's result into the first
traded minute and the remaining 29.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import importlib.util

_s = importlib.util.spec_from_file_location(
    "xc", Path(__file__).resolve().parent / "_run_boundary_crosscheck.py"
)
xc = importlib.util.module_from_spec(_s)
_s.loader.exec_module(xc)

_s2 = importlib.util.spec_from_file_location(
    "aln", Path(__file__).resolve().parent / "_run_boundary_crosscheck_aligned.py"
)
aln = importlib.util.module_from_spec(_s2)
_s2.loader.exec_module(aln)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "phase_shape_crosscheck_results.json"
INTERVAL, HORIZON, PIP = 30, 30, 1e-4
LOW, HIGH = 30.0, 70.0


def analyse(frame: pd.DataFrame, name: str) -> dict:
    t = frame.time.reset_index(drop=True)
    frame = frame.reset_index(drop=True)
    prev_ok = np.array(t.diff().eq(pd.Timedelta(minutes=1)).to_numpy(), copy=True)
    if "symbol" in frame:
        prev_ok &= np.asarray(frame.symbol.eq(frame.symbol.shift(1)).to_numpy())
    rsi = xc.wilder_rsi(frame.close.to_numpy(dtype=float), prev_ok, xc.RSI_LENGTH)
    side = np.select([rsi <= LOW, rsi >= HIGH], [1, -1], default=0).astype("int8")

    def leg(a, b):
        e = frame.open.shift(-a).astype(float)
        x = frame.open.shift(-b).astype(float)
        ok = t.shift(-a).eq(t + pd.Timedelta(minutes=a)) & t.shift(-b).eq(t + pd.Timedelta(minutes=b))
        if "symbol" in frame:
            ok &= frame.symbol.shift(-b).eq(frame.symbol)
        return ((x - e) / PIP).where(ok)

    d = pd.DataFrame(
        {
            "phase": ((t.dt.hour * 60 + t.dt.minute) % INTERVAL).to_numpy(),
            "side": side,
            "pnl": side * leg(1, 1 + HORIZON),
            "min1": side * leg(1, 2),
        }
    )
    d["rest"] = d.pnl - d.min1
    d = d.loc[d.side != 0]
    g = d.groupby("phase")
    tab = pd.DataFrame({"n": g.pnl.count(), "mean": g.pnl.mean(),
                        "min1": g.min1.mean(), "rest": g.rest.mean()})
    others = tab.drop(index=29)
    out = {"label": name, "n_phase29": int(tab.loc[29, "n"])}
    print(f"    n at phase 29 = {int(tab.loc[29,'n'])}, median n elsewhere = {int(others.n.median())}")
    for col in ["mean", "min1", "rest"]:
        exc = tab.loc[29, col] - others[col].median()
        rank = int((tab[col] < tab.loc[29, col]).sum()) + 1
        print(f"      {col:5s}  phase29={tab.loc[29,col]:+.4f}  others_median={others[col].median():+.4f}"
              f"  excess={exc:+.4f}  rank={rank}/30")
        out[col] = {"phase29": float(tab.loc[29, col]), "others_median": float(others[col].median()),
                    "excess": float(exc), "rank": rank}
    share = out["min1"]["excess"] / out["mean"]["excess"] if out["mean"]["excess"] != 0 else np.nan
    print(f"      share of the total phase-29 excess sitting in the FIRST MINUTE: {share:.0%}")
    out["first_minute_share_of_excess"] = float(share)
    out["table"] = tab.reset_index().to_dict("records")
    return out


def main() -> None:
    jobs = [
        ("IBKR/EURUSD", lambda: aln.load_ibkr_minutes("EURUSD")),
        ("IBKR/GBPUSD", lambda: aln.load_ibkr_minutes("GBPUSD")),
        ("LSE/EURUSD", lambda: aln.load_lse("EURUSD")),
        ("LSE/GBPUSD", lambda: aln.load_lse("GBPUSD")),
        ("CME/6E", lambda: aln.load_cme("6E")),
        ("CME/6B", lambda: aln.load_cme("6B")),
    ]
    results = {}
    for name, loader in jobs:
        print(f"\n================ {name} ================", flush=True)
        frame = loader()
        results[name] = analyse(frame, name)
        del frame
    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
