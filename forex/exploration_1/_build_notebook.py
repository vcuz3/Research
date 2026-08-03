"""Build the self-contained forex feature research notebook.

Run from the workspace root with:
    python forex/exploration_1/_build_notebook.py
"""

from pathlib import Path
from textwrap import dedent
import json
import hashlib

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "forex_feature_ml_research.ipynb"


def md(text: str):
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("markdown\0" + source).encode("utf-8")).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(text: str):
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "code",
        "id": hashlib.sha1(("code\0" + source).encode("utf-8")).hexdigest()[:12],
        "execution_count": None,
        "metadata": {},
        "outputs": [],
        "source": source.splitlines(keepends=True),
    }


cells = [
    md(
        r"""
        # Forex feature, prediction, and configurable-horizon TWAP research

        This notebook ports the investigation in `futures/nq/vei_exploration/notebooks/vei_feature_ml_research.ipynb`
        to EURUSD, GBPUSD, AUDUSD, and NZDUSD one-minute midpoint bars. It also incorporates the causal
        factor families from `forward_vol_factor_research.ipynb` and adds FX-specific clock, session,
        path-shape, and cross-pair features.

        ## Research contract

        - `PREDICTION_WINDOW_MIN` controls the forward signed and absolute endpoint-return horizon; the default is 30 minutes.
        - Decisions default to the same non-overlapping interval as the horizon. `DECISION_INTERVAL_MIN` can be set separately,
          but horizons longer than the interval create overlapping labels and positions.
        - A completed minute bar at time `t` may use only information observable by its close. Entry is the next minute's open;
          exit is the open exactly `PREDICTION_WINDOW_MIN` minutes later. Exact timestamp checks reject windows that cross gaps.
        - **2024 onward is the holdout.** The loader reads chronological CSV chunks, retains only rows before 2024, stops at the
          first chunk that reaches the boundary, and asserts that no retained analysis row is in the holdout.
        - All exploration and walk-forward model selection uses pre-2024 data. The holdout is not scored here.
        - FX volume is unavailable (`volume == -1`). No volume feature is used. The baseline signal is price versus cumulative
          session **TWAP**, not VWAP.
        - The data are midpoint OHLC without bid/ask spreads. Strategy results are gross diagnostics plus hypothetical cost
          stress, not evidence of tradability.
        - Spearman IC is reported alongside mean quintile spreads because rank association can miss tail expectancy.
        - This is exploration. Feature searches, model comparisons, and pre-2024 walk-forward results consume pre-2024 history;
          a survivor must be frozen before the 2024+ holdout is opened.

        The FX session is anchored at 17:00 New York time, the conventional daily rollover. Cumulative TWAP and session-reset
        features restart there. Clock labels use local Tokyo, London, and New York time so daylight-saving changes are handled.
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
        from scipy.stats import spearmanr

        from sklearn.compose import ColumnTransformer
        from sklearn.pipeline import Pipeline
        from sklearn.impute import SimpleImputer
        from sklearn.preprocessing import StandardScaler
        from sklearn.linear_model import Ridge
        from sklearn.ensemble import HistGradientBoostingRegressor
        from sklearn.metrics import mean_absolute_error, mean_squared_error, accuracy_score

        warnings.filterwarnings('ignore', category=FutureWarning)
        sns.set_theme(style='whitegrid', context='notebook')
        pd.set_option('display.max_columns', 200)
        pd.set_option('display.width', 220)

        # ----------------------------- user parameters -----------------------------
        PAIRS = ['EURUSD', 'GBPUSD', 'AUDUSD', 'NZDUSD']
        PREDICTION_WINDOW_MIN = 30
        DECISION_INTERVAL_MIN = PREDICTION_WINDOW_MIN
        HOLDOUT_START = pd.Timestamp('2024-01-01', tz='UTC')
        VEI_SHORT, VEI_LONG = 10, 50
        SLOT_LOOKBACK, SLOT_MIN_OBS = 90, 60
        ML_FIRST_TEST_YEAR, ML_LAST_TEST_YEAR = 2016, 2023
        IC_BOOT_DRAWS = 250
        TOP_FEATURES_FOR_BOOTSTRAP = 15
        RUN_ML = True
        PLOT_TOP_N = 20
        RANDOM_SEED = 20260801
        CSV_CHUNK_ROWS = 750_000
        HYPOTHETICAL_ROUND_TRIP_COST_BP = [0.0, 0.25, 0.50, 1.00, 1.50]
        # All pairs in this notebook are quoted to four decimal places: one pip = 0.0001 quote currency.
        PIP_SIZE = {pair: 0.0001 for pair in PAIRS}
        # --------------------------------------------------------------------------

        # A smoke run exercises the full pipeline on one pair and two test years.
        SMOKE_MODE = os.getenv('FOREX_EXPLORATION_SMOKE', '0') == '1'
        SMOKE_ALL_PAIRS = os.getenv('FOREX_EXPLORATION_SMOKE_ALL_PAIRS', '0') == '1'
        ACTIVE_PAIRS = PAIRS if (not SMOKE_MODE or SMOKE_ALL_PAIRS) else PAIRS[:1]
        PAIR_OVERRIDE = os.getenv('FOREX_EXPLORATION_PAIRS', '').strip()
        if PAIR_OVERRIDE:
            ACTIVE_PAIRS = [p.strip().upper() for p in PAIR_OVERRIDE.split(',') if p.strip()]
            assert set(ACTIVE_PAIRS).issubset(PAIRS), f'Unknown pair override: {ACTIVE_PAIRS}'
        RUN_ML = RUN_ML and os.getenv('FOREX_EXPLORATION_SKIP_ML', '0') != '1'
        if SMOKE_MODE:
            IC_BOOT_DRAWS = 30
            TOP_FEATURES_FOR_BOOTSTRAP = 6
            ML_FIRST_TEST_YEAR = 2022

        assert PREDICTION_WINDOW_MIN >= 1
        assert DECISION_INTERVAL_MIN >= 1
        assert 1440 % DECISION_INTERVAL_MIN == 0, 'Use a decision interval that divides a UTC day.'

        here = Path.cwd().resolve()
        if here.name == 'exploration_1':
            project_root = here
        elif (here / 'forex' / 'exploration_1').exists():
            project_root = here / 'forex' / 'exploration_1'
        else:
            raise FileNotFoundError('Run from the workspace root or forex/exploration_1.')
        data_dir = project_root.parent / 'data'

        print(f'Project root: {project_root}')
        print(f'Pairs: {ACTIVE_PAIRS}; horizon={PREDICTION_WINDOW_MIN}m; decision interval={DECISION_INTERVAL_MIN}m')
        print(f'Holdout seal: retained rows must be strictly before {HOLDOUT_START}')
        print(f'Mode: {"SMOKE" if SMOKE_MODE else "FULL"}')
        """
    ),
    md(
        r"""
        ## 1. Chronological loading and raw data-quality gate

        The source files are chronological CSVs, so unlike Parquet they cannot use predicate pushdown. The loader processes
        bounded chunks, discards any rows at or after the holdout boundary, and stops immediately when that boundary is reached.
        It never retains or analyzes a holdout row. A hard assertion is repeated after every construction stage.

        The raw gate reports timestamp order and duplication, OHLC consistency, non-positive prices, flat bars, weekend/daily
        gaps, and the unusable volume field. No completed-session bar-count filter is used to select decision rows.
        """
    ),
    code(
        r"""
        def load_pre_holdout_csv(pair):
            path = data_dir / f'{pair.lower()}_intraday_1min.csv'
            assert path.exists(), f'Missing {path}'
            dtype = {c: 'float32' for c in ['open', 'high', 'low', 'close', 'volume']}
            kept = []
            reached_boundary = False
            for chunk in pd.read_csv(path, dtype=dtype, parse_dates=['time'], chunksize=CSV_CHUNK_ROWS):
                if chunk.time.dt.tz is None:
                    chunk['time'] = chunk.time.dt.tz_localize('UTC')
                else:
                    chunk['time'] = chunk.time.dt.tz_convert('UTC')
                before = chunk.loc[chunk.time < HOLDOUT_START].copy()
                if len(before):
                    kept.append(before)
                if (chunk.time >= HOLDOUT_START).any():
                    reached_boundary = True
                    break
            raw = pd.concat(kept, ignore_index=True)
            raw = raw.sort_values('time', kind='stable').reset_index(drop=True)
            assert len(raw) and raw.time.max() < HOLDOUT_START
            return raw, path, reached_boundary


        def assign_fx_session(raw):
            ny = raw.time.dt.tz_convert('America/New_York')
            ny_date = ny.dt.tz_localize(None).dt.normalize()
            ny_minute = ny.dt.hour * 60 + ny.dt.minute
            raw['sdate'] = ny_date + pd.to_timedelta((ny_minute >= 17 * 60).astype(int), unit='D')
            raw['session_minute'] = ((ny_minute - 17 * 60) % 1440).astype('int16')
            raw['utc_minute'] = (raw.time.dt.hour * 60 + raw.time.dt.minute).astype('int16')
            raw['utc_dow'] = raw.time.dt.dayofweek.astype('int8')
            return raw


        def raw_quality_report(pair, raw, path, reached_boundary):
            delta_min = raw.time.diff().dt.total_seconds().div(60)
            ohlc_bad = ((raw.high < raw[['open', 'close', 'low']].max(axis=1)) |
                        (raw.low > raw[['open', 'close', 'high']].min(axis=1)))
            return {
                'pair': pair, 'file_gb': path.stat().st_size / 1e9, 'rows': len(raw),
                'first': raw.time.min(), 'last_retained': raw.time.max(),
                'sessions': raw.sdate.nunique(), 'boundary_reached': reached_boundary,
                'duplicate_ts': int(raw.time.duplicated().sum()),
                'out_of_order_ts': int((delta_min.dropna() <= 0).sum()),
                'one_minute_links': int(delta_min.eq(1).sum()),
                'gaps_gt_1m': int(delta_min.gt(1).sum()),
                'largest_gap_min': float(delta_min.max()),
                'nonpositive_price_rows': int((raw[['open','high','low','close']] <= 0).any(axis=1).sum()),
                'ohlc_invariant_failures': int(ohlc_bad.sum()),
                'flat_ohlc_rows': int((raw.open.eq(raw.high) & raw.high.eq(raw.low) & raw.low.eq(raw.close)).sum()),
                'volume_minus_one_share': float(raw.volume.eq(-1).mean()),
                'volume_distinct_values': int(raw.volume.nunique(dropna=False)),
            }
        """
    ),
    md(
        r"""
        ## 2. Causal feature and target construction

        Features below include:

        - repaired Wilder VEI, same-slot VEI percentile/z-score, RSI, ATR, TWAP distance/slope, Donchian position, returns,
          realized volatility, daily volatility, and trend efficiency from the source VEI investigation;
        - multi-horizon persistence, semivariance, volatility acceleration, realized ranges, path efficiency, jumps,
          concentration, quarticity, volatility-of-volatility, and prior-session state from the forward-volatility notebook;
        - FX additions: Tokyo/London/New York clock indicators, London-New York overlap, session-to-date return/range/RV,
          Bollinger z-score, short-horizon return autocorrelation, variance ratio, flat-return share, rolling close-location,
          and later a synchronized four-pair dollar-factor/residual panel.

        Rolling windows require their full number of consecutive one-minute observations. A missing minute makes the return on
        that link null; full-window rolling operations then remain null until the gap leaves the window. Wilder/EMA/RSI state
        restarts after an internal gap and pays its warm-up again. Session-cumulative RV uses available links, session range/return
        use observed prices, and TWAP carries the last observed typical price through missing minutes; the cumulative gap count is
        itself retained as a feature. Same-slot histories use strictly prior sessions with `shift(1)`.

        The target frame also stores the full holding-period high and low from the next-open entry through the configured exit.
        From those extrema it computes long- and short-oriented **maximum favorable excursion (MFE)** and **maximum adverse
        excursion (MAE)** in both log basis points and raw pips. Entry and exit prices are included, so excursions are non-negative.
        These extrema measure opportunity and heat; they do not reveal the order of a stop and target touched inside the same
        one-minute bar, and therefore are not a bracket backtest.
        """
    ),
    code(
        r"""
        def wilder_sma_seeded(values, n):
            x = np.asarray(values, dtype=float)
            out = np.full(len(x), np.nan)
            finite = np.isfinite(x)
            if len(x) < n or not finite[:n].all():
                return out
            out[n - 1] = x[:n].mean()
            for i in range(n, len(x)):
                if np.isfinite(x[i]) and np.isfinite(out[i - 1]):
                    out[i] = out[i - 1] + (x[i] - out[i - 1]) / n
            return out


        def prior_window_percentile(values, lookback=SLOT_LOOKBACK, min_obs=SLOT_MIN_OBS):
            x = np.asarray(values, dtype=float)
            out = np.full(len(x), np.nan)
            for i, value in enumerate(x):
                hist = x[max(0, i - lookback):i]
                hist = hist[np.isfinite(hist)]
                if np.isfinite(value) and len(hist) >= min_obs:
                    out[i] = np.mean(hist < value)
            return out


        def trailing_percentile_including_current(values, lookback=252, min_obs=126):
            x = np.asarray(values, dtype=float)
            out = np.full(len(x), np.nan)
            for i, value in enumerate(x):
                hist = x[max(0, i - lookback + 1):i + 1]
                hist = hist[np.isfinite(hist)]
                if np.isfinite(value) and len(hist) >= min_obs:
                    out[i] = np.mean(hist < value)
            return out


        def exact_lag(series, time, minutes):
            out = series.shift(minutes)
            return out.where(time.shift(minutes).eq(time - pd.Timedelta(minutes=minutes)))


        def rolling_rv(ret, window):
            return np.sqrt(ret.pow(2).rolling(window, min_periods=window).sum())


        FEATURE_GROUPS = {
            'vei': ['vei_raw','vei_smooth_3','vei_pct','vei_z_90'],
            'twap_momentum': ['dist_twap_atr14','twap_slope_5m_atr','rsi_14','ema_spread_atr',
                              'bollinger_z_60m','donchian_pos_15m','donchian_pos_60m'],
            'returns': ['ret_1m','ret_5m','ret_15m','ret_30m','ret_60m','ret_120m','ret_horizon'],
            'volatility_level': ['rv_5m','rv_15m','rv_30m','rv_60m','rv_120m','session_rv',
                                 'prior_session_rv','prior_rv_5d','prior_rv_20d','daily_vol_20','daily_vol_pct'],
            'semivariance': ['neg_semivar_15m','pos_semivar_15m','neg_semivar_30m','pos_semivar_30m',
                             'neg_semivar_60m','pos_semivar_60m','neg_share_30m','neg_share_60m'],
            'acceleration': ['rv_ratio_5_30','rv_ratio_15_60','rv_change_15_blocks','rv_30m_slot_z'],
            'range_path': ['range_rv_15m','range_rv_30m','range_rv_60m','range_ratio_15_60',
                           'path_efficiency_15m','path_efficiency_30m','path_efficiency_60m'],
            'jumps_tails': ['max_abs_ret_15m','max_abs_ret_30m','jump_share_30m','jump_share_60m',
                            'concentration_30m','quarticity_ratio_30m','absret_volvol_30m'],
            'session_state': ['session_return_bp','session_range_bp','session_rv_bp','session_progress',
                              'prior_session_range_bp','prior_session_abs_return_bp','session_gap_bp',
                              'session_gap_count_to_date'],
            'micro_path': ['bar_range_atr','close_location_value','clv_mean_15m','return_autocorr_30m',
                           'variance_ratio_30m','zero_return_share_30m'],
            'calendar': ['utc_time_sin','utc_time_cos','ny_time_sin','ny_time_cos','dow_sin','dow_cos',
                         'tokyo_open','london_open','newyork_open','london_newyork_overlap','rollover_hour'],
            'cross_pair': ['fx_basket_ret_5m','fx_basket_ret_15m','fx_basket_ret_30m',
                           'peer_rv_15m','peer_rv_30m','cross_pair_ret_dispersion_30m',
                           'idiosyncratic_ret_30m'],
        }


        def build_instrument_frame(pair):
            raw, path, reached_boundary = load_pre_holdout_csv(pair)
            raw = assign_fx_session(raw)
            quality = raw_quality_report(pair, raw, path, reached_boundary)
            assert quality['duplicate_ts'] == 0 and quality['out_of_order_ts'] == 0
            assert quality['nonpositive_price_rows'] == 0 and quality['ohlc_invariant_failures'] == 0

            same_session = raw.sdate.eq(raw.sdate.shift(1))
            one_minute = raw.time.diff().eq(pd.Timedelta(minutes=1))
            bad_link = ~(same_session & one_minute)
            internal_gap = same_session & ~one_minute
            raw['has_prior_internal_gap'] = internal_gap.groupby(raw.sdate).cummax()
            raw['session_gap_count_to_date'] = internal_gap.groupby(raw.sdate).cumsum().astype('int16')
            segment = raw['session_gap_count_to_date']

            log_close = np.log(raw.close.astype(float))
            ret1 = log_close.diff().mask(bad_link)
            absret = ret1.abs()
            range_log = np.log(raw.high.astype(float) / raw.low.astype(float)).mask(bad_link)

            # Session-reset true range and textbook Wilder indicators.
            prev_close = raw.close.shift(1).where(same_session)
            tr = pd.concat([(raw.high - raw.low), (raw.high - prev_close).abs(),
                            (raw.low - prev_close).abs()], axis=1).max(axis=1)
            # Restart the recursive state at a gap; the first new-segment TR is the
            # observable bar range, matching the ordinary session-start convention.
            tr = tr.mask(~same_session | internal_gap, raw.high - raw.low)
            segment_keys = [raw.sdate, segment]
            atr10 = tr.groupby(segment_keys, sort=False).transform(lambda s: wilder_sma_seeded(s.to_numpy(), VEI_SHORT))
            atr50 = tr.groupby(segment_keys, sort=False).transform(lambda s: wilder_sma_seeded(s.to_numpy(), VEI_LONG))
            atr14 = tr.groupby(segment_keys, sort=False).transform(lambda s: wilder_sma_seeded(s.to_numpy(), 14))
            vei = atr10 / atr50.replace(0, np.nan)

            # Equal-minute cumulative TWAP from the 17:00 New York session roll.
            typical = (raw.high.astype(float) + raw.low.astype(float) + raw.close.astype(float)) / 3.0
            elapsed = raw.time.diff().dt.total_seconds().div(60).where(same_session, 1.0).clip(lower=1.0)
            held_minutes = (elapsed - 1.0).clip(lower=0.0)
            weighted_typical = typical + held_minutes * typical.shift(1).where(same_session, typical)
            twap_weight = elapsed.groupby(raw.sdate, sort=False).cumsum()
            twap = weighted_typical.groupby(raw.sdate, sort=False).cumsum() / twap_weight

            # Common rolling volatility and path variables on uninterrupted one-minute links.
            rv = {w: rolling_rv(ret1, w) for w in [5, 15, 30, 60, 120]}
            negsv, possv, range_rv, max_abs = {}, {}, {}, {}
            for w in [15, 30, 60]:
                negsv[w] = np.sqrt(ret1.clip(upper=0).pow(2).rolling(w, min_periods=w).sum())
                possv[w] = np.sqrt(ret1.clip(lower=0).pow(2).rolling(w, min_periods=w).sum())
                range_rv[w] = np.sqrt(range_log.pow(2).rolling(w, min_periods=w).sum())
                max_abs[w] = absret.rolling(w, min_periods=w).max()

            rv2_30 = ret1.pow(2).rolling(30, min_periods=30).sum()
            rv2_60 = ret1.pow(2).rolling(60, min_periods=60).sum()
            bipower = absret * absret.shift(1)
            bv30 = (np.pi / 2) * bipower.rolling(29, min_periods=29).sum()
            bv60 = (np.pi / 2) * bipower.rolling(59, min_periods=59).sum()

            # Session-to-date and strictly prior completed-session features.
            session_rv = np.sqrt(ret1.pow(2).groupby(raw.sdate).cumsum())
            first_open = raw.groupby('sdate').open.transform('first').astype(float)
            session_return_bp = 1e4 * np.log(raw.close.astype(float) / first_open)
            session_high = raw.high.groupby(raw.sdate).cummax().astype(float)
            session_low = raw.low.groupby(raw.sdate).cummin().astype(float)
            session_range_bp = 1e4 * np.log(session_high / session_low)

            daily = raw.groupby('sdate', sort=True).agg(
                first_open=('open','first'), last_close=('close','last'), day_high=('high','max'), day_low=('low','min'),
                rows=('time','size'), unique_minutes=('session_minute','nunique'), internal_gaps=('has_prior_internal_gap','max'))
            daily['rth_rv'] = ret1.groupby(raw.sdate).apply(lambda s: np.sqrt(np.nansum(np.square(s.to_numpy(float)))))
            daily['session_range_bp'] = 1e4 * np.log(daily.day_high / daily.day_low)
            daily['session_abs_return_bp'] = 1e4 * np.log(daily.last_close / daily.first_open).abs()
            daily['session_log_return'] = np.log(daily.last_close).diff()
            daily['daily_vol_20'] = daily.session_log_return.rolling(20, min_periods=20).std().shift(1)
            daily['daily_vol_pct'] = trailing_percentile_including_current(daily.daily_vol_20)
            daily['prior_session_rv'] = daily.rth_rv.shift(1)
            daily['prior_rv_5d'] = daily.rth_rv.shift(1).rolling(5, min_periods=5).mean()
            daily['prior_rv_20d'] = daily.rth_rv.shift(1).rolling(20, min_periods=20).mean()
            prior_moves = daily.last_close.diff().abs().shift(1)
            daily['trend_eff_20'] = ((daily.last_close.shift(1) - daily.last_close.shift(21)).abs() /
                                     prior_moves.rolling(20, min_periods=20).sum())
            daily['prior_session_range_bp'] = daily.session_range_bp.shift(1)
            daily['prior_session_abs_return_bp'] = daily.session_abs_return_bp.shift(1)
            daily['prior_close'] = daily.last_close.shift(1)
            session_gap = 1e4 * np.log(daily.first_open / daily.prior_close)

            # Local-clock market-session indicators.
            tokyo = raw.time.dt.tz_convert('Asia/Tokyo')
            london = raw.time.dt.tz_convert('Europe/London')
            newyork = raw.time.dt.tz_convert('America/New_York')
            tokyo_open = tokyo.dt.hour.between(8, 16).astype('int8')
            london_open = london.dt.hour.between(8, 16).astype('int8')
            newyork_open = newyork.dt.hour.between(8, 16).astype('int8')
            ny_min = newyork.dt.hour * 60 + newyork.dt.minute

            # Decision at the completed bar; next-open entry and exact-horizon open exit.
            # Use the explicit minute-of-day rather than integer datetime storage units.
            # Pandas 3 may parse CSV timestamps as datetime64[us], so assuming nanoseconds
            # here would silently select the wrong decision clock.
            decision_mask = (raw.utc_minute % DECISION_INTERVAL_MIN).eq(DECISION_INTERVAL_MIN - 1)
            decision_index = raw.index[decision_mask]
            d = raw.loc[decision_index, ['time','sdate','session_minute','utc_minute','open','high','low','close']].copy()
            d = d.rename(columns={'time':'ts_utc'})
            take = lambda s: pd.Series(s, index=raw.index).loc[decision_index].to_numpy()

            # Targets: entry open t+1 to exit open t+H+1, plus path RV over those H open links.
            h = PREDICTION_WINDOW_MIN
            entry_open = raw.open.shift(-1).astype(float)
            exit_open = raw.open.shift(-(h + 1)).astype(float)
            exact_target = (raw.time.shift(-1).eq(raw.time + pd.Timedelta(minutes=1)) &
                            raw.time.shift(-(h + 1)).eq(raw.time + pd.Timedelta(minutes=h + 1)))
            signed_target = (1e4 * np.log(exit_open / entry_open)).where(exact_target)
            open_ret = np.log(raw.open.astype(float)).diff().where(raw.time.diff().eq(pd.Timedelta(minutes=1)))
            fwd_rv = (1e4 * np.sqrt(open_ret.pow(2).rolling(h, min_periods=h).sum().shift(-(h + 1)))).where(exact_target)

            # Holding-path extrema cover bars t+1 through t+H and explicitly include
            # entry t+1 open and exit t+H+1 open. Reverse rolling avoids future leakage
            # into features: these columns are labels used only for outcome diagnostics.
            holding_high = raw.high.astype(float).shift(-1)
            holding_low = raw.low.astype(float).shift(-1)
            forward_high = holding_high.iloc[::-1].rolling(h, min_periods=h).max().iloc[::-1]
            forward_low = holding_low.iloc[::-1].rolling(h, min_periods=h).min().iloc[::-1]
            forward_high = pd.concat([forward_high, entry_open, exit_open], axis=1).max(axis=1).where(exact_target)
            forward_low = pd.concat([forward_low, entry_open, exit_open], axis=1).min(axis=1).where(exact_target)

            pip_size = PIP_SIZE[pair]
            terminal_return_pips = ((exit_open - entry_open) / pip_size).where(exact_target)
            long_mfe_log_bp = (1e4 * np.log(forward_high / entry_open)).where(exact_target)
            long_mae_log_bp = (1e4 * np.log(entry_open / forward_low)).where(exact_target)
            long_mfe_pips = ((forward_high - entry_open) / pip_size).where(exact_target)
            long_mae_pips = ((entry_open - forward_low) / pip_size).where(exact_target)

            # Indicators and rolling controls.
            delta = raw.close.groupby(raw.sdate).diff().mask(internal_gap)
            avg_gain = delta.clip(lower=0).fillna(0).groupby(segment_keys).transform(lambda s: wilder_sma_seeded(s.to_numpy(), 14))
            avg_loss = (-delta.clip(upper=0)).fillna(0).groupby(segment_keys).transform(lambda s: wilder_sma_seeded(s.to_numpy(), 14))
            rs = avg_gain / avg_loss.replace(0, np.nan)
            rsi = 100 - 100 / (1 + rs)
            rsi = rsi.mask((avg_loss == 0) & (avg_gain == 0), 50).mask((avg_loss == 0) & (avg_gain > 0), 100)
            ema12 = raw.close.groupby(segment_keys).transform(lambda s: s.ewm(span=12, adjust=False, min_periods=12).mean())
            ema26 = raw.close.groupby(segment_keys).transform(lambda s: s.ewm(span=26, adjust=False, min_periods=26).mean())
            exact_current_15 = raw.time.shift(14).eq(raw.time - pd.Timedelta(minutes=14))
            exact_current_60 = raw.time.shift(59).eq(raw.time - pd.Timedelta(minutes=59))
            rolling_mean60 = log_close.rolling(60, min_periods=60).mean().where(exact_current_60)
            rolling_sd60 = log_close.rolling(60, min_periods=60).std(ddof=1).where(exact_current_60)
            clv = (((raw.close - raw.low) - (raw.high - raw.close)) /
                   (raw.high - raw.low).replace(0, np.nan))

            # Populate only the compact decision frame.
            d['pair'] = pair
            d['year'] = d.sdate.dt.year
            d['signed_return_bp'] = take(signed_target)
            d['absolute_return_bp'] = d.signed_return_bp.abs()
            d['forward_rv_bp'] = take(fwd_rv)
            d['entry_open'] = take(entry_open.where(exact_target))
            d['exit_open'] = take(exit_open.where(exact_target))
            d['forward_high'] = take(forward_high)
            d['forward_low'] = take(forward_low)
            d['terminal_return_pips'] = take(terminal_return_pips)
            d['long_mfe_log_bp'] = take(long_mfe_log_bp)
            d['long_mae_log_bp'] = take(long_mae_log_bp)
            d['short_mfe_log_bp'] = d.long_mae_log_bp
            d['short_mae_log_bp'] = d.long_mfe_log_bp
            d['long_mfe_pips'] = take(long_mfe_pips)
            d['long_mae_pips'] = take(long_mae_pips)
            d['short_mfe_pips'] = d.long_mae_pips
            d['short_mae_pips'] = d.long_mfe_pips
            d['twap'] = take(twap)
            d['twap_side'] = np.sign(d.close - d.twap)

            excursion_cols = ['long_mfe_log_bp','long_mae_log_bp','short_mfe_log_bp','short_mae_log_bp',
                              'long_mfe_pips','long_mae_pips','short_mfe_pips','short_mae_pips']
            assert d.loc[d.signed_return_bp.notna(), excursion_cols].notna().all().all()
            assert d[excursion_cols].min().min() >= -1e-9
            valid_excursion = d.signed_return_bp.notna()
            assert (d.loc[valid_excursion,'long_mfe_log_bp'] + 1e-8 >=
                    d.loc[valid_excursion,'signed_return_bp'].clip(lower=0)).all()
            assert (d.loc[valid_excursion,'long_mae_log_bp'] + 1e-8 >=
                    (-d.loc[valid_excursion,'signed_return_bp']).clip(lower=0)).all()
            assert (d.loc[valid_excursion,'long_mfe_pips'] + 1e-6 >=
                    d.loc[valid_excursion,'terminal_return_pips'].clip(lower=0)).all()
            assert (d.loc[valid_excursion,'long_mae_pips'] + 1e-6 >=
                    (-d.loc[valid_excursion,'terminal_return_pips']).clip(lower=0)).all()

            d['vei_raw'] = take(vei)
            d['vei_smooth_3'] = take(vei.groupby(segment_keys).transform(lambda s: s.ewm(span=3, adjust=False).mean()))
            d['dist_twap_atr14'] = take((raw.close - twap) / atr14.replace(0, np.nan))
            d['twap_slope_5m_atr'] = take((twap - exact_lag(twap, raw.time, 5)) / atr14.replace(0, np.nan))
            d['rsi_14'] = take(rsi)
            d['ema_spread_atr'] = take((ema12 - ema26) / atr14.replace(0, np.nan))
            d['bollinger_z_60m'] = take((log_close - rolling_mean60) / rolling_sd60.replace(0, np.nan))

            for lag in [1, 5, 15, 30, 60, 120]:
                d[f'ret_{lag}m'] = take(log_close - exact_lag(log_close, raw.time, lag))
            d['ret_horizon'] = take(log_close - exact_lag(log_close, raw.time, h))
            for w in [5, 15, 30, 60, 120]:
                d[f'rv_{w}m'] = take(rv[w])
            for w in [15, 30, 60]:
                d[f'neg_semivar_{w}m'] = take(negsv[w])
                d[f'pos_semivar_{w}m'] = take(possv[w])
                d[f'range_rv_{w}m'] = take(range_rv[w])
                d[f'max_abs_ret_{w}m'] = take(max_abs[w])
                endpoint = (log_close - exact_lag(log_close, raw.time, w)).abs()
                travelled = absret.rolling(w, min_periods=w).sum()
                d[f'path_efficiency_{w}m'] = take(endpoint / travelled.replace(0, np.nan))
            d['neg_share_30m'] = take(negsv[30].pow(2) / rv[30].pow(2).replace(0, np.nan))
            d['neg_share_60m'] = take(negsv[60].pow(2) / rv[60].pow(2).replace(0, np.nan))
            d['rv_ratio_5_30'] = take(rv[5] / rv[30].replace(0, np.nan))
            d['rv_ratio_15_60'] = take(rv[15] / rv[60].replace(0, np.nan))
            d['rv_change_15_blocks'] = take(rv[15] / exact_lag(rv[15], raw.time, 15).replace(0, np.nan))
            d['range_ratio_15_60'] = take(range_rv[15] / range_rv[60].replace(0, np.nan))
            d['jump_share_30m'] = take((rv2_30 - bv30).clip(lower=0) / rv2_30.replace(0, np.nan))
            d['jump_share_60m'] = take((rv2_60 - bv60).clip(lower=0) / rv2_60.replace(0, np.nan))
            d['concentration_30m'] = take(ret1.pow(2).rolling(30, min_periods=30).max() / rv2_30.replace(0, np.nan))
            d['quarticity_ratio_30m'] = take(ret1.pow(4).rolling(30, min_periods=30).sum() / rv2_30.pow(2).replace(0, np.nan))
            d['absret_volvol_30m'] = take(absret.rolling(30, min_periods=30).std(ddof=1))

            prior_high15 = raw.high.shift(1).rolling(15, min_periods=15).max()
            prior_low15 = raw.low.shift(1).rolling(15, min_periods=15).min()
            prior_high60 = raw.high.shift(1).rolling(60, min_periods=60).max()
            prior_low60 = raw.low.shift(1).rolling(60, min_periods=60).min()
            exact_prior_15 = raw.time.shift(15).eq(raw.time - pd.Timedelta(minutes=15))
            exact_prior_60 = raw.time.shift(60).eq(raw.time - pd.Timedelta(minutes=60))
            prior_high15, prior_low15 = prior_high15.where(exact_prior_15), prior_low15.where(exact_prior_15)
            prior_high60, prior_low60 = prior_high60.where(exact_prior_60), prior_low60.where(exact_prior_60)
            d['donchian_pos_15m'] = take((raw.close - prior_low15) / (prior_high15 - prior_low15).replace(0, np.nan))
            d['donchian_pos_60m'] = take((raw.close - prior_low60) / (prior_high60 - prior_low60).replace(0, np.nan))
            d['bar_range_atr'] = take((raw.high - raw.low) / atr14.replace(0, np.nan))
            d['close_location_value'] = take(clv)
            d['clv_mean_15m'] = take(clv.rolling(15, min_periods=15).mean().where(exact_current_15))
            d['return_autocorr_30m'] = take(ret1.rolling(30, min_periods=30).corr(ret1.shift(1)))
            endpoint30 = (log_close - exact_lag(log_close, raw.time, 30))
            d['variance_ratio_30m'] = take(endpoint30.pow(2) / rv2_30.replace(0, np.nan))
            d['zero_return_share_30m'] = take(ret1.eq(0).where(ret1.notna()).rolling(30, min_periods=30).mean())

            d['session_rv'] = take(session_rv)
            d['session_return_bp'] = take(session_return_bp)
            d['session_range_bp'] = take(session_range_bp)
            d['session_rv_bp'] = 1e4 * d.session_rv
            d['session_progress'] = d.session_minute / 1440.0
            for col in ['prior_session_rv','prior_rv_5d','prior_rv_20d','daily_vol_20','daily_vol_pct',
                        'trend_eff_20','prior_session_range_bp','prior_session_abs_return_bp']:
                d[col] = d.sdate.map(daily[col])
            d['session_gap_bp'] = d.sdate.map(session_gap)
            d['session_gap_count_to_date'] = take(raw.session_gap_count_to_date)

            utc_fraction = raw.utc_minute / 1440.0
            ny_fraction = ny_min / 1440.0
            dow = raw.time.dt.dayofweek
            d['utc_time_sin'] = take(np.sin(2*np.pi*utc_fraction))
            d['utc_time_cos'] = take(np.cos(2*np.pi*utc_fraction))
            d['ny_time_sin'] = take(np.sin(2*np.pi*ny_fraction))
            d['ny_time_cos'] = take(np.cos(2*np.pi*ny_fraction))
            d['dow_sin'] = take(np.sin(2*np.pi*dow/5))
            d['dow_cos'] = take(np.cos(2*np.pi*dow/5))
            d['tokyo_open'] = take(tokyo_open)
            d['london_open'] = take(london_open)
            d['newyork_open'] = take(newyork_open)
            d['london_newyork_overlap'] = d.london_open * d.newyork_open
            d['rollover_hour'] = take(ny_min.between(16*60+30, 17*60+30).astype('int8'))

            # Strictly prior same-slot normalizations and target baselines.
            d = d.sort_values(['sdate','session_minute']).reset_index(drop=True)
            d['vei_pct'] = d.groupby('session_minute').vei_raw.transform(prior_window_percentile)
            vei_mean = d.groupby('session_minute').vei_raw.transform(
                lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).mean())
            vei_sd = d.groupby('session_minute').vei_raw.transform(
                lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).std(ddof=1))
            d['vei_z_90'] = (d.vei_raw - vei_mean) / vei_sd.replace(0, np.nan)
            rv30_mean = d.groupby('session_minute').rv_30m.transform(
                lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).mean())
            rv30_sd = d.groupby('session_minute').rv_30m.transform(
                lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).std(ddof=1))
            d['rv_30m_slot_z'] = (d.rv_30m - rv30_mean) / rv30_sd.replace(0, np.nan)
            d['abs_target_slot_median_90'] = d.groupby('session_minute').absolute_return_bp.transform(
                lambda s: s.shift(1).rolling(SLOT_LOOKBACK, min_periods=SLOT_MIN_OBS).median())
            d['normalized_absolute_target'] = d.absolute_return_bp / d.abs_target_slot_median_90.replace(0, np.nan)

            # Rule 9a counts for gaps and under-populated rolling history.
            session_table = raw.groupby('sdate').agg(rows=('time','size'), unique_minutes=('session_minute','nunique'),
                                                      first_minute=('session_minute','min'), last_minute=('session_minute','max'),
                                                      internal_gap_seen=('has_prior_internal_gap','max'))
            quality.update({
                'decision_rows': len(d), 'valid_targets': int(d.signed_return_bp.notna().sum()),
                'target_missing': int(d.signed_return_bp.isna().sum()),
                'excursion_missing': int(d.long_mfe_log_bp.isna().sum()),
                'sessions_with_internal_gap': int(session_table.internal_gap_seen.sum()),
                'median_session_rows': float(session_table.rows.median()),
                'min_session_rows': int(session_table.rows.min()),
                'max_session_rows': int(session_table.rows.max()),
                'median_first_session_minute': float(session_table.first_minute.median()),
                'median_last_session_minute': float(session_table.last_minute.median()),
                'vei_warmup_missing': int(d.vei_raw.isna().sum()),
                'vei_slot_history_missing': int(d.vei_z_90.isna().sum()),
                'target_slot_history_missing': int(d.abs_target_slot_median_90.isna().sum()),
                'decision_rows_after_internal_gap': int(d.session_gap_count_to_date.gt(0).sum()),
            })
            assert d.ts_utc.max() < HOLDOUT_START and d.sdate.max() < HOLDOUT_START.tz_localize(None)

            del raw, daily, ret1, absret, range_log, rv, negsv, possv, range_rv, max_abs
            gc.collect()
            return d, quality, session_table
        """
    ),
    code(
        r"""
        frames, quality_rows, session_tables = {}, [], {}
        for pair in ACTIVE_PAIRS:
            print(f'Building {pair} ...')
            frames[pair], quality, session_tables[pair] = build_instrument_frame(pair)
            quality_rows.append(quality)
            print(f'  {len(frames[pair]):,} decisions; {frames[pair].sdate.nunique():,} sessions; '
                  f'{frames[pair].sdate.min().date()} to {frames[pair].sdate.max().date()}')

        quality_report = pd.DataFrame(quality_rows).set_index('pair')
        display(quality_report.T)
        assert quality_report.duplicate_ts.eq(0).all()
        assert quality_report.out_of_order_ts.eq(0).all()
        assert quality_report.ohlc_invariant_failures.eq(0).all()
        assert all(f.ts_utc.max() < HOLDOUT_START for f in frames.values())
        print('Holdout seal passed: no retained decision is from 2024 onward.')
        """
    ),
    md(
        r"""
        ### 2.1 Synchronized cross-pair dollar-factor features

        All four pairs quote USD second, so their equal-weighted past return is a simple common "foreign currencies versus USD"
        factor. Each pair receives the synchronized basket return, peer-average realized volatility, cross-sectional dispersion,
        and its own residual return. Exact timestamp joins forbid stale cross-pair values. These are contemporaneously observable
        at the decision close; they do not claim one pair leads another.
        """
    ),
    code(
        r"""
        if len(frames) >= 2:
            for horizon in [5, 15, 30]:
                wide = pd.concat({p: f.set_index('ts_utc')[f'ret_{horizon}m'] for p, f in frames.items()}, axis=1)
                basket = wide.mean(axis=1, skipna=True).rename(f'fx_basket_ret_{horizon}m')
                dispersion = wide.std(axis=1, ddof=1).rename(f'cross_pair_ret_dispersion_{horizon}m')
                for pair in frames:
                    frames[pair] = frames[pair].merge(basket, left_on='ts_utc', right_index=True, how='left', validate='one_to_one')
                    if horizon == 30:
                        frames[pair] = frames[pair].merge(dispersion, left_on='ts_utc', right_index=True, how='left', validate='one_to_one')
            for horizon in [15, 30]:
                wide_rv = pd.concat({p: f.set_index('ts_utc')[f'rv_{horizon}m'] for p, f in frames.items()}, axis=1)
                for pair in frames:
                    peer = wide_rv.drop(columns=pair).mean(axis=1, skipna=True).rename(f'peer_rv_{horizon}m')
                    frames[pair] = frames[pair].merge(peer, left_on='ts_utc', right_index=True, how='left', validate='one_to_one')
            for pair in frames:
                frames[pair]['idiosyncratic_ret_30m'] = frames[pair].ret_30m - frames[pair].fx_basket_ret_30m
        else:
            for pair in frames:
                for col in FEATURE_GROUPS['cross_pair']:
                    frames[pair][col] = np.nan

        feature_columns = list(dict.fromkeys(c for cols in FEATURE_GROUPS.values() for c in cols))
        for pair, frame in frames.items():
            missing = [c for c in feature_columns if c not in frame]
            assert not missing, f'{pair} missing feature columns: {missing}'
            assert frame.ts_utc.max() < HOLDOUT_START
        print(f'{len(feature_columns)} numeric features across {len(FEATURE_GROUPS)} families.')
        """
    ),
    md(
        r"""
        ## 3. Feature-stage data-quality gate

        Coverage is reported overall, by year, and by New-York-session minute. `min_slot_coverage` exposes a hidden clock filter;
        `first_year_coverage` exposes rolling warm-up. Missing rolling windows are kept as nulls and quantified rather than
        silently dropping rows. Model imputation is fit only on each training period; IC uses pairwise-complete rows and reports `n`.
        """
    ),
    code(
        r"""
        coverage_rows = []
        for pair, frame in frames.items():
            first_year, last_year = frame.year.min(), frame.year.max()
            for feature in feature_columns:
                by_slot = frame.groupby('session_minute')[feature].apply(lambda s: s.notna().mean())
                coverage_rows.append({
                    'pair': pair, 'feature': feature, 'family': next(k for k,v in FEATURE_GROUPS.items() if feature in v),
                    'coverage': frame[feature].notna().mean(),
                    'first_year_coverage': frame.loc[frame.year.eq(first_year), feature].notna().mean(),
                    'last_year_coverage': frame.loc[frame.year.eq(last_year), feature].notna().mean(),
                    'min_slot_coverage': by_slot.min(), 'max_slot_coverage': by_slot.max(),
                    'slot_coverage_spread': by_slot.max() - by_slot.min(),
                })
        coverage_table = pd.DataFrame(coverage_rows)
        display(coverage_table.sort_values(['pair','coverage']).style.format({
            'coverage':'{:.1%}','first_year_coverage':'{:.1%}','last_year_coverage':'{:.1%}',
            'min_slot_coverage':'{:.1%}','max_slot_coverage':'{:.1%}','slot_coverage_spread':'{:.1%}'}))

        target_coverage = pd.DataFrame({p: f.groupby('year').signed_return_bp.apply(lambda s:s.notna().mean())
                                        for p,f in frames.items()})
        display(target_coverage.style.format('{:.1%}'))
        print('Target missingness comes from exact-window gaps or the file/session boundary; no shorter substitute horizon is used.')
        """
    ),
    md(
        r"""
        ## 4. Signed and absolute return IC screen

        The primary association statistic is **within-session-slot Spearman IC**: feature and target ranks are formed separately
        within each New-York-session decision minute, then pooled. This removes the deterministic intraday volatility curve.
        Pooled IC is retained for comparison. Yearly sign consistency, mean target by feature quintile, and the q5-minus-q1 mean
        spread are also shown.

        Fixed-rank 90% confidence intervals resample complete FX sessions. To keep the notebook practical, intervals are computed
        for the top `TOP_FEATURES_FOR_BOOTSTRAP` features per pair/target after the point-estimate screen. They are descriptive
        search intervals, not multiple-testing-adjusted confirmation.
        """
    ),
    code(
        r"""
        def corr_from_sums(values):
            n, sx, sy, sxx, syy, sxy = values
            cov = sxy - sx * sy / n
            vx = sxx - sx * sx / n
            vy = syy - sy * sy / n
            return cov / np.sqrt(vx * vy) if n > 2 and vx > 0 and vy > 0 else np.nan


        def within_slot_rank_frame(frame, feature, target):
            z = frame[['sdate','session_minute',feature,target]].dropna().copy()
            z['rx'] = z.groupby('session_minute')[feature].rank(method='average', pct=True)
            z['ry'] = z.groupby('session_minute')[target].rank(method='average', pct=True)
            return z


        def fixed_rank_session_block_ci(frame, feature, target, draws, rng):
            z = within_slot_rank_frame(frame, feature, target)
            if len(z) < 100 or z.rx.nunique() < 3:
                return np.nan, np.nan, np.nan
            z['rxx'], z['ryy'], z['rxy'] = z.rx*z.rx, z.ry*z.ry, z.rx*z.ry
            g = z.groupby('sdate', sort=False)
            per = np.column_stack([g.size().to_numpy(float), g.rx.sum(), g.ry.sum(),
                                   g.rxx.sum(), g.ryy.sum(), g.rxy.sum()])
            real = corr_from_sums(per.sum(axis=0))
            boot = np.empty(draws)
            for b in range(draws):
                counts = np.bincount(rng.integers(0, len(per), len(per)), minlength=len(per))
                boot[b] = corr_from_sums((per * counts[:,None]).sum(axis=0))
            return real, *np.nanpercentile(boot, [5,95])


        def point_ic_row(frame, feature, target):
            z = frame[['year','session_minute',feature,target]].dropna().copy()
            if len(z) < 100 or z[feature].nunique() < 5:
                return None
            pooled = spearmanr(z[feature], z[target]).statistic
            z['rx'] = z.groupby('session_minute')[feature].rank(method='average', pct=True)
            z['ry'] = z.groupby('session_minute')[target].rank(method='average', pct=True)
            within = z.rx.corr(z.ry)
            yearly = z.groupby('year').apply(
                lambda g: spearmanr(g[feature], g[target]).statistic if g[feature].nunique() >= 3 else np.nan,
                include_groups=False)
            z['q'] = pd.qcut(z[feature].rank(method='first'), 5, labels=False, duplicates='drop')
            means = z.groupby('q')[target].mean()
            return {
                'n': len(z), 'coverage': len(z)/len(frame), 'pooled_ic': pooled, 'within_slot_ic': within,
                'yearly_positive_fraction': (yearly > 0).mean(),
                'yearly_same_sign_fraction': max((yearly > 0).mean(), (yearly < 0).mean()),
                'q1_mean': means.iloc[0], 'q5_mean': means.iloc[-1], 'q5_minus_q1_mean': means.iloc[-1]-means.iloc[0],
            }


        target_map = {'signed':'signed_return_bp', 'absolute':'absolute_return_bp'}
        screen_rows = []
        for pair, frame in frames.items():
            for target_kind, target in target_map.items():
                for feature in feature_columns:
                    row = point_ic_row(frame, feature, target)
                    if row is not None:
                        row.update({'pair':pair,'target_kind':target_kind,'feature':feature,
                                    'family':next(k for k,v in FEATURE_GROUPS.items() if feature in v)})
                        screen_rows.append(row)
        ic_screen = pd.DataFrame(screen_rows)
        ic_screen['ci_lo'] = np.nan
        ic_screen['ci_hi'] = np.nan

        boot_rng = np.random.default_rng(RANDOM_SEED)
        for (pair,target_kind), group in ic_screen.groupby(['pair','target_kind']):
            top = group.assign(score=group.within_slot_ic.abs()).nlargest(TOP_FEATURES_FOR_BOOTSTRAP,'score')
            target = target_map[target_kind]
            for idx, row in top.iterrows():
                ic, lo, hi = fixed_rank_session_block_ci(frames[pair], row.feature, target, IC_BOOT_DRAWS, boot_rng)
                ic_screen.loc[idx, ['within_slot_ic','ci_lo','ci_hi']] = [ic,lo,hi]

        for pair in frames:
            for target_kind in target_map:
                view = ic_screen.loc[(ic_screen.pair.eq(pair)) & (ic_screen.target_kind.eq(target_kind))].copy()
                view['abs_ic'] = view.within_slot_ic.abs()
                print(f'\n{pair} — {target_kind} return, strongest within-slot ICs')
                display(view.nlargest(PLOT_TOP_N,'abs_ic').drop(columns='abs_ic').set_index('feature').style.format({
                    'coverage':'{:.1%}','pooled_ic':'{:+.4f}','within_slot_ic':'{:+.4f}','ci_lo':'{:+.4f}','ci_hi':'{:+.4f}',
                    'yearly_positive_fraction':'{:.0%}','yearly_same_sign_fraction':'{:.0%}',
                    'q1_mean':'{:+.3f}','q5_mean':'{:+.3f}','q5_minus_q1_mean':'{:+.3f}'}))
        """
    ),
    code(
        r"""
        # Cross-pair replication summary. Signed features may be consistently positive or negative;
        # absolute-return features are most useful when positive across all pairs.
        replication_rows = []
        for (target_kind, feature), g in ic_screen.groupby(['target_kind','feature']):
            if len(g) != len(frames):
                continue
            vals = g.set_index('pair').within_slot_ic
            replication_rows.append({
                'target_kind':target_kind,'feature':feature,'family':g.family.iloc[0],
                'median_ic':vals.median(),'median_abs_ic':vals.abs().median(),'worst_abs_ic':vals.abs().min(),
                'all_positive':(vals>0).all(),'all_negative':(vals<0).all(),
                'same_sign_all_pairs':(vals>0).all() or (vals<0).all(),
                'min_yearly_same_sign_fraction':g.yearly_same_sign_fraction.min(),
                **{f'{p}_ic':vals.get(p,np.nan) for p in ACTIVE_PAIRS},
            })
        replication = pd.DataFrame(replication_rows)

        for target_kind in target_map:
            r = replication.loc[replication.target_kind.eq(target_kind)].copy()
            if target_kind == 'absolute':
                r['replication_score'] = np.where(r.all_positive, r.worst_abs_ic, -r.median_abs_ic)
            else:
                r['replication_score'] = np.where(r.same_sign_all_pairs, r.worst_abs_ic, -r.median_abs_ic)
            print(f'\nCross-pair replication — {target_kind} return')
            display(r.sort_values('replication_score',ascending=False).head(30).set_index('feature').style.format({
                c:'{:+.4f}' for c in r.columns if c.endswith('_ic') or c in ['median_ic','median_abs_ic','worst_abs_ic','replication_score']}))

        fig, axes = plt.subplots(1, 2, figsize=(16, 8))
        for ax, target_kind in zip(axes, ['signed','absolute']):
            p = replication.loc[replication.target_kind.eq(target_kind)].nlargest(PLOT_TOP_N,'median_abs_ic').sort_values('median_abs_ic')
            ax.barh(p.feature, p.median_ic, color=np.where(p.median_ic>=0,'tab:blue','tab:red'))
            ax.axvline(0,color='black',lw=1); ax.set_title(f'Median within-slot IC across pairs: {target_kind}')
        plt.tight_layout(); plt.show()
        """
    ),
    code(
        r"""
        # Parameterized single-feature diagnostic. Change these without touching the holdout seal.
        FEATURE_TO_EXPLORE = 'rsi_14'
        PAIR_TO_EXPLORE = ACTIVE_PAIRS[0]
        assert FEATURE_TO_EXPLORE in feature_columns and PAIR_TO_EXPLORE in frames

        explore = frames[PAIR_TO_EXPLORE][['year',FEATURE_TO_EXPLORE,'signed_return_bp','absolute_return_bp']].dropna().copy()
        explore['quintile'] = pd.qcut(explore[FEATURE_TO_EXPLORE].rank(method='first'),5,labels=False)
        display(explore.groupby('quintile').agg(
            n=('signed_return_bp','size'), feature_mean=(FEATURE_TO_EXPLORE,'mean'),
            signed_bp=('signed_return_bp','mean'), absolute_bp=('absolute_return_bp','mean')))

        yearly_feature = explore.groupby('year').apply(lambda g: pd.Series({
            'signed_ic':spearmanr(g[FEATURE_TO_EXPLORE],g.signed_return_bp).statistic,
            'absolute_ic':spearmanr(g[FEATURE_TO_EXPLORE],g.absolute_return_bp).statistic}), include_groups=False)
        yearly_feature.plot(marker='o',figsize=(12,4),title=f'{PAIR_TO_EXPLORE}: yearly IC — {FEATURE_TO_EXPLORE}')
        plt.axhline(0,color='black',lw=1); plt.tight_layout(); plt.show()

        # Explicit feature-to-position mapping for excursion/edge exploration.
        # IC alone does not define a trade side. These defaults test RSI mean reversion:
        # long at/below 30, short at/above 70. Quantile thresholds are discovery-only.
        EDGE_ORIENTATION = 'mean_reversion'       # 'mean_reversion' or 'momentum'
        EDGE_THRESHOLD_MODE = 'fixed'             # 'fixed' or exploratory 'quantile'
        EDGE_LOW_THRESHOLD = 30.0
        EDGE_HIGH_THRESHOLD = 70.0
        EDGE_TAIL_FRACTION = 0.20
        EDGE_TOUCH_LEVELS_PIPS = [2.0, 5.0, 10.0]

        assert EDGE_ORIENTATION in {'mean_reversion','momentum'}
        assert EDGE_THRESHOLD_MODE in {'fixed','quantile'}
        assert 0 < EDGE_TAIL_FRACTION < 0.5

        outcome_cols = [
            'sdate','year',FEATURE_TO_EXPLORE,'signed_return_bp','absolute_return_bp','terminal_return_pips',
            'long_mfe_log_bp','long_mae_log_bp','short_mfe_log_bp','short_mae_log_bp',
            'long_mfe_pips','long_mae_pips','short_mfe_pips','short_mae_pips',
        ]
        edge_universe = frames[PAIR_TO_EXPLORE][outcome_cols].dropna().copy()
        edge_universe['quintile'] = pd.qcut(
            edge_universe[FEATURE_TO_EXPLORE].rank(method='first'),5,labels=False)
        excursion_by_quintile = edge_universe.groupby('quintile').agg(
            n=('signed_return_bp','size'), feature_mean=(FEATURE_TO_EXPLORE,'mean'),
            signed_log_bp=('signed_return_bp','mean'), absolute_log_bp=('absolute_return_bp','mean'),
            long_mfe_log_bp=('long_mfe_log_bp','mean'),long_mae_log_bp=('long_mae_log_bp','mean'),
            long_mfe_pips=('long_mfe_pips','mean'),long_mae_pips=('long_mae_pips','mean'))
        print('Excursions by descriptive full-sample feature quintile (not causal thresholds):')
        display(excursion_by_quintile.style.format('{:.3f}'))

        if EDGE_THRESHOLD_MODE == 'fixed':
            edge_low, edge_high = EDGE_LOW_THRESHOLD, EDGE_HIGH_THRESHOLD
            threshold_note = 'fixed thresholds (causal if genuinely specified before the test period)'
        else:
            edge_low = edge_universe[FEATURE_TO_EXPLORE].quantile(EDGE_TAIL_FRACTION)
            edge_high = edge_universe[FEATURE_TO_EXPLORE].quantile(1 - EDGE_TAIL_FRACTION)
            threshold_note = 'full-sample exploratory quantiles (NON-CAUSAL; freeze or estimate on prior data before testing)'

        low_side, high_side = ((1, -1) if EDGE_ORIENTATION == 'mean_reversion' else (-1, 1))
        edge_universe['research_side'] = np.select(
            [edge_universe[FEATURE_TO_EXPLORE].le(edge_low), edge_universe[FEATURE_TO_EXPLORE].ge(edge_high)],
            [low_side, high_side], default=0).astype('int8')
        edge = edge_universe.loc[edge_universe.research_side.ne(0)].copy()
        edge['position'] = np.where(edge.research_side.gt(0),'long','short')
        edge['pnl_log_bp'] = edge.research_side * edge.signed_return_bp
        edge['pnl_pips'] = edge.research_side * edge.terminal_return_pips
        edge['mfe_log_bp'] = np.where(edge.research_side.gt(0),edge.long_mfe_log_bp,edge.short_mfe_log_bp)
        edge['mae_log_bp'] = np.where(edge.research_side.gt(0),edge.long_mae_log_bp,edge.short_mae_log_bp)
        edge['mfe_pips'] = np.where(edge.research_side.gt(0),edge.long_mfe_pips,edge.short_mfe_pips)
        edge['mae_pips'] = np.where(edge.research_side.gt(0),edge.long_mae_pips,edge.short_mae_pips)
        edge['giveback_log_bp'] = edge.mfe_log_bp - edge.pnl_log_bp
        edge['giveback_pips'] = edge.mfe_pips - edge.pnl_pips

        print(f'Edge rule: {EDGE_ORIENTATION}; {FEATURE_TO_EXPLORE} <= {edge_low:.4f} uses side {low_side:+d}, '
              f'{FEATURE_TO_EXPLORE} >= {edge_high:.4f} uses side {high_side:+d}.')
        print(f'Threshold provenance: {threshold_note}. Excursions are gross midpoint-path diagnostics, not fills.')

        def session_cluster_t(values, sessions):
            z = pd.DataFrame({'x':values,'session':sessions}).dropna()
            n, blocks = len(z), z.session.nunique()
            if n < 2 or blocks < 2:
                return np.nan
            mean = z.x.mean()
            block_score = (z.x - mean).groupby(z.session).sum()
            se = np.sqrt((blocks / (blocks - 1)) * np.square(block_score).sum()) / n
            return mean / se if se > 0 else np.nan

        def edge_summary_row(g):
            losses = -g.loc[g.pnl_log_bp.lt(0),'pnl_log_bp'].sum()
            p05 = g.pnl_log_bp.quantile(0.05)
            return pd.Series({
                'signals':len(g),'sessions':g.sdate.nunique(),
                'signals_per_session':len(g)/max(g.sdate.nunique(),1),
                'mean_pnl_log_bp':g.pnl_log_bp.mean(),'median_pnl_log_bp':g.pnl_log_bp.median(),
                'session_cluster_t':session_cluster_t(g.pnl_log_bp,g.sdate),
                'win_rate':g.pnl_log_bp.gt(0).mean(),
                'profit_factor':g.loc[g.pnl_log_bp.gt(0),'pnl_log_bp'].sum()/losses if losses>0 else np.nan,
                'p05_pnl_log_bp':p05,'expected_shortfall_5_log_bp':g.loc[g.pnl_log_bp.le(p05),'pnl_log_bp'].mean(),
                'mean_pnl_pips':g.pnl_pips.mean(),'median_pnl_pips':g.pnl_pips.median(),
            })

        def excursion_summary_row(g):
            return pd.Series({
                'signals':len(g),
                'mean_mfe_log_bp':g.mfe_log_bp.mean(),'median_mfe_log_bp':g.mfe_log_bp.median(),
                'p90_mfe_log_bp':g.mfe_log_bp.quantile(0.90),
                'mean_mae_log_bp':g.mae_log_bp.mean(),'median_mae_log_bp':g.mae_log_bp.median(),
                'p90_mae_log_bp':g.mae_log_bp.quantile(0.90),
                'mean_mfe_pips':g.mfe_pips.mean(),'median_mfe_pips':g.mfe_pips.median(),
                'p90_mfe_pips':g.mfe_pips.quantile(0.90),
                'mean_mae_pips':g.mae_pips.mean(),'median_mae_pips':g.mae_pips.median(),
                'p90_mae_pips':g.mae_pips.quantile(0.90),
                'mean_mfe_mae_ratio':g.mfe_log_bp.mean()/g.mae_log_bp.mean() if g.mae_log_bp.mean()>0 else np.nan,
                'mean_capture_of_mfe':g.pnl_log_bp.mean()/g.mfe_log_bp.mean() if g.mfe_log_bp.mean()>0 else np.nan,
                'mean_giveback_log_bp':g.giveback_log_bp.mean(),'mean_giveback_pips':g.giveback_pips.mean(),
            })

        edge_groups = [('all',edge),('long',edge.loc[edge.position.eq('long')]),('short',edge.loc[edge.position.eq('short')])]
        edge_summary = pd.DataFrame({name:edge_summary_row(g) for name,g in edge_groups}).T
        excursion_summary = pd.DataFrame({name:excursion_summary_row(g) for name,g in edge_groups}).T
        display(edge_summary.style.format({
            'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}','profit_factor':'{:.3f}',
            **{c:'{:+.3f}' for c in edge_summary.columns if c not in ['signals','sessions','win_rate','profit_factor']}}))
        display(excursion_summary.style.format({c:('{:,.0f}' if c=='signals' else '{:.3f}') for c in excursion_summary.columns}))

        yearly_edge = pd.DataFrame([
            {'year':year,**edge_summary_row(g).to_dict(),
             'mean_mfe_log_bp':g.mfe_log_bp.mean(),'mean_mae_log_bp':g.mae_log_bp.mean(),
             'mfe_mae_ratio':g.mfe_log_bp.mean()/g.mae_log_bp.mean() if g.mae_log_bp.mean()>0 else np.nan}
            for year,g in edge.groupby('year')]).set_index('year')
        display(yearly_edge.style.format({
            'signals':'{:,.0f}','sessions':'{:,.0f}','win_rate':'{:.1%}','profit_factor':'{:.3f}',
            **{c:'{:+.3f}' for c in yearly_edge.columns if c not in ['signals','sessions','win_rate','profit_factor']}}))

        touch_rows = []
        for group_name, g in edge_groups:
            for level in EDGE_TOUCH_LEVELS_PIPS:
                favorable = g.mfe_pips.ge(level)
                adverse = g.mae_pips.ge(level)
                touch_rows.append({
                    'side':group_name,'level_pips':level,'signals':len(g),
                    'favorable_touch':favorable.mean(),'adverse_touch':adverse.mean(),
                    'both_touch_order_unknown':(favorable & adverse).mean(),
                })
        excursion_touch_rates = pd.DataFrame(touch_rows).set_index(['side','level_pips'])
        display(excursion_touch_rates.style.format({
            'signals':'{:,.0f}','favorable_touch':'{:.1%}','adverse_touch':'{:.1%}',
            'both_touch_order_unknown':'{:.1%}'}))
        """
    ),
    md(
        r"""
        ## 5. Fixed TWAP-side baseline strategy

        At every decision close, buy if price is above cumulative session TWAP and sell if below. Fill at the next minute's open
        and exit at the exact configured horizon open. With the default equal decision interval and horizon, positions do not
        overlap. Daily/session P&L is the **sum** of position returns. There are no stops, targets, or intrabar path assumptions.

        Since the files contain midpoint prices and no spreads, the primary output is gross basis points. The cost grid is a
        hypothetical round-trip deduction per trade and must not be mistaken for a calibrated spread/slippage model.
        """
    ),
    code(
        r"""
        def twap_strategy_stats(trades, all_sessions, cost_bp=0.0):
            t = trades.copy()
            t['net_bp'] = t.gross_bp - cost_bp
            day = t.groupby('sdate').net_bp.sum().reindex(pd.DatetimeIndex(all_sessions),fill_value=0.0)
            sd = day.std(ddof=1)
            equity = day.cumsum(); drawdown = equity - equity.cummax()
            gains = t.loc[t.net_bp>0,'net_bp'].sum(); losses = -t.loc[t.net_bp<0,'net_bp'].sum()
            return pd.Series({
                'trades':len(t),'sessions':len(day),'trades_per_session':len(t)/max(len(day),1),
                'gross_bp_total':t.gross_bp.sum(),'mean_gross_bp_trade':t.gross_bp.mean(),
                'cost_bp_trade':cost_bp,'net_bp_total':t.net_bp.sum(),'mean_net_bp_trade':t.net_bp.mean(),
                'win_rate':(t.net_bp>0).mean(),'profit_factor':gains/losses if losses>0 else np.nan,
                'daily_sharpe':np.sqrt(252)*day.mean()/sd if sd>0 else np.nan,
                'daily_t':day.mean()/(sd/np.sqrt(len(day))) if sd>0 else np.nan,
                'max_drawdown_bp':-drawdown.min(),'worst_session_bp':day.min(),'best_session_bp':day.max(),
            })

        strategy_rows, yearly_strategy_rows, cost_rows = [], [], []
        strategy_trades = {}
        for pair, frame in frames.items():
            t = frame.loc[frame.signed_return_bp.notna() & frame.twap_side.ne(0),
                          ['sdate','year','session_minute','twap_side','signed_return_bp']].copy()
            t['gross_bp'] = t.twap_side * t.signed_return_bp
            strategy_trades[pair] = t
            stats = twap_strategy_stats(t, frame.sdate.drop_duplicates(), cost_bp=0)
            stats['pair'] = pair; stats['era'] = 'all_pre_2024_exploration'; strategy_rows.append(stats)
            for era, mask in [('early_through_2019',t.year<=2019),('late_2020_2023',t.year.between(2020,2023))]:
                sessions = frame.loc[(frame.year<=2019) if era.startswith('early') else frame.year.between(2020,2023),'sdate'].drop_duplicates()
                s = twap_strategy_stats(t.loc[mask],sessions,0); s['pair']=pair; s['era']=era; strategy_rows.append(s)
            for year,g in t.groupby('year'):
                s = twap_strategy_stats(g,frame.loc[frame.year.eq(year),'sdate'].drop_duplicates(),0)
                s['pair']=pair; s['year']=year; yearly_strategy_rows.append(s)
            for cost in HYPOTHETICAL_ROUND_TRIP_COST_BP:
                s = twap_strategy_stats(t,frame.sdate.drop_duplicates(),cost)
                s['pair']=pair; cost_rows.append(s)

        strategy_summary = pd.DataFrame(strategy_rows).set_index(['pair','era'])
        display(strategy_summary.style.format('{:.3f}'))
        yearly_strategy = pd.DataFrame(yearly_strategy_rows).set_index(['pair','year'])
        display(yearly_strategy[['trades','mean_gross_bp_trade','daily_sharpe','daily_t','win_rate','max_drawdown_bp']].style.format('{:.3f}'))
        cost_stress = pd.DataFrame(cost_rows)
        display(cost_stress.pivot(index='cost_bp_trade',columns='pair',values=['mean_net_bp_trade','daily_sharpe']).style.format('{:+.3f}'))
        print('Cost stress is sensitivity only. Bid/ask data are required before any net-P&L claim.')
        """
    ),
    md(
        r"""
        ## 6. Pre-holdout expanding-year machine-learning screen

        This stage asks whether nonlinear combinations add predictive value beyond simple controls. Each test year is fit using
        only earlier years. Models and features are fixed; nothing is tuned on a test year.

        - Signed target: zero forecast, Ridge, and histogram gradient boosting; score by signed-return Spearman IC and direction accuracy.
        - Absolute target: causal same-slot median, a two-state range/volatility core, and the full feature set; score by
          absolute-return IC and mean absolute forecast error. This forecast-error metric is spelled out in the output so it
          cannot be confused with maximum adverse excursion in the feature edge lab.
        - The same-year rows are shared by all models for a given pair/target. Heavy label overlap, if configured, is handled only
          approximately by session-level reporting; keep `DECISION_INTERVAL_MIN >= PREDICTION_WINDOW_MIN` for non-overlap.

        These walk-forward results remain pre-2024 exploration. They do not consume the sealed holdout.
        """
    ),
    code(
        r"""
        signed_features = [c for c in feature_columns if c not in ['abs_target_slot_median_90']]
        absolute_core_features = ['abs_target_slot_median_90','range_rv_15m','rv_15m','rv_30m']
        full_features = feature_columns + ['abs_target_slot_median_90']

        def ridge_model():
            return Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True)),
                             ('scale',StandardScaler()),('model',Ridge(alpha=10.0))])

        def hgb_model(seed):
            return Pipeline([('impute',SimpleImputer(strategy='median',add_indicator=True)),
                             ('model',HistGradientBoostingRegressor(
                                 max_iter=35 if SMOKE_MODE else 120, learning_rate=.04,
                                 max_leaf_nodes=15,l2_regularization=2.0,random_state=seed))])

        def run_walkforward(pair, frame):
            pair_signed_features = [c for c in signed_features if frame[c].notna().any()]
            pair_full_features = [c for c in full_features if frame[c].notna().any()]
            years = [y for y in sorted(frame.year.unique()) if ML_FIRST_TEST_YEAR <= y <= ML_LAST_TEST_YEAR]
            pred_parts = []
            for year in years:
                train = frame.loc[frame.year < year].dropna(subset=['signed_return_bp','absolute_return_bp']).copy()
                test = frame.loc[frame.year == year].dropna(subset=['signed_return_bp','absolute_return_bp']).copy()
                if len(train)<5000 or len(test)<500:
                    continue
                part = test[['sdate','session_minute','year','signed_return_bp','absolute_return_bp']].copy()
                part['signed_zero'] = 0.0
                ridge = ridge_model().fit(train[pair_signed_features],train.signed_return_bp)
                part['signed_ridge'] = ridge.predict(test[pair_signed_features])
                hgb_signed = hgb_model(RANDOM_SEED+year).fit(train[pair_signed_features],train.signed_return_bp)
                part['signed_hgb'] = hgb_signed.predict(test[pair_signed_features])
                part['absolute_slot_median'] = test.abs_target_slot_median_90.to_numpy()
                hgb_core = hgb_model(RANDOM_SEED+100+year).fit(
                    train[absolute_core_features],np.log1p(train.absolute_return_bp))
                part['absolute_core'] = np.expm1(hgb_core.predict(test[absolute_core_features])).clip(min=0)
                hgb_full = hgb_model(RANDOM_SEED+200+year).fit(
                    train[pair_full_features],np.log1p(train.absolute_return_bp))
                part['absolute_full'] = np.expm1(hgb_full.predict(test[pair_full_features])).clip(min=0)
                pred_parts.append(part)
            return pd.concat(pred_parts,ignore_index=True) if pred_parts else pd.DataFrame()

        wf_predictions = {}
        if RUN_ML:
            for pair, frame in frames.items():
                print(f'Walk-forward models: {pair}')
                wf_predictions[pair] = run_walkforward(pair,frame)
                assert wf_predictions[pair].year.max() <= 2023
        """
    ),
    code(
        r"""
        def score_prediction(g, prediction, target):
            z = g[[prediction,target,'year']].dropna()
            ic = spearmanr(z[prediction],z[target]).statistic if z[prediction].nunique()>1 else np.nan
            row = {'n':len(z),'spearman_ic':ic,
                   'mean_absolute_error_bp':mean_absolute_error(z[target],z[prediction]),
                   'root_mean_squared_error_bp':np.sqrt(mean_squared_error(z[target],z[prediction]))}
            if target == 'signed_return_bp':
                row['direction_accuracy'] = accuracy_score(z[target]>0,z[prediction]>0)
            yearly = z.groupby('year').apply(
                lambda x:spearmanr(x[prediction],x[target]).statistic if x[prediction].nunique()>1 else np.nan,
                include_groups=False)
            row['positive_year_fraction']=(yearly>0).mean()
            return row

        ml_rows = []
        if RUN_ML:
            for pair,pred in wf_predictions.items():
                for model in ['signed_zero','signed_ridge','signed_hgb']:
                    row=score_prediction(pred,model,'signed_return_bp'); row.update({'pair':pair,'target':'signed','model':model}); ml_rows.append(row)
                for model in ['absolute_slot_median','absolute_core','absolute_full']:
                    row=score_prediction(pred,model,'absolute_return_bp'); row.update({'pair':pair,'target':'absolute','model':model}); ml_rows.append(row)
            ml_summary=pd.DataFrame(ml_rows).set_index(['target','pair','model'])
            display(ml_summary.style.format({'spearman_ic':'{:+.4f}','mae_bp':'{:.3f}','rmse_bp':'{:.3f}',
                                             'direction_accuracy':'{:.1%}','positive_year_fraction':'{:.0%}'}))

            fig,axes=plt.subplots(1,2,figsize=(15,5))
            for ax,target in zip(axes,['signed','absolute']):
                plot=ml_summary.reset_index().loc[lambda x:x.target.eq(target)]
                sns.barplot(data=plot,x='pair',y='spearman_ic',hue='model',ax=ax)
                ax.axhline(0,color='black',lw=1); ax.set_title(f'Pre-2024 walk-forward {target} IC')
            plt.tight_layout(); plt.show()
        """
    ),
    md(
        r"""
        ## 7. Interpretation and holdout protocol

        A feature is only a **candidate** if its effect is economically non-trivial, has the same sign across all four pairs,
        is stable by year and clock slot, and is not merely a duplicate of a cheaper control. For absolute-return predictors,
        compare against trailing realized volatility and the same-slot median. For signed predictors, inspect both rank IC and
        q5-minus-q1 mean return: they can disagree when the effect lives in the tails.

        Before opening the 2024+ holdout:

        1. Freeze the prediction horizon, decision clock, exact feature list, transformations, model, and primary metric.
        2. Write a kill rule and choose at most a very small number of candidates from this screen.
        3. Add bid/ask data before evaluating any net TWAP-strategy claim.
        4. Run the holdout once in a separate confirmation notebook or immutable script. Do not tune and rescore it here.
        5. Use session/block inference; if the horizon exceeds the decision interval, also address overlapping labels explicitly.

        The assertions below are intentionally the last executable gate in the notebook.
        """
    ),
    code(
        r"""
        assert all(frame.ts_utc.max() < HOLDOUT_START for frame in frames.values())
        assert all(frame.sdate.max() < pd.Timestamp('2024-01-01') for frame in frames.values())
        assert quality_report.volume_minus_one_share.eq(1.0).all(), 'Unexpected volume values: revisit the no-volume contract.'
        print('FINAL HOLDOUT CHECK PASSED: all analysis and model predictions are strictly pre-2024.')
        print(f'To explore another horizon, change PREDICTION_WINDOW_MIN (and normally DECISION_INTERVAL_MIN) at the top, then restart and run all.')
        """
    ),
]


nb = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name": "Python 3", "language": "python", "name": "python3"},
        "language_info": {"name": "python", "version": "3.14"},
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}
OUT.write_text(json.dumps(nb, indent=1, ensure_ascii=False), encoding="utf-8")
print(f"Wrote {OUT} ({len(cells)} cells)")
