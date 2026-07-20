"""
RTY (E-mini Russell 2000) session loader for the Noise-Area + VWAP momentum grid
studies.

Faithful port of `futures/nq/noise_vwap/core/session.py` (via the GC port); only
the data path and contract economics differ (project convention: keep parity with
the audited NQ code, port fixes from NQ).

This module serves the grid runner (`scripts/grid_wfo.py`) and the fast numba
engine (`core.engine2_nb`), which key on `sdate`/`mfo` rather than `date`/`tod`.

VWAP anchor (the grid's first axis) is a SINGLE-VARIABLE swap of the `vwap` column:
  * "rth"  -- cumulative VWAP reset at the 09:30 ET RTH open (the faithful
              baseline; identical to core.data.load_rth's vwap).
  * "eth"  -- cumulative VWAP reset at the 18:00 ET Globex open, accumulating the
              full overnight session up to each RTH bar. The RTH trading window,
              the noise bands, and the 30-min decision clock are UNCHANGED; only
              the VWAP series feeding the entry gate (close vs vwap) and the stop
              (max(band, vwap)) differs. This isolates the anchor and does NOT
              re-open the session-hours question (HYP-0001, already rejected).

Hygiene (CLAUDE.md):
  * VWAP / noise-sigma are cumulative-within-session or strictly-prior-lookback:
    no session total, no lookahead (rule 7). The ETH VWAP at an RTH bar uses only
    overnight+intraday bars at or before that bar (causal).
  * ATR is the mean prior-`atr_lb`-session RTH range in points, strictly shifted
    (causal, one-sided; NOT ticks) -- carried for engine2 compatibility.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
from pathlib import Path

# Shared instrument data lives at the common RTY parent (futures/rty/data), per
# RESEARCH_WORKFLOW; kept identical to core.data.DATA. parents[2] = futures/rty.
DATA = Path(__file__).resolve().parents[2] / "data"
PATHS = {"RTY": DATA / "RTY_1m_clean.parquet"}

RTH_START = 9 * 60 + 30   # 09:30 ET (tod)
RTH_END = 16 * 60         # 16:00 ET (tod, exclusive)

# E-mini Russell 2000 (RTY, CME): $50 x index, min tick 0.10 index pt = $5, 1 pt = $50.
TICK = {"RTY": 0.10}
POINT_VALUE = {"RTY": 50.0}

MIN_BARS_RTH = 350

# Noise-band coverage tolerance (rule 9a); kept identical to core.data.BAND_MIN_FRAC
# so the numba fast path and the audited engine build the SAME bands. Requiring all
# `lookback` prior sessions at a minute nulls the band whenever one is missing; on GC
# that can silently delete late-day decisions on a thin instrument. See
# reports/DATA_QUALITY.md.
BAND_MIN_FRAC = 0.9


def _base(inst: str) -> pd.DataFrame:
    df = pd.read_parquet(PATHS[inst])
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df["etdate"] = et.dt.normalize().dt.tz_localize(None).values
    # ETH trade-date: (ET + 6h).date -> 18:00 ET rolls into the NEXT session; the
    # whole RTH day (<=16:00 ET) stays with its own date. Standard CME Globex date.
    df["sdate_eth"] = (et + pd.Timedelta(hours=6)).dt.normalize().dt.tz_localize(None).values
    return df.sort_values("et").reset_index(drop=True)


def _cum_vwap(df: pd.DataFrame, key: str) -> np.ndarray:
    """Cumulative causal session VWAP (typical price, volume-weighted), grouped by
    `key`, over the rows of `df` in time order."""
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype("float64").to_numpy()
    cum_v = df.groupby(key)["volume"].cumsum().astype("float64").to_numpy()
    cum_tpv = pd.Series(tp.to_numpy() * v, index=df.index).groupby(df[key]).cumsum().to_numpy()
    return cum_tpv / cum_v


def load_rth(inst: str, vwap_anchor: str = "rth", atr_lb: int = 14) -> pd.DataFrame:
    """
    RTH-trading 1-min bars (09:30..16:00 ET) with a selectable VWAP anchor, in the
    schema the numba engine expects: sdate, mfo, is_rth, o/h/l/c/volume, vwap, atr.

    The band/clock/window are RTH regardless of anchor; only `vwap` changes:
      vwap_anchor="rth" -> VWAP reset at 09:30 ET  (baseline; matches core.data)
      vwap_anchor="eth" -> VWAP reset at 18:00 ET Globex open (overnight-inclusive)
    """
    b = _base(inst)
    if vwap_anchor == "eth":
        # cumulative over the full Globex session (all 24h bars in the ETH date),
        # computed BEFORE the RTH filter so the overnight volume is included.
        b = b.sort_values("et").reset_index(drop=True)
        b["vwap"] = _cum_vwap(b, "sdate_eth")
    elif vwap_anchor != "rth":
        raise ValueError(f"unknown vwap_anchor {vwap_anchor!r}")

    rth = b[(b["tod"] >= RTH_START) & (b["tod"] < RTH_END)].copy()
    rth = rth.sort_values("et").reset_index(drop=True)
    rth["sdate"] = rth["etdate"]
    rth["mfo"] = (rth["tod"] - RTH_START).astype(int)
    rth["is_rth"] = True

    # near-complete RTH sessions only (identical filter across anchors so both trade
    # the SAME session set -- the anchor is the only variable).
    nb = rth.groupby("sdate")["et"].transform("size")
    rth = rth[nb >= MIN_BARS_RTH].reset_index(drop=True)

    if vwap_anchor == "rth":
        rth["vwap"] = _cum_vwap(rth, "sdate")   # reset at the 09:30 open
    # for eth, vwap already carried from the full-session cumulation above.

    # causal ATR: prior-atr_lb-session mean RTH (high-low) range in points.
    rng = (rth.groupby("sdate")["high"].max() - rth.groupby("sdate")["low"].min()).sort_index()
    atr = rng.shift(1).rolling(atr_lb, min_periods=atr_lb).mean()
    rth["atr"] = rth["sdate"].map(atr).to_numpy()

    rth["inst"] = inst
    rth["bar_i"] = rth.groupby("sdate").cumcount().to_numpy()
    return rth[["et", "sdate", "tod", "mfo", "is_rth", "bar_i", "inst", "symbol",
                "open", "high", "low", "close", "volume", "vwap", "atr"]]


def load_rth_both(inst: str, atr_lb: int = 14) -> pd.DataFrame:
    """RTH-trading bars carrying BOTH vwap anchors (`vwap_rth`, `vwap_eth`) so the
    5.2M-row parquet is read once for the whole grid. Otherwise identical to
    load_rth. The grid selects the `vwap` column per anchor cell downstream."""
    b = _base(inst)
    b = b.sort_values("et").reset_index(drop=True)
    veth_full = _cum_vwap(b, "sdate_eth")           # overnight-inclusive, pre-RTH-filter
    b["vwap_eth"] = veth_full

    # Overnight ETH anchor per trade-date: cumulative typical-price*volume and volume
    # over the PRE-RTH bars of the Globex session (18:00..09:29 ET). This is the fixed
    # context the ETH VWAP carries into the RTH open; the Null-C rebuilds vwap_eth as
    # (ov + reshuffled-RTH-cumulative), preserving overnight info, destroying RTH order.
    pre = b[(b["tod"] >= 18 * 60) | (b["tod"] < RTH_START)].copy()
    tp_pre = (pre["high"] + pre["low"] + pre["close"]) / 3.0
    v_pre = pre["volume"].astype("float64")
    ov = pd.DataFrame({"sdate": pre["sdate_eth"].to_numpy(),
                       "ov_tpv": (tp_pre * v_pre).to_numpy(),
                       "ov_v": v_pre.to_numpy()}).groupby("sdate").sum()

    rth = b[(b["tod"] >= RTH_START) & (b["tod"] < RTH_END)].copy()
    rth = rth.sort_values("et").reset_index(drop=True)
    rth["sdate"] = rth["etdate"]
    rth["mfo"] = (rth["tod"] - RTH_START).astype(int)
    rth["is_rth"] = True
    nb = rth.groupby("sdate")["et"].transform("size")
    rth = rth[nb >= MIN_BARS_RTH].reset_index(drop=True)
    rth["vwap_rth"] = _cum_vwap(rth, "sdate")        # reset at 09:30

    rng = (rth.groupby("sdate")["high"].max() - rth.groupby("sdate")["low"].min()).sort_index()
    atr = rng.shift(1).rolling(atr_lb, min_periods=atr_lb).mean()
    rth["atr"] = rth["sdate"].map(atr).to_numpy()
    rth["ov_tpv"] = rth["sdate"].map(ov["ov_tpv"]).to_numpy()
    rth["ov_v"] = rth["sdate"].map(ov["ov_v"]).to_numpy()
    rth["inst"] = inst
    rth["bar_i"] = rth.groupby("sdate").cumcount().to_numpy()
    return rth[["et", "sdate", "tod", "mfo", "is_rth", "bar_i", "inst", "symbol",
                "open", "high", "low", "close", "volume",
                "vwap_rth", "vwap_eth", "ov_tpv", "ov_v", "atr"]]


def noise_bands(df: pd.DataFrame, lookback: int, k: float = 1.0) -> pd.DataFrame:
    """
    Same-time-of-day Noise-Area bands, keyed by (sdate, mfo), with a volatility
    multiplier `k` on the band half-width:

      move[d, mfo]  = |close[d, mfo] / open[d, 0] - 1|
      sigma[d, mfo] = mean of move over the prior `lookback` sessions (strictly prior)
      upper[d, mfo] = max(open[d,0], prior_close[d]) * (1 + k*sigma)
      lower[d, mfo] = min(open[d,0], prior_close[d]) * (1 - k*sigma)

    k=1.0 reproduces the faithful baseline band exactly. Returns long frame:
    sdate, mfo, sigma, upper, lower, rth_open, prior_close.
    """
    base = _base_bands(df, lookback)
    return scale_bands(base, k)


def _base_bands(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """Bands at k=1 plus the references needed to rescale by k without recomputing
    the rolling excursion mean (grid efficiency: one pivot per lookback)."""
    opens = df[df["mfo"] == 0].set_index("sdate")["open"]
    if opens.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    # Tolerate up to (1 - BAND_MIN_FRAC) of the trailing window missing at a minute
    # (rule 9a): average over the present prior sessions instead of nulling the band.
    min_obs = max(1, int(np.ceil(BAND_MIN_FRAC * lookback)))
    sigma = move.shift(1).rolling(lookback, min_periods=min_obs).mean()

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    long["hi_ref"] = np.maximum(long["rth_open"], long["prior_close"])
    long["lo_ref"] = np.minimum(long["rth_open"], long["prior_close"])
    return long


def scale_bands(base: pd.DataFrame, k: float) -> pd.DataFrame:
    """Apply the vol multiplier k to a `_base_bands` frame -> upper/lower bands."""
    out = base.copy()
    out["upper"] = out["hi_ref"] * (1.0 + k * out["sigma"])
    out["lower"] = out["lo_ref"] * (1.0 - k * out["sigma"])
    return out[["sdate", "mfo", "sigma", "upper", "lower", "rth_open", "prior_close"]]


def decision_mfos(period: int, max_mfo: int) -> list[int]:
    """Concretum clock at `period` min: decide at mfo = j*period - 1 (open counted
    as minute 1), exposure next bar. period=30, RTH -> [29,59,...,389]."""
    out = []
    j = 1
    while j * period - 1 <= max_mfo:
        out.append(j * period - 1)
        j += 1
    return out


if __name__ == "__main__":
    for anchor in ("rth", "eth"):
        d = load_rth("RTY", vwap_anchor=anchor)
        b = noise_bands(d, 90)
        print(f"RTY anchor={anchor}: bars={len(d)} sessions={d['sdate'].nunique()} "
              f"{d['sdate'].min().date()}->{d['sdate'].max().date()} "
              f"band_rows={len(b)} vwap[0]={d['vwap'].iloc[0]:.2f}")
