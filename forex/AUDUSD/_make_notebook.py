"""Generate baseline_model.ipynb without nbformat (plain JSON schema v4)."""
import json

cells = []
def md(s):  cells.append({"cell_type":"markdown","metadata":{},"source":s.splitlines(keepends=True)})
def code(s):cells.append({"cell_type":"code","metadata":{},"execution_count":None,"outputs":[],
                          "source":s.splitlines(keepends=True)})

md("""# AUDUSD Baseline Predictive Model — Step 2

**Goal:** test whether the available macro / cross-asset / technical features contain any
*out-of-sample* predictive value for AUDUSD **before** adding any regime logic.

Thin, reproducible driver over three reusable modules:

| module | role |
|---|---|
| `baseline_features.py` | causal targets + technicals + NY-session labels |
| `walkforward.py` | expanding-window, embargoed, causal-standardized WF validation |
| `metrics.py` | overlap-aware regression / classification / trading metrics |

**Leakage safety:** expanding train window, an *embargo* of `horizon` bars between train and
test, scaler/imputer fit on train only, and honest significance on **non-overlapping** samples
(one every `horizon` bars). Horizons: 1h=4, 4h=16, 1d=96 bars.""")

code("""import pandas as pd, numpy as np, os
import matplotlib.pyplot as plt
import baseline_features as bf, walkforward as wf, metrics as mt
pd.set_option('display.width', 170); pd.set_option('display.max_columns', 40)
RES = 'results'""")

md("## 1. Load the feature/target panel\nBuilt once by `baseline_features.build_all()` and cached to parquet.")
code("""CACHE='data/_baseline_panel_cache.parquet'
if not os.path.exists(CACHE):
    df = bf.build_all(cost_buffer=bf.DEFAULT_ONE_WAY_COST)
    for tag in bf.HORIZONS_BARS: df[f'y_bin_{tag}']=(df[f'y_ret_{tag}']>0).astype('float32')
    df.to_parquet(CACHE)
df = pd.read_parquet(CACHE)
tech=[x for x in bf.INTRADAY_FEATURES if x in df.columns]; cond=bf.conditioning_features(df)
print('panel', df.shape, '| technical', len(tech), '| conditioning', len(cond))
df[['time','close','y_ret_h1h','y_ret_h1d']].tail(3)""")

code("""display(df['session_ny'].value_counts())
df.filter(regex=r'^y_ret_h').describe().T[['mean','std','count']]""")

md("""## 2. Walk-forward performance tables
Precomputed by `run_baseline.py` (re-run all from scratch: `!python run_baseline.py --rebuild`, ~4 min).""")

md("### 2a. Regression — rank IC by feature set × horizon\nNon-overlapping rank IC and its t-stat are the honest columns.")
code("""reg = pd.read_csv(f'{RES}/regression_metrics.csv')
reg[['horizon','feature_set','n_nonovlp','ic_pearson_nonovlp','rank_ic_nonovlp','ic_tstat_nonovlp','dir_acc_all']]""")
code("""fig,ax=plt.subplots(figsize=(7,3.2))
piv=reg.pivot(index='horizon',columns='feature_set',values='rank_ic_nonovlp').loc[['h1h','h4h','h1d']]
piv.plot.bar(ax=ax); ax.axhline(0,color='k',lw=.6)
ax.set_ylabel('non-overlap rank IC'); ax.set_title('Out-of-sample rank IC (higher=better)')
plt.tight_layout(); plt.show()""")
md("""**Read:** only the **technical** set shows a positive OOS IC (~0.01–0.02, t≈3.8 at 1h on
~77k non-overlap samples). The 38 macro/cross-asset **conditioning** features sit at ~0 and
*dilute* the signal when combined — "detectable but tiny".""")

md("### 2b. Confidence-bucket hit rate (combined Ridge, 1h)")
code("""cb = pd.read_csv(f'{RES}/conf_buckets_h1h.csv'); display(cb)
ax=cb.plot(x='bucket',y='dir_hit_rate',marker='o',legend=False,figsize=(6,3))
ax.axhline(0.5,color='r',ls='--',lw=.8); ax.set_ylabel('directional hit rate')
ax.set_title('Hit rate by predicted-magnitude quantile (1h)'); plt.tight_layout(); plt.show()""")
md("**Read:** flat ~0.50 across buckets — highest-confidence bucket is *no* better. No usable conviction.")

md("### 2c. Coefficient magnitudes (standardized, combined Ridge, 1h)")
code("""co = pd.read_csv(f'{RES}/coefficients_h1h.csv').rename(columns={'Unnamed: 0':'feature'}).head(12)
ax=co[::-1].plot.barh(x='feature',y='coef',legend=False,figsize=(6,4))
ax.set_title('Top |coef| — 1h Ridge (standardized)'); plt.tight_layout(); plt.show()
co""")
md("""**Read:** largest weights are AU–US short-rate differential, US 2s10s, distance-from-MA,
realized vol/ATR — carry + mean-reversion/vol microstructure. Sensible signs, tiny magnitudes.""")

md("### 2d. Classification (logistic direction) + calibration")
code("""clf = pd.read_csv(f'{RES}/classification_metrics.csv')
display(clf[['horizon','base_rate','accuracy','precision','recall','f1','roc_auc']])
cal = pd.read_csv(f'{RES}/calibration_h1d.csv')
ax=cal.plot(x='mean_pred',y='emp_freq',marker='o',legend=False,figsize=(4.5,4.5))
ax.plot([0,1],[0,1],'r--',lw=.8); ax.set_xlabel('mean predicted P(up)'); ax.set_ylabel('empirical freq')
ax.set_title('Calibration (1d)'); plt.tight_layout(); plt.show()""")
md("**Read:** ROC AUC ≈ 0.51 at every horizon; calibration poor at the extremes. No directional edge.")

md("""### 2e. Trading rule — transaction-cost sweep (combined Ridge)
Non-overlapping threshold rule (long/short/flat), one position per horizon; cost on turnover.""")
code("""tr = pd.read_csv(f'{RES}/trading_metrics.csv')
tr[['horizon','one_way_cost','n_trades','win_rate','profit_factor','sharpe_gross','sharpe_net','cost_drag_frac','max_drawdown']]""")
md("""**Read:** *gross* Sharpe ≈0 (0.02 at 1h, 0.06 at 1d); 4h negative even gross. After a
realistic 0.5-pip one-way cost net Sharpe is ≤0 at 1h/4h; at 1h cost drag is **~13× gross PnL**.""")

md("### 2f. Benchmark — better than naive AUDUSD momentum?")
code("""pd.read_csv(f'{RES}/benchmark_metrics.csv')""")
md("""**Read:** naive momentum (sign of `ret_12b`) has *negative* IC/Sharpe here — AUDUSD 15-min is
mildly mean-reverting. The model clears that low bar but is itself unprofitable net of costs.""")

md("### 2g. Illustrative net equity curve (combined Ridge, 1d, 0.5-pip cost)")
code("""res = wf.walk_forward_predict(df, tech+cond, 'y_ret_h1d', horizon_bars=96, task='reg', model='ridge', alpha=10.0)
f = mt.nonoverlap(res, 96); sig=f['pred'].values; ret=f['y'].values
pos=np.where(sig>0.0015,1.0,np.where(sig<-0.0015,-1.0,0.0))
turn=np.abs(pos-np.concatenate([[0],pos[:-1]])); net=pos*ret-0.00005*turn
tstamp = pd.to_datetime(df.loc[f.index, 'time'].values)
pd.Series(np.cumsum(net), index=tstamp).plot(figsize=(8,3),
    title='Cumulative net return — combined Ridge, 1d, 0.5-pip cost')
plt.ylabel('cum log ret'); plt.tight_layout(); plt.show()
print('final cum net:', round(float(np.cumsum(net)[-1]),4))""")

md("""## 3. Research summary — see `BASELINE_FINDINGS.md`

- **Baseline predictive value:** none that is *tradable*. A statistically detectable but
  economically negligible linear signal exists at short horizons from **technical** features
  (rank IC ≈ 0.014, t ≈ 3.8 at 1h); it does **not** survive costs (net Sharpe ≤ 0).
- **Features that matter:** intraday technicals (carry differential, MA distance, vol/ATR);
  the macro/cross-asset **conditioning** block adds nothing intraday and dilutes signal.
- **Most promising horizon:** 1-day (largest, most stable IC; least cost-dominated) — still net-flat.
- **OOS stability:** weak/unstable — flat confidence buckets, AUC≈0.51, poor calibration.
- **Better than momentum?** Yes, but momentum is negative here — a low, unprofitable bar.
- **Proceed to regime modelling?** Only as research; judge regime models as *net-of-cost*
  improvements over this clean, leakage-safe benchmark.""")

nb = {"cells":cells,
      "metadata":{"kernelspec":{"display_name":"Python 3","language":"python","name":"python3"},
                  "language_info":{"name":"python","version":"3.14"}},
      "nbformat":4,"nbformat_minor":5}
json.dump(nb, open('baseline_model.ipynb','w',encoding='utf-8'), indent=1)
print('wrote baseline_model.ipynb with', len(cells), 'cells')
