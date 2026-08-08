"""Build the editable, holdout-guarded, single-pair research notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "single_pair_zband_workbench.ipynb"


def md(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type": "markdown", "id": hashlib.sha1(("m" + source).encode()).hexdigest()[:12],
            "metadata": {}, "source": source.splitlines(keepends=True)}


def code(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type": "code", "id": hashlib.sha1(("c" + source).encode()).hexdigest()[:12],
            "execution_count": None, "metadata": {}, "outputs": [],
            "source": source.splitlines(keepends=True)}


cells = [
    md(r"""
    # Single-pair anchored Z-band research workbench

    This notebook is meant to be read and edited from top to bottom. It performs
    the data loading, feature calculation, parameter tuning, causal execution,
    metrics, and trade visualization directly in the notebook.

    Strategy clock:

    1. A completed signal bar closes beyond the arming Z threshold.
    2. A later completed bar closes back inside the same band without crossing the baseline.
    3. Entry occurs at the next observed complete signal bar's open.
    4. A frozen ATR stop and R-multiple target are replayed on the underlying one-minute bars.

    The default uses the clarified values: ±2.5Z arming and a 2.0×ATR stop.
    Position units are recalculated at every entry as percentage-of-equity risk
    divided by the ATR stop distance, so a wider volatility stop produces a
    smaller position.
    """),
    md(r"""
    ## 1. Imports and project location

    No project backtest module is imported. The calculations below are visible in
    this notebook so parameters and assumptions can be followed in sequence.
    """),
    code(r"""
    from itertools import product
    from pathlib import Path
    import os
    import warnings

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import matplotlib.dates as mdates
    from matplotlib.patches import Rectangle
    import seaborn as sns
    from IPython.display import display

    warnings.filterwarnings("ignore", category=FutureWarning)
    sns.set_theme(style="whitegrid", context="notebook")
    pd.set_option("display.max_columns", 100)
    pd.set_option("display.width", 240)

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == "exploration_3" else here / "forex" / "exploration_3"
    DATA_DIR = PROJECT_ROOT.parent / "data" / "clean"
    if not DATA_DIR.exists():
        raise FileNotFoundError("Run from the workspace root or forex/exploration_3")

    SMOKE_MODE = os.getenv("ZBAND_NOTEBOOK_SMOKE", "0") == "1"
    print("Project:", PROJECT_ROOT)
    print("Data:", DATA_DIR)
    """),
    md(r"""
    ## 2. Controls — edit this cell first

    `TRAIN_START` and `TRAIN_END` define the only rows used to rank parameter
    candidates. `OOS_START` and `OOS_END` are evaluated only after a candidate is
    selected. The default loader stops before 2024, so later data never enters memory.

    To open the holdout after every decision is frozen, set `OPEN_HOLDOUT=True` and
    type the exact confirmation phrase. Do not change a parameter after reading it.
    """),
    code(r"""
    # ------------------------------- market ---------------------------------
    PAIR = "EURUSD"               # AUDUSD, EURUSD, GBPUSD, NZDUSD
    SIGNAL_BAR_MINUTES = 15
    PRICE_SOURCE = "hlc3"         # close, hlc3, or ohlc4
    SESSION_TIMEZONE = "America/New_York"
    SESSION_START_HOUR = 17

    # -------------------------- development windows -------------------------
    TRAIN_START = "2012-01-01"
    TRAIN_END = "2020-01-01"      # exclusive
    OOS_START = "2021-01-01"
    OOS_END = "2024-01-01"        # exclusive
    WARMUP_DAYS = 30

    # ----------------------------- holdout lock ------------------------------
    HOLDOUT_START = "2024-01-01"
    HOLDOUT_END = None             # None means latest available row
    OPEN_HOLDOUT = False
    HOLDOUT_CONFIRMATION = ""      # required: FINAL CONFIGURATION IS FROZEN

    # ------------------------- manually chosen strategy ---------------------
    MANUAL_ANCHOR_MODE = "session" # session or sma
    MANUAL_SMA_LENGTH = 20
    MANUAL_ARM_Z = 2.5
    MANUAL_MAX_ARM_BARS = 10
    MANUAL_ATR_LENGTH = 14
    MANUAL_ATR_STOP_MULT = 2.0
    MANUAL_TARGET_R = 1.0

    # -------------------- optional train-only parameter search ---------------
    RUN_GRID_SEARCH = True
    GRID_ANCHOR_MODES = ["session", "sma"]
    GRID_SMA_LENGTHS = [10, 20, 40, 80]
    GRID_ARM_Z = [2.5]
    GRID_MAX_ARM_BARS = [10]
    GRID_ATR_LENGTHS = [14]
    GRID_ATR_STOP_MULT = [2.0]
    GRID_TARGET_R = [1.0]
    SELECTION_METRIC = "daily_sharpe_net_return"
    MIN_TRAIN_TRADES = 100
    MAX_CONFIGS = 250

    # ---------------------- risk sizing and account view ---------------------
    ROUND_TRIP_COST_PIPS = 1.0
    STARTING_CAPITAL_USD = 100_000
    RISK_PER_TRADE_PCT = 1.0       # cash risk to the ATR stop, before trading costs
    MAX_LEVERAGE = None            # e.g. 30.0 to cap notional/equity; None keeps pure risk scaling

    # ------------------------------ charts ----------------------------------
    TRADE_CHART_SAMPLE = "oos"    # train, oos, or holdout after it is opened
    TRADE_NUMBER = 0               # zero-based row within that sample
    CHART_BARS_BEFORE = 30
    CHART_BARS_AFTER = 30

    if SMOKE_MODE:
        TRAIN_START, TRAIN_END = "2018-01-01", "2019-01-01"
        OOS_START, OOS_END = "2021-01-01", "2021-07-01"
        GRID_SMA_LENGTHS = [20]

    SUPPORTED_PAIRS = {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD"}
    assert PAIR in SUPPORTED_PAIRS
    assert PRICE_SOURCE in {"close", "hlc3", "ohlc4"}
    assert MANUAL_ANCHOR_MODE in {"session", "sma"}
    assert 0 < RISK_PER_TRADE_PCT <= 100
    assert MAX_LEVERAGE is None or MAX_LEVERAGE > 0
    assert pd.Timestamp(TRAIN_START) < pd.Timestamp(TRAIN_END) <= pd.Timestamp(OOS_START)
    assert pd.Timestamp(OOS_START) < pd.Timestamp(OOS_END) <= pd.Timestamp(HOLDOUT_START)
    if OPEN_HOLDOUT:
        assert HOLDOUT_CONFIRMATION == "FINAL CONFIGURATION IS FROZEN", "Holdout confirmation phrase is missing"

    print(f"Pair={PAIR}; train={TRAIN_START} to {TRAIN_END}; OOS={OOS_START} to {OOS_END}")
    print("Holdout access:", "OPEN" if OPEN_HOLDOUT else "LOCKED — no 2024+ rows will load")
    """),
    md(r"""
    ## 3. Build the candidate list

    The manual configuration is always included. If grid search is enabled, the
    Cartesian product below is deduplicated. For the session anchor, SMA length is
    irrelevant, so only one session candidate is kept for each other parameter set.
    """),
    code(r"""
    manual_config = {
        "name": "manual",
        "anchor_mode": MANUAL_ANCHOR_MODE,
        "sma_length": int(MANUAL_SMA_LENGTH) if MANUAL_ANCHOR_MODE == "sma" else 0,
        "arm_z": float(MANUAL_ARM_Z),
        "max_arm_bars": int(MANUAL_MAX_ARM_BARS),
        "atr_length": int(MANUAL_ATR_LENGTH),
        "atr_stop_mult": float(MANUAL_ATR_STOP_MULT),
        "target_r": float(MANUAL_TARGET_R),
    }

    candidates = [manual_config]
    if RUN_GRID_SEARCH:
        for anchor, sma, z, arm_bars, atr_len, atr_mult, target_r in product(
            GRID_ANCHOR_MODES, GRID_SMA_LENGTHS, GRID_ARM_Z, GRID_MAX_ARM_BARS,
            GRID_ATR_LENGTHS, GRID_ATR_STOP_MULT, GRID_TARGET_R,
        ):
            effective_sma = int(sma) if anchor == "sma" else 0
            candidates.append({
                "name": f"{anchor}|sma{effective_sma}|z{z}|arm{arm_bars}|atr{atr_len}x{atr_mult}|R{target_r}",
                "anchor_mode": anchor,
                "sma_length": effective_sma,
                "arm_z": float(z),
                "max_arm_bars": int(arm_bars),
                "atr_length": int(atr_len),
                "atr_stop_mult": float(atr_mult),
                "target_r": float(target_r),
            })

    keys = ["anchor_mode", "sma_length", "arm_z", "max_arm_bars", "atr_length", "atr_stop_mult", "target_r"]
    unique = {}
    for cfg in candidates:
        unique.setdefault(tuple(cfg[k] for k in keys), cfg)
    candidates = list(unique.values())
    assert len(candidates) <= MAX_CONFIGS, f"Grid has {len(candidates)} configs; raise MAX_CONFIGS deliberately"

    display(pd.DataFrame(candidates))
    print(f"{len(candidates)} unique configuration(s)")
    """),
    md(r"""
    ## 4. Load only the permitted one-minute rows

    The Parquet filter is applied before pandas receives the data. With the default
    lock, the maximum timestamp must be earlier than both `OOS_END` and the holdout
    boundary. Thirty warm-up days are loaded before training but never scored.
    """),
    code(r"""
    data_path = DATA_DIR / f"{PAIR}_1m_clean.parquet"
    load_start = pd.Timestamp(TRAIN_START) - pd.Timedelta(days=WARMUP_DAYS)
    if OPEN_HOLDOUT:
        load_end = pd.Timestamp(HOLDOUT_END) if HOLDOUT_END else None
    else:
        load_end = min(pd.Timestamp(OOS_END), pd.Timestamp(HOLDOUT_START))

    filters = [("ts_utc", ">=", load_start.to_pydatetime())]
    if load_end is not None:
        filters.append(("ts_utc", "<", load_end.to_pydatetime()))

    raw = pd.read_parquet(
        data_path,
        columns=["ts_utc", "open", "high", "low", "close"],
        filters=filters,
    ).reset_index(drop=True)
    raw["raw_i"] = np.arange(len(raw), dtype=np.int64)

    assert len(raw), "No rows match the requested dates"
    assert raw.ts_utc.is_monotonic_increasing
    if not OPEN_HOLDOUT:
        assert raw.ts_utc.max() < pd.Timestamp(HOLDOUT_START)

    print(f"Loaded {len(raw):,} one-minute rows")
    print("Coverage:", raw.ts_utc.min(), "to", raw.ts_utc.max())
    """),
    md(r"""
    ## 5. Core data-quality checks

    Short gaps count missing minutes inside gaps of at most three hours. Longer
    closures are reported separately because normal FX weekends belong there.
    Nothing is sorted or silently repaired before these checks.
    """),
    code(r"""
    minute_delta = raw.ts_utc.diff().dt.total_seconds().div(60)
    invalid_ohlc = (
        raw[["open", "high", "low", "close"]].isna().any(axis=1)
        | (raw.high < raw[["open", "close"]].max(axis=1))
        | (raw.low > raw[["open", "close"]].min(axis=1))
        | (raw.high < raw.low)
    )

    data_quality = pd.Series({
        "rows": len(raw),
        "duplicate_timestamps": int(raw.ts_utc.duplicated().sum()),
        "out_of_order_timestamps": int((minute_delta <= 0).sum()),
        "invalid_ohlc_rows": int(invalid_ohlc.sum()),
        "gaps_over_1_minute": int((minute_delta > 1).sum()),
        "missing_minutes_inside_gaps_le_180": int((minute_delta[(minute_delta > 1) & (minute_delta <= 180)] - 1).sum()),
        "long_closures_over_180_minutes": int((minute_delta > 180).sum()),
        "maximum_gap_minutes": float(minute_delta.max()),
        "roll_boundaries": 0,
        "roll_policy": "not applicable — spot FX",
    }, name=PAIR)
    display(data_quality.to_frame())
    assert data_quality[["duplicate_timestamps", "out_of_order_timestamps", "invalid_ohlc_rows"]].sum() == 0

    hourly_raw_coverage = raw.groupby(raw.ts_utc.dt.hour).size().rename("one_minute_rows").to_frame()
    hourly_raw_coverage.index.name = "utc_hour"
    display(hourly_raw_coverage.T)
    """),
    md(r"""
    ## 6. Aggregate complete signal bars

    OHLC is formed from the underlying one-minute rows. Partial intervals are
    reported and excluded from signal formation; exit replay still uses every
    available one-minute row.
    """),
    code(r"""
    indexed = raw.set_index("ts_utc", drop=False)
    rule = f"{SIGNAL_BAR_MINUTES}min"
    bars_all = indexed.resample(rule, origin="epoch", label="left", closed="left").agg(
        open=("open", "first"), high=("high", "max"), low=("low", "min"), close=("close", "last"),
        minute_count=("close", "count"), raw_start_i=("raw_i", "first"), raw_end_i=("raw_i", "last"),
    )
    bars_all.index.name = "bar_open"
    bars_all = bars_all.reset_index()
    bars_all["complete_bar"] = bars_all.minute_count.eq(SIGNAL_BAR_MINUTES)

    observed_intervals = bars_all.loc[bars_all.minute_count.gt(0)].copy()
    coarse_coverage = observed_intervals.groupby(observed_intervals.bar_open.dt.hour).agg(
        observed_intervals=("minute_count", "size"),
        complete_bars=("complete_bar", "sum"),
        raw_minutes=("minute_count", "sum"),
    )
    coarse_coverage["complete_share"] = coarse_coverage.complete_bars / coarse_coverage.observed_intervals
    coarse_coverage.index.name = "utc_hour"
    display(coarse_coverage)

    bars = bars_all.loc[bars_all.complete_bar].copy().reset_index(drop=True)
    bars[["minute_count", "raw_start_i", "raw_end_i"]] = bars[["minute_count", "raw_start_i", "raw_end_i"]].astype("int64")
    print(f"Kept {len(bars):,} complete {SIGNAL_BAR_MINUTES}-minute bars; excluded {(~observed_intervals.complete_bar).sum():,} partial intervals")
    """),
    md(r"""
    ## 7. Calculate source price, session TWAP/SDEV, SMA bands, and Wilder ATR

    This cell intentionally shows each indicator directly. The session starts at
    17:00 New York with real daylight-saving transitions. The session dispersion
    matches the supplied Pine algorithm: squared deviations accumulate against the
    running mean. SMA standard deviation uses the population convention.

    Wilder ATR is seeded with the first full-window simple average and then updated
    recursively. It is not pandas' common first-value EWM shortcut.
    """),
    code(r"""
    if PRICE_SOURCE == "close":
        bars["source_price"] = bars.close
    elif PRICE_SOURCE == "hlc3":
        bars["source_price"] = (bars.high + bars.low + bars.close) / 3.0
    else:
        bars["source_price"] = (bars.open + bars.high + bars.low + bars.close) / 4.0

    local_time = bars.bar_open.dt.tz_localize("UTC").dt.tz_convert(SESSION_TIMEZONE)
    shifted_session_time = local_time - pd.Timedelta(hours=SESSION_START_HOUR)
    bars["session_id"] = shifted_session_time.dt.strftime("%Y-%m-%d")
    bars["session_slot"] = ((local_time.dt.hour - SESSION_START_HOUR) % 24) * 60 + local_time.dt.minute

    session_group = bars.source_price.groupby(bars.session_id, sort=False)
    session_count = session_group.cumcount() + 1
    bars["session_twap"] = session_group.cumsum() / session_count
    running_residual = bars.source_price - bars.session_twap
    bars["session_std"] = np.sqrt(running_residual.pow(2).groupby(bars.session_id, sort=False).cumsum() / session_count)
    bars.loc[session_count.eq(1), "session_std"] = np.nan

    needed_sma_lengths = sorted({MANUAL_SMA_LENGTH, *GRID_SMA_LENGTHS})
    for length in needed_sma_lengths:
        bars[f"sma_{length}"] = bars.source_price.rolling(length, min_periods=length).mean()
        bars[f"sma_std_{length}"] = bars.source_price.rolling(length, min_periods=length).std(ddof=0)

    previous_close = bars.close.shift(1)
    true_range = pd.concat([
        bars.high - bars.low,
        (bars.high - previous_close).abs(),
        (bars.low - previous_close).abs(),
    ], axis=1).max(axis=1).to_numpy(float).copy()
    true_range[0] = bars.high.iloc[0] - bars.low.iloc[0]

    needed_atr_lengths = sorted({MANUAL_ATR_LENGTH, *GRID_ATR_LENGTHS})
    for length in needed_atr_lengths:
        atr = np.full(len(bars), np.nan)
        if len(bars) >= length:
            atr[length - 1] = true_range[:length].mean()
            for i in range(length, len(bars)):
                atr[i] = atr[i - 1] + (true_range[i] - atr[i - 1]) / length
        bars[f"atr_{length}"] = atr

    display(bars[["bar_open", "open", "high", "low", "close", "session_id", "session_twap", "session_std",
                  f"sma_{MANUAL_SMA_LENGTH}", f"sma_std_{MANUAL_SMA_LENGTH}", f"atr_{MANUAL_ATR_LENGTH}"]].head(20))
    """),
    md(r"""
    ## 8. Exit replay helper

    This small helper does one job: starting at the entry minute, find the first
    reachable stop or target. The fill minute is included. Gap-through exits use
    the minute open, and unresolved same-minute dual touches go to the stop.
    """),
    code(r"""
    raw_time = raw.ts_utc.to_numpy()
    raw_open = raw.open.to_numpy(float)
    raw_high = raw.high.to_numpy(float)
    raw_low = raw.low.to_numpy(float)
    raw_close = raw.close.to_numpy(float)

    def replay_frozen_bracket(start_i, final_i, side, stop, target):
        for j in range(start_i, final_i + 1):
            op = raw_open[j]
            if side == 1:
                if op <= stop: return j, op, "stop", False, True
                if op >= target: return j, op, "target", False, True
                hit_stop, hit_target = raw_low[j] <= stop, raw_high[j] >= target
            else:
                if op >= stop: return j, op, "stop", False, True
                if op <= target: return j, op, "target", False, True
                hit_stop, hit_target = raw_high[j] >= stop, raw_low[j] <= target

            if hit_stop and hit_target: return j, stop, "stop", True, False
            if hit_stop: return j, stop, "stop", False, False
            if hit_target: return j, target, "target", False, False

        return final_i, raw_close[final_i], "window_end", False, False
    """),
    md(r"""
    ## 9. One transparent state-machine pass

    Parameter tuning needs to rerun identical state and execution logic, so this is
    the notebook's one substantial reusable block. It is kept in one cell and follows
    the strategy in chronological order: position gate → arm → disarm → re-entry →
    next-open fill → frozen bracket replay. Arrays are used only for speed.
    """),
    code(r"""
    PIP_SIZE = 0.0001

    def run_one_configuration(scope, config, final_raw_i, round_trip_cost_pips=ROUND_TRIP_COST_PIPS):
        baseline = (scope.session_twap.to_numpy(float) if config["anchor_mode"] == "session"
                    else scope[f"sma_{config['sma_length']}"] .to_numpy(float))
        dispersion = (scope.session_std.to_numpy(float) if config["anchor_mode"] == "session"
                      else scope[f"sma_std_{config['sma_length']}"] .to_numpy(float))
        atr = scope[f"atr_{config['atr_length']}"] .to_numpy(float)
        high, low, close = (scope.high.to_numpy(float), scope.low.to_numpy(float), scope.close.to_numpy(float))
        start_i = scope.raw_start_i.to_numpy(np.int64)
        end_i = scope.raw_end_i.to_numpy(np.int64)
        bar_time = scope.bar_open.to_numpy()
        session = scope.session_id.to_numpy()

        armed_long = armed_short = False
        armed_long_bar = armed_short_bar = -1
        active_exit_i = -1
        equity = float(STARTING_CAPITAL_USD)
        records = []

        for i in range(len(scope) - 1):
            if active_exit_i > end_i[i]:
                armed_long = armed_short = False
                continue
            if not (np.isfinite(baseline[i]) and np.isfinite(dispersion[i]) and dispersion[i] > 0):
                continue

            lower_band = baseline[i] - config["arm_z"] * dispersion[i]
            upper_band = baseline[i] + config["arm_z"] * dispersion[i]
            if close[i] < lower_band and not armed_long:
                armed_long, armed_long_bar = True, i
            if close[i] > upper_band and not armed_short:
                armed_short, armed_short_bar = True, i

            if armed_long and (i - armed_long_bar > config["max_arm_bars"] or close[i] >= baseline[i]):
                armed_long = False
            if armed_short and (i - armed_short_bar > config["max_arm_bars"] or close[i] <= baseline[i]):
                armed_short = False

            side = 1 if armed_long and close[i] > lower_band else 0
            if side == 0 and armed_short and close[i] < upper_band:
                side = -1
            if side == 0 or not np.isfinite(atr[i]) or atr[i] <= 0:
                continue

            entry_i = int(start_i[i + 1])
            if entry_i > final_raw_i:
                break
            entry_price = raw_open[entry_i]
            risk_price = atr[i] * config["atr_stop_mult"]
            equity_before = equity
            intended_risk_usd = equity_before * RISK_PER_TRADE_PCT / 100.0
            position_units = intended_risk_usd / risk_price
            if MAX_LEVERAGE is not None:
                maximum_units = equity_before * MAX_LEVERAGE / entry_price
                position_units = min(position_units, maximum_units)
            actual_risk_usd = position_units * risk_price
            notional_usd = position_units * entry_price
            stop = entry_price - side * risk_price
            target = entry_price + side * risk_price * config["target_r"]
            exit_i, exit_price, reason, ambiguous, gap_exit = replay_frozen_bracket(
                entry_i, final_raw_i, side, stop, target
            )

            gross_pips = side * (exit_price - entry_price) / PIP_SIZE
            risk_pips = risk_price / PIP_SIZE
            gross_usd = position_units * side * (exit_price - entry_price)
            cost_usd = position_units * PIP_SIZE * round_trip_cost_pips
            net_usd = gross_usd - cost_usd
            equity = equity_before + net_usd
            records.append({
                "config": config["name"], "signal_time": pd.Timestamp(bar_time[i]) + pd.Timedelta(minutes=SIGNAL_BAR_MINUTES),
                "entry_time": pd.Timestamp(raw_time[entry_i]), "exit_time": pd.Timestamp(raw_time[exit_i]),
                "entry_session": session[i], "side": "long" if side == 1 else "short",
                "entry_price": entry_price, "exit_price": exit_price, "stop_price": stop, "target_price": target,
                "risk_pips": risk_pips, "signal_z": (close[i] - baseline[i]) / dispersion[i],
                "position_units": position_units, "notional_usd": notional_usd,
                "leverage": notional_usd / equity_before, "intended_risk_usd": intended_risk_usd,
                "actual_risk_usd": actual_risk_usd, "actual_risk_pct": 100 * actual_risk_usd / equity_before,
                "gross_pips": gross_pips, "cost_pips": round_trip_cost_pips,
                "net_pips": gross_pips - round_trip_cost_pips,
                "gross_usd": gross_usd, "cost_usd": cost_usd, "net_usd": net_usd,
                "equity_before_usd": equity_before, "equity_after_usd": equity,
                "net_return_on_equity": net_usd / equity_before,
                "gross_r": gross_usd / actual_risk_usd, "net_r": net_usd / actual_risk_usd,
                "exit_reason": reason, "ambiguous_1m": ambiguous, "gap_exit": gap_exit,
            })
            active_exit_i = exit_i
            armed_long = armed_short = False
            if equity <= 0:
                break

        trades = pd.DataFrame(records)
        if len(trades):
            trades["hold_minutes"] = (trades.exit_time - trades.entry_time).dt.total_seconds() / 60
            trades["entry_gap_minutes"] = (trades.entry_time - trades.signal_time).dt.total_seconds() / 60
        return trades
    """),
    md(r"""
    ## 10. Metric helpers

    Trade averages use a New-York-session clustered standard error. Within each
    session, sequential percentage returns compound; no-trade sessions receive zero
    before annualizing Sharpe. Units vary on every trade so the cash risk from entry
    to the ATR stop equals `RISK_PER_TRADE_PCT` of then-current equity, unless the
    optional leverage cap binds.
    """),
    code(r"""
    def session_clustered_t(values, clusters):
        frame = pd.DataFrame({"x": values, "g": clusters}).dropna()
        mean, n, groups = frame.x.mean(), len(frame), frame.g.nunique()
        if n < 2 or groups < 2: return np.nan
        cluster_scores = (frame.x - mean).groupby(frame.g).sum()
        variance = (groups / (groups - 1)) * cluster_scores.pow(2).sum() / n**2
        return mean / np.sqrt(variance) if variance > 0 else np.nan

    def summarize(trades, all_sessions):
        trades = trades.loc[trades.exit_reason.ne("window_end")].copy()
        if trades.empty: return {"trades": 0}
        daily = trades.groupby("entry_session").net_return_on_equity.apply(lambda x: (1.0 + x).prod() - 1.0)
        daily = daily.reindex(sorted(all_sessions), fill_value=0.0)
        daily_std = daily.std(ddof=1)
        equity_index = (1.0 + daily).cumprod()
        drawdown = equity_index / equity_index.cummax() - 1.0
        gains = trades.loc[trades.net_usd > 0, "net_usd"].sum()
        losses = -trades.loc[trades.net_usd < 0, "net_usd"].sum()
        total_return = equity_index.iloc[-1] - 1.0
        return {
            "trades": len(trades), "sessions": len(daily), "trades_per_session": len(trades) / len(daily),
            "gross_mean_pips": trades.gross_pips.mean(), "net_mean_pips": trades.net_pips.mean(),
            "gross_total_pips": trades.gross_pips.sum(), "cost_total_pips": trades.cost_pips.sum(),
            "net_total_pips": trades.net_pips.sum(), "gross_mean_r": trades.gross_r.mean(),
            "net_mean_r": trades.net_r.mean(), "net_r_cluster_t": session_clustered_t(trades.net_r, trades.entry_session),
            "win_rate_net": (trades.net_usd > 0).mean(), "net_profit_factor": gains / losses if losses > 0 else np.inf,
            "net_total_usd": trades.net_usd.sum(), "total_return_pct": 100 * total_return,
            "cagr_pct": (100 * ((1.0 + total_return) ** (252 / len(daily)) - 1.0)
                         if total_return > -1.0 else -100.0),
            "ending_equity_usd": STARTING_CAPITAL_USD * (1.0 + total_return),
            "daily_sharpe_net_return": np.sqrt(252) * daily.mean() / daily_std if daily_std > 0 else np.nan,
            "daily_worst_return_pct": 100 * daily.min(), "max_drawdown_pct": 100 * drawdown.min(),
            "median_risk_pips": trades.risk_pips.median(), "median_hold_minutes": trades.hold_minutes.median(),
            "median_position_units": trades.position_units.median(), "median_leverage": trades.leverage.median(),
            "maximum_leverage": trades.leverage.max(), "median_actual_risk_pct": trades.actual_risk_pct.median(),
            "ambiguous_1m_share": trades.ambiguous_1m.mean(), "gap_exit_share": trades.gap_exit.mean(),
        }
    """),
    md(r"""
    ## 11. Tune on the training window only

    Every candidate is truncated at `TRAIN_END`. A still-open final trade is marked
    `window_end` and excluded from selection metrics. OOS rows have not been passed
    through any candidate here.
    """),
    code(r"""
    train_start, train_end = pd.Timestamp(TRAIN_START), pd.Timestamp(TRAIN_END)
    train_bars = bars.loc[(bars.bar_open >= train_start) & (bars.bar_open < train_end)].reset_index(drop=True)
    train_final_raw_i = int(np.searchsorted(raw_time, np.datetime64(train_end), side="left") - 1)
    train_sessions = set(train_bars.session_id.unique())
    assert len(train_bars) and train_final_raw_i >= 0

    tuning_rows = []
    tuning_trades = {}
    for number, cfg in enumerate(candidates, start=1):
        candidate_trades = run_one_configuration(train_bars, cfg, train_final_raw_i)
        tuning_trades[cfg["name"]] = candidate_trades
        row = cfg.copy()
        row.update(summarize(candidate_trades, train_sessions))
        tuning_rows.append(row)
        print(f"[{number:>3}/{len(candidates)}] {cfg['name']}: {row.get('trades', 0):,} trades; {SELECTION_METRIC}={row.get(SELECTION_METRIC, np.nan):.4f}")

    tuning = pd.DataFrame(tuning_rows)
    eligible = tuning.loc[tuning.trades >= MIN_TRAIN_TRADES].copy()
    assert len(eligible), "No candidate reaches MIN_TRAIN_TRADES"
    tuning = tuning.sort_values(SELECTION_METRIC, ascending=False, na_position="last").reset_index(drop=True)

    if RUN_GRID_SEARCH:
        selected_name = eligible.sort_values(SELECTION_METRIC, ascending=False, na_position="last").iloc[0]["name"]
        selected_config = next(cfg for cfg in candidates if cfg["name"] == selected_name)
    else:
        selected_config = manual_config
    tuning["selected"] = tuning.name.eq(selected_config["name"])

    display(tuning[["name", "anchor_mode", "sma_length", "arm_z", "atr_stop_mult", "target_r", "trades",
                    "gross_mean_pips", "net_mean_pips", "net_mean_r", "net_r_cluster_t",
                    "total_return_pct", "daily_sharpe_net_return", "max_drawdown_pct", "selected"]].round(4))
    print("Selected from training only:", selected_config)
    """),
    md(r"""
    ## 12. Freeze the selection, then run each allowed evaluation segment

    Training and OOS are run separately so positions, state, and end marks cannot
    leak across the unused calendar gap. Holdout execution is impossible unless its
    rows passed the explicit loader lock near the top.
    """),
    code(r"""
    segments = {
        "train": (pd.Timestamp(TRAIN_START), pd.Timestamp(TRAIN_END)),
        "oos": (pd.Timestamp(OOS_START), pd.Timestamp(OOS_END)),
    }
    if OPEN_HOLDOUT:
        holdout_end = pd.Timestamp(HOLDOUT_END) if HOLDOUT_END else raw.ts_utc.max() + pd.Timedelta(minutes=1)
        segments["holdout"] = (pd.Timestamp(HOLDOUT_START), holdout_end)

    segment_trades = {}
    segment_sessions = {}
    for label, (start, end) in segments.items():
        scope = bars.loc[(bars.bar_open >= start) & (bars.bar_open < end)].reset_index(drop=True)
        final_raw_i = int(np.searchsorted(raw_time, np.datetime64(end), side="left") - 1)
        result = run_one_configuration(scope, selected_config, final_raw_i)
        result = result.loc[result.exit_reason.ne("window_end")].copy()
        result["sample"] = label
        segment_trades[label] = result
        segment_sessions[label] = set(scope.session_id.unique())

    trades = pd.concat(segment_trades.values(), ignore_index=True)
    assert (trades.entry_time >= trades.signal_time).all()
    assert (trades.exit_time >= trades.entry_time).all()
    assert np.allclose(trades.net_pips, trades.gross_pips - trades.cost_pips)
    assert np.allclose(trades.net_usd, trades.gross_usd - trades.cost_usd)
    assert np.allclose(trades.equity_after_usd, trades.equity_before_usd + trades.net_usd)
    for label, group in trades.groupby("sample"):
        ordered = group.sort_values("entry_time")
        assert (ordered.entry_time.iloc[1:].to_numpy() >= ordered.exit_time.iloc[:-1].to_numpy()).all()

    print(trades.groupby("sample").size())
    print("Temporal, cost, and non-overlap assertions passed")
    """),
    md(r"""
    ## 13. Selected-feature coverage by period and time of day

    This is the rolling-window underpopulation report. Missing values are never
    silently converted into signals. Session dispersion is expected to be undefined
    on the first bar of each session; SMA/ATR warm-up occurs before scored dates.
    """),
    code(r"""
    if selected_config["anchor_mode"] == "session":
        selected_baseline = bars.session_twap
        selected_std = bars.session_std
    else:
        selected_baseline = bars[f"sma_{selected_config['sma_length']}"]
        selected_std = bars[f"sma_std_{selected_config['sma_length']}"]
    selected_atr = bars[f"atr_{selected_config['atr_length']}"]

    bars["selected_baseline"] = selected_baseline
    bars["selected_std"] = selected_std
    bars["selected_atr"] = selected_atr
    bars["decision_ready"] = selected_baseline.notna() & selected_std.gt(0) & selected_atr.gt(0)

    coverage_rows = []
    for label, (start, end) in segments.items():
        view = bars.loc[(bars.bar_open >= start) & (bars.bar_open < end)].copy()
        view["utc_hour"] = view.bar_open.dt.hour
        report = view.groupby("utc_hour").decision_ready.agg(["size", "sum"]).reset_index()
        report.columns = ["utc_hour", "signal_bars", "decision_ready"]
        report.insert(0, "sample", label)
        report["underpopulated_rows"] = report.signal_bars - report.decision_ready
        report["decision_ready_share"] = report.decision_ready / report.signal_bars
        coverage_rows.append(report)
    feature_coverage = pd.concat(coverage_rows, ignore_index=True)
    display(feature_coverage)
    """),
    md(r"""
    ## 14. Complete metric table and annual breakdown

    Gross, costs, and net are all shown. Position units change trade by trade so the
    ATR-stop cash risk is a fixed percentage of current equity. Dollar results remain
    illustrative because the archive contains midpoint rather than bid/ask prices.
    """),
    code(r"""
    metric_rows = []
    daily_frames = []
    for label, sample_trades in segment_trades.items():
        row = {"sample": label}
        row.update(summarize(sample_trades, segment_sessions[label]))
        metric_rows.append(row)

        daily = sample_trades.groupby("entry_session").net_return_on_equity.apply(lambda x: (1.0 + x).prod() - 1.0)
        daily = daily.reindex(sorted(segment_sessions[label]), fill_value=0.0)
        daily_frames.append(pd.DataFrame({"session_date": pd.to_datetime(daily.index), "daily_return": daily.values, "sample": label}))

    metrics = pd.DataFrame(metric_rows)
    display(metrics.round(4))

    annual_rows = []
    for (label, year), group in trades.groupby(["sample", trades.entry_time.dt.year]):
        year_sessions = {s for s in segment_sessions[label] if str(s).startswith(str(year))}
        row = {"sample": label, "year": int(year)}
        row.update(summarize(group, year_sessions))
        annual_rows.append(row)
    annual = pd.DataFrame(annual_rows)
    display(annual[["sample", "year", "trades", "gross_mean_pips", "net_mean_pips", "net_mean_r",
                    "total_return_pct", "daily_sharpe_net_return", "max_drawdown_pct"]].round(4))
    """),
    md(r"""
    ## 15. Performance visualizations

    Each segment starts at the editable initial capital so train and OOS remain
    comparable. Equity compounds the fixed percentage risk sizing; the unused
    calendar gap contributes no trades or returns.
    """),
    code(r"""
    daily_equity = pd.concat(daily_frames, ignore_index=True).sort_values(["sample", "session_date"])
    daily_equity["equity_usd"] = daily_equity.groupby("sample").daily_return.transform(
        lambda x: STARTING_CAPITAL_USD * (1.0 + x).cumprod()
    )

    fig, axes = plt.subplots(2, 2, figsize=(15, 10))
    sns.barplot(data=metrics, x="sample", y="gross_mean_pips", color="#4C78A8", ax=axes[0, 0], label="gross")
    sns.barplot(data=metrics, x="sample", y="net_mean_pips", color="#E45756", alpha=0.75, ax=axes[0, 0], label="net")
    axes[0, 0].axhline(0, color="black", lw=1)
    axes[0, 0].set_title("Mean gross and net pips per trade")
    axes[0, 0].legend()

    for label, group in daily_equity.groupby("sample"):
        axes[0, 1].plot(group.session_date, group.equity_usd, label=label)
    axes[0, 1].set_title(f"Equity at {RISK_PER_TRADE_PCT:.2f}% risk per trade")
    axes[0, 1].set_ylabel("USD")
    axes[0, 1].legend()

    sns.histplot(data=trades, x="net_r", hue="sample", bins=60, element="step", stat="density",
                 common_norm=False, ax=axes[1, 0])
    axes[1, 0].axvline(0, color="black", lw=1)
    axes[1, 0].set_title("Net R distribution")

    plot_annual = annual.pivot(index="year", columns="sample", values="total_return_pct")
    sns.heatmap(plot_annual.T, annot=True, fmt=".2f", center=0, cmap="RdYlGn", ax=axes[1, 1])
    axes[1, 1].set_title("Annual compounded return (%)")
    plt.tight_layout()
    plt.show()
    """),
    md(r"""
    ## 16. Cost sensitivity

    Because costs change equity and therefore every later position size, each cost
    row reruns the complete stateful backtest. This does not replace measured quote data.
    """),
    code(r"""
    cost_rows = []
    for cost in [0.0, 0.25, 0.5, 1.0, 1.5, 2.0]:
        for label, (start, end) in segments.items():
            scope = bars.loc[(bars.bar_open >= start) & (bars.bar_open < end)].reset_index(drop=True)
            final_raw_i = int(np.searchsorted(raw_time, np.datetime64(end), side="left") - 1)
            stressed = run_one_configuration(scope, selected_config, final_raw_i, round_trip_cost_pips=cost)
            stressed = stressed.loc[stressed.exit_reason.ne("window_end")].copy()
            row = {"sample": label, "round_trip_cost_pips": cost}
            row.update(summarize(stressed, segment_sessions[label]))
            cost_rows.append(row)
    cost_stress = pd.DataFrame(cost_rows)
    display(cost_stress[["sample", "round_trip_cost_pips", "net_mean_pips", "net_mean_r",
                         "total_return_pct", "daily_sharpe_net_return", "max_drawdown_pct"]].round(4))

    plt.figure(figsize=(9, 5))
    sns.lineplot(data=cost_stress, x="round_trip_cost_pips", y="total_return_pct", hue="sample", marker="o")
    plt.axhline(0, color="black", lw=1)
    plt.title("Compounded account return versus round-trip cost")
    plt.ylabel("total return (%)")
    plt.show()
    """),
    md(r"""
    ## 17. Visualize an individual trade

    Change `TRADE_CHART_SAMPLE` and `TRADE_NUMBER` in the control cell. The chart
    shows the completed signal bars, selected baseline and ±Z bands, and frozen
    entry/stop/target/exit levels. The actual exit was resolved on one-minute data,
    so its timestamp need not align with a signal bar.
    """),
    code(r"""
    chart_trades = trades.loc[trades["sample"].eq(TRADE_CHART_SAMPLE)].sort_values("entry_time").reset_index(drop=True)
    if len(chart_trades):
        chosen_number = min(max(int(TRADE_NUMBER), 0), len(chart_trades) - 1)
        trade = chart_trades.iloc[chosen_number]
        signal_bar_open = trade.signal_time - pd.Timedelta(minutes=SIGNAL_BAR_MINUTES)
        center_i = int(np.searchsorted(bars.bar_open.to_numpy(), np.datetime64(signal_bar_open)))
        left, right = max(0, center_i - CHART_BARS_BEFORE), min(len(bars), center_i + CHART_BARS_AFTER + 1)
        chart = bars.iloc[left:right].copy()
        chart["upper"] = chart.selected_baseline + selected_config["arm_z"] * chart.selected_std
        chart["lower"] = chart.selected_baseline - selected_config["arm_z"] * chart.selected_std

        fig, ax = plt.subplots(figsize=(15, 6))
        candle_width_days = (SIGNAL_BAR_MINUTES / (24 * 60)) * 0.65
        for row in chart.itertuples():
            x = mdates.date2num(row.bar_open)
            color = "#2A9D8F" if row.close >= row.open else "#E76F51"
            ax.vlines(x, row.low, row.high, color=color, lw=0.8)
            body_low = min(row.open, row.close)
            body_height = max(abs(row.close - row.open), PIP_SIZE * 0.05)
            ax.add_patch(Rectangle((x - candle_width_days / 2, body_low), candle_width_days, body_height,
                                   facecolor=color, edgecolor=color, alpha=0.65))
        ax.plot(chart.bar_open, chart.selected_baseline, color="#F4A261", lw=1.5, label="baseline")
        ax.plot(chart.bar_open, chart.upper, color="#E76F51", lw=1, ls="--", label="±Z arm band")
        ax.plot(chart.bar_open, chart.lower, color="#2A9D8F", lw=1, ls="--")
        signal_price = bars.loc[bars.bar_open.eq(signal_bar_open), "close"].iloc[0]
        ax.scatter(trade.signal_time, signal_price, marker="o", s=80,
                   color="purple", label="signal known")
        ax.scatter(trade.entry_time, trade.entry_price, marker="^" if trade.side == "long" else "v", s=120,
                   color="blue", label=f"{trade.side} entry")
        ax.scatter(trade.exit_time, trade.exit_price, marker="X", s=110, color="black", label=f"exit: {trade.exit_reason}")
        ax.hlines(trade.stop_price, trade.entry_time, trade.exit_time, color="red", lw=1.5, label="frozen stop")
        ax.hlines(trade.target_price, trade.entry_time, trade.exit_time, color="green", lw=1.5, label="frozen target")
        ax.set_title(f"{PAIR} {TRADE_CHART_SAMPLE} trade {chosen_number}: {trade.side}, {trade.net_pips:.2f} net pips")
        ax.set_ylabel("price")
        ax.xaxis_date()
        ax.legend(ncol=4, fontsize=9)
        plt.tight_layout()
        plt.show()
        display(trade.to_frame("value"))
    else:
        print(f"No trades in sample {TRADE_CHART_SAMPLE!r}")
    """),
    md(r"""
    ## 18. Research checklist before opening holdout

    Before changing `OPEN_HOLDOUT`:

    - Freeze the pair, dates, strategy parameters, selection metric, grid, costs, and kill test.
    - Save the training and OOS tables you used to decide.
    - Stop if OOS fails; do not use holdout to rescue it.
    - If OOS survives, type `FINAL CONFIGURATION IS FROZEN` and run exactly once.
    - After reading holdout, do not retune. Only future observations are clean new evidence.

    Important project-history note: an earlier notebook in this folder already
    inspected the 2024–2026 data during a misunderstood workflow. This notebook
    now enforces the intended lock, but those dates cannot scientifically become
    untouched again. Treat a later opening here as a workflow demonstration or
    descriptive test; a genuinely clean holdout must be future data.
    """),
]

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT}")
