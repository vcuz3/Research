"""Generate the same-slot area mean-reversion entry-variant notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "area_mean_reversion_entry_variants.ipynb"


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
    # Same-slot area mean reversion: two entry variants

    This notebook tests whether an unusually large cumulative FX-session move tends to reverse.
    Bands are the causal 90th and 10th percentiles of the cumulative session log return observed at
    the same New-York FX-session five-minute slot during the prior 90 calendar days.

    Two entry rules use identical bands and exits:

    1. **First crossing:** take the first completed-bar transition from inside to outside per FX
       session.
    2. **30-minute checkpoint:** evaluate the completed bar every 30 minutes. Enter when outside
       only if flat; checkpoints occurring while a position is open are skipped.

    An upper breach is faded short and a lower breach is faded long. Both variants enter at the next
    five-minute open. Direction-adjusted returns are measured open-to-open at 15, 30, 60, and 120
    minutes; the plotted strategy exit remains the configured 60-minute horizon. Missing endpoints
    remain null rather than bridging a closure. The primary result allows only the first signal per
    session and reports upper/lower sides separately.

    A symmetric absolute-move control uses causal same-slot history but ignores directional
    asymmetry. Its percentile threshold is calibrated using signal count only so its first-cross
    trade count matches the primary rule as closely as the discrete sample permits. All three rules
    are repeated unchanged on EURUSD, GBPUSD, AUDUSD, and NZDUSD.

    The default loader keeps 2024+ sealed. Midpoint OHLC has no measured spread, so the configured
    round-trip pip charge is a sensitivity assumption rather than a calibrated execution estimate.
    """),
    code(r"""
    from dataclasses import replace
    from pathlib import Path
    import importlib
    import os

    import numpy as np
    import pandas as pd
    import plotly.graph_objects as go
    from IPython.display import display

    import _area_mean_reversion_engine as area_engine
    importlib.reload(area_engine)
    from _area_mean_reversion_engine import (
        AreaConfig, build_area_bands, run_variants,
    )
    from _bollinger_engine import HOLDOUT_START, PAIRS, load_five_minute_bars

    pd.set_option("display.max_columns", 100)
    pd.set_option("display.width", 220)
    pd.set_option("display.float_format", lambda x: f"{x:.6f}")

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == "exploration_2" else here / "forex" / "exploration_2"
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError("Run from the workspace root or forex/exploration_2.")
    DATA_DIR = PROJECT_ROOT.parent / "data" / "clean"

    # ----------------------------- user controls -----------------------------
    SELECTED_PAIR = "EURUSD"
    RUN_ALL_PAIRS = True
    ALLOW_HOLDOUT = False
    HORIZONS = (15, 30, 60, 120)
    BASE_CONFIG = AreaConfig(
        window="90D", min_observations=40,
        upper_quantile=0.90, lower_quantile=0.10,
        holding_minutes=60, checkpoint_minutes=30,
        pip_size=0.0001,
    )

    # Imported ECN spread/commission anchors from
    # ../exploration_1/rsi_spread_economics_results.json. Slippage is an explicit
    # adverse 0.10 pip per side assumption; none of these costs is measured in the
    # midpoint archive, so edit or stress them for the intended venue and size.
    PAIR_COSTS = {
        "EURUSD": {"spread_pips": 0.20, "slippage_per_side_pips": 0.10, "commission_round_trip_pips": 0.70},
        "GBPUSD": {"spread_pips": 0.50, "slippage_per_side_pips": 0.10, "commission_round_trip_pips": 0.70},
        "AUDUSD": {"spread_pips": 0.50, "slippage_per_side_pips": 0.10, "commission_round_trip_pips": 0.70},
        "NZDUSD": {"spread_pips": 1.00, "slippage_per_side_pips": 0.10, "commission_round_trip_pips": 0.70},
    }

    PLOT_VARIANT = "checkpoint_30m"  # first_cross or checkpoint_30m
    PLOT_DATE = None                 # e.g. "2020-09-10"; None selects an actual trade
    PLOT_TIME = "02:30"
    HOURS_BEFORE = 4
    HOURS_AFTER = 4
    SMOKE_MODE = os.getenv("AREA_MR_SMOKE", "0") == "1"
    # -------------------------------------------------------------------------

    assert SELECTED_PAIR in PAIRS
    ANALYSIS_PAIRS = [SELECTED_PAIR] if (SMOKE_MODE or not RUN_ALL_PAIRS) else list(PAIRS)
    print("Pairs:", ANALYSIS_PAIRS)
    print("Holdout:", "OPEN" if ALLOW_HOLDOUT else f"sealed from {HOLDOUT_START.date()}")
    print("Base configuration:", BASE_CONFIG)
    display(pd.DataFrame(PAIR_COSTS).T.assign(
        total_cost_pips=lambda x: x.spread_pips + 2*x.slippage_per_side_pips + x.commission_round_trip_pips
    ))
    """),
    md(r"""
    ## 1. Load and audit five-minute bars

    The shared loader checks duplicate and out-of-order timestamps, invalid OHLC, source-minute
    coverage, five-minute partial bars, wall-clock gaps, and the holdout boundary. Partial bars remain
    visible for diagnosis but cannot create signals, entries, or exits.
    """),
    code(r"""
    bars_by_pair, quality_by_pair, config_by_pair = {}, {}, {}
    for pair in ANALYSIS_PAIRS:
        config_by_pair[pair] = replace(BASE_CONFIG, **PAIR_COSTS[pair])
        bars_by_pair[pair], quality_by_pair[pair] = load_five_minute_bars(
            pair, DATA_DIR, holdout_start=HOLDOUT_START, allow_holdout=ALLOW_HOLDOUT
        )
        q = quality_by_pair[pair]
        assert q.duplicate_timestamps == 0
        assert q.out_of_order_timestamps == 0
        assert q.invalid_ohlc_rows == 0
        if not ALLOW_HOLDOUT:
            assert q.holdout_rows_loaded == 0
    quality_table = pd.DataFrame(quality_by_pair).T
    display(quality_table)
    """),
    md(r"""
    ## 2. Causal same-slot area

    The current session never enters its own band. A single signed historical distribution produces
    both boundaries, avoiding separate positive/negative warm-ups. Quantiles control the historical
    firing rate more directly than conditional means.
    """),
    code(r"""
    area_by_pair = {
        pair: build_area_bands(bars_by_pair[pair], config_by_pair[pair])
        for pair in ANALYSIS_PAIRS
    }
    coverage_rows = []
    hourly_rows = []
    for pair, area in area_by_pair.items():
        coverage_rows.append({
            "pair": pair, "bars": len(area), "complete_bars": int(area.complete_5m.sum()),
            "band_ready_bars": int(area.band_ready.sum()),
            "underpopulated_valid_bars": int((area.valid_bar & ~area.band_ready).sum()),
            "upper_breaches": int(area.breach_side.eq(1).sum()),
            "lower_breaches": int(area.breach_side.eq(-1).sum()),
        })
        ny_hour = area.bar_open.dt.tz_convert("America/New_York").dt.hour
        hourly = (area.assign(ny_hour=ny_hour).groupby("ny_hour")
        .agg(
            bars=("bar_open", "size"),
            complete_share=("complete_5m", "mean"),
            band_ready_share=("band_ready", "mean"),
            breach_share=("breach_side", lambda x: x.ne(0).mean()),
            min_band_observations=("band_observations", "min"),
        )
        ).reset_index()
        hourly.insert(0, "pair", pair)
        hourly_rows.append(hourly)
    coverage_summary = pd.DataFrame(coverage_rows).set_index("pair")
    coverage_by_hour = pd.concat(hourly_rows, ignore_index=True)
    display(coverage_summary)
    display(coverage_by_hour)
    """),
    md(r"""
    ## 3. Execute both variants

    Signals use completed bars. Entries and exits use later bar opens. Variant 1 permits at most one
    trade per FX session. Variant 2 can re-enter at a checkpoint exactly when the previous position
    exits, but never overlaps positions.
    """),
    code(r"""
    trade_frames, control_match_rows = [], []
    for pair, area in area_by_pair.items():
        pair_trades = run_variants(area, config_by_pair[pair], horizons=HORIZONS)
        control_match_rows.append({
            "pair": pair,
            "control_percentile_threshold": pair_trades.attrs["control_percentile_threshold"],
            "primary_trades": pair_trades.attrs["primary_trade_count"],
            "control_trades": pair_trades.attrs["control_trade_count"],
            "count_difference": pair_trades.attrs["control_trade_count"] - pair_trades.attrs["primary_trade_count"],
        })
        pair_trades.insert(0, "pair", pair)
        trade_frames.append(pair_trades)
    trades = pd.concat(trade_frames, ignore_index=True)
    control_match = pd.DataFrame(control_match_rows)
    if trades.empty:
        raise AssertionError("No trades were generated")
    assert trades.entry_time.eq(trades.decision_time).all()
    assert trades.exit_time.sub(trades.entry_time).eq(pd.Timedelta(minutes=BASE_CONFIG.holding_minutes)).all()
    assert not trades[["entry_price", "exit_price", "gross_pips", "net_pips"]].isna().any().any()

    for pair, pair_trades in trades.groupby("pair"):
        primary = pair_trades[pair_trades.variant.eq("first_cross")]
        assert primary.groupby("session_date").size().max() == 1
        checkpoint = pair_trades[pair_trades.variant.eq("checkpoint_30m")].sort_values("entry_time")
        assert checkpoint.entry_time.iloc[1:].reset_index(drop=True).ge(
            checkpoint.exit_time.iloc[:-1].reset_index(drop=True)
        ).all()
    print("Trades by variant:")
    display(trades.groupby(["pair", "variant"]).size().rename("trades").to_frame())
    print("Matched-frequency control calibration:")
    display(control_match)
    display(trades.head())
    """),
    md(r"""
    ## 4. Early results

    `gross_pips` is the direction-adjusted mean-reversion return: positive means the fade worked.
    `net_pips` subtracts the configured round-trip cost. For the checkpoint rule, daily P&L is the
    sum of non-overlapping trades, never their mean.
    """),
    code(r"""
    horizon_rows = []
    for (pair, variant, breach), group in trades.groupby(["pair", "variant", "breach"], sort=False):
        for horizon in HORIZONS:
            gross = group[f"gross_pips_{horizon}m"].dropna()
            net = group.loc[gross.index, f"net_pips_{horizon}m"]
            horizon_rows.append({
                "pair": pair, "variant": variant, "breach": breach, "horizon": horizon,
                "trades": len(gross), "gross_mean_pips": gross.mean(),
                "net_mean_pips": net.mean(), "net_win_rate": net.gt(0).mean(),
            })
    horizon_summary = pd.DataFrame(horizon_rows)
    print("Primary one-signal-per-session result, upper/lower reported separately:")
    display(horizon_summary[horizon_summary.variant.eq("first_cross")])
    print("Matched-frequency large-move control:")
    display(horizon_summary[horizon_summary.variant.eq("large_move_control")])
    print("30-minute checkpoint secondary variant:")
    display(horizon_summary[horizon_summary.variant.eq("checkpoint_30m")])

    comparison_rows = []
    for (pair, variant), group in trades.groupby(["pair", "variant"], sort=False):
        for horizon in HORIZONS:
            gross = group[f"gross_pips_{horizon}m"].dropna()
            net = group.loc[gross.index, f"net_pips_{horizon}m"]
            comparison_rows.append({
                "pair": pair, "variant": variant, "horizon": horizon,
                "trades": len(gross), "gross_mean_pips": gross.mean(),
                "net_mean_pips": net.mean(),
            })
    comparison = pd.DataFrame(comparison_rows)
    display(comparison)

    daily = trades.groupby(["pair", "variant", "session_date"], as_index=False).net_pips.sum()
    daily_stats = daily.groupby(["pair", "variant"]).net_pips.agg(["count", "mean", "std", "min", "max"])
    display(daily_stats)
    """),
    md(r"""
    ## 5. Candles, bands, entries, and exits

    Set `PLOT_DATE` and `PLOT_TIME` above to inspect a specific window. When `PLOT_DATE=None`, the
    notebook centres the chart on an actual entry from the selected variant so the markers are
    immediately visible.
    """),
    code(r"""
    def plot_area_trades(
        area_df, trade_df, date, time, variant="first_cross",
        hours_before=4, hours_after=4, timezone="America/New_York",
    ):
        required = {"bar_open", "open", "high", "low", "close", "upper_band",
                    "lower_band", "session_open_price"}
        missing = required.difference(area_df.columns)
        if missing:
            raise ValueError(f"Missing area columns: {sorted(missing)}")
        if variant not in set(trade_df.variant):
            raise ValueError(f"Unknown or empty variant: {variant}")

        centre_local = pd.Timestamp(f"{date} {time}")
        if centre_local.tzinfo is None:
            centre_local = centre_local.tz_localize(timezone)
        else:
            centre_local = centre_local.tz_convert(timezone)
        centre_utc = centre_local.tz_convert("UTC")
        start_utc = centre_utc - pd.Timedelta(hours=hours_before)
        end_utc = centre_utc + pd.Timedelta(hours=hours_after)

        plot_df = area_df[area_df.bar_open.between(start_utc, end_utc)].copy()
        if plot_df.empty:
            raise ValueError(f"No bars between {start_utc} and {end_utc}")
        plot_df["plot_time"] = plot_df.bar_open.dt.tz_convert(timezone)

        variant_trades = trade_df[trade_df.variant.eq(variant)].copy()
        plot_trades = variant_trades[
            variant_trades.entry_time.le(end_utc) & variant_trades.exit_time.ge(start_utc)
        ].copy()
        for column in ("decision_time", "entry_time", "exit_time"):
            plot_trades[f"plot_{column}"] = plot_trades[column].dt.tz_convert(timezone)

        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=plot_df.plot_time, y=plot_df.lower_band, mode="lines",
            line=dict(color="rgba(65,105,225,0.9)", width=1),
            name="Lower band", hovertemplate="Lower: %{y:.5f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.plot_time, y=plot_df.upper_band, mode="lines", fill="tonexty",
            line=dict(color="rgba(65,105,225,0.9)", width=1),
            fillcolor="rgba(100,149,237,0.20)", name="Area",
            hovertemplate="Upper: %{y:.5f}<extra></extra>",
        ))
        fig.add_trace(go.Scatter(
            x=plot_df.plot_time, y=plot_df.session_open_price, mode="lines",
            line=dict(color="darkorange", width=1, dash="dash"), name="Session open",
            hovertemplate="Session open: %{y:.5f}<extra></extra>",
        ))
        fig.add_trace(go.Candlestick(
            x=plot_df.plot_time, open=plot_df.open, high=plot_df.high,
            low=plot_df.low, close=plot_df.close, name="OHLC",
            increasing_line_color="#16a085", decreasing_line_color="#e74c3c",
        ))

        # One batched line trace connects every entry to its corresponding exit.
        path_x, path_y = [], []
        for row in plot_trades.itertuples():
            path_x.extend([row.plot_entry_time, row.plot_exit_time, None])
            path_y.extend([row.entry_price, row.exit_price, None])
        if path_x:
            fig.add_trace(go.Scatter(
                x=path_x, y=path_y, mode="lines",
                line=dict(color="rgba(40,40,40,0.55)", width=1, dash="dot"),
                name="Trade path", hoverinfo="skip",
            ))

        for direction, color, symbol in (("long", "#00897b", "triangle-up"),
                                          ("short", "#d32f2f", "triangle-down")):
            entries = plot_trades[plot_trades.direction.eq(direction)]
            if not entries.empty:
                hover = [
                    f"{direction.title()} {r.breach} breach<br>Entry {r.entry_price:.5f}"
                    f"<br>Exit {r.exit_price:.5f}<br>Gross {r.gross_pips:.2f} pips"
                    f"<br>Net {r.net_pips:.2f} pips"
                    for r in entries.itertuples()
                ]
                fig.add_trace(go.Scatter(
                    x=entries.plot_entry_time, y=entries.entry_price, mode="markers",
                    marker=dict(color=color, size=12, symbol=symbol, line=dict(color="white", width=1)),
                    name=f"{direction.title()} entry", text=hover,
                    hovertemplate="%{text}<extra></extra>",
                ))
        if not plot_trades.empty:
            exit_hover = [
                f"Exit {r.exit_price:.5f}<br>Gross {r.gross_pips:.2f} pips"
                f"<br>Net {r.net_pips:.2f} pips"
                for r in plot_trades.itertuples()
            ]
            fig.add_trace(go.Scatter(
                x=plot_trades.plot_exit_time, y=plot_trades.exit_price, mode="markers",
                marker=dict(color="#212121", size=10, symbol="x"), name="Exit",
                text=exit_hover, hovertemplate="%{text}<extra></extra>",
            ))

        fig.add_vline(x=centre_local, line_color="purple", line_dash="dot", line_width=1.2)
        fig.update_layout(
            template="plotly_white", height=750, hovermode="x unified",
            title=f"{SELECTED_PAIR} {variant}: {centre_local.strftime('%Y-%m-%d %H:%M')} ({timezone})",
            xaxis_title=f"Time ({timezone})", yaxis_title="Price",
            legend=dict(orientation="h", y=1.02, x=0), margin=dict(l=60, r=30, t=100, b=60),
        )
        fig.update_xaxes(
            range=[centre_local - pd.Timedelta(hours=hours_before),
                   centre_local + pd.Timedelta(hours=hours_after)],
            rangeslider_visible=False,
        )
        return fig, plot_df, plot_trades
    """),
    code(r"""
    selected_area = area_by_pair[SELECTED_PAIR]
    selected_trades = trades[trades.pair.eq(SELECTED_PAIR)].copy()
    if PLOT_DATE is None:
        candidates = selected_trades[selected_trades.variant.eq(PLOT_VARIANT)]
        candidate = candidates.iloc[len(candidates) // 2]
        local_entry = candidate.entry_time.tz_convert("America/New_York")
        selected_date = local_entry.strftime("%Y-%m-%d")
        selected_time = local_entry.strftime("%H:%M")
    else:
        selected_date, selected_time = PLOT_DATE, PLOT_TIME

    fig, plot_bars, plot_trades = plot_area_trades(
        selected_area, selected_trades, date=selected_date, time=selected_time, variant=PLOT_VARIANT,
        hours_before=HOURS_BEFORE, hours_after=HOURS_AFTER,
    )
    display(plot_trades[[
        "variant", "breach", "direction", "decision_time", "entry_time", "exit_time",
        "entry_price", "exit_price", "gross_pips", "net_pips",
    ]])
    if SMOKE_MODE:
        print("Plot smoke:", len(plot_bars), "candles and", len(plot_trades), "trades")
    else:
        fig.show()
    """),
    md(r"""
    ## Interpretation guardrails

    - Read direction-adjusted gross returns before hit rate or net results.
    - Require both upper and lower breaches to agree; one-sided performance may be drift.
    - The 30-minute rule is a deployable non-overlapping policy, but repeated sessions remain
      dependent. Assess daily P&L rather than treating every trade as independent evidence.
    - Compare any survivor with a simpler large-move rule at matched entry frequency. The band may
      merely select generic large moves rather than unique same-slot information.
    - A gross mean below plausible spread and slippage is not a tradable edge.
    - Freeze the band, horizon, cost, and primary metric before opening 2024+.
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
print(OUT)
