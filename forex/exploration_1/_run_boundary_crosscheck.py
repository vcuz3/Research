"""Cross-vendor / cross-venue check of the :00 and :30 one-minute reversal effect.

The IBKR spot archive showed one-minute return lag-1 autocorrelation of about
-0.085 at minute :00 and -0.062 at :30 against a 60-minute median of -0.016,
which is what the RSI "scheduled clock" was sitting on. That could be real
round-clock order flow or an IBKR bar-construction artifact. This script repeats
the measurement on two independent sources:

  LSE  : tick-derived 1-second bars, EUR/USD + GBP/USD, 2009-09 to 2012.
         Different vendor AND a mostly non-overlapping period.
  CME  : Databento GLBX.MDP3 ohlcv-1m, 6E + 6B continuous front.
         Exchange-reported prints from a central limit order book.

Arms
  X1. Lag-1 autocorrelation of open-to-open one-minute returns by minute of hour.
  X2. Same on close-to-close, as a bar-construction robustness variant.
  X3. Full-range Spearman IC(RSI(14), signed forward 30-minute return) by
      half-hour phase - the direct replication of the ":29 is the best phase"
      result, rather than of its proposed mechanism.
  X4. Sampling diagnostics per minute of hour (row counts, and for LSE the tick
      density and the second-offset of the first tick in the minute), so a
      density artifact cannot masquerade as a microstructure effect.

Every return requires exactly contiguous minutes; CME additionally requires the
same contract on both ends so no roll jump enters a return.
"""

from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pyarrow.parquet as pq
from scipy.signal import lfilter
from scipy.stats import spearmanr

ROOT = Path(__file__).resolve().parent
RESEARCH = ROOT.parent.parent
LSE_DIR = RESEARCH / "forex" / "data" / "lse" / "fx"
CME_DIR = RESEARCH / "futures" / "data" / "databento"
OUT = ROOT / "boundary_crosscheck_results.json"

RSI_LENGTH = 14
HORIZON = 30
INTERVAL = 30

LSE_PAIRS = {"EURUSD": "EUR_USD", "GBPUSD": "GBP_USD"}
CME_FILES = {
    "6E": "6E_ohlcv-1m_6Ev0_20100606_20260728.parquet",
    "6B": "6B_ohlcv-1m_6Bv0_20100606_20260728.parquet",
}
PIP = {"EURUSD": 1e-4, "GBPUSD": 1e-4, "6E": 1e-4, "6B": 1e-4}


# ------------------------------------------------------------------ loaders
def load_lse_minutes(key: str) -> pd.DataFrame:
    """Aggregate sparse 1-second bars into a 1-minute grid. No forward fill."""
    stem = LSE_PAIRS[key]
    files = sorted(LSE_DIR.glob(f"fx_{stem}_1s*.parquet"))
    frames = []
    for path in files:
        tab = pq.read_table(path, columns=["ts", "open", "close"]).to_pandas()
        tab["minute"] = tab.ts.dt.floor("min")
        tab["sec"] = tab.ts.dt.second
        g = tab.groupby("minute", sort=True)
        frames.append(
            pd.DataFrame(
                {
                    "open": g.open.first(),
                    "close": g.close.last(),
                    "ticks": g.size(),
                    "first_sec": g.sec.first(),
                }
            )
        )
        del tab, g
    out = pd.concat(frames)
    out = out.groupby(level=0).agg(
        {"open": "first", "close": "last", "ticks": "sum", "first_sec": "first"}
    )
    out.index.name = "time"
    return out.reset_index()


def load_cme_minutes(key: str) -> pd.DataFrame:
    tab = pq.read_table(
        CME_DIR / CME_FILES[key], columns=["ts_event", "open", "close", "symbol", "volume"]
    ).to_pandas()
    tab = tab.rename(columns={"ts_event": "time"}).sort_values("time").reset_index(drop=True)
    tab["ticks"] = tab.volume.astype(float)
    tab["first_sec"] = np.nan
    return tab[["time", "open", "close", "symbol", "ticks", "first_sec"]]


# ------------------------------------------------------------------ analysis
def minute_returns(frame: pd.DataFrame, price_col: str, pip: float) -> pd.DataFrame:
    t = frame.time
    nxt_ok = np.array(t.shift(-1).eq(t + pd.Timedelta(minutes=1)).to_numpy(), copy=True)
    if "symbol" in frame:
        nxt_ok &= np.asarray(frame.symbol.shift(-1).eq(frame.symbol).to_numpy())
    px = frame[price_col].to_numpy(dtype=float)
    ret = np.full(len(px), np.nan)
    ret[:-1] = (px[1:] - px[:-1]) / pip
    ret[~nxt_ok] = np.nan
    prev = np.r_[np.nan, ret[:-1]]
    prev[np.r_[False, ~nxt_ok[:-1]]] = np.nan
    return pd.DataFrame(
        {
            "time": t,
            "min_of_hour": (t.dt.hour * 60 + t.dt.minute) % 60,
            "ret": ret,
            "prev_ret": prev,
        }
    )


def ac1_by_minute(rets: pd.DataFrame, label: str) -> dict:
    rows = []
    for m, cell in rets.groupby("min_of_hour"):
        z = cell[["prev_ret", "ret"]].dropna()
        rows.append({"min_of_hour": int(m), "n": int(len(z)), "ac1": float(z.prev_ret.corr(z.ret))})
    tab = pd.DataFrame(rows).set_index("min_of_hour").sort_index()
    med = float(tab.ac1.median())
    order = tab.ac1.rank(method="min")  # 1 = most negative
    out = {"label": label, "median_ac1": med, "table": tab.reset_index().to_dict("records")}
    print(f"    median ac1 across 60 minutes: {med:+.5f}   (rows/minute ~{int(tab.n.median())})")
    for m in [0, 30]:
        excess = tab.loc[m, "ac1"] - med
        z = excess * np.sqrt(tab.loc[m, "n"])
        print(f"      minute :{m:02d}  ac1={tab.loc[m,'ac1']:+.5f}  excess={excess:+.5f}  "
              f"z_vs_median={z:+.2f}  rank={int(order.loc[m])}/60  n={int(tab.loc[m,'n'])}")
        out[f"minute_{m:02d}"] = {"ac1": float(tab.loc[m, "ac1"]), "excess": float(excess),
                                  "z_vs_median": float(z), "rank": int(order.loc[m]),
                                  "n": int(tab.loc[m, "n"])}
    top = tab.ac1.sort_values().index.tolist()[:6]
    print(f"      six most negative minutes: {top}")
    out["six_most_negative"] = [int(x) for x in top]
    return out


def sma_seeded(values, starts, ends, length, alpha):
    out = np.full(len(values), np.nan)
    for s, e in zip(starts, ends):
        x = values[s:e]
        if len(x) < length:
            continue
        seed = float(np.mean(x[:length]))
        out[s + length - 1] = seed
        if len(x) > length:
            f, _ = lfilter([alpha], [1.0, -(1.0 - alpha)], x[length:], zi=[(1.0 - alpha) * seed])
            out[s + length:e] = f
    return out


def wilder_rsi(close, contiguous, length):
    starts = np.flatnonzero(~contiguous)
    ends = np.r_[starts[1:], len(close)]
    d = np.diff(close, prepend=close[0])
    d[starts] = 0.0
    ag = sma_seeded(np.clip(d, 0, None), starts, ends, length, 1.0 / length)
    al = sma_seeded(np.clip(-d, 0, None), starts, ends, length, 1.0 / length)
    rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al > 0)
    rsi = 100 - 100 / (1 + rs)
    rsi[(al == 0) & (ag == 0)] = 50
    rsi[(al == 0) & (ag > 0)] = 100
    return rsi


def ic_by_phase(frame: pd.DataFrame, pip: float, label: str) -> dict:
    t = frame.time
    prev_ok = np.array(t.diff().eq(pd.Timedelta(minutes=1)).to_numpy(), copy=True)
    if "symbol" in frame:
        prev_ok &= np.asarray(frame.symbol.eq(frame.symbol.shift(1)).to_numpy())
    rsi = wilder_rsi(frame.close.to_numpy(dtype=float), prev_ok, RSI_LENGTH)
    entry = frame.open.shift(-1).astype(float)
    exit_ = frame.open.shift(-(1 + HORIZON)).astype(float)
    exact = t.shift(-1).eq(t + pd.Timedelta(minutes=1)) & t.shift(-(1 + HORIZON)).eq(
        t + pd.Timedelta(minutes=1 + HORIZON)
    )
    if "symbol" in frame:
        exact &= frame.symbol.shift(-(1 + HORIZON)).eq(frame.symbol)
    fwd = ((exit_ - entry) / pip).where(exact)
    z = pd.DataFrame(
        {"phase": (t.dt.hour * 60 + t.dt.minute) % INTERVAL, "rsi": rsi, "fwd": fwd}
    ).dropna()
    ics = {int(p): float(spearmanr(c.rsi, c.fwd).statistic) for p, c in z.groupby("phase")}
    arr = np.array([ics[p] for p in range(INTERVAL)])
    rank29 = int((arr < arr[29]).sum()) + 1
    print(f"    phase29={arr[29]:+.5f}  median={np.median(arr):+.5f}  min={arr.min():+.5f} "
          f"(phase {int(arr.argmin())})  sd={arr.std():.5f}  "
          f"rank_of_29 (most negative=1) = {rank29}/30   n/phase~{len(z)//INTERVAL}")
    return {"label": label, "ic_by_phase": ics, "rank_of_29": rank29,
            "median": float(np.median(arr)), "sd": float(arr.std()), "n": int(len(z))}


def sampling_diag(frame: pd.DataFrame, label: str) -> dict:
    d = frame.copy()
    d["min_of_hour"] = (d.time.dt.hour * 60 + d.time.dt.minute) % 60
    g = d.groupby("min_of_hour").agg(n=("open", "size"), ticks=("ticks", "mean"),
                                     first_sec=("first_sec", "mean"))
    print(f"    rows/minute: median {int(g.n.median())}  :00 {int(g.n.loc[0])}  :30 {int(g.n.loc[30])}")
    print(f"    ticks/minute: median {g.ticks.median():.1f}  :00 {g.ticks.loc[0]:.1f}  :30 {g.ticks.loc[30]:.1f}")
    if g.first_sec.notna().any():
        print(f"    first-tick second offset: median {g.first_sec.median():.2f}  "
              f":00 {g.first_sec.loc[0]:.2f}  :30 {g.first_sec.loc[30]:.2f}")
    return {"label": label, "table": g.reset_index().to_dict("records")}


def main() -> None:
    results = {}
    jobs = [("LSE", k, load_lse_minutes) for k in LSE_PAIRS] + \
           [("CME", k, load_cme_minutes) for k in CME_FILES]
    for source, key, loader in jobs:
        name = f"{source}/{key}"
        print(f"\n================ {name} ================", flush=True)
        frame = loader(key)
        print(f"  rows={len(frame)}  {frame.time.min()} -> {frame.time.max()}")
        pip = PIP[key]
        out = {"rows": int(len(frame)), "first": str(frame.time.min()), "last": str(frame.time.max())}

        print("\n  [X1] open-to-open one-minute return ac1 by minute of hour")
        out["X1_open"] = ac1_by_minute(minute_returns(frame, "open", pip), f"{name}/open")

        print("\n  [X2] close-to-close variant")
        out["X2_close"] = ac1_by_minute(minute_returns(frame, "close", pip), f"{name}/close")

        print("\n  [X3] full-range RSI mean-reversion IC by half-hour phase")
        out["X3_ic_phase"] = ic_by_phase(frame, pip, name)

        print("\n  [X4] sampling diagnostics by minute of hour")
        out["X4_sampling"] = sampling_diag(frame, name)

        # era split for CME, which spans the IBKR window
        if source == "CME":
            sub = frame.loc[(frame.time >= "2012-01-01") & (frame.time < "2024-01-01")]
            print("\n  [X1b] CME restricted to 2012-2023 (the IBKR comparison window)")
            out["X1b_open_2012_2023"] = ac1_by_minute(minute_returns(sub, "open", pip), f"{name}/2012-2023")

        results[name] = out
        del frame

    OUT.write_text(json.dumps(results, indent=2, default=str), encoding="utf-8")
    print(f"\nWrote {OUT}")


if __name__ == "__main__":
    main()
