"""The 30-product CME panel: loading, clocks, rolls, and measured tick sizes.

Source archive
--------------
Databento ``GLBX.MDP3``, schema ``ohlcv-1m``, volume-ranked continuous front
(``<sym>.v.0``), **UNADJUSTED**, at ``futures/data/databento/``.

The source item (H-A1) says "40 CME products".  That is the *file* count: 40
parquets, of which 8 are 1-second or MBP-1 or back-adjusted duplicates and 2 are
non-parquet.  The true panel of distinct 1-minute products is **30**, which still
clears the ">= 20 products" bar in the kill test.

Session
-------
Verified against the archive rather than assumed (``scripts/data_quality.py``):
every one of the 30 products has an empty ET minute-of-day block ending at 17:59
and resumes at 18:00 ET, so the CME trade date

    sdate = date(t_ET + 6h)

is a uniform session key across all five asset classes.  The *start* of the
maintenance halt differs by product (17:00 / 17:01 / 17:15 / 17:30 ET); its end
does not.

Rolls (rule 11)
---------------
The archive is unadjusted, so the price change across an ``instrument_id`` change
is a synthetic contract-substitution jump, not a return anyone earned.  Every
such change is marked and the corresponding return is dropped from BOTH the
autocorrelation estimation and the P&L booking.  Nothing here back-adjusts: a
back-adjusted series has a different variance and different autocorrelations at
the roll, and the point of this study is to measure those quantities.

Tick sizes (rule 19)
--------------------
Measured from the price grid per product per year, never assumed, because six of
the seven FX contracts alone changed tick mid-sample at six different dates
(recorded in ``futures/forex/vwap_exploration/MEMORY.md``).  ``infer_ticks``
returns the largest candidate increment that at least ``frac`` of that year's
closes lie on.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd

DATA_DIR = Path(__file__).resolve().parents[3] / "data" / "databento"
CACHE_DIR = Path(__file__).resolve().parents[1] / "data"

# --------------------------------------------------------------------------- #
# panel registry
# --------------------------------------------------------------------------- #
# asset_class is the CLUSTER used by every bootstrap and every leave-one-out
# check in this project.  It is not decoration: MGC is GC at 1/10 notional and
# MCL is CL at 1/10 notional (same underlying, same tape), and ZT/ZF/ZN/ZB/UB are
# five points on one yield curve.  A 30-observation CI that ignores this is badly
# anti-conservative.
PANEL: dict[str, str] = {
    # FX
    "6A": "fx", "6B": "fx", "6C": "fx", "6E": "fx",
    "6J": "fx", "6N": "fx", "6S": "fx",
    # equity index
    "ES": "equity", "NQ": "equity", "RTY": "equity", "YM": "equity",
    # metals
    "GC": "metals", "SI": "metals", "HG": "metals",
    "PL": "metals", "PA": "metals", "MGC": "metals",
    # energy
    "CL": "energy", "BZ": "energy", "NG": "energy",
    "HO": "energy", "RB": "energy", "MCL": "energy",
    # rates
    "ZT": "rates", "ZF": "rates", "ZN": "rates", "ZB": "rates",
    "UB": "rates", "SR3": "rates", "ZQ": "rates",
}

PRODUCTS: tuple[str, ...] = tuple(PANEL)
ASSET_CLASSES: tuple[str, ...] = ("fx", "equity", "metals", "energy", "rates")

# Near-duplicate members: same underlying as another panel member at a smaller
# notional.  Dropped in the de-duplicated robustness arm.
MINI_DUPLICATES: dict[str, str] = {"MGC": "GC", "MCL": "CL"}

SESSION_OPEN_MOD = 18 * 60          # 18:00 ET
SESSION_ROLLOVER_HOURS = 6          # sdate = date(t_ET + 6h)


def _file_for(product: str) -> Path:
    matches = sorted(
        p for p in DATA_DIR.glob(f"{product}_ohlcv-1m_*.parquet")
        if "back_adjusted" not in p.name and "resampled" not in p.name
    )
    if len(matches) != 1:
        raise FileNotFoundError(f"{product}: expected 1 ohlcv-1m parquet, found {matches}")
    return matches[0]


# --------------------------------------------------------------------------- #
# tick measurement
# --------------------------------------------------------------------------- #
# Decimal increments plus the binary fractions the Treasury complex actually
# trades on (ZB/UB 1/32 = 0.03125, ZN 1/64, ZF 1/128, ZT 1/256 of a point).
_TICK_CANDIDATES = np.array(sorted(
    [m * 10.0 ** e for e in range(-7, 2) for m in (1.0, 2.5, 5.0)]
    + [2.0 ** -k for k in range(1, 11)]
    + [1.0, 5.0, 10.0, 25.0]
), dtype=np.float64)


def infer_tick(closes: np.ndarray, frac: float = 0.99, rtol: float = 1e-7) -> float:
    """Largest candidate increment that at least `frac` of `closes` lie on.

    Floating point makes an exact modulo test useless, so a price is "on the
    grid" when it is within `rtol` (relative to the price level) of a multiple of
    the candidate.  Returns NaN when nothing qualifies.
    """
    c = np.asarray(closes, dtype=np.float64)
    c = c[np.isfinite(c) & (c != 0.0)]
    if c.size == 0:
        return float("nan")
    tol = np.abs(c) * rtol
    best = float("nan")
    for g in _TICK_CANDIDATES:                       # ascending
        q = c / g
        on = np.abs(q - np.round(q)) * g <= tol
        if on.mean() >= frac:
            best = float(g)
    return best


def infer_ticks_by_year(daily: pd.DataFrame) -> pd.Series:
    """Measured tick per calendar year from that year's closes."""
    years = daily["sdate"].dt.year
    return daily.groupby(years)["close"].apply(lambda s: infer_tick(s.to_numpy()))


# --------------------------------------------------------------------------- #
# loading and clocks
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class LoadReport:
    product: str
    asset_class: str
    raw_rows: int
    rows: int
    sessions: int
    first_date: object
    last_date: object
    halt_rows_dropped: int
    roll_sessions: int
    short_sessions_dropped: int
    median_bars_per_session: float


def load_1m(product: str) -> pd.DataFrame:
    """Raw 1-minute bars with ET session columns attached."""
    df = pd.read_parquet(
        _file_for(product),
        columns=["ts_event", "open", "high", "low", "close", "volume", "instrument_id"],
    )
    et = df["ts_event"].dt.tz_convert("America/New_York")
    df["mod"] = (et.dt.hour * 60 + et.dt.minute).astype(np.int32)
    df["sdate"] = (
        (et + pd.Timedelta(hours=SESSION_ROLLOVER_HOURS)).dt.normalize().dt.tz_localize(None)
    )
    df["mfo"] = ((df["mod"] - SESSION_OPEN_MOD) % 1440).astype(np.int32)
    return df.sort_values(["sdate", "mfo"], kind="mergesort").reset_index(drop=True)


def daily_bars(product: str, min_session_bars: int = 60,
               ) -> tuple[pd.DataFrame, LoadReport]:
    """One row per CME trade date.

    Columns: ``sdate, open, high, low, close, volume, nbars, roll`` where ``roll``
    marks a session whose bars span more than one ``instrument_id`` OR whose
    first ``instrument_id`` differs from the previous session's last.  Both cases
    make the incoming price change a contract substitution rather than a return.
    """
    raw = load_1m(product)
    raw_rows = len(raw)

    halt = (raw["mod"] >= 17 * 60) & (raw["mod"] < 18 * 60)
    halt_rows = int(halt.sum())
    df = raw.loc[~halt]

    g = df.groupby("sdate", sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum().astype(np.float64),
        "nbars": g["close"].size(),
        "inst_first": g["instrument_id"].first(),
        "inst_last": g["instrument_id"].last(),
        "inst_n": g["instrument_id"].nunique(),
    }).reset_index()

    short = out["nbars"] < min_session_bars
    n_short = int(short.sum())
    out = out.loc[~short].reset_index(drop=True)

    prev_last = out["inst_last"].shift(1)
    out["roll"] = (out["inst_n"] > 1) | (out["inst_first"] != prev_last)
    out.loc[0, "roll"] = True                      # no prior session to come from

    rep = LoadReport(
        product=product, asset_class=PANEL[product], raw_rows=raw_rows, rows=int(len(df)),
        sessions=int(len(out)), first_date=out["sdate"].min(), last_date=out["sdate"].max(),
        halt_rows_dropped=halt_rows, roll_sessions=int(out["roll"].sum()) - 1,
        short_sessions_dropped=n_short,
        median_bars_per_session=float(out["nbars"].median()),
    )
    return out, rep


def slot_bars(product: str, minutes: int = 30, min_session_bars: int = 60,
              ) -> tuple[pd.DataFrame, LoadReport]:
    """One row per (trade date, `minutes`-slot) on the ET WALL CLOCK.

    The grid is pinned to `mfo // minutes`, never to minutes-from-open, so a
    missing minute shifts nothing (LEARNINGS 2026-08-01).  Slots with no bar at
    all are simply absent; the caller sees that through `nbars` and the
    per-slot coverage in the data-quality report.
    """
    raw = load_1m(product)
    raw_rows = len(raw)
    halt = (raw["mod"] >= 17 * 60) & (raw["mod"] < 18 * 60)
    halt_rows = int(halt.sum())
    df = raw.loc[~halt].copy()

    per_session = df.groupby("sdate")["close"].size()
    keep = per_session.index[per_session >= min_session_bars]
    n_short = int(len(per_session) - len(keep))
    df = df.loc[df["sdate"].isin(set(keep))]

    df["slot"] = (df["mfo"] // minutes).astype(np.int32)
    g = df.groupby(["sdate", "slot"], sort=True)
    out = pd.DataFrame({
        "open": g["open"].first(),
        "high": g["high"].max(),
        "low": g["low"].min(),
        "close": g["close"].last(),
        "volume": g["volume"].sum().astype(np.float64),
        "nbars": g["close"].size(),
        "inst_first": g["instrument_id"].first(),
        "inst_last": g["instrument_id"].last(),
        "inst_n": g["instrument_id"].nunique(),
    }).reset_index()

    prev_last = out["inst_last"].shift(1)
    out["roll"] = (out["inst_n"] > 1) | (out["inst_first"] != prev_last)
    out.loc[0, "roll"] = True

    rep = LoadReport(
        product=product, asset_class=PANEL[product], raw_rows=raw_rows, rows=int(len(df)),
        sessions=int(out["sdate"].nunique()), first_date=out["sdate"].min(),
        last_date=out["sdate"].max(), halt_rows_dropped=halt_rows,
        roll_sessions=int(out["roll"].sum()) - 1, short_sessions_dropped=n_short,
        median_bars_per_session=float(out.groupby("sdate")["slot"].size().median()),
    )
    return out, rep


# --------------------------------------------------------------------------- #
# risk units
# --------------------------------------------------------------------------- #
VOL_MIN_FRAC = 2.0 / 3.0


def risk_units(price: pd.Series, roll: pd.Series, vol_window: int = 63,
               min_periods: int | None = None) -> pd.DataFrame:
    """Price changes standardised by a strictly causal trailing volatility.

    Returns a frame with ``dp`` (raw price change, NaN across a roll), ``vol``
    (the causal scale in force for that period) and ``x = dp / vol``.

    `vol` is a **rolling** standard deviation, deliberately not an `ewm`: the
    workspace has a recorded defect where `ewm(alpha=1/n, min_periods=n,
    adjust=False)` admits bars with well under one e-folding of data and seeds
    the recursion at a single observation (LEARNINGS 2026-07-26).  A rolling
    window with an explicit `min_periods` has neither failure mode.

    `min_periods` defaults to **two thirds** of the window, not the whole of it,
    and that is load-bearing rather than fussy.  Rolls make `dp` missing at
    scattered rows; a strict ``min_periods == vol_window`` then requires all 63
    trailing sessions to be roll-free, and this project's first build showed
    exactly the LEARNINGS 2026-07-19 failure -- CL drops 4.7% of its returns to
    rolls, so essentially EVERY 63-session window contained one and the daily
    risk unit was defined on **0.0%** of rows for all six energy products.  The
    fractional floor restores them.  Per-product `x_defined` is reported by the
    data-quality gate; a value far below 1 is a finding, not a detail.

    Causality: the window ends at ``t-1``.  `vol` at row t uses only price
    changes strictly before t, so `x_t` is observable the instant `price_t`
    prints.
    """
    if min_periods is None:
        min_periods = max(10, int(round(VOL_MIN_FRAC * vol_window)))
    dp = price.diff()
    dp = dp.where(~roll.to_numpy())                      # a roll is not a return
    vol = dp.rolling(vol_window, min_periods=min_periods).std(ddof=1).shift(1)
    x = dp / vol.replace(0.0, np.nan)
    return pd.DataFrame({"dp": dp, "vol": vol, "x": x})


def slot_risk_units(frame: pd.DataFrame, lookback: int = 90, min_periods: int = 45,
                    ) -> pd.DataFrame:
    """`risk_units` for the intraday clock, standardised WITHIN each slot.

    Mandatory on the 30-minute grid, not optional.  Intraday volatility has a
    strong deterministic profile and one of the 46 slots straddles the overnight
    maintenance halt, so a pooled scale leaves `x` with a per-slot variance
    profile.  That breaks the thing the closed form is a statement about: `x` is
    supposed to be a stationary, unit-risk series, and a book sized off a pooled
    scale is over-risked in the quiet slots and under-risked in the busy ones,
    so its realised P&L is not the quantity PHI predicts.

    Note precisely what this does and does not fix.  A per-slot SCALE profile
    does NOT bias a pooled autocorrelation.  A per-slot MEAN profile does, and
    that is the LEARNINGS 2026-08-03 mechanism; `slot_demean` is the control for
    it and is reported separately.

    `lookback=90, min_periods=45` is the project standard set by measured 6B Asia
    coverage in `futures/forex/vwap_exploration` (finding G): a strict full
    window silently deletes decisions in an instrument's thin hours.

    `frame` must already be in chronological (sdate, slot) order; `dp` is the
    change along that order, so the slot straddling the maintenance halt carries
    the real overnight move rather than a dropped one.  Only the SCALE is
    per-slot.
    """
    out = frame.copy()
    dp = out["close"].diff()
    dp = dp.where(~out["roll"].to_numpy())
    scale = (
        dp.groupby(out["slot"].to_numpy())
          .transform(lambda s: s.rolling(lookback, min_periods=min_periods)
                                .std(ddof=1).shift(1))
    )
    return pd.DataFrame({"dp": dp, "vol": scale, "x": dp / scale.replace(0.0, np.nan)},
                        index=out.index)


def slot_demean(x: pd.Series, slot: pd.Series, lookback: int = 90,
                min_periods: int = 45) -> pd.Series:
    """Subtract the causal trailing SAME-SLOT mean from `x`.

    A deterministic per-slot MEAN is the contamination that actually reaches this
    project's predicted score.  A per-slot *scale* profile does not bias a
    pooled autocorrelation (independent draws stay independent however they are
    scaled), but a per-slot *mean* does: two consecutive readings covary partly
    because of where in the session they sit, and the pooled `rho(1)` reads that
    as memory.  That is the LEARNINGS 2026-08-03 mechanism, and it feeds both
    terms of PHI at once -- the autocorrelation sum through `rho`, and the drift
    term through `mean(x)^2`.

    Reported as a diagnostic on the intraday arm rather than applied by default,
    because a genuine per-slot drift is partly something a trend follower earns;
    the question the report has to answer is how much of the intraday PHI is it.
    """
    mu = (x.groupby(slot.to_numpy())
           .transform(lambda s: s.rolling(lookback, min_periods=min_periods)
                                 .mean().shift(1)))
    return x - mu
