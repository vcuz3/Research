"""Build the RSI clock-confound and feature-interaction exploration notebook."""

from pathlib import Path
from textwrap import dedent
import hashlib
import json

ROOT = Path(__file__).resolve().parent
OUT = ROOT / "rsi_clock_feature_interactions.ipynb"


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
        # RSI signal-clock confound and feature-interaction exploration

        This notebook tests the hypothesis that scheduled RSI extremes appear stronger than first-crossing signals primarily
        because their RSI readings are more extreme. It then asks which causal market-state features strengthen or weaken the
        relationship between RSI severity and subsequent mean-reversion returns.

        The analysis is deliberately exploratory and uses only pre-2024 EURUSD and GBPUSD minute data. It reports 2012–2020
        (`early_exploration`) and 2021–2023 (`late_exploration`) separately. The late era is an internal stability check—not a
        fresh holdout—and 2024+ is neither loaded nor scored.

        All outcomes enter at the next minute open after the completed signal bar and exit at an exact future open. Feature
        windows require continuous minute coverage. Midpoint prices contain no executable spread, so every return is gross.
    """),
    code(r"""
        from pathlib import Path
        import gc, os, warnings
        import numpy as np
        import pandas as pd
        import matplotlib.pyplot as plt
        import seaborn as sns
        from scipy.signal import lfilter
        from scipy.stats import spearmanr
        import statsmodels.api as sm
        import statsmodels.formula.api as smf
        from IPython.display import display

        warnings.filterwarnings('ignore',category=FutureWarning)
        sns.set_theme(style='whitegrid',context='notebook')
        pd.set_option('display.max_columns',200); pd.set_option('display.width',240)

        PAIRS=['EURUSD','GBPUSD']
        EXPLORATION_START=pd.Timestamp('2012-01-01',tz='UTC')
        ERA_SPLIT=pd.Timestamp('2021-01-01',tz='UTC')
        HOLDOUT_START=pd.Timestamp('2024-01-01',tz='UTC')
        RSI_LENGTH=14; RSI_LOW=30.0; RSI_HIGH=70.0
        SIGNAL_MODES=['scheduled_state','first_crossing_cooldown']
        SCHEDULE_INTERVAL_MIN=30; EVENT_COOLDOWN_MIN=30
        HORIZONS_MIN=[5,15,30,60]; PRIMARY_HORIZON_MIN=30
        SLOT_LOOKBACK=252; SLOT_MIN_OBS=126
        RSI_DEPTH_BIN_WIDTH=0.5; MIN_MATCH_CELL_N=30; MIN_SCREEN_N=250
        REPRO_TOLERANCE_PIPS=0.03
        PRIMARY_FEATURES_TO_PLOT=['vei_pct','range_break_30m','rv_30m_bp','range_rv_30m_bp',
                                  'impulse_30m_bp','extreme_age_min']
        CSV_CHUNK_ROWS=750_000

        SMOKE_MODE=os.getenv('RSI_INTERACTION_SMOKE','0')=='1'
        if SMOKE_MODE:
            PAIRS=PAIRS[:1]; HORIZONS_MIN=[5,30]; PRIMARY_FEATURES_TO_PLOT=PRIMARY_FEATURES_TO_PLOT[:3]

        assert EXPLORATION_START<ERA_SPLIT<HOLDOUT_START
        assert PRIMARY_HORIZON_MIN in HORIZONS_MIN
        here=Path.cwd().resolve()
        if here.name=='exploration_1': project_root=here
        elif (here/'forex'/'exploration_1').exists(): project_root=here/'forex'/'exploration_1'
        else: raise FileNotFoundError('Run from workspace root or forex/exploration_1.')
        data_dir=project_root.parent/'data'
        print(f'Pairs={PAIRS}; horizons={HORIZONS_MIN}; early=[{EXPLORATION_START},{ERA_SPLIT}); late=[{ERA_SPLIT},{HOLDOUT_START})')
        print('HOLDOUT POLICY: no row at or after 2024-01-01 is retained.')
    """),
    md(r"""
        ## 1. Estimands and interpretation

        For a long-after-oversold signal, `side = +1`; for a short-after-overbought signal, `side = -1`. Signed P&L is
        `side × future return`, so positive values mean mean reversion in either direction.

        `rsi_depth` is distance beyond the relevant threshold: `30 − RSI` for longs and `RSI − 70` for shorts. It equals zero
        at the crossing boundary and grows with severity. The clock comparison is evaluated four ways:

        1. raw mean difference;
        2. common-support comparison in half-RSI-point bins;
        3. session-clustered regression controlling flexibly for RSI depth, side, and time of day;
        4. a diagnostic model additionally controlling for extreme age and causal market state.

        The interaction screen fits `P&L ~ RSI depth + feature + RSI depth × feature`. A positive interaction means the feature
        strengthens the payoff gradient with RSI severity; a feature main effect alone means the market state changes average
        P&L without necessarily changing RSI's information. Early-era scaling and feature cutpoints are applied unchanged to the
        late era. Benjamini–Hochberg q-values address the declared feature screen, but do not make this confirmatory research.
    """),
]

cells.extend([
    code(r"""
        def load_pre_holdout(pair):
            clean_path=data_dir/'clean'/f'{pair}_1m_clean.parquet'
            csv_candidates=[data_dir/f'{pair.lower()}_intraday_1min.csv',
                            data_dir/'archive'/f'{pair.lower()}_intraday_1min.csv']
            duplicates=out_of_order=0; boundary=False
            if clean_path.exists():
                raw=pd.read_parquet(clean_path,columns=['ts_utc','open','high','low','close'],
                                    filters=[('ts_utc','<',HOLDOUT_START.tz_localize(None))])
                raw=raw.rename(columns={'ts_utc':'time'}); raw['volume']=-1.; source=str(clean_path)
                raw['time']=pd.to_datetime(raw.time,utc=True); boundary=True
                duplicates=int(raw.time.duplicated().sum()); out_of_order=int((raw.time.diff().dropna()<=pd.Timedelta(0)).sum())
            else:
                path=next((p for p in csv_candidates if p.exists()),None); assert path is not None,'No cleaned parquet or archive CSV found.'
                dtype={c:'float32' for c in ['open','high','low','close','volume']}; kept=[]; previous=None; source=str(path)
                for chunk in pd.read_csv(path,dtype=dtype,parse_dates=['time'],chunksize=CSV_CHUNK_ROWS):
                    chunk['time']=(chunk.time.dt.tz_localize('UTC') if chunk.time.dt.tz is None else chunk.time.dt.tz_convert('UTC'))
                    duplicates+=int(chunk.time.duplicated().sum()); out_of_order+=int((chunk.time.diff().dropna()<=pd.Timedelta(0)).sum())
                    if previous is not None and len(chunk) and chunk.time.iloc[0]<=previous: out_of_order+=1
                    if len(chunk): previous=chunk.time.iloc[-1]
                    before=chunk.loc[chunk.time<HOLDOUT_START].copy()
                    if len(before): kept.append(before)
                    if chunk.time.ge(HOLDOUT_START).any(): boundary=True; break
                raw=pd.concat(kept,ignore_index=True)
            assert len(raw) and raw.time.max()<HOLDOUT_START and duplicates==0 and out_of_order==0
            ny=raw.time.dt.tz_convert('America/New_York'); ny_min=ny.dt.hour*60+ny.dt.minute
            ny_date=ny.dt.tz_localize(None).dt.normalize()
            raw['sdate']=ny_date+pd.to_timedelta((ny_min>=17*60).astype(int),unit='D')
            raw['session_minute']=((ny_min-17*60)%1440).astype('int16')
            raw['utc_minute']=(raw.time.dt.hour*60+raw.time.dt.minute).astype('int16')
            dt=raw.time.diff(); one=dt.eq(pd.Timedelta(minutes=1)).to_numpy()
            bad=((raw.high<raw[['open','close','low']].max(axis=1))|
                 (raw.low>raw[['open','close','high']].min(axis=1)))
            quality={'pair':pair,'source':source,'rows':len(raw),'first':raw.time.min(),'last':raw.time.max(),
                     'sessions':raw.sdate.nunique(),'boundary_reached':boundary,'duplicates':duplicates,
                     'out_of_order':out_of_order,'gaps_gt_1m':int(dt.gt(pd.Timedelta(minutes=1)).sum()),
                     'largest_gap_min':dt.dt.total_seconds().div(60).max(),'ohlc_failures':int(bad.sum()),
                     'nonpositive_rows':int(raw[['open','high','low','close']].le(0).any(axis=1).sum()),
                     'volume_minus_one_share':raw.volume.eq(-1).mean()}
            assert quality['ohlc_failures']==0 and quality['nonpositive_rows']==0
            return raw,one,quality


        def sma_seeded_recursive(values,starts,ends,length,alpha):
            out=np.full(len(values),np.nan,float)
            for start,end in zip(starts,ends):
                x=values[start:end]
                if len(x)<length: continue
                seed=float(np.mean(x[:length])); k=start+length-1; out[k]=seed
                if len(x)>length:
                    filtered,_=lfilter([alpha],[1.,-(1.-alpha)],x[length:],zi=[(1.-alpha)*seed])
                    out[k+1:end]=filtered
            return out


        def recursive_wilder(values,one_minute,length):
            starts=np.flatnonzero(~one_minute); ends=np.r_[starts[1:],len(values)]
            return sma_seeded_recursive(np.asarray(values,float),starts,ends,length,1./length)


        def wilder_rsi(close,one_minute,length):
            starts=np.flatnonzero(~one_minute); ends=np.r_[starts[1:],len(close)]
            delta=np.diff(close,prepend=close[0]); delta[starts]=0
            ag=sma_seeded_recursive(np.clip(delta,0,None),starts,ends,length,1./length)
            al=sma_seeded_recursive(np.clip(-delta,0,None),starts,ends,length,1./length)
            rs=np.divide(ag,al,out=np.full_like(ag,np.nan),where=al>0); rsi=100-100/(1+rs)
            rsi[(al==0)&(ag==0)]=50; rsi[(al==0)&(ag>0)]=100
            return rsi


        def exact_lag(series,time,minutes):
            return series.shift(minutes).where(time.shift(minutes).eq(time-pd.Timedelta(minutes=minutes)))


        def exact_return_roll(series,time,window,op='sum'):
            rolled=getattr(series.rolling(window,min_periods=window),op)()
            return rolled.where(time.shift(window).eq(time-pd.Timedelta(minutes=window)))


        def cooldown_positions(positions,times,cooldown):
            accepted=[]; last=None
            for pos in positions:
                now=times.iloc[pos]
                if last is None or now-last>=pd.Timedelta(minutes=cooldown): accepted.append(pos); last=now
            return np.asarray(accepted,int)


        def signal_positions(raw,rsi,mode):
            side=np.select([rsi<=RSI_LOW,rsi>=RSI_HIGH],[1,-1],default=0).astype('int8')
            if mode=='scheduled_state':
                mask=raw.utc_minute.mod(SCHEDULE_INTERVAL_MIN).eq(SCHEDULE_INTERVAL_MIN-1).to_numpy()&(side!=0)
                pos=np.flatnonzero(mask)
            else:
                prev=np.roll(rsi,1); prev[0]=np.nan; exact=raw.time.diff().eq(pd.Timedelta(minutes=1)).to_numpy()
                crossed=(((side==1)&(prev>RSI_LOW))|((side==-1)&(prev<RSI_HIGH)))&exact
                pos=cooldown_positions(np.flatnonzero(crossed),raw.time,EVENT_COOLDOWN_MIN)
            return pos,side[pos]


        def endpoint(raw,horizon,pip):
            entry=raw.open.shift(-1).astype(float); exit_=raw.open.shift(-(horizon+1)).astype(float)
            exact=(raw.time.shift(-1).eq(raw.time+pd.Timedelta(minutes=1))&
                   raw.time.shift(-(horizon+1)).eq(raw.time+pd.Timedelta(minutes=horizon+1)))
            return (1e4*np.log(exit_/entry)).where(exact),((exit_-entry)/pip).where(exact)


        def causal_event_slot_stats(values,slots,event_positions,lookback=SLOT_LOOKBACK,min_obs=SLOT_MIN_OBS):
            values=np.asarray(values,float); slots=np.asarray(slots); event_positions=np.asarray(event_positions,int)
            pct=np.full(len(event_positions),np.nan); z=np.full(len(event_positions),np.nan)
            for slot in np.unique(slots[event_positions]):
                hist_pos=np.flatnonzero(slots==slot); hist_values=values[hist_pos]
                event_idx=np.flatnonzero(slots[event_positions]==slot); ep=event_positions[event_idx]
                loc=np.searchsorted(hist_pos,ep)
                for out_i,k in zip(event_idx,loc):
                    hist=hist_values[max(0,k-lookback):k]; hist=hist[np.isfinite(hist)]
                    value=values[event_positions[out_i]]
                    if np.isfinite(value) and len(hist)>=min_obs:
                        pct[out_i]=np.mean(hist<value); sd=np.std(hist,ddof=1)
                        z[out_i]=(value-np.mean(hist))/sd if sd>0 else np.nan
            return pct,z


        def session_cluster_t(values,sessions):
            z=pd.DataFrame({'x':values,'s':sessions}).dropna(); n=len(z); G=z.s.nunique()
            if n<2 or G<2:return np.nan
            mean=z.x.mean(); score=(z.x-mean).groupby(z.s).sum(); se=np.sqrt((G/(G-1))*np.square(score).sum())/n
            return mean/se if se>0 else np.nan


        def bh_adjust(p):
            p=np.asarray(p,float); out=np.full(len(p),np.nan); ok=np.isfinite(p)
            if not ok.any():return out
            x=p[ok]; order=np.argsort(x); ranked=x[order]; q=ranked*len(x)/np.arange(1,len(x)+1)
            q=np.minimum.accumulate(q[::-1])[::-1].clip(0,1); restored=np.empty(len(x)); restored[order]=q; out[ok]=restored
            return out
    """),
    md(r"""
        ## 2. Build the causal event-feature panel

        The panel contains only accepted events from the two signal clocks, but every feature is computed from the complete
        minute history available at the completed signal bar. `vei_pct` and `rv_30m_slot_z` use only the preceding 252 observed
        sessions at the same minute-of-session and require 126 prior observations. Range-break levels exclude the signal bar.
    """),
    code(r"""
        FEATURE_GROUPS={
            'rsi_state':['extreme_age_min','rsi_change_5_aligned'],
            'vei':['vei_raw','vei_pct','vei_z_252'],
            'volatility':['rv_5m_bp','rv_15m_bp','rv_30m_bp','rv_60m_bp','rv_30m_slot_z',
                          'rv_ratio_5_30','rv_ratio_15_60'],
            'range_volatility':['range_rv_15m_bp','range_rv_30m_bp','range_rv_60m_bp','range_ratio_15_60'],
            'impulse_extension':['impulse_5m_bp','impulse_15m_bp','impulse_30m_bp','impulse_60m_bp',
                                 'range_break_15m','range_break_30m','range_break_60m','break_distance_atr_30m',
                                 'donchian_extension_30m','twap_extension_atr','ema_extension_atr','bollinger_extension'],
            'path_shape':['path_efficiency_15m','path_efficiency_30m','path_efficiency_60m',
                          'adverse_semivar_30m_bp','counter_semivar_30m_bp','max_abs_ret_30m_bp',
                          'jump_share_30m','concentration_30m','return_autocorr_30m','variance_ratio_30m',
                          'zero_return_share_30m','bar_range_atr','close_rejection'],
            'session_state':['session_range_bp','session_impulse_bp','session_progress','london_open',
                             'newyork_open','london_newyork_overlap']
        }
        feature_columns=list(dict.fromkeys(x for group in FEATURE_GROUPS.values() for x in group))


        def build_pair_events(pair):
            raw,one,quality=load_pre_holdout(pair); pip=.0001
            time=raw.time; close=raw.close.to_numpy(float); logc=pd.Series(np.log(close)); ret1=logc.diff().where(one)
            rsi=wilder_rsi(close,one,RSI_LENGTH)

            # Recursive true range indicators restart after every missing-minute link.
            prev_close=np.r_[np.nan,close[:-1]]; tr=np.maximum.reduce([
                raw.high.to_numpy(float)-raw.low.to_numpy(float),np.abs(raw.high.to_numpy(float)-prev_close),
                np.abs(raw.low.to_numpy(float)-prev_close)])
            tr[~one]=(raw.high-raw.low).to_numpy(float)[~one]
            atr10=recursive_wilder(tr,one,10); atr14=recursive_wilder(tr,one,14); atr50=recursive_wilder(tr,one,50)
            vei=np.divide(atr10,atr50,out=np.full(len(raw),np.nan),where=atr50>0)

            rv={}; range_rv={}; range_log=pd.Series(np.log(raw.high.astype(float)/raw.low.astype(float))).where(one)
            for w in [5,15,30,60]:
                rv[w]=np.sqrt(exact_return_roll(ret1.pow(2),time,w,'sum'))
            for w in [15,30,60]: range_rv[w]=np.sqrt(exact_return_roll(range_log.pow(2),time,w,'sum'))
            negsv=np.sqrt(exact_return_roll(ret1.clip(upper=0).pow(2),time,30,'sum'))
            possv=np.sqrt(exact_return_roll(ret1.clip(lower=0).pow(2),time,30,'sum'))
            absret=ret1.abs(); rv2=exact_return_roll(ret1.pow(2),time,30,'sum')
            bv=(np.pi/2)*exact_return_roll(absret*absret.shift(1),time,29,'sum')
            max_abs=exact_return_roll(absret,time,30,'max')
            concentration=exact_return_roll(ret1.pow(2),time,30,'max')/rv2.replace(0,np.nan)
            autocorr=ret1.rolling(30,min_periods=30).corr(ret1.shift(1)).where(time.shift(30).eq(time-pd.Timedelta(minutes=30)))
            zero_share=exact_return_roll(ret1.eq(0).where(ret1.notna()).astype(float),time,30,'mean')

            typical=(raw.high.astype(float)+raw.low.astype(float)+raw.close.astype(float))/3
            same_session=raw.sdate.eq(raw.sdate.shift(1)); elapsed=time.diff().dt.total_seconds().div(60).where(same_session,1).clip(lower=1)
            weighted=typical+(elapsed-1).clip(lower=0)*typical.shift(1).where(same_session,typical)
            twap=weighted.groupby(raw.sdate,sort=False).cumsum()/elapsed.groupby(raw.sdate,sort=False).cumsum()
            segment=pd.Series(np.cumsum(~one))
            ema12=raw.close.groupby(segment).transform(lambda s:s.ewm(span=12,adjust=False,min_periods=12).mean())
            ema26=raw.close.groupby(segment).transform(lambda s:s.ewm(span=26,adjust=False,min_periods=26).mean())
            mean60=logc.rolling(60,min_periods=60).mean().where(time.shift(59).eq(time-pd.Timedelta(minutes=59)))
            sd60=logc.rolling(60,min_periods=60).std().where(time.shift(59).eq(time-pd.Timedelta(minutes=59)))
            clv=(((raw.close-raw.low)-(raw.high-raw.close))/(raw.high-raw.low).replace(0,np.nan))

            prior={}
            for w in [15,30,60]:
                exact=time.shift(w).eq(time-pd.Timedelta(minutes=w))
                prior[w]=(raw.high.shift(1).rolling(w,min_periods=w).max().where(exact),
                          raw.low.shift(1).rolling(w,min_periods=w).min().where(exact))

            session_open=raw.open.groupby(raw.sdate).transform('first').astype(float)
            session_hi=raw.high.groupby(raw.sdate).cummax().astype(float); session_lo=raw.low.groupby(raw.sdate).cummin().astype(float)
            session_ret=1e4*np.log(raw.close.astype(float)/session_open); session_range=1e4*np.log(session_hi/session_lo)
            london=time.dt.tz_convert('Europe/London'); newyork=time.dt.tz_convert('America/New_York')
            london_open=london.dt.hour.between(8,16).astype('int8'); newyork_open=newyork.dt.hour.between(8,16).astype('int8')

            minute_side=np.select([rsi<=RSI_LOW,rsi>=RSI_HIGH],[1,-1],default=0).astype('int8')
            age=np.zeros(len(raw),dtype='int16')
            for i in range(1,len(raw)):
                if one[i] and minute_side[i]!=0 and minute_side[i]==minute_side[i-1]: age[i]=min(age[i-1]+1,32767)

            frames=[]
            for mode in SIGNAL_MODES:
                pos,side=signal_positions(raw,rsi,mode)
                keep=(time.iloc[pos].ge(EXPLORATION_START)&time.iloc[pos].lt(HOLDOUT_START)).to_numpy(); pos=pos[keep]; side=side[keep]
                frames.append(pd.DataFrame({'decision_pos':pos,'side':side,'signal_mode':mode}))
            e=pd.concat(frames,ignore_index=True); pos=e.decision_pos.to_numpy(int); side=e.side.to_numpy(int)
            e['pair']=pair; e['ts_utc']=time.iloc[pos].to_numpy(); e['sdate']=raw.sdate.iloc[pos].to_numpy()
            e['era']=np.where(e.ts_utc<ERA_SPLIT,'early_exploration','late_exploration')
            e['direction']=np.where(side>0,'long','short'); e['utc_hour']=time.iloc[pos].dt.hour.to_numpy()
            e['session_minute']=raw.session_minute.iloc[pos].to_numpy(); e['rsi']=rsi[pos]
            e['rsi_depth']=np.where(side>0,RSI_LOW-rsi[pos],rsi[pos]-RSI_HIGH); e['extreme_age_min']=age[pos]

            # Outcomes and primary-horizon path excursions.
            for h in HORIZONS_MIN:
                bp,pips=endpoint(raw,h,pip); e[f'pnl_bp_h{h}']=side*bp.iloc[pos].to_numpy(); e[f'pnl_pips_h{h}']=side*pips.iloc[pos].to_numpy()
            h=PRIMARY_HORIZON_MIN; entry=raw.open.shift(-1).astype(float); exit_=raw.open.shift(-(h+1)).astype(float)
            exact=(time.shift(-1).eq(time+pd.Timedelta(minutes=1))&time.shift(-(h+1)).eq(time+pd.Timedelta(minutes=h+1)))
            hi=raw.high.astype(float).shift(-1).iloc[::-1].rolling(h,min_periods=h).max().iloc[::-1]
            lo=raw.low.astype(float).shift(-1).iloc[::-1].rolling(h,min_periods=h).min().iloc[::-1]
            hi=pd.concat([hi,entry,exit_],axis=1).max(axis=1).where(exact); lo=pd.concat([lo,entry,exit_],axis=1).min(axis=1).where(exact)
            long_mfe=(hi-entry)/pip; long_mae=(entry-lo)/pip
            e['mfe_pips']=np.where(side>0,long_mfe.iloc[pos],long_mae.iloc[pos]); e['mae_pips']=np.where(side>0,long_mae.iloc[pos],long_mfe.iloc[pos])

            take=lambda x:pd.Series(x,index=raw.index).iloc[pos].to_numpy()
            lag5=exact_lag(pd.Series(rsi),time,5); e['rsi_change_5_aligned']=-side*(rsi[pos]-lag5.iloc[pos].to_numpy())
            e['vei_raw']=vei[pos]
            unique_pos=np.unique(pos); pct,z=causal_event_slot_stats(vei,raw.session_minute.to_numpy(),unique_pos)
            pct_map=pd.Series(pct,index=unique_pos); z_map=pd.Series(z,index=unique_pos)
            e['vei_pct']=e.decision_pos.map(pct_map); e['vei_z_252']=e.decision_pos.map(z_map)

            for w in [5,15,30,60]: e[f'rv_{w}m_bp']=1e4*take(rv[w])
            _,rvz=causal_event_slot_stats(pd.Series(rv[30]).to_numpy(),raw.session_minute.to_numpy(),unique_pos)
            e['rv_30m_slot_z']=e.decision_pos.map(pd.Series(rvz,index=unique_pos))
            e['rv_ratio_5_30']=e.rv_5m_bp/e.rv_30m_bp.replace(0,np.nan); e['rv_ratio_15_60']=e.rv_15m_bp/e.rv_60m_bp.replace(0,np.nan)
            for w in [15,30,60]:
                e[f'range_rv_{w}m_bp']=1e4*take(range_rv[w])
                past=logc-exact_lag(logc,time,w); travelled=exact_return_roll(absret,time,w,'sum')
                e[f'path_efficiency_{w}m']=take(past.abs()/travelled.replace(0,np.nan))
            e['range_ratio_15_60']=e.range_rv_15m_bp/e.range_rv_60m_bp.replace(0,np.nan)

            for w in [5,15,30,60]: e[f'impulse_{w}m_bp']=-side*1e4*take(logc-exact_lag(logc,time,w))
            for w in [15,30,60]:
                ph,pl=prior[w]; phv=ph.iloc[pos].to_numpy(); plv=pl.iloc[pos].to_numpy()
                broke=np.where(side>0,raw.close.iloc[pos].to_numpy()<plv,raw.close.iloc[pos].to_numpy()>phv).astype(float)
                broke[~(np.isfinite(phv)&np.isfinite(plv))]=np.nan
                e[f'range_break_{w}m']=broke
            ph30,pl30=prior[30]; boundary=np.where(side>0,pl30.iloc[pos],ph30.iloc[pos]); distance=side*(boundary-raw.close.iloc[pos].to_numpy())
            e['break_distance_atr_30m']=distance/atr14[pos]
            prange=(ph30-pl30).iloc[pos].to_numpy()
            e['donchian_extension_30m']=np.divide(distance,prange,out=np.full(len(distance),np.nan),where=prange>0)
            e['twap_extension_atr']=-side*(raw.close.iloc[pos].to_numpy()-twap.iloc[pos].to_numpy())/atr14[pos]
            e['ema_extension_atr']=-side*(ema12.iloc[pos].to_numpy()-ema26.iloc[pos].to_numpy())/atr14[pos]
            e['bollinger_extension']=-side*take((logc-mean60)/sd60.replace(0,np.nan))

            e['adverse_semivar_30m_bp']=1e4*np.where(side>0,negsv.iloc[pos],possv.iloc[pos])
            e['counter_semivar_30m_bp']=1e4*np.where(side>0,possv.iloc[pos],negsv.iloc[pos])
            e['max_abs_ret_30m_bp']=1e4*take(max_abs); e['jump_share_30m']=take((rv2-bv).clip(lower=0)/rv2.replace(0,np.nan))
            e['concentration_30m']=take(concentration); e['return_autocorr_30m']=take(autocorr)
            past30=logc-exact_lag(logc,time,30); e['variance_ratio_30m']=take(past30.pow(2)/rv2.replace(0,np.nan))
            e['zero_return_share_30m']=take(zero_share); e['bar_range_atr']=(raw.high.iloc[pos].to_numpy()-raw.low.iloc[pos].to_numpy())/atr14[pos]
            e['close_rejection']=side*clv.iloc[pos].to_numpy()
            e['session_range_bp']=session_range.iloc[pos].to_numpy(); e['session_impulse_bp']=-side*session_ret.iloc[pos].to_numpy()
            e['session_progress']=e.session_minute/1440.; e['london_open']=london_open.iloc[pos].to_numpy()
            e['newyork_open']=newyork_open.iloc[pos].to_numpy(); e['london_newyork_overlap']=e.london_open*e.newyork_open

            quality.update({'events':len(e),'scheduled_events':int(e.signal_mode.eq('scheduled_state').sum()),
                            'crossing_events':int(e.signal_mode.eq('first_crossing_cooldown').sum()),
                            'primary_target_coverage':e[f'pnl_pips_h{PRIMARY_HORIZON_MIN}'].notna().mean(),
                            'vei_pct_coverage':e.vei_pct.notna().mean()})
            assert set(feature_columns)<=set(e.columns); assert e.ts_utc.max()<HOLDOUT_START
            return e,quality


        event_frames=[]; quality=[]
        for pair in PAIRS:
            print(f'Building {pair} ...',flush=True); frame,q=build_pair_events(pair); event_frames.append(frame); quality.append(q)
            print(f'  {len(frame):,} events',flush=True); gc.collect()
        events=pd.concat(event_frames,ignore_index=True); quality_report=pd.DataFrame(quality).set_index('pair')
        display(quality_report.T)
        assert events.ts_utc.max()<HOLDOUT_START
    """),
    code(r"""
        # Rule 9a: target/feature exclusions by era, signal clock, and time-of-day.
        events['time_block']=pd.cut(events.utc_hour,[0,7,12,16,24],right=False,
                                    labels=['00-07 UTC','07-12 UTC','12-16 UTC','16-24 UTC'],include_lowest=True)
        coverage_rows=[]
        for keys,g in events.groupby(['pair','era','signal_mode','time_block'],observed=True):
            base=dict(zip(['pair','era','signal_mode','time_block'],keys))|{'events':len(g)}
            for col in [f'pnl_pips_h{PRIMARY_HORIZON_MIN}','vei_pct','rv_30m_slot_z']+feature_columns:
                coverage_rows.append(base|{'field':col,'coverage':g[col].notna().mean(),'missing_n':int(g[col].isna().sum())})
        coverage_report=pd.DataFrame(coverage_rows)
        display(coverage_report.loc[coverage_report.field.isin([f'pnl_pips_h{PRIMARY_HORIZON_MIN}','vei_pct','rv_30m_slot_z'])].round(4))
        worst_feature_coverage=(coverage_report.loc[coverage_report.field.isin(feature_columns)]
                                .sort_values('coverage').groupby(['pair','era','signal_mode'],observed=True).head(8))
        display(worst_feature_coverage.round(4))

        # Reproduce the previously evaluated RSI fakeout notebook before extending its interpretation.
        previous_reference={
            ('EURUSD','early_exploration','scheduled_state'):0.646277,
            ('EURUSD','late_exploration','scheduled_state'):0.694797,
            ('EURUSD','early_exploration','first_crossing_cooldown'):0.417675,
            ('EURUSD','late_exploration','first_crossing_cooldown'):0.220163,
            ('GBPUSD','early_exploration','scheduled_state'):0.636556,
            ('GBPUSD','late_exploration','scheduled_state'):0.678986,
            ('GBPUSD','early_exploration','first_crossing_cooldown'):0.397352,
            ('GBPUSD','late_exploration','first_crossing_cooldown'):0.341393,
        }
        reproduction=(events.groupby(['pair','era','signal_mode'],observed=True)[f'pnl_pips_h{PRIMARY_HORIZON_MIN}']
                      .mean().rename('current_mean_pips').reset_index())
        reproduction['reference_mean_pips']=[previous_reference.get(tuple(x),np.nan)
            for x in reproduction[['pair','era','signal_mode']].itertuples(index=False,name=None)]
        reproduction['abs_difference_pips']=(reproduction.current_mean_pips-reproduction.reference_mean_pips).abs()
        reproduction['within_tolerance']=reproduction.abs_difference_pips.le(REPRO_TOLERANCE_PIPS)
        display(reproduction.round(6))
        assert reproduction.loc[reproduction.reference_mean_pips.notna(),'within_tolerance'].all()
    """),
    md(r"""
        ## 3. Does RSI severity explain the clock difference?

        The common-support table retains only half-point RSI-depth bins represented by both clocks for the same pair, era, and
        direction. It weights each retained cell by the smaller of the two clock counts, preventing the dense crossing stream or
        long scheduled tail from dominating. The regression coefficient is scheduled minus first-crossing gross pips.
    """),
    code(r"""
        ycol=f'pnl_pips_h{PRIMARY_HORIZON_MIN}'
        clock_headline=[]
        for keys,g in events.groupby(['pair','era','signal_mode'],observed=True):
            for h in HORIZONS_MIN:
                col=f'pnl_pips_h{h}'; z=g.loc[g[col].notna()]
                clock_headline.append(dict(zip(['pair','era','signal_mode'],keys))|
                    {'horizon_min':h,'n':len(z),'mean_pips':z[col].mean(),
                     'cluster_t':session_cluster_t(z[col],z.sdate),
                     'rsi_depth_ic':spearmanr(z.rsi_depth,z[col]).statistic})
        clock_headline=pd.DataFrame(clock_headline)
        display(clock_headline.round(4))

        severity_summary=(events.groupby(['pair','era','signal_mode','direction'],observed=True)
            .agg(n=('rsi','size'),mean_rsi=('rsi','mean'),median_rsi=('rsi','median'),mean_depth=('rsi_depth','mean'),
                 depth_p50=('rsi_depth','median'),depth_p90=('rsi_depth',lambda x:x.quantile(.9)),
                 mean_pips=(ycol,'mean')).reset_index())
        display(severity_summary.round(3))

        events['depth_bin_half']=(np.floor(events.rsi_depth/RSI_DEPTH_BIN_WIDTH)*RSI_DEPTH_BIN_WIDTH).clip(upper=20)
        binned=(events.groupby(['pair','era','direction','depth_bin_half','signal_mode'],observed=True)
                .agg(n=(ycol,'count'),mean_pips=(ycol,'mean')).reset_index())
        display(binned.loc[binned.n>=MIN_MATCH_CELL_N].head(80).round(3))

        matched_rows=[]
        for keys,g in binned.groupby(['pair','era','direction','depth_bin_half'],observed=True):
            if len(g)!=2:continue
            rec={row.signal_mode:row for row in g.itertuples(index=False)}
            if any(rec[m].n<MIN_MATCH_CELL_N for m in SIGNAL_MODES):continue
            weight=min(rec[m].n for m in SIGNAL_MODES)
            matched_rows.append(dict(zip(['pair','era','direction','depth_bin_half'],keys))|
                {'weight':weight,'scheduled_mean':rec['scheduled_state'].mean_pips,
                 'crossing_mean':rec['first_crossing_cooldown'].mean_pips,
                 'scheduled_minus_crossing':rec['scheduled_state'].mean_pips-rec['first_crossing_cooldown'].mean_pips})
        matched_cells=pd.DataFrame(matched_rows)
        matched_clock_effect=(matched_cells.groupby(['pair','era'],observed=True)
            .apply(lambda g:pd.Series({'matched_cells':len(g),'matched_weight':g.weight.sum(),
                'rsi_standardized_scheduled_minus_crossing':np.average(g.scheduled_minus_crossing,weights=g.weight)}),
                   include_groups=False).reset_index())
        display(matched_clock_effect.round(4))
    """),
    code(r"""
        def clock_model_record(g,formula,label):
            cols=[ycol,'sdate','clock_scheduled','rsi_depth','direction','utc_hour','extreme_age_min',
                  'rsi_change_5_aligned','vei_pct','range_break_30m','rv_30m_bp','path_efficiency_30m']
            z=g[cols].replace([np.inf,-np.inf],np.nan).dropna()
            if len(z)<500 or z.sdate.nunique()<30:return {'model':label,'n':len(z)}
            try:
                fit=smf.ols(formula,data=z).fit(cov_type='cluster',cov_kwds={'groups':z.sdate})
                return {'model':label,'n':int(fit.nobs),'clock_coef_pips':fit.params.get('clock_scheduled',np.nan),
                        'clock_t':fit.tvalues.get('clock_scheduled',np.nan),'clock_p':fit.pvalues.get('clock_scheduled',np.nan),
                        'r2':fit.rsquared}
            except Exception as exc:return {'model':label,'n':len(z),'error':str(exc)[:100]}


        events['clock_scheduled']=events.signal_mode.eq('scheduled_state').astype('int8')
        clock_models=[]
        formulas={
            'raw_clock':f'{ycol} ~ clock_scheduled',
            'RSI_depth_adjusted':f'{ycol} ~ clock_scheduled + bs(rsi_depth,df=5) + C(direction) + C(utc_hour)',
            'depth_and_state_adjusted':(f'{ycol} ~ clock_scheduled + bs(rsi_depth,df=5) + C(direction) + C(utc_hour) + '
                'np.log1p(extreme_age_min) + rsi_change_5_aligned + vei_pct + range_break_30m + rv_30m_bp + path_efficiency_30m')
        }
        for keys,g in events.groupby(['pair','era'],observed=True):
            # Restrict to the intersection of the two clocks' 1st–99th percentile severity support.
            support=[]
            for mode in SIGNAL_MODES:
                x=g.loc[g.signal_mode==mode,'rsi_depth'].dropna(); support.append((x.quantile(.01),x.quantile(.99)))
            lo=max(x[0] for x in support); hi=min(x[1] for x in support); common=g.loc[g.rsi_depth.between(lo,hi)].copy()
            for label,formula in formulas.items():
                row=dict(zip(['pair','era'],keys))|{'support_low':lo,'support_high':hi}
                row.update(clock_model_record(common,formula,label)); clock_models.append(row)
        clock_model_table=pd.DataFrame(clock_models)
        display(clock_model_table.round(4))
    """),
    md(r"""
        ## 4. Broad RSI × feature interaction screen

        Features are standardized using early-era median and interquartile range for each pair and signal clock; those same
        transformations are applied to the late era. Every regression includes side and UTC-hour controls and clusters by New
        York trading session. Binary features remain 0/1. `interaction_beta` is in pips per one-IQR increase in both RSI depth
        and the feature. Results are exploratory even when BH-adjusted q-values are small.
    """),
    code(r"""
        binary_features=['range_break_15m','range_break_30m','range_break_60m','london_open','newyork_open','london_newyork_overlap']
        scalers={}
        for (pair,mode),g in events.loc[events.era=='early_exploration'].groupby(['pair','signal_mode'],observed=True):
            for col in ['rsi_depth']+feature_columns:
                x=g[col].replace([np.inf,-np.inf],np.nan).dropna(); med=x.median(); scale=x.quantile(.75)-x.quantile(.25)
                if col in binary_features: med=0.; scale=1.
                scalers[(pair,mode,col)]=(med,scale if np.isfinite(scale) and scale>0 else np.nan)

        def interaction_fit(g,feature,horizon):
            y=f'pnl_pips_h{horizon}'; pair=g.pair.iloc[0]; mode=g.signal_mode.iloc[0]
            dm,ds=scalers.get((pair,mode,'rsi_depth'),(np.nan,np.nan)); fm,fs=scalers.get((pair,mode,feature),(np.nan,np.nan))
            z=g[[y,'sdate','direction','utc_hour','rsi_depth',feature]].replace([np.inf,-np.inf],np.nan).dropna().copy()
            if len(z)<MIN_SCREEN_N or not np.isfinite(ds) or not np.isfinite(fs):return {'n':len(z)}
            z['depth_z']=((z.rsi_depth-dm)/ds).clip(-5,5); z['feature_z']=((z[feature]-fm)/fs).clip(-5,5)
            z['interaction']=z.depth_z*z.feature_z
            X=pd.DataFrame({'const':1.,'depth_z':z.depth_z,'feature_z':z.feature_z,'interaction':z.interaction,
                            'short':z.direction.eq('short').astype(float),
                            'utc_sin':np.sin(2*np.pi*z.utc_hour/24),'utc_cos':np.cos(2*np.pi*z.utc_hour/24)})
            try:
                fit=sm.OLS(z[y].to_numpy(),X).fit(cov_type='cluster',cov_kwds={'groups':z.sdate})
                rho=spearmanr(z[feature],z[y],nan_policy='omit').statistic
                return {'n':len(z),'sessions':z.sdate.nunique(),'feature_ic':rho,
                        'feature_beta':fit.params['feature_z'],'feature_t':fit.tvalues['feature_z'],'feature_p':fit.pvalues['feature_z'],
                        'depth_beta':fit.params['depth_z'],'depth_t':fit.tvalues['depth_z'],
                        'interaction_beta':fit.params['interaction'],'interaction_t':fit.tvalues['interaction'],
                        'interaction_p':fit.pvalues['interaction'],'r2':fit.rsquared}
            except Exception as exc:return {'n':len(z),'error':str(exc)[:100]}

        screen=[]
        for keys,g in events.groupby(['pair','era','signal_mode'],observed=True):
            for horizon in HORIZONS_MIN:
                for feature in feature_columns:
                    row=dict(zip(['pair','era','signal_mode'],keys))|{'horizon_min':horizon,'feature':feature,
                                                                     'family':next(k for k,v in FEATURE_GROUPS.items() if feature in v)}
                    row.update(interaction_fit(g,feature,horizon)); screen.append(row)
        interaction_screen=pd.DataFrame(screen)
        interaction_screen['interaction_q']=np.nan; interaction_screen['feature_q']=np.nan
        for _,idx in interaction_screen.groupby(['pair','era','signal_mode','horizon_min'],observed=True).groups.items():
            interaction_screen.loc[idx,'interaction_q']=bh_adjust(interaction_screen.loc[idx,'interaction_p'])
            interaction_screen.loc[idx,'feature_q']=bh_adjust(interaction_screen.loc[idx,'feature_p'])
        display(interaction_screen.sort_values(['interaction_q','interaction_p']).head(80).round(4))
    """),
    md(r"""
        ## 5. Conditional RSI IC and payoff surfaces

        Early-era feature cutpoints define quintiles and are reused unchanged in the late era. Therefore a late-era Q5 means
        “above the early 80th-percentile boundary,” not the top 20% of the late sample. Within each bin the notebook reports mean
        signed P&L and Spearman IC between RSI depth and P&L. `IC boost Q5−Q1` directly tests observations such as “high VEI
        strengthens RSI IC.” Binary features use 0/1 bins.
    """),
    code(r"""
        cutpoints={}
        for (pair,mode),g in events.loc[events.era=='early_exploration'].groupby(['pair','signal_mode'],observed=True):
            for feature in feature_columns:
                x=g[feature].replace([np.inf,-np.inf],np.nan).dropna()
                if feature in binary_features: cuts=np.array([.5])
                else: cuts=np.unique(x.quantile([.2,.4,.6,.8]).to_numpy())
                cutpoints[(pair,mode,feature)]=cuts

        surface=[]
        for keys,g in events.groupby(['pair','era','signal_mode'],observed=True):
            pair,era,mode=keys
            for horizon in HORIZONS_MIN:
                y=f'pnl_pips_h{horizon}'
                for feature in feature_columns:
                    cuts=cutpoints[(pair,mode,feature)]; vals=g[feature].to_numpy(float)
                    bins=np.digitize(vals,cuts,right=True); valid=np.isfinite(vals)&g[y].notna().to_numpy()
                    for b in np.unique(bins[valid]):
                        z=g.loc[valid&(bins==b),[y,'rsi_depth','sdate']].dropna()
                        if len(z)<MIN_MATCH_CELL_N:continue
                        rho=spearmanr(z.rsi_depth,z[y]).statistic if z.rsi_depth.nunique()>2 else np.nan
                        surface.append({'pair':pair,'era':era,'signal_mode':mode,'horizon_min':horizon,'feature':feature,
                                        'feature_bin':int(b+1),'n':len(z),'mean_pips':z[y].mean(),
                                        'cluster_t':session_cluster_t(z[y],z.sdate),'rsi_depth_ic':rho})
        conditional_surface=pd.DataFrame(surface)

        boost=[]
        for keys,g in conditional_surface.groupby(['pair','era','signal_mode','horizon_min','feature'],observed=True):
            lo=g.loc[g.feature_bin==g.feature_bin.min()].iloc[0]; hi=g.loc[g.feature_bin==g.feature_bin.max()].iloc[0]
            boost.append(dict(zip(['pair','era','signal_mode','horizon_min','feature'],keys))|
                         {'low_bin':lo.feature_bin,'high_bin':hi.feature_bin,'low_n':lo.n,'high_n':hi.n,
                          'edge_boost_high_minus_low':hi.mean_pips-lo.mean_pips,
                          'ic_boost_high_minus_low':hi.rsi_depth_ic-lo.rsi_depth_ic,
                          'low_mean_pips':lo.mean_pips,'high_mean_pips':hi.mean_pips,
                          'low_depth_ic':lo.rsi_depth_ic,'high_depth_ic':hi.rsi_depth_ic})
        conditional_boost=pd.DataFrame(boost)
        display(conditional_boost.sort_values('ic_boost_high_minus_low',ascending=False).head(80).round(4))
    """),
    md(r"""
        ## 6. Cross-pair and early/late stability ranking

        A useful interaction should not merely win one cell. The ranking below counts the sign of its standardized interaction
        coefficient across EURUSD/GBPUSD and early/late eras for each clock and horizon. Four-of-four sign agreement is a
        descriptive stability requirement, not independent replication because both pairs share USD and the eras were inspected.
    """),
    code(r"""
        stability=[]
        for keys,g in interaction_screen.groupby(['signal_mode','horizon_min','feature','family'],observed=True):
            z=g.dropna(subset=['interaction_beta'])
            signs=np.sign(z.interaction_beta)
            stability.append(dict(zip(['signal_mode','horizon_min','feature','family'],keys))|
                {'cells':len(z),'positive_cells':int((signs>0).sum()),'negative_cells':int((signs<0).sum()),
                 'median_interaction_beta':z.interaction_beta.median(),'median_abs_interaction_t':z.interaction_t.abs().median(),
                 'max_interaction_q':z.interaction_q.max(),'min_interaction_q':z.interaction_q.min()})
        stability_table=pd.DataFrame(stability)
        stability_table['same_sign_all_four']=(stability_table.cells.eq(4)&
            ((stability_table.positive_cells.eq(4))|(stability_table.negative_cells.eq(4))))
        display(stability_table.sort_values(['same_sign_all_four','median_abs_interaction_t'],ascending=[False,False]).head(100).round(4))

        primary_stability=stability_table.loc[stability_table.horizon_min==PRIMARY_HORIZON_MIN].copy()
        fig,axes=plt.subplots(1,2,figsize=(15,8),sharey=False)
        for ax,mode in zip(axes,SIGNAL_MODES):
            p=primary_stability.loc[primary_stability.signal_mode==mode].sort_values('median_abs_interaction_t').tail(20)
            colors=np.where(p.same_sign_all_four,'#2471a3','#aab7b8')
            ax.barh(p.feature,p.median_interaction_beta,color=colors); ax.axvline(0,color='black',lw=1)
            ax.set_title(f'{mode}: median standardized interaction'); ax.set_xlabel('pips per IQR × IQR')
        plt.tight_layout(); plt.show()
    """),
    code(r"""
        for feature in [f for f in PRIMARY_FEATURES_TO_PLOT if f in feature_columns]:
            p=conditional_surface.loc[(conditional_surface.feature==feature)&
                                      (conditional_surface.horizon_min==PRIMARY_HORIZON_MIN)]
            if p.empty:continue
            grid=p.pivot_table(index=['pair','era','signal_mode'],columns='feature_bin',values=['mean_pips','rsi_depth_ic'])
            print(f'\n{feature}: early-cutpoint conditional surface'); display(grid.round(4))
    """),
    md(r"""
        ## 7. Interpretation guardrails

        - If the clock coefficient collapses after RSI-depth adjustment, the apparent clock advantage was mainly severity
          selection. If it remains after depth but collapses after extreme-age/path controls, it reflects episode maturity rather
          than the arbitrary fixed clock itself.
        - A feature “boosts RSI IC” only when conditional RSI-depth IC and the regression interaction move together. A high-bin
          payoff increase with a near-zero interaction is a feature main effect, often just a larger volatility scale.
        - Full-era binning is avoided, but early cutpoints and the feature list are still exploratory choices. Favor sign stability
          across both pairs and both eras over the single best q-value.
        - `range_break_30m` is binary and mechanically related to impulse direction. Do not count an identical impulse-plus-break
          row as independent evidence.
        - No net strategy claim is allowed without executable bid/ask costs, delayed entry, position overlap, and tail-risk tests.
    """),
    code(r"""
        research_tables={'quality_report':quality_report,'coverage_report':coverage_report,'reproduction':reproduction,
                         'clock_headline':clock_headline,
                         'severity_summary':severity_summary,'matched_cells':matched_cells,
                         'matched_clock_effect':matched_clock_effect,'clock_model_table':clock_model_table,
                         'interaction_screen':interaction_screen,'conditional_surface':conditional_surface,
                         'conditional_boost':conditional_boost,'stability_table':stability_table}
        assert events.ts_utc.max()<HOLDOUT_START and not events.ts_utc.ge(HOLDOUT_START).any()
        print(f'Complete: {len(events):,} event rows; {len(feature_columns)} features; max timestamp={events.ts_utc.max()}')
        print('No 2024+ row was retained. Tables are available in `research_tables`.')
    """),
])

notebook={"cells":cells,"metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
          "language_info":{"name":"python","version":"3.11"}},"nbformat":4,"nbformat_minor":5}
OUT.write_text(json.dumps(notebook,ensure_ascii=False,indent=1),encoding='utf-8')
print(f'Wrote {OUT} with {len(cells)} cells')
