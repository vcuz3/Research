"""Build a standalone pre-2024 TSI versus RSI mean-reversion notebook."""

import json
import textwrap
from pathlib import Path


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "tsi_vs_rsi_mean_reversion.ipynb"


def md(source):
    return {"cell_type": "markdown", "metadata": {}, "source": textwrap.dedent(source).strip().splitlines(True)}


def code(source):
    return {
        "cell_type": "code",
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": textwrap.dedent(source).strip().splitlines(True),
    }


cells = [
    md(r"""
    # True Strength Index versus RSI: short-horizon FX mean reversion

    This notebook asks whether William Blau's **True Strength Index (TSI)** contains the same short-horizon
    mean-reversion information previously found in close/Wilder RSI, and whether it adds anything economically or
    statistically useful.

    TSI double-smooths one-period close changes and their absolute values:

    \[
    TSI_t = 100\frac{EMA_s(EMA_r(\Delta C_t))}{EMA_s(EMA_r(|\Delta C_t|))}.
    \]

    Blau introduced TSI in *Technical Analysis of Stocks & Commodities* in November 1991. The canonical charting
    convention is `r=25`, `s=13`; a separate 7-to-12/13-period EMA is often plotted as a signal line. The signal line
    is deliberately excluded here because the question is about **extremes**, not crossover trend signals.

    Sources: [Traders' archive: William Blau](https://technical.traders.com/archive/combo/display5.asp?author=William+Blau),
    [Traders' glossary definition](https://traders.com/documentation/resource_docs/glossary/glossary_tz.html),
    [StockCharts calculation guide](https://chartschool.stockcharts.com/table-of-contents/technical-indicators-and-overlays/technical-indicators/true-strength-index),
    and [TradingView indicator notes](https://www.tradingview.com/support/solutions/43000592290-true-strength-index/).

    ## Research status and causal clock

    - Pairs: EURUSD and GBPUSD midpoint OHLC, one-minute bars.
    - Decision: completed bars at `:29` and `:59`; entry is the **next minute open**.
    - Exit: exact future open, 5/15/30/60/120 minutes after entry.
    - Discovery: 2012-2020. The 2021-2023 interval is already exposed and is only an internal robustness check.
    - Rows from 2024 onward are not retained or scored.
    - Per-signal mean is the economic estimand; inference clusters by New-York 17:00-to-17:00 session.
    - All P&L is gross midpoint P&L. Cost tables are hypothetical, not executable spread estimates.

    **Prespecified comparison / kill test.** Compare canonical TSI(25,13) with the pre-existing RSI(14) baseline.
    TSI is not an improvement if it fails to raise matched-frequency gross mean P&L and incremental within-slot rank
    information, or if any apparent benefit disappears under a one-minute feature lag or modest cost stress. This is
    exploratory research on consumed history, not a candidate approval or holdout test.
    """),
    code(r"""
    from pathlib import Path
    import os
    import warnings

    import numpy as np
    import pandas as pd
    import matplotlib
    matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    import seaborn as sns
    from scipy.signal import lfilter
    from scipy.stats import spearmanr
    from IPython.display import display

    warnings.filterwarnings('ignore', category=RuntimeWarning)
    pd.set_option('display.max_columns', 100)
    pd.set_option('display.width', 180)
    sns.set_theme(style='whitegrid')

    PROJECT_DIR = Path.cwd()
    if not (PROJECT_DIR / 'forex' / 'data').exists():
        PROJECT_DIR = Path.cwd().resolve().parents[1]
    DATA_DIR = PROJECT_DIR / 'forex' / 'data'

    PAIRS = ['EURUSD', 'GBPUSD']
    HOLDOUT_START = pd.Timestamp('2024-01-01', tz='UTC')
    DISCOVERY_START = pd.Timestamp('2012-01-01', tz='UTC')
    ERA_SPLIT = pd.Timestamp('2021-01-01', tz='UTC')
    HORIZONS = [5, 15, 30, 60, 120]
    RSI_LENGTHS = [7, 14, 21, 28]
    TSI_CONFIGS = [(13, 7), (25, 13), (40, 20)]
    PRIMARY_HORIZON = 30
    DECISION_INTERVAL_MIN = 30
    RSI_LOW, RSI_HIGH = 30.0, 70.0
    TSI_FIXED_THRESHOLD = 25.0
    COST_PIPS = [0.0, 0.25, 0.50, 1.00]
    NULL_DRAWS = 100
    CSV_CHUNK_ROWS = 750_000

    SMOKE_MODE = os.getenv('TSI_RSI_SMOKE', '0') == '1'
    SKIP_NULL = os.getenv('TSI_RSI_SKIP_NULL', '0') == '1'
    if SMOKE_MODE:
        PAIRS = ['EURUSD']
        HORIZONS = [5, 30]
        RSI_LENGTHS = [14]
        TSI_CONFIGS = [(13, 7), (25, 13)]
        NULL_DRAWS = 5

    print(f'Pairs={PAIRS}; horizons={HORIZONS}; RSI lengths={RSI_LENGTHS}; TSI configs={TSI_CONFIGS}')
    print('HOLDOUT POLICY: no row dated 2024 or later is retained or scored.')
    """),
    md(r"""
    ## 1. Data load, indicator construction, and quality gates

    Gaps start a new indicator segment. RSI uses the same SMA-seeded Wilder recursion as the existing RSI notebooks.
    Each TSI EMA is also SMA-seeded; after a gap, the long EMA and then the short EMA pay their full causal warm-up.
    This can differ slightly from chart packages that initialize an EMA from its first observation, so the initialization
    rule is explicit rather than silently assumed.
    """),
    code(r"""
    def load_pre_holdout(pair):
        path = DATA_DIR / f'{pair.lower()}_intraday_1min.csv'
        dtype = {c: 'float32' for c in ['open', 'high', 'low', 'close', 'volume']}
        kept, boundary = [], False
        previous = None
        duplicates = out_of_order = 0
        for chunk in pd.read_csv(path, dtype=dtype, parse_dates=['time'], chunksize=CSV_CHUNK_ROWS):
            chunk['time'] = (chunk.time.dt.tz_localize('UTC') if chunk.time.dt.tz is None
                             else chunk.time.dt.tz_convert('UTC'))
            duplicates += int(chunk.time.duplicated().sum())
            out_of_order += int((chunk.time.diff().dropna() <= pd.Timedelta(0)).sum())
            if previous is not None and len(chunk) and chunk.time.iloc[0] <= previous:
                out_of_order += 1
            if len(chunk):
                previous = chunk.time.iloc[-1]
            before = chunk.loc[chunk.time < HOLDOUT_START].copy()
            if len(before):
                kept.append(before)
            if chunk.time.ge(HOLDOUT_START).any():
                boundary = True
                break
        raw = pd.concat(kept, ignore_index=True)
        assert len(raw) and raw.time.max() < HOLDOUT_START
        ny = raw.time.dt.tz_convert('America/New_York')
        minute = ny.dt.hour * 60 + ny.dt.minute
        ny_date = ny.dt.tz_localize(None).dt.normalize()
        raw['sdate'] = ny_date + pd.to_timedelta((minute >= 17 * 60).astype(int), unit='D')
        raw['session_minute'] = ((minute - 17 * 60) % 1440).astype('int16')
        raw['utc_minute'] = (raw.time.dt.hour * 60 + raw.time.dt.minute).astype('int16')
        dt = raw.time.diff()
        one_minute = dt.eq(pd.Timedelta(minutes=1)).to_numpy()
        ohlc_bad = ((raw.high < raw[['open', 'close', 'low']].max(axis=1)) |
                    (raw.low > raw[['open', 'close', 'high']].min(axis=1)))
        quality = {
            'pair': pair, 'rows': len(raw), 'first': raw.time.min(), 'last': raw.time.max(),
            'sessions': raw.sdate.nunique(), 'boundary_reached': boundary,
            'duplicates': duplicates, 'out_of_order': out_of_order,
            'gaps_gt_1m': int(dt.gt(pd.Timedelta(minutes=1)).sum()),
            'largest_gap_min': dt.dt.total_seconds().div(60).max(),
            'ohlc_failures': int(ohlc_bad.sum()),
            'nonpositive_rows': int(raw[['open', 'high', 'low', 'close']].le(0).any(axis=1).sum()),
            'volume_minus_one_share': raw.volume.eq(-1).mean(),
        }
        assert duplicates == 0 and out_of_order == 0
        assert quality['ohlc_failures'] == 0 and quality['nonpositive_rows'] == 0
        return raw, one_minute, quality


    def segment_bounds(one_minute):
        starts = np.flatnonzero(~one_minute)
        return starts, np.r_[starts[1:], len(one_minute)]


    def ema_sma_seed(values, starts, ends, length):
        out = np.full(len(values), np.nan, dtype=float)
        alpha = 2.0 / (length + 1.0)
        for start, end in zip(starts, ends):
            x = np.asarray(values[start:end], float)
            finite = np.flatnonzero(np.isfinite(x))
            if len(finite) < length:
                continue
            first = finite[0]
            run = x[first:]
            # A second-stage EMA receives a leading NaN region but is continuous thereafter.
            if len(run) < length or not np.isfinite(run[:length]).all():
                continue
            seed = float(run[:length].mean())
            seed_pos = start + first + length - 1
            out[seed_pos] = seed
            if len(run) > length:
                filtered, _ = lfilter([alpha], [1.0, -(1.0 - alpha)], run[length:], zi=[(1.0-alpha)*seed])
                out[seed_pos + 1:end] = filtered
        return out


    def wilder_rsi(close, one_minute, length):
        starts, ends = segment_bounds(one_minute)
        delta = np.diff(close, prepend=close[0]).astype(float)
        delta[starts] = 0.0
        gains, losses = np.clip(delta, 0, None), np.clip(-delta, 0, None)
        # Wilder alpha=1/n, with an SMA seed.
        def wilder(values):
            out = np.full(len(values), np.nan, dtype=float)
            alpha = 1.0 / length
            for start, end in zip(starts, ends):
                x = values[start:end]
                if len(x) < length: continue
                seed = float(x[:length].mean()); pos = start + length - 1; out[pos] = seed
                if len(x) > length:
                    f, _ = lfilter([alpha], [1.0, -(1.0-alpha)], x[length:], zi=[(1.0-alpha)*seed])
                    out[pos+1:end] = f
            return out
        ag, al = wilder(gains), wilder(losses)
        rs = np.divide(ag, al, out=np.full_like(ag, np.nan), where=al > 0)
        rsi = 100 - 100 / (1 + rs)
        rsi[(al == 0) & (ag == 0)] = 50
        rsi[(al == 0) & (ag > 0)] = 100
        return rsi


    def true_strength_index(close, one_minute, long_length, short_length):
        starts, ends = segment_bounds(one_minute)
        delta = np.diff(close, prepend=close[0]).astype(float)
        delta[starts] = 0.0
        num1 = ema_sma_seed(delta, starts, ends, long_length)
        den1 = ema_sma_seed(np.abs(delta), starts, ends, long_length)
        num2 = ema_sma_seed(num1, starts, ends, short_length)
        den2 = ema_sma_seed(den1, starts, ends, short_length)
        tsi = 100 * np.divide(num2, den2, out=np.full_like(num2, np.nan), where=den2 > 0)
        tsi[(den2 == 0) & np.isfinite(num2)] = 0
        return tsi


    def exact_future(raw, horizon, pip_size):
        entry = raw.open.shift(-1).astype(float)
        exit_ = raw.open.shift(-(horizon + 1)).astype(float)
        exact = (raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1)) &
                 raw.time.shift(-(horizon + 1)).eq(raw.time + pd.Timedelta(minutes=horizon + 1)))
        return ((1e4 * np.log(exit_ / entry)).where(exact), ((exit_ - entry) / pip_size).where(exact))


    def reverse_roll(series, window, op):
        return getattr(series.iloc[::-1].rolling(window, min_periods=window), op)().iloc[::-1]


    def path_excursions(raw, horizon, pip_size):
        entry = raw.open.shift(-1).astype(float)
        exact = (raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1)) &
                 raw.time.shift(-(horizon + 1)).eq(raw.time + pd.Timedelta(minutes=horizon + 1)))
        hi = reverse_roll(raw.high.astype(float).shift(-1), horizon, 'max')
        lo = reverse_roll(raw.low.astype(float).shift(-1), horizon, 'min')
        return pd.DataFrame({'long_mfe_pips': ((hi-entry)/pip_size).where(exact),
                             'long_mae_pips': ((entry-lo)/pip_size).where(exact)})


    def session_cluster_t(values, sessions):
        z = pd.DataFrame({'x': values, 'session': sessions}).dropna()
        n, groups = len(z), z.session.nunique()
        if n < 2 or groups < 2: return np.nan
        mean = z.x.mean()
        scores = (z.x - mean).groupby(z.session).sum()
        se = np.sqrt((groups/(groups-1)) * np.square(scores).sum()) / n
        return mean / se if se > 0 else np.nan


    def within_slot_ic(feature, target, slots):
        z = pd.DataFrame({'f': feature, 'y': target, 'slot': slots}).dropna()
        if len(z) < 3: return np.nan
        rf = z.groupby('slot').f.rank(method='average', pct=True)
        ry = z.groupby('slot').y.rank(method='average', pct=True)
        return rf.corr(ry)
    """),
    code(r"""
    panels, quality_rows, coverage_rows = [], [], []
    for pair in PAIRS:
        print(f'Building {pair} ...', flush=True)
        raw, one_minute, quality = load_pre_holdout(pair)
        pip_size = 0.0001
        close = raw.close.to_numpy(float)
        features = {}
        for length in RSI_LENGTHS:
            features[f'rsi_{length}'] = wilder_rsi(close, one_minute, length)
        for long_length, short_length in TSI_CONFIGS:
            features[f'tsi_{long_length}_{short_length}'] = true_strength_index(
                close, one_minute, long_length, short_length)
        targets = {}
        for horizon in HORIZONS:
            targets[f'ret_bp_h{horizon}'], targets[f'ret_pips_h{horizon}'] = exact_future(raw, horizon, pip_size)
        excursion = path_excursions(raw, PRIMARY_HORIZON, pip_size)
        decision = raw.utc_minute.mod(DECISION_INTERVAL_MIN).eq(DECISION_INTERVAL_MIN-1)
        keep_cols = ['time', 'sdate', 'session_minute', 'utc_minute', 'open', 'high', 'low', 'close']
        panel = raw.loc[decision, keep_cols].copy()
        panel.rename(columns={'time': 'ts_utc'}, inplace=True)
        panel['pair'] = pair
        panel['year'] = panel.ts_utc.dt.year.astype('int16')
        panel['era'] = np.where(panel.ts_utc < ERA_SPLIT, 'discovery_2012_2020', 'check_2021_2023')
        for name, values in features.items(): panel[name] = values[decision.to_numpy()]
        for name, values in targets.items(): panel[name] = values.loc[decision].to_numpy()
        panel['long_mfe_pips'] = excursion.long_mfe_pips.loc[decision].to_numpy()
        panel['long_mae_pips'] = excursion.long_mae_pips.loc[decision].to_numpy()
        panel = panel.loc[panel.ts_utc >= DISCOVERY_START].reset_index(drop=True)
        quality['decisions_retained'] = len(panel)
        quality_rows.append(quality)
        for era, g in panel.groupby('era'):
            for name in list(features) + [f'ret_bp_h{h}' for h in HORIZONS]:
                coverage_rows.append({'pair': pair, 'era': era, 'field': name,
                                      'rows': len(g), 'valid': g[name].notna().sum(),
                                      'coverage': g[name].notna().mean()})
        panels.append(panel)
        del raw, features, targets, excursion

    panel = pd.concat(panels, ignore_index=True)
    raw_quality = pd.DataFrame(quality_rows).set_index('pair')
    feature_target_coverage = pd.DataFrame(coverage_rows)
    display(raw_quality)
    display(feature_target_coverage.pivot_table(index=['pair','era'], columns='field', values='coverage').round(4))
    slot_coverage = (panel.assign(valid=panel[f'ret_bp_h{PRIMARY_HORIZON}'].notna())
                     .groupby(['pair','era','session_minute']).valid.mean().reset_index())
    display(slot_coverage.groupby(['pair','era']).valid.agg(['min','median','max']).round(4))
    assert panel.ts_utc.max() < HOLDOUT_START and not panel.ts_utc.ge(HOLDOUT_START).any()
    """),
    md(r"""
    ## 2. Continuous mean-reversion information

    A negative within-slot Spearman IC means high oscillator readings predict lower future returns and low readings predict
    higher returns. Comparing within the same New-York session minute removes the oscillator's time-of-day distribution.
    The table also reports the fraction of sample years with the expected negative sign.
    """),
    code(r"""
    feature_specs = ([{'indicator':'RSI', 'config':str(n), 'column':f'rsi_{n}'} for n in RSI_LENGTHS] +
                     [{'indicator':'TSI', 'config':f'{a},{b}', 'column':f'tsi_{a}_{b}'} for a,b in TSI_CONFIGS])
    ic_rows = []
    for (pair, era), g in panel.groupby(['pair','era']):
        for spec in feature_specs:
            for horizon in HORIZONS:
                ic = within_slot_ic(g[spec['column']], g[f'ret_bp_h{horizon}'], g.session_minute)
                annual = [within_slot_ic(y[spec['column']], y[f'ret_bp_h{horizon}'], y.session_minute)
                          for _, y in g.groupby('year')]
                ic_rows.append({'pair':pair, 'era':era, **spec, 'horizon':horizon,
                                'n':g[[spec['column'],f'ret_bp_h{horizon}']].dropna().shape[0],
                                'within_slot_ic':ic, 'mean_reversion_ic':-ic,
                                'year_negative_fraction':np.mean(np.asarray(annual) < 0)})
    continuous_ic = pd.DataFrame(ic_rows)
    primary_ic = continuous_ic.loc[((continuous_ic.indicator=='RSI') & (continuous_ic.config=='14')) |
                                   ((continuous_ic.indicator=='TSI') & (continuous_ic.config=='25,13'))]
    display(primary_ic[['pair','era','indicator','config','horizon','n','within_slot_ic',
                        'mean_reversion_ic','year_negative_fraction']].round(4))

    fig, axes = plt.subplots(1, len(PAIRS), figsize=(7*len(PAIRS), 4), squeeze=False)
    for ax, pair in zip(axes.ravel(), PAIRS):
        z = primary_ic.loc[primary_ic.pair.eq(pair)]
        for keys, g in z.groupby(['era','indicator']):
            ax.plot(g.horizon, g.mean_reversion_ic, marker='o', label=' / '.join(keys))
        ax.axhline(0, color='black', lw=.8); ax.set_title(pair); ax.set_xlabel('forward horizon (minutes)')
        ax.set_ylabel('- within-slot Spearman IC'); ax.legend(fontsize=8)
    plt.tight_layout(); plt.show()

    config_summary = (continuous_ic.groupby(['pair','era','indicator','config'])
                      .agg(median_mr_ic=('mean_reversion_ic','median'),
                           worst_mr_ic=('mean_reversion_ic','min'),
                           negative_year_share=('year_negative_fraction','mean')).reset_index())
    display(config_summary.sort_values(['pair','era','median_mr_ic'], ascending=[True,True,False]).round(4))
    """),
    md(r"""
    ## 3. Extreme signals: conventional and matched-frequency comparisons

    Fixed thresholds compare RSI 30/70 with the commonly used TSI ±25 convention. Because those rules can have very different
    turnover, the fairer comparison finds a symmetric `|TSI|` threshold in 2012-2020 that matches RSI(14)'s signal rate for
    each pair. That threshold is then frozen and carried unchanged into 2021-2023.
    """),
    code(r"""
    def score_signal_frame(g, side, horizon=PRIMARY_HORIZON):
        z = g.loc[np.asarray(side) != 0].copy()
        z['side'] = np.asarray(side)[np.asarray(side) != 0]
        z['pnl_pips'] = z.side * z[f'ret_pips_h{horizon}']
        z['pnl_bp'] = z.side * z[f'ret_bp_h{horizon}']
        z['mfe_pips'] = np.where(z.side > 0, z.long_mfe_pips, z.long_mae_pips)
        z['mae_pips'] = np.where(z.side > 0, z.long_mae_pips, z.long_mfe_pips)
        valid = z.pnl_pips.notna()
        z = z.loc[valid]
        return z, {'signals':len(z), 'sessions':z.sdate.nunique(), 'signal_rate':len(z)/max(len(g),1),
                   'mean_pips':z.pnl_pips.mean(), 'cluster_t':session_cluster_t(z.pnl_pips,z.sdate),
                   'win_rate':z.pnl_pips.gt(0).mean(), 'long_share':z.side.gt(0).mean(),
                   'mean_mfe_pips':z.mfe_pips.mean(), 'mean_mae_pips':z.mae_pips.mean(),
                   'mfe_mae_ratio':z.mfe_pips.mean()/z.mae_pips.mean() if z.mae_pips.mean()>0 else np.nan}

    matched_tsi_threshold = {}
    threshold_rows = []
    for pair, g in panel.groupby('pair'):
        early = g.loc[g.era.eq('discovery_2012_2020')]
        rsi_side = np.select([early.rsi_14 <= RSI_LOW, early.rsi_14 >= RSI_HIGH], [1,-1], 0)
        rate = np.mean(rsi_side != 0)
        threshold = early.tsi_25_13.abs().quantile(1-rate)
        matched_tsi_threshold[pair] = threshold
        threshold_rows.append({'pair':pair,'rsi_signal_rate':rate,'matched_abs_tsi_threshold':threshold,
                               'fixed_abs_tsi_threshold':TSI_FIXED_THRESHOLD})
    threshold_calibration = pd.DataFrame(threshold_rows).set_index('pair')
    display(threshold_calibration.round(4))

    edge_rows, signal_frames = [], {}
    for (pair, era), g in panel.groupby(['pair','era']):
        definitions = {
            'RSI14 30/70': np.select([g.rsi_14<=RSI_LOW,g.rsi_14>=RSI_HIGH],[1,-1],0),
            'TSI25,13 fixed ±25': np.select([g.tsi_25_13<=-TSI_FIXED_THRESHOLD,g.tsi_25_13>=TSI_FIXED_THRESHOLD],[1,-1],0),
            'TSI25,13 RSI-rate-matched': np.select([g.tsi_25_13<=-matched_tsi_threshold[pair],
                                                    g.tsi_25_13>=matched_tsi_threshold[pair]],[1,-1],0),
        }
        for label, side in definitions.items():
            for horizon in HORIZONS:
                z, metrics = score_signal_frame(g, side, horizon)
                edge_rows.append({'pair':pair,'era':era,'definition':label,'horizon':horizon,**metrics})
                if horizon == PRIMARY_HORIZON:
                    signal_frames[(pair,era,label)] = z
    edge_summary = pd.DataFrame(edge_rows)
    display(edge_summary.loc[edge_summary.horizon.eq(PRIMARY_HORIZON)].round(4))

    horizon_plot = edge_summary.pivot_table(index=['pair','era','horizon'],columns='definition',values='mean_pips').reset_index()
    display(horizon_plot.round(4))

    cost_rows=[]
    for key,z in signal_frames.items():
        pair,era,label=key
        for cost in COST_PIPS:
            net=z.pnl_pips-cost
            cost_rows.append({'pair':pair,'era':era,'definition':label,'round_trip_cost_pips':cost,
                              'signals':len(net),'mean_net_pips':net.mean(),
                              'cluster_t':session_cluster_t(net,z.sdate),'net_win_rate':net.gt(0).mean()})
    cost_stress=pd.DataFrame(cost_rows)
    display(cost_stress.round(4))
    """),
    md(r"""
    ## 4. Overlap and incremental information

    The overlap table separates occasions when both selected oscillators are extreme from occasions when only one is extreme.
    The partial-rank table asks whether TSI retains within-slot rank information after linearly removing RSI's rank, and vice
    versa. These are descriptive incremental-information tests, not a trading portfolio with overlapping positions.
    """),
    code(r"""
    overlap_rows=[]
    partial_rows=[]
    for (pair,era),g in panel.groupby(['pair','era']):
        rsi_side=np.select([g.rsi_14<=RSI_LOW,g.rsi_14>=RSI_HIGH],[1,-1],0)
        threshold=matched_tsi_threshold[pair]
        tsi_side=np.select([g.tsi_25_13<=-threshold,g.tsi_25_13>=threshold],[1,-1],0)
        categories=np.select([(rsi_side!=0)&(tsi_side!=0)&(rsi_side==tsi_side),
                              (rsi_side!=0)&(tsi_side==0),(rsi_side==0)&(tsi_side!=0),
                              (rsi_side!=0)&(tsi_side!=0)&(rsi_side!=tsi_side)],
                             ['both agree','RSI only','TSI only','conflict'],default='neither')
        for category in ['both agree','RSI only','TSI only','conflict']:
            mask=categories==category
            if not mask.any(): continue
            side=np.where(mask,np.where(rsi_side!=0,rsi_side,tsi_side),0)
            _,metrics=score_signal_frame(g,side,PRIMARY_HORIZON)
            overlap_rows.append({'pair':pair,'era':era,'category':category,**metrics})
        for horizon in HORIZONS:
            z=g[['rsi_14','tsi_25_13','session_minute',f'ret_bp_h{horizon}']].dropna().copy()
            z['rsi_rank']=z.groupby('session_minute').rsi_14.rank(pct=True)
            z['tsi_rank']=z.groupby('session_minute').tsi_25_13.rank(pct=True)
            z['ret_rank']=z.groupby('session_minute')[f'ret_bp_h{horizon}'].rank(pct=True)
            def residual(y,x):
                xv=x.to_numpy(); yv=y.to_numpy(); return yv-np.polyval(np.polyfit(xv,yv,1),xv)
            tsi_res=residual(z.tsi_rank,z.rsi_rank); ret_res_rsi=residual(z.ret_rank,z.rsi_rank)
            rsi_res=residual(z.rsi_rank,z.tsi_rank); ret_res_tsi=residual(z.ret_rank,z.tsi_rank)
            partial_rows.append({'pair':pair,'era':era,'horizon':horizon,
                                 'TSI_partial_IC_given_RSI':np.corrcoef(tsi_res,ret_res_rsi)[0,1],
                                 'RSI_partial_IC_given_TSI':np.corrcoef(rsi_res,ret_res_tsi)[0,1]})
    overlap_table=pd.DataFrame(overlap_rows)
    partial_ic=pd.DataFrame(partial_rows)
    display(overlap_table.round(4))
    display(partial_ic.round(4))
    """),
    md(r"""
    ## 5. Timing sensitivity

    The oscillator is observed at the decision close, one minute earlier, and five minutes earlier while the same next-open
    target is retained. This directly tests whether the signal survives a small delay rather than sharing the final signal-bar
    move. TSI uses the discovery-calibrated threshold at every lag; it is not re-tuned after seeing lagged outcomes.
    """),
    md(r"""
    **Implementation note for timing:** the next cell rebuilds only the six selected lagged feature columns from raw minute
    data and merges them by exact timestamp. It prevents the 30-minute decision table's `.shift(1)` from being mistaken for a
    one-minute lag. The timing summary is then recomputed correctly.
    """),
    code(r"""
    lag_frames=[]
    for pair in PAIRS:
        raw,one_minute,_=load_pre_holdout(pair)
        close=raw.close.to_numpy(float)
        selected={'rsi_14':wilder_rsi(close,one_minute,14),
                  'tsi_25_13':true_strength_index(close,one_minute,25,13)}
        out=pd.DataFrame({'ts_utc':raw.time})
        for name,values in selected.items():
            s=pd.Series(values,index=raw.index)
            for lag in [0,1,5]:
                v=s.shift(lag).where(raw.time.shift(lag).eq(raw.time-pd.Timedelta(minutes=lag))) if lag else s
                out[f'{name}_lag{lag}']=v
        decision=raw.utc_minute.mod(DECISION_INTERVAL_MIN).eq(DECISION_INTERVAL_MIN-1)
        out=out.loc[decision & raw.time.ge(DISCOVERY_START)].copy(); out['pair']=pair
        lag_frames.append(out)
        del raw,selected
    lag_features=pd.concat(lag_frames,ignore_index=True)
    panel=panel.merge(lag_features,on=['pair','ts_utc'],how='left',validate='one_to_one')

    timing_rows=[]
    for (pair,era),g in panel.groupby(['pair','era']):
        for lag in [0,1,5]:
            rsi=g[f'rsi_14_lag{lag}']; tsi=g[f'tsi_25_13_lag{lag}']; threshold=matched_tsi_threshold[pair]
            for indicator,side in [('RSI',np.select([rsi<=RSI_LOW,rsi>=RSI_HIGH],[1,-1],0)),
                                   ('TSI',np.select([tsi<=-threshold,tsi>=threshold],[1,-1],0))]:
                _,metrics=score_signal_frame(g,side,PRIMARY_HORIZON)
                timing_rows.append({'pair':pair,'era':era,'indicator':indicator,'lag_min':lag,**metrics})
    timing_sensitivity=pd.DataFrame(timing_rows)
    display(timing_sensitivity.round(4))
    """),
    md(r"""
    ## 6. Claim-matched session re-pairing null

    For the primary 2012-2020, 30-minute matched-frequency comparison, each draw reassigns complete outcome sessions to
    different sessions **within the same pair and year**, while matching the same minute-of-session. It preserves each outcome
    session's intraday return pattern and both indicators' signal paths, but destroys their same-session alignment. The null is
    run through both signal rules and retains the TSI-minus-RSI difference. This is a selected-definition null, not a correction
    for every exploratory table in the notebook.
    """),
    code(r"""
    def repair_outcomes(g,rng):
        mapping=[]
        for year,y in g.groupby('year'):
            sessions=np.sort(y.sdate.unique())
            donors=rng.permutation(sessions)
            mapping.extend(zip(sessions,donors))
        m=pd.DataFrame(mapping,columns=['sdate','donor_sdate'])
        donor=g[['sdate','session_minute',f'ret_pips_h{PRIMARY_HORIZON}']].rename(
            columns={'sdate':'donor_sdate',f'ret_pips_h{PRIMARY_HORIZON}':'null_return'})
        return (g[['sdate','session_minute']].merge(m,on='sdate',how='left')
                .merge(donor,on=['donor_sdate','session_minute'],how='left').null_return.to_numpy())

    null_rows=[]; rng=np.random.default_rng(20260802)
    if not SKIP_NULL:
        for pair,g0 in panel.loc[panel.era.eq('discovery_2012_2020')].groupby('pair'):
            g=g0.sort_values(['sdate','session_minute']).reset_index(drop=True)
            rsi_side=np.select([g.rsi_14<=RSI_LOW,g.rsi_14>=RSI_HIGH],[1,-1],0)
            threshold=matched_tsi_threshold[pair]
            tsi_side=np.select([g.tsi_25_13<=-threshold,g.tsi_25_13>=threshold],[1,-1],0)
            observed_rsi=np.nanmean(np.where(rsi_side!=0,rsi_side*g[f'ret_pips_h{PRIMARY_HORIZON}'],np.nan))
            observed_tsi=np.nanmean(np.where(tsi_side!=0,tsi_side*g[f'ret_pips_h{PRIMARY_HORIZON}'],np.nan))
            null_rsi=[]; null_tsi=[]
            for draw in range(NULL_DRAWS):
                y=repair_outcomes(g,rng)
                null_rsi.append(np.nanmean(np.where(rsi_side!=0,rsi_side*y,np.nan)))
                null_tsi.append(np.nanmean(np.where(tsi_side!=0,tsi_side*y,np.nan)))
            null_rsi=np.asarray(null_rsi); null_tsi=np.asarray(null_tsi); null_delta=null_tsi-null_rsi
            observed_delta=observed_tsi-observed_rsi
            null_rows.append({'pair':pair,'draws':NULL_DRAWS,'observed_rsi_pips':observed_rsi,
                              'observed_tsi_pips':observed_tsi,'observed_tsi_minus_rsi':observed_delta,
                              'null_tsi_mean':null_tsi.mean(),'null_tsi_p95':np.quantile(null_tsi,.95),
                              'tsi_one_sided_p':(1+np.sum(null_tsi>=observed_tsi))/(1+NULL_DRAWS),
                              'null_delta_mean':null_delta.mean(),
                              'null_delta_p05':np.quantile(null_delta,.05),'null_delta_p95':np.quantile(null_delta,.95),
                              'delta_two_sided_p':(1+np.sum(np.abs(null_delta)>=abs(observed_delta)))/(1+NULL_DRAWS)})
        selection_null=pd.DataFrame(null_rows)
        display(selection_null.round(4))
    else:
        selection_null=pd.DataFrame(); print('Null skipped by TSI_RSI_SKIP_NULL=1.')
    """),
    md(r"""
    ## Executed findings (2026-08-02)

    The full EURUSD/GBPUSD run supports a **NO-GO on TSI as a replacement for, or additive improvement to, RSI**:

    - Canonical TSI(25,13) has negative within-slot IC at every 5-120 minute horizon and in every sample year, so it does
      contain mean-reversion information. It is consistently weaker than RSI(14): at 30 minutes the discovery mean-reversion
      IC is 0.0509/0.0534 for TSI versus 0.0681/0.0719 for RSI (EURUSD/GBPUSD).
    - Fixed +/-25 TSI fires about twice as often as RSI 30/70. Matching discovery signal frequency requires |TSI| thresholds
      32.60 EURUSD and 32.43 GBPUSD. At that matched frequency, discovery gross return is only 0.192/0.141 pips per TSI signal
      versus 0.646/0.637 for RSI; the exposed 2021-2023 check is 0.331/0.365 versus 0.695/0.679.
    - TSI-only extremes lose slightly in discovery (-0.039/-0.119 pips), while RSI-only extremes earn 0.935/0.984 pips.
      TSI partial IC after removing RSI is usually positive (the wrong sign for reversion); RSI partial IC after removing TSI
      remains negative at every pair, era, and horizon.
    - TSI is not more delay-robust in an economically useful way. A one-minute lag leaves discovery TSI at +0.154 pips on
      EURUSD and -0.021 on GBPUSD; five minutes leaves +0.017 and -0.085. At a hypothetical 0.50-pip round trip, matched TSI
      is negative in both eras and pairs.
    - In 100 within-year session re-pairings, selected TSI's one-sided p-values are 0.059 EURUSD and 0.109 GBPUSD. The observed
      TSI-minus-RSI disadvantage (-0.454/-0.496 pips) is more extreme than every null draw in absolute value (Monte Carlo
      two-sided p floor 1/101). This supports the relative conclusion: extra double smoothing discards useful fast-reversal
      information rather than adding an independent signal.

    This remains exploratory, gross-midpoint evidence on consumed pre-2024 history. It does not upgrade RSI to a tradable edge.
    """),
    md(r"""
    ## 7. Reading the evidence

    Use the continuous IC table to decide whether TSI carries mean-reversion information at all. Use the matched-frequency
    signal table—not fixed ±25 alone—to compare economics with RSI. Then check partial IC, one/five-minute lag sensitivity,
    MFE/MAE, hypothetical costs, and the re-pairing null.

    A positive gross midpoint result does not establish a tradable edge. These one-minute files contain no executable bid/ask
    quotes, both pairs are correlated USD markets, and all pre-2024 history shown here is consumed exploratory evidence.
    """),
    code(r"""
    # Compact machine-readable handoff and hard holdout assertions.
    primary_edges=edge_summary.loc[edge_summary.horizon.eq(PRIMARY_HORIZON)].copy()
    comparison=(primary_edges.pivot_table(index=['pair','era'],columns='definition',values='mean_pips').reset_index())
    print('30-minute gross mean comparison (pips per signal):')
    display(comparison.round(4))
    print('Incremental rank information (negative values imply incremental mean reversion):')
    display(partial_ic.round(4))

    research_tables={'raw_quality':raw_quality,'feature_target_coverage':feature_target_coverage,
                     'continuous_ic':continuous_ic,'threshold_calibration':threshold_calibration,
                     'edge_summary':edge_summary,'cost_stress':cost_stress,'overlap_table':overlap_table,
                     'partial_ic':partial_ic,'timing_sensitivity':timing_sensitivity,
                     'selection_null':selection_null,'comparison':comparison}
    assert panel.ts_utc.max()<HOLDOUT_START
    assert not panel.ts_utc.ge(HOLDOUT_START).any()
    assert raw_quality.duplicates.eq(0).all() and raw_quality.out_of_order.eq(0).all()
    print(f'Complete: {len(panel):,} decision rows; max timestamp={panel.ts_utc.max()}')
    print('FINAL HOLDOUT CHECK PASSED: every retained feature, target, and scored row is strictly pre-2024.')
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
print(f"Wrote {OUT}")
