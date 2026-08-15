"""Reference-location reversion primitives (exploration_5).

The question: is there a *reference level* that price is more likely to invert from?
Candidates: previous UTC-day high/low, and the 12:00-ET opening price. We measure the
forward return after price extends ``|z| = |price - level| / ATR >= k`` past a level, and
ask whether that reversion beats a matched generic-extension control and a re-pairing null.

Nothing here simulates a bracket fill or charges a cost: this is a signal / forward-return
study (RULES allow next-bar-open entry for that). Fills come later, if anything survives.

Calendars, eras, the dense forward-lookup ``MinuteGrid`` and the cluster-robust estimator
are imported from the audited ``exploration_4/_stage_a_lib`` rather than re-implemented.
Every non-trivial estimator below is unit-tested in ``test_ref_lib.py``.
"""

from __future__ import annotations

import math
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_EXP4 = Path(__file__).resolve().parent.parent / "exploration_4"
if str(_EXP4) not in sys.path:
    sys.path.insert(0, str(_EXP4))
import _stage_a_lib as lib  # noqa: E402  (audited calendars / MinuteGrid / cluster_stats)

PIP = 1e-4  # USD-major quote convention; all four pairs quote to 0.0001.


# --------------------------------------------------------------------------- #
# Daily structure: prior high/low and a causal ATR vol unit
# --------------------------------------------------------------------------- #

def daily_frame(minute_frame: pd.DataFrame) -> pd.DataFrame:
    """UTC-day OHLC plus prior-day high/low and a causal trailing ATR.

    ``pdh``/``pdl`` are the PRIOR day's extremes (``shift(1)``), so a level is fixed
    before the session that trades against it. ``atr`` is the mean daily true range over
    the prior ``atr`` window only (rolling then ``shift(1)``) -- it never sees the current
    day, so a decision at any intraday minute uses a vol unit that was already observable.
    """
    idx = lib.as_naive_utc(pd.DatetimeIndex(minute_frame["time"]))
    day = idx.floor("D")
    g = (pd.DataFrame({"day": day, "open": minute_frame["open"].to_numpy(),
                       "high": minute_frame["high"].to_numpy(),
                       "low": minute_frame["low"].to_numpy(),
                       "close": minute_frame["close"].to_numpy()})
         .groupby("day", observed=True)
         .agg(open=("open", "first"), high=("high", "max"),
              low=("low", "min"), close=("close", "last")))
    return g


def attach_atr(daily: pd.DataFrame, lookback_days: int, min_fraction: float) -> pd.DataFrame:
    """Add prior-day levels and a causal ATR (prior days only) to a daily frame."""
    d = daily.copy()
    prev_close = d["close"].shift(1)
    tr = pd.concat([(d["high"] - d["low"]),
                    (d["high"] - prev_close).abs(),
                    (d["low"] - prev_close).abs()], axis=1).max(axis=1)
    min_obs = max(2, int(math.ceil(min_fraction * lookback_days)))
    d["atr"] = tr.rolling(lookback_days, min_periods=min_obs).mean().shift(1)
    d["pdh"] = d["high"].shift(1)
    d["pdl"] = d["low"].shift(1)
    return d


def donchian_levels(daily: pd.DataFrame, lookback_days: int, min_fraction: float) -> tuple[pd.Series, pd.Series]:
    """Prior N-day channel: rolling max-high / min-low over the PRIOR ``lookback_days``.

    ``shift(1)`` excludes the current day, so the channel a decision trades against was
    fully formed before that session. ``pdh``/``pdl`` are the ``lookback_days=1`` special
    case; a larger N is the Turtle/Donchian breakout level whose fade is 'turtle soup'.
    """
    min_obs = max(1, int(math.ceil(min_fraction * lookback_days)))
    dch = daily["high"].rolling(lookback_days, min_periods=min_obs).max().shift(1)
    dcl = daily["low"].rolling(lookback_days, min_periods=min_obs).min().shift(1)
    return dch, dcl


def swing_levels(daily: pd.DataFrame, half_width: int) -> tuple[pd.Series, pd.Series]:
    """Most-recent CONFIRMED swing-high / swing-low pivot as of each day (causal).

    A pivot high at day ``i`` (its high is the unique maximum of ``[i-w, i+w]``) is only
    knowable ``w`` days later, so its level is placed at the CONFIRMATION day ``i+w`` and
    forward-filled from there. Using the pivot day itself would leak ``w`` days of future
    highs into the level -- the classic look-ahead in pivot studies. Stops of trapped
    traders cluster just beyond the last visible swing, which is the reference this tests.
    """
    hi = daily["high"].to_numpy(float)
    lo = daily["low"].to_numpy(float)
    n = len(hi)
    w = half_width
    sh = np.full(n, np.nan)
    sl = np.full(n, np.nan)
    for i in range(w, n - w):
        wh = hi[i - w:i + w + 1]
        wl = lo[i - w:i + w + 1]
        if hi[i] >= wh.max() and np.count_nonzero(wh == hi[i]) == 1:
            sh[i + w] = hi[i]
        if lo[i] <= wl.min() and np.count_nonzero(wl == lo[i]) == 1:
            sl[i + w] = lo[i]
    return (pd.Series(sh, index=daily.index).ffill(),
            pd.Series(sl, index=daily.index).ffill())


def attach_structure(daily: pd.DataFrame, cfg: dict) -> pd.DataFrame:
    """Add every daily structural level (pdh/pdl, Donchian, swing) as columns."""
    d = attach_atr(daily, cfg["atr_lookback_days"], cfg["atr_min_fraction"])
    dch, dcl = donchian_levels(daily, cfg["donchian_lookback_days"], cfg["atr_min_fraction"])
    sh, sl = swing_levels(daily, cfg["swing_half_width"])
    d["dch"], d["dcl"] = dch, dcl
    d["swing_high"], d["swing_low"] = sh, sl
    return d


def map_daily_to_minutes(minute_frame: pd.DataFrame, daily_col: pd.Series) -> np.ndarray:
    """Broadcast a per-UTC-day scalar to every minute of that day."""
    idx = lib.as_naive_utc(pd.DatetimeIndex(minute_frame["time"]))
    day = idx.floor("D")
    return daily_col.reindex(day).to_numpy()


# --------------------------------------------------------------------------- #
# Intraday reference: the 12:00-ET open, DST-aware
# --------------------------------------------------------------------------- #

def noon_et_level(minute_frame: pd.DataFrame, tz: str = "America/New_York",
                  noon_minute: int = 720) -> np.ndarray:
    """Per-minute 12:00-local opening price, valid only from noon onward that local day.

    The level is the ``open`` of the local-noon minute of each local trading day, broadcast
    to every minute of that local day AT OR AFTER noon. Minutes before local noon get NaN:
    the reference does not exist yet, so no crossing can be armed against it. Using the
    venue's own tz with real DST (not a hardcoded UTC hour) keeps the clock aligned across
    the March/November shifts.
    """
    idx = lib.as_naive_utc(pd.DatetimeIndex(minute_frame["time"]))
    loc = idx.tz_localize("UTC").tz_convert(tz)
    local_day = pd.DatetimeIndex(loc).floor("D")
    local_minute = pd.DatetimeIndex(loc).hour.to_numpy() * 60 + pd.DatetimeIndex(loc).minute.to_numpy()
    opens = minute_frame["open"].to_numpy()

    is_noon = local_minute == noon_minute
    noon_by_day = (pd.Series(np.where(is_noon, opens, np.nan), index=local_day)
                   .groupby(level=0).first())
    level = noon_by_day.reindex(local_day).to_numpy()
    level = np.where(local_minute >= noon_minute, level, np.nan)
    return level


# --------------------------------------------------------------------------- #
# Trailing-price control anchor (generic extension, no special location)
# --------------------------------------------------------------------------- #

def trailing_level(minute_frame: pd.DataFrame, lookback_minutes: int) -> np.ndarray:
    """Price ``lookback_minutes`` ago on the contiguous minute grid (NaN across gaps).

    This is the matched *generic-extension* control: crossing ``|price - price_{t-L}| >=
    k*ATR`` fires whenever price has simply moved k ATR over L minutes, with no structural
    level involved. Comparing a structural anchor against this at matched selection rate
    isolates whether the LEVEL matters or only the size of the excursion.
    """
    grid = MinuteAligned(minute_frame)
    off = grid.off
    src = np.full(grid.size, np.nan)
    src[off] = minute_frame["close"].to_numpy()
    lagged = np.full(grid.size, np.nan)
    if lookback_minutes < grid.size:
        lagged[lookback_minutes:] = src[:-lookback_minutes]
    return lagged[off]


# --------------------------------------------------------------------------- #
# Minute alignment helper
# --------------------------------------------------------------------------- #

class MinuteAligned:
    """Minute positions/offsets for a frame plus a contiguity flag (gap-aware)."""

    def __init__(self, minute_frame: pd.DataFrame):
        self.pos = lib.minute_positions(pd.DatetimeIndex(minute_frame["time"]))
        self.start = int(self.pos.min())
        self.size = int(self.pos.max()) - self.start + 1
        self.off = self.pos - self.start
        self.contiguous = np.empty(len(self.pos), bool)
        self.contiguous[0] = False
        self.contiguous[1:] = np.diff(self.pos) == 1


# --------------------------------------------------------------------------- #
# Crossing detection
# --------------------------------------------------------------------------- #

def crossing_events(price: np.ndarray, level: np.ndarray, atr: np.ndarray,
                    contiguous: np.ndarray, k: float, side: str) -> dict:
    """First-crossing rows where ``|price-level|/atr >= k`` on the requested side.

    ``side`` in {'above', 'below', 'both'}. 'First' means the immediately preceding
    contiguous minute was not already in the zone, so a retreat-and-return re-arms the
    signal and a gap always re-arms it. Returns the row indices, the signed displacement
    sign at the crossing (+1 price above level), and z.
    """
    price = np.asarray(price, float)
    level = np.asarray(level, float)
    atr = np.asarray(atr, float)
    disp = price - level
    with np.errstate(invalid="ignore", divide="ignore"):
        z = disp / atr
    if side == "above":
        cond = z >= k
    elif side == "below":
        cond = z <= -k
    elif side == "both":
        cond = np.abs(z) >= k
    else:
        raise ValueError(side)
    cond = np.where(np.isfinite(z), cond, False)

    prev_hot = np.zeros(len(cond), bool)
    prev_hot[1:] = cond[:-1] & contiguous[1:]
    events = np.flatnonzero(cond & ~prev_hot)
    return {"rows": events, "disp_sign": np.sign(disp[events]), "z": z[events]}


# --------------------------------------------------------------------------- #
# Forward outcome
# --------------------------------------------------------------------------- #

def forward_reversion(grid: "lib.MinuteGrid", entry_pos: np.ndarray, disp_sign: np.ndarray,
                      horizon: int, delay: int = 0) -> dict:
    """Signed-toward-anchor forward return in pips over ``horizon`` minutes.

    Entry is the open ``delay+1`` minutes after the signal minute (delay=0 -> next-minute
    open, the primary arm; delay=1 -> the paired shared-endpoint diagnostic). Reversion is
    ``-disp_sign * (exit_open - entry_open)`` so a move back toward the level is positive.
    ``complete`` screens that every minute in [entry, entry+horizon] exists, so the delayed
    arm is scored on exactly the same availability rule as the undelayed one.
    """
    entry_off = grid.offsets(np.asarray(entry_pos, np.int64) + 1 + delay)
    exit_off = entry_off + int(horizon)
    entry_open = grid.open_at(entry_off)
    exit_open = grid.open_at(exit_off)
    complete = grid.path_complete_span(entry_off, exit_off)
    rev_price = -np.asarray(disp_sign, float) * (exit_open - entry_open)
    rev_pips = rev_price / PIP
    rev_pips = np.where(complete, rev_pips, np.nan)
    return {"rev_pips": rev_pips, "rev_price": np.where(complete, rev_price, np.nan),
            "complete": complete, "entry_off": entry_off}


# --------------------------------------------------------------------------- #
# Re-pairing null: shuffle a per-day level across days within an era
# --------------------------------------------------------------------------- #

def repair_daily_levels(daily: pd.DataFrame, cols, era_of_day: np.ndarray,
                        rng: np.random.Generator) -> pd.DataFrame:
    """Permute ``cols`` across days WITHIN each era, keeping (pdh,pdl) paired per donor day.

    Preserves 'a horizontal level at a plausible prior-high/low value' and each pair's own
    intraday path, but destroys the specific relationship between today's path and today's
    real level. ATR is NOT permuted -- the vol unit stays the day's own, so only the level
    identity is nulled.
    """
    out = daily.copy()
    era = np.asarray(era_of_day)
    for e in np.unique(era):
        idx = np.flatnonzero(era == e)
        perm = idx.copy()
        rng.shuffle(perm)
        for c in cols:
            out.iloc[idx, out.columns.get_loc(c)] = daily[c].to_numpy()[perm]
    return out
