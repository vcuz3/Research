"""
Data-quality audit of the new Databento 1-minute continuous futures files, and a
head-to-head comparison against the OLD `*_1m_clean.parquet` that the pipeline was
built on. Motivated by two concrete defects the user found in the old vendor data:

  (a) "hours were not adjusted correctly in recent years" -> a timezone / session-
      alignment defect that would silently move which bars count as RTH;
  (b) "some days had spikes in PnL from missing data" -> intraday gaps that let a
      single 1-min bar span a large move, manufacturing fake fills/PnL.

Databento gives us a true UTC `ts_event`, so the ET session clock is unambiguous
(convert UTC -> America/New_York; DST is handled by the tz database, no lossy
Chicago round-trip and no ambiguous-hour NaT drops).

We audit the RAW (unadjusted continuous, NQ.v.0 / ES.v.0) file — the faithful
equivalent of the original "Nearest" continuous series. Rolls happen at UTC
midnight (i.e. between RTH sessions), so no RTH session, VWAP, or trade spans a
roll; within-session percentage moves are the real contract's true moves. (The
back-adjusted-additive file distorts intraday ratios and is NOT used.)

Run:  python -m futures.nq.noise_vwap.scripts.audit_data
"""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd

DB = Path(__file__).resolve().parents[3] / "data" / "databento"
OLD = Path(__file__).resolve().parents[1] / "data"
RAW = {
    "NQ": DB / "NQ_ohlcv-1m_NQv0_20110801_20260715.parquet",
    "ES": DB / "ES_ohlcv-1m_ESv0_20110801_20260715.parquet",
}
# the OLD vendor data is preserved in old_vendor_backup/ (the live *_1m_clean.parquet
# has since been rebuilt from Databento). Compare NEW (databento) vs that backup.
OLD_PATHS = {"NQ": OLD / "old_vendor_backup" / "NQ_1m_clean.parquet",
             "ES": OLD / "old_vendor_backup" / "ES_1m_clean.parquet"}

RTH_START = 9 * 60 + 30   # 09:30 ET
RTH_END = 16 * 60         # 16:00 ET (exclusive)
FULL_RTH_BARS = RTH_END - RTH_START   # 390


def _to_et_raw(df: pd.DataFrame) -> pd.DataFrame:
    """Databento raw: ts_event is tz-aware UTC. Convert to ET directly."""
    et = df["ts_event"].dt.tz_convert("America/New_York")
    out = pd.DataFrame({
        "et": et,
        "tod": (et.dt.hour * 60 + et.dt.minute).to_numpy(),
        "date": et.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": df["open"].to_numpy(), "high": df["high"].to_numpy(),
        "low": df["low"].to_numpy(), "close": df["close"].to_numpy(),
        "volume": df["volume"].to_numpy(),
        "iid": df["instrument_id"].to_numpy(),
    })
    return out


def _to_et_old(df: pd.DataFrame) -> pd.DataFrame:
    """Old clean parquet: `dt` is Chicago wall-clock, tz-naive. Reproduce the exact
    lossy round-trip the OLD loader used, so this is what the pipeline actually saw."""
    dt = pd.to_datetime(df["dt"])
    ct = dt.dt.tz_localize("America/Chicago", ambiguous="NaT", nonexistent="NaT")
    ok = ct.notna()
    df = df.loc[ok]
    et = ct[ok].dt.tz_convert("America/New_York")
    out = pd.DataFrame({
        "et": et.to_numpy(),
        "tod": (et.dt.hour * 60 + et.dt.minute).to_numpy(),
        "date": et.dt.normalize().dt.tz_localize(None).to_numpy(),
        "open": df["open"].to_numpy(), "high": df["high"].to_numpy(),
        "low": df["low"].to_numpy(), "close": df["close"].to_numpy(),
        "volume": df["volume"].to_numpy(),
    })
    return out


def hr(title: str) -> None:
    print("\n" + "=" * 78 + f"\n{title}\n" + "=" * 78)


def audit_full(inst: str, raw: pd.DataFrame) -> None:
    """Whole-file (24h) structural checks on the raw Databento bars (ET frame)."""
    hr(f"{inst}  RAW FILE STRUCTURE  ({RAW[inst].name})")
    n = len(raw)
    print(f"rows={n:,}  {raw['et'].min()} -> {raw['et'].max()}")
    print(f"contracts (instrument_id): {raw['iid'].nunique()}  rolls={int((raw['iid'].diff()!=0).sum())-1}")

    # 1. monotonic, unique timestamps
    ts = raw["et"]
    print(f"monotonic increasing ts: {ts.is_monotonic_increasing}")
    dup = ts.duplicated().sum()
    print(f"duplicate minute timestamps: {dup}")

    # 2. OHLC internal sanity
    o, h, l, c = raw["open"], raw["high"], raw["low"], raw["close"]
    bad_hilo = int((h < l).sum())
    bad_h = int((h < np.maximum(o, c)).sum())
    bad_l = int((l > np.minimum(o, c)).sum())
    nonpos = int((c <= 0).sum() + (o <= 0).sum() + (h <= 0).sum() + (l <= 0).sum())
    nan_ohlc = int(raw[["open", "high", "low", "close"]].isna().any(axis=1).sum())
    print(f"OHLC sanity: high<low={bad_hilo}  high<max(o,c)={bad_h}  "
          f"low>min(o,c)={bad_l}  nonpos={nonpos}  NaN={nan_ohlc}")

    # 3. timezone / session alignment: RTH volume share by ET hour. A correct ET
    #    frame puts the bulk of volume in 09:00-16:00 ET. This is the direct test
    #    of the "hours not adjusted in recent years" defect -> run it per-era.
    print("\ntimezone check — volume share by ET hour, by era "
          "(RTH 09:30-16:00 should dominate):")
    raw = raw.assign(yr=raw["et"].dt.year, hod=raw["et"].dt.hour)
    for lab, mask in [("2011-2015", raw["yr"] <= 2015),
                      ("2016-2020", (raw["yr"] >= 2016) & (raw["yr"] <= 2020)),
                      ("2021-2026", raw["yr"] >= 2021)]:
        sub = raw[mask]
        vh = sub.groupby("hod")["volume"].sum()
        rth_share = vh.loc[9:15].sum() / vh.sum()
        top = vh.sort_values(ascending=False).head(5).index.tolist()
        print(f"  {lab}: RTH(09-15h ET) vol share={rth_share:5.1%}  "
              f"top-5 ET hours={sorted(top)}")


def audit_rth(inst: str, raw: pd.DataFrame) -> pd.DataFrame:
    """RTH-session completeness + gap + spike audit. Returns per-session frame."""
    hr(f"{inst}  RTH SESSION COMPLETENESS & GAPS  (09:30-16:00 ET)")
    r = raw[(raw["tod"] >= RTH_START) & (raw["tod"] < RTH_END)].copy()
    r = r.sort_values("et").reset_index(drop=True)

    g = r.groupby("date")
    nb = g["et"].size()
    sess = pd.DataFrame({"bars": nb})
    # missing minutes = 390 - bars present (each session should have 390 1-min bars)
    sess["missing"] = FULL_RTH_BARS - sess["bars"]
    print(f"RTH sessions={len(sess)}  {sess.index.min().date()} -> {sess.index.max().date()}")
    print(f"median bars/session={int(nb.median())}  full(390)={int((nb==390).sum())}  "
          f"<350 bars={int((nb<350).sum())}  <200 bars={int((nb<200).sum())}")
    print(f"total missing RTH minutes (vs 390/session): {int(sess['missing'].clip(lower=0).sum()):,}")

    # largest intraday time gaps (consecutive-bar minute jumps) inside RTH — these
    # are where a single bar can span a big move (the "missing-data PnL spike").
    r["dmin"] = r.groupby("date")["et"].diff().dt.total_seconds() / 60.0
    biggap = r.groupby("date")["dmin"].max()
    worst = biggap.sort_values(ascending=False).head(10)
    print("\nworst 10 sessions by largest single intraday gap (minutes):")
    for d, gp in worst.items():
        print(f"  {pd.Timestamp(d).date()}  max_gap={gp:5.0f} min  bars={int(nb.loc[d])}")

    # 4. spike audit: extreme 1-min close-to-close returns WITHIN a session (a
    #    genuine data spike / bad print, or a gap-spanning bar). Report the tail.
    r["ret"] = r.groupby("date")["close"].pct_change()
    big = r.reindex(r["ret"].abs().sort_values(ascending=False).index).head(10)
    print("\ntop 10 largest 1-min intraday returns (bad-print / gap spikes):")
    for _, row in big.iterrows():
        print(f"  {row['et']}  ret={row['ret']:+.3%}  "
              f"close={row['close']:.2f}  prevgap={row['dmin']:.0f}min")
    return sess


def compare_old_new(inst: str, raw: pd.DataFrame, old: pd.DataFrame) -> None:
    """Head-to-head: what actually changed between old vendor data and Databento."""
    hr(f"{inst}  OLD vs NEW  (per-RTH-session join)")
    def rth_sess(df):
        r = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
        g = r.groupby("date")
        return pd.DataFrame({
            "bars": g["et"].size(),
            "open0930": r[r["tod"] == RTH_START].set_index("date")["open"],
            "close1559": r.sort_values("et").groupby("date").tail(1).set_index("date")["close"],
        })
    on, nn = rth_sess(old), rth_sess(raw)
    j = on.join(nn, lsuffix="_old", rsuffix="_new", how="outer")
    only_old = int(j["bars_new"].isna().sum())
    only_new = int(j["bars_old"].isna().sum())
    print(f"sessions: old={on.shape[0]}  new={nn.shape[0]}  "
          f"only_in_old={only_old}  only_in_new={only_new}")

    both = j.dropna(subset=["bars_old", "bars_new"]).copy()
    both["bars_diff"] = both["bars_new"] - both["bars_old"]
    print(f"common sessions={len(both)}  "
          f"identical 09:30 open={int(np.isclose(both['open0930_old'],both['open0930_new']).sum())}"
          f"/{len(both)}")

    # the recent-years hours defect: does the OLD 09:30 ET open price match the NEW
    # one? A timezone slip shifts the whole session, so the "09:30 open" in the old
    # frame is actually a different minute's price. Track the mismatch rate by year.
    both["yr"] = pd.to_datetime(both.index).year
    both["open_mismatch"] = ~np.isclose(both["open0930_old"].fillna(-1),
                                        both["open0930_new"].fillna(-2), rtol=0, atol=1e-6)
    by_yr = both.groupby("yr").agg(
        n=("open_mismatch", "size"),
        open_mismatch_rate=("open_mismatch", "mean"),
        mean_bars_old=("bars_old", "mean"),
        mean_bars_new=("bars_new", "mean"),
    )
    print("\nper-year: RTH 09:30-open mismatch rate (old vs new) + mean bars/session:")
    print(by_yr.to_string(float_format=lambda x: f"{x:8.3f}"))


def main() -> None:
    sessions = {}
    for inst in ("NQ", "ES"):
        raw = _to_et_raw(pd.read_parquet(
            RAW[inst], columns=["ts_event", "open", "high", "low", "close",
                                "volume", "instrument_id"]))
        audit_full(inst, raw)
        sessions[inst] = audit_rth(inst, raw)
        if OLD_PATHS[inst].exists():
            old = _to_et_old(pd.read_parquet(OLD_PATHS[inst]))
            compare_old_new(inst, raw, old)
    hr("SUMMARY")
    for inst, s in sessions.items():
        print(f"{inst}: {len(s)} RTH sessions, {int(s['bars'].sum()):,} RTH bars, "
              f"{int(s['missing'].clip(lower=0).sum()):,} missing minutes")


if __name__ == "__main__":
    main()
