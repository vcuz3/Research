"""Build the EURUSD/GBPUSD Asian-range sweep exploration notebook.

Run from the workspace root:
    python forex/exploration_1/_build_asian_range_sweep_notebook.py
"""

from pathlib import Path
from textwrap import dedent
import hashlib
import json


ROOT = Path(__file__).resolve().parent
OUT = ROOT / "asian_range_sweep_reversal_exploration.ipynb"


def md(text):
    source = dedent(text).strip() + "\n"
    return {
        "cell_type": "markdown",
        "id": hashlib.sha1(("md\0" + source).encode()).hexdigest()[:12],
        "metadata": {},
        "source": source.splitlines(keepends=True),
    }


def code(text):
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
    md(r"""
        # EURUSD / GBPUSD Asian-range sweeps and intraday reversal

        This notebook investigates the chart observation that EURUSD and GBPUSD often reverse during the trading day and
        that both sides of the Asian-session range are frequently swept before the 17:00 ET rollover.

        ## Research contract

        The trading day and sessions are defined in **America/New_York local time**, so US daylight-saving changes are handled:

        | Session | ET interval | Trading-day minute |
        |---|---:|---:|
        | Asian | 17:00-23:59 | 0-419 |
        | London | 00:00-05:59 | 420-779 |
        | NY_AM | 06:00-11:59 | 780-1139 |
        | NY_PM | 12:00-16:59 | 1140-1439 |

        A **high sweep** means a later minute high is strictly above the completed Asian high; a **low sweep** is defined
        symmetrically. A dual sweep requires both after 00:00 ET. Strict inequality avoids counting a tie as a break. Buffered
        definitions test whether the result survives 0.25, 0.50, and 1.00 pip penetration and range-scaled penetration.

        This is descriptive, pre-2024 exploration rather than an executable strategy. The 2024+ holdout is never retained.
        Minute highs/lows establish that levels were reached, but do not reveal ordering within a bar. Any same-minute two-level
        sequence is labelled ambiguous. Fixed-horizon fade diagnostics enter only at the next minute open and require an exact
        future timestamp. Prices are midpoint OHLC, so spread and slippage are unavailable.

        **Known source limitation:** the files commonly omit minutes around the 17:00 ET maintenance/rollover. Therefore the
        intended 17:00-23:59 range may be under-observed. The notebook reports missing slots and start-time distributions,
        labels the main measure `observed_asian_range`, and contrasts coverage rules and alternative 24-hour anchors.
    """),
    code(r"""
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

        warnings.filterwarnings('ignore', category=FutureWarning)
        sns.set_theme(style='whitegrid', context='notebook')
        pd.set_option('display.max_columns', 200)
        pd.set_option('display.width', 240)

        PAIRS = ['EURUSD', 'GBPUSD']
        EXPLORATION_START = pd.Timestamp('2012-01-01', tz='UTC')
        ERA_SPLIT = pd.Timestamp('2021-01-01', tz='UTC')
        HOLDOUT_START = pd.Timestamp('2024-01-01', tz='UTC')
        PIP_SIZE = {'EURUSD': 0.0001, 'GBPUSD': 0.0001}

        SESSION_BOUNDS = {
            'Asian': (0, 420),
            'London': (420, 780),
            'NY_AM': (780, 1140),
            'NY_PM': (1140, 1440),
        }
        MIN_SESSION_COVERAGE = 0.95
        BUFFER_PIPS = [0.0, 0.25, 0.50, 1.00]
        BUFFER_RANGE_FRACS = [0.00, 0.05, 0.10]
        FADE_HORIZONS_MIN = [15, 30, 60, 120]
        NULL_DRAWS = 500
        BLOCK_BOOT_DRAWS = 1000
        RANDOM_SEED = 20260803
        CSV_CHUNK_ROWS = 750_000
        RUN_ANCHOR_SENSITIVITY = True
        ANCHOR_HOURS_ET = [15, 16, 17, 18, 19]

        SMOKE_MODE = os.getenv('ASIAN_SWEEP_SMOKE', '0') == '1'
        if SMOKE_MODE:
            PAIRS = PAIRS[:1]
            EXPLORATION_START = pd.Timestamp('2022-01-01', tz='UTC')
            NULL_DRAWS = 20
            BLOCK_BOOT_DRAWS = 100
            ANCHOR_HOURS_ET = [16, 17, 18]
        RUN_ANCHOR_SENSITIVITY = RUN_ANCHOR_SENSITIVITY and os.getenv('ASIAN_SWEEP_SKIP_ANCHORS', '0') != '1'

        here = Path.cwd().resolve()
        if here.name == 'exploration_1':
            project_root = here
        elif (here / 'forex' / 'exploration_1').exists():
            project_root = here / 'forex' / 'exploration_1'
        else:
            raise FileNotFoundError('Run from the workspace root or forex/exploration_1.')
        data_dir = project_root.parent / 'data'

        assert EXPLORATION_START < HOLDOUT_START
        assert set(PAIRS) <= set(PIP_SIZE)
        print(f'Pairs={PAIRS}; sample=[{EXPLORATION_START},{HOLDOUT_START}); smoke={SMOKE_MODE}')
        print('HOLDOUT POLICY: 2024+ rows are neither retained nor scored.')
    """),
    md(r"""
        ## 1. Load data and run the raw quality gate

        Loading is chronological and chunked. The gate reports duplicates, order errors, OHLC violations, missing-minute gaps,
        and per-slot availability. The per-slot table is essential here: a daily bar-count average can hide a systematic gap at
        the exact time the reference range begins.
    """),
    code(r"""
        def load_pre_holdout(pair):
            path = data_dir / f'{pair.lower()}_intraday_1min.csv'
            assert path.exists(), f'Missing {path}'
            dtype = {c: 'float32' for c in ['open', 'high', 'low', 'close', 'volume']}
            kept = []
            source_duplicates = source_out_of_order = 0
            previous = None
            boundary_reached = False
            for chunk in pd.read_csv(path, dtype=dtype, parse_dates=['time'], chunksize=CSV_CHUNK_ROWS):
                chunk['time'] = (chunk.time.dt.tz_localize('UTC') if chunk.time.dt.tz is None
                                 else chunk.time.dt.tz_convert('UTC'))
                source_duplicates += int(chunk.time.duplicated().sum())
                source_out_of_order += int((chunk.time.diff().dropna() <= pd.Timedelta(0)).sum())
                if previous is not None and len(chunk) and chunk.time.iloc[0] <= previous:
                    source_out_of_order += 1
                if len(chunk):
                    previous = chunk.time.iloc[-1]
                part = chunk.loc[(chunk.time >= EXPLORATION_START) & (chunk.time < HOLDOUT_START)].copy()
                if len(part):
                    kept.append(part)
                if chunk.time.ge(HOLDOUT_START).any():
                    boundary_reached = True
                    break
            raw = pd.concat(kept, ignore_index=True).sort_values('time', kind='stable').reset_index(drop=True)
            assert len(raw) and raw.time.min() >= EXPLORATION_START and raw.time.max() < HOLDOUT_START
            assert source_duplicates == 0 and source_out_of_order == 0

            ny = raw.time.dt.tz_convert('America/New_York')
            ny_naive = ny.dt.tz_localize(None)
            minute_et = ny.dt.hour * 60 + ny.dt.minute
            raw['trading_date'] = (ny_naive.dt.normalize() +
                                   pd.to_timedelta((minute_et >= 17 * 60).astype(int), unit='D'))
            raw['slot'] = ((minute_et - 17 * 60) % 1440).astype('int16')
            raw['session'] = pd.cut(raw.slot, [-1, 419, 779, 1139, 1439],
                                    labels=['Asian', 'London', 'NY_AM', 'NY_PM'])
            raw['year'] = raw.trading_date.dt.year.astype('int16')
            raw['era'] = np.where(raw.time < ERA_SPLIT, '2012-2020', '2021-2023')

            dt = raw.time.diff()
            ohlc_bad = ((raw.high < raw[['open', 'close', 'low']].max(axis=1)) |
                        (raw.low > raw[['open', 'close', 'high']].min(axis=1)))
            report = {
                'pair': pair, 'rows': len(raw), 'first': raw.time.min(), 'last': raw.time.max(),
                'trading_days': raw.trading_date.nunique(), 'boundary_reached': boundary_reached,
                'duplicates': int(raw.time.duplicated().sum()),
                'out_of_order': int((dt.dropna() <= pd.Timedelta(0)).sum()),
                'gaps_gt_1m': int(dt.gt(pd.Timedelta(minutes=1)).sum()),
                'largest_gap_min': float(dt.dt.total_seconds().div(60).max()),
                'ohlc_failures': int(ohlc_bad.sum()),
                'nonpositive_prices': int((raw[['open','high','low','close']] <= 0).any(axis=1).sum()),
                'volume_minus_one_share': float(raw.volume.eq(-1).mean()),
            }
            return raw, report


        def coverage_tables(raw, pair):
            expected = {'Asian': 420, 'London': 360, 'NY_AM': 360, 'NY_PM': 300}
            counts = raw.groupby(['trading_date', 'session'], observed=True).size().unstack(fill_value=0)
            for name, n in expected.items():
                counts[f'{name}_coverage'] = counts[name] / n
            first_last = raw.groupby('trading_date').slot.agg(['min', 'max'])
            counts = counts.join(first_last)
            slot_cov = (raw.groupby('slot').trading_date.nunique() / raw.trading_date.nunique()).rename('day_share')
            slot_cov = slot_cov.reindex(range(1440), fill_value=0).rename_axis('slot').reset_index()
            slot_cov['pair'] = pair
            return counts.reset_index(), slot_cov
    """),
    md(r"""
        ## 2. Construct daily sweep and reversal geometry

        The daily record freezes the Asian high/low only after 23:59 ET. It then measures each later session independently and
        over the full post-Asian window. Alongside dual-sweep frequency it records:

        - first side and first-touch minute;
        - whether the opposite side is subsequently reached, and how long that takes;
        - return inside the range, midpoint reach, end-of-day location, and maximum overshoot;
        - exact next-open fade returns after the first unambiguous sweep;
        - session open-to-close returns, ranges, and consecutive-session sign reversals.

        This separates the weak statement “both extrema were eventually exceeded” from the stronger path claim “one breakout
        failed and price travelled through the entire prior range.”
    """),
    code(r"""
        def first_true_slot(mask, slots):
            hit = np.flatnonzero(mask)
            return int(slots[hit[0]]) if len(hit) else np.nan


        def build_daily_records(raw, pair):
            pip = PIP_SIZE[pair]
            rows, events = [], []
            for tdate, g in raw.groupby('trading_date', sort=True):
                g = g.sort_values('slot')
                slots = g.slot.to_numpy()
                asian = g.loc[g.slot < 420]
                post = g.loc[g.slot >= 420]
                if asian.empty or post.empty:
                    continue
                a_hi, a_lo = float(asian.high.max()), float(asian.low.min())
                a_open, a_close = float(asian.open.iloc[0]), float(asian.close.iloc[-1])
                width = a_hi - a_lo
                ph, pl = post.high.to_numpy(), post.low.to_numpy()
                ps = post.slot.to_numpy()
                high_slot = first_true_slot(ph > a_hi, ps)
                low_slot = first_true_slot(pl < a_lo, ps)
                high_swept, low_swept = np.isfinite(high_slot), np.isfinite(low_slot)
                same_bar_ambiguous = bool(high_swept and low_swept and high_slot == low_slot)
                if high_swept and (not low_swept or high_slot < low_slot):
                    first_side, first_slot, opposite_slot = 'high', int(high_slot), low_slot
                elif low_swept and (not high_swept or low_slot < high_slot):
                    first_side, first_slot, opposite_slot = 'low', int(low_slot), high_slot
                elif same_bar_ambiguous:
                    first_side, first_slot, opposite_slot = 'ambiguous', int(high_slot), np.nan
                else:
                    first_side, first_slot, opposite_slot = 'none', np.nan, np.nan

                rec = {
                    'pair': pair, 'trading_date': tdate, 'year': int(pd.Timestamp(tdate).year),
                    'era': '2012-2020' if pd.Timestamp(tdate) < pd.Timestamp('2021-01-01') else '2021-2023',
                    'dow': pd.Timestamp(tdate).day_name(), 'bars': len(g),
                    'asian_bars': len(asian), 'post_bars': len(post),
                    'first_slot': int(slots.min()), 'last_slot': int(slots.max()),
                    'observed_asian_high': a_hi, 'observed_asian_low': a_lo,
                    'asian_open': a_open, 'asian_close': a_close,
                    'asian_range_pips': width / pip,
                    'asian_return_pips': (a_close - a_open) / pip,
                    'asian_close_location': (a_close - a_lo) / width if width > 0 else np.nan,
                    'post_up_from_asian_close_pips': (float(post.high.max()) - a_close) / pip,
                    'post_down_from_asian_close_pips': (a_close - float(post.low.min())) / pip,
                    'distance_to_high_pips': (a_hi - a_close) / pip,
                    'distance_to_low_pips': (a_close - a_lo) / pip,
                    'high_swept': high_swept, 'low_swept': low_swept,
                    'dual_sweep': high_swept and low_swept,
                    'high_first_slot': high_slot, 'low_first_slot': low_slot,
                    'first_side': first_side, 'first_sweep_slot': first_slot,
                    'opposite_sweep_slot': opposite_slot,
                    'minutes_first_to_opposite': (opposite_slot - first_slot)
                        if np.isfinite(opposite_slot) and np.isfinite(first_slot) else np.nan,
                    'same_bar_dual_ambiguous': same_bar_ambiguous,
                    'eod_close_location': (float(post.close.iloc[-1]) - a_lo) / width if width > 0 else np.nan,
                    'high_overshoot_pips': max(0.0, (float(post.high.max()) - a_hi) / pip),
                    'low_overshoot_pips': max(0.0, (a_lo - float(post.low.min())) / pip),
                }
                for name, (lo, hi) in SESSION_BOUNDS.items():
                    block = g.loc[(g.slot >= lo) & (g.slot < hi)]
                    rec[f'{name}_bars'] = len(block)
                    rec[f'{name}_return_pips'] = ((float(block.close.iloc[-1]) - float(block.open.iloc[0])) / pip
                                                  if len(block) else np.nan)
                    rec[f'{name}_range_pips'] = ((float(block.high.max()) - float(block.low.min())) / pip
                                                 if len(block) else np.nan)
                    if name != 'Asian':
                        rec[f'{name}_high_sweep'] = bool(len(block) and block.high.max() > a_hi)
                        rec[f'{name}_low_sweep'] = bool(len(block) and block.low.min() < a_lo)
                rows.append(rec)

                if first_side in ('high', 'low'):
                    signal = g.loc[g.slot == first_slot]
                    after = g.loc[g.slot > first_slot]
                    if len(signal) and len(after):
                        sig = signal.iloc[0]
                        direction = -1 if first_side == 'high' else 1
                        boundary = a_hi if first_side == 'high' else a_lo
                        midpoint = (a_hi + a_lo) / 2
                        if first_side == 'high':
                            reentry_same_bar = bool(sig.low <= boundary)
                            subsequent_reentry = after.loc[after.low <= boundary]
                            subsequent_mid = after.loc[after.low <= midpoint]
                            subsequent_opposite = after.loc[after.low < a_lo]
                        else:
                            reentry_same_bar = bool(sig.high >= boundary)
                            subsequent_reentry = after.loc[after.high >= boundary]
                            subsequent_mid = after.loc[after.high >= midpoint]
                            subsequent_opposite = after.loc[after.high > a_hi]
                        entry_row = after.iloc[0] if int(after.iloc[0].slot) == first_slot + 1 else None
                        ev = {
                            'pair': pair, 'trading_date': tdate, 'era': rec['era'], 'year': rec['year'],
                            'first_side': first_side, 'signal_slot': first_slot,
                            'signal_session': next(n for n,(lo,hi) in SESSION_BOUNDS.items() if lo <= first_slot < hi),
                            'same_bar_reentry_ambiguous': reentry_same_bar,
                            'subsequent_reentry': len(subsequent_reentry) > 0,
                            'subsequent_midpoint': len(subsequent_mid) > 0,
                            'subsequent_opposite_sweep': len(subsequent_opposite) > 0,
                            'reentry_slot': int(subsequent_reentry.iloc[0].slot) if len(subsequent_reentry) else np.nan,
                            'midpoint_slot': int(subsequent_mid.iloc[0].slot) if len(subsequent_mid) else np.nan,
                            'opposite_slot': int(subsequent_opposite.iloc[0].slot) if len(subsequent_opposite) else np.nan,
                            'asian_range_pips': rec['asian_range_pips'],
                        }
                        for horizon in FADE_HORIZONS_MIN:
                            ev[f'fade_{horizon}m_pips'] = np.nan
                            if entry_row is None:
                                continue
                            exit_rows = g.loc[g.slot == first_slot + 1 + horizon]
                            if len(exit_rows):
                                ev[f'fade_{horizon}m_pips'] = (direction *
                                    (float(exit_rows.iloc[0].open) - float(entry_row.open)) / pip)
                        events.append(ev)
            daily = pd.DataFrame(rows)
            event = pd.DataFrame(events)
            for name, (lo, hi) in SESSION_BOUNDS.items():
                daily[f'{name}_coverage'] = daily[f'{name}_bars'] / (hi - lo)
            daily['eligible_95'] = np.logical_and.reduce([
                daily[f'{name}_coverage'].ge(MIN_SESSION_COVERAGE) for name in SESSION_BOUNDS
            ])
            daily['eligible_exact'] = np.logical_and.reduce([
                daily[f'{name}_coverage'].eq(1.0) for name in SESSION_BOUNDS
            ])
            return daily, event
    """),
    md(r"""
        ## 3. Primary frequencies, confidence intervals, and stability

        The primary estimand is the equal-weighted trading-day dual-sweep rate among days with at least 95% observed coverage in
        every named session. This is implementable as a day-level statistic and avoids overweighting high-activity days. Year-block
        bootstrap intervals retain within-year clustering. Results are also shown by year, era, weekday, month, first side, and
        session of first touch. A synchronized EURUSD/GBPUSD table measures joint occurrence and first-side agreement so the two
        correlated markets are not presented as independent confirmations. Exact-coverage results are reported even if that
        filter leaves no data.
    """),
    code(r"""
        def year_block_interval(frame, value_col, draws=BLOCK_BOOT_DRAWS, seed=RANDOM_SEED):
            use = frame[['year', value_col]].dropna()
            years = np.sort(use.year.unique())
            if not len(years):
                return (np.nan, np.nan)
            rng = np.random.default_rng(seed)
            vals = []
            groups = {y: use.loc[use.year.eq(y), value_col].to_numpy(float) for y in years}
            for _ in range(draws):
                selected = rng.choice(years, len(years), replace=True)
                vals.append(np.concatenate([groups[y] for y in selected]).mean())
            return tuple(np.quantile(vals, [0.025, 0.975]))


        def summarize_rates(daily):
            rows = []
            for pair, p in daily.groupby('pair'):
                for rule, mask in [('all_observed', np.ones(len(p), dtype=bool)),
                                   ('95pct_each_session', p.eligible_95.to_numpy()),
                                   ('exact_each_session', p.eligible_exact.to_numpy())]:
                    q = p.loc[mask]
                    lo, hi = year_block_interval(q, 'dual_sweep')
                    rows.append({'pair': pair, 'coverage_rule': rule, 'days': len(q),
                                 'high_sweep_rate': q.high_swept.mean(), 'low_sweep_rate': q.low_swept.mean(),
                                 'dual_sweep_rate': q.dual_sweep.mean(), 'dual_ci_low': lo, 'dual_ci_high': hi,
                                 'same_bar_dual_ambiguous_rate': q.same_bar_dual_ambiguous.mean()})
            return pd.DataFrame(rows)


        def grouped_rate(frame, columns):
            return (frame.groupby(columns, observed=True)
                    .agg(days=('dual_sweep','size'), high_rate=('high_swept','mean'),
                         low_rate=('low_swept','mean'), dual_rate=('dual_sweep','mean'),
                         asian_range_median=('asian_range_pips','median'))
                    .reset_index())
    """),
    md(r"""
        ## 4. Mechanical-range and definition sensitivity

        A narrow reference range is easier to break twice. To avoid mistaking geometry for a behavioral effect, this section:

        1. bins days by Asian-range quintile and reports both raw and range-normalized excursions;
        2. requires absolute penetration buffers of 0-1 pip and fractional buffers of 0-10% of the Asian range;
        3. compares several seven-hour reference windows in otherwise identical 24-hour days anchored at 15:00-19:00 ET.

        Anchor comparisons are deliberately labelled exploratory: the chosen clock was motivated by inspected charts, and the
        overlapping anchors are not independent tests.
    """),
    code(r"""
        def add_width_bins(daily):
            out = []
            for (_, era), g in daily.groupby(['pair','era']):
                z = g.copy()
                z['asian_width_quintile'] = pd.qcut(z.asian_range_pips.rank(method='first'), 5,
                                                   labels=['Q1 narrow','Q2','Q3','Q4','Q5 wide'])
                out.append(z)
            return pd.concat(out, ignore_index=True)


        def threshold_sensitivity(daily):
            rows = []
            for pair, g in daily.groupby('pair'):
                q = g.loc[g.eligible_95].copy()
                for b in BUFFER_PIPS:
                    high = q.high_overshoot_pips > b if b else q.high_swept
                    low = q.low_overshoot_pips > b if b else q.low_swept
                    rows.append({'pair':pair, 'buffer_type':'pips', 'buffer':b, 'days':len(q),
                                 'high_rate':high.mean(), 'low_rate':low.mean(), 'dual_rate':(high & low).mean()})
                for frac in BUFFER_RANGE_FRACS:
                    threshold = frac * q.asian_range_pips
                    high = q.high_overshoot_pips > threshold if frac else q.high_swept
                    low = q.low_overshoot_pips > threshold if frac else q.low_swept
                    rows.append({'pair':pair, 'buffer_type':'range_fraction', 'buffer':frac, 'days':len(q),
                                 'high_rate':high.mean(), 'low_rate':low.mean(), 'dual_rate':(high & low).mean()})
            return pd.DataFrame(rows)


        def anchor_sweep_rate(raw, pair, anchor_hour):
            ny = raw.time.dt.tz_convert('America/New_York')
            naive = ny.dt.tz_localize(None)
            minute = ny.dt.hour * 60 + ny.dt.minute
            anchor_minute = anchor_hour * 60
            anchor_date = naive.dt.normalize() + pd.to_timedelta((minute >= anchor_minute).astype(int), unit='D')
            slot = ((minute - anchor_minute) % 1440).astype('int16')
            temp = pd.DataFrame({'anchor_date':anchor_date, 'slot':slot,
                                 'high':raw.high.to_numpy(), 'low':raw.low.to_numpy()})
            rows = []
            for date, g in temp.groupby('anchor_date'):
                ref, test = g.loc[g.slot < 420], g.loc[g.slot >= 420]
                if len(ref) < 0.95*420 or len(test) < 0.95*1020:
                    continue
                hi, lo = ref.high.max(), ref.low.min()
                rows.append((test.high.max() > hi) and (test.low.min() < lo))
            return {'pair':pair, 'anchor_et':f'{anchor_hour:02d}:00', 'days':len(rows),
                    'dual_rate':np.mean(rows) if rows else np.nan}
    """),
    md(r"""
        ## 5. A claim-matched day re-pairing null

        The null keeps the empirical Asian geometry and empirical post-Asian path excursions but breaks their same-day pairing.
        Within each pair-year, the later path is circularly shifted to a different trading day and rebased at that donor day's
        Asian close. For recipient day *i*, a null high sweep occurs when donor post-Asian upside exceeds *i*'s distance from its
        Asian close to its Asian high; the low side is symmetric.

        This null answers a narrow question: does same-day linkage make dual sweeps more common than independently pairing an
        observed Asian range with a season-matched observed later path? Its center is also a useful mechanical benchmark. It does
        not prove tradability, and it does not test whether the entire unconditional frequency exceeds a diffusion model.
    """),
    code(r"""
        def repairing_null(daily, draws=NULL_DRAWS, seed=RANDOM_SEED):
            rng = np.random.default_rng(seed)
            outputs, summary = {}, []
            for pair, p in daily.loc[daily.eligible_95].groupby('pair'):
                p = p.reset_index(drop=True)
                observed = p.dual_sweep.mean()
                null_rates = []
                groups = [idx.to_numpy() for _, idx in p.groupby('year').groups.items()]
                for _ in range(draws):
                    donor = np.arange(len(p))
                    for idx in groups:
                        if len(idx) > 1:
                            shift = int(rng.integers(1, len(idx)))
                            donor[idx] = np.roll(idx, shift)
                    high = p.post_up_from_asian_close_pips.to_numpy()[donor] > p.distance_to_high_pips.to_numpy()
                    low = p.post_down_from_asian_close_pips.to_numpy()[donor] > p.distance_to_low_pips.to_numpy()
                    null_rates.append(np.mean(high & low))
                arr = np.asarray(null_rates)
                pval = (1 + np.sum(arr >= observed)) / (1 + len(arr))
                outputs[pair] = arr
                summary.append({'pair':pair, 'days':len(p), 'observed_dual_rate':observed,
                                'null_mean':arr.mean(), 'null_sd':arr.std(ddof=1),
                                'null_q025':np.quantile(arr,.025), 'null_q975':np.quantile(arr,.975),
                                'observed_minus_null':observed-arr.mean(), 'one_sided_p':pval})
            return pd.DataFrame(summary), outputs
    """),
    md(r"""
        ## 6. Reversal anatomy after the first sweep

        The strongest interpretation of the chart observation is sequential: after the first side breaks, price re-enters the
        Asian range, crosses its midpoint, then reaches the opposite side. The table below conditions on the first unambiguous
        sweep and reports each step, excluding same-bar ordering from “subsequent” probabilities. It also shows next-open fade
        returns as a timing diagnostic—not a costed strategy—and stratifies opposite-side probability by first-touch session and
        remaining minutes in the day.
    """),
    code(r"""
        def event_summary(events):
            if events.empty:
                return pd.DataFrame()
            value_cols = ['same_bar_reentry_ambiguous','subsequent_reentry','subsequent_midpoint',
                          'subsequent_opposite_sweep'] + [f'fade_{h}m_pips' for h in FADE_HORIZONS_MIN]
            return (events.groupby(['pair','era','first_side'], observed=True)[value_cols]
                    .agg(['size','mean']).round(4))


        def session_return_reversal(daily):
            pairs = [('Asian','London'), ('London','NY_AM'), ('NY_AM','NY_PM'),
                     ('Asian','NY_AM'), ('Asian','NY_PM')]
            rows = []
            for pair, p in daily.loc[daily.eligible_95].groupby('pair'):
                for left, right in pairs:
                    x, y = p[f'{left}_return_pips'], p[f'{right}_return_pips']
                    valid = x.notna() & y.notna() & x.ne(0) & y.ne(0)
                    rho = spearmanr(x[valid], y[valid]).statistic if valid.sum() > 2 else np.nan
                    rows.append({'pair':pair, 'from_session':left, 'to_session':right,
                                 'days':int(valid.sum()), 'opposite_sign_rate':float((np.sign(x[valid]) != np.sign(y[valid])).mean()),
                                 'return_spearman':rho,
                                 'mean_reversal_component_pips':float((-np.sign(x[valid])*y[valid]).mean())})
            return pd.DataFrame(rows)


        def cross_pair_dependence(daily):
            if daily.pair.nunique() < 2:
                return pd.DataFrame()
            left = daily.loc[(daily.pair == 'EURUSD') & daily.eligible_95,
                             ['trading_date','dual_sweep','high_swept','low_swept','first_side']]
            right = daily.loc[(daily.pair == 'GBPUSD') & daily.eligible_95,
                              ['trading_date','dual_sweep','high_swept','low_swept','first_side']]
            joined = left.merge(right, on='trading_date', suffixes=('_eur','_gbp'))
            valid_side = joined.first_side_eur.isin(['high','low']) & joined.first_side_gbp.isin(['high','low'])
            eur_rate, gbp_rate = joined.dual_sweep_eur.mean(), joined.dual_sweep_gbp.mean()
            return pd.DataFrame([{
                'synchronized_days': len(joined),
                'eur_dual_rate': eur_rate, 'gbp_dual_rate': gbp_rate,
                'both_dual_rate': (joined.dual_sweep_eur & joined.dual_sweep_gbp).mean(),
                'both_rate_if_independent': eur_rate * gbp_rate,
                'dual_indicator_correlation': joined.dual_sweep_eur.astype(float).corr(joined.dual_sweep_gbp.astype(float)),
                'same_first_side_rate': (joined.loc[valid_side,'first_side_eur'] ==
                                         joined.loc[valid_side,'first_side_gbp']).mean(),
                'valid_first_side_days': int(valid_side.sum()),
            }])
    """),
    md(r"""
        ## 7. Execute the study

        Intermediate raw frames are released pair by pair. Final objects are day/event tables, quality reports, sensitivity
        tables, null distributions, and compact figures. The assertions prevent accidental holdout use and ensure sweep logic is
        internally consistent.
    """),
    code(r"""
        raw_reports, coverage_frames, slot_frames = [], [], []
        daily_frames, event_frames, anchor_rows = [], [], []

        for pair in PAIRS:
            print(f'\nLoading {pair} ...')
            raw, report = load_pre_holdout(pair)
            raw_reports.append(report)
            coverage, slot_cov = coverage_tables(raw, pair)
            coverage['pair'] = pair
            coverage_frames.append(coverage)
            slot_frames.append(slot_cov)
            daily, events = build_daily_records(raw, pair)
            daily_frames.append(daily)
            event_frames.append(events)
            if RUN_ANCHOR_SENSITIVITY:
                for anchor in ANCHOR_HOURS_ET:
                    anchor_rows.append(anchor_sweep_rate(raw, pair, anchor))
            print(f'  rows={len(raw):,}; daily records={len(daily):,}; eligible95={daily.eligible_95.sum():,}')
            del raw
            gc.collect()

        quality = pd.DataFrame(raw_reports)
        coverage = pd.concat(coverage_frames, ignore_index=True)
        slot_coverage = pd.concat(slot_frames, ignore_index=True)
        daily = pd.concat(daily_frames, ignore_index=True)
        events = pd.concat(event_frames, ignore_index=True) if event_frames else pd.DataFrame()
        daily['month'] = pd.to_datetime(daily.trading_date).dt.month.astype('int8')
        daily = add_width_bins(daily)
        eligible_keys = daily.loc[daily.eligible_95, ['pair','trading_date']].drop_duplicates()
        eligible_events = events.merge(eligible_keys, on=['pair','trading_date'], how='inner')
        anchor_sensitivity = pd.DataFrame(anchor_rows)

        assert daily.trading_date.max() < pd.Timestamp('2024-01-01')
        assert not (daily.dual_sweep & ~(daily.high_swept & daily.low_swept)).any()
        assert not ((daily.first_side == 'high') & daily.high_first_slot.isna()).any()
        assert not ((daily.first_side == 'low') & daily.low_first_slot.isna()).any()

        rate_summary = summarize_rates(daily)
        yearly = grouped_rate(daily.loc[daily.eligible_95], ['pair','year'])
        era = grouped_rate(daily.loc[daily.eligible_95], ['pair','era'])
        weekday = grouped_rate(daily.loc[daily.eligible_95], ['pair','dow'])
        monthly = grouped_rate(daily.loc[daily.eligible_95], ['pair','month'])
        width = grouped_rate(daily.loc[daily.eligible_95], ['pair','era','asian_width_quintile'])
        threshold = threshold_sensitivity(daily)
        null_summary, null_draws = repairing_null(daily)
        reversal_summary = event_summary(eligible_events)
        event_by_session = (eligible_events.groupby(['pair','signal_session'], observed=True)
                            .agg(events=('subsequent_opposite_sweep','size'),
                                 reentry_rate=('subsequent_reentry','mean'),
                                 midpoint_rate=('subsequent_midpoint','mean'),
                                 opposite_rate=('subsequent_opposite_sweep','mean'),
                                 median_signal_slot=('signal_slot','median'))
                            .reset_index())
        session_reversal = session_return_reversal(daily)
        cross_pair = cross_pair_dependence(daily)

        display(quality)
        print('\nCoverage-rule sensitivity')
        display(rate_summary)
        print('\nEra stability')
        display(era)
        print('\nYearly stability')
        display(yearly)
        print('\nWeekday and calendar-month stability')
        display(weekday)
        display(monthly)
        print('\nWidth conditioning')
        display(width)
        print('\nPenetration sensitivity')
        display(threshold)
        print('\nSame-day re-pairing null')
        display(null_summary)
        print('\nSequential reversal anatomy')
        display(reversal_summary)
        print('\nSequential reversal by first-touch session (controls for time remaining)')
        display(event_by_session)
        print('\nSession-return reversal')
        display(session_reversal)
        if len(cross_pair):
            print('\nEURUSD/GBPUSD dependence (not independent replications)')
            display(cross_pair)
        if RUN_ANCHOR_SENSITIVITY:
            print('\nAlternative seven-hour reference anchors')
            display(anchor_sensitivity)
    """),
    md(r"""
        ## 8. Visual diagnostics

        The first chart shows annual stability rather than a pooled headline alone. The second exposes the mechanical dependence
        on Asian-range width. The third shows when first and opposite sweeps occur on the ET clock. The coverage chart zooms into
        the rollover and must be read before trusting the 17:00 boundary.
    """),
    code(r"""
        fig, axes = plt.subplots(2, 2, figsize=(16, 11))
        sns.lineplot(data=yearly, x='year', y='dual_rate', hue='pair', marker='o', ax=axes[0,0])
        axes[0,0].set_title('Dual-sweep rate by trading year')
        axes[0,0].set_ylim(0, 1)

        sns.lineplot(data=width, x='asian_width_quintile', y='dual_rate', hue='pair', style='era',
                     marker='o', ax=axes[0,1])
        axes[0,1].set_title('Dual sweeps versus observed Asian-range width')
        axes[0,1].tick_params(axis='x', rotation=25)

        touch = daily.loc[daily.eligible_95, ['pair','high_first_slot','low_first_slot']].melt(
            id_vars='pair', var_name='side', value_name='slot').dropna()
        touch['hour_et'] = ((17 + touch.slot / 60) % 24)
        sns.histplot(data=touch, x='hour_et', hue='side', bins=np.arange(0,25),
                     element='step', stat='probability', common_norm=False, ax=axes[1,0])
        axes[1,0].set_title('First sweep timing (ET hour; pairs pooled)')
        axes[1,0].set_xticks(range(0,24,3))

        rollover = slot_coverage.loc[slot_coverage.slot.between(0, 120)].copy()
        rollover['minutes_after_1700'] = rollover.slot
        sns.lineplot(data=rollover, x='minutes_after_1700', y='day_share', hue='pair', ax=axes[1,1])
        axes[1,1].set_title('Observed minute coverage after 17:00 ET')
        axes[1,1].set_ylim(0, 1.02)
        plt.tight_layout()
        plt.show()

        if RUN_ANCHOR_SENSITIVITY and len(anchor_sensitivity):
            plt.figure(figsize=(9,4))
            sns.lineplot(data=anchor_sensitivity, x='anchor_et', y='dual_rate', hue='pair', marker='o')
            plt.ylim(0,1)
            plt.title('Seven-hour reference-window anchor sensitivity')
            plt.show()

        if len(null_summary):
            fig, axes = plt.subplots(1, len(null_summary), figsize=(6*len(null_summary),4), squeeze=False)
            for ax, row in zip(axes.flat, null_summary.itertuples()):
                ax.hist(null_draws[row.pair], bins=25, alpha=.75)
                ax.axvline(row.observed_dual_rate, color='crimson', lw=2, label='observed')
                ax.axvline(row.null_mean, color='black', ls='--', label='null mean')
                ax.set_title(f'{row.pair}: within-year re-pairing null')
                ax.legend()
            plt.tight_layout(); plt.show()
    """),
    md(r"""
        ## 9. Interpretation checklist and promotion gate

        Read the evidence in this order:

        1. **Coverage:** Is 17:00-17:14 systematically absent? If so, call the measure an observed-range proxy. Compare the
           all-observed, 95%-coverage, exact-coverage, and nearby-anchor results before discussing magnitude.
        2. **Base frequency:** Are high and low marginal sweep rates both high, and is the dual rate stable by year and era?
        3. **Geometry:** Does the rate collapse for wide Asian ranges or modest penetration buffers? If yes, “both sides swept”
           is primarily a narrow-range/path-length statement.
        4. **Sequential reversal:** Exclude ambiguous same-bar cases. Separate re-entry, midpoint, and genuinely later opposite-
           side reach. Condition on first-touch session because a London touch has more time remaining than a NY_PM touch.
        5. **Null:** A high observed rate near the day-re-pairing null center is common path geometry, not evidence that a given
           Asian session predicts its own later reversal. A positive observed-minus-null gap is exploratory same-day linkage.
        6. **Economics:** Fixed-horizon fade returns are gross midpoint diagnostics. No candidate is tradable until executable
           bid/ask costs, causal order rules, overlap policy, and adverse path handling are specified.

        Because this idea came from inspected charts, all pre-2024 slicing is discovery. Before opening 2024+, freeze one primary
        definition, expected sign, minimum effect, kill threshold, and cost model; register it as a material experiment. A sensible
        candidate would need a stable buffered sequential-reversal rate, positive next-open gross effect after timing stress, and
        an effect meaningfully above the re-pairing null—not merely a large unbuffered dual-sweep percentage.
    """),
    code(r"""
        research_tables = {
            'quality': quality,
            'rate_summary': rate_summary,
            'era': era,
            'yearly': yearly,
            'weekday': weekday,
            'monthly': monthly,
            'width': width,
            'threshold': threshold,
            'anchor_sensitivity': anchor_sensitivity,
            'null_summary': null_summary,
            'event_by_session': event_by_session,
            'session_reversal': session_reversal,
            'cross_pair': cross_pair,
            'events': eligible_events,
        }

        print('Exploration complete. All results are pre-2024 discovery evidence.')
        print('Do not open the 2024+ holdout until a single candidate and kill rule are frozen and registered.')
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
print(f"Wrote {OUT} ({len(cells)} cells)")
