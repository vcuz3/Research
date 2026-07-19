# EXP-0015 Feature-Profit Diagnostic Screen

Status: exploratory screen only; no engine filter or Null-C validation.

Baseline sample: continuous-stop NQ trades from the existing WFO dataset, scored in net ATR R. RVOL is breakout/signal-minute volume divided by the strictly prior 90-session same-mfo average.

## Baseline

```csv
n,days,sumR,meanR,medianR,hit,trade_t,daily_sharpe,p90R,tail_share
4209,2050,91.196993,0.021667,-0.046485,0.261582,4.779107,1.717500,0.342289,3.297469
```

## Correlations

```csv
feature,description,n,pearson,spearman
ext_atr,"signal close extension beyond band, ATR units",4209,0.026592,-0.232274
vwap_dist_atr,"signal close distance beyond VWAP, ATR units",4209,0.012195,-0.124262
log_rvol_90,log1p(RVOL),4209,0.049684,-0.106808
rvol_90,breakout-minute RVOL vs prior 90 same-mfo bars,4209,0.049952,-0.106808
band_width_bps,"noise band width, bps",4209,0.001816,0.072692
aligned_gap,side * overnight/RTH gap,4209,0.015357,0.070012
sess_move,side-aligned session move at signal,4209,0.001906,-0.063642
abs_gap,absolute overnight/RTH gap,4209,0.015900,0.048081
atr_pts,"prior-14-session RTH ATR, points",4209,-0.008215,0.047753
ord_in_day,trade ordinal within session,4209,-0.024007,0.024935
```

## Strongest Single-Feature Bins By Mean R

```csv
feature,bin,n,sumR,meanR,hit,trade_t,daily_sharpe
rvol_90,"(1.701, 14.534]",842,45.273179,0.053769,0.301663,3.593067,2.233460
log_rvol_90,"(0.993, 2.743]",842,45.273179,0.053769,0.301663,3.593067,2.233460
ord_in_day,"(2.0, 3.0]",610,26.362876,0.043218,0.272131,3.499151,2.249044
ext_atr,"(0.207, 1.659]",842,35.026913,0.041600,0.368171,2.744453,1.750539
ext_atr,"(0.115, 0.207]",842,33.448174,0.039725,0.327791,3.528558,2.093401
band_width_bps,"(145.533, 196.989]",842,32.565791,0.038677,0.282660,3.649968,2.458543
abs_gap,"(0.00447, 0.00797]",844,29.831054,0.035345,0.276066,3.448626,2.831760
atr_pts,"(68.75, 180.236]",837,28.853002,0.034472,0.264038,3.212325,2.619369
aligned_gap,"(0.00718, 0.0687]",842,28.935517,0.034365,0.292162,3.443935,2.869302
sess_move,"(0.00465, 0.00599]",842,28.276007,0.033582,0.256532,3.112376,1.938778
```

## Weakest Single-Feature Bins By Mean R

```csv
feature,bin,n,sumR,meanR,hit,trade_t,daily_sharpe
ord_in_day,"(3.0, 8.0]",387,-2.391713,-0.006180,0.266150,-0.667240,-0.666757
ext_atr,"(0.0284, 0.0637]",842,5.282540,0.006274,0.173397,0.793256,0.482501
ext_atr,"(-0.0009524000000000001, 0.0284]",842,5.347494,0.006351,0.185273,1.165189,0.713238
rvol_90,"(0.635, 0.898]",842,5.557628,0.006601,0.243468,0.908354,0.556508
log_rvol_90,"(0.492, 0.641]",842,5.557628,0.006601,0.243468,0.908354,0.556508
atr_pts,"(39.982, 68.75]",844,7.477810,0.008860,0.250000,0.936701,0.727810
aligned_gap,"(-0.00138, 0.000958]",841,7.797993,0.009272,0.219976,0.862181,0.671101
abs_gap,"(-0.001, 0.00113]",842,7.970686,0.009466,0.220903,0.917929,0.717569
log_rvol_90,"(0.0167, 0.492]",842,8.287117,0.009842,0.243468,1.344847,0.877356
rvol_90,"(0.0169, 0.635]",842,8.287117,0.009842,0.243468,1.344847,0.877356
```

## Aligned Gap x RVOL Tercile Grid

```csv
gap_bin,rvol_bin,n,sumR,meanR,hit,trade_t,daily_sharpe
gap_against,rvol_high,532,14.604105,0.027451,0.255639,1.490878,1.221367
gap_against,rvol_low,419,-1.129481,-0.002696,0.198091,-0.260460,-0.244081
gap_against,rvol_mid,453,-0.017958,-0.000040,0.216336,-0.003051,-0.002609
gap_mid,rvol_high,420,14.801044,0.035241,0.295238,2.196978,1.938983
gap_mid,rvol_low,517,0.531559,0.001028,0.245648,0.114752,0.097917
gap_mid,rvol_mid,465,15.741953,0.033854,0.298925,2.614663,2.181884
gap_with,rvol_high,451,18.978246,0.042080,0.297118,2.560164,2.328390
gap_with,rvol_low,467,12.290124,0.026317,0.297645,2.904198,2.716786
gap_with,rvol_mid,485,15.397401,0.031747,0.249485,2.485630,2.144042
```
