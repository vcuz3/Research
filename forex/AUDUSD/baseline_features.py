"""
baseline_features.py — reusable feature/target builder for the AUDUSD
15-minute baseline predictive model (Step 2).

Everything here is CAUSAL:
  * rolling features use only trailing bars (no future values, no centering),
  * targets are explicitly forward-looking (that is their job),
  * lower-frequency conditioning features (f_*, macro_*) arrive in the panel
    already lagged by one business day (enforced upstream in
    build_intraday_panel.py) so we consume them as-is.

The intraday panel already ships a good set of technical + conditioning
features.  This module ADDS the targets requested by the Step-2 brief plus a
handful of extra interpretable AUDUSD technicals (ATR, vol/ATR percentiles,
distance-from-MA, range expansion) and NY-time session labels, without ever
touching the future.

Bar spacing is 15 minutes (~95-96 bars / trading day), so:
    1 hour  =  4 bars
    4 hours = 16 bars
    1 day   = 96 bars
"""

from __future__ import annotations

import numpy as np
import pandas as pd

# ---------------------------------------------------------------- constants ---
BARS_PER_HOUR = 4
HORIZONS_BARS = {"h1h": 4, "h4h": 16, "h1d": 96}      # forward-return horizons
DAY_BARS = 96

# Default *one-way* transaction cost in price-return units.
# AUDUSD retail spread is ~0.4-0.8 pip; 1 pip = 0.0001.  We have no BID_ASK pull
# yet (see CLAUDE.md gotcha #2), so this is an explicit placeholder to be swept.
DEFAULT_ONE_WAY_COST = 0.00005          # 0.5 pip one-way  (1.0 pip round trip)


# ------------------------------------------------------------------ loading ---
def load_panel(path: str = "data/audusd_intraday_modeling_panel.csv") -> pd.DataFrame:
    """Load the intraday modeling panel, parse the UTC time index, sort."""
    df = pd.read_csv(path, parse_dates=["time"])
    df = df.sort_values("time").reset_index(drop=True)
    # downcast the numeric block to save memory on the 332k x 57 panel
    floatcols = df.select_dtypes("float64").columns
    df[floatcols] = df[floatcols].astype("float32")
    return df


# ------------------------------------------------------------------ targets ---
def add_targets(
    df: pd.DataFrame,
    horizons: dict[str, int] = HORIZONS_BARS,
    cost_buffer: float = DEFAULT_ONE_WAY_COST,
    vol_col: str = "realized_vol_48b",
) -> pd.DataFrame:
    """
    Add forward-return, classification and risk-adjusted targets for each
    horizon.  All targets are forward log-returns of `close`.

    For horizon h (bars) and column suffix `tag`:
        y_ret_{tag}     forward log return close[t+h]/close[t]
        y_up_{tag}      1 if fwd ret >  +cost_buffer
        y_down_{tag}    1 if fwd ret <  -cost_buffer
        y_neutral_{tag} 1 otherwise           (|fwd ret| <= cost_buffer)
        y_dir_{tag}     sign(fwd ret) in {-1,0,+1} (0 only on exact tie)
        y_ret_vol_{tag} fwd ret / trailing realised vol   (vol-scaled)
        y_ret_atr_{tag} fwd ret / trailing ATR%           (ATR-scaled)
    """
    out = df.copy()
    logc = np.log(out["close"].astype("float64"))

    # trailing risk scalers (already causal / trailing in the panel + here)
    trail_vol = out[vol_col].astype("float64").replace(0, np.nan)
    if "atr_pct_14b" not in out:
        out = add_audusd_technicals(out)          # ensures atr_pct_14b exists
    trail_atr = out["atr_pct_14b"].astype("float64").replace(0, np.nan)

    for tag, h in horizons.items():
        fwd = logc.shift(-h) - logc                        # forward log return
        out[f"y_ret_{tag}"] = fwd.astype("float32")
        out[f"y_up_{tag}"] = (fwd > cost_buffer).astype("float32")
        out[f"y_down_{tag}"] = (fwd < -cost_buffer).astype("float32")
        out[f"y_neutral_{tag}"] = (fwd.abs() <= cost_buffer).astype("float32")
        out[f"y_dir_{tag}"] = np.sign(fwd).astype("float32")
        out[f"y_ret_vol_{tag}"] = (fwd / trail_vol).astype("float32")
        out[f"y_ret_atr_{tag}"] = (fwd / trail_atr).astype("float32")

    return out


# --------------------------------------------------------- extra technicals ---
def add_audusd_technicals(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add interpretable, strictly-trailing AUDUSD technicals on top of what the
    panel already carries.  Nothing here uses future bars.
    """
    out = df
    high = out["high"].astype("float64")
    low = out["low"].astype("float64")
    close = out["close"].astype("float64")
    prev_close = close.shift(1)

    # --- ATR (Wilder-style true range, simple rolling mean) as % of price -----
    tr = pd.concat(
        [(high - low),
         (high - prev_close).abs(),
         (low - prev_close).abs()],
        axis=1,
    ).max(axis=1)
    atr14 = tr.rolling(14, min_periods=14).mean()
    out["atr_pct_14b"] = (atr14 / close).astype("float32")

    # --- percentile ranks of vol / ATR over a trailing window ----------------
    # rolling rank of the *last* value within the trailing window -> in [0,1],
    # strictly causal (window ends at the current bar).
    def _trailing_pctile(s: pd.Series, win: int) -> pd.Series:
        return s.rolling(win, min_periods=win // 2).apply(
            lambda a: (a[-1] >= a).mean(), raw=True
        )

    out["realized_vol_pctile_500b"] = _trailing_pctile(
        out["realized_vol_48b"].astype("float64"), 500
    ).astype("float32")
    out["atr_pctile_500b"] = _trailing_pctile(
        out["atr_pct_14b"].astype("float64"), 500
    ).astype("float32")

    # --- distance from moving averages (trailing SMA) ------------------------
    for n in (48, 192):                     # 12h and 48h SMAs
        sma = close.rolling(n, min_periods=n).mean()
        out[f"dist_sma_{n}b"] = ((close - sma) / sma).astype("float32")

    # --- range expansion / contraction ---------------------------------------
    # current 1-bar range vs its trailing average -> >1 expansion, <1 contraction
    rng = (high - low)
    out["range_expansion_48b"] = (
        rng / rng.rolling(48, min_periods=24).mean()
    ).astype("float32")

    # --- short-term momentum not already in the panel ------------------------
    logc = np.log(close)
    out["ret_24b"] = (logc - logc.shift(24)).astype("float32")   # 6h momentum

    return out


# ------------------------------------------------------------- NY sessions ----
def add_ny_sessions(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add FX session labels using New York local time (handles DST correctly).

    Buckets (NY local hour):
        asia          18:00-03:00   (Sydney/Tokyo)
        london        03:00-08:00
        ny            08:00-12:00   (London/NY overlap + NY morning)
        ny_afternoon  12:00-16:00
        rollover      16:00-18:00   (5pm ET rollover / illiquid)
    Emits one-hot columns sess2_* plus a categorical `session_ny`.
    """
    out = df
    ny = out["time"].dt.tz_convert("America/New_York")
    h = ny.dt.hour

    def bucket(hr: int) -> str:
        if 18 <= hr or hr < 3:
            return "asia"
        if 3 <= hr < 8:
            return "london"
        if 8 <= hr < 12:
            return "ny"
        if 12 <= hr < 16:
            return "ny_afternoon"
        return "rollover"                    # 16-18

    out["session_ny"] = h.map(bucket).astype("category")
    for name in ["asia", "london", "ny", "ny_afternoon", "rollover"]:
        out[f"sess2_{name}"] = (out["session_ny"] == name).astype("float32")
    return out


# ------------------------------------------------------ feature-column sets ---
# Technical / intraday features (all causal, all present after the adds above).
INTRADAY_FEATURES = [
    "ret_1b", "ret_3b", "ret_6b", "ret_12b", "ret_24b", "ret_48b",
    "realized_vol_48b", "realized_vol_pctile_500b",
    "atr_pct_14b", "atr_pctile_500b",
    "range_1b", "range_expansion_48b",
    "zscore_48b",
    "dist_sma_48b", "dist_sma_192b",
    "sess2_asia", "sess2_london", "sess2_ny", "sess2_ny_afternoon", "sess2_rollover",
]

# Daily cross-asset / macro conditioning features already in the panel.
def conditioning_features(df: pd.DataFrame) -> list[str]:
    return [c for c in df.columns if c.startswith("f_") or c.startswith("macro_")]


def build_all(
    path: str = "data/audusd_intraday_modeling_panel.csv",
    cost_buffer: float = DEFAULT_ONE_WAY_COST,
) -> pd.DataFrame:
    """Full pipeline: load -> technicals -> NY sessions -> targets."""
    df = load_panel(path)
    df = add_audusd_technicals(df)
    df = add_ny_sessions(df)
    df = add_targets(df, cost_buffer=cost_buffer)
    return df


if __name__ == "__main__":
    d = build_all()
    print("rows", len(d), "cols", d.shape[1])
    print("intraday feats:", len(INTRADAY_FEATURES),
          "conditioning feats:", len(conditioning_features(d)))
    print(d["session_ny"].value_counts())
    print(d.filter(like="y_ret_").describe().T[["mean", "std", "count"]])
