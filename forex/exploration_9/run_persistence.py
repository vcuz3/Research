"""EXP-0001 exploration: is run-length reversion a 'grind vs lunge' shape effect?
Horse-races integer run count against continuous persistence features
(per-bar move, max-bar share) on EURUSD/GBPUSD, Frankfurt-open->NY-noon window.
Reversion target: folded 15m forward log-return, 5m grid, day-clustered t.
"""
import pandas as pd, numpy as np, sys

DATA='../data/clean/{}_1m_clean.parquet'
def load(sym):
    d=pd.read_parquet(DATA.format(sym)); d['ts_utc']=pd.to_datetime(d['ts_utc'])
    return d.drop_duplicates('ts_utc').set_index('ts_utc').sort_index().tz_localize('UTC')
def win(idx):
    ber=idx.tz_convert('Europe/Berlin'); ny=idx.tz_convert('America/New_York')
    return np.asarray(((ber.hour+ber.minute/60)>=8.0)&((ny.hour+ny.minute/60)<12.0)&(idx.weekday<5))
def vstreak(sgn):
    n=len(sgn); idx=np.arange(n); same=np.zeros(n,bool)
    same[1:]=(sgn[1:]==sgn[:-1])&(sgn[1:]!=0)
    ls=np.maximum.accumulate(np.where(~same,idx,-1)); st=idx-ls+1; st[sgn==0]=0; return st,ls
def cl_ols(X,y,g):
    ok=~np.isnan(y)&~np.isnan(X).any(1); X=X[ok];y=y[ok];g=np.asarray(g)[ok]
    XtXi=np.linalg.inv(X.T@X); beta=XtXi@(X.T@y); res=y-X@beta
    order=np.argsort(g,kind='stable'); Xs=X[order];rs=res[order];gs=g[order]
    idx=np.unique(gs,return_index=True)[1]; meat=np.zeros((X.shape[1],)*2)
    for s in np.split(np.arange(len(gs)),idx[1:]):
        u=(Xs[s]*rs[s][:,None]).sum(0); meat+=np.outer(u,u)
    G=len(idx); V=XtXi@meat@XtXi*(G/(G-1)); return beta,beta/np.sqrt(np.diag(V)),ok.sum()
def z(a): return (a-np.nanmean(a))/np.nanstd(a)

for sym in ['EURUSD','GBPUSD']:
    d=load(sym)
    r=pd.DataFrame({'close':d['close'].resample('5min').last(),'open':d['open'].resample('5min').first()}).dropna()
    lc=np.log(r['close'].values); n=len(lc); ret=np.diff(lc,prepend=np.nan); ar=np.abs(ret)
    v=np.sqrt(pd.Series(ar**2).rolling(78,min_periods=52).mean().shift(1).values)
    sgn=np.sign(ret); sgn[np.isnan(ret)]=0
    st,ls=vstreak(sgn); C=np.cumsum(np.where(np.isnan(ret),0.0,ret))
    start=np.arange(n)-(st-1); sc=start-1; sc[sc<0]=0
    disp=C-C[sc]                                   # signed run displacement
    seg=np.cumsum((st==1)|((sgn!=0)&(np.r_[True,sgn[1:]!=sgn[:-1]])))  # segment id
    maxbar=pd.Series(np.where(np.isnan(ar),0.0,ar)).groupby(seg).cummax().values
    fwd=np.full(n,np.nan); fwd[:n-3]=C[3:]-C[:n-3]
    adisp=np.abs(disp); dsig=adisp/v
    perbar=dsig/st                                 # mean per-bar move (sigma)
    maxshare=maxbar/np.where(adisp>0,adisp,np.nan) # in [1/k,1]; high=lunge
    lbl=r.index; sess=lbl.tz_convert('America/New_York').normalize().asi8
    m=win(pd.DatetimeIndex(lbl+pd.Timedelta(minutes=5)))&(st>=1)&~np.isnan(v)&~np.isnan(fwd)
    fold=(-sgn*fwd*1e4)[m]; K=st[m].astype(float); DS=dsig[m]; PB=perbar[m]; MS=maxshare[m]; S=sess[m]
    print(f'================ {sym}  n={m.sum()} ================')
    print('  corr: K~|dsig|=%.2f  K~perbar=%.2f  K~maxshare=%.2f  perbar~maxshare=%.2f'
          %(np.corrcoef(K,DS)[0,1],np.corrcoef(K,PB)[0,1],np.corrcoef(K,MS)[0,1],np.corrcoef(PB,MS)[0,1]))
    def run(name,cols):
        X=np.column_stack([np.ones(len(fold))]+[z(c) for c in cols]); b,t,_=cl_ols(X,fold,S)
        print(f'  {name:28s} '+'  '.join(f'{nm}={bb:+.3f}(t={tt:+.1f})' for nm,bb,tt in zip(['b0']+[c[0] for c in ncols],b,t) if nm!='b0'))
    for nm,c in [('|dsig|',DS),('count K',K),('perbar',PB),('maxshare',MS)]:
        ncols=[(nm,c)]; run('y ~ '+nm, [c])
    print('  --- joint ---')
    for label,ncols in [('y ~ |dsig|+K',[('|dsig|',DS),('K',K)]),
                        ('y ~ |dsig|+perbar',[('|dsig|',DS),('perbar',PB)]),
                        ('y ~ |dsig|+maxshare',[('|dsig|',DS),('maxshare',MS)]),
                        ('y ~ |dsig|+K+maxshare',[('|dsig|',DS),('K',K),('maxshare',MS)]),
                        ('y ~ |dsig|+K+perbar',[('|dsig|',DS),('K',K),('perbar',PB)])]:
        X=np.column_stack([np.ones(len(fold))]+[z(c) for _,c in ncols]); b,t,_=cl_ols(X,fold,S)
        print(f'  {label:26s} '+'  '.join(f'{nm}={bb:+.3f}(t={tt:+.1f})' for (nm,_),bb,tt in zip(ncols,b[1:],t[1:])))
    print('  folded reversion by maxshare quintile (pips):')
    mq=pd.qcut(MS,5,labels=False,duplicates='drop')
    for j in range(5):
        sel=mq==j; print(f'    MSq{j+1} share~{np.nanmedian(MS[sel]):.2f}  rev={np.nanmean(fold[sel]):+.3f}  n={sel.sum()}')
    print()
