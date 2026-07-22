"""
Alternative Noise-Area band constructions (HYP-0012 diffusion-cone programme).

The faithful baseline band lives in `core/session.py::noise_bands`: a per-slot
EMPIRICAL mean of same-time-of-day absolute displacement from the open, over the
prior `lookback` sessions. This module holds re-castings of that construct that
keep the FIXED open anchor (prior work showed re-anchoring on VWAP kills the edge)
and change only the dispersion SHAPE. Each factory emits the SAME long frame the
engines consume:

    [sdate, mfo, sigma, upper, lower, rth_open, prior_close]

so `engine2.run(bars, bands, ...)` is unchanged. `core/session.py::noise_bands`
is never modified — the faithful baseline stays bit-exact.

Transform 1 — DIFFUSION CONE (√t).
  Under a driftless random walk, expected absolute displacement from the open
  grows as √(elapsed). The baseline re-estimates that shape independently at each
  of the 13 decision slots from thin same-slot samples. The cone replaces those
  per-slot means with ONE causal per-session volatility scalar and an analytic
  √t profile:

      sigma_cone[d, mfo] = sigma_session[d] * sqrt(mfo / M)          (M = last mfo)

  where sigma_session[d] is the mean over the prior `lookback` sessions of the
  full-session displacement |session_close / session_open - 1|. Because that
  scalar uses only the open (mfo==0) and the session's last close — both present
  in any near-complete session — the cone needs NO per-slot rolling window, so the
  Rule-9a `min_periods` per-slot coverage deletion (which silently drops decisions
  on thin slots) cannot occur.

  Calibration: for RTH the session's last bar IS mfo==M, so sigma_session[d]
  equals the baseline's FINAL-slot empirical sigma. The cone therefore matches the
  baseline band width at end-of-day by construction, and the test isolates HOW the
  width is redistributed across the day (√t vs the empirical per-slot shape), i.e.
  pure shape, not width (width is a known Sharpe-vs-capacity dial).
"""
from __future__ import annotations

import numpy as np
import pandas as pd


def session_vol(df: pd.DataFrame, lookback: int) -> pd.Series:
    """
    Causal per-session volatility scalar (indexed by sdate):

        disp[d]        = |session_close[d] / session_open[d] - 1|
        sigma_session  = mean of disp over the prior `lookback` sessions (shift 1)

    session_open = the mfo==0 bar's open; session_close = the last bar's close.
    Both exist in any near-complete session, so there is no per-slot coverage
    requirement (contrast the per-(date,tod) rolling mean in the baseline band,
    which nulls a whole slot when a single trailing session lacks that minute —
    the Rule-9a defect). Strictly prior (shift 1): no lookahead (rule 7).
    """
    o0 = df[df["mfo"] == 0].set_index("sdate")["open"].sort_index()
    cN = (df.sort_values("et").groupby("sdate").tail(1)
          .set_index("sdate")["close"].sort_index())
    disp = (cN / o0.reindex(cN.index) - 1.0).abs()
    return disp.shift(1).rolling(lookback, min_periods=lookback).mean()


def noise_bands_cone(df: pd.DataFrame, lookback: int) -> pd.DataFrame:
    """
    Diffusion-cone Noise-Area bands, keyed by (sdate, mfo). Same output columns as
    `core/session.py::noise_bands`, so the engine consumes it unchanged.

        sigma[d, mfo] = sigma_session[d] * sqrt(mfo / M)     (M = max mfo in df)
        upper[d, mfo] = max(open[d,0], prior_session_close[d]) * (1 + sigma)
        lower[d, mfo] = min(open[d,0], prior_session_close[d]) * (1 - sigma)

    The gap adjustment (max/min with the prior close) is identical to the baseline,
    so ONLY the sigma shape changes. Rows are emitted for every mfo present in df;
    a row is dropped only when sigma_session is undefined (the first `lookback`
    sessions) or the anchors are missing — never for a per-slot coverage gap.
    """
    sig_s = session_vol(df, lookback)

    o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
    if o0.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = o0.reindex(dates)
    sig_s = sig_s.reindex(dates)

    mfos = np.sort(df["mfo"].unique()).astype(int)
    M = float(mfos.max())
    if M <= 0:
        raise ValueError("degenerate mfo axis (max mfo <= 0)")
    shape = np.sqrt(mfos.astype(float) / M)          # 0 at the open, 1 at mfo==M

    cone = pd.DataFrame(np.outer(sig_s.to_numpy(dtype=float), shape),
                        index=pd.Index(dates, name="sdate"),
                        columns=pd.Index(mfos, name="mfo"))

    long = cone.stack().rename("sigma").reset_index()
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long.reset_index(drop=True)


def noise_bands_asymmetric(df: pd.DataFrame, lookback: int,
                           tilt: float = 1.0) -> pd.DataFrame:
    """
    Transform 3 — ASYMMETRIC (per-side) noise band. Same per-slot construction,
    lookback and `min_periods=lookback` coverage as the faithful baseline (so the
    decision-point coverage is identical), but the ONE symmetric dispersion
    statistic is split into a separate UP and DOWN half-width.

    The baseline sizes BOTH edges from sigma = mean(|move|), pooling up-day and
    down-day displacements. On a drift-asymmetric index the two half-distributions
    differ (NQ up-days are larger and more frequent), so the pooled width mis-sizes
    at least one edge. This band sizes each edge from its own causal SEMI-mean:

        move[d, mfo] = close[d, mfo] / open[d, 0] - 1          (SIGNED)
        up[d, mfo]   = mean_{prior lb} max(move,  0)           (up   semi-mean)
        dn[d, mfo]   = mean_{prior lb} max(-move, 0)           (down semi-mean)

    By linearity over the same window, up + dn == mean(|move|) == the baseline
    sigma IDENTICALLY. The per-side half-widths are a tilt-blend from the baseline
    toward the full empirical split:

        sigma_up   = sigma + tilt*(2*up - sigma)   (= sigma(1-tilt) + 2*tilt*up)
        sigma_down = sigma + tilt*(2*dn - sigma)   (= sigma(1-tilt) + 2*tilt*dn)

    The TOTAL half-width budget is conserved for EVERY tilt:
        sigma_up + sigma_down == 2*sigma  (all tilt).
    So this is a PURE up/down REDISTRIBUTION of the baseline width, never a
    width/capacity dial (that confound killed EXP-0010/0012/0021). tilt=0 is the
    baseline BIT-EXACT (sigma_up == sigma_down == sigma); tilt=1 is the full
    empirical asymmetric band (sigma_up = 2*up, sigma_down = 2*dn); tilt>1 over-
    tilts (extrapolates the asymmetry). Per-side sigmas are floored at 0 so an
    over-tilt can zero a side but never invert the band.

        upper[d,mfo] = max(open[d,0], prior_close[d]) * (1 + sigma_up)
        lower[d,mfo] = min(open[d,0], prior_close[d]) * (1 - sigma_down)

    Same gap adjustment (max/min with the prior close) and same output columns as
    `core/session.py::noise_bands`, so `engine2.run` consumes it unchanged (the
    engine reads `upper`/`lower` directly and never re-derives them from `sigma`;
    the emitted `sigma` here is the conserved symmetric baseline sigma, for
    diagnostics only).
    """
    o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
    if o0.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = o0.reindex(dates)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    move = cm.div(o0, axis=0) - 1.0                       # SIGNED move
    up_semi = move.clip(lower=0.0)                        # max(move, 0)
    dn_semi = (-move).clip(lower=0.0)                     # max(-move, 0)
    roll = lambda s: s.shift(1).rolling(lookback, min_periods=lookback).mean()
    up = roll(up_semi)
    dn = roll(dn_semi)
    sigma = up + dn                                       # == mean(|move|), baseline
    sig_up = (sigma + tilt * (2.0 * up - sigma)).clip(lower=0.0)
    sig_dn = (sigma + tilt * (2.0 * dn - sigma)).clip(lower=0.0)

    def _stack(mat: pd.DataFrame, name: str) -> pd.DataFrame:
        return mat.stack().rename(name).reset_index().set_axis(
            ["sdate", "mfo", name], axis=1)

    long = _stack(sigma, "sigma")
    long = long.merge(_stack(sig_up, "sig_up"), on=["sdate", "mfo"])
    long = long.merge(_stack(sig_dn, "sig_dn"), on=["sdate", "mfo"])
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sig_up"])
    long["lower"] = lo_ref * (1.0 - long["sig_dn"])
    return long.reset_index(drop=True)


def noise_bands_surround(df: pd.DataFrame, hist: int, w: int) -> pd.DataFrame:
    """
    SURROUND-SMOOTHED noise band (HYP-0016). Same open anchor, gap adjustment and
    output columns as `core/session.py::noise_bands`; changes ONLY how the per-slot
    dispersion sigma is estimated.

    The baseline estimates sigma[d, mfo] from ONE thin same-time-of-day sample per
    prior day (the |move| at exactly `mfo`), averaged over the prior `lookback`
    (=90) sessions. That is a high-variance per-slot estimator, so it needs a long,
    lagging history. This estimator instead POOLS the local minute neighbourhood on
    each prior day before averaging over history, trading a little cross-slot bias
    for much lower variance so a SHORT (more adaptive) history becomes usable:

        move[p, j]          = |close[p, j] / open[p, 0] - 1|
        smooth_move[p, mfo] = mean over j in [mfo-w, mfo+w] of move[p, j]   (per day)
        sigma[d, mfo]       = mean over the prior `hist` sessions of smooth_move[·, mfo]

    The surround window is symmetric, CENTER-INCLUDED (2*w+1 minutes), and truncated
    at the session edges: at mfo==0 it spans [0, w] (center + forward only), i.e.
    "at the open we only average forward candles". `w` is a half-width (w=5 -> +/-5
    min). The forward minutes come only from prior, fully-completed sessions (the
    shift(1)), so using a later minute of a finished day is NOT lookahead (rule 7).

    Because both steps are plain averages this equals one mean over the box
    { prior `hist` sessions } x { j in [mfo-w, mfo+w] } of |move|. w=0 (no surround)
    reduces to `noise_bands(df, hist)` exactly. Note this changes the band WIDTH
    (the local move profile rises over the session, so a symmetric window over a
    convex profile shifts the level, most near the open) -- width is a known
    Sharpe-vs-capacity dial (EXP-0021), so read gross-per-trade and trade count, not
    Sharpe alone.
    """
    if hist < 1 or w < 0:
        raise ValueError(f"require hist>=1 and w>=0, got hist={hist}, w={w}")
    o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
    if o0.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = o0.reindex(dates)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    # full contiguous minute axis so a +/-w COLUMN window is exactly +/-w MINUTES
    full_mfo = np.arange(int(df["mfo"].min()), int(df["mfo"].max()) + 1)
    cm = cm.reindex(columns=full_mfo)
    move = (cm.div(o0, axis=0) - 1.0).abs()

    # 1) smooth across the local minute window WITHIN each day (center included,
    #    edge-truncated). Rolling over the minute axis (columns) via transpose.
    win = 2 * w + 1
    smooth = move.T.rolling(win, center=True, min_periods=1).mean().T
    # 2) average the smoothed profile over the prior `hist` sessions (strictly prior)
    sigma = smooth.shift(1).rolling(hist, min_periods=hist).mean()

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long.reset_index(drop=True)


def noise_bands_quantile(df: pd.DataFrame, lookback: int, q: float,
                         scale: float = 1.0) -> pd.DataFrame:
    """
    Transform 2 — QUANTILE envelope. Same per-slot construction and coverage as the
    faithful baseline, but the trailing same-time-of-day dispersion is the qth
    PERCENTILE of |move| instead of its MEAN:

        sigma[d, mfo] = quantile_q(|move[d-i, mfo]| : i=1..lookback) * scale

    "Above the noise area" then means literally "price has moved further than on
    (100q)% of comparable days by this time." Because it stays a per-slot rolling
    statistic (same `min_periods=lookback`), it PRESERVES the empirical intraday
    shape — including the super-diffusive morning the diffusion cone missed
    (EXP-0020) — and matches the baseline's coverage exactly.

    `scale` is a fixed multiplier used by the study to hold MEDIAN band width equal
    to the mean band, isolating the distribution-SHAPE effect (robustness to outlier
    trend days in the trailing window) from the raw width/capacity dial that a
    higher q would otherwise introduce. scale=1.0 is the raw quantile band.
    """
    if not 0.0 < q < 1.0:
        raise ValueError(f"q must be in (0, 1), got {q}")
    o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
    if o0.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = o0.reindex(dates)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()
    sigma = move.shift(1).rolling(lookback, min_periods=lookback).quantile(q) * scale

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long.reset_index(drop=True)


def laplace_weights(mu: float, b: float, lookback: int) -> np.ndarray:
    """One-/two-sided LAPLACE recency kernel over trailing session lag k=1..lookback.

        w_k = exp( -|k - mu| / b ),   k = 1 (most recent prior session) .. lookback

    `mu` is the center-of-mass lag (peak weight sits at k=mu); `b` is the scale
    (larger b = slower decay = flatter, more history-like). Two limits anchor it:
      * mu=1, small b  -> pure one-sided recency (weight collapses onto k=1);
      * b -> inf        -> uniform weights over 1..lookback == the FLAT mean band.
    Returns the raw (un-normalized) weight vector, w[0] == the k=1 (latest) weight.
    """
    if lookback < 1:
        raise ValueError(f"lookback must be >= 1, got {lookback}")
    if mu < 1:
        raise ValueError(f"mu (center-of-mass lag) must be >= 1, got {mu}")
    if not (b > 0):
        raise ValueError(f"b (scale) must be > 0, got {b}")
    k = np.arange(1, lookback + 1, dtype=float)
    if not np.isfinite(b):
        return np.ones_like(k)
    return np.exp(-np.abs(k - mu) / b)


def noise_bands_laplace(df: pd.DataFrame, mu: float, b: float, lookback: int,
                        scale: float = 1.0) -> pd.DataFrame:
    """
    LAPLACE-WEIGHTED noise band (HYP-0020). Same open anchor, gap adjustment,
    strict per-slot coverage (`min_periods=lookback`) and output columns as
    `core/session.py::noise_bands`; changes ONLY how the trailing same-time-of-day
    dispersion is aggregated across history — a flat mean becomes a recency-tilted
    weighted mean under a Laplace kernel:

        move[d-k, mfo] = |close[d-k, mfo] / open[d-k, 0] - 1|
        sigma[d, mfo]  = ( Σ_{k=1..lookback} w_k · move[d-k, mfo] ) / Σ w_k · scale
        w_k            = exp( -|k - mu| / b )                       (laplace_weights)

    The baseline uses w_k ≡ 1 (flat mean over the prior `lookback` sessions). This
    keeps a long window but can tilt the weight toward recent sessions (mu small,
    b small) so recent regime changes count more, WITHOUT truncating to a short,
    high-variance history (the EXP-0025 short-history failure). `b -> inf` reduces
    this to `noise_bands(df, lookback)` EXACTLY (uniform weights; proved in
    `tests/test_bands.py`), so the deployed lb90 baseline is the (mu=1, b=inf,
    lookback=90) cell.

    Causality: only strictly-prior sessions enter (the k>=1 lag is a shift(1)-style
    trailing window); a date's band never sees its own or any later session. Because
    every one of the `lookback` lagged frames must be present for the weighted sum to
    be non-null (a missing slot propagates NaN), coverage is IDENTICAL to
    `noise_bands(df, lookback)` — same strict `min_periods`.

    `scale` is a fixed study multiplier used to hold MEDIAN band width equal to the
    flat baseline, isolating the recency-tilt SHAPE from the width/capacity dial
    (EXP-0021). scale=1.0 is the raw laplace band.
    """
    w = laplace_weights(mu, b, lookback)
    o0 = df[df["mfo"] == 0].set_index("sdate")["open"]
    if o0.empty:
        raise ValueError("no session-open (mfo==0) bars found")
    last = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df["sdate"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = o0.reindex(dates)

    cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()

    # Weighted trailing mean: accumulate w_k * move.shift(k) for k=1..lookback.
    # A NaN in any lagged frame propagates to the sum, so a (date, slot) is defined
    # only when all `lookback` prior sessions have that slot == strict min_periods.
    num = None
    for k in range(1, lookback + 1):
        term = move.shift(k) * w[k - 1]
        num = term if num is None else num + term
    sigma = num / w.sum() * scale

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = long.merge(o0.rename("rth_open"), on="sdate")
    long = long.merge(prior_close.rename("prior_close"), on="sdate")
    long = long.dropna(subset=["rth_open", "prior_close", "sigma"])
    hi_ref = np.maximum(long["rth_open"], long["prior_close"])
    lo_ref = np.minimum(long["rth_open"], long["prior_close"])
    long["upper"] = hi_ref * (1.0 + long["sigma"])
    long["lower"] = lo_ref * (1.0 - long["sigma"])
    return long.reset_index(drop=True)
