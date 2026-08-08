"""Build the self-contained trade regime tester notebook with stdlib only."""

from __future__ import annotations

import json
from pathlib import Path
from textwrap import dedent


HERE = Path(__file__).resolve().parent
OUTPUT = HERE / "trade_regime_tester.ipynb"


def markdown(source: str) -> dict:
    return {
        "cell_type": "markdown",
        "metadata": {},
        "source": dedent(source).strip().splitlines(keepends=True),
    }


def code(source: str) -> dict:
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": dedent(source).strip().splitlines(keepends=True),
    }


cells: list[dict] = []

cells.append(markdown(r"""
# Reusable trade regime tester

This notebook takes a **frozen strategy's completed trades** and asks when that
strategy has historically worked. It deliberately contains no entry, exit,
fill, or sizing logic. The only strategy-specific input is a trades table; the
market, macro, benchmark, and event adapters are reusable.

The default example reads the frozen `AUDUSD / sma_80` trades produced by
`forex/exploration_3`. Edit the configuration cell to change the instrument,
timeframe, sample dates, outcome column, or frozen-configuration filters.

Scientific guardrails:

- Market features are joined **as of the decision timestamp**, never after it.
- Continuous regime boundaries, GARCH parameters, imputation, scaling, and
  clusters are fitted on the training sample only.
- The test sample validates fixed definitions. The holdout is physically
  excluded from parquet reads unless the explicit confirmation phrase is set.
- The screen reports coverage, effect stability, multiplicity-adjusted nulls,
  and thin cells. It does not turn the best historical row into a trading rule.
"""))

cells.append(markdown(r"""
## 0. Input contract

Minimum trades columns after mapping:

| Meaning | Default source column | Required |
| --- | --- | --- |
| decision clock | `signal_time` | yes |
| realised result | `net_r` | yes |
| direction | `side` | recommended |
| entry / exit clock | `entry_time`, `exit_time` | recommended |
| frozen selectors | `pair`, `config` | recommended |

`net_r` means net profit divided by initial trade risk. With
`OUTCOME_IS_R=True`, `RISK_PER_TRADE_PCT=1.0` converts 1R to a 1% equity return.
If your authoritative simulator already emits net equity returns, point
`OUTCOME_COLUMN` to that field and set `OUTCOME_IS_R=False`.

For future strategies either edit `TRADES_PATH`, or define a pre-filtered
`trades_input` DataFrame before running the load cell. Under a sealed holdout,
an in-memory frame must already exclude holdout rows. Parquet is required for a
strict on-disk predicate read.
"""))

cells.append(code(r"""
from pathlib import Path
from itertools import combinations
import hashlib
import json
import math
import os
import warnings

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import pyarrow.parquet as pq

from IPython.display import display
from scipy.optimize import minimize
from scipy.stats import kruskal, spearmanr
from statsmodels.stats.multitest import multipletests
from statsmodels.tsa.stattools import adfuller
from sklearn.cluster import KMeans
from sklearn.impute import SimpleImputer
from sklearn.preprocessing import StandardScaler

os.environ.setdefault("LOKY_MAX_CPU_COUNT", str(os.cpu_count() or 1))

pd.set_option("display.max_columns", 120)
pd.set_option("display.width", 180)
sns.set_theme(style="whitegrid", context="notebook")

WORKSPACE_ROOT = next(
    (p for p in [Path.cwd().resolve(), *Path.cwd().resolve().parents]
     if (p / "ai_shared_memory").exists()),
    None,
)
if WORKSPACE_ROOT is None:
    raise RuntimeError("Run from somewhere inside the Research workspace.")
PROJECT_DIR = WORKSPACE_ROOT / "forex" / "trade_regime_tester"

print("Workspace:", WORKSPACE_ROOT)
print("Project:  ", PROJECT_DIR)
print("pandas:", pd.__version__)
"""))

cells.append(markdown(r"""
## 1. Configuration — edit this cell

Dates are half-open intervals: start is included and end is excluded. The
default leaves calendar year 2020 as a deliberate embargo between training and
test. The holdout begins on 2024-01-01 and stays closed.

The macro example is AUDUSD-specific. For another pair, set `MACRO_SOURCE` to a
point-in-time table whose date is either the actual availability timestamp or
an observation date paired with a conservative publication lag.

`FROZEN_PARAMETER_SNAPSHOT` is provenance, not a parameter search: the supplied
trades must already have been produced by exactly that configuration.
"""))

cells.append(code(r"""
SMOKE_MODE = os.getenv("REGIME_TESTER_SMOKE", "0") == "1"

# Frozen strategy / trade input
INSTRUMENT = "AUDUSD"
FROZEN_TRADE_FILTERS = {"pair": INSTRUMENT, "config": "sma_80"}
FROZEN_PARAMETER_SNAPSHOT = {
    "strategy": "anchored_twap_sma_zband_pivot_sl",
    "sma_length": 80,
    "arm_zscore": 2.5,
    "atr_stop_multiplier": 2.0,
    "position_sizing": "percentage_equity_risk",
    "risk_per_trade_pct": 1.0,
}
TRADES_PATH = WORKSPACE_ROOT / "forex" / "exploration_3" / "artifacts" / "runs" / "EXP-0001" / "trades.parquet"
TRADE_COLUMN_MAP = {
    "signal_time": "decision_time",
    "entry_time": "entry_time",
    "exit_time": "exit_time",
    "side": "side",
    "net_r": "outcome",
}
OUTCOME_IS_R = True
RISK_PER_TRADE_PCT = float(FROZEN_PARAMETER_SNAPSHOT["risk_per_trade_pct"])
PRECOMPUTED_FEATURE_COLUMNS = []  # regime columns already present on the trades frame

# Sampling and market input. The clean store is the only pair-specific default.
TIMEFRAME_MINUTES = 15
MARKET_PATH = WORKSPACE_ROOT / "forex" / "data" / "clean" / f"{INSTRUMENT}_1m_clean.parquet"
MARKET_SOURCE_IS_MINUTE = True
MARKET_TIME_COLUMN = "ts_utc"
MARKET_OHLC_MAP = {"open": "open", "high": "high", "low": "low", "close": "close"}
MIN_BAR_COVERAGE = 0.80
MARKET_WARMUP_DAYS = 400

# Independent market benchmark for covariance/correlation regimes.
BENCHMARK_INSTRUMENT = "NZDUSD"
BENCHMARK_PATH = WORKSPACE_ROOT / "forex" / "data" / "clean" / f"{BENCHMARK_INSTRUMENT}_1m_clean.parquet"

# Point-in-time macro and daily cross-asset inputs. Set either path to None to skip.
MACRO_SOURCE = (
    WORKSPACE_ROOT / "forex" / "data" / "archive" / "audusd_point_in_time_macro_factors.csv"
    if INSTRUMENT == "AUDUSD" else None
)
MACRO_DATE_COLUMN = "date"
MACRO_DATE_IS_AVAILABILITY_TIME = False
MACRO_PUBLICATION_LAG_DAYS = 45  # conservative if the source date is an observation date
MACRO_MAX_STALENESS_DAYS = 180
MACRO_COLUMNS = [
    "relative_gdp_growth_trend_score",
    "relative_consumption_growth_score",
    "manufacturing_confidence_improvement_score",
    "relative_unemployment_trend_score",
    "relative_excess_core_cpi_score",
    "relative_excess_ppi_score",
    "relative_inflation_expectations_score",
    "relative_real_short_rate_score",
    "terms_of_trade_dynamics_score",
    "external_balance_trend_score",
    "equal_weight_macro_score",
]
CROSS_ASSET_SOURCE = WORKSPACE_ROOT / "forex" / "data" / "archive" / "raw_market_levels_daily.csv"
CROSS_ASSET_DATE_COLUMN = None  # None means the first CSV column
CROSS_ASSET_AVAILABILITY_LAG_DAYS = 1  # yesterday's daily close is usable today
CROSS_ASSET_COLUMNS = ["vix", "dxy_broad", "sp500", "usdcny", "oil_wti", "copper", "au_short_rate", "us_3m", "au_10y", "us_10y", "us_2s10s"]

# Optional scheduled-event table: event_time plus optional importance/name.
EVENTS_PATH = None
EVENT_TIME_COLUMN = "event_time"

# Train / test / untouched holdout
TRAIN_START, TRAIN_END = "2012-01-01", "2020-01-01"
TEST_START, TEST_END = "2021-01-01", "2024-01-01"
HOLDOUT_START, HOLDOUT_END = "2024-01-01", None
OPEN_HOLDOUT = False
HOLDOUT_CONFIRMATION = ""
REQUIRED_HOLDOUT_CONFIRMATION = "I understand this consumes the 2024+ holdout"

# Feature horizons (bars unless a suffix says days)
RV_SHORT_BARS = 16
RV_LONG_BARS = 96
ATR_BARS = 56
VOL_LEVEL_LOOKBACK_BARS = 96 * 60
VEI_Z_LOOKBACK_BARS = 96 * 60
MA_FAST_BARS = 96
MA_SLOW_BARS = 96 * 5
TREND_SLOPE_BARS = 96
HIGHER_TIMEFRAME = "4h"
HTF_MA_BARS = 30
HTF_SLOPE_BARS = 10
ADX_BARS = 14
KAUFMAN_BARS = 40
STAT_WINDOW_BARS = 96 * 20
STAT_STRIDE_BARS = 96 * 5
AUTOCORR_WINDOW_BARS = 96 * 10
AUTOCORR_LAGS = [1, 4, 16]
COVARIANCE_WINDOW_BARS = 96 * 20
GARCH_FIT_MAX_OBS = 50_000

# Regime evaluation
N_REGIME_BINS = 3
MIN_TRAIN_OBS = 80
MIN_CELL_OBS = 25
MIN_FEATURE_COVERAGE = 0.60
N_PERMUTATIONS = 500
RANDOM_SEED = 1729
RUN_COMPOSITE_CLUSTER = True
N_COMPOSITE_CLUSTERS = 4
MAX_COMPOSITE_FEATURES = 20
INTERACTION_FEATURES = ["rv_long_z", "htf_slope_atr", "adx", "kaufman_er", "autocorr_1", "macro_equal_weight_macro_score"]
PLOT_FEATURE = "rv_long_z"
PLOT_TRADE_NUMBER = 0

# Optional artifact export; keep false while exploring interactively.
WRITE_OUTPUTS = False
RUN_LABEL = "replace_with_registered_experiment_id"
ALLOW_OUTPUT_OVERWRITE = False

if SMOKE_MODE:
    TRAIN_START, TRAIN_END = "2019-01-01", "2020-01-01"
    TEST_START, TEST_END = "2021-01-01", "2022-01-01"
    MARKET_WARMUP_DAYS = 120
    STAT_WINDOW_BARS = 96 * 10
    STAT_STRIDE_BARS = 96 * 10
    VOL_LEVEL_LOOKBACK_BARS = 96 * 20
    VEI_Z_LOOKBACK_BARS = 96 * 20
    N_PERMUTATIONS = 50
    WRITE_OUTPUTS = False
"""))

cells.append(markdown(r"""
## 2. Seal the holdout and define active intervals

The confirmation is intentionally awkward. With the default settings, parquet
predicates stop the trade and market reads before 2024-01-01. Merely changing a
plot later cannot reveal holdout outcomes because those rows are absent.
"""))

cells.append(code(r"""
def naive_utc(value):
    'Parse a scalar timestamp and return timezone-naive UTC.'
    ts = pd.Timestamp(value)
    if ts.tzinfo is not None:
        ts = ts.tz_convert("UTC").tz_localize(None)
    return ts


train_start, train_end = naive_utc(TRAIN_START), naive_utc(TRAIN_END)
test_start, test_end = naive_utc(TEST_START), naive_utc(TEST_END)
holdout_start = naive_utc(HOLDOUT_START)
holdout_end = naive_utc(HOLDOUT_END) if HOLDOUT_END else pd.Timestamp.now("UTC").tz_localize(None) + pd.Timedelta(days=1)

if not (train_start < train_end <= test_start < test_end <= holdout_start < holdout_end):
    raise ValueError("Expected ordered, non-overlapping train/test/holdout intervals.")
if OPEN_HOLDOUT and HOLDOUT_CONFIRMATION != REQUIRED_HOLDOUT_CONFIRMATION:
    raise PermissionError("Holdout remains sealed: enter the exact confirmation phrase.")

active_end = holdout_end if OPEN_HOLDOUT else test_end
active_splits = ["train", "test"] + (["holdout"] if OPEN_HOLDOUT else [])
split_intervals = {
    "train": (train_start, train_end),
    "test": (test_start, test_end),
}
if OPEN_HOLDOUT:
    split_intervals["holdout"] = (holdout_start, holdout_end)

print("Active splits:", active_splits)
print("Read cutoff:  ", active_end)
print("Holdout:      ", "OPEN — do not tune further" if OPEN_HOLDOUT else "SEALED / NOT LOADED")
"""))

cells.append(markdown(r"""
## 3. Load and validate the frozen trades

This is the main plug-and-play boundary. Parquet filters apply the instrument,
frozen configuration, and active date cutoff before rows enter pandas. CSV is
rejected while the holdout is sealed because it cannot guarantee a predicate
read.
"""))

cells.append(code(r"""
source_time_col = next(k for k, v in TRADE_COLUMN_MAP.items() if v == "decision_time")

if "trades_input" in globals():
    raw_trades = trades_input.copy()
    source_times = pd.to_datetime(raw_trades[source_time_col], utc=True).dt.tz_convert(None)
    if not OPEN_HOLDOUT and (source_times >= holdout_start).any():
        raise PermissionError("trades_input contains holdout rows. Pre-filter it before injection.")
elif Path(TRADES_PATH).suffix.lower() in {".parquet", ".pq"}:
    parquet_columns = set(pq.ParquetFile(TRADES_PATH).schema.names)
    if source_time_col not in parquet_columns:
        raise KeyError(f"Decision-time source column {source_time_col!r} is absent from {TRADES_PATH}")
    trade_filters = [(source_time_col, ">=", train_start.to_pydatetime()), (source_time_col, "<", active_end.to_pydatetime())]
    available_filter_columns = [column for column in FROZEN_TRADE_FILTERS if column in parquet_columns]
    missing_filter_columns = [column for column in FROZEN_TRADE_FILTERS if column not in parquet_columns]
    trade_filters.extend((column, "==", FROZEN_TRADE_FILTERS[column]) for column in available_filter_columns)
    if missing_filter_columns:
        warnings.warn(
            f"Frozen selector columns absent from this file and not applied: {missing_filter_columns}. "
            "This is acceptable only when the file is already frozen to one instrument/config."
        )
    raw_trades = pd.read_parquet(TRADES_PATH, filters=trade_filters)
else:
    if not OPEN_HOLDOUT:
        raise PermissionError("Use parquet or a pre-filtered trades_input while holdout is sealed.")
    raw_trades = pd.read_csv(TRADES_PATH)

required_targets = {"decision_time", "outcome"}
required_sources = [source for source, target in TRADE_COLUMN_MAP.items() if target in required_targets]
missing_required_sources = [source for source in required_sources if source not in raw_trades.columns]
if missing_required_sources:
    raise KeyError(f"Missing required mapped trade columns: {missing_required_sources}")

trades = raw_trades.rename(columns=TRADE_COLUMN_MAP).copy()
for column in ["decision_time", "entry_time", "exit_time"]:
    if column in trades:
        trades[column] = pd.to_datetime(trades[column], utc=True).dt.tz_convert(None)
trades["outcome"] = pd.to_numeric(trades["outcome"], errors="coerce")
if "side" not in trades:
    trades["side"] = "unknown"
trades["side"] = trades["side"].astype(str).str.lower()

for column, value in FROZEN_TRADE_FILTERS.items():
    if column in trades:
        trades = trades.loc[trades[column].eq(value)].copy()

trades["split"] = "unused"
for split_name, (start, end) in split_intervals.items():
    mask = trades["decision_time"].ge(start) & trades["decision_time"].lt(end)
    trades.loc[mask, "split"] = split_name
trades = trades.loc[trades["split"].isin(active_splits)].sort_values("decision_time").reset_index(drop=True)
trades["trade_id"] = np.arange(len(trades))
trades["trade_return"] = trades["outcome"] * RISK_PER_TRADE_PCT / 100 if OUTCOME_IS_R else trades["outcome"]

if trades.empty:
    raise ValueError(
        "No trades remain after frozen filters and date splits. "
        f"Requested selectors={FROZEN_TRADE_FILTERS}, train={TRAIN_START}:{TRAIN_END}, "
        f"test={TEST_START}:{TEST_END}. Check the file's exact config label and date coverage."
    )
if trades["outcome"].isna().any() or not np.isfinite(trades["outcome"]).all():
    raise ValueError("Outcome contains missing or non-finite values.")
if not OPEN_HOLDOUT and trades["decision_time"].ge(holdout_start).any():
    raise AssertionError("Holdout row entered the analysis unexpectedly.")

display(trades.groupby(["split", "side"], observed=True).agg(
    trades=("trade_id", "size"),
    first_decision=("decision_time", "min"),
    last_decision=("decision_time", "max"),
    mean_outcome=("outcome", "mean"),
))
print("Frozen selectors:", FROZEN_TRADE_FILTERS)
print("Frozen parameter snapshot:", FROZEN_PARAMETER_SNAPSHOT)
"""))

cells.append(markdown(r"""
### Trade-table quality checks

Multiple trades at one timestamp are not automatically wrong, but they change
portfolio accounting. Likewise, overlapping entry/exit intervals mean that a
simple sequential compounding curve is diagnostic rather than authoritative.
The regime-level mean outcome remains valid if each row's net result is valid.
"""))

cells.append(code(r"""
duplicate_rows = int(trades.duplicated(subset=["decision_time", "side"], keep=False).sum())
out_of_order = int((trades["decision_time"].diff().dropna() < pd.Timedelta(0)).sum())
overlap_count = np.nan
if {"entry_time", "exit_time"}.issubset(trades.columns):
    chronological = trades.sort_values("entry_time")
    prior_latest_exit = chronological["exit_time"].cummax().shift(1)
    overlap_count = int(chronological["entry_time"].lt(prior_latest_exit).sum())

trade_quality = pd.Series({
    "rows": len(trades),
    "duplicate decision+side rows": duplicate_rows,
    "out-of-order rows after sort": out_of_order,
    "overlapping trade intervals": overlap_count,
    "missing side": int(trades["side"].eq("unknown").sum()),
    "max absolute outcome": float(trades["outcome"].abs().max()),
})
display(trade_quality.to_frame("value"))
if overlap_count and overlap_count > 0:
    warnings.warn("Overlapping trades detected: equity curves below are diagnostic. Use an authoritative portfolio return series for exact accounting.")
"""))

cells.append(markdown(r"""
## 4. Load market data and build completed bars

Minute bars are aggregated to the chosen timeframe. A 15-minute bar labelled
00:00 becomes available at 00:15. Later, `merge_asof` attaches only a feature
timestamp less than or equal to the trade decision time. Incomplete bars remain
flagged so their coverage can be audited and tested as a market-quality regime.
"""))

cells.append(code(r"""
market_load_start = train_start - pd.Timedelta(days=MARKET_WARMUP_DAYS)
bar_delta = pd.Timedelta(minutes=TIMEFRAME_MINUTES)

if "market_input" in globals():
    raw_market = market_input.copy()
    input_market_times = pd.to_datetime(raw_market[MARKET_TIME_COLUMN], utc=True).dt.tz_convert(None)
    if not OPEN_HOLDOUT and input_market_times.ge(holdout_start).any():
        raise PermissionError("market_input contains sealed holdout timestamps.")
elif Path(MARKET_PATH).suffix.lower() in {".parquet", ".pq"}:
    market_filters = [(MARKET_TIME_COLUMN, ">=", market_load_start.to_pydatetime()), (MARKET_TIME_COLUMN, "<", active_end.to_pydatetime())]
    raw_market = pd.read_parquet(MARKET_PATH, filters=market_filters)
else:
    if not OPEN_HOLDOUT:
        raise PermissionError("Use parquet or a pre-filtered market_input while holdout is sealed.")
    raw_market = pd.read_csv(MARKET_PATH)

raw_market = raw_market.rename(columns={v: k for k, v in MARKET_OHLC_MAP.items()})
required_market = [MARKET_TIME_COLUMN, "open", "high", "low", "close"]
missing_market = [c for c in required_market if c not in raw_market.columns]
if missing_market:
    raise KeyError(f"Missing market columns: {missing_market}")
raw_market[MARKET_TIME_COLUMN] = pd.to_datetime(raw_market[MARKET_TIME_COLUMN], utc=True).dt.tz_convert(None)
raw_market = raw_market.sort_values(MARKET_TIME_COLUMN).drop_duplicates(MARKET_TIME_COLUMN, keep="last")
raw_market = raw_market.set_index(MARKET_TIME_COLUMN)

if MARKET_SOURCE_IS_MINUTE:
    frequency = f"{TIMEFRAME_MINUTES}min"
    bars = raw_market[["open", "high", "low", "close"]].resample(frequency, label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last")
    )
    bars["source_observations"] = raw_market["close"].resample(frequency, label="left", closed="left").count()
    bars["bar_coverage"] = bars["source_observations"] / TIMEFRAME_MINUTES
else:
    bars = raw_market[["open", "high", "low", "close"]].copy()
    bars["source_observations"] = 1
    bars["bar_coverage"] = 1.0

bars.index.name = "bar_open_time"
bars = bars.dropna(subset=["open", "high", "low", "close"]).reset_index()
bars["feature_time"] = bars["bar_open_time"] + bar_delta
bars["bar_complete"] = bars["bar_coverage"].ge(MIN_BAR_COVERAGE)
bars = bars.loc[bars["feature_time"].lt(active_end)].set_index("feature_time").sort_index()

market_quality = pd.Series({
    "bars": len(bars),
    "first feature time": bars.index.min(),
    "last feature time": bars.index.max(),
    "duplicate feature times": int(bars.index.duplicated().sum()),
    "incomplete bars": int((~bars["bar_complete"]).sum()),
    "median source observations": float(bars["source_observations"].median()),
})
display(market_quality.to_frame("value"))
"""))

cells.append(markdown(r"""
## 5. Intraday volatility, range, jump, and liquidity regimes

`VEI` here is a volatility-expansion index:

\[
VEI_t = \log\left(\frac{RV_{short,t}}{RV_{long,t}}\right)
\]

Its z-score uses only earlier observations for the rolling mean and standard
deviation. Volatility percentiles also use prior observations; the current
value is ranked against the historical window rather than against the full
sample.
"""))

cells.append(code(r"""
mkt = bars.copy()
mkt["log_close"] = np.log(mkt["close"])
mkt["log_return"] = mkt["log_close"].diff()
mkt["simple_return"] = mkt["close"].pct_change()

previous_close = mkt["close"].shift(1)
true_range_parts = pd.concat([
    mkt["high"] - mkt["low"],
    (mkt["high"] - previous_close).abs(),
    (mkt["low"] - previous_close).abs(),
], axis=1)
mkt["true_range"] = true_range_parts.max(axis=1)
mkt["atr"] = mkt["true_range"].ewm(alpha=1 / ATR_BARS, adjust=False, min_periods=ATR_BARS).mean()
mkt["atr_pct"] = mkt["atr"] / mkt["close"]

annualisation = math.sqrt(252 * 24 * 60 / TIMEFRAME_MINUTES)
mkt["rv_short"] = mkt["log_return"].rolling(RV_SHORT_BARS, min_periods=RV_SHORT_BARS).std() * annualisation
mkt["rv_long"] = mkt["log_return"].rolling(RV_LONG_BARS, min_periods=RV_LONG_BARS).std() * annualisation
mkt["rv_short_long_ratio"] = mkt["rv_short"] / mkt["rv_long"].replace(0, np.nan)
mkt["vei"] = np.log(mkt["rv_short_long_ratio"].clip(lower=1e-12))

vei_history = mkt["vei"].shift(1)
vei_mean = vei_history.rolling(VEI_Z_LOOKBACK_BARS, min_periods=max(50, VEI_Z_LOOKBACK_BARS // 4)).mean()
vei_std = vei_history.rolling(VEI_Z_LOOKBACK_BARS, min_periods=max(50, VEI_Z_LOOKBACK_BARS // 4)).std()
mkt["vei_z"] = (mkt["vei"] - vei_mean) / vei_std.replace(0, np.nan)
mkt["rv_acceleration"] = np.log(mkt["rv_long"].clip(lower=1e-12)).diff(RV_SHORT_BARS)
mkt["atr_short_long_ratio"] = (
    mkt["true_range"].rolling(RV_SHORT_BARS, min_periods=RV_SHORT_BARS).mean()
    / mkt["true_range"].rolling(RV_LONG_BARS, min_periods=RV_LONG_BARS).mean().replace(0, np.nan)
)

rv_history = mkt["rv_long"].shift(1)
rv_mean = rv_history.rolling(VOL_LEVEL_LOOKBACK_BARS, min_periods=max(100, VOL_LEVEL_LOOKBACK_BARS // 4)).mean()
rv_std = rv_history.rolling(VOL_LEVEL_LOOKBACK_BARS, min_periods=max(100, VOL_LEVEL_LOOKBACK_BARS // 4)).std()
mkt["rv_long_z"] = (mkt["rv_long"] - rv_mean) / rv_std.replace(0, np.nan)
mkt["rv_long_percentile"] = rv_history.rolling(
    VOL_LEVEL_LOOKBACK_BARS,
    min_periods=max(100, VOL_LEVEL_LOOKBACK_BARS // 4),
).rank(pct=True)

atr_history = mkt["atr_pct"].shift(1)
mkt["atr_pct_z"] = (
    (mkt["atr_pct"] - atr_history.rolling(VOL_LEVEL_LOOKBACK_BARS, min_periods=max(100, VOL_LEVEL_LOOKBACK_BARS // 4)).mean())
    / atr_history.rolling(VOL_LEVEL_LOOKBACK_BARS, min_periods=max(100, VOL_LEVEL_LOOKBACK_BARS // 4)).std().replace(0, np.nan)
)

mkt["bar_range_atr"] = (mkt["high"] - mkt["low"]) / mkt["atr"].replace(0, np.nan)
mkt["jump_score"] = mkt["log_return"].abs() / (mkt["rv_long"] / annualisation).replace(0, np.nan)
mkt["downside_semivol"] = mkt["log_return"].where(mkt["log_return"] < 0, 0).pow(2).rolling(RV_LONG_BARS, min_periods=RV_LONG_BARS).mean().pow(0.5) * annualisation
mkt["upside_semivol"] = mkt["log_return"].where(mkt["log_return"] > 0, 0).pow(2).rolling(RV_LONG_BARS, min_periods=RV_LONG_BARS).mean().pow(0.5) * annualisation
mkt["semivol_imbalance"] = (mkt["upside_semivol"] - mkt["downside_semivol"]) / (mkt["upside_semivol"] + mkt["downside_semivol"]).replace(0, np.nan)
mkt["close_location"] = (mkt["close"] - mkt["low"]) / (mkt["high"] - mkt["low"]).replace(0, np.nan)
mkt["gap_from_previous_close_atr"] = (mkt["open"] - previous_close).abs() / mkt["atr"].replace(0, np.nan)
mkt["missing_bar_fraction_1d"] = 1 - mkt["bar_coverage"].rolling(max(1, 24 * 60 // TIMEFRAME_MINUTES), min_periods=1).mean().clip(upper=1)
"""))

cells.append(markdown(r"""
### Train-fitted GARCH(1,1)

The static GARCH parameters are estimated once using training returns only.
The variance recursion then walks forward in timestamp order. Training values
are therefore an in-sample description; test and (if deliberately opened)
holdout values use frozen parameters. The forecast at a bar close uses that
completed bar's return to forecast the next bar.
"""))

cells.append(code(r"""
train_return_mask = (mkt.index >= train_start) & (mkt.index < train_end)
garch_fit_returns = (mkt.loc[train_return_mask, "log_return"].dropna() * 100).tail(GARCH_FIT_MAX_OBS).to_numpy()
if len(garch_fit_returns) < 500:
    raise ValueError("Too few training returns to estimate GARCH.")

def garch_variance_path(returns, omega, alpha, beta, initial_variance=None):
    'One transparent GARCH recursion; values are in squared percent returns.'
    returns = np.asarray(returns, dtype=float)
    initial_variance = float(np.nanvar(returns)) if initial_variance is None else float(initial_variance)
    variance = np.empty(len(returns), dtype=float)
    variance[0] = max(initial_variance, 1e-10)
    for i in range(1, len(returns)):
        variance[i] = omega + alpha * returns[i - 1] ** 2 + beta * variance[i - 1]
    return np.maximum(variance, 1e-10)


def garch_negative_log_likelihood(parameters, returns):
    omega, alpha, beta = parameters
    if omega <= 0 or alpha < 0 or beta < 0 or alpha + beta >= 0.999:
        return 1e30
    variance = garch_variance_path(returns, omega, alpha, beta)
    return float(0.5 * np.sum(np.log(variance) + returns ** 2 / variance))


fit_variance = float(np.var(garch_fit_returns))
garch_start = np.array([fit_variance * 0.05, 0.05, 0.90])
garch_fit = minimize(
    garch_negative_log_likelihood,
    garch_start,
    args=(garch_fit_returns,),
    method="SLSQP",
    bounds=[(1e-10, max(fit_variance * 2, 1e-6)), (1e-6, 0.50), (1e-6, 0.998)],
    constraints=[{"type": "ineq", "fun": lambda p: 0.998 - p[1] - p[2]}],
    options={"maxiter": 200, "ftol": 1e-9},
)
if not garch_fit.success:
    warnings.warn(f"GARCH fit did not converge ({garch_fit.message}); using conservative fallback parameters.")
    garch_parameters = np.array([fit_variance * 0.05, 0.05, 0.90])
else:
    garch_parameters = garch_fit.x

full_returns_pct = (mkt["log_return"].fillna(0) * 100).to_numpy()
garch_variance = garch_variance_path(full_returns_pct, *garch_parameters, initial_variance=fit_variance)
# Convert one-bar percent volatility to annualised decimal volatility.
mkt["garch_vol"] = np.sqrt(garch_variance) / 100 * annualisation
mkt["garch_acceleration"] = np.log(pd.Series(mkt["garch_vol"], index=mkt.index).clip(lower=1e-12)).diff(RV_SHORT_BARS)

display(pd.Series(dict(zip(["omega", "alpha", "beta"], garch_parameters)), name="train_fit").to_frame())
"""))

cells.append(markdown(r"""
## 6. Trend and directional-strength regimes

The standard moving-average features use completed strategy-timeframe bars.
The higher-timeframe features use only the last completed 4-hour close. Slopes
are divided by ATR to make them more comparable across price and volatility
levels. ADX measures directional strength without direction; Kaufman's
Efficiency Ratio measures how directly price travelled relative to total path
length.
"""))

cells.append(code(r"""
mkt["ma_fast"] = mkt["close"].rolling(MA_FAST_BARS, min_periods=MA_FAST_BARS).mean()
mkt["ma_slow"] = mkt["close"].rolling(MA_SLOW_BARS, min_periods=MA_SLOW_BARS).mean()
mkt["ma_spread_atr"] = (mkt["ma_fast"] - mkt["ma_slow"]) / mkt["atr"].replace(0, np.nan)
mkt["price_vs_ma_atr"] = (mkt["close"] - mkt["ma_slow"]) / mkt["atr"].replace(0, np.nan)
mkt["ma_slope_atr"] = (mkt["ma_slow"] - mkt["ma_slow"].shift(TREND_SLOPE_BARS)) / mkt["atr"].replace(0, np.nan)
mkt["trend_return"] = mkt["close"].pct_change(MA_SLOW_BARS)

htf_close = mkt["close"].resample(HIGHER_TIMEFRAME, label="right", closed="right").last().dropna()
htf_atr = mkt["atr"].resample(HIGHER_TIMEFRAME, label="right", closed="right").last().reindex(htf_close.index)
htf_frame = pd.DataFrame({"htf_close": htf_close, "htf_atr": htf_atr})
htf_frame["htf_ma"] = htf_frame["htf_close"].rolling(HTF_MA_BARS, min_periods=HTF_MA_BARS).mean()
htf_frame["htf_slope_atr"] = (htf_frame["htf_ma"] - htf_frame["htf_ma"].shift(HTF_SLOPE_BARS)) / htf_frame["htf_atr"].replace(0, np.nan)
htf_frame["htf_price_vs_ma_atr"] = (htf_frame["htf_close"] - htf_frame["htf_ma"]) / htf_frame["htf_atr"].replace(0, np.nan)
mkt = pd.merge_asof(
    mkt.reset_index().sort_values("feature_time"),
    htf_frame.reset_index().rename(columns={htf_frame.index.name or "index": "htf_feature_time"}).sort_values("htf_feature_time"),
    left_on="feature_time",
    right_on="htf_feature_time",
    direction="backward",
).set_index("feature_time")

up_move = mkt["high"].diff()
down_move = -mkt["low"].diff()
plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
smoothed_tr = mkt["true_range"].ewm(alpha=1 / ADX_BARS, adjust=False, min_periods=ADX_BARS).mean()
plus_di = 100 * plus_dm.ewm(alpha=1 / ADX_BARS, adjust=False, min_periods=ADX_BARS).mean() / smoothed_tr.replace(0, np.nan)
minus_di = 100 * minus_dm.ewm(alpha=1 / ADX_BARS, adjust=False, min_periods=ADX_BARS).mean() / smoothed_tr.replace(0, np.nan)
dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
mkt["adx"] = dx.ewm(alpha=1 / ADX_BARS, adjust=False, min_periods=ADX_BARS).mean()
mkt["di_spread"] = plus_di - minus_di

net_path = (mkt["close"] - mkt["close"].shift(KAUFMAN_BARS)).abs()
gross_path = mkt["close"].diff().abs().rolling(KAUFMAN_BARS, min_periods=KAUFMAN_BARS).sum()
mkt["kaufman_er"] = net_path / gross_path.replace(0, np.nan)
"""))

cells.append(markdown(r"""
## 7. Statistical-distribution and dependence regimes

Skewness, excess kurtosis, autocorrelation, and variance ratio are rolling and
causal. ADF stationarity and Hurst exponent are much more expensive, so they are
re-estimated at a fixed stride and carried forward. Their `stat_age_bars` field
makes that staleness visible instead of hiding it.
"""))

cells.append(code(r"""
mkt["return_skew"] = mkt["log_return"].rolling(STAT_WINDOW_BARS, min_periods=STAT_WINDOW_BARS).skew()
mkt["return_excess_kurtosis"] = mkt["log_return"].rolling(STAT_WINDOW_BARS, min_periods=STAT_WINDOW_BARS).kurt()

stat_positions = range(STAT_WINDOW_BARS, len(mkt), STAT_STRIDE_BARS)
adf_points, hurst_points, stat_update_points = {}, {}, {}
log_prices = mkt["log_close"].to_numpy()
for position in stat_positions:
    window = log_prices[position - STAT_WINDOW_BARS:position]
    if np.isfinite(window).sum() < STAT_WINDOW_BARS * 0.95:
        continue
    timestamp = mkt.index[position]
    try:
        adf_points[timestamp] = float(adfuller(window, maxlag=1, regression="c", autolag=None)[1])
    except (ValueError, np.linalg.LinAlgError):
        adf_points[timestamp] = np.nan
    lags = np.array([2, 4, 8, 16, 32])
    tau = np.array([np.std(window[lag:] - window[:-lag]) for lag in lags])
    hurst_points[timestamp] = float(np.polyfit(np.log(lags), np.log(np.maximum(tau, 1e-12)), 1)[0])
    stat_update_points[timestamp] = position

mkt["adf_pvalue"] = pd.Series(adf_points, dtype=float).reindex(mkt.index).ffill()
mkt["hurst_exponent"] = pd.Series(hurst_points, dtype=float).reindex(mkt.index).ffill()
last_update_position = pd.Series(stat_update_points, dtype=float).reindex(mkt.index).ffill()
mkt["stat_age_bars"] = np.arange(len(mkt)) - last_update_position

for lag in AUTOCORR_LAGS:
    mkt[f"autocorr_{lag}"] = mkt["log_return"].rolling(
        AUTOCORR_WINDOW_BARS,
        min_periods=AUTOCORR_WINDOW_BARS,
    ).corr(mkt["log_return"].shift(lag))

variance_one = mkt["log_return"].rolling(AUTOCORR_WINDOW_BARS, min_periods=AUTOCORR_WINDOW_BARS).var()
return_four = mkt["log_close"].diff(4)
variance_four = return_four.rolling(AUTOCORR_WINDOW_BARS, min_periods=AUTOCORR_WINDOW_BARS).var()
mkt["variance_ratio_4"] = variance_four / (4 * variance_one).replace(0, np.nan)
"""))

cells.append(markdown(r"""
## 8. Benchmark covariance and cross-market dependence

The default benchmark is NZDUSD for AUDUSD. Change it to a broad dollar index,
regional peer, equity index, rates future, or other causal reference series.
Covariance, correlation, beta, downside correlation, and relative momentum are
all computed with completed bars.
"""))

cells.append(code(r"""
benchmark_available = BENCHMARK_PATH is not None and Path(BENCHMARK_PATH).exists()
if benchmark_available:
    if "benchmark_input" in globals():
        raw_benchmark = benchmark_input.copy()
        benchmark_times = pd.to_datetime(raw_benchmark[MARKET_TIME_COLUMN], utc=True).dt.tz_convert(None)
        if not OPEN_HOLDOUT and benchmark_times.ge(holdout_start).any():
            raise PermissionError("benchmark_input contains sealed holdout timestamps.")
    elif Path(BENCHMARK_PATH).suffix.lower() in {".parquet", ".pq"}:
        benchmark_filters = [(MARKET_TIME_COLUMN, ">=", market_load_start.to_pydatetime()), (MARKET_TIME_COLUMN, "<", active_end.to_pydatetime())]
        raw_benchmark = pd.read_parquet(BENCHMARK_PATH, filters=benchmark_filters)
    else:
        raise PermissionError("Benchmark must be parquet or a pre-filtered benchmark_input while holdout is sealed.")

    raw_benchmark = raw_benchmark.rename(columns={v: k for k, v in MARKET_OHLC_MAP.items()})
    raw_benchmark[MARKET_TIME_COLUMN] = pd.to_datetime(raw_benchmark[MARKET_TIME_COLUMN], utc=True).dt.tz_convert(None)
    raw_benchmark = raw_benchmark.sort_values(MARKET_TIME_COLUMN).drop_duplicates(MARKET_TIME_COLUMN).set_index(MARKET_TIME_COLUMN)
    if MARKET_SOURCE_IS_MINUTE:
        benchmark_close = raw_benchmark["close"].resample(f"{TIMEFRAME_MINUTES}min", label="left", closed="left").last().dropna()
        benchmark_close.index = benchmark_close.index + bar_delta
    else:
        benchmark_close = raw_benchmark["close"].copy()
    benchmark_return = np.log(benchmark_close).diff().rename("benchmark_return")
    mkt = mkt.join(benchmark_return, how="left")
    mkt["rolling_covariance"] = mkt["log_return"].rolling(COVARIANCE_WINDOW_BARS, min_periods=COVARIANCE_WINDOW_BARS).cov(mkt["benchmark_return"])
    mkt["rolling_correlation"] = mkt["log_return"].rolling(COVARIANCE_WINDOW_BARS, min_periods=COVARIANCE_WINDOW_BARS).corr(mkt["benchmark_return"])
    benchmark_variance = mkt["benchmark_return"].rolling(COVARIANCE_WINDOW_BARS, min_periods=COVARIANCE_WINDOW_BARS).var()
    mkt["rolling_beta"] = mkt["rolling_covariance"] / benchmark_variance.replace(0, np.nan)
    primary_down = mkt["log_return"].where(mkt["log_return"] < 0)
    benchmark_down = mkt["benchmark_return"].where(mkt["benchmark_return"] < 0)
    mkt["downside_correlation"] = primary_down.rolling(COVARIANCE_WINDOW_BARS, min_periods=COVARIANCE_WINDOW_BARS // 4).corr(benchmark_down)
    mkt["relative_momentum"] = mkt["log_close"].diff(COVARIANCE_WINDOW_BARS) - np.log(benchmark_close).reindex(mkt.index).ffill().diff(COVARIANCE_WINDOW_BARS)
else:
    warnings.warn("Benchmark source is unavailable; covariance family will be skipped.")
"""))

cells.append(markdown(r"""
## 9. Macro, rates, inflation, economy, and cross-asset regimes

Macro values are joined by **availability time**. The default source is a
point-in-time AUDUSD factor file; because its date is an observation date, the
notebook adds a conservative 45-day lag. Replace that lag with actual release
timestamps whenever they are available. Market-level cross-asset closes get a
one-day lag so an intraday trade never sees the same day's closing value.

Do not add columns named `target_*`, forward return, or forward direction here.
Those are outcomes and would leak future information.
"""))

cells.append(code(r"""
macro_features = pd.DataFrame()
if MACRO_SOURCE is not None and Path(MACRO_SOURCE).exists():
    if "macro_input" in globals():
        macro_raw = macro_input.copy()
    else:
        macro_raw = pd.read_csv(MACRO_SOURCE)
    macro_raw[MACRO_DATE_COLUMN] = pd.to_datetime(macro_raw[MACRO_DATE_COLUMN], utc=True).dt.tz_convert(None)
    macro_raw = macro_raw.loc[macro_raw[MACRO_DATE_COLUMN].lt(active_end)].copy()
    forbidden_macro = [c for c in macro_raw.columns if "target" in c.lower() or "fwd" in c.lower()]
    if forbidden_macro:
        raise ValueError(f"Forward/target macro columns are forbidden: {forbidden_macro}")
    usable_macro = [c for c in MACRO_COLUMNS if c in macro_raw.columns]
    macro_features = macro_raw[[MACRO_DATE_COLUMN, *usable_macro]].copy()
    lag = pd.Timedelta(0) if MACRO_DATE_IS_AVAILABILITY_TIME else pd.Timedelta(days=MACRO_PUBLICATION_LAG_DAYS)
    macro_features["macro_available_time"] = macro_features[MACRO_DATE_COLUMN] + lag
    macro_features = macro_features.drop(columns=MACRO_DATE_COLUMN).rename(columns={c: f"macro_{c}" for c in usable_macro})
    macro_features = macro_features.sort_values("macro_available_time").drop_duplicates("macro_available_time", keep="last")
    print(f"Macro columns loaded: {len(usable_macro)}; conservative availability lag: {lag}")
else:
    warnings.warn("No macro source configured; macro regimes will be marked unavailable.")

cross_features = pd.DataFrame()
if CROSS_ASSET_SOURCE is not None and Path(CROSS_ASSET_SOURCE).exists():
    if "cross_asset_input" in globals():
        cross_raw = cross_asset_input.copy()
    else:
        cross_raw = pd.read_csv(CROSS_ASSET_SOURCE)
    if CROSS_ASSET_DATE_COLUMN is None:
        cross_date_source = cross_raw.columns[0]
    else:
        cross_date_source = CROSS_ASSET_DATE_COLUMN
    cross_raw[cross_date_source] = pd.to_datetime(cross_raw[cross_date_source], utc=True).dt.tz_convert(None)
    cross_raw = cross_raw.loc[cross_raw[cross_date_source].lt(active_end)].sort_values(cross_date_source).copy()
    usable_cross = [c for c in CROSS_ASSET_COLUMNS if c in cross_raw.columns]
    cross_numeric = cross_raw.set_index(cross_date_source)[usable_cross].apply(pd.to_numeric, errors="coerce")
    cross_features = pd.DataFrame(index=cross_numeric.index)
    for column in usable_cross:
        cross_features[f"cross_{column}_level"] = cross_numeric[column]
        cross_features[f"cross_{column}_change_21d"] = cross_numeric[column].pct_change(21, fill_method=None)
        history = cross_numeric[column].shift(1)
        cross_features[f"cross_{column}_z_252d"] = (
            (cross_numeric[column] - history.rolling(252, min_periods=126).mean())
            / history.rolling(252, min_periods=126).std().replace(0, np.nan)
        )
    if {"au_short_rate", "us_3m"}.issubset(cross_numeric.columns):
        cross_features["cross_short_rate_differential"] = cross_numeric["au_short_rate"] - cross_numeric["us_3m"]
    if {"au_10y", "us_10y"}.issubset(cross_numeric.columns):
        cross_features["cross_10y_rate_differential"] = cross_numeric["au_10y"] - cross_numeric["us_10y"]
    cross_features = cross_features.reset_index().rename(columns={cross_date_source: "cross_observation_time"})
    cross_features["cross_available_time"] = cross_features["cross_observation_time"] + pd.Timedelta(days=CROSS_ASSET_AVAILABILITY_LAG_DAYS)
    cross_features = cross_features.drop(columns="cross_observation_time").sort_values("cross_available_time")
    print(f"Cross-asset columns loaded: {len(usable_cross)}")
"""))

cells.append(markdown(r"""
## 10. Join regimes to each trade at its decision clock

Market features have a tight tolerance: a stale Friday bar should not silently
describe a Monday signal. Macro and daily market features have explicit, wider
staleness limits suited to their update frequency. Optional scheduled events
can add hours-since and hours-to-event; the latter is valid only when the event
calendar was genuinely published before the trade.
"""))

cells.append(code(r"""
feature_columns_from_market = [
    c for c in mkt.columns
    if c not in {"open", "high", "low", "close", "bar_open_time", "log_close"}
]
market_for_join = mkt.reset_index().sort_values("feature_time")
enriched = pd.merge_asof(
    trades.sort_values("decision_time"),
    market_for_join[["feature_time", *feature_columns_from_market]],
    left_on="decision_time",
    right_on="feature_time",
    direction="backward",
    tolerance=bar_delta * 3,
)
enriched["market_feature_age_minutes"] = (enriched["decision_time"] - enriched["feature_time"]).dt.total_seconds() / 60

if not macro_features.empty:
    enriched = pd.merge_asof(
        enriched.sort_values("decision_time"),
        macro_features,
        left_on="decision_time",
        right_on="macro_available_time",
        direction="backward",
        tolerance=pd.Timedelta(days=MACRO_MAX_STALENESS_DAYS),
    )
    enriched["macro_age_days"] = (enriched["decision_time"] - enriched["macro_available_time"]).dt.total_seconds() / 86400

if not cross_features.empty:
    enriched = pd.merge_asof(
        enriched.sort_values("decision_time"),
        cross_features,
        left_on="decision_time",
        right_on="cross_available_time",
        direction="backward",
        tolerance=pd.Timedelta(days=7),
    )
    enriched["cross_asset_age_days"] = (enriched["decision_time"] - enriched["cross_available_time"]).dt.total_seconds() / 86400

if EVENTS_PATH is not None or "events_input" in globals():
    events = events_input.copy() if "events_input" in globals() else pd.read_parquet(EVENTS_PATH)
    events[EVENT_TIME_COLUMN] = pd.to_datetime(events[EVENT_TIME_COLUMN], utc=True).dt.tz_convert(None)
    events = events.loc[events[EVENT_TIME_COLUMN].lt(active_end)].sort_values(EVENT_TIME_COLUMN)
    past_events = events[[EVENT_TIME_COLUMN]].rename(columns={EVENT_TIME_COLUMN: "previous_event_time"})
    next_events = events[[EVENT_TIME_COLUMN]].rename(columns={EVENT_TIME_COLUMN: "next_event_time"})
    enriched = pd.merge_asof(enriched.sort_values("decision_time"), past_events, left_on="decision_time", right_on="previous_event_time", direction="backward")
    enriched = pd.merge_asof(enriched.sort_values("decision_time"), next_events, left_on="decision_time", right_on="next_event_time", direction="forward")
    enriched["hours_since_event"] = (enriched["decision_time"] - enriched["previous_event_time"]).dt.total_seconds() / 3600
    enriched["hours_to_scheduled_event"] = (enriched["next_event_time"] - enriched["decision_time"]).dt.total_seconds() / 3600

# Calendar states use UTC by default. Change these labels if your strategy uses another session clock.
hour = enriched["decision_time"].dt.hour
enriched["session_utc"] = pd.cut(
    hour,
    bins=[-1, 6, 12, 16, 21, 23],
    labels=["asia", "london", "overlap", "new_york", "rollover"],
)
enriched["weekday"] = enriched["decision_time"].dt.day_name().str[:3]
enriched["month"] = enriched["decision_time"].dt.month.astype(str)
enriched["month_end"] = enriched["decision_time"].dt.is_month_end
enriched["quarter_end"] = enriched["decision_time"].dt.is_quarter_end

if not OPEN_HOLDOUT and enriched["decision_time"].ge(holdout_start).any():
    raise AssertionError("Holdout row entered after feature joins.")
display(enriched[["decision_time", "split", "side", "outcome", "feature_time", "market_feature_age_minutes"]].head())
"""))

cells.append(markdown(r"""
### Causal strategy-state regimes

Drawdown and recent hit rate can matter even when the market regime is unchanged.
These features use only trades whose **exit time** was known before the next
decision. This avoids the common error of feeding a still-open trade's eventual
result into an earlier decision.
"""))

cells.append(code(r"""
if "exit_time" in enriched and enriched["exit_time"].notna().any():
    completed = enriched[["exit_time", "outcome", "trade_return"]].dropna(subset=["exit_time"]).sort_values("exit_time").copy()
    completed["strategy_recent_mean_20"] = completed["outcome"].rolling(20, min_periods=5).mean()
    completed["strategy_recent_win_rate_20"] = completed["outcome"].gt(0).rolling(20, min_periods=5).mean()
    completed["strategy_recent_vol_20"] = completed["outcome"].rolling(20, min_periods=5).std()
    completed["strategy_equity_after_exit"] = (1 + completed["trade_return"].clip(lower=-0.999)).cumprod()
    completed["strategy_peak_after_exit"] = completed["strategy_equity_after_exit"].cummax()
    completed["strategy_drawdown_after_exit"] = completed["strategy_equity_after_exit"] / completed["strategy_peak_after_exit"] - 1
    state_columns = ["exit_time", "strategy_recent_mean_20", "strategy_recent_win_rate_20", "strategy_recent_vol_20", "strategy_drawdown_after_exit"]
    enriched = pd.merge_asof(
        enriched.sort_values("decision_time"),
        completed[state_columns].sort_values("exit_time"),
        left_on="decision_time",
        right_on="exit_time",
        direction="backward",
        allow_exact_matches=True,
        suffixes=("", "_last_completed"),
    )
else:
    warnings.warn("No exit_time available; completed-trade strategy state is skipped.")

previous_decision = enriched["decision_time"].shift(1)
enriched["hours_since_previous_signal"] = (enriched["decision_time"] - previous_decision).dt.total_seconds() / 3600
"""))

cells.append(markdown(r"""
## 11. Feature catalogue and coverage audit

This catalogue is the notebook's extensibility point. Add a numeric feature to
the table and it automatically receives train-fitted quantile regimes. Add a
categorical or boolean feature and its observed labels are evaluated directly.
Missing optional data does not crash the screen; the feature is marked
unavailable and excluded.
"""))

cells.append(code(r"""
feature_specs = [
    # family, feature, kind, description
    ("volatility acceleration", "vei", "continuous", "log short-RV / long-RV"),
    ("volatility acceleration", "vei_z", "continuous", "VEI relative to prior history"),
    ("volatility acceleration", "rv_short_long_ratio", "continuous", "short / long realised volatility"),
    ("volatility acceleration", "rv_acceleration", "continuous", "change in log realised volatility"),
    ("volatility acceleration", "atr_short_long_ratio", "continuous", "short / long true range"),
    ("volatility acceleration", "garch_acceleration", "continuous", "change in train-fitted GARCH forecast"),
    ("volatility level", "rv_long", "continuous", "annualised long-window realised volatility"),
    ("volatility level", "rv_long_z", "continuous", "realised-volatility z-score"),
    ("volatility level", "rv_long_percentile", "continuous", "realised-volatility trailing percentile"),
    ("volatility level", "atr_pct", "continuous", "ATR as fraction of price"),
    ("volatility level", "atr_pct_z", "continuous", "ATR-percent z-score"),
    ("volatility level", "garch_vol", "continuous", "train-fitted GARCH forecast volatility"),
    ("trend", "ma_spread_atr", "continuous", "fast minus slow MA in ATR"),
    ("trend", "price_vs_ma_atr", "continuous", "price distance from slow MA in ATR"),
    ("trend", "ma_slope_atr", "continuous", "slow-MA slope in ATR"),
    ("trend", "trend_return", "continuous", "long-horizon return"),
    ("trend", "htf_slope_atr", "continuous", "completed higher-timeframe MA slope"),
    ("trend", "htf_price_vs_ma_atr", "continuous", "higher-timeframe price versus MA"),
    ("directional strength", "adx", "continuous", "Wilder ADX"),
    ("directional strength", "kaufman_er", "continuous", "Kaufman Efficiency Ratio"),
    ("directional strength", "di_spread", "continuous", "positive minus negative directional index"),
    ("distribution", "adf_pvalue", "continuous", "rolling price-level ADF p-value"),
    ("distribution", "hurst_exponent", "continuous", "rolling Hurst exponent estimate"),
    ("distribution", "return_skew", "continuous", "rolling return skewness"),
    ("distribution", "return_excess_kurtosis", "continuous", "rolling excess kurtosis"),
    ("dependence", "variance_ratio_4", "continuous", "four-bar variance ratio"),
    ("dependence", "rolling_covariance", "continuous", "return covariance with benchmark"),
    ("dependence", "rolling_correlation", "continuous", "return correlation with benchmark"),
    ("dependence", "rolling_beta", "continuous", "rolling beta to benchmark"),
    ("dependence", "downside_correlation", "continuous", "correlation when both returns are negative"),
    ("dependence", "relative_momentum", "continuous", "instrument minus benchmark momentum"),
    ("tail / jump", "bar_range_atr", "continuous", "current completed-bar range in ATR"),
    ("tail / jump", "jump_score", "continuous", "absolute return relative to local volatility"),
    ("tail / jump", "downside_semivol", "continuous", "downside semivolatility"),
    ("tail / jump", "semivol_imbalance", "continuous", "upside versus downside semivolatility"),
    ("tail / jump", "close_location", "continuous", "close location inside completed bar"),
    ("liquidity / quality", "bar_coverage", "continuous", "source observation coverage"),
    ("liquidity / quality", "missing_bar_fraction_1d", "continuous", "one-day missing observation fraction"),
    ("liquidity / quality", "gap_from_previous_close_atr", "continuous", "opening gap in ATR"),
    ("liquidity / quality", "market_feature_age_minutes", "continuous", "age of latest market feature"),
    ("calendar", "session_utc", "categorical", "UTC trading session"),
    ("calendar", "weekday", "categorical", "weekday"),
    ("calendar", "month", "categorical", "calendar month"),
    ("calendar", "month_end", "categorical", "month-end flag"),
    ("calendar", "quarter_end", "categorical", "quarter-end flag"),
    ("strategy state", "strategy_recent_mean_20", "continuous", "last 20 completed trades mean outcome"),
    ("strategy state", "strategy_recent_win_rate_20", "continuous", "last 20 completed trades win rate"),
    ("strategy state", "strategy_recent_vol_20", "continuous", "last 20 completed trades outcome volatility"),
    ("strategy state", "strategy_drawdown_after_exit", "continuous", "drawdown after last completed trade"),
    ("strategy state", "hours_since_previous_signal", "continuous", "time since preceding signal"),
    ("event proximity", "hours_since_event", "continuous", "hours since last supplied event"),
    ("event proximity", "hours_to_scheduled_event", "continuous", "hours to next known scheduled event"),
]
for lag in AUTOCORR_LAGS:
    feature_specs.append(("dependence", f"autocorr_{lag}", "continuous", f"rolling return autocorrelation at lag {lag}"))
for column in [c for c in enriched.columns if c.startswith("macro_") and c not in {"macro_available_time", "macro_age_days"}]:
    family = "macro / rates" if "rate" in column else "macro / inflation" if any(x in column for x in ["cpi", "ppi", "inflation"]) else "macro / economy"
    feature_specs.append((family, column, "continuous", column.removeprefix("macro_").replace("_", " ")))
for column in [c for c in enriched.columns if c.startswith("cross_") and c not in {"cross_available_time", "cross_asset_age_days"}]:
    feature_specs.append(("cross-asset / risk appetite", column, "continuous", column.removeprefix("cross_").replace("_", " ")))
for column in PRECOMPUTED_FEATURE_COLUMNS:
    feature_specs.append(("strategy-supplied", column, "continuous", "precomputed causal feature supplied with trades"))

feature_catalog = pd.DataFrame(feature_specs, columns=["family", "feature", "kind", "description"]).drop_duplicates("feature")
feature_catalog["available"] = feature_catalog["feature"].isin(enriched.columns)

available_features = feature_catalog.loc[feature_catalog["available"], "feature"].tolist()
coverage = enriched.groupby("split", observed=True)[available_features].agg(lambda s: s.notna().mean()).T
coverage = coverage.reindex(columns=active_splits)
coverage["minimum_active_coverage"] = coverage.min(axis=1)
feature_catalog = feature_catalog.merge(coverage.reset_index().rename(columns={"index": "feature"}), on="feature", how="left")
feature_catalog["eligible"] = feature_catalog["available"] & feature_catalog["minimum_active_coverage"].ge(MIN_FEATURE_COVERAGE)

display(feature_catalog.groupby(["family", "available", "eligible"], dropna=False).size().rename("features").to_frame())
display(feature_catalog.sort_values(["eligible", "minimum_active_coverage"], ascending=[False, False]).head(25))

coverage_plot = feature_catalog.loc[feature_catalog["available"], ["feature", *active_splits]].set_index("feature")
plt.figure(figsize=(7, max(5, len(coverage_plot) * 0.18)))
sns.heatmap(coverage_plot, vmin=0, vmax=1, cmap="viridis", annot=False)
plt.title("Feature availability by split")
plt.xlabel("split")
plt.ylabel("")
plt.tight_layout()
plt.show()
"""))

cells.append(markdown(r"""
## 12. Fit regime definitions on training only

Every eligible continuous feature is divided using training quantiles. Those
fixed numerical cut points are then applied unchanged to test and holdout.
This is crucial: re-ranking each test period into equal thirds would leak its
future distribution and hide genuine regime drift.

Categorical labels are not re-estimated. Sparse levels are retained in the raw
table but later fail the minimum-cell rule.
"""))

cells.append(code(r"""
eligible_catalog = feature_catalog.loc[feature_catalog["eligible"]].copy()
train_rows = enriched["split"].eq("train")
regime_thresholds = {}
regime_columns = []
new_regime_data = {}

for spec in eligible_catalog.itertuples(index=False):
    feature = spec.feature
    regime_column = f"regime__{feature}"
    if spec.kind == "continuous":
        train_values = pd.to_numeric(enriched.loc[train_rows, feature], errors="coerce").dropna()
        if len(train_values) < MIN_TRAIN_OBS or train_values.nunique() < 2:
            continue
        quantiles = np.linspace(0, 1, N_REGIME_BINS + 1)[1:-1]
        cut_points = np.unique(train_values.quantile(quantiles).to_numpy(dtype=float))
        if len(cut_points) == 0:
            continue
        labels = ["low", "high"] if len(cut_points) == 1 else ["low", "middle", "high"]
        edges = np.r_[-np.inf, cut_points, np.inf]
        new_regime_data[regime_column] = pd.cut(enriched[feature], bins=edges, labels=labels, include_lowest=True).astype("object")
        regime_thresholds[feature] = {
            "kind": "continuous",
            "cut_points": cut_points.tolist(),
            "labels": labels,
            "training_n": int(len(train_values)),
        }
    else:
        new_regime_data[regime_column] = enriched[feature].astype("object").where(enriched[feature].notna(), "missing").astype(str)
        regime_thresholds[feature] = {
            "kind": "categorical",
            "labels": sorted(new_regime_data[regime_column].loc[train_rows].dropna().unique().tolist()),
            "training_n": int(new_regime_data[regime_column].loc[train_rows].notna().sum()),
        }
    regime_columns.append(regime_column)

enriched = pd.concat([enriched, pd.DataFrame(new_regime_data, index=enriched.index)], axis=1).copy()

print(f"Eligible input features: {len(eligible_catalog)}")
print(f"Regime definitions fitted: {len(regime_columns)}")
display(pd.DataFrame([
    {"feature": feature, **definition}
    for feature, definition in regime_thresholds.items()
]).head(15))
"""))

cells.append(markdown(r"""
### Optional composite regime (train-fitted cluster)

Single-feature screens miss combinations such as high volatility plus weak
trend plus risk-off macro. This optional K-means view uses a predeclared list of
eligible continuous inputs, training-only median imputation and scaling, and
frozen centroids. Cluster numbers have no ordinal meaning.
"""))

cells.append(code(r"""
cluster_model_bundle = None
if RUN_COMPOSITE_CLUSTER:
    requested_cluster_features = [
        "vei_z", "rv_long_z", "garch_vol", "htf_slope_atr", "adx", "kaufman_er",
        "return_skew", "return_excess_kurtosis", "hurst_exponent", "autocorr_1",
        "rolling_correlation", "downside_correlation", "semivol_imbalance",
        "macro_equal_weight_macro_score", "cross_vix_z_252d", "cross_dxy_broad_change_21d",
        "strategy_drawdown_after_exit", "hours_since_previous_signal",
    ]
    cluster_features = [
        feature for feature in requested_cluster_features
        if feature in eligible_catalog.loc[eligible_catalog["kind"].eq("continuous"), "feature"].tolist()
    ][:MAX_COMPOSITE_FEATURES]
    if len(cluster_features) >= 3 and train_rows.sum() >= N_COMPOSITE_CLUSTERS * MIN_CELL_OBS:
        imputer = SimpleImputer(strategy="median")
        scaler = StandardScaler()
        train_matrix = imputer.fit_transform(enriched.loc[train_rows, cluster_features])
        train_matrix = scaler.fit_transform(train_matrix)
        cluster_model = KMeans(n_clusters=N_COMPOSITE_CLUSTERS, random_state=RANDOM_SEED, n_init=20)
        cluster_model.fit(train_matrix)
        all_matrix = scaler.transform(imputer.transform(enriched[cluster_features]))
        enriched["regime__composite_cluster"] = [f"cluster_{x}" for x in cluster_model.predict(all_matrix)]
        regime_columns.append("regime__composite_cluster")
        feature_catalog = pd.concat([feature_catalog, pd.DataFrame([{
            "family": "composite", "feature": "composite_cluster", "kind": "categorical",
            "description": "train-fitted multivariate K-means state", "available": True,
            "eligible": True, **{split: 1.0 for split in active_splits}, "minimum_active_coverage": 1.0,
        }])], ignore_index=True)
        regime_thresholds["composite_cluster"] = {
            "kind": "categorical", "labels": sorted(enriched["regime__composite_cluster"].unique()),
            "features": cluster_features,
        }
        cluster_model_bundle = {"imputer": imputer, "scaler": scaler, "model": cluster_model, "features": cluster_features}
        print("Composite features:", cluster_features)
    else:
        warnings.warn("Composite clustering skipped: fewer than three eligible inputs or too few training trades.")
"""))

cells.append(markdown(r"""
## 13. Overall strategy metrics before conditioning

These are the reference results the regimes must improve on. `trade_t_stat` is
the conventional mean/standard-error statistic and `daily_sharpe` aggregates
same-day trade returns first. CAGR and drawdown use sequential trade
compounding and are diagnostic if trades overlap.
"""))

cells.append(code(r"""
def summarise_trades(frame):
    'Compact net-trade and diagnostic portfolio metrics.'
    ordered = frame.sort_values("decision_time")
    outcome = ordered["outcome"].dropna()
    returns = ordered["trade_return"].fillna(0).clip(lower=-0.999)
    positive = outcome[outcome > 0].sum()
    negative = -outcome[outcome < 0].sum()
    equity = (1 + returns).cumprod()
    drawdown = equity / equity.cummax() - 1 if len(equity) else pd.Series(dtype=float)
    daily = ordered.assign(day=ordered["decision_time"].dt.floor("D")).groupby("day")["trade_return"].sum()
    elapsed_years = max((ordered["decision_time"].max() - ordered["decision_time"].min()).days / 365.25, 1 / 365.25) if len(ordered) > 1 else np.nan
    return pd.Series({
        "trades": len(outcome),
        "win_rate": outcome.gt(0).mean(),
        "mean_outcome": outcome.mean(),
        "median_outcome": outcome.median(),
        "total_outcome": outcome.sum(),
        "profit_factor": positive / negative if negative > 0 else np.nan,
        "trade_t_stat": outcome.mean() / (outcome.std(ddof=1) / math.sqrt(len(outcome))) if len(outcome) > 1 and outcome.std(ddof=1) > 0 else np.nan,
        "daily_sharpe": math.sqrt(252) * daily.mean() / daily.std(ddof=1) if len(daily) > 1 and daily.std(ddof=1) > 0 else np.nan,
        "cagr": equity.iloc[-1] ** (1 / elapsed_years) - 1 if len(equity) and elapsed_years > 0 and equity.iloc[-1] > 0 else np.nan,
        "max_drawdown": drawdown.min() if len(drawdown) else np.nan,
    })


overall_metrics = pd.DataFrame({split: summarise_trades(enriched.loc[enriched["split"].eq(split)]) for split in active_splits}).T
display(overall_metrics.style.format({
    "win_rate": "{:.1%}", "mean_outcome": "{:.3f}", "median_outcome": "{:.3f}",
    "profit_factor": "{:.2f}", "daily_sharpe": "{:.2f}", "cagr": "{:.1%}", "max_drawdown": "{:.1%}",
}))
"""))

cells.append(markdown(r"""
## 14. Performance by every regime

Each cell reports sample size, coverage share, net outcome, win rate, profit
factor, trade t-statistic, and a daily-clustered t-statistic. The daily version
reduces false precision when several trades share the same market day.
"""))

cells.append(code(r"""
regime_rows = []
for regime_column in regime_columns:
    feature = regime_column.removeprefix("regime__")
    family_match = feature_catalog.loc[feature_catalog["feature"].eq(feature), "family"]
    family = family_match.iloc[0] if len(family_match) else "unknown"
    for split in active_splits:
        split_frame = enriched.loc[enriched["split"].eq(split)].copy()
        split_total = len(split_frame)
        for label, group in split_frame.dropna(subset=[regime_column]).groupby(regime_column, observed=True):
            outcome = group["outcome"]
            positive = outcome[outcome > 0].sum()
            negative = -outcome[outcome < 0].sum()
            daily_outcome = group.assign(day=group["decision_time"].dt.floor("D")).groupby("day")["outcome"].sum()
            regime_rows.append({
                "family": family,
                "feature": feature,
                "split": split,
                "regime": str(label),
                "trades": len(group),
                "share_of_split": len(group) / split_total if split_total else np.nan,
                "mean_outcome": outcome.mean(),
                "median_outcome": outcome.median(),
                "total_outcome": outcome.sum(),
                "win_rate": outcome.gt(0).mean(),
                "profit_factor": positive / negative if negative > 0 else np.nan,
                "trade_t_stat": outcome.mean() / (outcome.std(ddof=1) / math.sqrt(len(outcome))) if len(outcome) > 1 and outcome.std(ddof=1) > 0 else np.nan,
                "daily_cluster_t": daily_outcome.mean() / (daily_outcome.std(ddof=1) / math.sqrt(len(daily_outcome))) if len(daily_outcome) > 1 and daily_outcome.std(ddof=1) > 0 else np.nan,
                "thin_cell": len(group) < MIN_CELL_OBS,
            })

regime_metrics = pd.DataFrame(regime_rows)
display(regime_metrics.sort_values(["split", "feature", "regime"]).head(30))
print("Regime cells:", len(regime_metrics), "| thin cells:", int(regime_metrics["thin_cell"].sum()))
"""))

cells.append(markdown(r"""
## 15. Train-to-test stability and circular-shift null

For continuous features, the declared contrast is high minus low. For
categorical features, the training-best label is fixed and compared with all
other labels; that same label is evaluated in test. This category selection is
optimistic in training, which is why test confirmation matters.

The circular-shift null rotates the regime-label sequence relative to trade
outcomes. It preserves regime persistence and the outcome sequence while
breaking their alignment. Benjamini-Hochberg q-values control the false
discovery rate across the broad screen.
"""))

cells.append(code(r"""
def regime_contrast(frame, regime_column, kind, selected_label=None):
    'Return effect and the categorical label chosen on training when needed.'
    usable = frame.dropna(subset=[regime_column, "outcome"])
    if kind == "continuous":
        labels = regime_thresholds[regime_column.removeprefix("regime__")]["labels"]
        low_label, high_label = labels[0], labels[-1]
        low = usable.loc[usable[regime_column].eq(low_label), "outcome"]
        high = usable.loc[usable[regime_column].eq(high_label), "outcome"]
        if min(len(low), len(high)) < MIN_CELL_OBS:
            return np.nan, None
        return float(high.mean() - low.mean()), None
    means = usable.groupby(regime_column, observed=True)["outcome"].agg(["mean", "size"])
    valid_labels = means.index[means["size"].ge(MIN_CELL_OBS)]
    if selected_label is None:
        if len(valid_labels) < 2:
            return np.nan, None
        selected_label = means.loc[valid_labels, "mean"].idxmax()
    selected = usable.loc[usable[regime_column].eq(selected_label), "outcome"]
    rest = usable.loc[~usable[regime_column].eq(selected_label), "outcome"]
    if min(len(selected), len(rest)) < MIN_CELL_OBS:
        return np.nan, selected_label
    return float(selected.mean() - rest.mean()), selected_label


def contrast_from_arrays(outcomes, labels, kind, feature, selected_label=None):
    'Fast contrast used inside the permutation loop; no DataFrame copies.'
    outcomes = np.asarray(outcomes, dtype=float)
    labels = np.asarray(labels, dtype=object)
    valid = np.isfinite(outcomes) & pd.notna(labels)
    if kind == "continuous":
        ordered_labels = regime_thresholds[feature]["labels"]
        low_mask = valid & (labels == ordered_labels[0])
        high_mask = valid & (labels == ordered_labels[-1])
        if min(low_mask.sum(), high_mask.sum()) < MIN_CELL_OBS:
            return np.nan
        return float(outcomes[high_mask].mean() - outcomes[low_mask].mean())
    selected_mask = valid & (labels == selected_label)
    rest_mask = valid & (labels != selected_label)
    if min(selected_mask.sum(), rest_mask.sum()) < MIN_CELL_OBS:
        return np.nan
    return float(outcomes[selected_mask].mean() - outcomes[rest_mask].mean())


rng = np.random.default_rng(RANDOM_SEED)
stability_rows = []
for regime_column in regime_columns:
    feature = regime_column.removeprefix("regime__")
    kind_match = feature_catalog.loc[feature_catalog["feature"].eq(feature), "kind"]
    kind = kind_match.iloc[0] if len(kind_match) else "categorical"
    train_frame = enriched.loc[enriched["split"].eq("train")].sort_values("decision_time")
    test_frame = enriched.loc[enriched["split"].eq("test")].sort_values("decision_time")
    train_effect, selected_label = regime_contrast(train_frame, regime_column, kind)
    test_effect, _ = regime_contrast(test_frame, regime_column, kind, selected_label)

    split_pvalues = {}
    for split_name, split_frame, observed_effect in [("train", train_frame, train_effect), ("test", test_frame, test_effect)]:
        null_effects = []
        n = len(split_frame)
        if np.isfinite(observed_effect) and n >= 2 * MIN_CELL_OBS:
            labels_original = split_frame[regime_column].to_numpy(copy=True)
            outcomes_original = split_frame["outcome"].to_numpy(dtype=float, copy=True)
            min_shift = max(5, n // 10)
            max_shift = max(min_shift + 1, n - min_shift)
            for _ in range(N_PERMUTATIONS):
                shift = int(rng.integers(min_shift, max_shift))
                null_effect = contrast_from_arrays(
                    outcomes_original,
                    np.roll(labels_original, shift),
                    kind,
                    feature,
                    selected_label,
                )
                if np.isfinite(null_effect):
                    null_effects.append(null_effect)
        split_pvalues[split_name] = (
            (1 + np.sum(np.abs(null_effects) >= abs(observed_effect))) / (1 + len(null_effects))
            if null_effects and np.isfinite(observed_effect) else np.nan
        )

    family_match = feature_catalog.loc[feature_catalog["feature"].eq(feature), "family"]
    stability_rows.append({
        "family": family_match.iloc[0] if len(family_match) else "unknown",
        "feature": feature,
        "kind": kind,
        "declared_contrast": "high - low" if kind == "continuous" else f"{selected_label} - rest",
        "train_effect": train_effect,
        "test_effect": test_effect,
        "same_sign": bool(np.sign(train_effect) == np.sign(test_effect)) if np.isfinite(train_effect) and np.isfinite(test_effect) else False,
        "effect_retention": test_effect / train_effect if np.isfinite(train_effect) and train_effect != 0 else np.nan,
        "train_permutation_p": split_pvalues["train"],
        "test_permutation_p": split_pvalues["test"],
    })

stability = pd.DataFrame(stability_rows)
for split in ["train", "test"]:
    p_column = f"{split}_permutation_p"
    q_column = f"{split}_fdr_q"
    valid = stability[p_column].notna()
    stability[q_column] = np.nan
    if valid.any():
        stability.loc[valid, q_column] = multipletests(stability.loc[valid, p_column], method="fdr_bh")[1]

stability["provisional_oos_confirmation"] = (
    stability["same_sign"]
    & stability["train_fdr_q"].lt(0.10)
    & stability["test_fdr_q"].lt(0.10)
)
stability["stability_score"] = stability["same_sign"].astype(int) * stability["test_effect"].abs() * (1 - stability["test_fdr_q"].fillna(1))
stability = stability.sort_values(["provisional_oos_confirmation", "stability_score"], ascending=[False, False]).reset_index(drop=True)
display(stability.head(25).style.format({
    "train_effect": "{:.3f}", "test_effect": "{:.3f}", "effect_retention": "{:.2f}",
    "train_permutation_p": "{:.3f}", "test_permutation_p": "{:.3f}",
    "train_fdr_q": "{:.3f}", "test_fdr_q": "{:.3f}",
}))
"""))

cells.append(markdown(r"""
## 16. Visual diagnostics

The first chart compares fixed train/test contrasts. The second shows all cells
for one selected feature. The third treats each regime as a causal gate—trades
outside the gate receive zero return—to make the economic effect easier to see.
This gated curve is still diagnostic when trades overlap.
"""))

cells.append(code(r"""
plot_stability = stability.dropna(subset=["train_effect", "test_effect"]).head(18).sort_values("test_effect")
if not plot_stability.empty:
    positions = np.arange(len(plot_stability))
    fig, ax = plt.subplots(figsize=(10, max(5, len(plot_stability) * 0.35)))
    ax.barh(positions - 0.18, plot_stability["train_effect"], height=0.35, label="train")
    ax.barh(positions + 0.18, plot_stability["test_effect"], height=0.35, label="test")
    ax.axvline(0, color="black", linewidth=1)
    ax.set_yticks(positions, plot_stability["feature"])
    ax.set_xlabel("declared contrast in net outcome")
    ax.set_title("Train-to-test regime contrast stability")
    ax.legend()
    plt.tight_layout()
    plt.show()

if PLOT_FEATURE not in regime_thresholds:
    available_plot_features = [f for f in stability["feature"] if f in regime_thresholds]
    PLOT_FEATURE = available_plot_features[0] if available_plot_features else None

if PLOT_FEATURE:
    selected_metrics = regime_metrics.loc[regime_metrics["feature"].eq(PLOT_FEATURE) & ~regime_metrics["thin_cell"]].copy()
    if not selected_metrics.empty:
        plt.figure(figsize=(9, 5))
        sns.barplot(data=selected_metrics, x="regime", y="mean_outcome", hue="split", errorbar=None)
        plt.axhline(0, color="black", linewidth=1)
        plt.title(f"Mean net outcome by {PLOT_FEATURE} regime")
        plt.ylabel("mean outcome")
        plt.tight_layout()
        plt.show()

    plot_split = "test"
    plot_frame = enriched.loc[enriched["split"].eq(plot_split)].sort_values("decision_time").copy()
    regime_column = f"regime__{PLOT_FEATURE}"
    if regime_column in plot_frame and plot_frame[regime_column].notna().any():
        fig, ax = plt.subplots(figsize=(11, 5))
        baseline_equity = (1 + plot_frame.set_index("decision_time")["trade_return"].clip(lower=-0.999)).cumprod()
        ax.plot(baseline_equity, color="black", linewidth=2, label="all trades")
        for label in plot_frame[regime_column].dropna().unique():
            gated = plot_frame["trade_return"].where(plot_frame[regime_column].eq(label), 0).clip(lower=-0.999)
            gated_equity = (1 + gated).cumprod()
            gated_equity.index = plot_frame["decision_time"]
            ax.plot(gated_equity, alpha=0.85, label=str(label))
        ax.set_title(f"Diagnostic {plot_split} equity if gated by {PLOT_FEATURE}")
        ax.set_ylabel("growth of $1")
        ax.legend(ncol=2)
        plt.tight_layout()
        plt.show()
"""))

cells.append(markdown(r"""
## 17. Pairwise regime interactions

Markets are multidimensional, but a full Cartesian grid becomes sparse very
quickly. This section uses only the predeclared `INTERACTION_FEATURES`, keeps
cell counts visible, and refuses cells below `MIN_CELL_OBS`. Treat these as
exploratory hypotheses for a separately registered test—not as extra shots on
goal hidden inside the main screen.
"""))

cells.append(code(r"""
interaction_features = [f for f in INTERACTION_FEATURES if f"regime__{f}" in enriched.columns]
interaction_rows = []
for left_feature, right_feature in combinations(interaction_features, 2):
    left_regime, right_regime = f"regime__{left_feature}", f"regime__{right_feature}"
    for split in [s for s in active_splits if s in {"train", "test"}]:
        subset = enriched.loc[enriched["split"].eq(split)].dropna(subset=[left_regime, right_regime])
        grouped = subset.groupby([left_regime, right_regime], observed=True)["outcome"].agg(["size", "mean", "sum"])
        for (left_label, right_label), row in grouped.iterrows():
            interaction_rows.append({
                "left_feature": left_feature,
                "right_feature": right_feature,
                "left_regime": str(left_label),
                "right_regime": str(right_label),
                "split": split,
                "trades": int(row["size"]),
                "mean_outcome": row["mean"],
                "total_outcome": row["sum"],
                "thin_cell": row["size"] < MIN_CELL_OBS,
            })
interaction_metrics = pd.DataFrame(interaction_rows)
if not interaction_metrics.empty:
    display(interaction_metrics.loc[~interaction_metrics["thin_cell"]].sort_values(["split", "mean_outcome"], ascending=[True, False]).head(30))
    first_pair = interaction_metrics[["left_feature", "right_feature"]].drop_duplicates().iloc[0]
    heatmap_data = interaction_metrics.loc[
        interaction_metrics["split"].eq("test")
        & interaction_metrics["left_feature"].eq(first_pair["left_feature"])
        & interaction_metrics["right_feature"].eq(first_pair["right_feature"])
        & ~interaction_metrics["thin_cell"]
    ].pivot(index="left_regime", columns="right_regime", values="mean_outcome")
    if not heatmap_data.empty:
        plt.figure(figsize=(7, 5))
        sns.heatmap(heatmap_data, annot=True, fmt=".2f", cmap="RdYlGn", center=0)
        plt.title(f"Test mean outcome: {first_pair['left_feature']} × {first_pair['right_feature']}")
        plt.tight_layout()
        plt.show()
else:
    print("No configured interaction pair is available.")
"""))

cells.append(markdown(r"""
## 18. Trade drill-down

Select a row number within the test sample to inspect the price path around that
trade. The title carries its contemporaneous regime labels so a statistical
cell can be connected back to an actual setup. Entry and exit markers use the
authoritative trade table when those fields exist.
"""))

cells.append(code(r"""
test_trades = enriched.loc[enriched["split"].eq("test")].sort_values("decision_time").reset_index(drop=True)
if len(test_trades):
    selected_trade = test_trades.iloc[min(PLOT_TRADE_NUMBER, len(test_trades) - 1)]
    centre = selected_trade["decision_time"]
    window_start, window_end = centre - pd.Timedelta(days=2), centre + pd.Timedelta(days=2)
    price_window = mkt.loc[(mkt.index >= window_start) & (mkt.index <= window_end), "close"]
    fig, ax = plt.subplots(figsize=(12, 5))
    ax.plot(price_window.index, price_window, color="steelblue", linewidth=1, label=f"{INSTRUMENT} close")
    entry_time = selected_trade.get("entry_time", selected_trade["decision_time"])
    exit_time = selected_trade.get("exit_time", pd.NaT)
    entry_price = selected_trade.get("entry_price", np.nan)
    exit_price = selected_trade.get("exit_price", np.nan)
    if pd.notna(entry_time):
        entry_y = entry_price if np.isfinite(entry_price) else price_window.asof(entry_time)
        ax.scatter(entry_time, entry_y, marker="^", s=90, color="green", label="entry", zorder=5)
    if pd.notna(exit_time):
        exit_y = exit_price if np.isfinite(exit_price) else price_window.asof(exit_time)
        ax.scatter(exit_time, exit_y, marker="v", s=90, color="red", label="exit", zorder=5)
    regime_summary = ", ".join(
        f"{feature}={selected_trade.get('regime__' + feature)}"
        for feature in [PLOT_FEATURE, "htf_slope_atr", "adx", "composite_cluster"]
        if feature and f"regime__{feature}" in selected_trade.index
    )
    ax.set_title(f"Trade {int(selected_trade['trade_id'])}: {selected_trade['side']} | outcome={selected_trade['outcome']:.2f} | {regime_summary}")
    ax.legend()
    plt.tight_layout()
    plt.show()
    display(selected_trade[[c for c in ["trade_id", "decision_time", "entry_time", "exit_time", "side", "outcome", "split"] if c in selected_trade.index]].to_frame("value"))
"""))

cells.append(markdown(r"""
## 19. Regime persistence and transitions

A useful gate must occur often enough and persist long enough to trade. This
diagnostic measures consecutive run lengths on market bars for the selected
feature and the transition matrix between labels. It catches superficially
attractive regimes that flicker every bar.
"""))

cells.append(code(r"""
if PLOT_FEATURE in regime_thresholds and regime_thresholds[PLOT_FEATURE]["kind"] == "continuous" and PLOT_FEATURE in mkt:
    definition = regime_thresholds[PLOT_FEATURE]
    edges = np.r_[-np.inf, definition["cut_points"], np.inf]
    labels = definition["labels"]
    market_regime = pd.cut(mkt[PLOT_FEATURE], bins=edges, labels=labels, include_lowest=True).astype("object")
    run_id = market_regime.ne(market_regime.shift()).cumsum()
    run_lengths = pd.DataFrame({"regime": market_regime}).dropna().groupby(run_id).agg(regime=("regime", "first"), bars=("regime", "size"))
    persistence = run_lengths.groupby("regime")["bars"].agg(["count", "median", "mean", "max"])
    transition = pd.crosstab(market_regime.shift(), market_regime, normalize="index")
    display(persistence)
    display(transition.style.format("{:.1%}"))
"""))

cells.append(markdown(r"""
## 20. Decision table and interpretation checklist

`provisional_oos_confirmation=True` means only that a predeclared contrast kept
its sign and survived a 10% false-discovery-rate threshold in both train and
test under this null. It is **not** permission to open holdout and is not proof
of deployability.

Before promoting any regime gate:

1. Check the feature's time-of-day and split coverage, cell counts, and age.
2. Inspect costs, side balance, calendar-rate matching, and neighboring
   thresholds—not just the chosen quantile.
3. Register one exact gate and kill test before another experiment.
4. Re-run the authoritative stateful portfolio engine with skipped trades;
   do not rely on diagnostic row filtering when trades overlap.
5. Open holdout once, after the rule is frozen, and never tune on it afterward.
"""))

cells.append(code(r"""
decision_columns = [
    "family", "feature", "declared_contrast", "train_effect", "test_effect", "same_sign",
    "effect_retention", "train_fdr_q", "test_fdr_q", "provisional_oos_confirmation",
]
decision_table = stability[decision_columns].copy()
display(decision_table.head(30))

coverage_failures = feature_catalog.loc[
    feature_catalog["available"] & ~feature_catalog["eligible"],
    ["family", "feature", *active_splits, "minimum_active_coverage"],
].sort_values("minimum_active_coverage")
if not coverage_failures.empty:
    print("Available but excluded for coverage:")
    display(coverage_failures.head(20))

print("Holdout status:", "CONSUMED" if OPEN_HOLDOUT else "SEALED — no 2024+ trade or market rows loaded")
print("Provisional train+test confirmations:", int(stability["provisional_oos_confirmation"].sum()))
"""))

cells.append(markdown(r"""
## 21. Optional reproducible export

Set `WRITE_OUTPUTS=True` and use a registered experiment ID as `RUN_LABEL`.
The cell refuses to overwrite an existing directory unless explicitly allowed.
It stores the fixed thresholds and tables—not raw source data.
"""))

cells.append(code(r"""
run_config = {
    "instrument": INSTRUMENT,
    "frozen_trade_filters": FROZEN_TRADE_FILTERS,
    "frozen_parameter_snapshot": FROZEN_PARAMETER_SNAPSHOT,
    "trades_path": str(TRADES_PATH),
    "market_path": str(MARKET_PATH),
    "benchmark_path": str(BENCHMARK_PATH),
    "macro_source": str(MACRO_SOURCE) if MACRO_SOURCE else None,
    "timeframe_minutes": TIMEFRAME_MINUTES,
    "train": [str(train_start), str(train_end)],
    "test": [str(test_start), str(test_end)],
    "holdout": [str(holdout_start), str(holdout_end)],
    "holdout_opened": OPEN_HOLDOUT,
    "outcome_is_r": OUTCOME_IS_R,
    "risk_per_trade_pct": RISK_PER_TRADE_PCT,
    "n_regime_bins": N_REGIME_BINS,
    "min_cell_obs": MIN_CELL_OBS,
    "n_permutations": N_PERMUTATIONS,
    "random_seed": RANDOM_SEED,
    "garch_parameters": dict(zip(["omega", "alpha", "beta"], map(float, garch_parameters))),
}
config_fingerprint = hashlib.sha256(json.dumps(run_config, sort_keys=True).encode()).hexdigest()[:16]
print("Configuration fingerprint:", config_fingerprint)

if WRITE_OUTPUTS:
    output_dir = PROJECT_DIR / "artifacts" / "runs" / RUN_LABEL
    if output_dir.exists() and any(output_dir.iterdir()) and not ALLOW_OUTPUT_OVERWRITE:
        raise FileExistsError(f"Refusing to overwrite populated run directory: {output_dir}")
    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "config.json").write_text(json.dumps(run_config, indent=2, default=str), encoding="utf-8")
    (output_dir / "regime_thresholds.json").write_text(json.dumps(regime_thresholds, indent=2, default=str), encoding="utf-8")
    overall_metrics.to_csv(output_dir / "overall_metrics.csv", index_label="split")
    feature_catalog.to_csv(output_dir / "feature_catalog.csv", index=False)
    regime_metrics.to_csv(output_dir / "regime_metrics.csv", index=False)
    stability.to_csv(output_dir / "stability.csv", index=False)
    decision_table.to_csv(output_dir / "decision_table.csv", index=False)
    if not interaction_metrics.empty:
        interaction_metrics.to_csv(output_dir / "interaction_metrics.csv", index=False)
    print("Wrote:", output_dir)
"""))

cells.append(markdown(r"""
## What this covers—and what needs a separate data adapter

Implemented families include macro growth/inflation/rates, volatility
acceleration and level, GARCH, multi-timeframe trend, ADX, Kaufman efficiency,
stationarity, skew, kurtosis, Hurst, autocorrelation, variance ratio,
cross-market covariance/correlation/beta, tail asymmetry, jumps, bar quality,
calendar/session, cross-asset risk appetite, completed-trade strategy state,
event proximity, multivariate clusters, persistence, and pairwise interactions.

Two useful families cannot be honestly inferred from OHLC plus trades alone:

- **True liquidity / positioning:** bid-ask spread, depth, volume, CFTC
  positioning, options skew, and dealer gamma require dedicated point-in-time
  sources. Bar completeness and gap size are only proxies.
- **Surprise and event semantics:** realised-versus-consensus macro surprise,
  central-bank tone, and event importance require timestamped vintages and the
  calendar that was known at the time.

Add those as causal columns to `macro_input`, `cross_asset_input`,
`events_input`, or `PRECOMPUTED_FEATURE_COLUMNS`; the thresholding, validation,
metrics, and visual pipeline will pick them up without changing strategy code.
"""))


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUTPUT.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"Wrote {OUTPUT} with {len(cells)} cells")
