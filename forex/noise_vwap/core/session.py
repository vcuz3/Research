"""
FX session construction, the volume-free VWAP replacement, and the Noise-Area
bands, ported from `futures/nq/noise_vwap/core/data.py`.

THE ONE STRUCTURAL DIFFERENCE FROM THE NQ/ES PORT
--------------------------------------------------
IBKR cash-FX bars carry no size (`volume == -1` on 100% of 22.0M rows across the
four pairs; asserted in `core/build_clean.py`). The published strategy uses the
session VWAP in two distinct roles:

    (1) an ENTRY GATE  -- long only if close > upper band AND close > VWAP;
    (2) the STOP REFERENCE -- long stop below max(upper, VWAP).

Both need a causal, session-anchored "average price so far". The exact degenerate
limit of VWAP when every bar carries the same weight is the cumulative session
mean of the typical price, i.e. the **TWAP**:

    vwap  = sum(tp_i * v_i) / sum(v_i)        with v_i == const  =>  mean(tp_i)

so `anchor="twap"` is not a new indicator, it is the VWAP formula evaluated at
the only volume vector the data supports. `tests/test_session.py` pins this
identity: TWAP equals VWAP computed with a constant volume column, and it does
NOT equal VWAP computed with real (non-constant) weights.

Sessions
--------
The FX week is unambiguous in the data: quotes run Sunday 17:00 ET to Friday
17:00 ET with a daily roll break at 17:00-17:05 ET. Two session definitions are
carried, both anchored on the ET wall clock (DST-safe: US DST switches at 02:00
Sunday, inside the closed weekend):

  fxday  -- 17:00 ET -> 16:59 ET, the industry FX trading day (1440 slots). The
            faithful "one instrument-day" port. Its overnight gap is ~0 by
            construction because the prior close is the adjacent minute.
  active -- 03:00 ET -> 16:59 ET, London open through the NY close (840 slots).
            The closer analogue of an equity cash session: a liquid directional
            window preceded by a genuine overnight (Asia) gap.

`mfo` (minutes from open) is computed from the ET clock, not the bar index, so a
missing minute shifts nothing.

Causality
---------
* `twap` at bar t uses bars 0..t of the same session only.
* `sigma[s, mfo]` averages strictly PRIOR sessions (`shift(1)`).
* `min_periods` is the rule-9a fractional floor (default 0.9 * lookback), not the
  strict `min_periods=lookback` that silently deleted 28% of GC's late-day
  decisions (`futures/gc/noise_vwap/reports/DATA_QUALITY.md`).
"""
from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd

DATA = Path(__file__).resolve().parents[2] / "data" / "clean"

PAIRS = ("EURUSD", "GBPUSD", "AUDUSD", "NZDUSD")

# All four pairs are USD-quoted majors: 1 pip = 0.0001 of quote, worth $10 per
# standard lot (100,000 base units). Results are reported in pips; dollars are
# pips * PIP_VALUE at one standard lot.
PIP = 1e-4
PIP_VALUE = 10.0

# Session definitions: (start tod in ET minutes, length in minutes).
#
# The `fxday` anchor is 17:15 ET, not the nominal 17:00 roll, because of a
# measured archive defect (`reports/DATA_QUALITY.md`): the IBKR download drops
# the first 15 minutes of an hour at chunk boundaries. 17:00-17:14 ET is absent
# on 100% of EUR/GBP/AUD sessions and 21% of NZD sessions. Anchoring at 17:00
# would therefore give NZDUSD an open at 17:00 on 79% of sessions and 17:15 on
# the rest -- a session-varying anchor for the band's `move` denominator, and a
# different anchor from the other three pairs. 17:15 is the first minute present
# for all four pairs, so the anchor is uniform within and across pairs.
SESSIONS = {
    "fxday": (17 * 60 + 15, 1425),   # 17:15 ET -> 16:59 ET
    "active": (3 * 60, 840),         # 03:00 ET -> 16:59 ET
}

# A session must be near-complete to be usable (weekend stubs are dropped).
MIN_BAR_FRAC = 0.90

# Rule-9a fractional coverage floor for the trailing per-slot band estimate.
BAND_MIN_FRAC = 0.90


def path(pair: str) -> Path:
    return DATA / f"{pair}_1m_clean.parquet"


def load_session(pair: str, session: str = "fxday") -> pd.DataFrame:
    """
    Return 1-minute bars for `pair` restricted to `session`, with the ET clock,
    the session id, minutes-from-open, and the causal session TWAP.

    Columns: et, date, mfo, bar_i, pair, open, high, low, close, twap.
    `date` labels the session by the ET calendar date on which it ENDS.
    """
    if session not in SESSIONS:
        raise ValueError(f"unknown session {session!r}; have {sorted(SESSIONS)}")
    start_tod, length = SESSIONS[session]

    df = pd.read_parquet(path(pair))
    et = pd.to_datetime(df["ts_utc"], utc=True).dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"] = et.values
    tod = (et.dt.hour * 60 + et.dt.minute).to_numpy()

    # minutes from the session anchor on the ET wall clock
    mfo = (tod - start_tod) % 1440
    keep = mfo < length
    df["mfo"] = mfo
    # session label: the ET date the session ends on. Bars at or after the
    # anchor belong to the NEXT calendar date's session when the anchor is in
    # the afternoon (fxday); `active` never crosses midnight.
    day = et.dt.normalize().dt.tz_localize(None).to_numpy()
    rolls_over = (tod >= start_tod) & (start_tod + length > 1440)
    df["date"] = day + np.where(rolls_over, np.timedelta64(1, "D"), np.timedelta64(0, "D"))

    df = df.loc[keep].sort_values("et").reset_index(drop=True)

    # drop near-empty sessions (weekend stubs, holiday half-days)
    nb = df.groupby("date")["et"].transform("size")
    df = df.loc[nb >= MIN_BAR_FRAC * length].reset_index(drop=True)

    # causal cumulative session TWAP == VWAP under constant volume
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    g = df.groupby("date", sort=False)
    df["twap"] = (tp.groupby(df["date"]).cumsum() / (g.cumcount() + 1)).to_numpy()
    df["bar_i"] = g.cumcount().to_numpy()
    df["pair"] = pair
    return df[["et", "date", "mfo", "bar_i", "pair",
               "open", "high", "low", "close", "twap"]]


def decision_mfos(session: str = "fxday", step: int = 30) -> list[int]:
    """
    Concretum decision clock, pinned to the ET WALL CLOCK rather than to minutes
    from the open: decide on the close of every bar whose ET minute-of-hour is
    `step-1` mod `step`, i.e. :29 and :59 for the default 30-minute step. This is
    the NQ project's `09:59, 10:29, ...` grid expressed so that it does not move
    when the session anchor moves.

    Pinning to the wall clock also keeps every decision out of the :00-:14
    archive holes documented in `reports/DATA_QUALITY.md`; deriving decisions
    from the open instead would place the `fxday` grid at :14/:44 and delete
    NZDUSD decisions at 13:14, 14:14 and 15:14 ET.

    Decisions inside the first block are dropped (the session needs one full
    block of information first), as is the final block (a decision there could
    not be filled at a next-bar open inside the session).
    """
    start_tod, length = SESSIONS[session]
    out = []
    for mfo in range(step - 1, length - 1):
        minute_of_hour = (start_tod + mfo) % 60
        if (minute_of_hour + 1) % step == 0:
            out.append(mfo)
    return out


def noise_bands(df: pd.DataFrame, lookback: int = 90,
                min_frac: float = BAND_MIN_FRAC) -> pd.DataFrame:
    """
    Per (date, mfo) upper/lower Noise-Area bands. Identical construction to
    `futures/nq/noise_vwap/core/data.py::noise_bands` apart from the rule-9a
    fractional `min_periods`.

        move[d, mfo]  = |close[d, mfo] / open[d, 0] - 1|
        sigma[d, mfo] = mean of move over the prior `lookback` sessions (shift 1)
        upper[d, mfo] = max(open[d], prior_close[d]) * (1 + sigma)
        lower[d, mfo] = min(open[d], prior_close[d]) * (1 - sigma)

    Returns a long frame: date, mfo, sigma, sess_open, prior_close, upper, lower.
    """
    first = df.sort_values("et").groupby("date").head(1).set_index("date")
    opens = first["open"]
    last = df.sort_values("et").groupby("date").tail(1).set_index("date")["close"]
    dates = df["date"].drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)
    o0 = opens.reindex(dates)

    cm = df.pivot_table(index="date", columns="mfo", values="close", aggfunc="last")
    cm = cm.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()

    mp = max(1, int(math.ceil(min_frac * lookback)))
    sigma = move.shift(1).rolling(lookback, min_periods=mp).mean()

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["date", "mfo", "sigma"]
    long = long.merge(o0.rename("sess_open"), on="date")
    long = long.merge(prior_close.rename("prior_close"), on="date")
    long = long.dropna(subset=["sess_open", "prior_close", "sigma"])
    hi = np.maximum(long["sess_open"], long["prior_close"])
    lo = np.minimum(long["sess_open"], long["prior_close"])
    long["upper"] = hi * (1.0 + long["sigma"])
    long["lower"] = lo * (1.0 - long["sigma"])
    return long.reset_index(drop=True)


def daily_atr(df: pd.DataFrame, n: int = 14) -> pd.Series:
    """
    Causal per-session risk unit in PIPS: Wilder-seeded rolling mean of the
    session true range over the prior `n` sessions (strictly prior, shift(1)).
    Used to express per-trade P&L in R (rule 19/21), never inside a signal.
    """
    g = df.groupby("date")
    hi = g["high"].max()
    lo = g["low"].min()
    cl = g["close"].last()
    pc = cl.shift(1)
    tr = pd.concat([hi - lo, (hi - pc).abs(), (lo - pc).abs()], axis=1).max(axis=1)
    return (tr.rolling(n, min_periods=n).mean().shift(1) / PIP).rename("atr_pips")


if __name__ == "__main__":
    for sess in ("fxday", "active"):
        for pair in PAIRS:
            d = load_session(pair, sess)
            b = noise_bands(d, 90)
            print(f"{sess:<7s} {pair} bars={len(d):>9,d} sessions={d['date'].nunique():>5,d} "
                  f"{str(d['date'].min())[:10]}->{str(d['date'].max())[:10]} "
                  f"band_rows={len(b):>9,d} median_sigma_bp={b['sigma'].median()*1e4:.2f}")
