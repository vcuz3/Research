"""EXP-0002: stability & transfer of the run-persistence reversion signal.
(1) era stability by calendar year, (2) cross-pair transfer AUDUSD/NZDUSD,
(3) within-window time-of-day (by NY wall-clock hour).
Metric per cell: mean folded 15m reversion (pip) + causal joint horse-race
(count vs causal-vol-normalised displacement), session-day cluster-robust t.
Run from project root: python run_stability.py"""
import pandas as pd, numpy as np
rng=np.random.default_rng(11)
DATA='../data/clean/{}_1m_clean.parquet'
def load(sym):
    d=pd.read_parquet(DATA.format(sym)); d['ts_utc']=pd.to_datetime(d['ts_utc'])
    return d.drop_duplicates('ts_utc').set_index('ts_utc').sort_index().tz_localize('UTC')
def win(idx):
    ber=idx.tz_convert('Europe/Berlin'); ny=idx.tz_convert('America/New_York')
    return np.asarray(((ber.hour+ber.minute/60)>=8.0)&((ny.hour+ny.minute/60)<12.0)&(idx.weekday<5))
def cl_ols(X,y,g):
    XtXi=np.linalg.inv(X.T@X); beta=XtXi@(X.T@y); res=y-X@beta
    order=np.argsort(g,kind='stable'); Xs=X[order];rs=res[order];gs=g[order]
    idx=np.unique(gs,return_index=True)[1]; meat=np.zeros((X.shape[1],)*2)
    for s in np.split(np.arange(len(gs)),idx[1:]):
        u=(Xs[s]*rs[s][:,None]).sum(0); meat+=np.outer(u,u)
    G=len(idx); V=XtXi@meat@XtXi*(G/(G-1)); return beta,beta/np.sqrt(np.diag(V)),G
def vstreak(sgn):
    n=len(sgn); idx=np.arange(n); same=np.zeros(n,bool); same[1:]=(sgn[1:]==sgn[:-1])&(sgn[1:]!=0)
    ls=np.maximum.accumulate(np.where(~same,idx,-1)); st=idx-ls+1; st[sgn==0]=0; return st

def build(sym):
    d=load(sym)
    r=pd.DataFrame({'close':d['close'].resample('5min').last(),'open':d['open'].resample('5min').first()}).dropna()
    lc=np.log(r['close'].values); n=len(lc); ret=np.diff(lc,prepend=np.nan); ar=np.abs(ret)
    ar0=np.where(np.isnan(ar),0.0,ar)
    v=np.sqrt(pd.Series(ar**2).rolling(78,min_periods=52).mean().shift(1).values)
    lbl=r.index; inwin=win(pd.DatetimeIndex(lbl+pd.Timedelta(minutes=5)))
    ny=lbl.tz_convert('America/New_York'); sess=ny.normalize().asi8
    valid=~np.isnan(ret); s0=np.sign(ret); s0[~valid]=0
    rr=s0*ar0; C=np.cumsum(rr); st=vstreak(s0)
    start=np.arange(n)-(st-1); sc=start-1; sc[sc<0]=0; disp=C-C[sc]
    fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
    dsig=disp/v; scnt=s0*st
    base=inwin&(st>=1)&~np.isnan(v)&~np.isnan(fwd)
    return dict(n=n,fwd=fwd,dsig=dsig,scnt=scnt,sgn=s0,sess=sess,base=base,
                year=ny.year.values,hour=ny.hour.values,ar0=ar0,valid=valid,v=v,C=C,st=st,
                inwin=inwin,lbl=lbl)

def cell(P,mask):
    m=P['base']&mask
    if m.sum()<500: return None
    fold=(-P['sgn'][m]*P['fwd'][m]*1e4)
    y=P['fwd'][m]*1e4; X=np.column_stack([np.ones(m.sum()),P['dsig'][m],P['scnt'][m]])
    b,t,G=cl_ols(X,y,P['sess'][m])
    return dict(n=int(m.sum()),G=G,mf=fold.mean(),bc=b[2],tc=t[2],bd=b[1],td=t[1])

def signflip_fold_count(P,ND=200):
    # null on the whole in-window sample, matches EXP-0001
    n=P['n']; ar0=P['ar0']; valid=P['valid']; v=P['v']; inwin=P['inwin']
    def stat(sgn):
        rr=sgn*ar0; C=np.cumsum(rr); st=vstreak(sgn)
        start=np.arange(n)-(st-1); sc=start-1; sc[sc<0]=0; disp=C-C[sc]
        fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
        dsig=disp/v; scnt=sgn*st
        m=inwin&(st>=1)&~np.isnan(v)&~np.isnan(fwd)
        fold=(-sgn[m]*fwd[m]*1e4).mean()
        y=fwd[m]*1e4; X=np.column_stack([np.ones(m.sum()),dsig[m],scnt[m]])
        XtXi=np.linalg.inv(X.T@X); bb=XtXi@(X.T@y); res=y-X@bb
        s2=(res@res)/(len(y)-3); tc=bb[2]/np.sqrt(np.diag(XtXi)[2]*s2)
        return fold,tc
    mf=np.empty(ND); tc=np.empty(ND)
    for b in range(ND):
        sn=np.zeros(n); sn[valid]=rng.choice([-1.0,1.0],valid.sum()); mf[b],tc[b]=stat(sn)
    s0=P['sgn']; mfr,tcr=stat(s0)
    p_mf=(np.sum(mf>=mfr)+1)/(ND+1); p_tc=(np.sum(tc<=tcr)+1)/(ND+1)
    return mfr,mf.mean(),mf.std(),p_mf,tcr,tc.mean(),tc.std(),p_tc

print('='*78)
print('(1) ERA STABILITY BY YEAR  +  (3) TIME-OF-DAY (NY hour)  — EURUSD, GBPUSD')
print('='*78)
for sym in ['EURUSD','GBPUSD']:
    P=build(sym)
    print(f'\n-- {sym} : by year (mean fold pip / count b,t / n,sessions) --')
    for yr in range(2011,2027):
        c=cell(P,P['year']==yr)
        if c: print(f'  {yr}: fold={c["mf"]:+.3f}  count b={c["bc"]:+.3f} t={c["tc"]:+.1f}  n={c["n"]:6d} G={c["G"]}')
    npos=sum(1 for yr in range(2011,2027) if (c:=cell(P,P['year']==yr)) and c['mf']>0)
    nyr =sum(1 for yr in range(2011,2027) if cell(P,P['year']==yr))
    print(f'  -> fold>0 in {npos}/{nyr} years')
    print(f'-- {sym} : by NY wall-clock hour --')
    for h in range(0,13):
        c=cell(P,P['hour']==h)
        if c: print(f'  NY {h:02d}h: fold={c["mf"]:+.3f}  count b={c["bc"]:+.3f} t={c["tc"]:+.1f}  n={c["n"]:6d}')

print('\n'+'='*78)
print('(2) CROSS-PAIR TRANSFER — AUDUSD, NZDUSD (full pipeline incl. signflip null)')
print('='*78)
for sym in ['AUDUSD','NZDUSD']:
    P=build(sym)
    c=cell(P,np.ones(P['n'],bool))
    mfr,mfn,mfs,pmf,tcr,tcn,tcs,ptc=signflip_fold_count(P)
    print(f'\n== {sym} == n={c["n"]} G={c["G"]}')
    print(f'   JOINT: count b={c["bc"]:+.4f}(t={c["tc"]:+.1f})  disp b={c["bd"]:+.4f}(t={c["td"]:+.1f})  meanfold={c["mf"]:+.3f}pip')
    print(f'   signflip null 200: meanfold real={mfr:+.3f} null={mfn:+.3f}+-{mfs:.3f} p={pmf:.4f}'
          f' | count_t real={tcr:+.1f} null={tcn:+.2f}+-{tcs:.2f} p={ptc:.4f}')
    # by-year for transfer pairs too (sign stability)
    npos=sum(1 for yr in range(2011,2027) if (cc:=cell(P,P['year']==yr)) and cc['mf']>0)
    nyr =sum(1 for yr in range(2011,2027) if cell(P,P['year']==yr))
    print(f'   fold>0 in {npos}/{nyr} years')
