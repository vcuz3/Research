"""Follow-up: the scheduled RSI clock's advantage is a PHASE effect. Which one?

Arm D of the decomposition showed the :29 sampling phase is the best of all 30
phases of the half hour (rank 30/30 in three of four pair/era cells), with a
cross-phase spread far larger than the scheduled-vs-crossing gap itself. That
rules out "scheduled sampling selects a better state" and points at the wall
clock. This script asks which part of the wall clock.

  G1. Phase sweep split into the first traded minute and the remaining 29.
  G2. Phase sweep with entry and exit both delayed one minute, which keeps the
      signal phase but moves the traded window off the half-hour boundary.
  G3. Full-range (no threshold) rank IC between RSI and the signed forward
      30-minute return, per phase. Uses every row, so it is not a small-sample
      artifact of the 30/70 extremes.
  G4. Minute-of-hour data quality: open-to-previous-close discontinuity, mean
      one-minute return, and bar coverage.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
from scipy.stats import spearmanr

import importlib.util

spec = importlib.util.spec_from_file_location(
    "decomp", Path(__file__).resolve().parent / "_run_rsi_clock_decomposition.py"
)
decomp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(decomp)

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "rsi_clock_phase_forensics_results.json"
INTERVAL = decomp.SCHEDULE_INTERVAL_MIN
HORIZON = decomp.HORIZON_MIN


def main() -> None:
    results = {}
    for pair in decomp.PAIRS:
        print(f"\n================ {pair} ================", flush=True)
        raw, one_minute = decomp.load_pre_holdout(pair)
        rsi = decomp.wilder_rsi(raw.close.to_numpy(dtype=float), one_minute, decomp.RSI_LENGTH)
        side = np.select([rsi <= decomp.LOW, rsi >= decomp.HIGH], [1, -1], default=0).astype("int8")

        panel = pd.DataFrame(
            {
                "time": raw.time,
                "sdate": raw.sdate,
                "utc_minute": raw.utc_minute,
                "rsi": rsi,
                "side": side,
                "fwd30": decomp.endpoint_pips(raw, 1, 1 + HORIZON),
                "fwd1": decomp.endpoint_pips(raw, 1, 2),
                "fwd30_delayed": decomp.endpoint_pips(raw, 2, 2 + HORIZON),
                "open": raw.open.astype(float),
                "close": raw.close.astype(float),
            }
        )
        panel["era"] = np.where(panel.time < decomp.ERA_SPLIT, "early", "late")
        panel = panel.loc[panel.time >= decomp.EXPLORATION_START].reset_index(drop=True)
        panel["phase"] = panel.utc_minute % INTERVAL
        panel["pnl"] = panel.side * panel.fwd30
        panel["pnl_min1"] = panel.side * panel.fwd1
        panel["pnl_rest"] = panel.pnl - panel.pnl_min1
        panel["pnl_delayed"] = panel.side * panel.fwd30_delayed

        pair_out = {}

        # -------- G1 / G2
        print("\n[G1/G2] Phase sweep: first minute vs rest, and a one-minute delayed window")
        rows = []
        for era in ["early", "late"]:
            e = panel.loc[(panel.era == era) & (panel.side != 0)]
            g = e.groupby("phase")
            table = pd.DataFrame(
                {
                    "n": g.pnl.count(),
                    "mean": g.pnl.mean(),
                    "min1": g.pnl_min1.mean(),
                    "rest": g.pnl_rest.mean(),
                    "delayed": g.pnl_delayed.mean(),
                }
            )
            print(f"  -- {era}")
            print("     phase 29 :", table.loc[29].round(4).to_dict())
            others = table.drop(index=29)
            print("     other 29 phases (median):",
                  {k: round(float(v), 4) for k, v in others.median().to_dict().items()})
            print(f"     phase-29 excess over median:  total={table.loc[29,'mean']-others['mean'].median():+.4f}"
                  f"  first-minute={table.loc[29,'min1']-others['min1'].median():+.4f}"
                  f"  rest={table.loc[29,'rest']-others['rest'].median():+.4f}"
                  f"  delayed={table.loc[29,'delayed']-others['delayed'].median():+.4f}")
            print(f"     rank of phase 29 -- total {int((table['mean']<table.loc[29,'mean']).sum())+1}/30"
                  f" | first-minute {int((table['min1']<table.loc[29,'min1']).sum())+1}/30"
                  f" | rest {int((table['rest']<table.loc[29,'rest']).sum())+1}/30"
                  f" | delayed {int((table['delayed']<table.loc[29,'delayed']).sum())+1}/30")
            rows.append({"era": era, "table": table.reset_index().to_dict("records")})
        pair_out["G1_G2_phase_split"] = rows

        # -------- G3 full-range IC per phase
        print("\n[G3] Full-range rank IC(rsi, signed fwd 30m) by phase, all rows, no threshold")
        ic_rows = []
        for era in ["early", "late"]:
            e = panel.loc[panel.era == era, ["phase", "rsi", "fwd30"]].dropna()
            ics = {}
            for phase, cell in e.groupby("phase"):
                ics[int(phase)] = float(spearmanr(cell.rsi, cell.fwd30).statistic)
            arr = np.array([ics[p] for p in range(INTERVAL)])
            # more negative = stronger mean reversion
            print(f"  -- {era}: phase29={arr[29]:+.5f}  median={np.median(arr):+.5f}  "
                  f"min={arr.min():+.5f} (phase {int(arr.argmin())})  max={arr.max():+.5f}  "
                  f"sd={arr.std():.5f}  rank_of_29 (most negative=1) = "
                  f"{int((arr < arr[29]).sum())+1}/30   n_per_phase~{len(e)//INTERVAL}")
            ic_rows.append({"era": era, "ic_by_phase": ics})
        pair_out["G3_fullrange_ic"] = ic_rows

        # -------- G4 minute-of-hour data quality
        print("\n[G4] Minute-of-hour bar structure (all rows, both eras pooled)")
        p = panel.copy()
        p["prev_close"] = p.close.shift(1)
        p["contiguous"] = one_minute[-len(p):] if len(one_minute) >= len(p) else np.nan
        p["jump_pips"] = (p.open - p.prev_close).abs() / decomp.PIP_SIZE
        p["min_of_hour"] = (p.utc_minute % 60).astype(int)
        p["ret_pips"] = (p.close - p.open) / decomp.PIP_SIZE
        q = p.loc[p.contiguous == True]
        agg = q.groupby("min_of_hour").agg(
            n=("open", "size"),
            mean_open_close_jump_pips=("jump_pips", "mean"),
            share_open_eq_prev_close=("jump_pips", lambda s: float((s == 0).mean())),
            mean_bar_ret_pips=("ret_pips", "mean"),
        )
        special = agg.loc[[0, 29, 30, 59]]
        print("     minutes 0 / 29 / 30 / 59 vs the all-minute median")
        print(special.round(5).to_string())
        print("     median across all 60 minutes:",
              {k: round(float(v), 5) for k, v in agg.median().to_dict().items()})
        pair_out["G4_minute_of_hour"] = agg.reset_index().to_dict("records")

        results[pair] = pair_out

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
