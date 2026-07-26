"""EXP-0032 follow-up: does the intraday-ATR buffer's uplift hold in recent years?

Re-runs only the relevant variants (close-confirmed anchor + the k=1.5 ATR cells
+ k=0 + the matched-width fixed buffer) and stratifies zero-day daily net Sharpe
by calendar year and by trailing cutoffs, reporting the uplift vs close-confirmed.
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from ..core.data import load_rth, noise_bands, POINT_VALUE, TICK
from ..core.engine import run as run_1m
from ..core.atr_buffer import ONE_SECOND_PATH, run_streaming_atr

OUT = Path(__file__).resolve().parents[1] / "artifacts" / "runs" / "EXP-0032"
FEES_PT = 2.25 / POINT_VALUE["NQ"]
SLIP = 0.5


def sharpe_on(trades, eligible_dates):
    cost_side = FEES_PT + SLIP * TICK["NQ"]
    dates = pd.Index(pd.to_datetime(eligible_dates), name="date")
    if len(dates) == 0:
        return 0.0, 0.0, 0
    t = trades.copy()
    t["date"] = pd.to_datetime(t["date"])
    t = t[t["date"].isin(dates)]
    gross = t.groupby("date")["points"].sum().reindex(dates, fill_value=0.0)
    counts = t.groupby("date").size().reindex(dates, fill_value=0)
    usd = (gross - counts * 2.0 * cost_side) * POINT_VALUE["NQ"]
    sd = usd.std(ddof=1)
    sh = float(usd.mean() / sd * np.sqrt(252)) if sd > 0 else 0.0
    return sh, float(usd.mean()), int(len(t))


def main():
    bars = load_rth("NQ")
    bands = noise_bands(bars, 90)
    eligible = np.sort(bands["date"].unique().astype("datetime64[ns]"))
    bars_e = bars[bars["date"].isin(eligible)].copy()

    one_min = run_1m(bars_e, bands, exit_check="every_bar")
    specs = [("N20_k1.5", 20, 1.5), ("N10_k1.5", 10, 1.5), ("N30_k1.5", 30, 1.5),
             ("k0_first_touch", 5, 0.0), ("fixed_matched", "const1", 6.375)]
    print(f"Scanning 1s once for {len(specs)} variants ...")
    tr, aud = run_streaming_atr(ONE_SECOND_PATH, bars_e, bands, specs)
    common = pd.to_datetime(np.asarray(aud["covered_dates"], dtype="datetime64[ns]"))

    frames = {"close_confirmed": one_min}
    frames.update({nm: tr[nm] for nm, _, _ in specs})

    yrs = pd.DatetimeIndex(common).year
    eras = {}
    for y in sorted(set(yrs)):
        eras[f"CY{y}"] = common[yrs == y]
    for cut in (2020, 2022, 2023, 2024, 2025):
        eras[f">={cut}"] = common[yrs >= cut]
    eras["full"] = common
    # trailing 252 eligible sessions (~last year)
    eras["last_252d"] = common.sort_values()[-252:]

    order = ["full", ">=2020", ">=2022", ">=2023", ">=2024", ">=2025",
             "last_252d"] + [f"CY{y}" for y in sorted(set(yrs)) if y >= 2021]
    rows = []
    for era in order:
        ed = eras[era]
        cc, _, _ = sharpe_on(frames["close_confirmed"], ed)
        row = {"era": era, "days": len(ed), "close_confirmed": cc}
        for nm in ["N20_k1.5", "N10_k1.5", "N30_k1.5", "fixed_matched", "k0_first_touch"]:
            sh, _, _ = sharpe_on(frames[nm], ed)
            row[nm] = sh
        row["uplift_N20k1.5_vs_cc"] = row["N20_k1.5"] - cc
        row["scaling_vs_fixed"] = row["N20_k1.5"] - row["fixed_matched"]
        rows.append(row)
    tab = pd.DataFrame(rows).set_index("era")
    tab.to_csv(OUT / "era_sharpe.csv")

    pd.set_option("display.width", 220, "display.max_columns", 20)
    print("\nZERO-DAY DAILY SHARPE BY ERA (0.5 tick/side)")
    print(tab.round(3).to_string())
    recent = tab.loc[[">=2024", ">=2025", "last_252d"]][
        ["close_confirmed", "N20_k1.5", "fixed_matched", "uplift_N20k1.5_vs_cc", "scaling_vs_fixed"]]
    print("\nRECENT-ERA FOCUS")
    print(recent.round(3).to_string())
    (OUT / "era_sharpe_summary.json").write_text(
        json.dumps({k: {c: float(v) for c, v in r.items()}
                    for k, r in tab.round(4).iterrows()}, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
