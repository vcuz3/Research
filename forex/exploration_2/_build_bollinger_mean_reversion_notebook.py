"""Generate the Bollinger excursion/re-entry mean-reversion notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "bollinger_reentry_mean_reversion.ipynb"


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
    # FX Bollinger excursion/re-entry mean reversion

    This notebook implements a distinct hypothesis from the failed breakout system:

    1. A completed five-minute close moves outside the 200-observed-bar Bollinger band.
    2. Within a configurable number of bars, price closes back inside the same outer band.
    3. Enter toward the moving average at the next bar's open.
    4. Exit at a frozen inner-band/mean target, a wide frozen catastrophic stop, a timeout, or
       the New-York Friday 17:00 close—whichever occurs first.

    The default uses ±1.5σ for the excursion, allows six bars for re-entry, targets the entry-time
    moving average, uses a ±2.5σ stop, and times out after 120 minutes. Stop-free and nearer-target
    controls are included so entry information can be separated from exit geometry.

    ## Three implementation corrections

    - **BB(200) coverage:** the prior notebook grouped every uninterrupted wall-clock block and
      restarted after the daily rollover gap. With roughly one gap per trading day, a 200-bar warm-up
      left the band defined only around 09:50–17:00 New York. Here BB(200) always means the last 200
      valid observed closes, across scheduled rollover/weekend closures. Coverage is asserted above
      99.5% after the one-time start-of-file warm-up.
    - **Causal RV regimes:** current trailing RV30 is compared with shifted same-slot distributions
      from the prior 90 and prior 252 New-York FX sessions. Both causal medians, ratios to median, and
      percentiles are available. The current observation never enters its own baseline.
    - **Single-pair account:** choose `SELECTED_PAIR`. The equity curve and headline account metrics
      use that pair only. Other pairs are diagnostic robustness rows, never combined into one account.

    The default loader excludes 2024+ rows. Midpoint bars contain no measured bid/ask spread, so cost
    stress is essential and no output is a tradability claim.
    """),
    code(r"""
    from dataclasses import asdict, replace
    from itertools import product
    from pathlib import Path
    import os
    import warnings

    import numpy as np
    import pandas as pd
    import matplotlib.pyplot as plt
    import seaborn as sns
    from IPython.display import display

    from _bollinger_engine import PAIRS, HOLDOUT_START, load_five_minute_bars
    from _bollinger_mean_reversion_engine import (
        MeanReversionConfig, build_mean_reversion_features, performance_stats,
        portfolio_equity, run_mean_reversion_config,
    )

    warnings.filterwarnings('ignore', category=FutureWarning)
    sns.set_theme(style='whitegrid', context='notebook')
    pd.set_option('display.max_columns', 100)
    pd.set_option('display.width', 240)

    here = Path.cwd().resolve()
    PROJECT_ROOT = here if here.name == 'exploration_2' else here / 'forex' / 'exploration_2'
    if not PROJECT_ROOT.exists():
        raise FileNotFoundError('Run from the workspace root or forex/exploration_2.')
    DATA_DIR = PROJECT_ROOT.parent / 'data' / 'clean'

    # ----------------------------- user controls -----------------------------
    SELECTED_PAIR = 'EURUSD'  # EURUSD, GBPUSD, AUDUSD, NZDUSD
    RUN_CROSS_PAIR_DIAGNOSTICS = True
    STARTING_BALANCE = 10_000.0
    RISK_PER_TRADE = 0.01
    EQUITY_CONFIG_NAME = 'reentry_baseline'
    EQUITY_SAMPLES = ['development_pre2021', 'evaluation_2021_2023']
    GAP_PROXIMITY_BARS = 12  # 60 minutes on either side

    ALLOW_HOLDOUT = False
    RUN_PARAMETER_SWEEP = True
    FULL_FACTORIAL = False
    MAX_CONFIGS = 400
    SHORT_RV_MEMORY = 90
    LONG_RV_MEMORY = 252
    RV_MIN_FRACTION = 2 / 3
    SMOKE_MODE = os.getenv('BB_REENTRY_SMOKE', '0') == '1'
    # -------------------------------------------------------------------------

    BASE = MeanReversionConfig(
        name='reentry_baseline', bb_length=200, outer_sigma=1.5,
        max_reentry_bars=6, target_sigma=0.0, stop_sigma=2.5,
        sizing_stop_sigma=2.5, min_risk_sigma=0.5, timeout_bars=24, rv_gate_mode='none',
        round_trip_cost_pips=0.0, stop_slippage_pips=0.0,
    )
    assert SELECTED_PAIR in PAIRS
    assert not ALLOW_HOLDOUT, 'Opening 2024+ requires a separately frozen decision.'
    print('Selected account pair:', SELECTED_PAIR)
    print('Holdout seal:', f'rows >= {HOLDOUT_START} will not be loaded')
    """),
    md(r"""
    ## 1. Execution specification and kill rule

    Target and stop levels are frozen from the re-entry signal bar. A gap through either level exits
    at the next open, not the stale level. Both are active on the entry bar. If a five-minute bar
    touches target and stop, the stop is credited first. Timeout is measured open-to-open. Only one
    position per pair is allowed.

    Initial R is the distance from entry to the configurable ±2.5σ sizing stop. The stop-free arm
    keeps this same risk unit so it remains comparable. Reject the candidate if the stop-free fixed-
    horizon entry diagnostic does not clear plausible costs, or if the full strategy fails to deliver
    positive net average R in both samples with at least three-of-four pair agreement. Any searched
    survivor still requires matched-selectivity controls and a claim-matched null before 2024+.
    """),
    code(r"""
    import subprocess, sys
    test = subprocess.run(
        [sys.executable, '_test_bollinger_mean_reversion_engine.py'],
        cwd=PROJECT_ROOT, capture_output=True, text=True, check=True,
    )
    print(test.stdout.strip())
    """),
    md(r"""
    ## 2. Compact parameter and regime sweep

    The default changes one component at a time. `FULL_FACTORIAL=True` is available but materially
    enlarges the search. RV gates include the requested causal median slot RV and the longer-memory
    252-session regime. Percentile gates use the same shifted prior-slot history.
    """),
    code(r"""
    def named(base, **updates):
        cfg = replace(base, **updates)
        return replace(cfg, name='|'.join(f'{k}={v}' for k, v in updates.items()))

    def make_configs(full_factorial=FULL_FACTORIAL):
        if full_factorial:
            out = []
            for outer, wait, target, stop, timeout, gate in product(
                [1.25, 1.5, 1.75], [3, 6, 12], [0.0, 0.75],
                [None, 2.5, 3.0], [12, 24, 48],
                ['none', 'above_short_median', 'above_long_median', 'long_percentile'],
            ):
                name = f'o{outer}|wait{wait}|t{target}|s{stop}|to{timeout}|{gate}'
                out.append(replace(BASE, name=name, outer_sigma=outer, max_reentry_bars=wait,
                                   target_sigma=target, stop_sigma=stop, timeout_bars=timeout,
                                   rv_gate_mode=gate))
        else:
            out = [BASE]
            out += [named(BASE, outer_sigma=x) for x in [1.25, 1.75, 2.0]]
            out += [named(BASE, max_reentry_bars=x) for x in [1, 3, 12]]
            out += [named(BASE, target_sigma=x) for x in [0.75, None]]
            out += [named(BASE, stop_sigma=x) for x in [None, 2.0, 3.0]]
            out += [named(BASE, min_risk_sigma=x) for x in [0.25, 0.75, 1.0]]
            out += [named(BASE, timeout_bars=x) for x in [6, 12, 48]]
            out += [named(BASE, rv_gate_mode=x) for x in [
                'above_short_median', 'above_long_median', 'joint_medians']]
            for mode in ['short_percentile', 'long_percentile']:
                out += [named(BASE, rv_gate_mode=mode, rv_percentile_threshold=x) for x in [0.6, 0.8]]
            out += [named(BASE, round_trip_cost_pips=x) for x in [0.5, 1.0]]
            out += [named(BASE, stop_slippage_pips=x) for x in [0.5, 1.0]]
        unique = {tuple(asdict(c).items()): c for c in out}
        out = list(unique.values())
        if len(out) > MAX_CONFIGS:
            raise ValueError(f'{len(out)} configs exceeds MAX_CONFIGS={MAX_CONFIGS}')
        return out

    configs = make_configs()
    analysis_pairs = list(PAIRS) if RUN_CROSS_PAIR_DIAGNOSTICS else [SELECTED_PAIR]
    if SMOKE_MODE:
        analysis_pairs = [SELECTED_PAIR]
        configs = configs[:5]
    display(pd.DataFrame([asdict(c) for c in configs]))
    print(f'{len(configs)} configurations; account pair={SELECTED_PAIR}; diagnostic pairs={analysis_pairs}')
    """),
    md(r"""
    ## 3. Load bars, build continuous BB(200), and audit coverage

    Bollinger and RV use different clocks intentionally:

    - Bollinger operates on the sequence of valid observed closes and crosses closures.
    - RV30 requires six consecutive five-minute returns and restarts after a wall-clock gap.
    - Same-slot medians/percentiles use only prior sessions and tolerate a configurable fraction of
      missing same-slot observations.

    The coverage table reports each feature by sample. The assertion prevents a repeat of the prior
    hidden 30%-coverage strategy.
    """),
    code(r"""
    bb_lengths = sorted({c.bb_length for c in configs})
    frames, quality_rows, coverage_rows = {}, [], []
    for pair in analysis_pairs:
        bars, quality = load_five_minute_bars(pair, DATA_DIR, HOLDOUT_START, ALLOW_HOLDOUT)
        if SMOKE_MODE:
            bars = bars.loc[bars.bar_open >= pd.Timestamp('2019-01-01', tz='UTC')].reset_index(drop=True)
            bars['session_id'] = pd.factorize(bars.session_date, sort=True)[0].astype('int32')
        frame, coverage = build_mean_reversion_features(
            bars, bb_lengths, SHORT_RV_MEMORY, LONG_RV_MEMORY, RV_MIN_FRACTION,
        )
        assert frame.bar_open.max() < HOLDOUT_START
        bb200 = coverage.loc[coverage.feature.eq('bb_mid_200')]
        assert bb200.coverage.min() > 0.995, bb200
        frames[pair] = frame
        quality_rows.append(quality)
        coverage.insert(0, 'pair', pair)
        coverage_rows.append(coverage)

    quality = pd.DataFrame(quality_rows).set_index('pair')
    coverage = pd.concat(coverage_rows, ignore_index=True)
    display(quality.T)
    display(coverage.loc[coverage.feature.isin([
        'bb_mid_200', 'bb_sd_200', 'rv30',
        'rv30_slot_median_90', 'rv30_vs_slot_median_90', 'rv30_slot_pct_90',
        'rv30_slot_median_252', 'rv30_vs_slot_median_252', 'rv30_slot_pct_252',
    ])].round(4))

    gap_profile = []
    for pair, f in frames.items():
        g = f.loc[f.gap_before, ['bar_open', 'gap_minutes_before']].copy()
        g['pair'] = pair
        g['gap_hours'] = g.gap_minutes_before / 60
        gap_profile.append(g)
    gap_profile = pd.concat(gap_profile, ignore_index=True)
    display(gap_profile.groupby('pair').gap_hours.agg(['count', 'min', 'median', 'max']).round(2))
    """),
    md(r"""
    ## 4. Run the re-entry strategy and parameter sweep

    Cross-pair rows are shown only for robustness. No pooled multi-pair account is constructed.
    Headline metrics and later equity plots are filtered to `SELECTED_PAIR`.
    """),
    code(r"""
    trade_frames, signal_frames = [], {}
    for pair, frame in frames.items():
        for cfg in (configs if RUN_PARAMETER_SWEEP else [BASE]):
            t, s = run_mean_reversion_config(frame, pair, cfg)
            if len(t):
                trade_frames.append(t)
            if cfg.name == BASE.name:
                signal_frames[pair] = s
    trades = pd.concat(trade_frames, ignore_index=True) if trade_frames else pd.DataFrame()
    assert len(trades), 'No trades generated.'
    assert pd.to_datetime(trades.entry_time, utc=True).max() < HOLDOUT_START

    rows = []
    for (config_name, pair, sample), g in trades.groupby(['config', 'pair', 'sample'], observed=True):
        row = {'config': config_name, 'pair': pair, 'sample': sample}
        row.update(performance_stats(g).to_dict())
        rows.append(row)
    stats = pd.DataFrame(rows)
    selected_stats = stats.loc[stats.pair.eq(SELECTED_PAIR)]
    display(selected_stats.loc[selected_stats.config.eq(BASE.name)].round(4))
    display(selected_stats.sort_values(['sample', 'session_pooled_sharpe_active_only'],
                                       ascending=[True, False]).round(4))
    display(stats.loc[stats.config.eq(BASE.name)].round(4))
    print('Adverse same-bar resolutions:', int(trades.ambiguous_bar_adverse_stop.sum()))
    print('Gap exits:', int(trades.gap_exit.sum()))
    print('Baseline signals rejected for sub-minimum initial risk:',
          sum(int(s.risk_too_small_at_next_open.sum()) for s in signal_frames.values()))
    """),
    md(r"""
    ## 5. Stop-free entry-information diagnostic

    This measures each baseline re-entry at fixed open-to-open horizons with no target or stop. A
    horizon-specific cooldown enforces non-overlap. It is the cheapest check that the entry—not the
    bracket—contains information. Gross pips, hypothetical net pips, hit rate, and session-clustered
    t-statistics are reported.
    """),
    code(r"""
    def cluster_t(x, cluster):
        x, cluster = np.asarray(x, float), np.asarray(cluster)
        ok = np.isfinite(x)
        x, cluster = x[ok], cluster[ok]
        if len(x) < 2:
            return np.nan
        centered = x - x.mean()
        sums = pd.Series(centered).groupby(cluster).sum().to_numpy()
        se = np.sqrt(np.square(sums).sum()) / len(x)
        return x.mean() / se if se > 0 else np.nan

    entry_rows = []
    for pair, signals in signal_frames.items():
        f = frames[pair]
        for sample, start, end in [
            ('development_pre2021', pd.Timestamp('1900-01-01', tz='UTC'), pd.Timestamp('2021-01-01', tz='UTC')),
            ('evaluation_2021_2023', pd.Timestamp('2021-01-01', tz='UTC'), HOLDOUT_START),
        ]:
            base_idx = signals.loc[
                pd.to_datetime(signals.signal_time, utc=True).between(start, end, inclusive='left'),
                'signal_index'].to_numpy(int)
            for horizon_min in [5, 15, 30, 60, 120, 240]:
                h = horizon_min // 5
                idx = base_idx[base_idx + 1 + h < len(f)]
                keep, free = [], -1
                for i in idx:
                    if i + 1 >= free:
                        keep.append(i); free = i + 1 + h
                idx = np.asarray(keep, int)
                sides = signals.set_index('signal_index').loc[idx, 'side'].to_numpy(float)
                entry = f.open.iloc[idx + 1].to_numpy()
                exit_ = f.open.iloc[idx + 1 + h].to_numpy()
                pips = sides * (exit_ - entry) / 0.0001
                entry_rows.append({
                    'pair': pair, 'sample': sample, 'horizon_min': horizon_min, 'signals': len(idx),
                    'gross_pips': np.mean(pips), 'after_0.5_pip': np.mean(pips - 0.5),
                    'after_1.0_pip': np.mean(pips - 1.0), 'hit_rate': np.mean(pips > 0),
                    'session_cluster_t': cluster_t(pips, f.session_date.iloc[idx]),
                })
    entry_diagnostic = pd.DataFrame(entry_rows)
    display(entry_diagnostic.loc[entry_diagnostic.pair.eq(SELECTED_PAIR)].round(4))
    display(entry_diagnostic.groupby(['sample', 'horizon_min']).agg(
        signals=('signals', 'sum'), median_gross_pips=('gross_pips', 'median'),
        median_after_05=('after_0.5_pip', 'median'), median_cluster_t=('session_cluster_t', 'median'),
        pairs_positive=('gross_pips', lambda x: int((x > 0).sum())),
    ).round(4))
    """),
    md(r"""
    ## 6. Post-hoc rollover-gap analysis

    This does not filter the strategy. It labels completed baseline trades by whether their signal
    occurred within `GAP_PROXIMITY_BARS` before or after a data gap. The analysis answers whether
    carrying BB(200) across closures concentrates losses around discontinuities.
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
    display(gap_trade_stats.loc[gap_trade_stats.pair.eq(SELECTED_PAIR)].round(4))
    display(gap_trade_stats.round(4))
    """),
    md(r"""
    ## 7. Causal RV-gate comparison and regime tables

    `above_short_median` means RV30 exceeds the prior-90-session same-slot median.
    `above_long_median` uses 252 sessions. Percentile gates use the corresponding causal reference
    distribution. These gates are evaluated in the full state machine—not applied after trades.
    """),
    code(r"""
    rv_configs = [c.name for c in configs if c.rv_gate_mode != 'none'] + [BASE.name]
    display(selected_stats.loc[selected_stats.config.isin(rv_configs)]
            .sort_values(['sample', 'session_pooled_sharpe_active_only'], ascending=[True, False])
            .round(4))

    selected_baseline = baseline.loc[baseline.pair.eq(SELECTED_PAIR)].copy()
    selected_baseline['rv90_regime'] = pd.cut(
        selected_baseline.rv30_slot_pct_90, [0, 1/3, 2/3, 1],
        labels=['low', 'medium', 'high'], include_lowest=True)
    selected_baseline['rv252_regime'] = pd.cut(
        selected_baseline.rv30_slot_pct_252, [0, 1/3, 2/3, 1],
        labels=['low', 'medium', 'high'], include_lowest=True)

    regime_rows = []
    for feature in ['rv90_regime', 'rv252_regime']:
        for (sample, regime), g in selected_baseline.groupby(['sample', feature], observed=True):
            row = {'sample': sample, 'feature': feature, 'regime': regime}
            row.update(performance_stats(g).to_dict())
            regime_rows.append(row)
    regime_stats = pd.DataFrame(regime_rows)
    display(regime_stats.round(4))
    """),
    md(r"""
    ## 8. Selected-pair yearly metrics, distribution, and equity

    The account is explicitly filtered to `SELECTED_PAIR`; no other pair affects sizing, P&L, CAGR,
    drawdown, Sortino, or Calmar. Each displayed sample restarts at $10,000 and risks 1% of realised
    equity per trade. With one-position-per-pair there are no overlapping positions in this curve.
    """),
    code(r"""
    account_trades = trades.loc[
        trades.pair.eq(SELECTED_PAIR) & trades.config.eq(EQUITY_CONFIG_NAME)
    ].copy()
    yearly_rows = []
    for (sample, year), g in account_trades.groupby(['sample', 'year'], observed=True):
        row = {'pair': SELECTED_PAIR, 'config': EQUITY_CONFIG_NAME, 'sample': sample, 'year': year}
        row.update(performance_stats(g).to_dict())
        yearly_rows.append(row)
    yearly_stats = pd.DataFrame(yearly_rows)
    display(yearly_stats.round(4))

    fig, axes = plt.subplots(2, 2, figsize=(14, 9))
    equity_rows = []
    for sample, color in zip(EQUITY_SAMPLES, ['tab:blue', 'tab:orange']):
        g = account_trades.loc[account_trades['sample'].eq(sample)]
        curve, summary = portfolio_equity(g, STARTING_BALANCE, RISK_PER_TRADE)
        axes[0, 0].plot(curve.time, curve.equity, label=sample, color=color)
        axes[0, 1].plot(curve.time, curve.drawdown, label=sample, color=color)
        sns.histplot(g.net_r, bins=60, stat='density', element='step', fill=False,
                     label=sample, color=color, ax=axes[1, 0])
        session_r = g.groupby(pd.to_datetime(g.session_date)).net_r.sum()
        sns.histplot(session_r, bins=50, stat='density', element='step', fill=False,
                     label=sample, color=color, ax=axes[1, 1])
        equity_rows.append({'pair': SELECTED_PAIR, 'config': EQUITY_CONFIG_NAME,
                            'sample': sample, **summary.to_dict(),
                            **performance_stats(g).to_dict()})
    axes[0, 0].set(title=f'{SELECTED_PAIR} realised equity', ylabel='$')
    axes[0, 1].set(title=f'{SELECTED_PAIR} drawdown', ylabel='fraction')
    axes[1, 0].set(title='Trade return distribution', xlabel='Net R')
    axes[1, 1].set(title='Active-session return distribution', xlabel='Summed net R')
    for ax in axes.flat: ax.legend()
    plt.tight_layout()
    display(pd.DataFrame(equity_rows).round(4))
    """),
    md(r"""
    ## 9. Optional export

    Exports remain pre-2024. The selected-pair account and cross-pair diagnostics are separate files.
    """),
    code(r"""
    EXPORT_RESULTS = False
    if EXPORT_RESULTS:
        out = PROJECT_ROOT / 'outputs'
        out.mkdir(exist_ok=True)
        trades.to_parquet(out / 'bollinger_reentry_trades_pre2024.parquet', index=False)
        stats.to_csv(out / 'bollinger_reentry_statistics_pre2024.csv', index=False)
        account_trades.to_parquet(out / f'{SELECTED_PAIR}_account_trades_pre2024.parquet', index=False)
        yearly_stats.to_csv(out / f'{SELECTED_PAIR}_yearly_metrics_pre2024.csv', index=False)
        entry_diagnostic.to_csv(out / 'bollinger_reentry_entry_information_pre2024.csv', index=False)
        gap_trade_stats.to_csv(out / 'bollinger_reentry_gap_diagnostics_pre2024.csv', index=False)
        regime_stats.to_csv(out / f'{SELECTED_PAIR}_rv_regimes_pre2024.csv', index=False)
        coverage.to_csv(out / 'bollinger_reentry_feature_coverage_pre2024.csv', index=False)
        quality.to_csv(out / 'bollinger_reentry_data_quality_pre2024.csv')
        print('Wrote:', out)
    """),
    md(r"""
    ## Interpretation checklist

    - Read the stop-free fixed-horizon table before the bracketed strategy.
    - Require gross expectancy to exceed plausible costs; a negative cost-stressed fade is not saved
      by a high hit rate.
    - Compare RV gates with deeper outer-band thresholds at matched trade frequency before calling a
      gate informative.
    - Treat the rollover table as post-hoc diagnosis, not a permission to delete losing gap trades.
    - Four USD pairs are correlated evidence. Require pair-level agreement but do not count them as
      four independent tests.
    - Do not open 2024+ until one configuration, primary metric, and kill rule are frozen.
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
