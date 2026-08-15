"""Build the editable triangular-pricing research notebook."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "triangular_arbitrage_workbench.ipynb"


def md(source: str):
    text = dedent(source).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("m" + text).encode()).hexdigest()[:12],
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(source: str):
    text = dedent(source).strip() + "\n"
    return {
        "cell_type": "code",
        "execution_count": None,
        "id": hashlib.sha1(("c" + text).encode()).hexdigest()[:12],
        "metadata": {},
        "outputs": [],
        "source": text.splitlines(keepends=True),
    }


cells = [
    md(r"""
    # AUD triangular-pricing workbench

    This notebook studies the relationship

    $$\mathrm{AUDUSD}_{synthetic}=\frac{\mathrm{AUDJPY}}{\mathrm{USDJPY}}$$

    and the observed spread

    $$s_t=\mathrm{AUDUSD}_t-\frac{\mathrm{AUDJPY}_t}{\mathrm{USDJPY}_t}.$$

    You can choose the bar timeframe, rolling Z-score lookback, and entry
    threshold in the first code cell. A positive extreme produces a short signal;
    a negative extreme produces a long signal.

    **Important distinction.** These local files contain midpoint OHLC bars from
    separate archives, not simultaneous executable bid/ask quotes. They can test a
    relative-value mean-reversion hypothesis, but they cannot prove executable
    triangular arbitrage. The notebook therefore reports both (1) the requested
    AUDUSD-only trade and (2) a three-leg residual basket. Neither should be called
    risk-free arbitrage without synchronized quotes, latency, and all-leg fills.
    """),
    md(r"""
    ## 1. Choose the timeframe and Z-score parameters

    `TIMEFRAME_MINUTES` accepts 1, 5, 15, 30, or 60. The lookback is measured in
    bars, so change it when changing timeframe if you want to preserve the same
    amount of clock time. For example, one 24-hour market day is 1,440 one-minute
    bars, 288 five-minute bars, or 96 fifteen-minute bars.

    The default window is development data only. Dates from 2024 onward remain
    locked unless you explicitly opt in after freezing the method.
    """),
    code(r"""
    import pandas as pd

    # ------------------------- USER PARAMETERS -------------------------
    START = "2015-01-01"
    END = "2020-01-01"             # half-open: END itself is excluded
    OPEN_LOCKED_PERIOD = False      # required for any END later than 2024-01-01

    TIMEFRAME_MINUTES = 5           # choose: 1, 5, 15, 30, or 60
    ZSCORE_LOOKBACK_BARS = 288      # history used for mean/std
    ENTRY_Z = 2.0                   # choose your entry threshold
    BASIS_MODE = "log"              # "log" (scale-stable) or "raw" (actual-synthetic)
    SIGNAL_MODE = "cross"           # "cross" = first threshold crossing; "state" = every extreme bar

    HORIZON_BARS = [1, 3, 12]       # fixed holding periods to test
    ROUND_TRIP_COST_BPS_PER_LEG = 0.5
    NON_OVERLAPPING = True
    # -------------------------------------------------------------------

    if TIMEFRAME_MINUTES not in {1, 5, 15, 30, 60}:
        raise ValueError("Choose TIMEFRAME_MINUTES from 1, 5, 15, 30, 60")
    if ENTRY_Z <= 0:
        raise ValueError("ENTRY_Z must be positive")
    if pd.Timestamp(END) > pd.Timestamp("2024-01-01") and not OPEN_LOCKED_PERIOD:
        raise ValueError("2024+ is locked. Freeze the method, then set OPEN_LOCKED_PERIOD=True explicitly.")

    print(f"Timeframe: {TIMEFRAME_MINUTES} minutes")
    print(f"Z-score: {ZSCORE_LOOKBACK_BARS} bars, entry at +/-{ENTRY_Z:.2f}")
    print(f"Approximate lookback: {ZSCORE_LOOKBACK_BARS * TIMEFRAME_MINUTES / 60:.1f} market hours")
    """),
    md(r"""
    ## 2. Setup

    Signals use a completed bar. Location and scale use only earlier bars. The
    baseline enters at the following bar's open. Because these midpoint archives
    commonly have `next open == previous close`, a two-bar entry is also run later
    as a boundary-noise control.
    """),
    code(r"""
    from pathlib import Path
    import sys

    import numpy as np
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display

    sns.set_theme(style="whitegrid", context="notebook")
    pd.set_option("display.max_columns", 100)
    pd.set_option("display.width", 220)

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == "exploration_8" else here / "forex" / "exploration_8"
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError("Run from the workspace root or forex/exploration_8")
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))

    from data_loader import load_triangle_data
    from strategy.triangle import build_triangle_features
    from backtest_engine.engine import build_event_returns, summarize_events

    print("Project:", PROJECT_ROOT)
    """),
    md(r"""
    ## 3. Load, align, and audit the three archives

    All timestamps are normalized to UTC. Bars are constructed from one-minute
    data and retained only when every constituent minute exists. The final panel
    is an exact inner join; there is no forward fill. AUDUSD supplies the canonical
    session calendar, which removes closed-market padding in another archive.
    """),
    code(r"""
    triangle = load_triangle_data(PROJECT_ROOT, START, END, TIMEFRAME_MINUTES)
    panel = triangle.panel

    display(triangle.raw_quality)
    display(triangle.alignment.to_frame())
    display(
        triangle.bar_coverage
        .groupby("pair", observed=True)
        .agg(observed_intervals=("observed_intervals", "sum"),
             complete_bars=("complete_bars", "sum"),
             raw_minutes=("raw_minutes", "sum"))
        .assign(complete_share=lambda x: x.complete_bars / x.observed_intervals)
        .round(5)
    )

    assert triangle.raw_quality[["duplicate_ts", "out_of_order", "invalid_ohlc"]].to_numpy().sum() == 0
    assert panel.index.is_monotonic_increasing and panel.index.is_unique
    print(f"Aligned panel: {len(panel):,} complete {TIMEFRAME_MINUTES}-minute bars")
    """),
    md(r"""
    The next table makes incomplete-window filtering visible by year and UTC hour.
    Inspect unexpectedly low cells before interpreting a time-of-day pattern.
    """),
    code(r"""
    hourly_coverage = (
        triangle.bar_coverage
        .assign(complete_share=lambda x: x.complete_bars / x.observed_intervals)
        .pivot_table(index=["pair", "year"], columns="utc_hour", values="complete_share")
    )
    display(hourly_coverage.round(4))
    """),
    md(r"""
    ## 4. Build the synthetic price and causal Z-score

    `spread_pips` follows the requested arithmetic spread. The default normalizer
    uses the log basis

    $$e_t=\log(AUDUSD_t)-\log(AUDJPY_t)+\log(USDJPY_t),$$

    which is approximately the percentage pricing error and is more comparable
    through time. Set `BASIS_MODE="raw"` to Z-score the arithmetic spread instead.
    The rolling mean and standard deviation are shifted one bar.
    """),
    code(r"""
    features = build_triangle_features(
        panel,
        zscore_lookback_bars=ZSCORE_LOOKBACK_BARS,
        entry_z=ENTRY_Z,
        basis_mode=BASIS_MODE,
        signal_mode=SIGNAL_MODE,
    )
    underpopulated = features["zscore"].isna().sum()
    print(f"Under-populated/undefined Z-score rows: {underpopulated:,} / {len(features):,}")
    display(features[["actual_audusd", "synthetic_audusd", "spread_pips", "zscore", "direction"]].dropna().head())
    """),
    code(r"""
    plot_tail = features.dropna().tail(min(10_000, features["zscore"].notna().sum()))
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(plot_tail.index, plot_tail.actual_audusd, label="Actual AUDUSD", lw=1)
    axes[0].plot(plot_tail.index, plot_tail.synthetic_audusd, label="AUDJPY / USDJPY", lw=1, alpha=0.8)
    axes[0].set_ylabel("USD per AUD")
    axes[0].legend()
    axes[0].set_title("Actual versus synthetic AUDUSD (latest plotted window)")

    axes[1].plot(plot_tail.index, plot_tail.zscore, color="tab:purple", lw=0.8)
    axes[1].axhline(ENTRY_Z, color="tab:red", ls="--")
    axes[1].axhline(-ENTRY_Z, color="tab:green", ls="--")
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set_ylabel("Causal Z-score")
    plt.tight_layout()
    plt.show()
    """),
    md(r"""
    ## 5. Signal coverage and clock diagnostics

    A fixed Z threshold can become an unintended time-of-day selector if basis
    volatility changes by hour. The signal rate is therefore shown for every UTC
    hour before any P&L is read.
    """),
    code(r"""
    ready = features["zscore"].notna()
    signal = features["direction"].ne(0)
    fire = pd.DataFrame({"ready": ready, "signal": signal}, index=features.index)
    fire["utc_hour"] = fire.index.hour
    fire_rate = fire.groupby("utc_hour").agg(opportunities=("ready", "sum"), signals=("signal", "sum"))
    fire_rate["signal_rate"] = fire_rate.signals / fire_rate.opportunities
    display(fire_rate)
    print(f"Total signals before non-overlap: {signal.sum():,}")
    print(f"Hourly signal-rate CV: {fire_rate.signal_rate.std() / fire_rate.signal_rate.mean():.3f}")
    """),
    md(r"""
    ## 6. Fixed-horizon test

    The AUDUSD-only arm implements the requested long/short rule. The residual arm
    uses the matching three-leg log-return basket:

    $$r_{residual}=r_{AUDUSD}-r_{AUDJPY}+r_{USDJPY}.$$

    The basket direction is reversed when the Z-score is positive. This is a
    relative-value diagnostic, not executable arbitrage. Costs are an editable
    sensitivity in round-trip basis points per leg; three times the per-leg cost is
    charged to the basket.
    """),
    code(r"""
    event_sets = []
    summaries = []
    for horizon in HORIZON_BARS:
        events = build_event_returns(
            panel, features,
            horizon_bars=horizon,
            timeframe_minutes=TIMEFRAME_MINUTES,
            entry_delay_bars=1,
            round_trip_cost_bps_per_leg=ROUND_TRIP_COST_BPS_PER_LEG,
            non_overlapping=NON_OVERLAPPING,
        )
        events["horizon_minutes"] = horizon * TIMEFRAME_MINUTES
        event_sets.append(events)
        summary = summarize_events(events)
        summary["horizon_bars"] = horizon
        summary["horizon_minutes"] = horizon * TIMEFRAME_MINUTES
        summaries.append(summary)

    all_events = pd.concat(event_sets, ignore_index=True) if event_sets else pd.DataFrame()
    results = pd.concat(summaries, ignore_index=True) if summaries else pd.DataFrame()
    display(results[["horizon_minutes", "model", "trades", "mean_bps", "median_bps", "hit_rate", "day_cluster_t", "daily_sharpe"]].round(4))
    """),
    code(r"""
    if not results.empty:
        chart = results.pivot(index="horizon_minutes", columns="model", values="mean_bps")
        chart.plot(kind="bar", figsize=(12, 5))
        plt.axhline(0, color="black", lw=1)
        plt.ylabel("Mean return (basis points per event)")
        plt.title("Gross and cost-stressed fixed-horizon results")
        plt.tight_layout()
        plt.show()
    """),
    md(r"""
    ## 7. One-bar embargo control

    On these archives, a next-bar open is often the same numerical midpoint as the
    signal bar's close. A second entry delay uses the identical signal definition but
    waits one additional full bar. A large collapse suggests the apparent reversion
    is concentrated at the shared boundary rather than being a durable opportunity.
    """),
    code(r"""
    delay_rows = []
    for delay in (1, 2):
        events = build_event_returns(
            panel, features,
            horizon_bars=HORIZON_BARS[-1],
            timeframe_minutes=TIMEFRAME_MINUTES,
            entry_delay_bars=delay,
            round_trip_cost_bps_per_leg=ROUND_TRIP_COST_BPS_PER_LEG,
            non_overlapping=NON_OVERLAPPING,
        )
        summary = summarize_events(events)
        summary["entry_delay_bars"] = delay
        delay_rows.append(summary)
    delay_control = pd.concat(delay_rows, ignore_index=True)
    display(delay_control[["entry_delay_bars", "model", "trades", "mean_bps", "day_cluster_t", "daily_sharpe"]].round(4))
    """),
    md(r"""
    ## 8. Cost sensitivity

    This is not measured spread. It shows how much room the midpoint result has for
    spread, slippage, and fees. True triangular execution requires contemporaneous
    bid/ask quotes and must pass the executable cycle inequalities described at the
    end of the notebook.
    """),
    code(r"""
    cost_rows = []
    for cost in (0.0, 0.25, 0.5, 1.0, 2.0):
        events = build_event_returns(
            panel, features,
            horizon_bars=HORIZON_BARS[-1],
            timeframe_minutes=TIMEFRAME_MINUTES,
            entry_delay_bars=1,
            round_trip_cost_bps_per_leg=cost,
            non_overlapping=NON_OVERLAPPING,
        )
        summary = summarize_events(events)
        summary["cost_bps_per_leg"] = cost
        cost_rows.append(summary)
    cost_sensitivity = pd.concat(cost_rows, ignore_index=True)
    display(cost_sensitivity[["cost_bps_per_leg", "model", "trades", "mean_bps", "day_cluster_t", "daily_sharpe"]].round(4))
    """),
    md(r"""
    ## 9. How to interpret the result

    A research result is only interesting if it survives all of these:

    - the three sources are genuinely synchronized rather than merely sharing a minute label;
    - the two-bar embargo does not erase the result;
    - the three-leg residual, not only unhedged AUDUSD, moves in the predicted way;
    - gross expectancy comfortably exceeds plausible cost on all three legs;
    - neighboring timeframes, lookbacks, and Z thresholds give a stable pattern;
    - a date-block or circular-shift re-pairing null destroys the cross-pair link and the real result beats the full null distribution;
    - a frozen out-of-sample period succeeds without retuning.

    With synchronized bid/ask quotes, the actual executable cycle tests would be:

    $$AUDUSD_{bid}\,USDJPY_{bid}/AUDJPY_{ask}>1$$

    for selling expensive AUDUSD and buying AUD synthetically, and

    $$AUDJPY_{bid}/(AUDUSD_{ask}\,USDJPY_{ask})>1$$

    for the reverse cycle. Midpoint bar data cannot evaluate either inequality.
    Keep `OPEN_LOCKED_PERIOD=False` while choosing the timeframe, lookback, threshold,
    and horizon. Once those choices have been inspected on historical data, they are
    part of the search and must be frozen before opening a later period.
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
OUTPUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")
print(f"Wrote {OUTPUT}")
