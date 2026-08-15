"""Generate paired incremental-value and signal-state cost validation notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "area_mean_reversion_incremental_validation.ipynb"


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
    # Area mean reversion: incremental value and signal-state costs

    This notebook tests the two unresolved questions from the entry-variant study:

    1. Does the signed 90th/10th percentile area add value beyond the frequency-matched symmetric
       large-move control?
    2. Does any gross effect survive a spread estimate that widens in the volatile states where the
       signal fires?

    The primary estimand is **first-cross minus matched-control pips per eligible FX session**.
    Sessions on which a rule does not trade contribute zero. A circular 20-session moving-block
    bootstrap preserves short-run dependence. The combined four-pair row aligns common dates before
    equal-weighting pairs, preserving their contemporaneous USD dependence within each resampled block.

    The archive contains midpoint OHLC only, not bid/ask. Therefore the cost model is explicitly a
    proxy: imported ECN round-trip spread anchors are multiplied by signal-time trailing 30-minute
    realised volatility relative to the pair median, bounded to 1x–4x. A 0.70-pip round-trip
    commission and 0.10-pip adverse slippage per side are then added.

    **Kill rule:** reject incremental area information if the 60-minute paired gross block-bootstrap
    interval includes zero for the common-date portfolio, or if results are not directionally stable
    across pairs. Reject economic viability if proxy net expectancy is non-positive on either side or
    fails under the ECN cost regime. The default loader keeps 2024+ sealed.
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
    import _area_validation as validation
    importlib.reload(area_engine)
    importlib.reload(validation)
    from _area_mean_reversion_engine import AreaConfig, build_area_bands, run_variants
    from _area_validation import (
        add_signal_state_costs, common_date_portfolio,
        moving_block_bootstrap_mean, paired_session_panel,
    )
    from _bollinger_engine import HOLDOUT_START, PAIRS, load_five_minute_bars

    pd.set_option("display.max_columns", 100)
    pd.set_option("display.width", 240)
    pd.set_option("display.float_format", lambda x: f"{x:.6f}")

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == "exploration_2" else here / "forex" / "exploration_2"
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError("Run from the workspace root or forex/exploration_2.")
    DATA_DIR = PROJECT_ROOT.parent / "data" / "clean"

    # ----------------------------- frozen controls -----------------------------
    ALLOW_HOLDOUT = False
    HORIZONS = (15, 30, 60, 120)
    PRIMARY_HORIZON = 60
    BLOCK_LENGTH = 20
    BOOTSTRAP_DRAWS = 5_000
    BOOTSTRAP_SEED = 20260809
    BASE = AreaConfig(
        window="90D", min_observations=40,
        upper_quantile=0.90, lower_quantile=0.10,
        holding_minutes=60, checkpoint_minutes=30, pip_size=0.0001,
    )
    BASE_RT_SPREAD = {"EURUSD": 0.20, "GBPUSD": 0.50, "AUDUSD": 0.50, "NZDUSD": 1.00}
    COMMISSION_RT_PIPS = 0.70
    SLIPPAGE_PER_SIDE_PIPS = 0.10
    SPREAD_REGIMES = {"ECN": 1.0, "retail": 2.0, "wide": 3.0}
    VOLATILITY_MULTIPLIER_CAP = 4.0
    SMOKE_MODE = os.getenv("AREA_VALIDATION_SMOKE", "0") == "1"
    ANALYSIS_PAIRS = ["EURUSD"] if SMOKE_MODE else list(PAIRS)
    DRAWS = 500 if SMOKE_MODE else BOOTSTRAP_DRAWS
    # ---------------------------------------------------------------------------

    print("Pairs:", ANALYSIS_PAIRS)
    print("Holdout:", "OPEN" if ALLOW_HOLDOUT else f"sealed from {HOLDOUT_START.date()}")
    print("Bootstrap:", DRAWS, "draws with", BLOCK_LENGTH, "session blocks")
    """),
    md(r"""
    ## 1. Rebuild the unchanged signals

    This uses the same causal bands, first-cross entry, matched-frequency control, next-open fill,
    and exact forward horizons as the entry-variant notebook. Data-quality gates run before any
    result is interpreted.
    """),
    code(r"""
    bars_by_pair, area_by_pair, trades_by_pair, quality_by_pair = {}, {}, {}, {}
    match_rows = []
    for pair in ANALYSIS_PAIRS:
        bars, quality = load_five_minute_bars(
            pair, DATA_DIR, holdout_start=HOLDOUT_START, allow_holdout=ALLOW_HOLDOUT
        )
        assert quality.duplicate_timestamps == 0
        assert quality.out_of_order_timestamps == 0
        assert quality.invalid_ohlc_rows == 0
        assert ALLOW_HOLDOUT or quality.holdout_rows_loaded == 0
        area = build_area_bands(bars, BASE)
        pair_trades = run_variants(area, BASE, horizons=HORIZONS)
        bars_by_pair[pair], area_by_pair[pair] = bars, area
        trades_by_pair[pair], quality_by_pair[pair] = pair_trades, quality
        match_rows.append({
            "pair": pair,
            "primary_trades": pair_trades.attrs["primary_trade_count"],
            "control_trades": pair_trades.attrs["control_trade_count"],
            "count_difference": pair_trades.attrs["control_trade_count"] - pair_trades.attrs["primary_trade_count"],
            "control_percentile": pair_trades.attrs["control_percentile_threshold"],
            "band_ready_share": area.band_ready.mean(),
            "partial_five_minute_bars": quality.partial_five_minute_bars,
        })
    quality_table = pd.DataFrame(quality_by_pair).T
    match_table = pd.DataFrame(match_rows)
    display(quality_table)
    display(match_table)
    """),
    md(r"""
    ## 2. Paired session-block inference

    Primary and control are aligned by FX session. Missing signals are zero P&L—not deleted. The
    pair rows preserve serial dependence with moving blocks. The portfolio row uses only dates shared
    by every included pair and resamples their equal-weight difference jointly.
    """),
    code(r"""
    gross_panels, gross_bootstrap_rows = {}, []
    panels_by_horizon = {}
    for horizon in HORIZONS:
        pair_panels = {}
        for number, pair in enumerate(ANALYSIS_PAIRS):
            panel = paired_session_panel(
                area_by_pair[pair], trades_by_pair[pair], horizon, value_prefix="gross_pips"
            )
            pair_panels[pair] = panel
            result = moving_block_bootstrap_mean(
                panel.difference, block_length=BLOCK_LENGTH, draws=DRAWS,
                seed=BOOTSTRAP_SEED + 100 * horizon + number,
            )
            gross_bootstrap_rows.append({"scope": pair, "horizon": horizon, **result})
        panels_by_horizon[horizon] = pair_panels
        if len(pair_panels) > 1:
            portfolio = common_date_portfolio(pair_panels)
            result = moving_block_bootstrap_mean(
                portfolio.difference, block_length=BLOCK_LENGTH, draws=DRAWS,
                seed=BOOTSTRAP_SEED + 100 * horizon + 99,
            )
            gross_bootstrap_rows.append({"scope": "equal_weight_common_dates", "horizon": horizon, **result})
    gross_bootstrap = pd.DataFrame(gross_bootstrap_rows)
    display(gross_bootstrap)

    primary_gross_test = gross_bootstrap[gross_bootstrap.horizon.eq(PRIMARY_HORIZON)]
    display(primary_gross_test)
    """),
    md(r"""
    ## 3. Stability of the paired difference

    Era rows are descriptive diagnostics, not separately selected strategies. A credible incremental
    effect should not come entirely from one early interval.
    """),
    code(r"""
    era_rows = []
    for pair, panel in panels_by_horizon[PRIMARY_HORIZON].items():
        p = panel.copy()
        year = pd.to_datetime(p.session_date).dt.year
        p["era"] = pd.cut(year, [2010, 2015, 2019, 2023], labels=["2011-2015", "2016-2019", "2020-2023"])
        for era, group in p.groupby("era", observed=True):
            era_rows.append({
                "pair": pair, "era": str(era), "sessions": len(group),
                "primary_pips_per_session": group.first_cross.mean(),
                "control_pips_per_session": group.large_move_control.mean(),
                "difference_pips_per_session": group.difference.mean(),
            })
    era_stability = pd.DataFrame(era_rows)
    display(era_stability)
    """),
    md(r"""
    ## 4. Signal-state spread proxy

    This does **not** claim to recover quoted spreads from midpoint bars. It reports how much more
    volatile and illiquid the actual entry states are, then widens an imported ECN spread anchor by
    that measured volatility multiplier. Absolute costs remain assumptions and are swept below.
    """),
    code(r"""
    priced_by_pair, cost_diagnostic_rows = {}, []
    for pair in ANALYSIS_PAIRS:
        priced, diagnostics = add_signal_state_costs(
            area_by_pair[pair], trades_by_pair[pair],
            base_round_trip_spread_pips=BASE_RT_SPREAD[pair],
            pip_size=BASE.pip_size,
            commission_round_trip_pips=COMMISSION_RT_PIPS,
            slippage_per_side_pips=SLIPPAGE_PER_SIDE_PIPS,
            volatility_multiplier_cap=VOLATILITY_MULTIPLIER_CAP,
            horizons=HORIZONS,
        )
        priced_by_pair[pair] = priced
        row = {"pair": pair, **diagnostics.to_dict()}
        cost_diagnostic_rows.append(row)
    cost_diagnostics = pd.DataFrame(cost_diagnostic_rows)
    display(cost_diagnostics)

    state_rows = []
    for pair, priced in priced_by_pair.items():
        baseline_illiquid = cost_diagnostics.set_index("pair").loc[pair, "baseline_illiquid_hour_share"]
        for variant, group in priced.groupby("variant"):
            state_rows.append({
                "pair": pair, "variant": variant, "trades": len(group),
                "median_vol_multiplier": group.spread_vol_multiplier.median(),
                "mean_estimated_rt_spread_pips": group.estimated_rt_spread_pips.mean(),
                "mean_all_in_cost_pips": group.estimated_all_in_cost_pips.mean(),
                "illiquid_hour_share": group.illiquid_hour.mean(),
                "illiquid_tilt_vs_all_bars": group.illiquid_hour.mean() / baseline_illiquid,
            })
    signal_state_table = pd.DataFrame(state_rows)
    display(signal_state_table)
    """),
    md(r"""
    ## 5. Proxy-net economics and paired net difference

    Upper and lower sides remain separate. `break_even_cost_pips` is simply gross expectancy: the
    maximum all-in round-trip friction that would leave mean P&L at zero.
    """),
    code(r"""
    economics_rows = []
    for pair, priced in priced_by_pair.items():
        selected = priced[priced.variant.isin(["first_cross", "large_move_control"])]
        for (variant, breach), group in selected.groupby(["variant", "breach"]):
            for horizon in HORIZONS:
                gross = group[f"gross_pips_{horizon}m"]
                net = group[f"proxy_net_pips_{horizon}m"]
                economics_rows.append({
                    "pair": pair, "variant": variant, "breach": breach, "horizon": horizon,
                    "trades": int(gross.notna().sum()),
                    "gross_mean_pips": gross.mean(),
                    "mean_proxy_cost_pips": group.estimated_all_in_cost_pips.mean(),
                    "proxy_net_mean_pips": net.mean(),
                    "break_even_cost_pips": gross.mean(),
                    "cost_headroom_pips": gross.mean() - group.estimated_all_in_cost_pips.mean(),
                })
    economics = pd.DataFrame(economics_rows)
    display(economics[economics.variant.eq("first_cross")])

    net_bootstrap_rows = []
    for horizon in HORIZONS:
        pair_panels = {}
        for number, pair in enumerate(ANALYSIS_PAIRS):
            panel = paired_session_panel(
                area_by_pair[pair], priced_by_pair[pair], horizon,
                value_prefix="proxy_net_pips",
            )
            pair_panels[pair] = panel
            result = moving_block_bootstrap_mean(
                panel.difference, BLOCK_LENGTH, DRAWS,
                seed=BOOTSTRAP_SEED + 10_000 + 100 * horizon + number,
            )
            net_bootstrap_rows.append({"scope": pair, "horizon": horizon, **result})
        if len(pair_panels) > 1:
            portfolio = common_date_portfolio(pair_panels)
            result = moving_block_bootstrap_mean(
                portfolio.difference, BLOCK_LENGTH, DRAWS,
                seed=BOOTSTRAP_SEED + 10_000 + 100 * horizon + 99,
            )
            net_bootstrap_rows.append({"scope": "equal_weight_common_dates", "horizon": horizon, **result})
    net_bootstrap = pd.DataFrame(net_bootstrap_rows)
    display(net_bootstrap)
    """),
    md(r"""
    ## 6. Cost-regime sensitivity

    Spread anchors are multiplied by 1x, 2x, and 3x while commission, slippage, and each trade's
    observed volatility multiplier are held fixed. This is a sensitivity analysis, not fill proof.
    """),
    code(r"""
    regime_rows = []
    for pair, priced in priced_by_pair.items():
        primary = priced[priced.variant.eq("first_cross")]
        for regime, spread_multiple in SPREAD_REGIMES.items():
            cost = (
                BASE_RT_SPREAD[pair] * spread_multiple * primary.spread_vol_multiplier
                + COMMISSION_RT_PIPS + 2 * SLIPPAGE_PER_SIDE_PIPS
            )
            for horizon in HORIZONS:
                gross = primary[f"gross_pips_{horizon}m"]
                regime_rows.append({
                    "pair": pair, "regime": regime, "horizon": horizon,
                    "gross_mean_pips": gross.mean(), "mean_cost_pips": cost.mean(),
                    "net_mean_pips": (gross - cost).mean(),
                })
    cost_regime_table = pd.DataFrame(regime_rows)
    display(cost_regime_table)
    """),
    md(r"""
    ## 7. Visual diagnostics

    The cumulative chart is the primary-minus-control gross difference, not either strategy's total
    P&L. A persistent upward slope would indicate incremental area information.
    """),
    code(r"""
    primary_panels = panels_by_horizon[PRIMARY_HORIZON]
    fig = go.Figure()
    for pair, panel in primary_panels.items():
        fig.add_trace(go.Scatter(
            x=panel.session_date, y=panel.difference.cumsum(), mode="lines", name=pair,
            hovertemplate="%{x|%Y-%m-%d}<br>Cumulative difference: %{y:.1f} pips<extra></extra>",
        ))
    if len(primary_panels) > 1:
        portfolio = common_date_portfolio(primary_panels)
        fig.add_trace(go.Scatter(
            x=portfolio.session_date, y=portfolio.difference.cumsum(), mode="lines",
            line=dict(color="black", width=3), name="Equal-weight common dates",
        ))
    fig.update_layout(
        template="plotly_white", height=650,
        title=f"Cumulative first-cross minus matched-control difference ({PRIMARY_HORIZON}m)",
        xaxis_title="FX session date", yaxis_title="Cumulative gross difference (pips/session)",
        hovermode="x unified", legend=dict(orientation="h", y=1.02),
    )
    if SMOKE_MODE:
        print("Plot smoke:", len(fig.data), "cumulative traces")
    else:
        fig.show()
    """),
    md(r"""
    ## Decision guide

    - Incremental information requires the 60-minute common-date portfolio interval to exclude zero
      and pair/era signs to be reasonably stable.
    - Economic viability requires positive proxy-net expectancy on upper and lower breaches, not just
      a positive gross average.
    - A positive primary-minus-control **net** difference does not make either strategy profitable;
      inspect absolute proxy-net tables as well.
    - Because 2024+ remains sealed here, freeze any follow-up rule before changing `ALLOW_HOLDOUT`.
    - Midpoint-derived volatility can scale an external spread anchor, but it cannot validate quoted
      spread or fills. Broker/venue bid-ask data is required for deployment evidence.
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
