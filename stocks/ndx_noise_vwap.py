"""Faithful Noise-Area + VWAP strategy adapters for Nasdaq-100 constituents.

This module does NOT re-implement the strategy. It reuses the audited futures
engine (`futures/nq/noise_vwap/core/engine.py` and its `data.noise_bands`) so the
entry, stateful exit, next-open fills and forced end-of-session flatten are
bit-for-bit the published Noise-Area + VWAP momentum logic:

  * decisions on the Concretum 30-min clock (mfo 29,59,...,389 == tod 599..959);
  * LONG when close > upper band AND close > VWAP; SHORT symmetric;
  * HOLD until the close returns through max(upper, VWAP) (long) / min(lower, VWAP)
    (short) -- i.e. the noise-area / VWAP is breached -- then exit at the NEXT
    bar's open. A reverse signal flips at a decision bar;
  * if never breached, the position is FORCE-FLATTENED at the last RTH close and
    the return is recorded (reason="eod"). Positions are never dropped for
    crossing the session close.

The only thing built here is a stock loader that yields the exact bar frame the
engine expects (the LSE stock parquet has a different schema and timezone than the
Databento futures files). `noise_bands` and `run` are re-exported unchanged.

Per-trade P&L is returned in RETURN units (bps of entry notional) so names priced
$20 and $1000 pool cleanly -- the equal-risk-ish estimand a stock selector fishes
in. Faithful published defaults: lookback=90 same-tod sessions, require_vwap=True,
decision-cadence stop.
"""
from __future__ import annotations

from pathlib import Path
import sys

import numpy as np
import pandas as pd

# Locate the workspace root (holds the futures package) and make it importable.
_ROOT = Path(__file__).resolve().parent
while _ROOT != _ROOT.parent and not (_ROOT / "futures" / "nq" / "noise_vwap").exists():
    _ROOT = _ROOT.parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

# Audited, unchanged strategy machinery (namespace-package import; no re-impl).
from futures.nq.noise_vwap.core.data import noise_bands  # noqa: E402  re-exported
from futures.nq.noise_vwap.core.engine import run, DECISION_TODS  # noqa: E402

RTH_START = 9 * 60 + 30   # 09:30 ET (tod)
RTH_END = 16 * 60         # 16:00 ET (tod, exclusive)
SESSION_MINUTES = RTH_END - RTH_START  # 390
ET = "America/New_York"
MIN_BARS = 350            # a session must be near-complete (of 390) to be usable
DEFAULT_LOOKBACK = 90     # faithful Quantitativo same-tod lookback

__all__ = ["load_rth_stock", "noise_bands", "run", "DECISION_TODS",
           "run_stock", "trades_returns", "build_ew_index", "index_bars_from_ew",
           "RTH_START", "RTH_END", "SESSION_MINUTES", "ET", "DEFAULT_LOOKBACK"]


def load_rth_stock(path: Path | str) -> pd.DataFrame:
    """Load one LSE 1-min stock parquet as an engine-compatible RTH bar frame.

    Mirrors `futures...core.data.load_rth` (same columns, same causal session
    VWAP) for the LSE schema: `ts` is tz-aware UTC; pre/post-market bars and
    incomplete sessions are dropped. One row per bar, columns:
    et, date, tod, bar_i, inst, symbol, open, high, low, close, volume, vwap.
    """
    df = pd.read_parquet(path, columns=["ts", "symbol", "open", "high", "low", "close", "volume"])
    et = pd.to_datetime(df["ts"], utc=True).dt.tz_convert(ET)
    df = df.copy()
    df["et"] = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df["date"] = et.dt.normalize().dt.tz_localize(None).values
    df = df[(df["tod"] >= RTH_START) & (df["tod"] < RTH_END)]
    df = df.sort_values("et").reset_index(drop=True)
    # defensive: one bar per (date, tod)
    df = df.drop_duplicates(["date", "tod"], keep="first").reset_index(drop=True)

    # keep only near-complete sessions
    nb = df.groupby("date")["et"].transform("size")
    df = df[nb >= MIN_BARS].reset_index(drop=True)

    # causal cumulative session VWAP (typical price, real volume)
    tp = (df["high"] + df["low"] + df["close"]) / 3.0
    v = df["volume"].astype("float64").to_numpy()
    g = df.groupby("date", sort=False)
    cum_v = g["volume"].cumsum().astype("float64").to_numpy()
    cum_tpv = pd.Series(tp.to_numpy() * v, index=df.index).groupby(df["date"]).cumsum().to_numpy()
    df["vwap"] = cum_tpv / np.where(cum_v == 0.0, np.nan, cum_v)
    df["bar_i"] = g.cumcount().to_numpy()
    df["inst"] = df["symbol"].iloc[0] if len(df) else ""
    return df[["et", "date", "tod", "bar_i", "inst", "symbol",
               "open", "high", "low", "close", "volume", "vwap"]]


def run_stock(bars: pd.DataFrame, lookback: int = DEFAULT_LOOKBACK, **run_kwargs) -> pd.DataFrame:
    """Run the faithful engine on one stock's bars. Returns the per-trade frame
    (columns: date, side, entry_tod, exit_tod, entry_px, exit_px, points, reason).
    Faithful published defaults (require_vwap=True, decision-cadence stop)."""
    bands = noise_bands(bars, lookback)
    return run(bars, bands, **run_kwargs)


def trades_returns(trades: pd.DataFrame, cost_bp: float = 0.0) -> pd.DataFrame:
    """Add return-space P&L to a per-trade frame.

    ret     = side*(exit_px-entry_px)/entry_px         (fraction of entry notional)
    ret_bp  = ret * 1e4                                 (basis points)
    net_bp  = ret_bp - cost_bp                          (round-trip cost charge)
    Poolable across differently-priced names; the equal-notional estimand a
    stock selector actually earns.
    """
    t = trades.copy()
    if t.empty:
        for c in ("ret", "ret_bp", "net_bp"):
            t[c] = pd.Series(dtype="float64")
        return t
    t["ret"] = t["points"] / t["entry_px"]
    t["ret_bp"] = t["ret"] * 1e4
    t["net_bp"] = t["ret_bp"] - cost_bp
    return t


def build_ew_index(loaded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Equal-weight core-index level keyed by (date, tod).

    Per-minute equal-weight of within-session simple returns (no overnight gap),
    compounded to a level that bases at 1.0 each session. Returns a long frame
    with columns date, tod, ret, level -- the aggregate risk-on vehicle used for
    the positive-control run and the market-residual.
    """
    sum_ret = None
    cnt_ret = None
    for d in loaded.values():
        r = d.groupby("date")["close"].pct_change()
        key = pd.MultiIndex.from_arrays([d["date"].values, d["tod"].values])
        r = pd.Series(r.values, index=key)
        r = r[~r.index.duplicated(keep="first")]
        sum_ret = r if sum_ret is None else r.add(sum_ret, fill_value=0.0)
        cnt = pd.Series(np.where(r.notna(), 1.0, 0.0), index=r.index)
        cnt_ret = cnt if cnt_ret is None else cnt.add(cnt_ret, fill_value=0.0)
    ew_ret = (sum_ret / cnt_ret.replace(0.0, np.nan)).fillna(0.0)
    ew = ew_ret.rename("ret").reset_index()
    ew.columns = ["date", "tod", "ret"]
    ew = ew.sort_values(["date", "tod"], kind="mergesort").reset_index(drop=True)
    ew["level"] = ew.groupby("date")["ret"].transform(lambda x: (1.0 + x).cumprod())
    return ew


def index_bars_from_ew(ew: pd.DataFrame) -> pd.DataFrame:
    """Reshape the EW index level into an engine-compatible bar frame so the
    identical strategy can run on the aggregate (the positive-control / validity
    gate).

    o=h=l=c=level (the index has no intrabar range). VWAP is a real, causal
    *equal-volume* running mean of the level within the session (volume==1, so the
    dollar-VWAP degenerates to the running average of the typical price = level).
    Setting VWAP==level would make the faithful `close > VWAP` entry gate
    `close > close` and silently disable every entry -- so the running mean is
    required, not cosmetic. (A cross-price dollar VWAP is ill-defined across
    differently-priced names, hence the equal-volume proxy.)"""
    b = ew.copy()
    for c in ("open", "high", "low", "close"):
        b[c] = b["level"].to_numpy()
    b["volume"] = 1.0
    # causal within-session running mean of the level (equal-volume VWAP proxy)
    g = b.groupby("date", sort=False)
    b["vwap"] = (g["level"].cumsum() / (g.cumcount() + 1.0)).to_numpy()
    b["symbol"] = "_EWINDEX_"
    b["inst"] = "_EWINDEX_"
    b["bar_i"] = g.cumcount().to_numpy()
    b["et"] = pd.NaT
    return b[["et", "date", "tod", "bar_i", "inst", "symbol",
              "open", "high", "low", "close", "volume", "vwap"]]


def index_return_over(ew_level: pd.DataFrame, date, tod_from, tod_to) -> float:
    """EW index simple return over [tod_from, tod_to] within one session (for the
    market-residual over a trade's actual, variable holding window)."""
    lv = ew_level.loc[date]
    try:
        return float(lv.loc[tod_to] / lv.loc[tod_from] - 1.0)
    except KeyError:
        return np.nan
