"""Build the AUD translation of the supplied EURUSD Pine v6 strategy."""

from __future__ import annotations

import hashlib
import json
from pathlib import Path
from textwrap import dedent


ROOT = Path(__file__).resolve().parent
OUTPUT = ROOT / "audusd_pine_triangular_strategy.ipynb"


def md(source: str) -> dict:
    text = dedent(source).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("m" + text).encode()).hexdigest()[:12],
        "metadata": {},
        "source": text.splitlines(keepends=True),
    }


def code(source: str) -> dict:
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
    # Synthetic AUDUSD triangular strategy — Pine v6 translation

    This is a Python notebook translation of the supplied **Synthetic EURUSD
    Triangular Strategy**, with the instruments changed as follows:

    | Pine source | AUD translation |
    | --- | --- |
    | chart symbol EURUSD | actual AUDUSD |
    | Leg A EURJPY | AUDJPY |
    | Leg B USDJPY | USDJPY |
    | `EURJPY / USDJPY` | `AUDJPY / USDJPY` |

    The strategy trades **AUDUSD only**, exactly like the source script trades
    EURUSD only. It does not execute all three legs and therefore is a statistical
    relative-value strategy, not executable triangular arbitrage.
    """),
    md(r"""
    ## 1. Parameters translated from Pine

    All source defaults are retained. `TIMEFRAME_MINUTES` represents the
    TradingView chart timeframe and may be 1, 5, 15, 30, or 60 minutes.

    The default dates are an exploratory development window. Keep 2024 onward
    locked while changing parameters.
    """),
    code(r"""
    import pandas as pd

    # ------------------------ DATA / CHART ------------------------
    START = "2015-01-01"
    END = "2020-01-01"             # half-open; END is excluded
    OPEN_LOCKED_PERIOD = False
    TIMEFRAME_MINUTES = 5           # TradingView chart timeframe

    # -------------------- PINE Z-SCORE INPUTS --------------------
    LOOKBACK_PERIOD = 50
    Z_ENTRY = 1.5
    Z_EXIT = 0.25

    # ---------------------- PINE ATR INPUTS ----------------------
    USE_ATR_RISK = True
    ATR_PERIOD = 14
    ATR_STOP_MULT = 2.0
    ATR_TARGET_MULT = 3.0

    # -------------------- PINE STRATEGY INPUTS -------------------
    INITIAL_CAPITAL = 100_000.0
    FIXED_QUANTITY_AUD = 100_000.0
    COMMISSION_PERCENT = 0.0        # per order, matching the source default

    if TIMEFRAME_MINUTES not in {1, 5, 15, 30, 60}:
        raise ValueError("Choose TIMEFRAME_MINUTES from 1, 5, 15, 30, or 60")
    if not 0 < Z_EXIT < Z_ENTRY:
        raise ValueError("Require 0 < Z_EXIT < Z_ENTRY")
    if pd.Timestamp(END) > pd.Timestamp("2024-01-01") and not OPEN_LOCKED_PERIOD:
        raise ValueError("2024+ is locked; freeze the strategy before explicitly opening it")

    print(f"{TIMEFRAME_MINUTES}-minute bars | Z({LOOKBACK_PERIOD}) entry +/-{Z_ENTRY}, exit +/-{Z_EXIT}")
    print(f"ATR({ATR_PERIOD}) stop {ATR_STOP_MULT}x, target {ATR_TARGET_MULT}x | enabled={USE_ATR_RISK}")
    """),
    md(r"""
    ## 2. Setup

    Market entries and Z-reversion closes are generated from a completed bar and
    fill at the following bar's open. ATR stop/target levels are frozen from the
    **signal close**, matching the supplied Pine code rather than recentering on
    the eventual entry price.
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
    from strategy.pine_translation import build_pine_features
    from backtest_engine.pine_strategy import run_pine_strategy, summarize_pine_trades

    print("Project:", PROJECT_ROOT)
    """),
    md(r"""
    ## 3. Load and audit AUDUSD, AUDJPY, and USDJPY

    Each chart bar must contain every underlying minute. The three pairs are joined
    on exact UTC timestamps without forward filling. This is intentionally more
    conservative than Pine's `barmerge.gaps_off`, which can carry a stale cross-leg
    value across a missing bar.
    """),
    code(r"""
    triangle = load_triangle_data(PROJECT_ROOT, START, END, TIMEFRAME_MINUTES)
    panel = triangle.panel

    display(triangle.raw_quality)
    display(triangle.alignment.to_frame())
    coverage = (
        triangle.bar_coverage.groupby("pair", observed=True)
        .agg(observed_intervals=("observed_intervals", "sum"),
             complete_bars=("complete_bars", "sum"), raw_minutes=("raw_minutes", "sum"))
        .assign(complete_share=lambda x: x.complete_bars / x.observed_intervals)
    )
    display(coverage.round(5))
    assert triangle.raw_quality[["duplicate_ts", "out_of_order", "invalid_ohlc"]].to_numpy().sum() == 0
    assert panel.index.is_unique and panel.index.is_monotonic_increasing
    """),
    md(r"""
    ## 4. Pine-compatible features

    The synthetic rate and spread are:

    $$SyntheticAUDUSD_t=\frac{AUDJPY_t}{USDJPY_t},\qquad
      Spread_t=AUDUSD_t-SyntheticAUDUSD_t.$$

    Like Pine's `ta.sma` and `ta.stdev`, the current completed bar is included in
    the rolling window. Standard deviation uses the population convention
    (`ddof=0`). ATR is Wilder's RMA, seeded by the first ATR-period simple average.
    """),
    code(r"""
    features = build_pine_features(
        panel,
        triangle.audusd_bars,
        lookback_period=LOOKBACK_PERIOD,
        atr_period=ATR_PERIOD,
    )
    print(f"Feature-ready decisions: {features.feature_ready.sum():,} / {len(features):,}")
    display(features[["actual_audusd", "synthetic_audusd", "spread_pips", "zscore", "atr", "feature_ready"]].head(LOOKBACK_PERIOD + 3).tail())
    """),
    code(r"""
    plot_data = features.loc[features.feature_ready].tail(min(10_000, features.feature_ready.sum()))
    fig, axes = plt.subplots(2, 1, figsize=(14, 8), sharex=True)
    axes[0].plot(plot_data.index, plot_data.actual_audusd, label="Actual AUDUSD", lw=1)
    axes[0].plot(plot_data.index, plot_data.synthetic_audusd, label="AUDJPY / USDJPY", lw=1, alpha=0.8)
    axes[0].legend()
    axes[0].set_ylabel("USD per AUD")
    axes[0].set_title("Actual and synthetic AUDUSD")

    axes[1].plot(plot_data.index, plot_data.zscore, color="tab:purple", lw=0.8)
    axes[1].axhline(Z_ENTRY, color="tab:red", ls="--", label="short entry")
    axes[1].axhline(-Z_ENTRY, color="tab:green", ls="--", label="long entry")
    axes[1].axhline(Z_EXIT, color="tab:red", ls=":", alpha=0.7)
    axes[1].axhline(-Z_EXIT, color="tab:green", ls=":", alpha=0.7)
    axes[1].axhline(0, color="black", lw=0.8)
    axes[1].set_ylabel("Spread Z-score")
    axes[1].legend(ncol=2)
    plt.tight_layout()
    plt.show()
    """),
    md(r"""
    ## 5. Signal-rate diagnostic

    The Pine rule enters from a **state** (`Z <= -entry` or `Z >= entry`) whenever
    flat, not only on the first threshold crossing. Signal opportunity rates are
    shown by UTC hour because a fixed all-hours Z threshold can inadvertently act
    as a clock filter.
    """),
    code(r"""
    opportunities = features.loc[features.feature_ready, ["zscore"]].copy()
    opportunities["entry_state"] = opportunities.zscore.abs().ge(Z_ENTRY)
    opportunities["utc_hour"] = opportunities.index.hour
    hourly = opportunities.groupby("utc_hour").agg(
        ready_bars=("entry_state", "size"), entry_state_bars=("entry_state", "sum")
    )
    hourly["entry_state_rate"] = hourly.entry_state_bars / hourly.ready_bars
    display(hourly)
    print("Hourly entry-state-rate CV:", round(hourly.entry_state_rate.std() / hourly.entry_state_rate.mean(), 3))
    """),
    md(r"""
    ## 6. Stateful strategy replay

    The engine maintains one AUDUSD position, matching `strategy.position_size == 0`.
    It replays ATR brackets on the underlying one-minute AUDUSD bars, starting in
    the entry bar. If stop and target both touch in one minute, the stop is assumed
    first. A gap through a level fills at the minute open.
    """),
    code(r"""
    trades, actions, final_state = run_pine_strategy(
        triangle.audusd_bars,
        triangle.audusd_1m,
        features,
        timeframe_minutes=TIMEFRAME_MINUTES,
        z_entry=Z_ENTRY,
        z_exit=Z_EXIT,
        use_atr_risk=USE_ATR_RISK,
        atr_stop_mult=ATR_STOP_MULT,
        atr_target_mult=ATR_TARGET_MULT,
        initial_capital=INITIAL_CAPITAL,
        quantity=FIXED_QUANTITY_AUD,
        commission_percent=COMMISSION_PERCENT,
    )
    summary = summarize_pine_trades(trades, INITIAL_CAPITAL)
    display(summary.to_frame("value"))
    print("Open position at data end:", final_state["open_position"] is not None)
    print("Pending order at data end:", final_state["pending_order"])
    """),
    code(r"""
    if not trades.empty:
        display(trades.head(10))
        display(trades.groupby(["side", "exit_reason"], observed=True).agg(
            trades=("net_pnl_usd", "size"),
            gross_pnl_usd=("gross_pnl_usd", "sum"),
            net_pnl_usd=("net_pnl_usd", "sum"),
            mean_net_usd=("net_pnl_usd", "mean"),
            win_rate=("net_pnl_usd", lambda x: x.gt(0).mean()),
        ).round(3))

        fig, axes = plt.subplots(1, 2, figsize=(14, 4.5))
        axes[0].plot(trades.exit_ts, trades.equity)
        axes[0].axhline(INITIAL_CAPITAL, color="black", lw=0.8)
        axes[0].set(title="Realized trade equity", ylabel="USD", xlabel="Exit time")
        trades.exit_reason.value_counts().plot(kind="bar", ax=axes[1])
        axes[1].set(title="Exit reasons", ylabel="Trades", xlabel="Reason")
        plt.tight_layout()
        plt.show()
    """),
    md(r"""
    ## 7. Commission sensitivity

    The source Pine script sets commission to zero. This reruns the complete
    stateful engine under alternative per-order percentage commissions. It still
    does **not** measure bid/ask spread or three-leg execution costs.
    """),
    code(r"""
    sensitivity_rows = []
    for commission in (0.0, 0.001, 0.0025, 0.005, 0.01):
        cost_trades = trades.copy()
        if not cost_trades.empty:
            cost_trades["cost_usd"] = (
                FIXED_QUANTITY_AUD * (cost_trades.entry_price + cost_trades.exit_price)
                * commission / 100.0
            )
            cost_trades["net_pnl_usd"] = cost_trades.gross_pnl_usd - cost_trades.cost_usd
            cost_trades["equity"] = INITIAL_CAPITAL + cost_trades.net_pnl_usd.cumsum()
            cost_trades["peak_equity"] = cost_trades.equity.cummax()
            cost_trades["drawdown_usd"] = cost_trades.equity - cost_trades.peak_equity
        row = summarize_pine_trades(cost_trades, INITIAL_CAPITAL)
        row["commission_percent_per_order"] = commission
        sensitivity_rows.append(row)
    commission_sensitivity = pd.DataFrame(sensitivity_rows)
    display(commission_sensitivity[["commission_percent_per_order", "trades", "gross_pnl_usd", "cost_usd", "net_pnl_usd", "profit_factor", "daily_sharpe"]].round(3))
    """),
    md(r"""
    ## 8. Translation notes and limitations

    Preserved from Pine:

    - arithmetic spread `AUDUSD - AUDJPY/USDJPY`;
    - current-window SMA and population standard deviation;
    - state-based flat-position entries at ±`Z_ENTRY`;
    - Z-reversion exits at ±`Z_EXIT`;
    - Wilder ATR and stop/target levels frozen from the signal close;
    - fixed 100,000-AUD order size and next-bar market fills;
    - one position at a time.

    Deliberate local differences:

    - exact synchronized complete-bar joins replace `barmerge.gaps_off` stale-value
      filling;
    - one-minute replay resolves coarse-bar bracket behavior, with stop-first
      treatment when the one-minute path remains ambiguous;
    - gap-through stops/targets use the first tradable minute open;
    - this does not attempt to reproduce a particular OANDA feed, TradingView
      session, chart timezone, or broker-emulator version;
    - midpoint data omit bid/ask spread and cannot establish executable triangular
      arbitrage.

    Treat any run while changing timeframe or parameters as exploration. Freeze the
    complete configuration and a kill test before inspecting a later evaluation
    window.
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
