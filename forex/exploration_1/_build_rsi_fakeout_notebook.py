"""Build the EURUSD/GBPUSD RSI fakeout and reversal exploration notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "rsi_fakeout_reversal_exploration.ipynb"


def md(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type":"markdown","id":hashlib.sha1(("md\0"+source).encode()).hexdigest()[:12],
            "metadata":{},"source":source.splitlines(keepends=True)}


def code(text):
    source = dedent(text).strip() + "\n"
    return {"cell_type":"code","id":hashlib.sha1(("code\0"+source).encode()).hexdigest()[:12],
            "execution_count":None,"metadata":{},"outputs":[],"source":source.splitlines(keepends=True)}


cells = [
    md(r"""
        # EURUSD / GBPUSD RSI fakeout and full-reversal exploration

        This notebook operationalizes the market thesis that EURUSD and GBPUSD frequently make short-lived directional pushes
        or range breaks that fail, creating a mean-reversion or full-reversal opportunity. The fixed reference feature is
        close-source, SMA-seeded Wilder RSI(14). Nothing from 2024 onward is loaded or scored.

        The notebook separates four questions:

        1. **Endpoint mean reversion:** after RSI is extreme, is the next-open forward return opposite the impulse?
        2. **Execution timing:** which part of the return arrives in minutes 0–1, 1–5, 5–15, and 15–30, and what survives
           one-, two-, or five-minute delayed entry?
        3. **Fakeout / full reversal:** after a prior-range break or directional impulse, does price re-enter the range, reach
           its midpoint/opposite side, retrace half/full of the impulse, or does RSI return through 50?
        4. **Signal clock:** do scheduled 30-minute observations and first threshold-crossing events with a 30-minute cooldown
           tell the same story?

        All entries use the first available minute open after the completed signal bar. Path targets use one-minute highs/lows
        only to measure reach and time; they are not bracket fills. Same-bar target/stop order remains unknown. Midpoint data do
        not contain executable spreads, so costs are hypothetical. This is pre-2024 exploration, not holdout testing.
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
        from scipy.signal import lfilter

        warnings.filterwarnings('ignore',category=FutureWarning)
        sns.set_theme(style='whitegrid',context='notebook')
        pd.set_option('display.max_columns',200)
        pd.set_option('display.width',240)

        # ------------------------------ research scope -----------------------------
        PAIRS = ['EURUSD','GBPUSD']
        EXPLORATION_START = pd.Timestamp('2012-01-01',tz='UTC')
        ERA_SPLIT = pd.Timestamp('2021-01-01',tz='UTC')
        HOLDOUT_START = pd.Timestamp('2024-01-01',tz='UTC')

        RSI_LENGTH = 14
        PRIMARY_THRESHOLDS = (30.0,70.0)
        THRESHOLD_PAIRS = [(25.0,75.0),(30.0,70.0)]
        SIGNAL_MODES = ['scheduled_state','first_crossing_cooldown']
        SCHEDULE_INTERVAL_MIN = 30
        EVENT_COOLDOWN_MIN = 30

        PRIMARY_HORIZON_MIN = 30
        ENDPOINT_HORIZONS_MIN = [1,5,15,30,60]
        RETURN_DECOMPOSITION_BREAKS_MIN = [1,5,15,30]
        ENTRY_DELAYS_MIN = [0,1,2,5]
        IMPULSE_WINDOWS_MIN = [15,30,60]
        BREAKOUT_LOOKBACKS_MIN = [15,30]
        REVERSAL_MAX_HORIZON_MIN = 240
        REVERSAL_CHECKPOINTS_MIN = [30,60,120,240]

        HYPOTHETICAL_COST_PIPS = [0.0,0.25,0.50,0.75,1.00]

        # Selection-aware endpoint null. It repeats the declared search over these
        # lengths, horizons, thresholds, and signal modes after session re-pairing.
        RUN_SELECTION_NULL = True
        NULL_RSI_LENGTHS = [7,10,14,21,28]
        NULL_HORIZONS_MIN = [5,15,30,60]
        NULL_DRAWS = 100
        RANDOM_SEED = 20260802
        CSV_CHUNK_ROWS = 750_000
        # --------------------------------------------------------------------------

        SMOKE_MODE = os.getenv('RSI_FAKEOUT_SMOKE','0') == '1'
        if SMOKE_MODE:
            PAIRS = PAIRS[:1]
            IMPULSE_WINDOWS_MIN = [15,30]
            BREAKOUT_LOOKBACKS_MIN = [30]
            REVERSAL_MAX_HORIZON_MIN = 60
            REVERSAL_CHECKPOINTS_MIN = [30,60]
            NULL_RSI_LENGTHS = [10,14]
            NULL_HORIZONS_MIN = [15,30]
            NULL_DRAWS = 8
        RUN_SELECTION_NULL = RUN_SELECTION_NULL and os.getenv('RSI_FAKEOUT_SKIP_NULL','0') != '1'

        assert EXPLORATION_START < ERA_SPLIT < HOLDOUT_START
        assert PRIMARY_HORIZON_MIN in ENDPOINT_HORIZONS_MIN
        assert set(RETURN_DECOMPOSITION_BREAKS_MIN) <= set(ENDPOINT_HORIZONS_MIN)
        assert REVERSAL_CHECKPOINTS_MIN[-1] <= REVERSAL_MAX_HORIZON_MIN
        assert set(PAIRS) <= {'EURUSD','GBPUSD','AUDUSD','NZDUSD'}

        here = Path.cwd().resolve()
        if here.name == 'exploration_1':
            project_root = here
        elif (here/'forex'/'exploration_1').exists():
            project_root = here/'forex'/'exploration_1'
        else:
            raise FileNotFoundError('Run from the workspace root or forex/exploration_1.')
        data_dir = project_root.parent/'data'

        print(f'Pairs={PAIRS}; exploration=[{EXPLORATION_START},{HOLDOUT_START}); era split={ERA_SPLIT}')
        print(f'RSI=close/Wilder/{RSI_LENGTH}; thresholds={THRESHOLD_PAIRS}; modes={SIGNAL_MODES}')
        print('HOLDOUT POLICY: rows from 2024 onward are never retained or tested.')
    """),
    md(r"""
        ## 1. Operational definitions

        - **Scheduled state:** at each 30-minute decision close, long when RSI ≤ the lower threshold and short when RSI ≥ the
          upper threshold. Consecutive scheduled observations can represent the same episode, but 30-minute fixed-horizon trades
          do not overlap.
        - **First crossing + cooldown:** signal only when RSI first crosses into the extreme; accept no new signal for 30 minutes.
        - **Impulse reversal:** for a long/short signal, the preceding source move must be down/up. Half and full reversal mean
          recovering 50% and 100% of that prior move.
        - **Range fakeout:** a long closes below the prior range low or a short above the prior range high. Re-entry reaches the
          broken boundary; deeper reversal reaches the prior midpoint or opposite boundary.
        - **RSI neutralization:** the first future completed bar where long RSI ≥ 50 or short RSI ≤ 50, with exit at the following
          minute open. It is a causal variable exit but may overlap across signals, so it is reported as a per-signal diagnostic.

        Exact timestamp checks null any target or path crossing a missing-minute gap. RSI and rolling features restart/re-warm
        after gaps. The notebook reports every exclusion rather than substituting a shorter window.
    """),
]

cells.extend([
    code(r"""
        def load_pre_holdout(pair):
            path = data_dir/f'{pair.lower()}_intraday_1min.csv'
            assert path.exists(),f'Missing {path}'
            dtype = {c:'float32' for c in ['open','high','low','close','volume']}
            kept=[]; boundary=False; previous=None; duplicates=out_of_order=0
            for chunk in pd.read_csv(path,dtype=dtype,parse_dates=['time'],chunksize=CSV_CHUNK_ROWS):
                chunk['time'] = (chunk.time.dt.tz_localize('UTC') if chunk.time.dt.tz is None
                                 else chunk.time.dt.tz_convert('UTC'))
                duplicates += int(chunk.time.duplicated().sum())
                out_of_order += int((chunk.time.diff().dropna()<=pd.Timedelta(0)).sum())
                if previous is not None and len(chunk) and chunk.time.iloc[0]<=previous: out_of_order += 1
                if len(chunk): previous=chunk.time.iloc[-1]
                before=chunk.loc[chunk.time<HOLDOUT_START].copy()
                if len(before): kept.append(before)
                if chunk.time.ge(HOLDOUT_START).any(): boundary=True; break
            raw=pd.concat(kept,ignore_index=True)
            assert len(raw) and raw.time.max()<HOLDOUT_START and duplicates==0 and out_of_order==0
            ny=raw.time.dt.tz_convert('America/New_York')
            ny_min=ny.dt.hour*60+ny.dt.minute
            ny_date=ny.dt.tz_localize(None).dt.normalize()
            raw['sdate']=ny_date+pd.to_timedelta((ny_min>=17*60).astype(int),unit='D')
            raw['session_minute']=((ny_min-17*60)%1440).astype('int16')
            raw['utc_minute']=(raw.time.dt.hour*60+raw.time.dt.minute).astype('int16')
            dt=raw.time.diff(); one_minute=dt.eq(pd.Timedelta(minutes=1))
            ohlc_bad=((raw.high<raw[['open','close','low']].max(axis=1))|
                      (raw.low>raw[['open','close','high']].min(axis=1)))
            quality={'pair':pair,'rows':len(raw),'first':raw.time.min(),'last':raw.time.max(),
                     'sessions':raw.sdate.nunique(),'boundary_reached':boundary,'duplicates':duplicates,
                     'out_of_order':out_of_order,'one_minute_links':int(one_minute.sum()),
                     'gaps_gt_1m':int(dt.gt(pd.Timedelta(minutes=1)).sum()),
                     'largest_gap_min':dt.dt.total_seconds().div(60).max(),
                     'ohlc_failures':int(ohlc_bad.sum()),
                     'nonpositive_rows':int(raw[['open','high','low','close']].le(0).any(axis=1).sum()),
                     'volume_minus_one_share':raw.volume.eq(-1).mean()}
            assert quality['ohlc_failures']==0 and quality['nonpositive_rows']==0
            return raw,one_minute.to_numpy(),quality


        def sma_seeded_recursive(values,starts,ends,length,alpha):
            out=np.full(len(values),np.nan,dtype=float)
            for start,end in zip(starts,ends):
                x=values[start:end]
                if len(x)<length: continue
                seed=float(np.mean(x[:length])); seed_index=start+length-1
                out[seed_index]=seed
                if len(x)>length:
                    filtered,_=lfilter([alpha],[1.0,-(1.0-alpha)],x[length:],zi=[(1.0-alpha)*seed])
                    out[seed_index+1:end]=filtered
            return out


        def wilder_rsi(close,one_minute,length):
            starts=np.flatnonzero(~one_minute); ends=np.r_[starts[1:],len(close)]
            delta=np.diff(close,prepend=close[0]); delta[starts]=0.0
            gains=np.clip(delta,0,None); losses=np.clip(-delta,0,None)
            ag=sma_seeded_recursive(gains,starts,ends,length,1.0/length)
            al=sma_seeded_recursive(losses,starts,ends,length,1.0/length)
            rs=np.divide(ag,al,out=np.full_like(ag,np.nan),where=al>0)
            rsi=100-100/(1+rs)
            rsi[(al==0)&(ag==0)]=50; rsi[(al==0)&(ag>0)]=100
            return rsi


        def exact_shift(series,time,minutes,direction='past'):
            if direction=='past':
                shifted=series.shift(minutes)
                return shifted.where(time.shift(minutes).eq(time-pd.Timedelta(minutes=minutes)))
            shifted=series.shift(-minutes)
            return shifted.where(time.shift(-minutes).eq(time+pd.Timedelta(minutes=minutes)))


        def cooldown_positions(positions,times,cooldown_min):
            accepted=[]; last_time=None
            for pos in positions:
                now=times.iloc[pos]
                if last_time is None or now-last_time>=pd.Timedelta(minutes=cooldown_min):
                    accepted.append(pos); last_time=now
            return np.asarray(accepted,dtype=int)


        def signal_positions(raw,rsi,low,high,mode):
            side=np.select([rsi<=low,rsi>=high],[1,-1],default=0).astype('int8')
            if mode=='scheduled_state':
                mask=raw.utc_minute.mod(SCHEDULE_INTERVAL_MIN).eq(SCHEDULE_INTERVAL_MIN-1).to_numpy() & (side!=0)
                positions=np.flatnonzero(mask)
            else:
                previous=np.roll(rsi,1); previous[0]=np.nan
                exact_previous=raw.time.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
                crossed=((side==1)&(previous>low)|(side==-1)&(previous<high))&exact_previous
                positions=cooldown_positions(np.flatnonzero(crossed),raw.time,EVENT_COOLDOWN_MIN)
            return positions,side[positions]


        def session_cluster_t(values,sessions):
            z=pd.DataFrame({'x':values,'session':sessions}).dropna(); n=len(z); g=z.session.nunique()
            if n<2 or g<2:return np.nan
            mean=z.x.mean(); score=(z.x-mean).groupby(z.session).sum()
            se=np.sqrt((g/(g-1))*np.square(score).sum())/n
            return mean/se if se>0 else np.nan


        def endpoint_series(raw,start_offset,end_offset,pip_size):
            entry=raw.open.shift(-start_offset).astype(float)
            exit_=raw.open.shift(-end_offset).astype(float)
            exact=(raw.time.shift(-start_offset).eq(raw.time+pd.Timedelta(minutes=start_offset))&
                   raw.time.shift(-end_offset).eq(raw.time+pd.Timedelta(minutes=end_offset)))
            return (1e4*np.log(exit_/entry)).where(exact),((exit_-entry)/pip_size).where(exact)


        def reverse_roll(series,window,op):
            return getattr(series.iloc[::-1].rolling(window,min_periods=window),op)().iloc[::-1]


        def path_excursions(raw,horizon,pip_size):
            entry=raw.open.shift(-1).astype(float); exit_=raw.open.shift(-(horizon+1)).astype(float)
            exact=(raw.time.shift(-1).eq(raw.time+pd.Timedelta(minutes=1))&
                   raw.time.shift(-(horizon+1)).eq(raw.time+pd.Timedelta(minutes=horizon+1)))
            hi=reverse_roll(raw.high.astype(float).shift(-1),horizon,'max')
            lo=reverse_roll(raw.low.astype(float).shift(-1),horizon,'min')
            hi=pd.concat([hi,entry,exit_],axis=1).max(axis=1).where(exact)
            lo=pd.concat([lo,entry,exit_],axis=1).min(axis=1).where(exact)
            return pd.DataFrame({'long_mfe_bp':(1e4*np.log(hi/entry)).where(exact),
                                 'long_mae_bp':(1e4*np.log(entry/lo)).where(exact),
                                 'long_mfe_pips':((hi-entry)/pip_size).where(exact),
                                 'long_mae_pips':((entry-lo)/pip_size).where(exact)})
    """),
    md(r"""
        ## 2. Build causal signal and outcome panels

        Each pair is processed independently and raw minute history is released before loading the next pair. The retained signal
        table contains both threshold pairs and both signal clocks, endpoint returns, delayed-entry variants, incremental return
        segments, 30-minute MFE/MAE, causal past impulse/range state, and reversal-completion labels.
    """),
])

analysis_cells = [
    md(r"""
        ## 3. Endpoint edge, direction symmetry, and stability

        The primary economic estimand is mean signed P&L per signal. A long signal multiplies the future return by +1 and a
        short signal by -1; therefore a positive result means movement away from the RSI extreme in both cases. The t-statistic
        clusters observations by New York trading session (17:00-to-17:00), because signals within a session are dependent.
        Profit factor is gross winning pips divided by gross losing pips and is undefined when there are no losses.
    """),
    code(r"""
        def edge_record(g,pips_col='pnl_pips',bp_col='pnl_bp'):
            z=g.loc[g[pips_col].notna()].copy()
            wins=z.loc[z[pips_col]>0,pips_col].sum()
            losses=-z.loc[z[pips_col]<0,pips_col].sum()
            out={'n':len(z),'sessions':z.sdate.nunique(),'mean_pips':z[pips_col].mean(),
                 'median_pips':z[pips_col].median(),'cluster_t':session_cluster_t(z[pips_col],z.sdate),
                 'win_rate':z[pips_col].gt(0).mean(),'profit_factor':wins/losses if losses>0 else np.nan}
            if bp_col in z: out['mean_log_bp']=z[bp_col].mean()
            if {'mfe_pips','mae_pips'}<=set(z.columns) and pips_col=='pnl_pips':
                out.update({'mean_mfe_pips':z.mfe_pips.mean(),'mean_mae_pips':z.mae_pips.mean(),
                            'mfe_mae_ratio':z.mfe_pips.mean()/z.mae_pips.mean(),
                            'endpoint_capture':z[pips_col].mean()/z.mfe_pips.mean(),
                            'mae_p90_pips':z.mae_pips.quantile(.90)})
            return pd.Series(out)


        primary=all_signals.loc[(all_signals.low_threshold==PRIMARY_THRESHOLDS[0])&
                                (all_signals.high_threshold==PRIMARY_THRESHOLDS[1])].copy()
        headline=(primary.groupby(['pair','era','signal_mode'],observed=True)
                  .apply(edge_record,include_groups=False).reset_index())
        display(headline.round(3))

        direction=(primary.assign(direction=np.where(primary.side>0,'long after oversold','short after overbought'))
                   .groupby(['pair','era','signal_mode','direction'],observed=True)
                   .apply(edge_record,include_groups=False).reset_index())
        display(direction[['pair','era','signal_mode','direction','n','mean_pips','cluster_t','win_rate']].round(3))

        horizon_rows=[]
        for h in ENDPOINT_HORIZONS_MIN:
            for keys,g in all_signals.groupby(['pair','era','signal_mode','low_threshold'],observed=True):
                row=dict(zip(['pair','era','signal_mode','low_threshold'],keys))
                row['horizon_min']=h
                row.update(edge_record(g,f'pnl_pips_h{h}',f'pnl_bp_h{h}').to_dict())
                horizon_rows.append(row)
        horizon_table=pd.DataFrame(horizon_rows)
        display(horizon_table.sort_values(['pair','era','signal_mode','low_threshold','horizon_min']).round(3))

        annual=(primary.groupby(['pair','signal_mode','year'],observed=True)
                .apply(edge_record,include_groups=False).reset_index())
        display(annual[['pair','signal_mode','year','n','mean_pips','cluster_t','win_rate']].round(3))
    """),
    code(r"""
        fig,axes=plt.subplots(len(PAIRS),2,figsize=(14,4.2*len(PAIRS)),squeeze=False)
        for row,pair in enumerate(PAIRS):
            for col,mode in enumerate(SIGNAL_MODES):
                p=annual.loc[(annual.pair==pair)&(annual.signal_mode==mode)]
                axes[row,col].bar(p.year,p.mean_pips,color=np.where(p.mean_pips>=0,'#2471a3','#c0392b'))
                axes[row,col].axhline(0,color='black',lw=1); axes[row,col].set_title(f'{pair} | {mode}')
                axes[row,col].set_ylabel('mean gross pips / signal')
        plt.suptitle('Annual stability of the primary 30-minute endpoint edge',y=1.01)
        plt.tight_layout(); plt.show()
    """),
    md(r"""
        ## 4. Where does the return occur, and how fragile is entry timing?

        Incremental segments prevent a cumulative 30-minute result from hiding that all profit occurred in the first minute.
        A fixed-clock delay keeps the original exit time and shortens exposure; fixed-hold delays both entry and exit so the
        holding period stays at 30 minutes. Both remain next-open simulations.
    """),
    code(r"""
        decomposition=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            for start,end in zip([0]+RETURN_DECOMPOSITION_BREAKS_MIN[:-1],RETURN_DECOMPOSITION_BREAKS_MIN):
                col=f'segment_{start}_{end}_pips'; z=g.loc[g[col].notna()]
                decomposition.append(dict(zip(['pair','era','signal_mode'],keys))|
                                     {'segment':f'{start}-{end}m','n':len(z),'mean_pips':z[col].mean(),
                                      'cluster_t':session_cluster_t(z[col],z.sdate)})
        decomposition=pd.DataFrame(decomposition)
        display(decomposition.round(3))

        delay_rows=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            for delay in ENTRY_DELAYS_MIN:
                for convention in ['fixed_clock','fixed_hold']:
                    col=f'delay_{delay}_{convention}_pips'; z=g.loc[g[col].notna()]
                    delay_rows.append(dict(zip(['pair','era','signal_mode'],keys))|
                        {'delay_min':delay,'convention':convention,'n':len(z),'mean_pips':z[col].mean(),
                         'cluster_t':session_cluster_t(z[col],z.sdate),'win_rate':z[col].gt(0).mean()})
        delay_table=pd.DataFrame(delay_rows)
        display(delay_table.round(3))
    """),
    md(r"""
        ## 5. Fakeout and full-reversal diagnostics

        Touch probabilities use only signals whose continuous future path covers the stated checkpoint. A 30-minute re-entry
        probability answers a different question from a 240-minute full-reversal probability, so the notebook reports them
        separately. Touches are reach diagnostics from minute highs/lows, not claims that a resting order filled before another
        level on the same bar.
    """),
    code(r"""
        def touch_curve(frame,touch_col,checkpoints):
            rows=[]
            for checkpoint in checkpoints:
                eligible=frame.loc[frame.path_available_min>=checkpoint]
                touch=eligible[touch_col]
                rows.append({'checkpoint_min':checkpoint,'eligible_n':len(eligible),
                             'touch_probability':touch.le(checkpoint).mean(),
                             'median_touch_min_if_touched':touch.loc[touch.le(checkpoint)].median()})
            return pd.DataFrame(rows)


        impulse_rows=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            for window in IMPULSE_WINDOWS_MIN:
                subset=g.loc[g[f'impulse_{window}_direction_consistent']]
                for label in ['half','full']:
                    curve=touch_curve(subset,f'{label}_retrace_{window}_min',REVERSAL_CHECKPOINTS_MIN)
                    curve['target']=f'{label}_{window}m_impulse'; curve['impulse_subset_n']=len(subset)
                    for name,value in zip(['pair','era','signal_mode'],keys): curve[name]=value
                    impulse_rows.append(curve)
        impulse_reversal=pd.concat(impulse_rows,ignore_index=True)
        display(impulse_reversal[['pair','era','signal_mode','target','impulse_subset_n','checkpoint_min',
                                  'eligible_n','touch_probability','median_touch_min_if_touched']].round(3))

        breakout_rows=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            for lookback in BREAKOUT_LOOKBACKS_MIN:
                subset=g.loc[g[f'breakout_{lookback}']]
                for target in ['range_reentry','range_midpoint','range_opposite']:
                    curve=touch_curve(subset,f'{target}_{lookback}_min',REVERSAL_CHECKPOINTS_MIN)
                    curve['target']=f'{target}_{lookback}m'; curve['all_extreme_n']=len(g)
                    curve['breakout_n']=len(subset); curve['breakout_share']=len(subset)/len(g) if len(g) else np.nan
                    for name,value in zip(['pair','era','signal_mode'],keys): curve[name]=value
                    breakout_rows.append(curve)
        breakout_reversal=pd.concat(breakout_rows,ignore_index=True)
        display(breakout_reversal[['pair','era','signal_mode','target','all_extreme_n','breakout_n','breakout_share',
                                   'checkpoint_min','eligible_n','touch_probability','median_touch_min_if_touched']].round(3))

        rsi50_rows=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            curve=touch_curve(g,'rsi50_exit_min',REVERSAL_CHECKPOINTS_MIN)
            for name,value in zip(['pair','era','signal_mode'],keys): curve[name]=value
            exited=g.loc[g.rsi50_exit_pips.notna()]
            curve['variable_exit_mean_pips']=exited.rsi50_exit_pips.mean()
            curve['variable_exit_cluster_t']=session_cluster_t(exited.rsi50_exit_pips,exited.sdate)
            rsi50_rows.append(curve)
        rsi50_table=pd.concat(rsi50_rows,ignore_index=True)
        display(rsi50_table.round(3))
    """),
    md(r"""
        ## 6. Which conditions strengthen the mean-reversion thesis?

        These are descriptive cuts, not separately validated rules. The table compares the unconditional RSI extreme with a
        directionally consistent 30-minute impulse, a 30-minute prior-range break, their intersection, and market-session bins.
        Any attractive cut remains a hypothesis until it survives a frozen specification and the untouched holdout.
    """),
    code(r"""
        condition_rows=[]
        impulse_window=30 if 30 in IMPULSE_WINDOWS_MIN else IMPULSE_WINDOWS_MIN[-1]
        breakout_window=30 if 30 in BREAKOUT_LOOKBACKS_MIN else BREAKOUT_LOOKBACKS_MIN[-1]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            masks={'all RSI extremes':np.ones(len(g),dtype=bool),
                   f'{impulse_window}m directional impulse':g[f'impulse_{impulse_window}_direction_consistent'].to_numpy(bool),
                   f'{breakout_window}m range break':g[f'breakout_{breakout_window}'].to_numpy(bool),
                   'range break + impulse':(g[f'breakout_{breakout_window}']&
                                             g[f'impulse_{impulse_window}_direction_consistent']).to_numpy(bool)}
            for label,mask in masks.items():
                z=g.loc[mask]; row=dict(zip(['pair','era','signal_mode'],keys))|{'condition':label}
                row.update(edge_record(z).to_dict())
                row['rsi50_by_60m']=z.loc[z.path_available_min>=60,'rsi50_exit_min'].le(60).mean()
                row[f'full_impulse_reversal_by_{REVERSAL_CHECKPOINTS_MIN[-1]}m']=(
                    z.loc[z.path_available_min>=REVERSAL_CHECKPOINTS_MIN[-1],f'full_retrace_{impulse_window}_min']
                     .le(REVERSAL_CHECKPOINTS_MIN[-1]).mean())
                condition_rows.append(row)
        condition_table=pd.DataFrame(condition_rows)
        display(condition_table.round(3))

        session_table=(primary.groupby(['pair','era','signal_mode','market_session'],observed=True)
                       .apply(edge_record,include_groups=False).reset_index())
        display(session_table[['pair','era','signal_mode','market_session','n','mean_pips','cluster_t','win_rate',
                               'mean_mfe_pips','mean_mae_pips']].round(3))

        # Coarse, within-pair quantiles avoid imposing one pair's pip/volatility scale on the other.
        condition_bins=primary.copy()
        condition_bins['impulse_size_bin']=(condition_bins.groupby('pair',observed=True)['past_return60_bp']
            .transform(lambda x: pd.qcut(x.abs(),4,labels=['Q1 small','Q2','Q3','Q4 large'],duplicates='drop')))
        impulse_size_table=(condition_bins.groupby(['pair','era','signal_mode','impulse_size_bin'],observed=True)
                            .apply(edge_record,include_groups=False).reset_index())
        display(impulse_size_table[['pair','era','signal_mode','impulse_size_bin','n','mean_pips','cluster_t','win_rate']].round(3))
    """),
    md(r"""
        ## 7. MFE, MAE, and hypothetical friction

        MFE is the greatest favorable movement during the first 30 minutes after entry; MAE is the greatest adverse movement.
        Both are positive magnitudes in log basis points and raw pips. Endpoint capture is mean endpoint P&L divided by mean
        MFE. The cost table subtracts a stated round-trip pip charge per signal; it is a sensitivity analysis, not a claim about
        historical executable spreads or fills.
    """),
    code(r"""
        excursion=(primary.groupby(['pair','era','signal_mode'],observed=True)
                   .apply(edge_record,include_groups=False).reset_index())
        display(excursion[['pair','era','signal_mode','n','mean_pips','mean_log_bp','mean_mfe_pips','mean_mae_pips',
                           'mfe_mae_ratio','endpoint_capture','mae_p90_pips','cluster_t']].round(3))

        cost_rows=[]
        for keys,g in primary.groupby(['pair','era','signal_mode'],observed=True):
            for cost in HYPOTHETICAL_COST_PIPS:
                z=g.loc[g.pnl_pips.notna()].copy(); z['net_pips']=z.pnl_pips-cost
                cost_rows.append(dict(zip(['pair','era','signal_mode'],keys))|
                    {'round_trip_cost_pips':cost,'n':len(z),'mean_net_pips':z.net_pips.mean(),
                     'cluster_t':session_cluster_t(z.net_pips,z.sdate),'net_win_rate':z.net_pips.gt(0).mean()})
        cost_table=pd.DataFrame(cost_rows)
        display(cost_table.round(3))
    """),
    md(r"""
        ## 8. Selection-aware session re-pairing null

        The exploration searches multiple RSI lengths, thresholds, signal clocks, and horizons. For each null draw, the entire
        return path of every New York session is reassigned to another session within the same year while keeping each signal's
        pair, year, and minute-of-session fixed. The declared search is repeated and its maximum cluster t-statistic retained.
        This preserves intraday shape and within-session outcome dependence while breaking the same-session signal/outcome link.
        The result calibrates endpoint search optimism; it does not validate the path-dependent reversal labels.
    """),
    code(r"""
        def fast_cluster_t(values,sessions):
            values=np.asarray(values,float); sessions=np.asarray(sessions)
            keep=np.isfinite(values) & pd.notna(sessions)
            values=values[keep]; sessions=sessions[keep]
            if len(values)<2:return np.nan
            codes,uniques=pd.factorize(sessions); groups=len(uniques)
            if groups<2:return np.nan
            mean=values.mean(); score=np.bincount(codes,weights=values-mean,minlength=groups)
            se=np.sqrt((groups/(groups-1))*np.square(score).sum())/len(values)
            return mean/se if se>0 else np.nan


        def evaluate_selection_null(pair,candidates,lookup,draws,seed):
            candidates=pd.concat(candidates,ignore_index=True)
            candidate_groups=list(candidates.groupby(['length','low','high','mode'],observed=True,sort=False))
            observed=[]
            for key,cand in candidate_groups:
                idx=pd.MultiIndex.from_arrays([cand.sdate,cand.slot],names=['sdate','slot'])
                for horizon in NULL_HORIZONS_MIN:
                    target=lookup[f'target_h{horizon}'].reindex(idx).to_numpy()
                    t=fast_cluster_t(cand.side.to_numpy()*target,cand.sdate.to_numpy())
                    observed.append((*key,horizon,len(cand),t))
            observed=pd.DataFrame(observed,columns=['length','low','high','mode','horizon','signal_n','cluster_t'])
            observed_max=observed.cluster_t.max()

            rng=np.random.default_rng(seed)
            available_dates=pd.DatetimeIndex(lookup.index.get_level_values('sdate').unique())
            date_by_year={year:dates for year,dates in pd.Series(available_dates,index=available_dates).groupby(available_dates.year)}
            null_max=[]
            for draw in range(draws):
                mapping={}
                for year,dates_series in date_by_year.items():
                    dates=pd.DatetimeIndex(dates_series.to_numpy())
                    donor=dates[rng.permutation(len(dates))]
                    mapping.update(dict(zip(dates,donor)))
                draw_best=-np.inf
                for _,cand in candidate_groups:
                    donors=pd.DatetimeIndex([mapping.get(pd.Timestamp(d),pd.NaT) for d in cand.sdate])
                    idx=pd.MultiIndex.from_arrays([donors,cand.slot],names=['sdate','slot'])
                    for horizon in NULL_HORIZONS_MIN:
                        target=lookup[f'target_h{horizon}'].reindex(idx).to_numpy()
                        t=fast_cluster_t(cand.side.to_numpy()*target,cand.sdate.to_numpy())
                        if np.isfinite(t): draw_best=max(draw_best,t)
                null_max.append(draw_best)
            null_max=np.asarray(null_max)
            p=(1+np.sum(null_max>=observed_max))/(1+len(null_max))
            summary={'pair':pair,'candidate_cells':len(observed),'observed_max_t':observed_max,
                     'null_draws':len(null_max),'null_max_t_median':np.nanmedian(null_max),
                     'null_max_t_p95':np.nanquantile(null_max,.95),'familywise_p':p}
            return observed.sort_values('cluster_t',ascending=False),null_max,summary


        null_summaries=[]; null_details={}; null_distributions={}
        if RUN_SELECTION_NULL:
            for pair,(candidates,lookup) in null_inputs.items():
                print(f'Selection null: {pair} ({NULL_DRAWS} draws) ...',flush=True)
                detail,distribution,summary=evaluate_selection_null(
                    pair,candidates,lookup,NULL_DRAWS,RANDOM_SEED+sum(map(ord,pair)))
                null_details[pair]=detail; null_distributions[pair]=distribution; null_summaries.append(summary)
                display(detail.head(12).round(3))
            selection_null_summary=pd.DataFrame(null_summaries)
            display(selection_null_summary.round(3))
        else:
            selection_null_summary=pd.DataFrame()
            print('Selection null skipped by configuration.')
    """),
    md(r"""
        ## 9. Interpretation checklist and exportable research tables

        Read the evidence in this order:

        1. Require the sign to agree across early and late exploration eras, across EURUSD and GBPUSD, and preferably both
           long and short directions. The late era is a robustness slice, **not** a holdout.
        2. Check incremental returns and delayed entries. A result that vanishes after one minute is unlikely to support a
           discretionary confirmation rule or slower execution.
        3. Distinguish simple mean re-entry, half retracement, and full reversal. They imply different exits and holding times.
        4. Compare MFE with MAE and the cost grid. A positive endpoint average with large adverse travel can still be impractical.
        5. Treat condition tables as new hypotheses and freeze any chosen rule before looking at 2024 onward.

        The notebook deliberately does not rank one final strategy or touch the holdout. It identifies which definition of
        “fakeout” is most stable and whether there is enough gross movement to justify a later execution-aware specification.
    """),
    code(r"""
        research_tables={'quality_report':quality_report,'headline':headline,'direction':direction,
                         'horizon_table':horizon_table,'annual':annual,'decomposition':decomposition,
                         'delay_table':delay_table,'impulse_reversal':impulse_reversal,
                         'breakout_reversal':breakout_reversal,'rsi50_table':rsi50_table,
                         'condition_table':condition_table,'session_table':session_table,
                         'impulse_size_table':impulse_size_table,'cost_table':cost_table,
                         'selection_null_summary':selection_null_summary}
        assert all_signals.ts_utc.max()<HOLDOUT_START
        assert not all_signals.ts_utc.ge(HOLDOUT_START).any()
        print(f'Complete: {len(all_signals):,} signal rows; max timestamp={all_signals.ts_utc.max()}')
        print('No 2024+ observation was loaded into the analysis panel. Objects in `research_tables` are ready for export.')
    """),
]

cells.extend([
    code(r"""
        def first_touch_minutes(side,highs,lows,target):
            touched=(highs>=target) if side>0 else (lows<=target)
            hits=np.flatnonzero(touched)
            return float(hits[0]+1) if len(hits) else np.nan


        def reversal_labels(raw,rsi,unique_signals):
            highs=raw.high.to_numpy(float); lows=raw.low.to_numpy(float)
            closes=raw.close.to_numpy(float); opens=raw.open.to_numpy(float)
            times=raw.time
            rows=[]
            for item in unique_signals.itertuples(index=False):
                pos=int(item.decision_pos); side=int(item.side)
                row={'decision_pos':pos,'side':side}
                max_end=min(pos+REVERSAL_MAX_HORIZON_MIN+1,len(raw)-1)
                if pos+1>=len(raw):
                    row['path_available_min']=0; rows.append(row); continue
                future_times=times.iloc[pos+1:max_end+1]
                if not len(future_times):
                    row['path_available_min']=0; rows.append(row); continue
                diffs=future_times.diff().iloc[1:].eq(pd.Timedelta(minutes=1)).to_numpy()
                breaks=np.flatnonzero(~diffs)
                available=int(breaks[0]+1) if len(breaks) else len(future_times)
                available=min(available,REVERSAL_MAX_HORIZON_MIN)
                row['path_available_min']=available
                path_hi=highs[pos+1:pos+1+available]
                path_lo=lows[pos+1:pos+1+available]
                future_rsi=rsi[pos+1:pos+1+available]

                neutral=np.flatnonzero(future_rsi>=50 if side>0 else future_rsi<=50)
                if len(neutral):
                    k=int(neutral[0]+1); exit_pos=pos+1+k
                    if exit_pos<len(raw) and times.iloc[exit_pos]==times.iloc[pos]+pd.Timedelta(minutes=k+1):
                        entry=opens[pos+1]; exit_price=opens[exit_pos]
                        row['rsi50_exit_min']=float(k)
                        row['rsi50_exit_bp']=side*1e4*np.log(exit_price/entry)
                        row['rsi50_exit_pips']=side*(exit_price-entry)/(0.01 if PAIR.endswith('JPY') else 0.0001)

                for window in IMPULSE_WINDOWS_MIN:
                    exact=pos>=window and times.iloc[pos-window]==times.iloc[pos]-pd.Timedelta(minutes=window)
                    anchor=closes[pos-window] if exact else np.nan
                    impulse=closes[pos]-anchor if exact else np.nan
                    consistent=np.isfinite(impulse) and side*impulse<0
                    row[f'impulse_{window}_direction_consistent']=bool(consistent)
                    row[f'impulse_{window}_pips']=abs(impulse)/(0.01 if PAIR.endswith('JPY') else 0.0001) if consistent else np.nan
                    if consistent and available:
                        half=closes[pos]-0.5*impulse
                        row[f'half_retrace_{window}_min']=first_touch_minutes(side,path_hi,path_lo,half)
                        row[f'full_retrace_{window}_min']=first_touch_minutes(side,path_hi,path_lo,anchor)

                for lookback in BREAKOUT_LOOKBACKS_MIN:
                    exact=pos>=lookback and times.iloc[pos-lookback]==times.iloc[pos]-pd.Timedelta(minutes=lookback)
                    if not exact:
                        row[f'breakout_{lookback}']=False; continue
                    prior_hi=float(np.max(highs[pos-lookback:pos])); prior_lo=float(np.min(lows[pos-lookback:pos]))
                    broke=(closes[pos]<prior_lo) if side>0 else (closes[pos]>prior_hi)
                    row[f'breakout_{lookback}']=bool(broke)
                    if broke and available:
                        boundary=prior_lo if side>0 else prior_hi
                        midpoint=(prior_hi+prior_lo)/2
                        opposite=prior_hi if side>0 else prior_lo
                        row[f'range_reentry_{lookback}_min']=first_touch_minutes(side,path_hi,path_lo,boundary)
                        row[f'range_midpoint_{lookback}_min']=first_touch_minutes(side,path_hi,path_lo,midpoint)
                        row[f'range_opposite_{lookback}_min']=first_touch_minutes(side,path_hi,path_lo,opposite)
                rows.append(row)
            return pd.DataFrame(rows)


        def build_pair_artifacts(pair):
            global PAIR
            PAIR=pair
            raw,one_minute,quality=load_pre_holdout(pair)
            pip=0.01 if pair.endswith('JPY') else 0.0001
            close=raw.close.to_numpy(float)
            main_rsi=wilder_rsi(close,one_minute,RSI_LENGTH)

            log_close=pd.Series(np.log(close))
            ret1=log_close.diff().where(one_minute)
            exact60=raw.time.shift(60).eq(raw.time-pd.Timedelta(minutes=60))
            rv60=np.sqrt(ret1.pow(2).rolling(60,min_periods=60).sum()).where(exact60)
            past60=(log_close-log_close.shift(60)).where(exact60)
            travelled60=ret1.abs().rolling(60,min_periods=60).sum().where(exact60)
            path_eff60=past60.abs()/travelled60.replace(0,np.nan)

            endpoint_bp={}; endpoint_pips={}
            all_horizons=sorted(set(ENDPOINT_HORIZONS_MIN+NULL_HORIZONS_MIN))
            for h in all_horizons:
                endpoint_bp[(0,h)],endpoint_pips[(0,h)]=endpoint_series(raw,1,1+h,pip)
            for delay in ENTRY_DELAYS_MIN:
                endpoint_bp[(delay,'fixed_clock')],endpoint_pips[(delay,'fixed_clock')]=endpoint_series(
                    raw,1+delay,1+PRIMARY_HORIZON_MIN,pip)
                endpoint_bp[(delay,'fixed_hold')],endpoint_pips[(delay,'fixed_hold')]=endpoint_series(
                    raw,1+delay,1+delay+PRIMARY_HORIZON_MIN,pip)
            excursions=path_excursions(raw,PRIMARY_HORIZON_MIN,pip)

            signal_frames=[]
            for low,high in THRESHOLD_PAIRS:
                for mode in SIGNAL_MODES:
                    positions,sides=signal_positions(raw,main_rsi,low,high,mode)
                    keep=(raw.time.iloc[positions].ge(EXPLORATION_START)&raw.time.iloc[positions].lt(HOLDOUT_START)).to_numpy()
                    positions,sides=positions[keep],sides[keep]
                    f=pd.DataFrame({'decision_pos':positions,'side':sides,'low_threshold':low,
                                    'high_threshold':high,'signal_mode':mode})
                    signal_frames.append(f)
            signals=pd.concat(signal_frames,ignore_index=True)
            positions=signals.decision_pos.to_numpy(int); sides=signals.side.to_numpy(int)
            signals['pair']=pair; signals['ts_utc']=raw.time.iloc[positions].to_numpy()
            signals['sdate']=raw.sdate.iloc[positions].to_numpy(); signals['year']=raw.time.iloc[positions].dt.year.to_numpy()
            signals['era']=np.where(signals.ts_utc<ERA_SPLIT,'early_exploration','late_exploration')
            signals['session_minute']=raw.session_minute.iloc[positions].to_numpy()
            signal_hours=raw.time.iloc[positions].dt.hour.to_numpy()
            signals['market_session']=np.select(
                [(signal_hours>=7)&(signal_hours<12),(signal_hours>=12)&(signal_hours<16),
                 (signal_hours>=16)&(signal_hours<22)],
                ['London morning','London/New York overlap','New York afternoon'],default='Asia/other')
            signals['weekday']=raw.time.iloc[positions].dt.day_name().str[:3].to_numpy()
            signals['rsi']=main_rsi[positions]
            lag5=np.full(len(positions),np.nan)
            eligible=positions>=5
            exact5=np.zeros(len(positions),dtype=bool)
            exact5[eligible]=(raw.time.iloc[positions[eligible]-5].to_numpy()==
                              (raw.time.iloc[positions[eligible]]-pd.Timedelta(minutes=5)).to_numpy())
            lag5[eligible&exact5]=main_rsi[positions[eligible&exact5]-5]
            signals['rsi_change_5m']=main_rsi[positions]-lag5
            signals['trailing_rv60_bp']=(1e4*rv60.iloc[positions]).to_numpy()
            signals['past_return60_bp']=(1e4*past60.iloc[positions]).to_numpy()
            signals['path_efficiency60']=path_eff60.iloc[positions].to_numpy()

            for h in ENDPOINT_HORIZONS_MIN:
                signals[f'pnl_bp_h{h}']=sides*endpoint_bp[(0,h)].iloc[positions].to_numpy()
                signals[f'pnl_pips_h{h}']=sides*endpoint_pips[(0,h)].iloc[positions].to_numpy()
            previous_break=0
            for end in RETURN_DECOMPOSITION_BREAKS_MIN:
                cumulative=signals[f'pnl_pips_h{end}']
                signals[f'segment_{previous_break}_{end}_pips']=cumulative-(signals[f'pnl_pips_h{previous_break}'] if previous_break else 0)
                previous_break=end
            for delay in ENTRY_DELAYS_MIN:
                signals[f'delay_{delay}_fixed_clock_pips']=sides*endpoint_pips[(delay,'fixed_clock')].iloc[positions].to_numpy()
                signals[f'delay_{delay}_fixed_hold_pips']=sides*endpoint_pips[(delay,'fixed_hold')].iloc[positions].to_numpy()

            ex=excursions.iloc[positions].reset_index(drop=True)
            signals['mfe_bp']=np.where(sides>0,ex.long_mfe_bp,ex.long_mae_bp)
            signals['mae_bp']=np.where(sides>0,ex.long_mae_bp,ex.long_mfe_bp)
            signals['mfe_pips']=np.where(sides>0,ex.long_mfe_pips,ex.long_mae_pips)
            signals['mae_pips']=np.where(sides>0,ex.long_mae_pips,ex.long_mfe_pips)
            signals['pnl_bp']=signals[f'pnl_bp_h{PRIMARY_HORIZON_MIN}']
            signals['pnl_pips']=signals[f'pnl_pips_h{PRIMARY_HORIZON_MIN}']

            unique=signals[['decision_pos','side']].drop_duplicates().sort_values('decision_pos')
            labels=reversal_labels(raw,main_rsi,unique)
            signals=signals.merge(labels,on=['decision_pos','side'],how='left',validate='many_to_one')

            # Null candidates and a same-minute target lookup are retained compactly.
            null_candidates=[]
            rsi_cache={RSI_LENGTH:main_rsi}
            for length in NULL_RSI_LENGTHS:
                if length not in rsi_cache:rsi_cache[length]=wilder_rsi(close,one_minute,length)
                for low,high in THRESHOLD_PAIRS:
                    for mode in SIGNAL_MODES:
                        p,s=signal_positions(raw,rsi_cache[length],low,high,mode)
                        keep=(raw.time.iloc[p].ge(EXPLORATION_START)&raw.time.iloc[p].lt(HOLDOUT_START)).to_numpy()
                        p,s=p[keep],s[keep]
                        null_candidates.append(pd.DataFrame({'decision_pos':p,'side':s,'length':length,
                            'low':low,'high':high,'mode':mode,'sdate':raw.sdate.iloc[p].to_numpy(),
                            'year':raw.time.iloc[p].dt.year.to_numpy(),'slot':raw.session_minute.iloc[p].to_numpy()}))
            lookup=pd.DataFrame({'sdate':raw.sdate,'slot':raw.session_minute,'year':raw.time.dt.year})
            for h in NULL_HORIZONS_MIN: lookup[f'target_h{h}']=endpoint_pips[(0,h)].to_numpy()
            lookup=lookup.loc[raw.time.ge(EXPLORATION_START)&raw.time.lt(HOLDOUT_START)].drop_duplicates(['sdate','slot'])
            lookup=lookup.set_index(['sdate','slot'])

            quality.update({'signals':len(signals),'unique_signal_events':len(unique),
                            'primary_target_coverage':signals.pnl_pips.notna().mean(),
                            'reversal_full_path_coverage':signals.path_available_min.ge(REVERSAL_MAX_HORIZON_MIN).mean()})
            del raw,excursions,ret1,rv60,past60,path_eff60,rsi_cache
            gc.collect()
            return signals,quality,null_candidates,lookup


        pair_signals={}; quality_rows=[]; null_inputs={}
        for pair in PAIRS:
            print(f'Building {pair} ...',flush=True)
            pair_signals[pair],quality,candidates,lookup=build_pair_artifacts(pair)
            quality_rows.append(quality); null_inputs[pair]=(candidates,lookup)
            print(f"  {len(pair_signals[pair]):,} signal rows; {quality['unique_signal_events']:,} unique events")
        quality_report=pd.DataFrame(quality_rows).set_index('pair')
        display(quality_report.T)
        all_signals=pd.concat(pair_signals.values(),ignore_index=True)
        assert all_signals.ts_utc.max()<HOLDOUT_START
    """),
])

cells.extend(analysis_cells)

notebook = {
    "cells": cells,
    "metadata": {
        "kernelspec": {"display_name":"Python 3","language":"python","name":"python3"},
        "language_info": {"name":"python","version":"3.11"}
    },
    "nbformat": 4,
    "nbformat_minor": 5,
}

OUT.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding="utf-8")
print(f"Wrote {OUT} with {len(cells)} cells")
