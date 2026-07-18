"""
Characterize the ~5-8% recent-year NQ 09:30-open mismatches the migration audit
logged. Two competing explanations:

  (H1 shift)  the old 09:30 bar is really a DIFFERENT minute's price -> the old
              session's 09:30 open matches the NEW session at some other tod (an
              hours mislabel, like ES).
  (H2 noise)  same minute, slightly different vendor print (a tick or two) -> old
              09:30 open is close to new 09:30 open but not bit-identical, and does
              NOT match any other minute better.

For every recent-year (2021+) common session whose 09:30 open mismatches, find which
NEW-session tod the OLD 09:30 open price best matches. If shifts, best-match tod is a
constant non-570 offset. If noise, best match stays at/near 570 with a tiny delta.

Run:  python -u -m futures.nq.noise_vwap.scripts.probe_nq_mismatch
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OLD = Path(__file__).resolve().parents[1] / "data" / "old_vendor_backup"
DB = Path(__file__).resolve().parents[3] / "data" / "databento"
RAW_NQ = DB / "NQ_ohlcv-1m_NQv0_20110801_20260715.parquet"
OLD_NQ = OLD / "NQ_1m_clean.parquet"


def main() -> None:
    old = pd.read_parquet(OLD_NQ)
    dt = pd.to_datetime(old["dt"])
    ct = dt.dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
    ok = ct.notna()
    etO = ct[ok].dt.tz_convert("America/New_York")
    oldf = pd.DataFrame({
        "tod": (etO.dt.hour * 60 + etO.dt.minute).to_numpy(),
        "date": etO.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": old.loc[ok, "open"].to_numpy(),
    })

    new = pd.read_parquet(RAW_NQ, columns=["ts_event", "open"])
    etN = new["ts_event"].dt.tz_convert("America/New_York")
    newf = pd.DataFrame({
        "tod": (etN.dt.hour * 60 + etN.dt.minute).to_numpy(),
        "date": etN.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": new["open"].to_numpy(),
    })

    oldf = oldf[(oldf["tod"] >= 570) & (oldf["tod"] < 960)]
    newf = newf[(newf["tod"] >= 540) & (newf["tod"] < 990)]
    oldf["yr"] = pd.to_datetime(oldf["date"]).dt.year
    recent_dates = sorted(oldf.loc[oldf["yr"] >= 2021, "date"].unique())

    old_open0930 = oldf[oldf["tod"] == 570].set_index("date")["open"]
    new_by_date = {d: g for d, g in newf.groupby("date")}
    new_open0930 = newf[newf["tod"] == 570].set_index("date")["open"]

    shift_tods = []
    noise = 0
    shift = 0
    examples = []
    n_checked = 0
    for d in recent_dates:
        if d not in old_open0930.index or d not in new_by_date:
            continue
        oo = old_open0930.loc[d]
        no = new_open0930.get(d, np.nan)
        if np.isclose(oo, no, rtol=0, atol=1e-6):
            continue  # matched, not a mismatch
        n_checked += 1
        g = new_by_date[d]
        # which new tod does the old 09:30 open best match?
        i = (g["open"] - oo).abs().values.argmin()
        best_tod = int(g["tod"].values[i])
        best_delta = float(abs(g["open"].values[i] - oo))
        delta_at_570 = float(abs(no - oo)) if not np.isnan(no) else np.nan
        if best_tod != 570 and best_delta < 1e-6:
            shift += 1
            shift_tods.append(best_tod)
        else:
            noise += 1
        if len(examples) < 12:
            examples.append((str(pd.Timestamp(d).date()), oo, no,
                             best_tod, best_delta, delta_at_570))

    print("=" * 78)
    print("Recent-year (2021+) NQ 09:30-open MISMATCHES — shift vs vendor-print noise")
    print("=" * 78)
    print(f"recent common sessions with a 09:30 mismatch: {n_checked}")
    print(f"  classified as HOURS-SHIFT (old 09:30 exactly = new price at tod!=570): {shift}")
    print(f"  classified as vendor-print NOISE (best match at/near 570, tiny delta): {noise}")
    if shift_tods:
        vc = pd.Series(shift_tods).value_counts().head(10)
        print(f"  shift best-match tods (if any): \n{vc.to_string()}")
    print("\nexamples (date | old0930 | new0930 | best_new_tod | delta@best | delta@570):")
    for e in examples:
        print(f"  {e[0]}  old={e[1]:.2f}  new={e[2]:.2f}  best_tod={e[3]}  "
              f"d@best={e[4]:.4f}  d@570={e[5]:.4f}")


if __name__ == "__main__":
    main()
