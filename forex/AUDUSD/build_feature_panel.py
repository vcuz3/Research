"""
Assemble one modeling panel from the two data layers:

  * monthly point-in-time MACRO factor scores  (download_public_macro_factors.py)
  * daily MARKET / cross-asset features         (download_market_factors.py)

Alignment rules (all designed to avoid look-ahead):
  * Daily market features are used as-of their own date.
  * Monthly macro scores are stamped at month-end (already "as released by that
    date" via ALFRED), then made available on the NEXT business day and
    forward-filled. A small extra lag can be added for extra caution.

This is the substrate for a backtest. The DAILY forward return target here is a
PLACEHOLDER: the actual project goal is an INTRADAY directional strategy, whose
target and price features must come from an intraday vendor (see
data/external_data_registry.csv). The intraday hook is marked TODO below.

    python build_feature_panel.py
    -> data/audusd_modeling_panel_daily.csv
"""

from pathlib import Path

import numpy as np
import pandas as pd


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"

MACRO_EXTRA_LAG_DAYS = 1   # extra caution on top of the next-business-day stamp
TARGET_HORIZONS = [1, 5, 21]  # forward log-return horizons for the placeholder target


def load_layers():
    macro = pd.read_csv(DATA_DIR / "audusd_point_in_time_macro_factors.csv",
                        parse_dates=["date"], index_col="date")
    market = pd.read_csv(DATA_DIR / "audusd_market_factors_daily.csv",
                         parse_dates=["date"], index_col="date")
    return macro, market


def align_macro_to_daily(macro, daily_index):
    """Put month-end macro scores on the daily grid without look-ahead."""
    # NB: equal_weight_macro_score already ends in "_score", so build a de-duped,
    # order-preserving keep list to avoid a duplicate column downstream.
    score_cols = [c for c in macro.columns if c.endswith("_score")]
    keep = list(dict.fromkeys(score_cols + ["n_macro_factors"]))
    keep = [c for c in keep if c in macro.columns]
    m = macro[keep].copy()

    # month-end value becomes visible the next business day (+ optional extra lag)
    m.index = m.index + pd.offsets.BusinessDay(1) + pd.Timedelta(days=MACRO_EXTRA_LAG_DAYS)
    daily = m.reindex(daily_index.union(m.index)).ffill().reindex(daily_index)
    return daily.add_prefix("macro_")


def build_panel():
    macro, market = load_layers()
    daily_index = market.index

    macro_daily = align_macro_to_daily(macro, daily_index)

    # market file already carries raw levels + f_ features; keep the f_ features
    # plus a few raw levels useful downstream
    feature_cols = [c for c in market.columns if c.startswith("f_")]
    raw_keep = [c for c in ["audusd", "vix", "dxy_broad"] if c in market.columns]
    panel = pd.concat([market[raw_keep], market[feature_cols], macro_daily], axis=1)

    # -------- placeholder target: forward AUDUSD log returns (DAILY) ---------- #
    # TODO(intraday): replace `audusd` (daily DEXUSAL) with intraday AUDUSD bars
    #   and define an intraday forward-return / directional target here. Everything
    #   above this line is reusable as slow conditioning features for that model.
    logpx = np.log(panel["audusd"])
    for h in TARGET_HORIZONS:
        panel[f"target_fwd_ret_{h}d"] = logpx.shift(-h) - logpx
        panel[f"target_fwd_dir_{h}d"] = np.sign(panel[f"target_fwd_ret_{h}d"])

    panel.index.name = "date"
    panel.to_csv(DATA_DIR / "audusd_modeling_panel_daily.csv")

    feat_cols = [c for c in panel.columns
                 if c.startswith(("f_", "macro_")) or c in raw_keep]
    print("Saved:", DATA_DIR / "audusd_modeling_panel_daily.csv")
    print("Panel shape:", panel.shape)
    print("Date range:", panel.index.min().date(), "to", panel.index.max().date())
    print(f"\n{len(feat_cols)} feature columns, {len(TARGET_HORIZONS)} target horizons.")

    # quick, purely informational in-sample sniff test (NOT a backtest):
    # does the equal-weight macro composite line up with fwd 21d returns?
    sub = panel[["macro_equal_weight_macro_score", "target_fwd_ret_21d"]].dropna()
    if len(sub) > 100:
        corr = sub.corr().iloc[0, 1]
        print(f"\nIn-sample corr(macro composite, fwd 21d ret) = {corr:+.3f} "
              f"over {len(sub)} days (informational only, not tradable evidence).")


if __name__ == "__main__":
    build_panel()
