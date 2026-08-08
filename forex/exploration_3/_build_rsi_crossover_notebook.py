"""Build the editable, holdout-guarded RSI crossover workbench."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "single_pair_rsi_crossover_workbench.ipynb"
TEMPLATE = ROOT / "single_pair_zband_workbench.ipynb"


def md(text: str) -> dict:
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("m" + source).encode()).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(text: str) -> dict:
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "code",
        "id": hashlib.sha1(("c" + source).encode()).hexdigest()[:12],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


template = json.loads(TEMPLATE.read_text(encoding="utf-8"))


def template_code(index: int) -> dict:
    source = "".join(template["cells"][index]["source"])
    return code(source)


cells = [
    md(r"""
    # Single-pair RSI arm-and-reset crossover workbench

    This notebook performs data loading, RSI/ATR construction, optional
    train-only parameter tuning, causal execution, complete metrics, cost stress,
    export, and trade visualisation in readable sequential sections.

    RSI is scaled from 0 to 1. The default short sequence is:

    1. A completed signal bar crosses above `SHORT_ARM_THRESHOLD=0.70`.
    2. A later completed bar crosses back to or below `SHORT_ENTRY_THRESHOLD=0.65`.
    3. A short enters at the next complete signal bar's open.

    Longs mirror the logic: cross below 0.30 to arm, then cross back to or above
    0.35 to enter. Stops are frozen at `ATR × stop multiplier`; take profit is
    expressed in R, where 1R is the entry-to-stop distance. Underlying one-minute
    bars resolve the bracket, including the fill minute, adverse dual touches,
    and gap-through exits.
    """),
    md(r"""
    ## 1. Imports and project location

    Strategy calculations are visible in this notebook. No hidden strategy or
    backtest module is imported.
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

    SMOKE_MODE = os.getenv("RSI_CROSSOVER_NOTEBOOK_SMOKE", "0") == "1"
    print("Project:", PROJECT_ROOT)
    print("Data:", DATA_DIR)
    """),
    md(r"""
    ## 2. Controls — edit this cell first

    Dates are half-open. Only training is used to rank candidates. Calendar 2020
    remains an embargo; 2021–2023 is OOS. With the default lock, 2024+ data is
    excluded by the parquet read itself.

    `TAKE_PROFIT_R=1.5` means the profit target is 1.5 times the ATR-defined stop
    distance. Set `RUN_GRID_SEARCH=False` to run exactly the manual parameters.
    """),
    code(r"""
    # ------------------------------- market ---------------------------------
    PAIR = "EURUSD"               # AUDUSD, EURUSD, GBPUSD, NZDUSD
    SIGNAL_BAR_MINUTES = 15
    PRICE_SOURCE = "close"        # close, hlc3, or ohlc4
    SESSION_TIMEZONE = "America/New_York"
    SESSION_START_HOUR = 17

    # -------------------------- development windows -------------------------
    TRAIN_START = "2012-01-01"
    TRAIN_END = "2020-01-01"
    OOS_START = "2021-01-01"
    OOS_END = "2024-01-01"
    WARMUP_DAYS = 30

    # ----------------------------- holdout lock ------------------------------
    HOLDOUT_START = "2024-01-01"
    HOLDOUT_END = None
    OPEN_HOLDOUT = False
    HOLDOUT_CONFIRMATION = ""      # required: FINAL CONFIGURATION IS FROZEN

    # ------------------------- manually chosen strategy ---------------------
    MANUAL_RSI_LENGTH = 14
    MANUAL_SHORT_ARM_THRESHOLD = 0.70
    MANUAL_SHORT_ENTRY_THRESHOLD = 0.65
    MANUAL_LONG_ARM_THRESHOLD = 0.30
    MANUAL_LONG_ENTRY_THRESHOLD = 0.35
    MANUAL_MAX_ARM_BARS = 30
    MANUAL_ATR_LENGTH = 14
    MANUAL_ATR_STOP_MULT = 2.0
    MANUAL_TAKE_PROFIT_R = 1.5

    # -------------------- optional train-only parameter search ---------------
    RUN_GRID_SEARCH = False
    GRID_RSI_LENGTHS = [7, 14, 21]
    GRID_UPPER_ARM_THRESHOLDS = [0.70, 0.75, 0.80]
    GRID_RESET_GAPS = [0.05, 0.10]
    GRID_MAX_ARM_BARS = [10, 30]
    GRID_ATR_LENGTHS = [14]
    GRID_ATR_STOP_MULT = [1.0, 2.0, 3.0]
    GRID_TAKE_PROFIT_R = [1.0, 1.5, 2.0]
    SELECTION_METRIC = "daily_sharpe_net_return"
    MIN_TRAIN_TRADES = 100
    MAX_CONFIGS = 400

    # ---------------------- risk sizing and account view ---------------------
    ROUND_TRIP_COST_PIPS = 1.0
    STARTING_CAPITAL_USD = 100_000
    RISK_PER_TRADE_PCT = 1.0
    MAX_LEVERAGE = None

    # ------------------------- export and visualisation ----------------------
    EXPORT_TRADES = False
    EXPORT_PATH = PROJECT_ROOT / "artifacts" / "manual_rsi_crossover_trades.parquet"
    ALLOW_EXPORT_OVERWRITE = False
    TRADE_CHART_SAMPLE = "oos"
    TRADE_NUMBER = 0
    CHART_BARS_BEFORE = 30
    CHART_BARS_AFTER = 60

    if SMOKE_MODE:
        TRAIN_START, TRAIN_END = "2018-01-01", "2019-01-01"
        OOS_START, OOS_END = "2021-01-01", "2021-07-01"
        RUN_GRID_SEARCH = False
        EXPORT_TRADES = False

    SUPPORTED_PAIRS = {"AUDUSD", "EURUSD", "GBPUSD", "NZDUSD"}
    assert PAIR in SUPPORTED_PAIRS
    assert PRICE_SOURCE in {"close", "hlc3", "ohlc4"}
    assert 0 < MANUAL_LONG_ARM_THRESHOLD < MANUAL_LONG_ENTRY_THRESHOLD < 0.5
    assert 0.5 < MANUAL_SHORT_ENTRY_THRESHOLD < MANUAL_SHORT_ARM_THRESHOLD < 1
    assert 0 < RISK_PER_TRADE_PCT <= 100
    assert MANUAL_ATR_STOP_MULT > 0 and MANUAL_TAKE_PROFIT_R > 0
    assert pd.Timestamp(TRAIN_START) < pd.Timestamp(TRAIN_END) <= pd.Timestamp(OOS_START)
    assert pd.Timestamp(OOS_START) < pd.Timestamp(OOS_END) <= pd.Timestamp(HOLDOUT_START)
    if OPEN_HOLDOUT:
        assert HOLDOUT_CONFIRMATION == "FINAL CONFIGURATION IS FROZEN", "Holdout confirmation phrase is missing"

    print(f"Pair={PAIR}; train={TRAIN_START} to {TRAIN_END}; OOS={OOS_START} to {OOS_END}")
    print("Holdout access:", "OPEN" if OPEN_HOLDOUT else "LOCKED — no 2024+ rows will load")
    """),
    md(r"""
    ## 3. Build the candidate list

    The manual configuration is always included. The optional grid uses
    symmetric thresholds: an upper arm of 0.75 with a 0.05 reset gap implies a
    short entry at 0.70, long arm at 0.25, and long entry at 0.30.
    """),
    code(r"""
    def config_name(cfg):
        return (
            f"rsi{cfg['rsi_length']}|SA{cfg['short_arm']:.2f}|SE{cfg['short_entry']:.2f}|"
            f"LA{cfg['long_arm']:.2f}|LE{cfg['long_entry']:.2f}|arm{cfg['max_arm_bars']}|"
            f"atr{cfg['atr_length']}x{cfg['atr_stop_mult']:.1f}|R{cfg['take_profit_r']:.1f}"
        )


    manual_config = {
        "rsi_length": int(MANUAL_RSI_LENGTH),
        "short_arm": float(MANUAL_SHORT_ARM_THRESHOLD),
        "short_entry": float(MANUAL_SHORT_ENTRY_THRESHOLD),
        "long_arm": float(MANUAL_LONG_ARM_THRESHOLD),
        "long_entry": float(MANUAL_LONG_ENTRY_THRESHOLD),
        "max_arm_bars": int(MANUAL_MAX_ARM_BARS),
        "atr_length": int(MANUAL_ATR_LENGTH),
        "atr_stop_mult": float(MANUAL_ATR_STOP_MULT),
        "take_profit_r": float(MANUAL_TAKE_PROFIT_R),
    }
    manual_config["name"] = config_name(manual_config)

    candidates = [manual_config]
    if RUN_GRID_SEARCH:
        for rsi_length, upper_arm, reset_gap, arm_bars, atr_length, atr_mult, take_profit_r in product(
            GRID_RSI_LENGTHS, GRID_UPPER_ARM_THRESHOLDS, GRID_RESET_GAPS,
            GRID_MAX_ARM_BARS, GRID_ATR_LENGTHS, GRID_ATR_STOP_MULT, GRID_TAKE_PROFIT_R,
        ):
            short_entry = upper_arm - reset_gap
            cfg = {
                "rsi_length": int(rsi_length),
                "short_arm": float(upper_arm),
                "short_entry": float(short_entry),
                "long_arm": float(1 - upper_arm),
                "long_entry": float(1 - short_entry),
                "max_arm_bars": int(arm_bars),
                "atr_length": int(atr_length),
                "atr_stop_mult": float(atr_mult),
                "take_profit_r": float(take_profit_r),
            }
            if not (0 < cfg["long_arm"] < cfg["long_entry"] < 0.5 < cfg["short_entry"] < cfg["short_arm"] < 1):
                continue
            cfg["name"] = config_name(cfg)
            candidates.append(cfg)

    keys = ["rsi_length", "short_arm", "short_entry", "long_arm", "long_entry", "max_arm_bars", "atr_length", "atr_stop_mult", "take_profit_r"]
    unique = {}
    for cfg in candidates:
        unique.setdefault(tuple(cfg[k] for k in keys), cfg)
    candidates = list(unique.values())
    assert len(candidates) <= MAX_CONFIGS, f"Grid has {len(candidates)} configs; raise MAX_CONFIGS deliberately"

    display(pd.DataFrame(candidates))
    print(f"{len(candidates)} unique configuration(s)")
    """),
    md(r"""
    ## 4. Load only permitted one-minute rows

    Parquet predicates apply before pandas receives data. Warm-up rows precede
    training but are never scored. With the lock closed, 2024+ cannot enter memory.
    """),
    template_code(8),
    md(r"""
    ## 5. Core one-minute data-quality checks

    Missing minutes, closures, duplicates, ordering, and invalid OHLC are reported
    before feature construction.
    """),
    template_code(10),
    md(r"""
    ## 6. Aggregate complete signal bars

    RSI decisions use completed signal bars. Entries use the next complete bar's
    first observed minute; exits replay every available one-minute row.
    """),
    template_code(12),
    md(r"""
    ## 7. Calculate Wilder RSI and Wilder ATR

    Both recursions are seeded with their length-bar simple average rather than
    silently using pandas' first-observation EWM seed. RSI is stored on a 0–1
    scale. Under-populated windows remain missing.
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

    price_delta = bars.source_price.diff().to_numpy(float)
    gains = np.maximum(price_delta, 0)
    losses = np.maximum(-price_delta, 0)
    needed_rsi_lengths = sorted({MANUAL_RSI_LENGTH, *GRID_RSI_LENGTHS})
    for length in needed_rsi_lengths:
        average_gain = np.full(len(bars), np.nan)
        average_loss = np.full(len(bars), np.nan)
        if len(bars) > length:
            average_gain[length] = np.nanmean(gains[1:length + 1])
            average_loss[length] = np.nanmean(losses[1:length + 1])
            for i in range(length + 1, len(bars)):
                average_gain[i] = average_gain[i - 1] + (gains[i] - average_gain[i - 1]) / length
                average_loss[i] = average_loss[i - 1] + (losses[i] - average_loss[i - 1]) / length
        denominator = average_gain + average_loss
        rsi = np.divide(average_gain, denominator, out=np.full(len(bars), np.nan), where=denominator > 0)
        rsi[(denominator == 0) & np.isfinite(denominator)] = 0.5
        bars[f"rsi_{length}"] = rsi

    previous_close = bars.close.shift(1)
    true_range = pd.concat([
        bars.high - bars.low,
        (bars.high - previous_close).abs(),
        (bars.low - previous_close).abs(),
    ], axis=1).max(axis=1).to_numpy(dtype=float, copy=True)
    true_range[0] = bars.high.iloc[0] - bars.low.iloc[0]
    needed_atr_lengths = sorted({MANUAL_ATR_LENGTH, *GRID_ATR_LENGTHS})
    for length in needed_atr_lengths:
        atr = np.full(len(bars), np.nan)
        if len(bars) >= length:
            atr[length - 1] = true_range[:length].mean()
            for i in range(length, len(bars)):
                atr[i] = atr[i - 1] + (true_range[i] - atr[i - 1]) / length
        bars[f"atr_{length}"] = atr

    display(bars[["bar_open", "open", "high", "low", "close", "session_id", f"rsi_{MANUAL_RSI_LENGTH}", f"atr_{MANUAL_ATR_LENGTH}"]].head(25))
    """),
    md(r"""
    ## 8. Frozen-bracket exit replay

    The fill minute is included. Gap-through exits receive the first observed
    minute open. If stop and target touch inside one minute and order is unknown,
    the stop wins.
    """),
    template_code(17),
    md(r"""
    ## 9. RSI arm/reset state machine and position sizing

    The current completed bar can only create a signal. Entry occurs at the next
    complete bar's open. While a position is active, no new arm is retained.
    Position units risk the chosen percentage of current equity to the ATR stop.
    """),
    code(r"""
    PIP_SIZE = 0.0001

    def run_one_configuration(scope, config, final_raw_i, round_trip_cost_pips=ROUND_TRIP_COST_PIPS):
        rsi = scope[f"rsi_{config['rsi_length']}"] .to_numpy(float)
        atr = scope[f"atr_{config['atr_length']}"] .to_numpy(float)
        start_i = scope.raw_start_i.to_numpy(np.int64)
        end_i = scope.raw_end_i.to_numpy(np.int64)
        bar_time = scope.bar_open.to_numpy()
        session = scope.session_id.to_numpy()

        armed_side = 0
        armed_bar = -1
        armed_rsi = np.nan
        active_exit_i = -1
        equity = float(STARTING_CAPITAL_USD)
        records = []

        for i in range(1, len(scope) - 1):
            if active_exit_i > end_i[i]:
                armed_side = 0
                continue
            if not (np.isfinite(rsi[i - 1]) and np.isfinite(rsi[i])):
                continue

            if armed_side and i - armed_bar > config["max_arm_bars"]:
                armed_side = 0

            crossed_short_arm = rsi[i - 1] <= config["short_arm"] and rsi[i] > config["short_arm"]
            crossed_long_arm = rsi[i - 1] >= config["long_arm"] and rsi[i] < config["long_arm"]
            if armed_side == 0 and crossed_short_arm:
                armed_side, armed_bar, armed_rsi = -1, i, rsi[i]
            elif armed_side == 0 and crossed_long_arm:
                armed_side, armed_bar, armed_rsi = 1, i, rsi[i]

            crossed_short_entry = rsi[i - 1] > config["short_entry"] and rsi[i] <= config["short_entry"]
            crossed_long_entry = rsi[i - 1] < config["long_entry"] and rsi[i] >= config["long_entry"]
            side = -1 if armed_side == -1 and crossed_short_entry else 0
            if side == 0 and armed_side == 1 and crossed_long_entry:
                side = 1
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
            target = entry_price + side * risk_price * config["take_profit_r"]
            exit_i, exit_price, reason, ambiguous, gap_exit = replay_frozen_bracket(entry_i, final_raw_i, side, stop, target)

            gross_pips = side * (exit_price - entry_price) / PIP_SIZE
            risk_pips = risk_price / PIP_SIZE
            gross_usd = position_units * side * (exit_price - entry_price)
            cost_usd = position_units * PIP_SIZE * round_trip_cost_pips
            net_usd = gross_usd - cost_usd
            equity = equity_before + net_usd
            records.append({
                "config": config["name"],
                "arm_time": pd.Timestamp(bar_time[armed_bar]) + pd.Timedelta(minutes=SIGNAL_BAR_MINUTES),
                "signal_time": pd.Timestamp(bar_time[i]) + pd.Timedelta(minutes=SIGNAL_BAR_MINUTES),
                "entry_time": pd.Timestamp(raw_time[entry_i]), "exit_time": pd.Timestamp(raw_time[exit_i]),
                "entry_session": session[i], "side": "long" if side == 1 else "short",
                "arm_rsi": armed_rsi, "signal_rsi": rsi[i], "armed_bars": i - armed_bar,
                "entry_price": entry_price, "exit_price": exit_price, "stop_price": stop, "target_price": target,
                "risk_pips": risk_pips, "position_units": position_units, "notional_usd": notional_usd,
                "leverage": notional_usd / equity_before, "intended_risk_usd": intended_risk_usd,
                "actual_risk_usd": actual_risk_usd, "actual_risk_pct": 100 * actual_risk_usd / equity_before,
                "gross_pips": gross_pips, "cost_pips": round_trip_cost_pips, "net_pips": gross_pips - round_trip_cost_pips,
                "gross_usd": gross_usd, "cost_usd": cost_usd, "net_usd": net_usd,
                "equity_before_usd": equity_before, "equity_after_usd": equity,
                "net_return_on_equity": net_usd / equity_before,
                "gross_r": gross_usd / actual_risk_usd, "net_r": net_usd / actual_risk_usd,
                "exit_reason": reason, "ambiguous_1m": ambiguous, "gap_exit": gap_exit,
            })
            active_exit_i = exit_i
            armed_side = 0
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

    Metrics include gross/net pips, R, costs, clustered inference, compounded
    percentage-equity returns, daily Sharpe, drawdown, leverage, and exit quality.
    """),
    template_code(21),
    md(r"""
    ## 11. Tune on training only

    Every candidate ends at `TRAIN_END`. OOS is not passed through the candidates.
    The selected configuration is then frozen for the next section.
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

    display(tuning[["name", "rsi_length", "short_arm", "short_entry", "long_arm", "long_entry",
                    "atr_stop_mult", "take_profit_r", "trades", "gross_mean_pips", "net_mean_pips",
                    "net_mean_r", "net_r_cluster_t", "total_return_pct", "daily_sharpe_net_return",
                    "max_drawdown_pct", "selected"]].round(4))
    print("Selected from training only:", selected_config)
    """),
    md(r"""
    ## 12. Freeze selection and run train/OOS separately

    State, positions, and equity restart for each segment. This prevents the 2020
    gap or a position near a boundary from leaking into the next evaluation.
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
    ## 13. Feature coverage and threshold-event rate by hour

    This reports RSI/ATR under-population and how often the selected thresholds
    arm or reset by UTC hour. A strong clock gradient is a confound to investigate,
    not a reason to optimize a session filter after reading P&L.
    """),
    code(r"""
    bars["selected_rsi"] = bars[f"rsi_{selected_config['rsi_length']}"]
    bars["selected_atr"] = bars[f"atr_{selected_config['atr_length']}"]
    bars["decision_ready"] = bars.selected_rsi.notna() & bars.selected_atr.gt(0)
    previous_rsi = bars.selected_rsi.shift(1)
    bars["short_arm_cross"] = previous_rsi.le(selected_config["short_arm"]) & bars.selected_rsi.gt(selected_config["short_arm"])
    bars["long_arm_cross"] = previous_rsi.ge(selected_config["long_arm"]) & bars.selected_rsi.lt(selected_config["long_arm"])
    bars["short_reset_cross"] = previous_rsi.gt(selected_config["short_entry"]) & bars.selected_rsi.le(selected_config["short_entry"])
    bars["long_reset_cross"] = previous_rsi.lt(selected_config["long_entry"]) & bars.selected_rsi.ge(selected_config["long_entry"])

    coverage_rows = []
    for label, (start, end) in segments.items():
        view = bars.loc[(bars.bar_open >= start) & (bars.bar_open < end)].copy()
        view["utc_hour"] = view.bar_open.dt.hour
        report = view.groupby("utc_hour").agg(
            signal_bars=("decision_ready", "size"),
            decision_ready=("decision_ready", "sum"),
            short_arms=("short_arm_cross", "sum"), long_arms=("long_arm_cross", "sum"),
            short_resets=("short_reset_cross", "sum"), long_resets=("long_reset_cross", "sum"),
        ).reset_index()
        report.insert(0, "sample", label)
        report["underpopulated_rows"] = report.signal_bars - report.decision_ready
        report["decision_ready_share"] = report.decision_ready / report.signal_bars
        for event in ["short_arms", "long_arms", "short_resets", "long_resets"]:
            report[f"{event}_per_1000_bars"] = 1000 * report[event] / report.signal_bars
        coverage_rows.append(report)
    feature_coverage = pd.concat(coverage_rows, ignore_index=True)
    display(feature_coverage)
    """),
    md(r"""
    ## 14. Complete metrics and annual breakdown

    Gross, modeled cost, and net results are all retained. Percentage-equity risk
    means position size falls automatically when the ATR stop widens.
    """),
    template_code(39),
    md(r"""
    ## 15. Performance visualisations
    """),
    template_code(41),
    md(r"""
    ## 16. Cost sensitivity

    This reruns the complete stateful strategy at each cost rather than subtracting
    a cost from an already-filtered summary.
    """),
    template_code(43),
    md(r"""
    ## 17. Visualise one trade and its RSI sequence

    The upper panel shows price and the frozen bracket. The lower panel shows the
    RSI arming and reset thresholds, arm event, and entry signal.
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

        fig, (price_ax, rsi_ax) = plt.subplots(2, 1, figsize=(15, 9), sharex=True, gridspec_kw={"height_ratios": [2, 1]})
        candle_width_days = (SIGNAL_BAR_MINUTES / (24 * 60)) * 0.65
        for row in chart.itertuples():
            x = mdates.date2num(row.bar_open)
            color = "#2A9D8F" if row.close >= row.open else "#E76F51"
            price_ax.vlines(x, row.low, row.high, color=color, lw=0.8)
            body_low = min(row.open, row.close)
            body_height = max(abs(row.close - row.open), PIP_SIZE * 0.05)
            price_ax.add_patch(Rectangle((x - candle_width_days / 2, body_low), candle_width_days, body_height,
                                         facecolor=color, edgecolor=color, alpha=0.65))
        price_ax.scatter(trade.entry_time, trade.entry_price, marker="^" if trade.side == "long" else "v", s=120, color="blue", label=f"{trade.side} entry")
        price_ax.scatter(trade.exit_time, trade.exit_price, marker="X", s=110, color="black", label=f"exit: {trade.exit_reason}")
        price_ax.hlines(trade.stop_price, trade.entry_time, trade.exit_time, color="red", lw=1.5, label="frozen stop")
        price_ax.hlines(trade.target_price, trade.entry_time, trade.exit_time, color="green", lw=1.5, label="frozen target")
        price_ax.set_title(f"{PAIR} {TRADE_CHART_SAMPLE} trade {chosen_number}: {trade.side}, {trade.net_pips:.2f} net pips")
        price_ax.set_ylabel("price")
        price_ax.legend(ncol=4, fontsize=9)

        rsi_ax.plot(chart.bar_open, chart.selected_rsi, color="#4C78A8", label=f"RSI({selected_config['rsi_length']})")
        for level, color, label in [
            (selected_config["short_arm"], "#B22222", "short arm"),
            (selected_config["short_entry"], "#E76F51", "short reset"),
            (selected_config["long_entry"], "#2A9D8F", "long reset"),
            (selected_config["long_arm"], "#006400", "long arm"),
        ]:
            rsi_ax.axhline(level, color=color, ls="--", lw=1, label=label)
        arm_bar_open = trade.arm_time - pd.Timedelta(minutes=SIGNAL_BAR_MINUTES)
        rsi_ax.scatter(arm_bar_open, trade.arm_rsi, marker="o", s=80, color="purple", zorder=5, label="armed")
        rsi_ax.scatter(signal_bar_open, trade.signal_rsi, marker="D", s=75, color="black", zorder=5, label="entry signal")
        rsi_ax.set_ylim(0, 1)
        rsi_ax.set_ylabel("RSI (0–1)")
        rsi_ax.legend(ncol=3, fontsize=8)
        rsi_ax.xaxis_date()
        plt.tight_layout()
        plt.show()
        display(trade.to_frame("value"))
    else:
        print(f"No trades in sample {TRADE_CHART_SAMPLE!r}")
    """),
    md(r"""
    ## 18. Export the exact frozen trades

    Enable `EXPORT_TRADES` only after the selected configuration is frozen. The
    output contains both train and OOS labels plus pair/config metadata, ready for
    `trade_regime_tester.ipynb`. Existing files are protected by default.
    """),
    code(r"""
    if EXPORT_TRADES:
        export_frame = trades.copy()
        export_frame.insert(0, "pair", PAIR)
        if export_frame.signal_time.ge(pd.Timestamp(HOLDOUT_START)).any() and not OPEN_HOLDOUT:
            raise AssertionError("Sealed holdout row entered export")
        if EXPORT_PATH.exists() and not ALLOW_EXPORT_OVERWRITE:
            raise FileExistsError(f"Refusing to overwrite {EXPORT_PATH}")
        EXPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
        export_frame.to_parquet(EXPORT_PATH, index=False)
        print("Wrote", EXPORT_PATH, "with", len(export_frame), "trades")
    else:
        print("EXPORT_TRADES=False — no file written")
    """),
    md(r"""
    ## 19. Research checklist before opening holdout

    - Freeze pair, dates, RSI thresholds, reset thresholds, ATR/target parameters,
      costs, selection metric, and kill test.
    - Inspect threshold-event rates by hour and neighbouring thresholds.
    - Stop if OOS fails; do not use holdout to rescue it.
    - If OOS survives, type `FINAL CONFIGURATION IS FROZEN` and run once.
    - Historical 2024–2026 data in this project was already inspected elsewhere;
      it is descriptive, not a scientifically fresh holdout. Only future data is clean.
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

OUT.write_text(json.dumps(notebook, indent=1), encoding="utf-8")
print(f"Wrote {OUT} with {len(cells)} cells")
