"""
Volume-weighted Noise-Area band variants, for the A/B against the equal-weight
baseline (core.data.noise_bands). Two ideas the user proposed:

  Variant 2  vwap_sigma_bands():  band = VWAP +/- mult * sigma_vw, where sigma_vw
             is the CUMULATIVE, CAUSAL volume-weighted std of typical price around
             the running session VWAP. The band is centered on VWAP (so it DRIFTS
             intraday, unlike the static baseline band) and its width is set by
             where volume actually traded. `mult` is fixed by the caller to
             width-match the baseline (so we test band SHAPE, not width).

  Variant 3  noise_bands_volshare(): identical structure to the baseline band
             (same max/min(open, prior_close) reference), but the cross-day mean
             of the excursion is WEIGHTED by each historical day's volume SHARE at
             that time-of-day. A historical day's excursion at tod counts more if a
             larger fraction of that day's volume printed at tod. `scale` is fixed
             by the caller to width-match the baseline.

Both are fully causal (CLAUDE.md rule 7/8):
  * sigma_vw at bar k uses only bars 0..k of the same session.
  * volume SHARE of a historical day uses that day's OWN completed session total,
    and only strictly-prior sessions feed the current day's band (shift 1).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from .data import RTH_START


# ----------------------------------------------------------------------------
# Variant 2: VWAP +/- mult * volume-weighted sigma (cumulative, causal)
# ----------------------------------------------------------------------------
def vwap_sigma_bands(df: pd.DataFrame, mult: float) -> pd.DataFrame:
    """
    band[d, tod] = vwap[d, tod] +/- mult * sigma_vw[d, tod]

    sigma_vw[k] = sqrt( sum_{i<=k} v_i (tp_i - vwap_k)^2 / sum_{i<=k} v_i )
                = sqrt( (sum v_i tp_i^2)/(sum v_i) - vwap_k^2 )   (causal, all i<=k)

    Returns long frame: date, tod, sigma (=sigma_vw), upper, lower.
    """
    d = df.sort_values(["date", "tod"]).reset_index(drop=True)
    tp = ((d["high"] + d["low"] + d["close"]) / 3.0).to_numpy()
    v = d["volume"].astype("float64").to_numpy()
    g = d.groupby("date", sort=False)
    cum_v = g["volume"].cumsum().astype("float64").to_numpy()
    cum_vtp = pd.Series(v * tp, index=d.index).groupby(d["date"]).cumsum().to_numpy()
    cum_vtp2 = pd.Series(v * tp * tp, index=d.index).groupby(d["date"]).cumsum().to_numpy()
    vwap = cum_vtp / cum_v
    var = cum_vtp2 / cum_v - vwap * vwap
    sig = np.sqrt(np.clip(var, 0.0, None))

    out = pd.DataFrame({
        "date": d["date"].to_numpy(),
        "tod": d["tod"].to_numpy(),
        "sigma": sig,
        "upper": vwap + mult * sig,
        "lower": vwap - mult * sig,
    })
    return out


# ----------------------------------------------------------------------------
# Variant 3: volume-share-weighted cross-day excursion profile
# ----------------------------------------------------------------------------
def noise_bands_volshare(df: pd.DataFrame, lookback: int,
                         scale: float = 1.0) -> pd.DataFrame:
    """
    Same reference and shape as core.data.noise_bands, but the cross-day mean of
    the excursion is weighted by each historical day's volume SHARE at that tod:

      move[d, tod]   = |close[d, tod] / open[d, 09:30] - 1|
      vshare[d, tod] = volume[d, tod] / (that day's completed session total volume)
      sigma[d, tod]  = sum_{prior lb} vshare*move  /  sum_{prior lb} vshare
                       (strictly prior sessions; shift 1)
      sigma          = sigma * scale     (width-match knob, fixed by caller)
      upper/lower     = max/min(open, prior_close) * (1 +/- sigma)

    Returns long frame: date, tod, sigma, upper, lower, rth_open, prior_close.
    """
    opens = df[df["tod"] == RTH_START].set_index("date")["open"]
    if opens.empty:
        raise ValueError("no 09:30 open bars found")
    last = df.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = df["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)

    cm = df.pivot_table(index="date", columns="tod", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    vm = df.pivot_table(index="date", columns="tod", values="volume", aggfunc="sum")
    vm = vm.reindex(index=dates, columns=cm.columns)
    o0 = opens.reindex(dates)

    move = (cm.div(o0, axis=0) - 1.0).abs()
    day_total = vm.sum(axis=1)                       # each day's OWN completed total
    vshare = vm.div(day_total, axis=0)

    # weighted rolling mean over the strictly-prior `lookback` sessions
    num = (vshare * move).shift(1).rolling(lookback, min_periods=lookback).sum()
    den = vshare.shift(1).rolling(lookback, min_periods=lookback).sum()
    sigma = (num / den) * scale

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["date", "tod", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="date")
    long = long.merge(prior_close.rename("prior_close"), on="date")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long


def median_halfwidth(bands: pd.DataFrame) -> float:
    """Median band half-width in POINTS = median( (upper - lower) / 2 )."""
    return float(((bands["upper"] - bands["lower"]) / 2.0).median())
