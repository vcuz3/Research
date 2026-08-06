"""Generate the reproducible Bollinger breakout and regime-sweep notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "bollinger_breakout_regime_sweep.ipynb"


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
    # EURUSD / GBPUSD / AUDUSD / NZDUSD Bollinger breakout

    This notebook tests a five-minute momentum breakout:

    - signal after a completed close beyond the 200-bar mean ± 1.5 population standard deviations;
    - enter at the next five-minute open;
    - no take profit;
    - a ratcheting stop at the mean ± 0.75 standard deviations, updated only from completed bars;
    - close any open position at the New York Friday 17:00 FX close.

    Bollinger windows contain the last 200 valid observed closes. Scheduled rollover and weekend
    closures are not observations and do not reset the moving average. Short-horizon RV/ATR
    features still restart after a wall-clock gap so that their stated time horizons remain honest.

    It also sweeps Bollinger geometry, volatility level, volatility acceleration (RV5/RV30 and
    ATR-based VEI), and higher-timeframe SMA/EMA trend gates. All price-derived inputs are causal.
    Vectorised pandas/NumPy builds the features; a compiled array loop handles the stateful stop.

    ## Research boundary

    The default loader physically excludes every row at or after **2024-01-01 UTC**. Pre-2021 is
    the development sample and 2021-2023 is the requested in-sample evaluation period. Prior work
    has already inspected 2021-2023, so it is an internal temporal check, not pristine out-of-sample
    evidence. The 2024+ holdout stays sealed unless `ALLOW_HOLDOUT=True` is deliberately changed.

    Source bars are midpoint OHLC and do not contain an executable spread. Results therefore show
    gross performance plus explicit hypothetical cost stress. They are research diagnostics, not a
    tradability claim. “Calgar” is interpreted as the standard **Calmar ratio** (CAGR / max drawdown).
    """),
    code(r"""
    from dataclasses import asdict, replace
    from itertools import product
    from pathlib import Path
    import importlib
    import os
    import warnings

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display

    # Jupyter retains imported modules across reruns. Force the current engine from disk
    # so an already-open kernel cannot silently reuse the old gap-reset BB construction.
    import _bollinger_engine as bb_engine
    bb_engine = importlib.reload(bb_engine)
    from _bollinger_engine import (
        PAIRS, HOLDOUT_START, BREAKOUT_ENGINE_VERSION, StrategyConfig, build_feature_frame,
        load_five_minute_bars, performance_stats, portfolio_equity,
        observed_bar_rolling, run_config, sharpe_by_group,
    )

    warnings.filterwarnings('ignore', category=FutureWarning)
    sns.set_theme(style='whitegrid', context='notebook')
    pd.set_option('display.max_columns', 100)
    pd.set_option('display.width', 220)

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == 'exploration_2' else here / 'forex' / 'exploration_2'
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError('Run from the workspace root or forex/exploration_2.')
    DATA_DIR = PROJECT_ROOT.parent / 'data' / 'clean'

    RUN_PAIRS = list(PAIRS)
    ALLOW_HOLDOUT = False
    DEVELOPMENT_END = pd.Timestamp('2021-01-01', tz='UTC')
    EVALUATION_END = HOLDOUT_START
    STARTING_BALANCE = 10_000.0
    RISK_PER_TRADE = 0.01
    SLOT_LOOKBACK_SESSIONS = 90
    SLOT_MIN_FRACTION = 2 / 3
    GAP_PROXIMITY_BARS = 12
    RUN_PARAMETER_SWEEP = True
    FULL_FACTORIAL = False
    MAX_CONFIGS = 500
    SMOKE_MODE = os.getenv('BB_SWEEP_SMOKE', '0') == '1'

    BASE = StrategyConfig(
        name='baseline_bb200_e1.5_s0.75', bb_length=200, entry_sigma=1.5, stop_sigma=0.75,
        round_trip_cost_pips=0.0, stop_slippage_pips=0.0,
    )

    assert not ALLOW_HOLDOUT, 'Holdout opening should be an explicit, frozen research decision.'
    assert DEVELOPMENT_END < EVALUATION_END
    _bb_probe = observed_bar_rolling(
        pd.Series([1., 2., 3., 4., 5.]), pd.Series([True] * 5), 3, 'mean'
    )
    assert np.allclose(_bb_probe.dropna(), [2., 3., 4.]), 'Continuous BB engine check failed.'
    print('Data:', DATA_DIR)
    print('Engine:', Path(bb_engine.__file__).resolve())
    print('Engine version:', BREAKOUT_ENGINE_VERSION)
    print('Holdout seal:', f'rows >= {HOLDOUT_START} will not be loaded')
    """),
    md(r"""
    ## 1. Frozen execution interpretation and kill tests

    The “trailing 0.75σ band” is interpreted as a ratchet: a long stop can only rise and a short
    stop can only fall. The stop for bar *t* is calculated from information completed by *t-1*.
    It is live on the entry bar. A gap through the stop fills at that bar's open, not at the stale
    stop price. Only one position per pair is permitted; pairs may overlap in the portfolio.

    Before treating any sweep winner as interesting, require: positive average net R in both time
    samples, positive results on at least three of four correlated pairs, no collapse under a
    one-pip round trip, and stability across neighbouring settings. This is a searched screen; a
    survivor still needs a frozen claim-matched null and the sealed holdout.
    """),
    code(r"""
    # Executable timing/fill invariants. These complete in a few seconds, including Numba warm-up.
    import subprocess, sys
    test = subprocess.run(
        [sys.executable, '_test_bollinger_engine.py'], cwd=PROJECT_ROOT,
        capture_output=True, text=True, check=True,
    )
    print(test.stdout.strip())
    """),
    md(r"""
    ## 2. Parameter sweep design

    The default is a one-factor-at-a-time screen around the requested baseline. It is deliberately
    compact and interpretable. Set `FULL_FACTORIAL=True` for joint combinations, but treat that as a
    much larger multiple-search problem. Regime percentiles compare the current reading with the
    prior 90 New-York FX sessions at the same five-minute session slot; the current session never
    enters its own reference distribution.
    """),
    code(r"""
    def named(cfg, **updates):
        body = replace(cfg, **updates)
        tags = [f'{k}={v}' for k, v in updates.items() if k != 'name']
        return replace(body, name='|'.join(tags))

    def make_sweep(base=BASE, full_factorial=FULL_FACTORIAL):
        if full_factorial:
            configs = []
            for bb, entry, stop, rv, accel, trend in product(
                [100, 200, 300], [1.25, 1.5, 1.75, 2.0], [0.5, 0.75, 1.0],
                [None, 0.6, 0.8], [None, 0.6, 0.8],
                [(None, None, 'any'), ('sma', 50, 'aligned'), ('ema', 50, 'aligned')],
            ):
                kind, hours, mode = trend
                name = f'bb{bb}|e{entry}|s{stop}|rv{rv}|acc{accel}|{kind}{hours}|{mode}'
                configs.append(replace(base, name=name, bb_length=bb, entry_sigma=entry,
                    stop_sigma=stop, rv30_min_pct=rv, acceleration_min_pct=accel,
                    trend_kind=kind, trend_hours=hours, trend_mode=mode))
        else:
            configs = [base]
            configs += [named(base, bb_length=x) for x in [100, 300]]
            configs += [named(base, entry_sigma=x) for x in [1.25, 1.75, 2.0]]
            configs += [named(base, stop_sigma=x) for x in [0.5, 1.0, 1.25]]
            configs += [named(base, rv30_min_pct=x) for x in [0.4, 0.6, 0.8]]
            configs += [named(base, acceleration_min_pct=x) for x in [0.4, 0.6, 0.8]]
            for fast, slow in [(10, 50), (14, 50), (25, 100)]:
                for pct in [0.6, 0.8]:
                    configs.append(named(base, vei_fast=fast, vei_slow=slow, vei_min_pct=pct))
            for kind, hours, mode, strength in product(
                ['sma', 'ema'], [20, 50, 100], ['aligned', 'counter'], [None, 1.0]
            ):
                configs.append(named(base, trend_kind=kind, trend_hours=hours,
                                     trend_mode=mode, trend_strength_min=strength))
            configs += [named(base, round_trip_cost_pips=x) for x in [0.5, 1.0]]
        # Stable de-duplication (the baseline may recur in a supplied grid).
        unique = {tuple(asdict(c).items()): c for c in configs}
        configs = list(unique.values())
        if len(configs) > MAX_CONFIGS:
            raise ValueError(f'{len(configs)} configs exceeds MAX_CONFIGS={MAX_CONFIGS}')
        return configs

    configs = make_sweep()
    if SMOKE_MODE:
        RUN_PAIRS = ['EURUSD']
        configs = configs[:4]
    config_table = pd.DataFrame([asdict(c) for c in configs])
    display(config_table)
    print(f'{len(configs)} configurations across {len(RUN_PAIRS)} pairs')
    """),
    md(r"""
    ## 3. Load data, aggregate to five minutes, and run quality gates

    Bollinger bands roll over valid observed closes across scheduled market closures. This fixes the
    prior implementation, which restarted BB(200) after every non-five-minute link and therefore
    defined the indicator on only about 30% of rows. RV30, ATR and VEI remain segmented because a
    fixed-bar volatility horizon should not bridge a wall-clock gap.

    The report exposes raw gaps, partial five-minute bars, period coverage, time-of-day coverage,
    rolling-feature warm-up loss, and Friday-close markers. Partial five-minute bars remain visible
    for reporting but cannot form a signal, fill, or rolling input. The BB(200) assertion prevents
    the low-coverage construction from returning unnoticed.
    """),
    code(r"""
    bb_lengths = sorted({c.bb_length for c in configs} | {200})
    vei_pairs = sorted({(c.vei_fast, c.vei_slow) for c in configs if c.vei_fast is not None}
                       | {(10, 50), (14, 50), (25, 100)})
    trend_specs = sorted({(c.trend_kind, c.trend_hours) for c in configs if c.trend_kind is not None}
                         | {('sma', 20), ('sma', 50), ('sma', 100),
                            ('ema', 20), ('ema', 50), ('ema', 100)})

    frames, raw_quality, feature_coverage = {}, [], []
    for pair in RUN_PAIRS:
        bars, quality = load_five_minute_bars(pair, DATA_DIR, HOLDOUT_START, ALLOW_HOLDOUT)
        if SMOKE_MODE:
            bars = bars.loc[bars.bar_open >= pd.Timestamp('2020-01-01', tz='UTC')].reset_index(drop=True)
            bars['session_id'] = pd.factorize(bars.session_date, sort=True)[0].astype('int32')
        frame, coverage = build_feature_frame(
            bars, bb_lengths, vei_pairs, trend_specs,
            SLOT_LOOKBACK_SESSIONS, SLOT_MIN_FRACTION,
        )
        assert frame.bar_open.max() < HOLDOUT_START
        bb200 = coverage.loc[coverage.feature.eq('bb_mid_200')]
        assert bb200.coverage.min() > 0.995, bb200
        frames[pair] = frame
        raw_quality.append(quality)
        coverage.insert(0, 'pair', pair)
        feature_coverage.append(coverage)

    raw_quality = pd.DataFrame(raw_quality).set_index('pair')
    feature_coverage = pd.concat(feature_coverage, ignore_index=True)
    display(raw_quality.T)
    bb200_coverage = feature_coverage.loc[
        feature_coverage.feature.isin(['bb_mid_200', 'bb_sd_200'])
    ].copy()
    print('BB(200) COVERAGE — this table must be above 99.5%:')
    display(bb200_coverage.round(4))
    all_feature_coverage = (
        feature_coverage.groupby(['pair', 'sample']).coverage.agg(['min', 'median', 'max'])
    )
    print('ALL-FEATURE COVERAGE — minimum may be low because causal regime features need history; it is not BB coverage:')
    display(all_feature_coverage)

    gap_profile = []
    for pair, f in frames.items():
        g = f.loc[f.gap_before, ['bar_open', 'gap_minutes_before']].copy()
        g['pair'] = pair
        g['gap_hours'] = g.gap_minutes_before / 60
        gap_profile.append(g)
    gap_profile = pd.concat(gap_profile, ignore_index=True)
    display(gap_profile.groupby('pair').gap_hours.agg(['count', 'min', 'median', 'max']).round(2))

    slot_quality = []
    for pair, f in frames.items():
        sample = np.where(f.bar_open < DEVELOPMENT_END, 'development_pre2021', 'evaluation_2021_2023')
        q = (f.assign(sample=sample).groupby(['sample', 'session_slot'], observed=True)
             .agg(bars=('bar_open', 'size'), complete_share=('complete_5m', 'mean'),
                  first=('bar_open', 'min'), last=('bar_open', 'max')).reset_index())
        q.insert(0, 'pair', pair)
        slot_quality.append(q)
    slot_quality = pd.concat(slot_quality, ignore_index=True)
    display(slot_quality.groupby(['pair', 'sample']).complete_share.agg(['min', 'median', 'max']))
    """),
    md(r"""
    ## 4. Baseline and sweep

    Statistics are calculated from summed realised R by New-York FX session. The requested Sharpe
    excludes no-trade sessions and annualises by √252; `active_sessions` is printed beside it so the
    conditioning is explicit. Daily P&L is a sum, never an average of that day's trades.
    """),
    code(r"""
    all_trades = []
    run_configs = configs if RUN_PARAMETER_SWEEP else [BASE]
    for pair, frame in frames.items():
        for cfg in run_configs:
            t = run_config(frame, pair, cfg)
            if len(t):
                all_trades.append(t)
    trades = pd.concat(all_trades, ignore_index=True) if all_trades else pd.DataFrame()
    assert len(trades), 'No trades were generated.'
    assert pd.to_datetime(trades.entry_time, utc=True).max() < HOLDOUT_START

    metric_rows = []
    for (config_name, sample, pair), g in trades.groupby(['config', 'sample', 'pair'], observed=True):
        row = {'config': config_name, 'sample': sample, 'pair': pair}
        row.update(performance_stats(g).to_dict())
        metric_rows.append(row)
    for (config_name, sample), g in trades.groupby(['config', 'sample'], observed=True):
        row = {'config': config_name, 'sample': sample, 'pair': 'POOLED_PORTFOLIO'}
        row.update(performance_stats(g).to_dict())
        curve, eq = portfolio_equity(g, STARTING_BALANCE, RISK_PER_TRADE)
        row.update(eq.to_dict())
        metric_rows.append(row)
    sweep_stats = pd.DataFrame(metric_rows)

    baseline_stats = sweep_stats.loc[sweep_stats.config.eq(BASE.name)]
    display(baseline_stats.round(4))
    display(sweep_stats.loc[sweep_stats.pair.eq('POOLED_PORTFOLIO')]
            .sort_values(['sample', 'session_pooled_sharpe_active_only'], ascending=[True, False])
            .round(4))
    print('Entry-stop marketable events:', int(trades.entry_stop_marketable.sum()))
    print('Gap-stop exits:', int(trades.gap_stop.sum()))
    print('Friday exits:', int(trades.exit_reason.eq('friday_close').sum()))
    """),
    md(r"""
    ## 5. Post-hoc rollover-gap analysis

    This does not filter the strategy. It labels completed baseline trades by whether their signal
    occurred within `GAP_PROXIMITY_BARS` before or after a data gap. This shows whether carrying the
    BB window across closures concentrates performance around discontinuities.
    """),
    code(r"""
    baseline = trades.loc[trades.config.eq(BASE.name)].copy()
    after = baseline.bars_since_gap.le(GAP_PROXIMITY_BARS)
    before = baseline.bars_to_next_gap.le(GAP_PROXIMITY_BARS)
    baseline['gap_bucket'] = np.select(
        [after & before, after, before],
        ['near_both_sides', 'after_gap', 'before_gap'], default='not_near_gap',
    )
    gap_rows = []
    for (pair, sample, bucket), g in baseline.groupby(['pair', 'sample', 'gap_bucket'], observed=True):
        row = {'pair': pair, 'sample': sample, 'gap_bucket': bucket}
        row.update(performance_stats(g).to_dict())
        gap_rows.append(row)
    gap_trade_stats = pd.DataFrame(gap_rows)
    display(gap_trade_stats.round(4))
    """),
    md(r"""
    ## 6. Stability: years, volatility regimes, and trend strength

    Regime labels are descriptive bins on causal values observed at the signal close. Volatility
    percentiles are terciles of their prior-same-slot percentile. Trend strength is the absolute
    log distance from a completed-hour EMA(50), divided by trailing 30-minute realised volatility.
    """),
    code(r"""
    # Attach a common EMA(50h) trend measure even though the baseline itself is ungated.
    baseline['trend_ema_50h_strength'] = np.nan
    baseline['trend_ema_50h_alignment'] = np.nan
    for pair, idx in baseline.groupby('pair').groups.items():
        f = frames[pair]
        trade_idx = baseline.loc[idx, 'entry_index'].to_numpy(int)
        signal_idx = np.maximum(trade_idx - 1, 0)
        baseline.loc[idx, 'trend_ema_50h_strength'] = f.trend_ema_50h_strength.iloc[signal_idx].to_numpy()
        baseline.loc[idx, 'trend_ema_50h_alignment'] = (
            baseline.loc[idx, 'side'].to_numpy() * f.trend_ema_50h_direction.iloc[signal_idx].to_numpy()
        )

    baseline['vol_level_regime'] = pd.cut(
        baseline.rv30_pct, [0, 1/3, 2/3, 1], labels=['low', 'medium', 'high'], include_lowest=True)
    baseline['vol_acceleration_regime'] = pd.cut(
        baseline.rv_acceleration_pct, [0, 1/3, 2/3, 1], labels=['low', 'medium', 'high'], include_lowest=True)
    baseline['trend_strength_regime'] = pd.cut(
        baseline.trend_ema_50h_strength, [0, 0.5, 1.0, 2.0, np.inf],
        labels=['weak_<0.5', '0.5_to_1', '1_to_2', 'strong_2plus'], include_lowest=True)
    baseline['trend_alignment'] = np.where(baseline.trend_ema_50h_alignment > 0, 'aligned', 'counter')

    yearly = sharpe_by_group(baseline, ['pair', 'sample', 'year'])
    vol_table = sharpe_by_group(baseline.dropna(subset=['vol_level_regime']),
                                ['pair', 'sample', 'vol_level_regime'])
    accel_table = sharpe_by_group(baseline.dropna(subset=['vol_acceleration_regime']),
                                  ['pair', 'sample', 'vol_acceleration_regime'])
    trend_table = sharpe_by_group(baseline.dropna(subset=['trend_strength_regime']),
                                  ['pair', 'sample', 'trend_strength_regime', 'trend_alignment'])
    pooled_vol = sharpe_by_group(baseline.dropna(subset=['vol_level_regime']),
                                 ['sample', 'vol_level_regime']).assign(pair='POOLED_PORTFOLIO')
    pooled_accel = sharpe_by_group(baseline.dropna(subset=['vol_acceleration_regime']),
                                   ['sample', 'vol_acceleration_regime']).assign(pair='POOLED_PORTFOLIO')
    pooled_trend = sharpe_by_group(baseline.dropna(subset=['trend_strength_regime']),
                                   ['sample', 'trend_strength_regime', 'trend_alignment']).assign(pair='POOLED_PORTFOLIO')
    vol_table = pd.concat([vol_table, pooled_vol], ignore_index=True)
    accel_table = pd.concat([accel_table, pooled_accel], ignore_index=True)
    trend_table = pd.concat([trend_table, pooled_trend], ignore_index=True)
    display(yearly.round(4))
    display(vol_table.round(4))
    display(accel_table.round(4))
    display(trend_table.round(4))
    """),
    md(r"""
    ## 7. Return distribution and $10,000 equity curve

    Each trade risks 1% of realised equity at entry. Concurrent pairs may each risk 1%, so aggregate
    open risk can exceed 1%; there is no leverage cap. Equity is updated when trades close and is not
    marked to market between exits. CAGR and Calmar therefore describe this explicit simulation, not
    a broker-margin model.
    """),
    code(r"""
    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    for ax, sample in zip(axes.flat[:2], ['development_pre2021', 'evaluation_2021_2023']):
        x = baseline.loc[baseline['sample'].eq(sample), 'net_r'].dropna()
        sns.histplot(x, bins=80, stat='density', kde=True, ax=ax)
        ax.axvline(0, color='black', lw=1)
        ax.set(title=f'Baseline trade-return distribution: {sample}', xlabel='Net R')

    equity_summaries = []
    for sample, color in [('development_pre2021', 'tab:blue'), ('evaluation_2021_2023', 'tab:orange')]:
        g = baseline.loc[baseline['sample'].eq(sample)]
        curve, summary = portfolio_equity(g, STARTING_BALANCE, RISK_PER_TRADE)
        axes[1, 0].plot(curve.time, curve.equity, label=sample, color=color)
        axes[1, 1].plot(curve.time, curve.drawdown, label=sample, color=color)
        equity_summaries.append(pd.Series({'sample': sample, **summary.to_dict()}))
    axes[1, 0].set(title='Realised equity (each sample restarts at $10,000)', ylabel='$')
    axes[1, 1].set(title='Drawdown', ylabel='fraction')
    axes[1, 0].legend(); axes[1, 1].legend()
    plt.tight_layout()
    display(pd.DataFrame(equity_summaries).round(4))
    """),
    md(r"""
    ## 8. Parameter surfaces and export

    The export contains trades, configuration-level statistics, yearly/regime tables, and quality
    reports. No 2024+ results are written. Ranking a searched table is exploratory; do not treat the
    best row as an unbiased estimate.
    """),
    code(r"""
    # Neighbouring Bollinger geometry, holding other baseline settings fixed.
    geometry_names = [BASE.name] + [c.name for c in configs if (
        c.rv30_min_pct is None and c.acceleration_min_pct is None and c.vei_min_pct is None
        and c.trend_kind is None and c.round_trip_cost_pips == 0
    )]
    geometry = sweep_stats.loc[
        sweep_stats.config.isin(set(geometry_names)) & sweep_stats.pair.eq('POOLED_PORTFOLIO')
    ].copy()
    display(geometry.sort_values(['sample', 'session_pooled_sharpe_active_only'], ascending=[True, False]).round(4))

    EXPORT_RESULTS = False
    if EXPORT_RESULTS:
        out = PROJECT_ROOT / 'outputs'
        out.mkdir(exist_ok=True)
        trades.to_parquet(out / 'bollinger_sweep_trades_pre2024.parquet', index=False)
        sweep_stats.to_csv(out / 'bollinger_sweep_statistics_pre2024.csv', index=False)
        yearly.to_csv(out / 'baseline_yearly_statistics_pre2024.csv', index=False)
        vol_table.to_csv(out / 'baseline_volatility_regimes_pre2024.csv', index=False)
        accel_table.to_csv(out / 'baseline_acceleration_regimes_pre2024.csv', index=False)
        trend_table.to_csv(out / 'baseline_trend_regimes_pre2024.csv', index=False)
        gap_trade_stats.to_csv(out / 'baseline_gap_proximity_pre2024.csv', index=False)
        raw_quality.to_csv(out / 'data_quality_pre2024.csv')
        feature_coverage.to_csv(out / 'feature_coverage_pre2024.csv', index=False)
        slot_quality.to_csv(out / 'time_of_day_coverage_pre2024.csv', index=False)
        print('Wrote:', out)
    """),
    md(r"""
    ## Interpretation checklist

    - Compare gross and cost-stressed results; midpoint bars do not measure spread.
    - Read all four pairs separately; they are correlated confirmations, not four independent tests.
    - Prefer neighbouring-parameter stability over the single best searched cell.
    - Check `entry_stop_marketable`, gap-stop, Friday-exit, BB-coverage, gap-proximity, and
      slot-coverage counts.
    - If a regime gate merely reduces trade count, compare it with a deeper Bollinger entry threshold
      at a matched rate before calling it information.
    - Freeze any survivor and run a path-preserving, claim-matched null before opening 2024+.
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
