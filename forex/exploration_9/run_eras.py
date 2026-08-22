"""EXP-0003: which reversion signal is significant in FULL vs RECENT era, per pair.
For each pair x era in {FULL 2011-2026, RECENT 2020-2026}:
  - unconditional fold (fade the run, unweighted): mean pip + session-cluster t
    + signflip null p (200 draws, shared across eras within a pair)
  - joint horse race count vs causal-vol-normalised displacement (cluster t)
Run from project root: python run_eras.py"""
import pandas as pd, numpy as np
rng=np.random.default_rng(13)
DATA='../data/clean/{}_1m_clean.parquet'
def load(sym):
    d=pd.read_parquet(DATA.format(sym)); d['ts_utc']=pd.to_datetime(d['ts_utc'])
    return d.drop_duplicates('ts_utc').set_index('ts_utc').sort_index().tz_localize('UTC')
def win(idx):
    ber=idx.tz_convert('Europe/Berlin'); ny=idx.tz_convert('America/New_York')
    return np.asarray(((ber.hour+ber.minute/60)>=8.0)&((ny.hour+ny.minute/60)<12.0)&(idx.weekday<5))
def cl_t(X,y,g):
    XtXi=np.linalg.inv(X.T@X); beta=XtXi@(X.T@y); res=y-X@beta
    order=np.argsort(g,kind='stable'); Xs=X[order];rs=res[order];gs=g[order]
    idx=np.unique(gs,return_index=True)[1]; meat=np.zeros((X.shape[1],)*2)
    for s in np.split(np.arange(len(gs)),idx[1:]):
        u=(Xs[s]*rs[s][:,None]).sum(0); meat+=np.outer(u,u)
    G=len(idx); V=XtXi@meat@XtXi*(G/(G-1)); return beta,beta/np.sqrt(np.diag(V)),G
def vstreak(sgn):
    n=len(sgn); idx=np.arange(n); same=np.zeros(n,bool); same[1:]=(sgn[1:]==sgn[:-1])&(sgn[1:]!=0)
    ls=np.maximum.accumulate(np.where(~same,idx,-1)); st=idx-ls+1; st[sgn==0]=0; return st

ERAS={'FULL':(2011,2026),'RECENT':(2020,2026)}
for sym in ['EURUSD','GBPUSD','AUDUSD','NZDUSD']:
    d=load(sym)
    r=pd.DataFrame({'close':d['close'].resample('5min').last(),'open':d['open'].resample('5min').first()}).dropna()
    lc=np.log(r['close'].values); n=len(lc); ret=np.diff(lc,prepend=np.nan); ar=np.abs(ret)
    ar0=np.where(np.isnan(ar),0.0,ar)
    v=np.sqrt(pd.Series(ar**2).rolling(78,min_periods=52).mean().shift(1).values)
    lbl=r.index; inwin=win(pd.DatetimeIndex(lbl+pd.Timedelta(minutes=5)))
    ny=lbl.tz_convert('America/New_York'); sess=ny.normalize().asi8; year=ny.year.values
    valid=~np.isnan(ret); s0=np.sign(ret); s0[~valid]=0
    emask={k:(year>=a)&(year<=b) for k,(a,b) in ERAS.items()}
    def foldmean(sgn,era):  # unconditional fold in an era, real |ret| fixed by caller via ar0
        rr=sgn*ar0; C=np.cumsum(rr); st=vstreak(sgn)
        fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
        m=inwin&(st>=1)&~np.isnan(v)&~np.isnan(fwd)&emask[era]
        return (-sgn[m]*fwd[m]*1e4).mean()
    # real stats
    rr=s0*ar0; C=np.cumsum(rr); st=vstreak(s0)
    start=np.arange(n)-(st-1); sc=start-1; sc[sc<0]=0; disp=C-C[sc]
    fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
    dsig=disp/v; scnt=s0*st
    print(f'\n== {sym} ==')
    # signflip null shared across eras
    ND=200; nullf={k:np.empty(ND) for k in ERAS}
    for b in range(ND):
        sn=np.zeros(n); sn[valid]=rng.choice([-1.0,1.0],valid.sum())
        for k in ERAS: nullf[k][b]=foldmean(sn,k)
    for k in ERAS:
        m=inwin&(st>=1)&~np.isnan(v)&~np.isnan(fwd)&emask[k]
        fold=(-s0[m]*fwd[m]*1e4)
        _,tu,G=cl_t(np.ones((m.sum(),1)),s0[m]*0+fold,sess[m])  # t of mean, clustered
        # (regress fold on constant => beta=mean, cl-robust t)
        y=fwd[m]*1e4; X=np.column_stack([np.ones(m.sum()),dsig[m],scnt[m]])
        b_,t_,_=cl_t(X,y,sess[m])
        real=fold.mean(); nu=nullf[k]; p=(np.sum(nu>=real)+1)/(ND+1)
        yr0,yr1=ERAS[k]
        print(f'  {k:6s} {yr0}-{yr1}: fold={real:+.3f}pip cl-t={tu[0]:+.1f}  signflip null={nu.mean():+.3f}+-{nu.std():.3f} p={p:.4f}'
              f'   | joint: count t={t_[2]:+.1f} disp t={t_[1]:+.1f}  n={m.sum():6d} G={G}')
