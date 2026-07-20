"""
Load GC (COMEX Gold) 1-minute RTH bars and build the per-session cumulative,
CAUSAL, volume-weighted VWAP and its standard-deviation bands for the VWAP
mean-reversion (fade) strategy.

This is a DIFFERENT strategy from `futures/gc/noise_vwap` (which fades/breaks a
same-time-of-day "noise area" band). Here the band is the classic VWAP ±kσ
envelope, where σ is the volume-weighted dispersion of typical price around the
running session VWAP. Shared with the noise_vwap project: the raw clean parquet,
the RTH window convention, and the contract economics.

Conventions:
  * Source parquet is `futures/gc/noise_vwap/data/GC_1m_clean.parquet` (Databento
    `GC.v.0` raw continuous 1m; `ts_utc` tz-aware UTC). We reuse the already-built,
    already-audited clean file rather than duplicate 78 MB. Provenance and the
    build script live in the noise_vwap project (`core/build_clean.py`).
  * RTH cash session = 09:30..16:00 ET (equity session, same as the noise_vwap
    port; a gold-native window is a separate research question, not the baseline).
  * VWAP is cumulative WITHIN the RTH session, reset each day, from typical price
    tp=(H+L+C)/3 volume-weighted. Causal: bar t uses only bars 0..t.
  * sigma[t] = sqrt( (sum_k v_k tp_k^2)/(sum_k v_k) - vwap_t^2 ), the volume-
    weighted std of typical price about the running VWAP, cumulative and causal.
    Band(k)[t] = vwap_t ± k*sigma_t. No lookahead: everything is elapsed-to-date.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from numba import njit
from pathlib import Path

# reuse the audited clean parquet from the sibling noise_vwap project
DATA = Path(__file__).resolve().parents[2] / "noise_vwap" / "data"
PATHS = {"GC": DATA / "GC_1m_clean.parquet"}
# 1-second RTH file built by core.build_clean_1s in the shared GC data dir.
DATA_1S = Path(__file__).resolve().parents[2] / "data"
PATHS_1S = {"GC": DATA_1S / "GC_1s_rth.parquet"}

RTH_START = 9 * 60 + 30   # 09:30 ET (tod, minutes from midnight ET)
RTH_END = 16 * 60         # 16:00 ET (tod, exclusive)

# COMEX Gold (GC): 100 troy oz contract, min tick 0.10 = $10, 1 point = $100.
# (The project trades MGC micro-gold, 1/10 notional; economics scale by 10.)
TICK = {"GC": 0.10}
TICK_VALUE = {"GC": 10.0}       # $ / tick / contract
POINT_VALUE = {"GC": 100.0}     # $ / point / contract

MIN_BARS = 350   # a session must be near-complete to be usable


@njit(cache=True)
def _session_features(codes: np.ndarray, high: np.ndarray, low: np.ndarray,
                      close: np.ndarray, volume: np.ndarray):
    """Build cumulative features in one native pass over session-sorted bars."""
    n = codes.size
    vwap = np.empty(n, np.float64)
    sigma = np.empty(n, np.float64)
    bar_i = np.empty(n, np.int64)
    previous = -1
    cv = 0.0
    ctpv = 0.0
    ctp2v = 0.0
    bi = 0
    for i in range(n):
        code = codes[i]
        if code != previous:
            previous = code
            cv = 0.0
            ctpv = 0.0
            ctp2v = 0.0
            bi = 0
        tp = (high[i] + low[i] + close[i]) / 3.0
        vol = volume[i]
        cv += vol
        ctpv += tp * vol
        ctp2v += tp * tp * vol
        w = ctpv / cv
        var = ctp2v / cv - w * w
        vwap[i] = w
        sigma[i] = np.sqrt(var) if var > 0.0 else 0.0
        bar_i[i] = bi
        bi += 1
    return vwap, sigma, bar_i


def _add_vwap_sigma(df: pd.DataFrame) -> pd.DataFrame:
    """Attach the cumulative causal session VWAP and volume-weighted sigma.
    `df` must be time-sorted with a `date` session key. Adds vwap, sigma, bar_i."""
    codes, _ = pd.factorize(df["date"], sort=False)
    vwap, sigma, bar_i = _session_features(
        codes.astype(np.int64, copy=False),
        df["high"].to_numpy(np.float64, copy=False),
        df["low"].to_numpy(np.float64, copy=False),
        df["close"].to_numpy(np.float64, copy=False),
        df["volume"].to_numpy(np.float64, copy=False))
    df["vwap"] = vwap
    df["sigma"] = sigma
    df["bar_i"] = bar_i
    return df


def _load(inst: str, path: Path, min_bars: int) -> pd.DataFrame:
    """Common loader: read a clean parquet, place the ET clock, filter to RTH and
    near-complete sessions, attach VWAP/sigma. Works for 1m or 1s files."""
    # Read only columns used downstream. On the 39.6M-row 1s archive, avoiding
    # unused flags and a second full-frame copy materially reduces peak memory.
    columns = ["ts_utc", "symbol", "open", "high", "low", "close", "volume"]
    df = pd.read_parquet(path, columns=columns)

    # Pandas' per-row timezone conversion is disproportionately expensive at 1s.
    # RTH never straddles an ET offset transition, so determine the DST-correct
    # UTC->ET offset once per UTC date (~6k values), then broadcast by integer day.
    utc_ns = df["ts_utc"].array.asi8
    day_ns = 86_400_000_000_000
    utc_day = np.floor_divide(utc_ns, day_ns)
    days, day_code = np.unique(utc_day, return_inverse=True)
    day_ts = pd.to_datetime(days, unit="D", utc=True).as_unit("ns")
    local_day_ts = day_ts.tz_convert("America/New_York").tz_localize(None)
    offsets_ns = local_day_ts.asi8 - day_ts.asi8
    local_ns = utc_ns + offsets_ns[day_code]
    local_sec = np.floor_divide(local_ns, 1_000_000_000)
    tsec = np.mod(local_sec, 86_400).astype(np.int32)

    # Keep the historical `et` representation (timezone-naive UTC instants) for
    # schema compatibility; session keys and clocks below are ET-local.
    df["et"] = utc_ns.view("datetime64[ns]")
    df["tod"] = (tsec // 60).astype(np.int16)
    df["tsec"] = tsec
    df["date"] = np.floor_divide(local_ns, day_ns).astype("datetime64[D]").astype("datetime64[ns]")
    df = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
    df = df.sort_values("et").reset_index(drop=True)
    codes, _ = pd.factorize(df["date"], sort=False)
    sizes = np.bincount(codes)
    keep = sizes[codes] >= min_bars
    df = df.loc[keep].reset_index(drop=True)
    df = _add_vwap_sigma(df)
    # These identifiers repeat tens of millions of times; categoricals avoid an
    # object pointer per row while preserving normal equality/grouping behavior.
    df["symbol"] = df["symbol"].astype("category")
    df["inst"] = pd.Categorical.from_codes(
        np.zeros(len(df), dtype=np.int8), categories=[inst])
    return df[["et", "date", "tod", "tsec", "bar_i", "inst", "symbol",
               "open", "high", "low", "close", "volume", "vwap", "sigma"]]


def load_rth(inst: str) -> pd.DataFrame:
    """RTH 1-MINUTE bars with the ET clock (tod/tsec), causal session VWAP and
    volume-weighted sigma. One row per bar, time-sorted."""
    return _load(inst, PATHS[inst], MIN_BARS)


# a 1s RTH session is far from fully populated (gold trades sporadically at 1s);
# require a materially-traded session, well under the ~23400 theoretical seconds.
MIN_BARS_1S = 3000


def load_rth_1s(inst: str) -> pd.DataFrame:
    """RTH 1-SECOND bars (built by core.build_clean_1s) with the ET clock, causal
    1s session VWAP and volume-weighted sigma. Same schema as load_rth, so the
    engine runs on it unchanged; the finer path makes fills/stops observable
    rather than adversely assumed (rule 3)."""
    return _load(inst, PATHS_1S[inst], MIN_BARS_1S)


if __name__ == "__main__":
    d = load_rth("GC")
    print("GC bars", len(d), "sessions", d["date"].nunique(),
          d["date"].min().date(), "->", d["date"].max().date())
    # sigma sanity at 10:00 (30 min in) — should be a small positive $ dispersion
    s10 = d[d["tod"] == 600]["sigma"]
    print(f"sigma@10:00 median={s10.median():.3f} pt  "
          f"(bands ±2sigma = ±{2*s10.median():.2f} pt / ${2*s10.median()*100:.0f})")
