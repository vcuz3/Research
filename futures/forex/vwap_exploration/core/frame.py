"""The shared decision panel: one row per (session, decision minute).

Decision clock
--------------
A 30-minute grid pinned to the **ET wall clock**, not to minutes-from-open: the
decision minutes are `mfo in {29, 59, 89, ...}`, i.e. ET :29 and :59 of every
hour, 46 per session.  Pinning to the wall clock is deliberate -- deriving the
grid from minutes-from-open puts it on whatever offset the archive's first
present minute happens to be, which in `forex/noise_vwap` silently deleted a
whole pair's :14 decisions.

Execution convention (rules 1, 2)
---------------------------------
The bar at `mfo = m` closes and its OHLC becomes observable.  The earliest
tradable price is the OPEN of bar `m+1`.  Every forward return is therefore

    fwd_H = close(m + H) - open(m + 1)

which is the P&L of a position entered at the next available price and closed H
minutes later at a bar close.  There is no stop, no target and no barrier: this
is an ENTRY-INFORMATION study (rule 15), so nothing here can be manufactured by
exit geometry.

Note the incidental benefit for rule-16-style artifacts: the trailing feature ends
at `close(m)` and the forward return starts at `open(m+1)`, so the two share NO
price.  A measurement that let both touch `close(m)` would inherit mechanical
negative correlation from the bid-ask bounce at that single print -- worth 31-56%
of measured 5-minute reversion on NQ/ES/GC (LEARNINGS 2026-07-31d).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from . import data as D
from . import vwap as V

PERIOD = 30
HORIZONS = (30, 60, 120)


def decision_mfos(period: int = PERIOD) -> np.ndarray:
    return np.arange(period - 1, D.SESSION_MINUTES, period)


def _grid(bars: pd.DataFrame, col: str) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Pivot `col` to a (session x minute) matrix. Returns (matrix, sdates, mfos)."""
    piv = bars.pivot_table(index="sdate", columns="mfo", values=col, aggfunc="last")
    piv = piv.reindex(columns=np.arange(D.SESSION_MINUTES))
    return piv.to_numpy(float), piv.index.to_numpy(), piv.columns.to_numpy()


def build_panel(product: str, scope: str = "explore", *,
                period: int = PERIOD, horizons=HORIZONS,
                anchors=V.ANCHORS) -> pd.DataFrame:
    """One row per decision, with anchors, deviations, forward and trailing returns."""
    bars, _rep = D.load_bars(product, scope=scope)
    bars = V.add_anchors(bars)
    bars = V.add_deviations(bars, anchors=anchors)

    close_m, sdates, _ = _grid(bars, "close")
    open_m, _, _ = _grid(bars, "open")
    n_s = len(sdates)

    dm = decision_mfos(period)
    dm = dm[dm < D.SESSION_MINUTES]

    # ---- forward and trailing returns, in price units -------------------
    # Forward entry price is the first available OPEN at or after m+1: a missing
    # minute must not silently become a different (later) entry than the return's
    # measurement bar, so a missing m+1 open disqualifies the decision instead.
    entry = np.full((n_s, len(dm)), np.nan)
    for j, m in enumerate(dm):
        if m + 1 < D.SESSION_MINUTES:
            entry[:, j] = open_m[:, m + 1]

    fwd = {}
    for h in horizons:
        arr = np.full((n_s, len(dm)), np.nan)
        for j, m in enumerate(dm):
            if m + h < D.SESSION_MINUTES:
                arr[:, j] = close_m[:, m + h] - entry[:, j]
        fwd[h] = arr
    # to the session close: the last minute of the session that has a bar
    last_idx = np.full(n_s, -1)
    valid = np.isfinite(close_m)
    for i in range(n_s):
        w = np.flatnonzero(valid[i])
        last_idx[i] = w[-1] if w.size else -1
    last_close = np.where(last_idx >= 0, close_m[np.arange(n_s), last_idx], np.nan)
    fwd_close = last_close[:, None] - entry

    past = {}
    for h in horizons:
        arr = np.full((n_s, len(dm)), np.nan)
        for j, m in enumerate(dm):
            if m - h >= 0:
                arr[:, j] = close_m[:, m] - close_m[:, m - h]
        past[h] = arr

    # ---- assemble ---------------------------------------------------------
    idx = pd.MultiIndex.from_product([sdates, dm], names=["sdate", "mfo"])
    panel = pd.DataFrame(index=idx).reset_index()
    for h in horizons:
        panel[f"fwd_{h}"] = fwd[h].ravel()
        panel[f"past_{h}"] = past[h].ravel()
    panel["fwd_close"] = fwd_close.ravel()
    panel["entry_px"] = entry.ravel()

    keep = ["sdate", "mfo", "close", "volume", "et"]
    keep += [c for c in bars.columns
             if c.startswith(("dev_", "scale_", "vwap", "twap", "open_anchor", "pclose"))]
    panel = panel.merge(bars[keep].drop_duplicates(["sdate", "mfo"]),
                        on=["sdate", "mfo"], how="left")

    mod = (panel["mfo"].to_numpy() + D.SESSION_OPEN_MOD) % 1440
    panel["mod"] = mod
    panel["block"] = D.block_of_mod(mod)
    panel["year"] = panel["sdate"].dt.year
    panel["product"] = product

    # Per-product reporting unit: 1e-4 for 6E/6B (unchanged), 1e-6 for 6J, whose
    # quote is dollars per YEN near 0.0091. See `data._PIP_SIZE`.
    pip = D.pip_size(product)
    for h in list(horizons):
        panel[f"fwd_{h}_pip"] = panel[f"fwd_{h}"] / pip
        panel[f"past_{h}_pip"] = panel[f"past_{h}"] / pip
    panel["fwd_close_pip"] = panel["fwd_close"] / pip
    return panel


def session_volume_shares(product: str, scope: str = "explore",
                          period: int = PERIOD) -> pd.DataFrame:
    """Per-session share of total session volume traded in each 30-minute block."""
    bars, _ = D.load_bars(product, scope=scope)
    bars = bars.assign(slot=(bars["mfo"] // period) * period)
    g = bars.groupby(["sdate", "slot"])["volume"].sum().reset_index()
    tot = g.groupby("sdate")["volume"].transform("sum")
    g["share"] = g["volume"] / tot
    return g
