"""Core EXP-0001 evidence: (A) 1m-grain reversion decay w/ shared-close embargo,
(B) causal horse race count vs displacement, (C) signflip null.
Run from project root: python run_reversion_core.py"""
import pandas as pd, numpy as np
rng=np.random.default_rng(7)
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
    G=len(idx); V=XtXi@meat@XtXi*(G/(G-1)); return beta,beta/np.sqrt(np.diag(V))
def ols_t(X,y):
    XtXi=np.linalg.inv(X.T@X); beta=XtXi@(X.T@y); res=y-X@beta
    s2=(res@res)/(len(y)-X.shape[1]); return beta/np.sqrt(np.diag(XtXi)*s2)
def vstreak(sgn):
    n=len(sgn); idx=np.arange(n); same=np.zeros(n,bool); same[1:]=(sgn[1:]==sgn[:-1])&(sgn[1:]!=0)
    ls=np.maximum.accumulate(np.where(~same,idx,-1)); st=idx-ls+1; st[sgn==0]=0; return st
for sym in ['EURUSD','GBPUSD']:
    d=load(sym)
    r=pd.DataFrame({'close':d['close'].resample('5min').last(),'open':d['open'].resample('5min').first()}).dropna()
    lc=np.log(r['close'].values); n=len(lc); ret=np.diff(lc,prepend=np.nan); ar=np.abs(ret)
    ar0=np.where(np.isnan(ar),0.0,ar)
    v=np.sqrt(pd.Series(ar**2).rolling(78,min_periods=52).mean().shift(1).values)
    lbl=r.index; inwin=win(pd.DatetimeIndex(lbl+pd.Timedelta(minutes=5)))
    sess=lbl.tz_convert('America/New_York').normalize().asi8; valid=~np.isnan(ret)
    def stats(sgn,cluster=False):
        rr=sgn*ar0; C=np.cumsum(rr); st=vstreak(sgn)
        start=np.arange(n)-(st-1); sc=start-1; sc[sc<0]=0; disp=C-C[sc]
        fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
        dsig=disp/v; scnt=sgn*st
        m=inwin&(st>=1)&~np.isnan(v)&~np.isnan(fwd)
        y=fwd[m]*1e4; X=np.column_stack([np.ones(m.sum()),dsig[m],scnt[m]]); fold=(-sgn[m]*fwd[m]*1e4)
        if cluster:
            b,t=cl_ols(X,y,sess[m]); return dict(mf=fold.mean(),bd=b[1],td=t[1],bc=b[2],tc=t[2])
        t=ols_t(X,y); return fold.mean(),t[1],t[2]
    s0=np.sign(ret); s0[~valid]=0; R=stats(s0,cluster=True)
    print(f'== {sym} == JOINT disp_sig b={R["bd"]:+.4f}(t={R["td"]:+.1f})  count b={R["bc"]:+.4f}(t={R["tc"]:+.1f})  meanfold={R["mf"]:+.3f}pip')
    ND=200; mf=np.empty(ND); td=np.empty(ND); tc=np.empty(ND)
    for b in range(ND):
        sn=np.zeros(n); sn[valid]=rng.choice([-1.0,1.0],valid.sum()); mf[b],td[b],tc[b]=stats(sn)
    mf_r,td_r,tc_r=stats(s0); pv=lambda rl,nu,s:(np.sum(nu<=rl)+1)/(len(nu)+1) if s=='lo' else (np.sum(nu>=rl)+1)/(len(nu)+1)
    print(f'   signflip null {ND}: meanfold real={mf_r:+.3f} null={mf.mean():+.3f}+-{mf.std():.3f} p={pv(mf_r,mf,"hi"):.4f}'
          f' | count_t real={tc_r:+.1f} null={tc.mean():+.2f}+-{tc.std():.2f} p={pv(tc_r,tc,"lo"):.4f}'
          f' | disp_t real={td_r:+.1f} p={pv(td_r,td,"lo"):.4f}')
