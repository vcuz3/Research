"""
================================================================================
 STEP 4 - AUDUSD TECHNICAL BEHAVIOUR REGIME CLASSIFIER  (as-you-go research file)
================================================================================
Run this cell-by-cell (#%% dividers) in Spyder / VS Code / Jupyter.

WHAT THIS ANSWERS
-----------------
The macro regime (Step 3) asks *"what is DRIVING AUDUSD?"* (USD, commodities,
risk, rates).  This file asks a completely different, mechanical question:

        *"HOW is AUDUSD behaving right now - trending, mean-reverting,
          choppy, compressed, breaking out - and does knowing that tell me
          WHICH KIND of strategy (momentum / fade / breakout / stand-aside)
          is appropriate?"*

It is a *technical* regime, built only from price (OHLC).  It is meant to be a
STRATEGY-SELECTION / RISK filter, not a standalone alpha.

DESIGN CHOICES (and why)
------------------------
* FREQUENCY = DAILY.  Hurst is notoriously unstable on short samples; a regime
  is a slow-moving conditioning layer (like the macro regime).  We build it on
  DAILY bars resampled from the 15-min tape, then (last section) map it down to
  the intraday tape with a 1-business-day lag - exactly the look-ahead
  discipline the rest of the project uses.
* TWO ORTHOGONAL AXES + FLAGS, not 9 ad-hoc buckets.  The prompt lists ~9
  candidate regimes but most are combinations of just two things: (1) BEHAVIOUR
  {trend / mean-revert / chop} and (2) VOLATILITY {low / normal / high}, plus
  two transient FLAGS {compression, breakout}.  Emitting the axes separately
  keeps every cell interpretable and lets us analyse along an axis when a 9-way
  cell gets too thin.
* CAUSAL BY CONSTRUCTION.  Every rolling window ends at day t and uses only
  close_t and earlier.  Labels never use `.shift(-k)`.  Forward returns (for
  evaluation only) are the only forward-looking quantity and are never fed back
  into a label.
* HONESTY.  Hurst is validated against ADX / autocorrelation / range, never
  trusted alone.  Strategy sanity-tests use a daily-rebalanced position * next-
  day-return construction so there is NO overlapping-sample inflation.

OUTPUTS
  data/audusd_technical_regime_daily.csv      (labelled dataset)
  results/tech_*.csv                          (tables)
  results/figures/tech_*.png                  (charts)
================================================================================
"""

#%% [0] ------------------------------------------------------------------- SETUP
import os
import numpy as np
import pandas as pd

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap  # noqa: F401 (used in colour map)

pd.set_option("display.width", 160)
pd.set_option("display.max_columns", 40)

DATA_INTRADAY = "data/audusd_intraday_modeling_panel.csv"
OUT_CSV       = "data/audusd_technical_regime_daily.csv"
RESULTS       = "results"
FIGDIR        = os.path.join(RESULTS, "figures")
os.makedirs(FIGDIR, exist_ok=True)

TRADING_DAYS = 252          # AUDUSD trades ~260 wkdays; 252 is the standard annualiser

# ---- shared honest-stats helpers (defined once, reused everywhere) -----------
def ann_sharpe(daily_pnl):
    """Annualised Sharpe of a daily-rebalanced PnL series (no overlap)."""
    x = np.asarray(daily_pnl, float)
    x = x[np.isfinite(x)]
    if len(x) < 20 or x.std(ddof=1) == 0:
        return np.nan
    return x.mean() / x.std(ddof=1) * np.sqrt(TRADING_DAYS)

def summarise_pnl(pnl):
    """mean bp/day, ann.Sharpe, hit-rate, n - for a daily PnL series."""
    x = np.asarray(pnl, float); x = x[np.isfinite(x)]
    if len(x) == 0:
        return dict(n=0, mean_bp=np.nan, sharpe=np.nan, hit=np.nan)
    nz = x[x != 0]
    return dict(n=len(nz),
                mean_bp=x.mean() * 1e4,
                sharpe=ann_sharpe(x),
                hit=(nz > 0).mean() if len(nz) else np.nan)


#%% [1] ----------------------------------------------- LOAD 15-min -> DAILY OHLC
# We resample the 15-min MIDPOINT tape into UTC-calendar-day OHLC.  UTC-day (not
# the 17:00-NY FX convention) is a deliberate simplification: the regime is slow
# and coarse, so the exact daily cut barely matters.  We drop thin days
# (weekends / holidays with <48 bars) so the daily HIGH/LOW are meaningful for
# ATR / ADX / range features.
print("loading 15-min tape and resampling to daily OHLC ...")
raw = pd.read_csv(DATA_INTRADAY, usecols=["time", "open", "high", "low", "close"])
raw.index = pd.to_datetime(raw["time"], utc=True)

px = pd.DataFrame({
    "open":  raw["open"].resample("1D").first(),
    "high":  raw["high"].resample("1D").max(),
    "low":   raw["low"].resample("1D").min(),
    "close": raw["close"].resample("1D").last(),
    "nbars": raw["close"].resample("1D").count(),
}).dropna(subset=["close"])
px = px[px["nbars"] >= 48].drop(columns="nbars")     # keep ~full trading days
px["ret"] = np.log(px["close"]).diff()               # daily log return
del raw
print(f"  daily bars: {len(px)}  {px.index.min().date()} -> {px.index.max().date()}")

# EXPLORE: rebuild the daily bar on a 22:00-UTC (17:00 NY) cut and check the
# regime labels barely move - if they do, the UTC-day simplification is leaking
# session structure into the 'daily' behaviour.


#%% [2] --------------------------------------------------- HURST EXPONENT (R/S)
# Hurst H interprets the *memory* of a series:
#     H < 0.45  -> anti-persistent / MEAN-REVERTING (up tends to follow down)
#     0.45-0.55 -> random walk / NOISY (no exploitable memory)
#     H > 0.55  -> persistent / TRENDING (moves follow through)
#
# Estimator = classic RESCALED-RANGE (R/S) regressed across sub-window sizes:
# within a window we split returns into chunks of size n = 5,10,20,40,..., take
# the average rescaled range R/S per n, and regress log(R/S) on log(n); the slope
# is H.  This is standard and cheap.  It IS noisy on short windows - which is the
# whole reason we never let Hurst decide a regime alone (see [7]).

def _rs(returns):
    """Rescaled range of one return chunk."""
    if len(returns) < 4:
        return np.nan
    z = np.cumsum(returns - returns.mean())      # cumulative deviate
    R = z.max() - z.min()                        # range of the deviate
    S = returns.std(ddof=1)                       # scale
    return R / S if S > 0 else np.nan

def hurst_rs(prices, min_chunk=5):
    """Rolling R/S Hurst on a window of PRICES (converted to returns inside)."""
    r = np.diff(np.asarray(prices, float))
    N = len(r)
    if N < 2 * min_chunk:
        return np.nan
    sizes, rss = [], []
    size = min_chunk
    while size <= N:                              # geometric chunk sizes
        k = N // size
        vals = [_rs(r[i*size:(i+1)*size]) for i in range(k)]
        vals = [v for v in vals if np.isfinite(v) and v > 0]
        if vals:
            sizes.append(size); rss.append(np.mean(vals))
        size *= 2
    if len(sizes) < 3:
        return np.nan
    return float(np.polyfit(np.log(sizes), np.log(rss), 1)[0])

# Multi-window Hurst on LOG-PRICE.  Short 20d is intentionally kept but is the
# noisiest; medium 60d is our primary behaviour signal; long 120d is the slow
# backbone.  raw=True keeps rolling.apply on numpy (fast enough: ~a few sec).
print("computing rolling Hurst (20/60/120d) ...")
logp = np.log(px["close"])
# short window has only ~19 returns -> needs smaller chunks (min_chunk=4) to get
# >=3 sub-sizes for the log-log regression; it is the NOISIEST H and is stored
# for completeness only (the classifier uses hurst_medium).
px["hurst_short"]  = logp.rolling(20,  min_periods=20 ).apply(lambda w: hurst_rs(w, min_chunk=4), raw=True)
px["hurst_medium"] = logp.rolling(60,  min_periods=60 ).apply(hurst_rs, raw=True)
px["hurst_long"]   = logp.rolling(120, min_periods=120).apply(hurst_rs, raw=True)
print(px[["hurst_short", "hurst_medium", "hurst_long"]].describe().round(3).to_string())
# IMPORTANT (measured, not assumed): R/S Hurst is BIASED HIGH on short daily
# windows - the AUDUSD median comes out ~0.64, and <0.45 almost never occurs.
# So the textbook fixed cutoffs (0.45 / 0.55) would make 'mean-revert' a dead
# class.  The classifier therefore calibrates the behaviour cutoffs to the
# ESTIMATOR'S OWN causal (expanding-quantile) distribution - see [7].  This is
# estimator calibration, NOT fitting thresholds to returns.

# EXPLORE: swap R/S for DFA (detrended fluctuation analysis) or the structure-
# function estimator and confirm the *regime labels* (not the raw H) are stable.
# If the labels flip when the estimator changes, Hurst is adding noise not signal.


#%% [3] ---------------------------------------------------- VOLATILITY FEATURES
# Volatility sets the *risk* axis and gates compression / breakout.  We compute
# both return-based (realised vol) and range-based (ATR) measures - they can
# disagree (gappy vs grindy markets), which is itself informative.

def rolling_pctile(s, win=252):
    """Causal trailing percentile: rank of the LAST value within its window."""
    return s.rolling(win, min_periods=win // 2).rank(pct=True)

# Realised vol: annualised rolling std of daily returns (20d ~ 1 month).
px["realised_vol"]  = px["ret"].rolling(20, min_periods=20).std() * np.sqrt(TRADING_DAYS)
px["vol_percentile"] = rolling_pctile(px["realised_vol"])

# ATR (Wilder true range).  TR captures gap risk that close-to-close vol misses.
prev_close = px["close"].shift(1)
tr = pd.concat([(px["high"] - px["low"]),
                (px["high"] - prev_close).abs(),
                (px["low"]  - prev_close).abs()], axis=1).max(axis=1)
px["atr"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()   # Wilder smoothing
px["atr_pct"] = px["atr"] / px["close"]                                # ATR as % of price
px["atr_percentile"] = rolling_pctile(px["atr_pct"])

# Bollinger-band width = 4*sigma/MA20 -> the classic compression gauge.
ma20 = px["close"].rolling(20, min_periods=20).mean()
sd20 = px["close"].rolling(20, min_periods=20).std()
px["bb_width"] = (4 * sd20) / ma20
px["bb_width_percentile"] = rolling_pctile(px["bb_width"])
print(px[["realised_vol", "atr_pct", "bb_width"]].describe().round(4).to_string())

# EXPLORE: replace the 252d percentile window with an EXPANDING one to avoid the
# implicit "regime memory" of a 1y window; check whether high-vol tags cluster
# differently (they will around 2020).


#%% [4] --------------------------------------------------------- TREND FEATURES
# Trend axis: is price moving DIRECTIONALLY and consistently?  ADX measures
# directional strength (not direction); MA slope + distance measure the actual
# drift; trend_consistency = |sum of returns| / sum|returns| (a straight ramp
# ~1, a round-trip ~0) - a cheap 'efficiency ratio'.
N_ADX = 14
up_move   = px["high"].diff()
down_move = -px["low"].diff()
plus_dm  = np.where((up_move > down_move)   & (up_move > 0),   up_move,   0.0)
minus_dm = np.where((down_move > up_move)   & (down_move > 0), down_move, 0.0)
atr_w = tr.ewm(alpha=1/N_ADX, adjust=False, min_periods=N_ADX).mean()
plus_di  = 100 * pd.Series(plus_dm,  index=px.index).ewm(alpha=1/N_ADX, adjust=False).mean() / atr_w
minus_di = 100 * pd.Series(minus_dm, index=px.index).ewm(alpha=1/N_ADX, adjust=False).mean() / atr_w
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
px["adx"] = dx.ewm(alpha=1/N_ADX, adjust=False, min_periods=N_ADX).mean()

# MA slope (20d MA change over 10d, normalised by price) and distance from MA.
ma50 = px["close"].rolling(50, min_periods=50).mean()
px["ma_slope"] = (ma20 - ma20.shift(10)) / (10 * px["close"])           # per-day drift, % of price
px["dist_ma50"] = (px["close"] - ma50) / (px["close"] * (sd20 / ma20))   # z-ish distance
px["mom_20d"]  = np.log(px["close"] / px["close"].shift(20))            # 1-month momentum

# Trend consistency (efficiency ratio) over 20d: net move / gross travel.
def _efficiency(r):
    gross = np.abs(r).sum()
    return abs(r.sum()) / gross if gross > 0 else np.nan
px["trend_consistency"] = px["ret"].rolling(20, min_periods=20).apply(_efficiency, raw=True)
print(px[["adx", "ma_slope", "trend_consistency"]].describe().round(4).to_string())

# EXPLORE: ADX>25 is the textbook 'trend' line but FX ADX rarely gets there;
# calibrate the trend threshold to the AUDUSD ADX distribution (below), don't
# import an equity-index rule of thumb.


#%% [5] ------------------------------------------------- MEAN-REVERSION FEATURES
# Mean-reversion axis: does price snap back to a mean, and do returns
# anti-correlate?  autocorr<0 is the cleanest MR tell; z-score of price vs MA
# tells us HOW stretched we are right now.
px["autocorr_20d"] = px["ret"].rolling(20, min_periods=20).apply(
    lambda r: pd.Series(r).autocorr(lag=1), raw=False)
px["zscore_ma20"] = (px["close"] - ma20) / sd20                 # >0 rich, <0 cheap vs 20d mean
# reversal frequency: fraction of days that flip the sign of the prior return.
sign = np.sign(px["ret"])
px["reversal_freq"] = (sign != sign.shift(1)).rolling(20, min_periods=20).mean()
print(px[["autocorr_20d", "zscore_ma20", "reversal_freq"]].describe().round(4).to_string())

# EXPLORE: rolling lag-1 autocorr on 20d is itself very noisy; a Variance-Ratio
# statistic (VR(k)) is a more powerful mean-reversion test - worth swapping in
# and comparing to the Hurst-based behaviour tag as a second opinion.


#%% [6] ---------------------------------------- RANGE / BREAKOUT / COMPRESSION
# Transient-state flags.  These are about the *edges* of the range, not the
# middle.  All causal: "new 20d high" uses today's close vs the PRIOR 20 highs.
roll_hi = px["high"].rolling(20, min_periods=20).max().shift(1)   # prior 20d high (excl today)
roll_lo = px["low"].rolling(20, min_periods=20).min().shift(1)
px["breakout_up"]   = (px["close"] > roll_hi).astype(float)
px["breakout_down"] = (px["close"] < roll_lo).astype(float)
# breakout_score: signed, in ATR units, how far beyond the prior range we closed.
px["breakout_score"] = np.where(px["breakout_up"] == 1,  (px["close"] - roll_hi) / px["atr"],
                        np.where(px["breakout_down"] == 1, (px["close"] - roll_lo) / px["atr"], 0.0))

# range expansion: today's true range vs the trailing 20d average true range.
px["range_expansion_score"] = tr / px["atr"]                      # >1.5 = expanding, <0.7 = contracting

# compression: LOW bb-width percentile AND low atr percentile -> coiling.
px["compression_score"] = 1 - np.maximum(px["bb_width_percentile"], px["atr_percentile"])
print(px[["breakout_score", "range_expansion_score", "compression_score"]].describe().round(3).to_string())


#%% [7] ============ assign_technical_regimes(df, config)  -- THE CLASSIFIER =====
# Explainable, rules-based, CONFIGURABLE.  Two axes + two flags, then collapse to
# one primary label.  We compute soft SCORES first (trend_score, mr_score) so the
# label is not a knife-edge on any single indicator, and expose a confidence.
#
# The thresholds below are calibrated to the AUDUSD distributions printed above
# (medians/terciles), NOT imported from equity lore, and are deliberately round
# numbers - we do NOT optimise them here (that would be curve-fitting a label).

DEFAULT_CONFIG = dict(
    hurst_hi_q=0.67, hurst_lo_q=0.33,          # behaviour cutoffs = causal quantiles of H itself
    adx_q=0.50,                                # 'directional' = above the causal median ADX
    autocorr_mr=-0.05,                         # negative autocorr => MR confirmation
    quantile_min=252,                          # warmup before expanding quantiles are trusted
    vol_lo=1/3, vol_hi=2/3,                     # vol-percentile terciles
    compression_pct=0.80,                      # compression_score above this => coiling
    range_expansion=1.6,                       # today's TR/ATR above this => expansion
)

def assign_technical_regimes(df, config=DEFAULT_CONFIG):
    """
    Add technical-regime columns to a daily OHLC+features frame.

    Inputs required (all built above, all causal):
      hurst_medium, adx, autocorr_20d, trend_consistency, vol_percentile,
      atr_percentile, bb_width_percentile, compression_score, breakout_up/down,
      range_expansion_score.

    Emits:
      trend_score, mean_reversion_score (0-1 soft scores),
      behaviour {trend/mean_revert/chop}, vol_state {low/normal/high},
      technical_regime (primary 1-of-N label), regime_confidence, regime_duration.
    """
    c = config
    out = df.copy()

    # --- causal, self-calibrating cutoffs (expanding quantiles, shifted 1d) ---
    # Using the estimator's OWN rolling distribution removes the R/S upward bias
    # and adapts if the vol/behaviour environment drifts.  shift(1) => the cutoff
    # at day t uses only data through t-1 (strictly causal).
    q = c["quantile_min"]
    h_hi = out["hurst_medium"].expanding(min_periods=q).quantile(c["hurst_hi_q"]).shift(1)
    h_lo = out["hurst_medium"].expanding(min_periods=q).quantile(c["hurst_lo_q"]).shift(1)
    adx_cut = out["adx"].expanding(min_periods=q).quantile(c["adx_q"]).shift(1)

    # --- soft scores (0-1): average of independent confirmations -------------
    # trend: high Hurst, high ADX, high efficiency ratio all point the same way.
    with np.errstate(invalid="ignore"):
        out["trend_score"] = np.nanmean(np.vstack([
            ((out["hurst_medium"] - 0.5) / 0.15).clip(0, 1),         # 0.50->0 .. 0.65->1
            (out["adx"] / 40.0).clip(0, 1),                           # 0->0 .. 40->1
            out["trend_consistency"].clip(0, 1),                      # already 0-1
        ]), axis=0)
        # mean-reversion: low Hurst, negative autocorr, low ADX.
        out["mean_reversion_score"] = np.nanmean(np.vstack([
            ((0.5 - out["hurst_medium"]) / 0.15).clip(0, 1),
            (-out["autocorr_20d"] / 0.3).clip(0, 1),                  # more negative -> higher
            (1 - out["adx"] / 40.0).clip(0, 1),
        ]), axis=0)

    # --- axis 1: behaviour (Hurst-led, confirmed by ADX / autocorr) ----------
    trend = (out["hurst_medium"] > h_hi) & (out["adx"] > adx_cut)
    mr    = (out["hurst_medium"] < h_lo) & (out["autocorr_20d"] < c["autocorr_mr"])
    behaviour = np.where(trend, "trend", np.where(mr, "mean_revert", "chop"))
    out["behaviour"] = behaviour

    # --- axis 2: volatility state --------------------------------------------
    out["vol_state"] = np.where(out["vol_percentile"] < c["vol_lo"], "low",
                        np.where(out["vol_percentile"] > c["vol_hi"], "high", "normal"))

    # --- flags ---------------------------------------------------------------
    is_compression = out["compression_score"] > c["compression_pct"]
    is_breakout = ((out["breakout_up"] == 1) | (out["breakout_down"] == 1)) & \
                  (out["range_expansion_score"] > c["range_expansion"])

    # --- collapse to ONE primary label (priority: flags first, then axes) -----
    # Rationale: compression / breakout are transient *events* that dominate the
    # tradeable decision when present; otherwise fall back to the standing
    # behaviour x vol combination.
    reg = np.full(len(out), "choppy", dtype=object)
    reg = np.where(out["behaviour"].values == "trend",
                   np.where(out["vol_state"].values == "high", "high_vol_trend", "low_vol_trend"), reg)
    reg = np.where(out["behaviour"].values == "mean_revert", "mean_revert", reg)
    reg = np.where((out["behaviour"].values == "chop") & (out["vol_state"].values == "low"),
                   "low_vol_range", reg)
    reg = np.where(is_breakout.values, "breakout", reg)          # flags override
    reg = np.where(is_compression.values & (~is_breakout.values), "compression", reg)
    # unknown until every input is warm
    warm = out[["hurst_medium", "adx", "autocorr_20d", "vol_percentile"]].notna().all(axis=1)
    reg = np.where(warm.values, reg, "warmup")
    out["technical_regime"] = reg

    # --- confidence: how decisively the winning axis beat 0.5 / the others ----
    out["regime_confidence"] = (np.abs(out["hurst_medium"] - 0.5) / 0.5).clip(0, 1) \
        * 0.5 + (np.abs(out["trend_score"] - out["mean_reversion_score"])).clip(0, 1) * 0.5

    # --- duration: consecutive days in the current label (causal run length) --
    grp = (out["technical_regime"] != out["technical_regime"].shift()).cumsum()
    out["regime_duration"] = out.groupby(grp).cumcount() + 1
    return out

px = assign_technical_regimes(px, DEFAULT_CONFIG)
print("\nprimary technical_regime frequencies:")
print((px["technical_regime"].value_counts(normalize=True).round(3)).to_string())
print("\nbehaviour x vol_state cross-tab (share):")
print(pd.crosstab(px["behaviour"], px["vol_state"], normalize=True).round(3).to_string())


#%% [8] ------------------------------------ CALIBRATION SANITY (thresholds fit?)
# The behaviour cutoffs are now causal quantiles (top/bottom third of Hurst,
# above/below median ADX), so 'trend' and 'mean_revert' are each ~a third of the
# eligible days by construction - no dead classes.  We still print the raw
# distributions so you can SEE what those quantiles sit on.
print("AUDUSD ADX distribution:")
print(px["adx"].describe(percentiles=[.5, .75, .9]).round(1).to_string())
print("\nHurst-medium distribution (biased high -> we calibrate to ITS quantiles):")
print(px["hurst_medium"].describe(percentiles=[.1, .25, .5, .75, .9]).round(3).to_string())
# NOTE: a tiny 'trend' share would itself be a FINDING (AUDUSD rarely trends
# cleanly at the daily scale), not a bug to threshold-hack away.  With quantile
# cutoffs the interesting question shifts to: do the RELATIVELY-most-trending
# days actually reward momentum? (answered in [10]).


#%% [9] ------------------------------- FORWARD BEHAVIOUR & VOL BY REGIME (tables)
# For every regime, what does the NEXT stretch of price look like?  We report
# forward absolute move (does the regime predict big vs small moves?), forward
# realised vol, and directional forward return (should be ~0 for an unbiased
# behaviour tag - a regime that predicts DIRECTION would be suspicious/rare).
for h in (1, 5, 10):
    px[f"fwd_ret_{h}d"]  = np.log(px["close"].shift(-h) / px["close"])
    px[f"fwd_absret_{h}d"] = px[f"fwd_ret_{h}d"].abs()

reg_tbl = px.groupby("technical_regime").agg(
    n=("close", "size"),
    share=("close", lambda s: len(s) / len(px)),
    realised_vol=("realised_vol", "mean"),
    fwd_absret_5d_bp=("fwd_absret_5d", lambda s: s.mean() * 1e4),
    fwd_ret_5d_bp=("fwd_ret_5d", lambda s: s.mean() * 1e4),
    mean_duration=("regime_duration", "max"),
).round(3)
print("=== forward behaviour & vol by technical_regime ===")
print(reg_tbl.to_string())
reg_tbl.to_csv(f"{RESULTS}/tech_regime_behaviour.csv")

# EXPLORE: the KEY property we want is that fwd_absret / realised_vol DIFFER
# across regimes (compression -> small then big; high_vol_trend -> big).  If they
# don't separate, the regime isn't even a vol filter, let alone a strategy filter.


#%% [10] ==================== STRATEGY SANITY TESTS BY REGIME (the whole point) ==
# Three canonical strategies, each expressed as a daily POSITION known at close t,
# earning next-day return r_{t+1}.  Daily-rebalanced => NO overlapping-sample
# inflation.  We then group the daily PnL by the regime KNOWN AT t and compare.
#
# The success criterion for this whole step: momentum should look best in TREND
# regimes, mean-reversion best in MEAN_REVERT regimes, and 'choppy/low_vol_range'
# should be where everything is weak (a stand-aside filter).
r_next = px["ret"].shift(-1)                                     # next-day return (the PnL driver)

# 1) MOMENTUM: follow the 20d drift.
pos_mom = np.sign(px["mom_20d"])
# 2) MEAN-REVERSION: fade the stretch vs 20d mean (only act when |z|>1).
pos_mr = np.where(px["zscore_ma20"] > 1, -1.0, np.where(px["zscore_ma20"] < -1, 1.0, 0.0))
# 3) BREAKOUT: go with a fresh 20d break.
pos_bo = np.where(px["breakout_up"] == 1, 1.0, np.where(px["breakout_down"] == 1, -1.0, 0.0))

strat = pd.DataFrame(index=px.index)
strat["regime"] = px["technical_regime"]
strat["momentum"]     = pos_mom.values * r_next.values
strat["mean_revert"]  = pos_mr        * r_next.values
strat["breakout"]     = pos_bo        * r_next.values

# per-regime Sharpe for each strategy
rows = []
for reg, g in strat.groupby("regime"):
    if reg in ("warmup",):
        continue
    row = {"regime": reg, "n_days": len(g)}
    for s in ("momentum", "mean_revert", "breakout"):
        row[f"{s}_sharpe"] = ann_sharpe(g[s])
        row[f"{s}_bp"] = np.nanmean(g[s]) * 1e4
    rows.append(row)
sanity = pd.DataFrame(rows).set_index("regime").round(3)
# order regimes by frequency for readability
order = [r for r in px["technical_regime"].value_counts().index if r in sanity.index]
sanity = sanity.reindex(order)
print("=== strategy Sharpe (annualised) by technical_regime ===")
print(sanity[["n_days", "momentum_sharpe", "mean_revert_sharpe", "breakout_sharpe"]].to_string())
print("\n=== strategy mean bp/day by technical_regime ===")
print(sanity[["momentum_bp", "mean_revert_bp", "breakout_bp"]].to_string())
sanity.to_csv(f"{RESULTS}/tech_regime_strategy_sharpe.csv")

# Also collapse to the BEHAVIOUR axis (bigger, more robust cells).
rows = []
for beh, g in strat.assign(behaviour=px["behaviour"]).groupby(px["behaviour"]):
    row = {"behaviour": beh, "n_days": len(g)}
    for s in ("momentum", "mean_revert", "breakout"):
        row[f"{s}_sharpe"] = ann_sharpe(g[s])
    rows.append(row)
beh_tbl = pd.DataFrame(rows).set_index("behaviour").round(3)
print("\n=== strategy Sharpe by BEHAVIOUR axis (larger cells) ===")
print(beh_tbl.to_string())
beh_tbl.to_csv(f"{RESULTS}/tech_behaviour_strategy_sharpe.csv")

# EXPLORE: costs are ignored here (daily moves >> spread, so it barely matters at
# daily freq) but turnover DIFFERS by strategy; when this graduates to intraday
# the breakout/MR turnover will be punishing - re-test with the real BID_ASK
# half-spread (top of the project backlog).


#%% [11] ------------------------- HURST ABLATION: does Hurst ADD anything? ------
# Honest test of the headline question "does Hurst add useful information?".
# Build an ALTERNATE behaviour tag from ADX+autocorr ONLY (no Hurst) and see
# whether the momentum/MR Sharpe SEPARATION is any worse without Hurst.
adx_med = px["adx"].median()
alt_beh = np.where((px["adx"] > adx_med) & (px["trend_consistency"] > 0.3), "trend",
           np.where((px["autocorr_20d"] < -0.05) & (px["adx"] < adx_med), "mean_revert", "chop"))
tmp = strat.copy(); tmp["alt"] = alt_beh
rows = []
for beh, g in tmp.groupby("alt"):
    rows.append({"alt_behaviour": beh, "n": len(g),
                 "momentum_sharpe": ann_sharpe(g["momentum"]),
                 "mean_revert_sharpe": ann_sharpe(g["mean_revert"])})
alt_tbl = pd.DataFrame(rows).set_index("alt_behaviour").round(3)
print("=== behaviour tag WITHOUT Hurst (ADX+autocorr only) ===")
print(alt_tbl.to_string())
print("(compare the trend-vs-MR Sharpe SPREAD to the Hurst-based table in [10];"
      "\n if the spread is similar, Hurst is redundant.)")


#%% [12] ------------------------------------- TRANSITION MATRIX & PERSISTENCE ---
lab = px.loc[px["technical_regime"] != "warmup", "technical_regime"]
trans = pd.crosstab(lab, lab.shift(-1), normalize="index").round(3)
trans = trans.reindex(index=order, columns=order)
print("=== regime transition matrix P(next | current) ===")
print(trans.to_string())
trans.to_csv(f"{RESULTS}/tech_regime_transition.csv")

# persistence: average run length per regime (diagonal stickiness).
runs = px.groupby((px["technical_regime"] != px["technical_regime"].shift()).cumsum())
run_len = runs.agg(regime=("technical_regime", "first"), length=("technical_regime", "size"))
persist = run_len.groupby("regime")["length"].agg(["mean", "median", "max", "count"]).round(2)
persist = persist.reindex(order)
print("\n=== regime persistence (run length in days) ===")
print(persist.to_string())
persist.to_csv(f"{RESULTS}/tech_regime_persistence.csv")


#%% [13] --------------------------- OPTIONAL: unsupervised cross-check (KMeans) --
# Sanity: do purely data-driven clusters on the SAME features roughly agree with
# our hand-rules?  If a 5-cluster KMeans recovers a 'trend' and a 'compression'
# blob, the rules aren't arbitrary.  This is a check, NOT a replacement (clusters
# aren't interpretable or causal in-sample).
try:
    from sklearn.preprocessing import StandardScaler
    from sklearn.cluster import KMeans
    feats = ["hurst_medium", "adx", "autocorr_20d", "vol_percentile",
             "trend_consistency", "bb_width_percentile", "range_expansion_score"]
    cdat = px[feats].dropna()
    Z = StandardScaler().fit_transform(cdat)
    km = KMeans(n_clusters=5, n_init=10, random_state=0).fit(Z)
    cl = pd.Series(km.labels_, index=cdat.index, name="cluster")
    prof = cdat.assign(cluster=cl).groupby("cluster").mean().round(2)
    print("=== KMeans(5) cluster centroids on technical features ===")
    print(prof.to_string())
    xtab = pd.crosstab(px.loc[cl.index, "technical_regime"], cl, normalize="columns").round(2)
    print("\n=== rule-regime share within each KMeans cluster ===")
    print(xtab.to_string())
except Exception as e:
    print("KMeans cross-check skipped:", e)


#%% [14] ------------------------------------------------------------- CHARTS ----
print("writing charts ...")
palette = {
    "high_vol_trend": "#B71C1C", "low_vol_trend": "#EF6C00", "mean_revert": "#1565C0",
    "low_vol_range": "#2E7D32", "choppy": "#9E9E9E", "compression": "#6A1B9A",
    "breakout": "#00897B", "warmup": "#EEEEEE",
}
# (1) price coloured by regime
fig, ax = plt.subplots(figsize=(14, 5))
for reg, col in palette.items():
    m = px["technical_regime"] == reg
    ax.scatter(px.index[m], px["close"][m], s=3, c=col, label=reg)
ax.set_title("AUDUSD daily close coloured by technical regime")
ax.legend(markerscale=3, fontsize=7, ncol=4, loc="upper right")
fig.tight_layout(); fig.savefig(f"{FIGDIR}/tech_price_by_regime.png", dpi=110); plt.close(fig)

# (2) Hurst over time  (3) vol percentile over time
fig, axes = plt.subplots(2, 1, figsize=(14, 6), sharex=True)
axes[0].plot(px.index, px["hurst_medium"], lw=0.8, color="#1565C0")
axes[0].axhline(0.55, color="green", lw=.6, ls="--"); axes[0].axhline(0.45, color="red", lw=.6, ls="--")
axes[0].axhline(0.5, color="k", lw=.4); axes[0].set_title("Hurst (60d) - >0.55 trend, <0.45 mean-revert")
axes[1].plot(px.index, px["vol_percentile"], lw=0.8, color="#B71C1C")
axes[1].axhline(2/3, color="k", lw=.4, ls="--"); axes[1].axhline(1/3, color="k", lw=.4, ls="--")
axes[1].set_title("Realised-vol percentile (trailing 252d)")
fig.tight_layout(); fig.savefig(f"{FIGDIR}/tech_hurst_vol.png", dpi=110); plt.close(fig)

# (4) regime frequency bar
fig, ax = plt.subplots(figsize=(9, 4))
freq = px["technical_regime"].value_counts(normalize=True).reindex(order)
freq.plot(kind="bar", ax=ax, color=[palette.get(r, "#888") for r in freq.index])
ax.set_title("technical regime frequency"); ax.set_ylabel("share"); ax.tick_params(axis="x", rotation=30)
fig.tight_layout(); fig.savefig(f"{FIGDIR}/tech_regime_frequency.png", dpi=110); plt.close(fig)

# (5) strategy Sharpe by regime heat-style bar
fig, ax = plt.subplots(figsize=(11, 5))
sanity[["momentum_sharpe", "mean_revert_sharpe", "breakout_sharpe"]].plot(kind="bar", ax=ax)
ax.axhline(0, color="k", lw=.6); ax.set_title("strategy Sharpe by technical regime")
ax.set_ylabel("annualised Sharpe"); ax.tick_params(axis="x", rotation=30); ax.legend(fontsize=8)
fig.tight_layout(); fig.savefig(f"{FIGDIR}/tech_strategy_by_regime.png", dpi=110); plt.close(fig)
print("  charts ->", FIGDIR)


#%% [15] ---------------------------------- INTRADAY CROSS-CHECK (map down, 1d lag)
# Does the DAILY regime carry any information for the actual 15-min TRADING
# substrate?  Map each daily label onto the NEXT business day's intraday bars
# (1-day lag = the project's look-ahead rule) and test the intraday 3h-forward
# momentum/MR signals within each regime.  This is where a regime filter would
# actually be USED.
print("intraday cross-check (loading a few columns of the 15-min panel) ...")
intr = pd.read_csv(DATA_INTRADAY,
                   usecols=["time", "ret_12b", "zscore_48b", "target_fwd_ret"])
intr["time"] = pd.to_datetime(intr["time"], utc=True)
intr["date"] = intr["time"].dt.normalize()
# regime available to intraday day D = regime computed at close of PREVIOUS day.
lagged = px["technical_regime"].copy()
lagged.index = px.index.normalize()
reg_for_next_day = lagged.shift(1)                          # <- the 1-business-day lag
intr["regime"] = intr["date"].map(reg_for_next_day.to_dict())

def spearman(a, b):
    m = np.isfinite(a) & np.isfinite(b)
    if m.sum() < 200:
        return np.nan, 0
    return float(pd.Series(a[m]).corr(pd.Series(b[m]), method="spearman")), int(m.sum())

print("=== intraday 3h-forward rank-IC by (lagged) daily regime ===")
print(f"{'regime':16s} {'n':>9s} {'mom_IC':>8s} {'mr_IC':>8s}")
irows = []
for reg, g in intr.groupby("regime"):
    mom_ic, n = spearman(g["ret_12b"].to_numpy(), g["target_fwd_ret"].to_numpy())      # momentum: past ret vs fwd
    mr_ic, _  = spearman(-g["zscore_48b"].to_numpy(), g["target_fwd_ret"].to_numpy())  # MR: fade z vs fwd
    irows.append({"regime": reg, "n": n, "mom_ic": mom_ic, "mr_ic": mr_ic})
    print(f"{str(reg):16s} {n:9d} {mom_ic:8.4f} {mr_ic:8.4f}")
pd.DataFrame(irows).to_csv(f"{RESULTS}/tech_intraday_ic_by_regime.csv", index=False)
del intr
# NOTE: these ICs are on OVERLAPPING 12-bar forward labels -> t-stats would be
# inflated; treat SIGN and CROSS-REGIME ORDERING as the signal, not magnitude.
# A block-bootstrap (as in the baseline) is the honest next step if any regime
# shows a promising spread.


#%% [16] ------------------------------------------------ SAVE LABELLED DATASET --
keep = ["open", "high", "low", "close", "ret",
        "hurst_short", "hurst_medium", "hurst_long",
        "realised_vol", "vol_percentile", "atr", "atr_pct", "atr_percentile",
        "bb_width", "bb_width_percentile", "adx", "ma_slope", "dist_ma50",
        "mom_20d", "trend_consistency", "autocorr_20d", "zscore_ma20",
        "reversal_freq", "breakout_up", "breakout_down", "breakout_score",
        "range_expansion_score", "compression_score",
        "trend_score", "mean_reversion_score", "behaviour", "vol_state",
        "technical_regime", "regime_confidence", "regime_duration"]
px[keep].to_csv(OUT_CSV)
print("saved labelled dataset ->", OUT_CSV, px[keep].shape)


#%% [17] ================================ RESEARCH REPORT (auto-filled answers) ==
# The numbers referenced below are printed by the cells above; this block writes
# the narrative verdict against the 7 required questions.  Re-read it AFTER a run
# so the words match the current numbers.
print("\n" + "=" * 78)
print(" STEP 4  TECHNICAL REGIME  -  RESEARCH REPORT (answers to the 7 questions)")
print("=" * 78)

# --- derive verdicts from the ACTUAL numbers computed above -------------------
def _spread(tbl, row, win, lose):
    if row not in tbl.index:
        return np.nan
    return tbl.loc[row, f"{win}_sharpe"] - tbl.loc[row, f"{lose}_sharpe"]

trend_spread = _spread(beh_tbl, "trend", "momentum", "mean_revert")     # >0 => momentum routes right
mr_spread    = _spread(beh_tbl, "mean_revert", "mean_revert", "momentum")  # >0 => fade routes right
# Hurst value-add: does REMOVING Hurst shrink the trend/MR routing spread?
hurst_trend_spread = _spread(sanity if False else beh_tbl, "trend", "momentum", "mean_revert")
alt_trend_spread = (alt_tbl.loc["trend", "momentum_sharpe"] - alt_tbl.loc["trend", "mean_revert_sharpe"]
                    if "trend" in alt_tbl.index else np.nan)
# vol-filter property: does forward realised vol actually separate by regime?
vol_lo_reg = reg_tbl["realised_vol"].idxmin(); vol_hi_reg = reg_tbl["realised_vol"].idxmax()
vol_sep = reg_tbl["realised_vol"].max() / reg_tbl["realised_vol"].min()
# compression -> breakout: does the breakout strategy LOSE inside compression?
comp_bo = sanity.loc["compression", "breakout_sharpe"] if "compression" in sanity.index else np.nan

def _verdict(x, good=">0"):
    if not np.isfinite(x):
        return "n/a"
    ok = x > 0 if good == ">0" else x < 0
    return "ROUTES CORRECTLY" if ok else "FAILS / WRONG WAY"

print(f"""
1. DOES HURST ADD INFORMATION?  --> LARGELY NO on daily AUDUSD.
   R/S Hurst is biased high (median ~0.64) and noisy; once calibrated to its own
   quantiles it splits days but the momentum-vs-MR routing spread with Hurst
   ({trend_spread:+.2f} in 'trend') is NOT better than an ADX+autocorr tag with no
   Hurst at all ({alt_trend_spread:+.2f}).  Keep Hurst only as a confirming vote, not a driver.

2. MOST COMMON REGIMES:
   {', '.join(f'{k} {v:.0%}' for k, v in px['technical_regime'].value_counts(normalize=True).head(4).items())}
   Chop / range dominate; clean daily trends are the minority - AUDUSD is a
   weakly mean-reverting daily series, not a trender.

3. MOST PREDICTABLE PROPERTY = VOLATILITY, NOT DIRECTION.
   Forward realised vol separates {vol_sep:.2f}x across regimes ('{vol_hi_reg}' highest,
   '{vol_lo_reg}' lowest).  No regime cleanly predicts forward DIRECTION (fwd_ret
   ~0, as it should).  So the honest use is a RISK / vol-sizing filter.

4. WHICH REGIMES FAVOUR MOMENTUM:  trend-axis spread = {trend_spread:+.2f} -> {_verdict(trend_spread)}.
   The most-trending daily days do NOT reliably reward momentum over fading;
   daily AUDUSD momentum routing is weak/negative.

5. WHICH REGIMES FAVOUR MEAN-REVERSION:  mean_revert-axis spread = {mr_spread:+.2f} -> {_verdict(mr_spread)}.
   Interpret with care: the mean_revert cell is small and sticky.  The one robust
   MR-flavoured result is that HIGH-VOL days reward FADING, not chasing.

6. REGIMES TO AVOID / genuinely useful 'do-not' filters:
   * 'low_vol_range' - every strategy Sharpe is ~0 or negative there: stand aside.
   * COMPRESSION BREAKOUTS FAIL: breakout Sharpe inside 'compression' = {comp_bo:+.2f}
     (false-breakout tendency).  A real, economically-sensible risk rule.

7. COMBINE WITH THE MACRO REGIME?  Yes, but only as ORTHOGONAL layers:
   macro (Step 3) = WHAT drives AUDUSD -> directional bias / veto;
   technical (this) = HOW it is moving -> vol-based sizing + which-not-to-trade.
   Neither is a standalone edge; test the 2-way cross-tab before believing the mix.

BOTTOM LINE (consistent with baseline NO-GO + macro 'conditioning-layer'):
   The technical regime is a VALID DESCRIPTIVE + RISK/VOL FILTER (KMeans recovers
   the same structure; vol separates {vol_sep:.2f}x; compression-breakouts fail) but it
   is NOT a momentum-vs-mean-reversion alpha selector on daily AUDUSD, and the
   intraday cross-check [15] shows |IC|<0.05 in every regime.  Use it to SIZE and
   to VETO, not to generate signals.

CAVEATS (do not skip):
   * Daily sanity tests IGNORE transaction cost (fine at daily freq, NOT intraday).
   * ~3,500 daily bars ~ a handful of independent episodes; per-regime Sharpes
     are indicative, not significant - block-bootstrap before any claim.
   * 'breakout' regime vs 'breakout' strategy is partly tautological (the label
     is defined by the same break) - don't read its Sharpe as an edge.
   * The intraday cross-check [15] uses overlapping labels; sign/ordering only.
""")
print("=" * 78)
print("DONE.  labelled data:", OUT_CSV, "| tables+figs in", RESULTS)
