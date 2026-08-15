"""Causal cross-sectional features for the NDX noise-VWAP filter study.

The pre-screen (`ndx_noise_vwap`) measures each stock's faithful strategy return.
This module adds the *cross-sectional* half: for each (ticker, date) it builds
three CAUSAL features that stand in for where the risk-on bid concentrates, and
ranks them across the basket as of that date. A later filter selects trades whose
name sits in a chosen tail of one feature.

The three axes (a pre-registered battery — see the notebook):

  * ``size``  -- log trailing-mean daily *dollar* volume (price x volume). An
    in-data proxy for market cap / index weight (bigger, more-traded names).
  * ``mom``   -- trailing simple return (prior close over L sessions ago). The
    "recent winners" tilt. Deliberately kept SEPARATE from size because big caps
    are partly just past winners; keeping them apart shows which is load-bearing.
  * ``attn``  -- prior-session dollar volume over its trailing mean (abnormal
    volume). A causal proxy for "this name is in the headlines", with NO hindsight
    theme list (that would be leakage).

Causality is the whole point. Every feature for date D is built only from data
STRICTLY BEFORE D (a per-ticker date-sort then ``shift(1)`` on already-trailing
statistics), so it is known at the session open and cannot see the trade it will
be used to filter. `assert_causal` checks this on request.

Cross-sectional ranks are percentiles across all names with a valid feature on
that date (the basket), so a trade inherits its name's position in the basket --
the "relative to basket" framing the study is about.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

FEATURES = ("size", "mom", "attn")


def daily_panel(loaded: dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Per (ticker, date): last RTH close and total daily dollar volume."""
    rows = []
    for t, b in loaded.items():
        close = b.groupby("date")["close"].last()
        dvol = (b["close"] * b["volume"]).groupby(b["date"]).sum()
        d = pd.DataFrame({"close": close, "dvol": dvol}).reset_index()
        d["ticker"] = t
        rows.append(d)
    return pd.concat(rows, ignore_index=True)


def name_features(panel: pd.DataFrame, *, size_lb: int = 60, mom_lb: int = 60,
                  attn_lb: int = 60, min_frac: float = 0.5) -> pd.DataFrame:
    """Add causal size/mom/attn and their per-date cross-sectional percentile rank.

    All three are functions of data strictly before each date (trailing stats then
    shift(1)); `*_rk` is the percentile within the basket on that date.
    """
    out = []
    for _, d in panel.groupby("ticker", sort=False):
        d = d.sort_values("date").copy()
        mp_s = max(10, int(size_lb * min_frac))
        mp_a = max(10, int(attn_lb * min_frac))
        d["size"] = np.log(d["dvol"].rolling(size_lb, min_periods=mp_s).mean().shift(1))
        d["mom"] = d["close"].shift(1) / d["close"].shift(1 + mom_lb) - 1.0
        base = d["dvol"].rolling(attn_lb, min_periods=mp_a).mean().shift(1)
        d["attn"] = d["dvol"].shift(1) / base
        out.append(d)
    p = pd.concat(out, ignore_index=True)
    for c in FEATURES:
        p[f"{c}_rk"] = p.groupby("date")[c].rank(pct=True)
    return p


def attach_to_trades(trades: pd.DataFrame, feats: pd.DataFrame) -> pd.DataFrame:
    """Left-join per-(ticker, date) feature ranks onto the per-trade frame."""
    cols = ["ticker", "date"] + list(FEATURES) + [f"{c}_rk" for c in FEATURES]
    return trades.merge(feats[cols], on=["ticker", "date"], how="left")


def assert_causal(panel: pd.DataFrame, feats: pd.DataFrame, ticker: str,
                  size_lb: int = 60, mom_lb: int = 60, attn_lb: int = 60) -> None:
    """Recompute one name's features at a cutoff using ONLY prior rows and confirm
    they match the full-history values -> no look-ahead in the construction."""
    d = panel[panel["ticker"] == ticker].sort_values("date").reset_index(drop=True)
    if len(d) < mom_lb + 5:
        return
    i = len(d) - 1
    hist = d.iloc[:i]  # strictly before date d.iloc[i]
    size_i = np.log(hist["dvol"].tail(size_lb).mean())
    mom_i = hist["close"].iloc[-1] / hist["close"].iloc[-1 - mom_lb] - 1.0
    attn_i = hist["dvol"].iloc[-1] / hist["dvol"].tail(attn_lb).mean()
    f = feats[(feats["ticker"] == ticker) & (feats["date"] == d.iloc[i]["date"])].iloc[0]
    for name, ref in (("size", size_i), ("mom", mom_i), ("attn", attn_i)):
        got = f[name]
        if pd.notna(got) and pd.notna(ref):
            assert abs(got - ref) < 1e-9, f"{name} not causal: {got} vs {ref}"


if __name__ == "__main__":
    # tiny self-test on synthetic 2-name data
    rng = np.random.default_rng(0)
    dates = pd.bdate_range("2020-01-01", periods=200)
    frames = {}
    for t in ("AAA", "BBB"):
        px = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, len(dates))))
        rows = []
        for dt, p in zip(dates, px):
            for tod in range(570, 960, 30):
                rows.append({"date": dt, "tod": tod, "close": p,
                             "volume": rng.uniform(1e3, 1e4)})
        frames[t] = pd.DataFrame(rows)
    panel = daily_panel(frames)
    feats = name_features(panel)
    assert_causal(panel, feats, "AAA")
    assert_causal(panel, feats, "BBB")
    assert set(f"{c}_rk" for c in FEATURES) <= set(feats.columns)
    # ranks are per-date percentiles in [0,1]
    rk = feats.dropna(subset=["size_rk"])["size_rk"]
    assert rk.between(0, 1).all()
    print("ndx_xsection self-test PASS:", feats.shape, "features", list(FEATURES))
