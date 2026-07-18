"""
Focused probe: was the OLD NQ vendor data's clock actually mislabelled in recent
years, the way ES was? The migration audit said NQ was "mostly clean" on the basis
of a 09:30-open PRICE match (5-8% mismatch recent). The user says NQ recent data was
ALSO mislabelled at 09:30 ET. A price-equality test can MISS a shift if the shifted
minute happens to carry a near-equal price, and it conflates "wrong hour" with "right
hour, slightly different vendor print". So test the clock the *direct* way instead:

  1. Volume-share-by-ET-hour, per era, on the OLD backup under the EXACT lossy
     Chicago->ET round-trip the old loader used (reproduce what the pipeline saw).
     A correctly-clocked frame peaks in 09:30-16:00 ET; a shifted one does not.
  2. Same, but treating old `dt` as if it were already ET (localize, don't convert)
     -- to see which interpretation actually lines the volume up with the RTH bell.
  3. Bar-level look at a handful of recent NQ sessions: where does the volume-weighted
     session actually sit, old vs new, minute by minute around the 09:30 open and
     16:00 close.

Run:  python -u -m futures.nq.noise_vwap.scripts.probe_old_nq_tz
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

OLD = Path(__file__).resolve().parents[1] / "data" / "old_vendor_backup"
DB = Path(__file__).resolve().parents[3] / "data" / "databento"
RAW_NQ = DB / "NQ_ohlcv-1m_NQv0_20110801_20260715.parquet"
OLD_NQ = OLD / "NQ_1m_clean.parquet"
OLD_ES = OLD / "ES_1m_clean.parquet"


def vol_by_hour_era(et: pd.Series, vol: pd.Series, label: str) -> None:
    yr = et.dt.year
    hod = et.dt.hour
    df = pd.DataFrame({"yr": yr.to_numpy(), "hod": hod.to_numpy(), "vol": vol.to_numpy()})
    print(f"\n  [{label}] volume share by ET hour, per era:")
    for lab, mask in [("2011-2015", df["yr"] <= 2015),
                      ("2016-2020", (df["yr"] >= 2016) & (df["yr"] <= 2020)),
                      ("2021-2023", (df["yr"] >= 2021) & (df["yr"] <= 2023)),
                      ("2024-2026", df["yr"] >= 2024)]:
        sub = df[mask]
        if sub.empty:
            continue
        vh = sub.groupby("hod")["vol"].sum()
        share = vh.loc[9:15].sum() / vh.sum()
        top = vh.sort_values(ascending=False).head(5).index.tolist()
        print(f"    {lab}: RTH(9-15h ET) share={share:6.1%}  peak ET hours={sorted(top)}")


def main() -> None:
    print("=" * 78)
    print("OLD NQ vendor data — is the recent-years clock actually correct?")
    print("=" * 78)

    old = pd.read_parquet(OLD_NQ)
    print(f"old NQ rows={len(old):,}  columns={list(old.columns)}")
    dt = pd.to_datetime(old["dt"])
    print(f"old `dt` range: {dt.min()} -> {dt.max()}  (tz={dt.dt.tz})")

    # interpretation A: old loader treated `dt` as Chicago wall-clock, converted to ET
    ctA = dt.dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
    okA = ctA.notna()
    etA = ctA[okA].dt.tz_convert("America/New_York")
    vol_by_hour_era(etA, old.loc[okA, "volume"], "A: dt=Chicago -> ET (what loader did)")

    # interpretation B: `dt` was actually already ET (localize only, no shift)
    etB = dt.dt.tz_localize("America/New_York", ambiguous="NaT", nonexistent="NaT")
    okB = etB.notna()
    vol_by_hour_era(etB[okB], old.loc[okB, "volume"], "B: dt already ET (localize only)")

    # interpretation C: `dt` was UTC
    etC = dt.dt.tz_localize("UTC").dt.tz_convert("America/New_York")
    vol_by_hour_era(etC, old["volume"], "C: dt=UTC -> ET")

    # ---- new (databento truth) for reference
    new = pd.read_parquet(RAW_NQ, columns=["ts_event", "volume"])
    etN = new["ts_event"].dt.tz_convert("America/New_York")
    vol_by_hour_era(etN, new["volume"], "NEW databento (truth)")

    # ---- bar-level: a few recent NQ sessions, old(A) vs new, around the bell
    print("\n" + "=" * 78)
    print("Bar-level recent NQ sessions: minute of session's PEAK-volume bar & first/last")
    print("(if the clock is right, RTH volume peaks 09:30-16:00 ET; open bar tod=570)")
    print("=" * 78)
    oldA = pd.DataFrame({
        "et": etA.to_numpy(),
        "tod": (etA.dt.hour * 60 + etA.dt.minute).to_numpy(),
        "date": etA.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": old.loc[okA, "open"].to_numpy(),
        "close": old.loc[okA, "close"].to_numpy(),
        "volume": old.loc[okA, "volume"].to_numpy(),
    })
    newf = pd.DataFrame({
        "et": etN.to_numpy(),
        "tod": (etN.dt.hour * 60 + etN.dt.minute).to_numpy(),
        "date": etN.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": new["open"].to_numpy() if "open" in new else np.nan,
        "close": new["close"].to_numpy() if "close" in new else np.nan,
        "volume": new["volume"].to_numpy(),
    }) if "open" in new.columns else None
    if newf is None:
        newfull = pd.read_parquet(RAW_NQ, columns=["ts_event", "open", "close", "volume"])
        etNf = newfull["ts_event"].dt.tz_convert("America/New_York")
        newf = pd.DataFrame({
            "et": etNf.to_numpy(),
            "tod": (etNf.dt.hour * 60 + etNf.dt.minute).to_numpy(),
            "date": etNf.dt.normalize().dt.tz_localize(None).to_numpy(),
            "open": newfull["open"].to_numpy(),
            "close": newfull["close"].to_numpy(),
            "volume": newfull["volume"].to_numpy(),
        })

    for probe in ["2024-06-03", "2025-02-03", "2025-06-02", "2025-11-03", "2026-06-01"]:
        d = pd.Timestamp(probe).normalize()
        oo = oldA[oldA["date"] == d]
        nn = newf[newf["date"] == d]
        if oo.empty and nn.empty:
            continue
        def peak(df):
            if df.empty:
                return None
            rth = df[(df["tod"] >= 540) & (df["tod"] < 990)]
            if rth.empty:
                rth = df
            pk = rth.loc[rth["volume"].idxmax()]
            return pk["tod"]
        # open price at tod 570 in each
        def open0930(df):
            row = df[df["tod"] == 570]
            return float(row["open"].iloc[0]) if len(row) else float("nan")
        print(f"\n{probe}: old peakvol tod={peak(oo)}  new peakvol tod={peak(nn)}  "
              f"| old 09:30open={open0930(oo):.2f}  new 09:30open={open0930(nn):.2f}  "
              f"| old first/last tod={oo['tod'].min() if len(oo) else None}/{oo['tod'].max() if len(oo) else None}"
              f" new={nn['tod'].min() if len(nn) else None}/{nn['tod'].max() if len(nn) else None}")


if __name__ == "__main__":
    main()
