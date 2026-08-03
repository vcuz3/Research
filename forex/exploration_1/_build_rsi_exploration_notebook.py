"""Build the standalone FX RSI parameter and edge exploration notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "rsi_parameter_exploration.ipynb"


def md(text: str):
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("markdown\0" + source).encode()).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(text: str):
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "code",
        "id": hashlib.sha1(("code\0" + source).encode()).hexdigest()[:12],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


cells = [
    md(
        r"""
        # FX RSI parameter, horizon, and mean-reversion edge exploration

        This notebook investigates one configurable FX pair using one-minute midpoint OHLC. It compares:

        - RSI lengths;
        - Wilder/RMA, EMA, and SMA gain/loss smoothing;
        - close versus `(open + high + low) / 3` calculation sources;
        - multiple next-open-to-exact-open prediction horizons;
        - continuous signed-return IC and explicit oversold-long / overbought-short edge rules.

        Outcomes include endpoint log-basis-point return, raw pips, absolute return, long/short maximum favorable excursion
        (MFE), maximum adverse excursion (MAE), capture/giveback, tail loss, and touch rates. Features use only completed-bar
        information; entry is the next minute's open. Holding-path extrema are labels, not inputs.

        ## Research status and boundaries

        This is a searched exploratory grid, not a confirmatory strategy test. The default discovery period is 2012–2019.
        A selected configuration can be checked on 2020–2023, but that interval has already been exposed elsewhere in this
        project and is not a pristine holdout. Rows from 2024 onward are never retained or scored. Any survivor must be frozen,
        tested with a claim-matched null and executable costs, and only then evaluated on the 2024+ holdout.

        Midpoint bars contain no executable bid/ask spread. All P&L-like outputs are gross diagnostics. If a stop and target
        are both touched inside a one-minute bar, their order is unknown; MFE/MAE do not resolve that ambiguity.
        """
    ),
    code(
        r"""
        from pathlib import Path
        import gc
        import os
        import warnings

        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns
        from IPython.display import display
        from scipy.signal import lfilter
        from scipy.stats import norm, spearmanr

        warnings.filterwarnings('ignore', category=FutureWarning)
        sns.set_theme(style='whitegrid', context='notebook')
        pd.set_option('display.max_columns', 200)
        pd.set_option('display.width', 240)

        # ----------------------------- pair and periods ----------------------------
        PAIR = 'EURUSD'  # EURUSD, GBPUSD, AUDUSD, or NZDUSD
        HOLDOUT_START = pd.Timestamp('2024-01-01', tz='UTC')

        # Grid selection uses only this interval. Endpoints are [start, end).
        IN_SAMPLE_START = pd.Timestamp('2012-01-01', tz='UTC')
        IN_SAMPLE_END_EXCLUSIVE = pd.Timestamp('2020-01-01', tz='UTC')

        # Internal check after selecting on the in-sample interval. Already exposed;
        # useful for temporal stability, but not a pristine holdout.
        PRE_HOLDOUT_CHECK_START = pd.Timestamp('2020-01-01', tz='UTC')
        PRE_HOLDOUT_CHECK_END_EXCLUSIVE = HOLDOUT_START
        RUN_PRE_HOLDOUT_CHECK = True
        # --------------------------------------------------------------------------

        # ------------------------------- RSI grid ---------------------------------
        RSI_LENGTHS = [5, 7, 10, 14, 21, 28, 50]
        RSI_SMOOTHERS = ['wilder', 'ema', 'sma']
        RSI_SOURCES = ['close', 'ohl3']  # ohl3 is exactly (open + high + low) / 3
        PREDICTION_WINDOWS_MIN = [5, 15, 30, 60, 120]
        DECISION_INTERVAL_MIN = 30
        FEATURE_TIMING_LAGS_MIN = [0, 1, 5]

        EDGE_ORIENTATION = 'mean_reversion'
        EDGE_LOW_THRESHOLD = 30.0
        EDGE_HIGH_THRESHOLD = 70.0
        THRESHOLD_LOW_GRID = [20.0, 25.0, 30.0, 35.0, 40.0]

        # None means select the highest in-sample mean-reversion IC from the grid.
        # To freeze a choice, use e.g. {'source':'close','smoother':'wilder','length':14,'horizon':30}.
        MANUAL_SELECTED_CONFIG = None
        SELECTION_PRIMARY_METRIC = 'mean_reversion_ic'
        MIN_SELECTED_SIGNALS = 500
        MIN_YEARLY_EXPECTED_SIGN_FRACTION = 0.60

        BOOTSTRAP_DRAWS = 300
        RANDOM_SEED = 20260802
        CSV_CHUNK_ROWS = 750_000
        TOUCH_LEVELS_PIPS = [2.0, 5.0, 10.0, 15.0]
        HYPOTHETICAL_ROUND_TRIP_COST_PIPS = [0.0, 0.25, 0.50, 1.00, 1.50]
        # --------------------------------------------------------------------------

        SMOKE_MODE = os.getenv('RSI_EXPLORATION_SMOKE', '0') == '1'
        PAIR = os.getenv('RSI_EXPLORATION_PAIR', PAIR).upper()
        if SMOKE_MODE:
            RSI_LENGTHS = [7, 14]
            PREDICTION_WINDOWS_MIN = [15, 30]
            BOOTSTRAP_DRAWS = 40
        SKIP_BOOTSTRAP = os.getenv('RSI_EXPLORATION_SKIP_BOOTSTRAP', '0') == '1'

        assert PAIR in {'EURUSD','GBPUSD','AUDUSD','NZDUSD'}
        assert set(RSI_SMOOTHERS) <= {'wilder','ema','sma'}
        assert set(RSI_SOURCES) <= {'close','ohl3','hlc3','ohlc4'}
        assert 1440 % DECISION_INTERVAL_MIN == 0
        assert IN_SAMPLE_START < IN_SAMPLE_END_EXCLUSIVE <= PRE_HOLDOUT_CHECK_START
        assert PRE_HOLDOUT_CHECK_START < PRE_HOLDOUT_CHECK_END_EXCLUSIVE <= HOLDOUT_START

        here = Path.cwd().resolve()
        if here.name == 'exploration_1':
            project_root = here
        elif (here / 'forex' / 'exploration_1').exists():
            project_root = here / 'forex' / 'exploration_1'
        else:
            raise FileNotFoundError('Run from the workspace root or forex/exploration_1.')
        data_dir = project_root.parent / 'data'
        pip_size = 0.01 if PAIR.endswith('JPY') else 0.0001

        print(f'Pair={PAIR}; RSI configs={len(RSI_LENGTHS)*len(RSI_SMOOTHERS)*len(RSI_SOURCES)}; '
              f'horizons={PREDICTION_WINDOWS_MIN}; decision interval={DECISION_INTERVAL_MIN}m')
        print(f'In-sample: [{IN_SAMPLE_START}, {IN_SAMPLE_END_EXCLUSIVE}); '
              f'pre-holdout check: [{PRE_HOLDOUT_CHECK_START}, {PRE_HOLDOUT_CHECK_END_EXCLUSIVE})')
        print(f'Holdout seal: no row at or after {HOLDOUT_START} is retained.')
        """
    ),
    md(
        r"""
        ## 1. Load pre-holdout data and run the raw quality gate

        The chronological CSV is read in chunks and stopped as soon as the 2024 boundary is reached. The gate reports duplicates,
        timestamp ordering, gaps, OHLC validity, flat bars, and the unusable volume field. New-York 17:00 defines the FX session.
        A gap starts a new RSI calculation segment; no return is silently stretched across missing time.
        """
    ),
    code(
        r"""
        def load_pre_holdout(pair):
            path = data_dir / f'{pair.lower()}_intraday_1min.csv'
            assert path.exists(), f'Missing {path}'
            dtype = {c:'float32' for c in ['open','high','low','close','volume']}
            kept, reached_boundary = [], False
            source_duplicate_ts = source_out_of_order = 0
            previous_last = None
            for chunk in pd.read_csv(path, dtype=dtype, parse_dates=['time'], chunksize=CSV_CHUNK_ROWS):
                if chunk.time.dt.tz is None:
                    chunk['time'] = chunk.time.dt.tz_localize('UTC')
                else:
                    chunk['time'] = chunk.time.dt.tz_convert('UTC')
                source_duplicate_ts += int(chunk.time.duplicated().sum())
                source_out_of_order += int((chunk.time.diff().dropna() <= pd.Timedelta(0)).sum())
                if previous_last is not None and len(chunk) and chunk.time.iloc[0] <= previous_last:
                    source_out_of_order += 1
                if len(chunk):
                    previous_last = chunk.time.iloc[-1]
                before = chunk.loc[chunk.time < HOLDOUT_START].copy()
                if len(before):
                    kept.append(before)
                if chunk.time.ge(HOLDOUT_START).any():
                    reached_boundary = True
                    break
            raw = pd.concat(kept, ignore_index=True)
            assert len(raw) and raw.time.max() < HOLDOUT_START
            assert source_duplicate_ts == 0 and source_out_of_order == 0

            ny = raw.time.dt.tz_convert('America/New_York')
            ny_minute = ny.dt.hour * 60 + ny.dt.minute
            ny_date = ny.dt.tz_localize(None).dt.normalize()
            raw['sdate'] = ny_date + pd.to_timedelta((ny_minute >= 17*60).astype(int),unit='D')
            raw['session_minute'] = ((ny_minute - 17*60) % 1440).astype('int16')
            raw['utc_minute'] = (raw.time.dt.hour * 60 + raw.time.dt.minute).astype('int16')

            dt = raw.time.diff()
            one_minute = dt.eq(pd.Timedelta(minutes=1))
            ohlc_failure = ((raw.low > raw[['open','close']].min(axis=1)) |
                            (raw.high < raw[['open','close']].max(axis=1)) |
                            (raw.high < raw.low)).sum()
            quality = pd.Series({
                'file_gb':path.stat().st_size/1e9,'rows':len(raw),'first':raw.time.min(),'last_retained':raw.time.max(),
                'sessions':raw.sdate.nunique(),'boundary_reached':reached_boundary,
                'duplicate_ts':source_duplicate_ts,'out_of_order_ts':source_out_of_order,
                'one_minute_links':int(one_minute.sum()),'gaps_gt_1m':int(dt.gt(pd.Timedelta(minutes=1)).sum()),
                'largest_gap_min':dt.dt.total_seconds().div(60).max(),
                'nonpositive_price_rows':int(raw[['open','high','low','close']].le(0).any(axis=1).sum()),
                'ohlc_invariant_failures':int(ohlc_failure),
                'flat_ohlc_rows':int(raw[['open','high','low','close']].nunique(axis=1).eq(1).sum()),
                'volume_minus_one_share':float(raw.volume.eq(-1).mean()),
                'volume_distinct_values':int(raw.volume.nunique(dropna=False)),
            })
            assert quality.nonpositive_price_rows == 0 and quality.ohlc_invariant_failures == 0
            return raw, one_minute, quality

        raw, one_minute_link, raw_quality = load_pre_holdout(PAIR)
        display(raw_quality.to_frame('value'))
        yearly_coverage = raw.groupby(raw.time.dt.year).agg(
            rows=('time','size'),sessions=('sdate','nunique'),first=('time','min'),last=('time','max'))
        display(yearly_coverage)
        """
    ),
    md(
        r"""
        ## 2. RSI construction grid

        RSI is computed from source-price changes on uninterrupted one-minute segments. All smoothers use the same first valid
        seed: the simple mean of the first `length` gains and losses in a segment. Thereafter:

        - **Wilder/RMA:** `alpha = 1 / length`;
        - **EMA:** `alpha = 2 / (length + 1)`;
        - **SMA:** a trailing simple mean over `length` observations.

        This isolates the smoothing recurrence rather than confounding it with a different seed. The first observation after a
        gap has zero gain and loss and every configuration pays its full warm-up again. RSI is available only at the completed
        decision bar. Timing-placebo copies at one and five minutes earlier are retained for the selected-configuration audit.
        """
    ),
    code(
        r"""
        def sma_by_segments(values, starts, ends, length):
            out = np.full(len(values), np.nan, dtype=float)
            for start, end in zip(starts, ends):
                x = values[start:end]
                if len(x) < length:
                    continue
                cs = np.concatenate(([0.0], np.cumsum(x, dtype=float)))
                out[start + length - 1:end] = (cs[length:] - cs[:-length]) / length
            return out


        def recursive_sma_seeded(values, starts, ends, length, alpha):
            out = np.full(len(values), np.nan, dtype=float)
            for start, end in zip(starts, ends):
                x = values[start:end]
                if len(x) < length:
                    continue
                seed = float(np.mean(x[:length]))
                seed_index = start + length - 1
                out[seed_index] = seed
                if len(x) > length:
                    filtered, _ = lfilter([alpha], [1.0, -(1.0-alpha)], x[length:], zi=[(1.0-alpha)*seed])
                    out[seed_index + 1:end] = filtered
            return out


        def calculate_rsi(source, length, smoother, starts, ends):
            delta = np.diff(source, prepend=source[0])
            delta[starts] = 0.0
            gains = np.clip(delta, 0, None)
            losses = np.clip(-delta, 0, None)
            if smoother == 'sma':
                avg_gain = sma_by_segments(gains, starts, ends, length)
                avg_loss = sma_by_segments(losses, starts, ends, length)
            else:
                alpha = 1.0/length if smoother == 'wilder' else 2.0/(length+1.0)
                avg_gain = recursive_sma_seeded(gains, starts, ends, length, alpha)
                avg_loss = recursive_sma_seeded(losses, starts, ends, length, alpha)
            rs = np.divide(avg_gain, avg_loss, out=np.full_like(avg_gain,np.nan), where=avg_loss>0)
            rsi = 100.0 - 100.0/(1.0+rs)
            rsi[(avg_loss == 0) & (avg_gain == 0)] = 50.0
            rsi[(avg_loss == 0) & (avg_gain > 0)] = 100.0
            return rsi


        source_arrays = {
            'close':raw.close.to_numpy(float),
            'ohl3':raw[['open','high','low']].mean(axis=1).to_numpy(float),
            'hlc3':raw[['high','low','close']].mean(axis=1).to_numpy(float),
            'ohlc4':raw[['open','high','low','close']].mean(axis=1).to_numpy(float),
        }
        segment_start_mask = ~one_minute_link.to_numpy()
        segment_starts = np.flatnonzero(segment_start_mask)
        segment_ends = np.r_[segment_starts[1:], len(raw)]

        decision_mask = raw.utc_minute.mod(DECISION_INTERVAL_MIN).eq(DECISION_INTERVAL_MIN-1).to_numpy()
        decision_positions = np.flatnonzero(decision_mask)
        base_decisions = raw.loc[decision_mask,['time','sdate','session_minute','utc_minute','open','high','low','close']].copy()
        base_decisions = base_decisions.rename(columns={'time':'ts_utc'}).reset_index(drop=True)
        base_decisions['year'] = base_decisions.ts_utc.dt.year

        london = base_decisions.ts_utc.dt.tz_convert('Europe/London')
        newyork = base_decisions.ts_utc.dt.tz_convert('America/New_York')
        tokyo = base_decisions.ts_utc.dt.tz_convert('Asia/Tokyo')
        london_open = london.dt.hour.between(8,16)
        newyork_open = newyork.dt.hour.between(8,16)
        tokyo_open = tokyo.dt.hour.between(8,16)
        base_decisions['market_session'] = np.select(
            [london_open & newyork_open,london_open,newyork_open,tokyo_open],
            ['london_ny_overlap','london','new_york','tokyo'],default='other')
        base_decisions['day_of_week'] = base_decisions.ts_utc.dt.day_name().str[:3]

        # Causal state controls for later condition exploration.
        log_close = np.log(raw.close.to_numpy(float))
        ret1 = np.diff(log_close, prepend=np.nan)
        ret1[segment_start_mask] = np.nan
        ret1_series = pd.Series(ret1)
        exact_60 = raw.time.shift(60).eq(raw.time - pd.Timedelta(minutes=60)).to_numpy()
        rv60 = np.sqrt(ret1_series.pow(2).rolling(60,min_periods=60).sum()).where(exact_60)
        past_return60 = pd.Series(log_close) - pd.Series(log_close).shift(60)
        past_return60 = past_return60.where(exact_60)
        travelled60 = ret1_series.abs().rolling(60,min_periods=60).sum().where(exact_60)
        path_eff60 = past_return60.abs()/travelled60.replace(0,np.nan)
        base_decisions['trailing_rv_60_log_bp'] = 1e4*rv60.iloc[decision_positions].to_numpy()
        base_decisions['past_return_60_log_bp'] = 1e4*past_return60.iloc[decision_positions].to_numpy()
        base_decisions['path_efficiency_60'] = path_eff60.iloc[decision_positions].to_numpy()

        rsi_metadata, rsi_at_lag = [], {lag:{} for lag in FEATURE_TIMING_LAGS_MIN}
        for source_name in RSI_SOURCES:
            source = source_arrays[source_name]
            for smoother in RSI_SMOOTHERS:
                for length in RSI_LENGTHS:
                    column = f'rsi__{source_name}__{smoother}__{length}'
                    values = calculate_rsi(source,length,smoother,segment_starts,segment_ends)
                    rsi_metadata.append({'column':column,'source':source_name,'smoother':smoother,'length':length})
                    for lag in FEATURE_TIMING_LAGS_MIN:
                        positions = decision_positions - lag
                        valid = positions >= 0
                        exact = np.zeros(len(positions),dtype=bool)
                        exact[valid] = (raw.time.iloc[positions[valid]].to_numpy() ==
                                        (raw.time.iloc[decision_positions[valid]]-pd.Timedelta(minutes=lag)).to_numpy())
                        taken = np.full(len(positions),np.nan,dtype=np.float32)
                        taken[exact] = values[positions[exact]].astype(np.float32)
                        rsi_at_lag[lag][column] = taken
                    del values
        rsi_metadata = pd.DataFrame(rsi_metadata)
        rsi_at_lag = {lag:pd.DataFrame(values) for lag,values in rsi_at_lag.items()}
        print(f'Built {len(rsi_metadata)} RSI configurations at {len(base_decisions):,} decision times.')
        """
    ),
]

cells.extend([
    md(
        r"""
        ## 3. Multi-horizon endpoint and path targets

        For a decision made after minute `t` closes, every horizon enters at minute `t+1` open and exits at `t+H+1` open.
        Exact timestamp checks reject windows containing a missing minute. Holding extrema cover bars `t+1` through `t+H`
        and explicitly include entry and exit. Log basis points are `10,000 × log(price ratio)`; raw pips use the pair's quote
        convention. Excursions are stored from the long lens; short MFE equals long MAE and short MAE equals long MFE.
        """
    ),
    code(
        r"""
        def reverse_rolling(series, window, operation):
            reversed_series = series.iloc[::-1]
            rolled = getattr(reversed_series.rolling(window,min_periods=window),operation)()
            return rolled.iloc[::-1]


        target_columns = {}
        entry_open = raw.open.shift(-1).astype(float)
        for horizon in PREDICTION_WINDOWS_MIN:
            exit_open = raw.open.shift(-(horizon+1)).astype(float)
            exact = (raw.time.shift(-1).eq(raw.time+pd.Timedelta(minutes=1)) &
                     raw.time.shift(-(horizon+1)).eq(raw.time+pd.Timedelta(minutes=horizon+1)))
            ret_log_bp = (1e4*np.log(exit_open/entry_open)).where(exact)
            ret_pips = ((exit_open-entry_open)/pip_size).where(exact)

            forward_high = reverse_rolling(raw.high.astype(float).shift(-1),horizon,'max')
            forward_low = reverse_rolling(raw.low.astype(float).shift(-1),horizon,'min')
            forward_high = pd.concat([forward_high,entry_open,exit_open],axis=1).max(axis=1).where(exact)
            forward_low = pd.concat([forward_low,entry_open,exit_open],axis=1).min(axis=1).where(exact)
            long_mfe_log_bp = (1e4*np.log(forward_high/entry_open)).where(exact)
            long_mae_log_bp = (1e4*np.log(entry_open/forward_low)).where(exact)
            long_mfe_pips = ((forward_high-entry_open)/pip_size).where(exact)
            long_mae_pips = ((entry_open-forward_low)/pip_size).where(exact)

            take = lambda s: pd.Series(s).iloc[decision_positions].to_numpy()
            prefix = f'h{horizon}'
            target_columns[f'ret_log_bp_{prefix}'] = take(ret_log_bp)
            target_columns[f'abs_log_bp_{prefix}'] = np.abs(target_columns[f'ret_log_bp_{prefix}'])
            target_columns[f'ret_pips_{prefix}'] = take(ret_pips)
            target_columns[f'long_mfe_log_bp_{prefix}'] = take(long_mfe_log_bp)
            target_columns[f'long_mae_log_bp_{prefix}'] = take(long_mae_log_bp)
            target_columns[f'long_mfe_pips_{prefix}'] = take(long_mfe_pips)
            target_columns[f'long_mae_pips_{prefix}'] = take(long_mae_pips)

            valid = np.isfinite(target_columns[f'ret_log_bp_{prefix}'])
            assert np.isfinite(target_columns[f'long_mfe_log_bp_{prefix}'][valid]).all()
            assert np.isfinite(target_columns[f'long_mae_log_bp_{prefix}'][valid]).all()
            assert (target_columns[f'long_mfe_log_bp_{prefix}'][valid]+1e-8 >=
                    np.maximum(target_columns[f'ret_log_bp_{prefix}'][valid],0)).all()
            assert (target_columns[f'long_mae_log_bp_{prefix}'][valid]+1e-8 >=
                    np.maximum(-target_columns[f'ret_log_bp_{prefix}'][valid],0)).all()
            assert (target_columns[f'long_mfe_pips_{prefix}'][valid]+1e-6 >=
                    np.maximum(target_columns[f'ret_pips_{prefix}'][valid],0)).all()
            assert (target_columns[f'long_mae_pips_{prefix}'][valid]+1e-6 >=
                    np.maximum(-target_columns[f'ret_pips_{prefix}'][valid],0)).all()

        targets = pd.DataFrame(target_columns)
        assert len(targets) == len(base_decisions)
        print(f'Built exact targets for {len(PREDICTION_WINDOWS_MIN)} horizons.')
        """
    ),
    md(
        r"""
        ## 4. Decision-stage data quality and period coverage

        Coverage is reported by period, horizon, RSI configuration, year, and decision slot. Missing targets are not replaced
        with shorter horizons. RSI warm-up loss is causal and visible; it must not become a hidden time-of-day filter.
        """
    ),
    code(
        r"""
        period_masks = {
            'in_sample':base_decisions.ts_utc.ge(IN_SAMPLE_START) & base_decisions.ts_utc.lt(IN_SAMPLE_END_EXCLUSIVE),
            'pre_holdout_check':base_decisions.ts_utc.ge(PRE_HOLDOUT_CHECK_START) &
                                base_decisions.ts_utc.lt(PRE_HOLDOUT_CHECK_END_EXCLUSIVE),
        }
        assert not base_decisions.ts_utc.ge(HOLDOUT_START).any()

        target_coverage_rows = []
        for period, mask in period_masks.items():
            for horizon in PREDICTION_WINDOWS_MIN:
                col = f'ret_log_bp_h{horizon}'
                target_coverage_rows.append({
                    'period':period,'horizon':horizon,'decisions':int(mask.sum()),
                    'valid_targets':int(targets.loc[mask,col].notna().sum()),
                    'coverage':targets.loc[mask,col].notna().mean(),
                })
        target_coverage = pd.DataFrame(target_coverage_rows).set_index(['period','horizon'])
        display(target_coverage.style.format({'coverage':'{:.1%}'}))

        rsi_coverage = rsi_metadata.copy()
        for period, mask in period_masks.items():
            rsi_coverage[f'{period}_coverage'] = [rsi_at_lag[0].loc[mask,c].notna().mean() for c in rsi_coverage.column]
        display(rsi_coverage.set_index('column').style.format({c:'{:.1%}' for c in rsi_coverage if c.endswith('coverage')}))

        slot_coverage = pd.DataFrame({
            'target_30m':targets.ret_log_bp_h30.notna() if 30 in PREDICTION_WINDOWS_MIN else targets.iloc[:,0].notna(),
            'rsi_longest':rsi_at_lag[0][rsi_metadata.sort_values('length').iloc[-1].column].notna(),
            'session_minute':base_decisions.session_minute,
        }).groupby('session_minute').mean()
        display(slot_coverage.style.format('{:.1%}'))

        quality_by_year = base_decisions.assign(
            valid_target=targets[f'ret_log_bp_h{PREDICTION_WINDOWS_MIN[-1]}'].notna(),
            valid_rsi=rsi_at_lag[0][rsi_metadata.iloc[-1].column].notna()).groupby('year').agg(
                decisions=('ts_utc','size'),sessions=('sdate','nunique'),
                longest_target_coverage=('valid_target','mean'),longest_rsi_coverage=('valid_rsi','mean'))
        display(quality_by_year.style.format({c:'{:.1%}' for c in quality_by_year if c.endswith('coverage')}))
        """
    ),
    md(
        r"""
        ## 5. In-sample RSI × source × smoother × length × horizon grid

        The primary continuous statistic is within-session-slot Spearman IC between RSI and signed endpoint return. Because
        the expected mean-reversion sign is negative, `mean_reversion_ic = -within_slot_ic` is positive when the hypothesis
        works. The explicit rule is long at RSI ≤ 30 and short at RSI ≥ 70.

        Per-signal returns are the estimand. Dependence is handled with a New-York-session clustered t-statistic; observations
        are not averaged into one value per session. Approximate normal p-values receive a Benjamini-Hochberg adjustment across
        the full grid, but that adjustment does not replace a selection-aware null or independent validation.
        """
    ),
    code(
        r"""
        def session_cluster_t(values, sessions):
            z = pd.DataFrame({'x':values,'session':sessions}).dropna()
            n, blocks = len(z), z.session.nunique()
            if n < 2 or blocks < 2:
                return np.nan
            mean = z.x.mean()
            block_score = (z.x-mean).groupby(z.session).sum()
            se = np.sqrt((blocks/(blocks-1))*np.square(block_score).sum())/n
            return mean/se if se>0 else np.nan


        def within_slot_ic(feature, target, slot):
            z = pd.DataFrame({'feature':feature,'target':target,'slot':slot}).dropna()
            if len(z)<3 or z.feature.nunique()<3 or z.target.nunique()<3:
                return np.nan, len(z)
            z['rf'] = z.groupby('slot').feature.rank(method='average',pct=True)
            z['rt'] = z.groupby('slot').target.rank(method='average',pct=True)
            return z.rf.corr(z.rt), len(z)


        def benjamini_hochberg(pvalues):
            p = np.asarray(pvalues,float)
            out = np.full(len(p),np.nan)
            finite = np.isfinite(p)
            idx = np.flatnonzero(finite)
            if not len(idx):
                return out
            order = idx[np.argsort(p[idx])]
            ranked = p[order]*len(order)/np.arange(1,len(order)+1)
            ranked = np.minimum.accumulate(ranked[::-1])[::-1]
            out[order] = np.minimum(ranked,1.0)
            return out


        def score_config(feature, horizon, mask):
            prefix = f'h{horizon}'
            z = pd.DataFrame({
                'feature':feature,'target':targets[f'ret_log_bp_{prefix}'],
                'abs_target':targets[f'abs_log_bp_{prefix}'],'ret_pips':targets[f'ret_pips_{prefix}'],
                'long_mfe_bp':targets[f'long_mfe_log_bp_{prefix}'],'long_mae_bp':targets[f'long_mae_log_bp_{prefix}'],
                'long_mfe_pips':targets[f'long_mfe_pips_{prefix}'],'long_mae_pips':targets[f'long_mae_pips_{prefix}'],
                'slot':base_decisions.session_minute,'session':base_decisions.sdate,'year':base_decisions.year,
            }).loc[mask].dropna()
            pooled_ic = spearmanr(z.feature,z.target).statistic if z.feature.nunique()>2 else np.nan
            slot_ic, n = within_slot_ic(z.feature,z.target,z.slot)
            extremeness_abs_ic = spearmanr((z.feature-50).abs(),z.abs_target).statistic

            side = np.select([z.feature.le(EDGE_LOW_THRESHOLD),z.feature.ge(EDGE_HIGH_THRESHOLD)],[1,-1],default=0)
            signal = side != 0
            e = z.loc[signal].copy()
            e['side'] = side[signal]
            e['pnl_bp'] = e.side*e.target
            e['pnl_pips'] = e.side*e.ret_pips
            e['mfe_bp'] = np.where(e.side.gt(0),e.long_mfe_bp,e.long_mae_bp)
            e['mae_bp'] = np.where(e.side.gt(0),e.long_mae_bp,e.long_mfe_bp)
            e['mfe_pips'] = np.where(e.side.gt(0),e.long_mfe_pips,e.long_mae_pips)
            e['mae_pips'] = np.where(e.side.gt(0),e.long_mae_pips,e.long_mfe_pips)

            yearly_ics = []
            for _, g in z.groupby('year'):
                ic, _ = within_slot_ic(g.feature,g.target,g.slot)
                yearly_ics.append(ic)
            yearly_ics = np.asarray(yearly_ics,float)
            cluster_t = session_cluster_t(e.pnl_bp,e.session)
            losses = -e.loc[e.pnl_bp.lt(0),'pnl_bp'].sum()
            low_q = z.feature.quantile(0.20); high_q = z.feature.quantile(0.80)
            q1 = z.loc[z.feature.le(low_q),'target'].mean()
            q5 = z.loc[z.feature.ge(high_q),'target'].mean()
            return {
                'n':n,'coverage':n/max(int(mask.sum()),1),'pooled_ic':pooled_ic,'within_slot_ic':slot_ic,
                'mean_reversion_ic':-slot_ic,'extremeness_abs_ic':extremeness_abs_ic,
                'yearly_expected_sign_fraction':np.nanmean(yearly_ics<0),
                'worst_year_mean_reversion_ic':np.nanmin(-yearly_ics),
                'q5_minus_q1_signed_log_bp':q5-q1,
                'signals':len(e),'signal_rate':len(e)/max(len(z),1),
                'mean_pnl_log_bp':e.pnl_bp.mean(),'mean_pnl_pips':e.pnl_pips.mean(),
                'session_cluster_t':cluster_t,'cluster_pvalue':2*norm.sf(abs(cluster_t)) if np.isfinite(cluster_t) else np.nan,
                'win_rate':e.pnl_bp.gt(0).mean(),
                'profit_factor':e.loc[e.pnl_bp.gt(0),'pnl_bp'].sum()/losses if losses>0 else np.nan,
                'mean_mfe_log_bp':e.mfe_bp.mean(),'mean_mae_log_bp':e.mae_bp.mean(),
                'mean_mfe_pips':e.mfe_pips.mean(),'mean_mae_pips':e.mae_pips.mean(),
                'mfe_mae_ratio':e.mfe_bp.mean()/e.mae_bp.mean() if e.mae_bp.mean()>0 else np.nan,
                'mfe_capture':e.pnl_bp.mean()/e.mfe_bp.mean() if e.mfe_bp.mean()>0 else np.nan,
                'long_signals':int(e.side.gt(0).sum()),'short_signals':int(e.side.lt(0).sum()),
                'long_mean_pnl_log_bp':e.loc[e.side.gt(0),'pnl_bp'].mean(),
                'short_mean_pnl_log_bp':e.loc[e.side.lt(0),'pnl_bp'].mean(),
            }


        grid_rows = []
        in_sample_mask = period_masks['in_sample']
        for meta in rsi_metadata.itertuples(index=False):
            feature = rsi_at_lag[0][meta.column]
            for horizon in PREDICTION_WINDOWS_MIN:
                row = score_config(feature,horizon,in_sample_mask)
                row.update({'column':meta.column,'source':meta.source,'smoother':meta.smoother,
                            'length':meta.length,'horizon':horizon})
                grid_rows.append(row)
        rsi_grid = pd.DataFrame(grid_rows)
        rsi_grid['edge_bh_qvalue'] = benjamini_hochberg(rsi_grid.cluster_pvalue)
        print(f'Scored {len(rsi_grid)} searched configurations on the in-sample period.')
        """
    ),
])

cells.extend([
    md(
        r"""
        ## 7. Chronological pre-holdout check

        This section applies the one selected in-sample configuration unchanged to 2020–2023. It does not re-rank the grid or
        retune thresholds. Because this interval has already been viewed in related project work, call it an internal temporal
        check—not untouched out-of-sample evidence.
        """
    ),
    code(
        r"""
        period_comparison_rows = []
        for period, mask in period_masks.items():
            if period == 'pre_holdout_check' and not RUN_PRE_HOLDOUT_CHECK:
                continue
            score = score_config(selected_feature,selected_config['horizon'],mask)
            edge_frame = make_edge_frame(selected_feature,selected_config['horizon'],mask)
            detail = detailed_edge_metrics(edge_frame).to_dict()
            period_comparison_rows.append({'period':period,**score,**{f'detail_{k}':v for k,v in detail.items()}})
        selected_period_comparison = pd.DataFrame(period_comparison_rows).set_index('period')
        compare_cols = ['n','within_slot_ic','mean_reversion_ic','extremeness_abs_ic','yearly_expected_sign_fraction',
                        'signals','mean_pnl_log_bp','mean_pnl_pips','session_cluster_t','win_rate','profit_factor',
                        'mean_mfe_log_bp','mean_mae_log_bp','mfe_mae_ratio','mfe_capture']
        display(selected_period_comparison[compare_cols].style.format({
            'yearly_expected_sign_fraction':'{:.0%}','win_rate':'{:.1%}',
            **{c:'{:+.4f}' for c in compare_cols if c.endswith('ic')},
            **{c:'{:+.3f}' for c in compare_cols if c not in ['n','signals','yearly_expected_sign_fraction','win_rate'] and not c.endswith('ic')}}))

        if RUN_PRE_HOLDOUT_CHECK:
            selected_check = make_edge_frame(selected_feature,selected_config['horizon'],period_masks['pre_holdout_check'])
            check_yearly = pd.DataFrame([
                {'year':year,**detailed_edge_metrics(g).to_dict()} for year,g in selected_check.groupby('year')]).set_index('year')
            display(check_yearly.style.format({
                'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}','profit_factor':'{:.3f}',
                **{c:'{:+.3f}' for c in check_yearly if c not in ['signals','sessions','win_rate','profit_factor']}}))
        """
    ),
    md(
        r"""
        ## 8. Conditions that may explain or concentrate the selected edge

        These are discovery diagnostics, not independent tests. They split the selected in-sample signals by side, market
        session, weekday, trailing volatility, prior-path efficiency, RSI depth, and whether RSI is moving back toward 50.
        Volatility and path-efficiency quintile cutoffs are fitted on the in-sample period only and can be carried unchanged into
        the internal check. Condition counts, clustered t-statistics, and MFE/MAE geometry are shown to discourage tiny-slice
        storytelling.
        """
    ),
    code(
        r"""
        def condition_row(g):
            m = detailed_edge_metrics(g)
            return pd.Series({k:m.get(k,np.nan) for k in [
                'signals','sessions','mean_pnl_log_bp','mean_pnl_pips','session_cluster_t','win_rate','profit_factor',
                'mean_mfe_log_bp','mean_mae_log_bp','mean_mfe_pips','mean_mae_pips','mfe_mae_ratio','mfe_capture']})


        rv_edges = selected_is.rv60.quantile([0,.2,.4,.6,.8,1]).to_numpy(copy=True)
        efficiency_edges = selected_is.path_eff60.quantile([0,.2,.4,.6,.8,1]).to_numpy(copy=True)
        rv_edges[0],rv_edges[-1] = -np.inf,np.inf
        efficiency_edges[0],efficiency_edges[-1] = -np.inf,np.inf

        for frame in [selected_is] + ([selected_check] if RUN_PRE_HOLDOUT_CHECK else []):
            frame['volatility_quintile_from_is'] = pd.cut(frame.rv60,bins=np.unique(rv_edges),include_lowest=True,labels=False)
            frame['path_efficiency_quintile_from_is'] = pd.cut(
                frame.path_eff60,bins=np.unique(efficiency_edges),include_lowest=True,labels=False)
            frame['rsi_depth'] = np.where(frame.side.gt(0),EDGE_LOW_THRESHOLD-frame.rsi,
                                          np.where(frame.side.lt(0),frame.rsi-EDGE_HIGH_THRESHOLD,np.nan))

        lag5_selected = rsi_at_lag[5][selected_config['column']]
        selected_is['rsi_lag5'] = lag5_selected.loc[selected_is.index].to_numpy()
        selected_is['toward_center_5m'] = selected_is.side*(selected_is.rsi-selected_is.rsi_lag5)
        selected_is['rsi_turn_state'] = np.where(selected_is.toward_center_5m.gt(0),'turning_toward_50','moving_deeper')
        selected_is['depth_bucket'] = pd.cut(selected_is.rsi_depth,[-np.inf,2,5,10,np.inf],
                                             labels=['0-2','2-5','5-10','10+'])

        condition_tables = {}
        for condition in ['position','market_session','day_of_week','volatility_quintile_from_is',
                          'path_efficiency_quintile_from_is','depth_bucket','rsi_turn_state']:
            rows = []
            for value,g in selected_is_signals.assign(**{
                    c:selected_is.loc[selected_is_signals.index,c] for c in
                    ['volatility_quintile_from_is','path_efficiency_quintile_from_is','depth_bucket','rsi_turn_state']
                }).groupby(condition,observed=True):
                rows.append({'condition_value':value,**condition_row(g).to_dict()})
            table = pd.DataFrame(rows).set_index('condition_value')
            condition_tables[condition] = table
            print(f'Condition: {condition}')
            display(table.style.format({'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}',
                'profit_factor':'{:.3f}',**{c:'{:+.3f}' for c in table if c not in ['signals','sessions','win_rate','profit_factor']}}))
        """
    ),
    md(
        r"""
        ## 9. Feature-timing placebo

        The same selected RSI definition is sampled at the decision close, one minute earlier, and five minutes earlier. Targets,
        thresholds, and observations otherwise stay fixed. A large collapse after a one-minute lag would make adjacent-bar
        midpoint behavior a plausible explanation and materially weaken the strategy thesis.
        """
    ),
    code(
        r"""
        timing_rows = []
        for period, mask in period_masks.items():
            if period=='pre_holdout_check' and not RUN_PRE_HOLDOUT_CHECK:
                continue
            for lag in FEATURE_TIMING_LAGS_MIN:
                feature = rsi_at_lag[lag][selected_config['column']]
                score = score_config(feature,selected_config['horizon'],mask)
                timing_rows.append({'period':period,'feature_lag_min':lag,**score})
        timing_placebo = pd.DataFrame(timing_rows).set_index(['period','feature_lag_min'])
        timing_cols = ['n','mean_reversion_ic','yearly_expected_sign_fraction','signals','mean_pnl_log_bp','mean_pnl_pips',
                       'session_cluster_t','win_rate','mean_mfe_log_bp','mean_mae_log_bp','mfe_mae_ratio']
        display(timing_placebo[timing_cols].style.format({
            'yearly_expected_sign_fraction':'{:.0%}','win_rate':'{:.1%}','mean_reversion_ic':'{:+.4f}',
            **{c:'{:+.3f}' for c in timing_cols if c not in ['n','signals','yearly_expected_sign_fraction','win_rate','mean_reversion_ic']}}))
        """
    ),
    md(
        r"""
        ## 10. Session-block uncertainty for the selected configuration

        The bootstrap resamples whole New-York sessions. It reports intervals for per-signal mean gross return and fixed-rank
        within-slot IC. This handles within-session dependence and overlapping horizons more honestly than an IID row bootstrap.
        It does not correct the automatic search over the full grid; the selected result remains exploratory.
        """
    ),
    code(
        r"""
        def block_bootstrap_selected(feature, horizon, mask, draws, rng):
            prefix = f'h{horizon}'
            z = pd.DataFrame({'feature':feature,'target':targets[f'ret_log_bp_{prefix}'],
                              'slot':base_decisions.session_minute,'session':base_decisions.sdate}).loc[mask].dropna()
            z['side'] = np.select([z.feature.le(EDGE_LOW_THRESHOLD),z.feature.ge(EDGE_HIGH_THRESHOLD)],[1,-1],default=0)
            z['pnl'] = z.side*z.target
            z['rf'] = z.groupby('slot').feature.rank(method='average',pct=True)
            z['rt'] = z.groupby('slot').target.rank(method='average',pct=True)
            z = z.dropna()
            session_stats = z.groupby('session').agg(
                n=('target','size'),sum_rf=('rf','sum'),sum_rt=('rt','sum'),
                sum_rf2=('rf',lambda s:np.square(s).sum()),sum_rt2=('rt',lambda s:np.square(s).sum()),
                sum_cross=('rf',lambda s:np.nan),
                signal_n=('side',lambda s:s.ne(0).sum()),signal_pnl=('pnl',lambda s:s.where(z.loc[s.index,'side'].ne(0)).sum()))
            # Cross-products require both columns and are filled separately.
            session_stats['sum_cross'] = z.assign(cross=z.rf*z.rt).groupby('session').cross.sum()
            arrays = session_stats.to_numpy(float)
            columns = {c:i for i,c in enumerate(session_stats.columns)}
            g = len(session_stats)
            ic_draws, pnl_draws = [], []
            for _ in range(draws):
                sampled = arrays[rng.integers(0,g,size=g)].sum(axis=0)
                n = sampled[columns['n']]
                sx,sy = sampled[columns['sum_rf']],sampled[columns['sum_rt']]
                sxx,syy,sxy = sampled[columns['sum_rf2']],sampled[columns['sum_rt2']],sampled[columns['sum_cross']]
                cov = sxy-sx*sy/n
                varx,vary = sxx-sx*sx/n,syy-sy*sy/n
                ic_draws.append(cov/np.sqrt(varx*vary) if varx>0 and vary>0 else np.nan)
                signal_n = sampled[columns['signal_n']]
                pnl_draws.append(sampled[columns['signal_pnl']]/signal_n if signal_n>0 else np.nan)
            point_ic = z.rf.corr(z.rt)
            point_pnl = z.loc[z.side.ne(0),'pnl'].mean()
            return {'n':len(z),'sessions':g,'within_slot_ic':point_ic,
                    'ic_ci_lo':np.nanquantile(ic_draws,.025),'ic_ci_hi':np.nanquantile(ic_draws,.975),
                    'mean_pnl_log_bp':point_pnl,'pnl_ci_lo':np.nanquantile(pnl_draws,.025),
                    'pnl_ci_hi':np.nanquantile(pnl_draws,.975)}


        bootstrap_rows = []
        if not SKIP_BOOTSTRAP:
            rng = np.random.default_rng(RANDOM_SEED)
            for period, mask in period_masks.items():
                if period=='pre_holdout_check' and not RUN_PRE_HOLDOUT_CHECK:
                    continue
                row = block_bootstrap_selected(selected_feature,selected_config['horizon'],mask,BOOTSTRAP_DRAWS,rng)
                row['period'] = period
                bootstrap_rows.append(row)
        selected_bootstrap = pd.DataFrame(bootstrap_rows).set_index('period') if bootstrap_rows else pd.DataFrame()
        if len(selected_bootstrap):
            display(selected_bootstrap.style.format({c:'{:+.4f}' for c in selected_bootstrap if c not in ['n','sessions']}))
        else:
            print('Bootstrap skipped by environment parameter.')
        """
    ),
    md(
        r"""
        ## 11. Interpretation checklist and next research step

        Useful evidence would be a smooth dose-response across RSI bins/thresholds, stable negative signed IC across years and
        horizons, both long and short participation, favorable MFE/MAE geometry, persistence under the one- and five-minute
        timing placebo, and a selected configuration that degrades only modestly in the later pre-holdout interval.

        Warning signs are a single isolated optimum, one-side dependence, tiny condition slices, an edge comparable to a fraction
        of a pip, poor MFE capture, large adverse excursions, or collapse after a one-minute feature lag. Do not design a stop or
        target from MFE/MAE and score it on the same sample as confirmation. Once a compact condition is chosen, freeze the entry,
        horizon, execution, cost model, primary metric, kill rule, and claim-matched null before opening 2024+.
        """
    ),
    code(
        r"""
        assert raw.time.max() < HOLDOUT_START
        assert base_decisions.ts_utc.max() < HOLDOUT_START
        assert IN_SAMPLE_END_EXCLUSIVE <= PRE_HOLDOUT_CHECK_START
        print('FINAL HOLDOUT CHECK PASSED: every retained bar, feature, target, and scored observation is strictly pre-2024.')
        print(f'Selected configuration: {selected_config}')
        print(f'Selection provenance: {selection_provenance}')
        print('Any threshold, condition, or configuration inspected here is part of the discovery search.')
        """
    ),
])


notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
cells.extend([
    code(
        r"""
        ranking_columns = [
            'source','smoother','length','horizon','n','coverage','within_slot_ic','mean_reversion_ic',
            'extremeness_abs_ic','yearly_expected_sign_fraction','worst_year_mean_reversion_ic',
            'signals','signal_rate','mean_pnl_log_bp','mean_pnl_pips','session_cluster_t','edge_bh_qvalue',
            'win_rate','profit_factor','mean_mfe_log_bp','mean_mae_log_bp','mfe_mae_ratio','mfe_capture',
            'long_mean_pnl_log_bp','short_mean_pnl_log_bp',
        ]
        display(rsi_grid.nlargest(40,SELECTION_PRIMARY_METRIC)[ranking_columns].style.format({
            'coverage':'{:.1%}','signal_rate':'{:.1%}','yearly_expected_sign_fraction':'{:.0%}',
            'win_rate':'{:.1%}','edge_bh_qvalue':'{:.3g}',
            **{c:'{:+.4f}' for c in ranking_columns if c.endswith('ic')},
            **{c:'{:+.3f}' for c in ranking_columns if c not in ['source','smoother','length','horizon','n','signals','coverage',
                'signal_rate','yearly_expected_sign_fraction','win_rate','edge_bh_qvalue'] and not c.endswith('ic')},
        }))

        factor_parts = []
        for factor in ['source','smoother','length','horizon']:
            part = rsi_grid.groupby(factor).agg(
                mean_reversion_ic=('mean_reversion_ic','median'),worst_ic=('mean_reversion_ic','min'),
                mean_edge_bp=('mean_pnl_log_bp','median')).rename_axis('level').reset_index()
            part['factor'] = factor
            factor_parts.append(part)
        factor_summary = pd.concat(factor_parts,ignore_index=True).set_index(['factor','level'])
        display(factor_summary.style.format('{:+.4f}'))

        robust_by_rsi = rsi_grid.groupby(['source','smoother','length']).agg(
            median_mean_reversion_ic=('mean_reversion_ic','median'),
            worst_horizon_ic=('mean_reversion_ic','min'),
            positive_horizon_fraction=('mean_reversion_ic',lambda s:(s>0).mean()),
            median_edge_log_bp=('mean_pnl_log_bp','median'),
            min_year_sign_fraction=('yearly_expected_sign_fraction','min')).sort_values(
                ['worst_horizon_ic','median_mean_reversion_ic'],ascending=False)
        display(robust_by_rsi.head(30).style.format({
            'median_mean_reversion_ic':'{:+.4f}','worst_horizon_ic':'{:+.4f}',
            'positive_horizon_fraction':'{:.0%}','median_edge_log_bp':'{:+.3f}','min_year_sign_fraction':'{:.0%}'}))

        fig, axes = plt.subplots(len(RSI_SOURCES),len(RSI_SMOOTHERS),
                                 figsize=(5*len(RSI_SMOOTHERS),4*len(RSI_SOURCES)),squeeze=False)
        for i, source in enumerate(RSI_SOURCES):
            for j, smoother in enumerate(RSI_SMOOTHERS):
                pivot = rsi_grid.loc[rsi_grid.source.eq(source)&rsi_grid.smoother.eq(smoother)].pivot(
                    index='length',columns='horizon',values='mean_reversion_ic')
                sns.heatmap(pivot,annot=True,fmt='.3f',center=0,cmap='RdBu',ax=axes[i,j])
                axes[i,j].set_title(f'{source} / {smoother}: mean-reversion IC')
        plt.tight_layout(); plt.show()

        source_pair = rsi_grid.pivot_table(index=['smoother','length','horizon'],columns='source',values='mean_reversion_ic')
        if {'close','ohl3'} <= set(source_pair.columns):
            source_pair['ohl3_minus_close'] = source_pair.ohl3-source_pair.close
            print('Paired source comparison on identical smoother/length/horizon cells:')
            display(source_pair.describe().style.format('{:+.4f}'))
        """
    ),
    md(
        r"""
        ## 6. Select one configuration and inspect its geometry

        Automatic selection is explicitly data-mined: it chooses the best in-sample primary metric after minimum signal and
        yearly-sign-stability gates. Set `MANUAL_SELECTED_CONFIG` near the top to replace it with a frozen choice. The detailed
        tables show raw RSI bins, symmetric threshold dose-response, long/short asymmetry, annual stability, terminal tails,
        MFE/MAE, capture, giveback, and individual touch probabilities.
        """
    ),
    code(
        r"""
        if MANUAL_SELECTED_CONFIG is None:
            eligible = rsi_grid.loc[
                rsi_grid.signals.ge(MIN_SELECTED_SIGNALS) &
                rsi_grid.yearly_expected_sign_fraction.ge(MIN_YEARLY_EXPECTED_SIGN_FRACTION)].copy()
            assert len(eligible), 'No configuration passes the automatic-selection coverage gates.'
            selected = eligible.nlargest(1,SELECTION_PRIMARY_METRIC).iloc[0]
            selection_provenance = f'AUTO-SELECTED on in-sample {SELECTION_PRIMARY_METRIC}; searched {len(rsi_grid)} cells'
        else:
            match = rsi_grid.loc[
                rsi_grid.source.eq(MANUAL_SELECTED_CONFIG['source']) &
                rsi_grid.smoother.eq(MANUAL_SELECTED_CONFIG['smoother']) &
                rsi_grid.length.eq(MANUAL_SELECTED_CONFIG['length']) &
                rsi_grid.horizon.eq(MANUAL_SELECTED_CONFIG['horizon'])]
            assert len(match)==1, 'Manual selected configuration not found in the grid.'
            selected = match.iloc[0]
            selection_provenance = 'MANUALLY SPECIFIED in the parameter cell'

        selected_config = {k:selected[k] for k in ['column','source','smoother','length','horizon']}
        selected_config['length'] = int(selected_config['length'])
        selected_config['horizon'] = int(selected_config['horizon'])
        print(selection_provenance)
        print(selected_config)

        def make_edge_frame(feature, horizon, mask, low=EDGE_LOW_THRESHOLD, high=EDGE_HIGH_THRESHOLD):
            prefix = f'h{horizon}'
            z = pd.DataFrame({
                'ts_utc':base_decisions.ts_utc,'sdate':base_decisions.sdate,'year':base_decisions.year,
                'slot':base_decisions.session_minute,'market_session':base_decisions.market_session,
                'day_of_week':base_decisions.day_of_week,'rv60':base_decisions.trailing_rv_60_log_bp,
                'past_return60':base_decisions.past_return_60_log_bp,'path_eff60':base_decisions.path_efficiency_60,
                'rsi':feature,'target_bp':targets[f'ret_log_bp_{prefix}'],'abs_target_bp':targets[f'abs_log_bp_{prefix}'],
                'target_pips':targets[f'ret_pips_{prefix}'],'long_mfe_bp':targets[f'long_mfe_log_bp_{prefix}'],
                'long_mae_bp':targets[f'long_mae_log_bp_{prefix}'],'long_mfe_pips':targets[f'long_mfe_pips_{prefix}'],
                'long_mae_pips':targets[f'long_mae_pips_{prefix}'],
            }).loc[mask].dropna(subset=['rsi','target_bp']).copy()
            z['side'] = np.select([z.rsi.le(low),z.rsi.ge(high)],[1,-1],default=0).astype('int8')
            z['position'] = np.select([z.side.gt(0),z.side.lt(0)],['long','short'],default='none')
            z['pnl_bp'] = z.side*z.target_bp
            z['pnl_pips'] = z.side*z.target_pips
            z['mfe_bp'] = np.where(z.side.gt(0),z.long_mfe_bp,z.long_mae_bp)
            z['mae_bp'] = np.where(z.side.gt(0),z.long_mae_bp,z.long_mfe_bp)
            z['mfe_pips'] = np.where(z.side.gt(0),z.long_mfe_pips,z.long_mae_pips)
            z['mae_pips'] = np.where(z.side.gt(0),z.long_mae_pips,z.long_mfe_pips)
            z['giveback_bp'] = z.mfe_bp-z.pnl_bp
            z['giveback_pips'] = z.mfe_pips-z.pnl_pips
            return z


        def detailed_edge_metrics(frame, include_no_signal=False):
            g = frame if include_no_signal else frame.loc[frame.side.ne(0)]
            if not len(g):
                return pd.Series(dtype=float)
            losses = -g.loc[g.pnl_bp.lt(0),'pnl_bp'].sum()
            p05 = g.pnl_bp.quantile(0.05)
            sessions = max(g.sdate.nunique(),1)
            return pd.Series({
                'signals':len(g),'sessions':sessions,'signals_per_session':len(g)/sessions,
                'mean_pnl_log_bp':g.pnl_bp.mean(),'median_pnl_log_bp':g.pnl_bp.median(),
                'mean_pnl_pips':g.pnl_pips.mean(),'median_pnl_pips':g.pnl_pips.median(),
                'breakeven_roundtrip_cost_log_bp':g.pnl_bp.mean(),
                'breakeven_roundtrip_cost_pips':g.pnl_pips.mean(),
                'session_cluster_t':session_cluster_t(g.pnl_bp,g.sdate),'win_rate':g.pnl_bp.gt(0).mean(),
                'profit_factor':g.loc[g.pnl_bp.gt(0),'pnl_bp'].sum()/losses if losses>0 else np.nan,
                'p05_pnl_log_bp':p05,'expected_shortfall_5_log_bp':g.loc[g.pnl_bp.le(p05),'pnl_bp'].mean(),
                'mean_mfe_log_bp':g.mfe_bp.mean(),'median_mfe_log_bp':g.mfe_bp.median(),'p90_mfe_log_bp':g.mfe_bp.quantile(.9),
                'mean_mae_log_bp':g.mae_bp.mean(),'median_mae_log_bp':g.mae_bp.median(),'p90_mae_log_bp':g.mae_bp.quantile(.9),
                'mean_mfe_pips':g.mfe_pips.mean(),'median_mfe_pips':g.mfe_pips.median(),'p90_mfe_pips':g.mfe_pips.quantile(.9),
                'mean_mae_pips':g.mae_pips.mean(),'median_mae_pips':g.mae_pips.median(),'p90_mae_pips':g.mae_pips.quantile(.9),
                'mfe_mae_ratio':g.mfe_bp.mean()/g.mae_bp.mean() if g.mae_bp.mean()>0 else np.nan,
                'mfe_capture':g.pnl_bp.mean()/g.mfe_bp.mean() if g.mfe_bp.mean()>0 else np.nan,
                'mean_giveback_log_bp':g.giveback_bp.mean(),'mean_giveback_pips':g.giveback_pips.mean(),
            })


        selected_feature = rsi_at_lag[0][selected_config['column']]
        selected_is = make_edge_frame(selected_feature,selected_config['horizon'],in_sample_mask)
        selected_is_signals = selected_is.loc[selected_is.side.ne(0)].copy()

        rsi_bins = pd.cut(selected_is.rsi,bins=np.arange(0,101,10),include_lowest=True)
        binned_relationship = selected_is.groupby(rsi_bins,observed=True).agg(
            n=('target_bp','size'),rsi_mean=('rsi','mean'),signed_log_bp=('target_bp','mean'),
            signed_pips=('target_pips','mean'),absolute_log_bp=('abs_target_bp','mean'),
            long_mfe_log_bp=('long_mfe_bp','mean'),long_mae_log_bp=('long_mae_bp','mean'),
            long_mfe_pips=('long_mfe_pips','mean'),long_mae_pips=('long_mae_pips','mean'))
        display(binned_relationship.style.format('{:.3f}'))

        threshold_rows = []
        for low in THRESHOLD_LOW_GRID:
            high = 100-low
            f = make_edge_frame(selected_feature,selected_config['horizon'],in_sample_mask,low,high)
            row = detailed_edge_metrics(f).to_dict()
            row.update({'low_threshold':low,'high_threshold':high,'searched':True})
            threshold_rows.append(row)
        threshold_grid = pd.DataFrame(threshold_rows).set_index(['low_threshold','high_threshold'])
        print('Threshold dose-response is exploratory and adds to the multiple-search burden:')
        display(threshold_grid.style.format({
            'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}',
            **{c:'{:+.3f}' for c in threshold_grid if c not in ['signals','sessions','win_rate','searched']}}))

        selected_group_rows = {'all':detailed_edge_metrics(selected_is)}
        for position,g in selected_is_signals.groupby('position'):
            selected_group_rows[position] = detailed_edge_metrics(g)
        selected_edge_summary = pd.DataFrame(selected_group_rows).T
        display(selected_edge_summary.style.format({
            'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}','profit_factor':'{:.3f}',
            **{c:'{:+.3f}' for c in selected_edge_summary if c not in ['signals','sessions','win_rate','profit_factor']}}))

        cost_rows = []
        for cost_pips in HYPOTHETICAL_ROUND_TRIP_COST_PIPS:
            net_pips = selected_is_signals.pnl_pips-cost_pips
            cost_rows.append({'cost_pips_trade':cost_pips,'signals':len(net_pips),
                              'mean_net_pips_trade':net_pips.mean(),
                              'session_cluster_t':session_cluster_t(net_pips,selected_is_signals.sdate),
                              'net_win_rate':net_pips.gt(0).mean()})
        hypothetical_cost_stress = pd.DataFrame(cost_rows).set_index('cost_pips_trade')
        print('Hypothetical cost sensitivity only; the midpoint files do not contain executable spreads:')
        display(hypothetical_cost_stress.style.format({'signals':'{:,.0f}','mean_net_pips_trade':'{:+.3f}',
                                                       'session_cluster_t':'{:+.3f}','net_win_rate':'{:.1%}'}))

        selected_yearly = pd.DataFrame([
            {'year':year,**detailed_edge_metrics(g).to_dict()} for year,g in selected_is.groupby('year')]).set_index('year')
        display(selected_yearly.style.format({
            'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}','profit_factor':'{:.3f}',
            **{c:'{:+.3f}' for c in selected_yearly if c not in ['signals','sessions','win_rate','profit_factor']}}))

        touch_rows = []
        for side_name,g in [('all',selected_is_signals),*list(selected_is_signals.groupby('position'))]:
            for level in TOUCH_LEVELS_PIPS:
                favorable, adverse = g.mfe_pips.ge(level),g.mae_pips.ge(level)
                touch_rows.append({'side':side_name,'level_pips':level,'signals':len(g),
                    'favorable_touch':favorable.mean(),'adverse_touch':adverse.mean(),
                    'both_touch_order_unknown':(favorable&adverse).mean()})
        touch_rates = pd.DataFrame(touch_rows).set_index(['side','level_pips'])
        display(touch_rates.style.format({'signals':'{:,.0f}','favorable_touch':'{:.1%}',
            'adverse_touch':'{:.1%}','both_touch_order_unknown':'{:.1%}'}))
        """
    ),
])

# Section 6 is assembled last to keep the large patches manageable; place it
# chronologically before section 7 in the emitted notebook.
section6_index = next(i for i, cell in enumerate(cells)
                      if cell["cell_type"] == "markdown" and "## 6." in "".join(cell["source"]))
section7_index = next(i for i, cell in enumerate(cells)
                      if cell["cell_type"] == "markdown" and "## 7." in "".join(cell["source"]))
section6_cells = cells[section6_index:section6_index + 2]
del cells[section6_index:section6_index + 2]
section7_index = next(i for i, cell in enumerate(cells)
                      if cell["cell_type"] == "markdown" and "## 7." in "".join(cell["source"]))
cells[section7_index:section7_index] = section6_cells

ranking_index = next(i for i, cell in enumerate(cells)
                     if cell["cell_type"] == "code" and "ranking_columns = [" in "".join(cell["source"]))
ranking_cell = cells.pop(ranking_index)
section6_index = next(i for i, cell in enumerate(cells)
                      if cell["cell_type"] == "markdown" and "## 6." in "".join(cell["source"]))
cells.insert(section6_index, ranking_cell)

notebook["cells"] = cells
OUT.write_text(json.dumps(notebook, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT} ({len(cells)} cells)")
