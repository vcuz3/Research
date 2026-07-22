"""
Faithful entry-signal encoding of SSRN-6650958 sections 3.3-3.6, on the 15m clock.

A signal is evaluated on a COMPLETED 15m bar t (all quantities knowable at its
close). The engine enters at the OPEN of bar t+1 (rule 2: bar-close information
cannot trade earlier in its own bar). Long conditions (short = exact symmetric
inverse):

  C1 regime : C_t > EMA200_t, and |C_t-EMA200_t|/EMA200_t >= 0.001 (skip the
              +-0.1% boundary-ambiguity zone, sec 3.3).
  C2 VWAP   : C_t > VWAP_t (institutional buy side).
  C3 prox   : min(L_t, L_{t-1}) <= EMA50_t <= C_t (touched/pierced the 50 EMA
              intrabar but closed above it).
  C4 reject : pin bar (lower_wick >= 2*body AND upper_wick <= 0.5*lower_wick)
              OR bullish engulfing (C_t > O_{t-1} AND O_t < C_{t-1}).
  C5 volume : V_t > 1.1 * MA20(V).
  C6 ATR    : (H_t - L_t) >= 0.8 * ATR14_t.

Initial stop (sec 3.6): SL = L_signal - 0.5*ATR14 (long) / H_signal + 0.5*ATR14
(short); 1R = |entry - SL|. Target = +/-3R (sec 4.1). Those bracket levels are
attached to the signal row and consumed by core.engine.

Output: the input frame with added columns sig_side (0/+1/-1, the side to enter at
NEXT bar open), sig_ref (L_signal for long / H_signal for short), sig_atr (ATR14
at the signal bar). Only bars that also leave room for a same-session next-bar
entry and clear EMA200 warmup carry a non-zero sig_side.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from ..core.data import WARMUP_BARS, N_BARS

VWAP_EPS = 0.0
REGIME_BAND = 0.001   # +-0.1% EMA200 boundary-ambiguity zone


CONDITION_NAMES = ("regime", "boundary", "vwap", "ema_touch", "ema_close_side",
                   "rejection", "volume", "range", "actionable")


def _conditions(df: pd.DataFrame) -> tuple[dict[str, np.ndarray], dict[str, np.ndarray]]:
    """Return the paper's cumulative-ready long/short Boolean conditions.

    Keeping the individual predicates available makes the low signal frequency
    auditable rather than treating the final conjunction as a black box.
    """
    o = df["open"].to_numpy(); h = df["high"].to_numpy()
    l = df["low"].to_numpy(); c = df["close"].to_numpy()
    ema200 = df["ema200"].to_numpy(); ema50 = df["ema50"].to_numpy()
    vwap = df["vwap"].to_numpy(); vol = df["volume"].to_numpy(float)
    volma = df["volma20"].to_numpy(); atr = df["atr14"].to_numpy()
    o1 = df["open"].shift(1).to_numpy(); c1 = df["close"].shift(1).to_numpy()
    l1 = df["low"].shift(1).to_numpy(); h1 = df["high"].shift(1).to_numpy()

    body = np.abs(c - o)
    lower_wick = np.minimum(o, c) - l
    upper_wick = h - np.maximum(o, c)
    rng = h - l
    dist = np.abs(c - ema200) / np.where(ema200 != 0, ema200, np.nan)

    bull_pin = (lower_wick >= 2.0 * body) & (upper_wick <= 0.5 * lower_wick)
    bear_pin = (upper_wick >= 2.0 * body) & (lower_wick <= 0.5 * upper_wick)
    # The prose says bullish/bearish candles, while its displayed inequalities
    # omit candle colours. Require both: this is the stricter literal-prose read.
    bull_engulf = (c > o) & (c1 < o1) & (c > o1) & (o < c1)
    bear_engulf = (c < o) & (c1 > o1) & (c < o1) & (o > c1)

    sess_bar = df["sess_bar"].to_numpy()
    actionable = ((df["bar_ix"].to_numpy() >= WARMUP_BARS) & (sess_bar >= 1)
                  & (sess_bar <= N_BARS - 2) & np.isfinite(atr)
                  & np.isfinite(volma) & np.isfinite(ema200))
    boundary = dist >= REGIME_BAND
    long = {
        "regime": c > ema200, "boundary": boundary, "vwap": c > vwap + VWAP_EPS,
        "ema_touch": np.minimum(l, l1) <= ema50, "ema_close_side": ema50 <= c,
        "rejection": bull_pin | bull_engulf, "volume": vol > 1.1 * volma,
        "range": rng >= 0.8 * atr, "actionable": actionable,
    }
    short = {
        "regime": c < ema200, "boundary": boundary, "vwap": c < vwap - VWAP_EPS,
        "ema_touch": np.maximum(h, h1) >= ema50, "ema_close_side": c <= ema50,
        "rejection": bear_pin | bear_engulf, "volume": vol > 1.1 * volma,
        "range": rng >= 0.8 * atr, "actionable": actionable,
    }
    return long, short


def condition_funnel(df: pd.DataFrame) -> pd.DataFrame:
    """Counts surviving bars after each cumulative paper condition by side."""
    long, short = _conditions(df)
    rows = []
    for side, conds in (("long", long), ("short", short)):
        keep = np.ones(len(df), dtype=bool)
        for name in CONDITION_NAMES:
            keep &= conds[name]
            rows.append({"side": side, "condition": name,
                         "standalone": int(conds[name].sum()),
                         "cumulative": int(keep.sum())})
    return pd.DataFrame(rows)


def add_signals(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    long, short = _conditions(df)
    long_ok = np.logical_and.reduce([long[n] for n in CONDITION_NAMES])
    short_ok = np.logical_and.reduce([short[n] for n in CONDITION_NAMES])
    side = np.where(long_ok, 1, np.where(short_ok, -1, 0)).astype(np.int64)
    l = df["low"].to_numpy(); h = df["high"].to_numpy()
    atr = df["atr14"].to_numpy()

    df["sig_side"] = side
    df["sig_ref"] = np.where(side == 1, l, np.where(side == -1, h, np.nan))
    df["sig_atr"] = np.where(side != 0, atr, np.nan)
    return df
