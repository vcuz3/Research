# New York rollover blackout diagnostic

Blackout: 16:45--18:00 America/New_York (inclusive).

The baseline and blackout arms rerun the complete non-overlap event engine; the blackout is not applied after trades are formed.

## Signal counts

```text
 timeframe_minutes  lookback_bars  lookback_hours      arm  ready_bars  signals  signals_removed_by_blackout
                15            200            50.0 baseline      145297     1976                            0
                15            200            50.0 blackout      145297      824                         1152
                30            100            50.0 baseline       71554     1307                            0
                30            100            50.0 blackout       71554      536                          771
```

## Residual results

```text
 timeframe_minutes      arm  entry_delay_bars  horizon_minutes          model  trades  mean_bps  median_bps  hit_rate  day_cluster_t  daily_sharpe
                15 baseline                 1               30 residual_gross    1100    1.0671      0.7577    0.8045        11.3129        6.2594
                15 baseline                 1               30   residual_net    1100   -0.4329     -0.7423    0.3109        -4.5896       -2.5882
                15 baseline                 1               90 residual_gross     981    1.1311      0.9037    0.8063        10.0832        5.7740
                15 baseline                 1               90   residual_net     981   -0.3689     -0.5963    0.3191        -3.2884       -1.9036
                15 baseline                 1              360 residual_gross     780    1.6899      1.0109    0.8372         7.5867        4.6784
                15 baseline                 1              360   residual_net     780    0.1899     -0.4891    0.3705         0.8527        0.5274
                15 baseline                 2               30 residual_gross    1069    0.1742      0.0844    0.5762         3.3489        1.8977
                15 baseline                 2               30   residual_net    1069   -1.3258     -1.4156    0.0599       -25.4876      -13.2965
                15 baseline                 2               90 residual_gross     966    0.2777      0.0739    0.5870         3.9035        2.2683
                15 baseline                 2               90   residual_net     966   -1.2223     -1.4261    0.0580       -17.1791       -9.6199
                15 baseline                 2              360 residual_gross     763    0.6952      0.1032    0.6003         3.6909        2.2995
                15 baseline                 2              360   residual_net     763   -0.8048     -1.3968    0.0682        -4.2732       -2.6459
                15 blackout                 1               30 residual_gross     786    0.9954      0.5852    0.7672         7.9129        5.1514
                15 blackout                 1               30   residual_net     786   -0.5046     -0.9148    0.2990        -4.0109       -2.6495
                15 blackout                 1               90 residual_gross     701    0.9906      0.6193    0.7532         6.5848        4.4086
                15 blackout                 1               90   residual_net     701   -0.5094     -0.8807    0.3024        -3.3860       -2.2796
                15 blackout                 1              360 residual_gross     537    1.5504      0.6923    0.7691         5.6612        4.0899
                15 blackout                 1              360   residual_net     537    0.0504     -0.8077    0.3259         0.1841        0.1337
                15 blackout                 2               30 residual_gross     768    0.0674      0.0132    0.5221         0.9894        0.6549
                15 blackout                 2               30   residual_net     768   -1.4326     -1.4868    0.0286       -21.0199      -13.3568
                15 blackout                 2               90 residual_gross     688    0.1654      0.0226    0.5218         1.7191        1.1613
                15 blackout                 2               90   residual_net     688   -1.3346     -1.4774    0.0247       -13.8745       -9.2922
                15 blackout                 2              360 residual_gross     522    0.5757      0.0154    0.5115         2.4272        1.7756
                15 blackout                 2              360   residual_net     522   -0.9243     -1.4846    0.0249        -3.8967       -2.8592
                30 baseline                 1               30 residual_gross     617    1.2529      0.9241    0.8120         7.7474        5.4550
                30 baseline                 1               30   residual_net     617   -0.2471     -0.5759    0.3566        -1.5278       -1.0996
                30 baseline                 1               90 residual_gross     573    1.5630      1.0291    0.8185         8.3104        5.9743
                30 baseline                 1               90   residual_net     573    0.0630     -0.4709    0.3717         0.3348        0.2451
                30 baseline                 1              360 residual_gross     454    2.2793      1.1018    0.8458         5.9126        4.6127
                30 baseline                 1              360   residual_net     454    0.7793     -0.3982    0.4097         2.0215        1.5872
                30 baseline                 2               30 residual_gross     604    0.1670      0.0391    0.5414         1.8180        1.3087
                30 baseline                 2               30   residual_net     604   -1.3330     -1.4609    0.0315       -14.5105      -10.4278
                30 baseline                 2               90 residual_gross     563    0.4560      0.0201    0.5169         2.4003        1.7544
                30 baseline                 2               90   residual_net     563   -1.0440     -1.4799    0.0266        -5.4950       -4.0567
                30 baseline                 2              360 residual_gross     436    0.9817      0.0356    0.5390         2.7187        2.1757
                30 baseline                 2              360   residual_net     436   -0.5183     -1.4644    0.0298        -1.4356       -1.1470
                30 blackout                 1               30 residual_gross     530    1.2095      0.8323    0.7925         6.4840        4.8741
                30 blackout                 1               30   residual_net     530   -0.2905     -0.6677    0.3623        -1.5574       -1.1963
                30 blackout                 1               90 residual_gross     495    1.5427      0.9416    0.8020         7.1368        5.4561
                30 blackout                 1               90   residual_net     495    0.0427     -0.5584    0.3697         0.1978        0.1539
                30 blackout                 1              360 residual_gross     382    2.1244      1.0469    0.8168         5.7080        4.7720
                30 blackout                 1              360   residual_net     382    0.6244     -0.4531    0.4031         1.6778        1.4140
                30 blackout                 2               30 residual_gross     522    0.1850      0.0389    0.5402         1.7493        1.3366
                30 blackout                 2               30   residual_net     522   -1.3150     -1.4611    0.0326       -12.4372       -9.6066
                30 blackout                 2               90 residual_gross     485    0.4826      0.0076    0.5052         2.2082        1.7168
                30 blackout                 2               90   residual_net     485   -1.0174     -1.4924    0.0289        -4.6555       -3.6684
                30 blackout                 2              360 residual_gross     368    0.9038      0.0318    0.5272         2.5062        2.1475
                30 blackout                 2              360   residual_net     368   -0.5962     -1.4682    0.0326        -1.6533       -1.4234
```

## Primary result by year

```text
 timeframe_minutes      arm  entry_delay_bars  horizon_minutes  year  trades  residual_gross_mean_bps  residual_net_mean_bps  audusd_gross_mean_bps  audusd_net_mean_bps
                15 baseline                 1               30  2015     193                   1.4224                -0.0776                 2.0189               1.5189
                15 baseline                 1               30  2016     222                   1.0506                -0.4494                 2.5978               2.0978
                15 baseline                 1               30  2017     212                   0.8547                -0.6453                 0.9519               0.4519
                15 baseline                 1               30  2018     169                   0.7524                -0.7476                 0.7051               0.2051
                15 baseline                 1               30  2019     158                   0.7791                -0.7209                 1.0751               0.5751
                15 baseline                 1               30  2020     146                   1.6068                 0.1068                 0.6271               0.1271
                15 blackout                 1               30  2015     161                   1.5210                 0.0210                 2.5930               2.0930
                15 blackout                 1               30  2016     182                   1.0064                -0.4936                 2.9507               2.4507
                15 blackout                 1               30  2017     163                   0.8052                -0.6948                 1.3343               0.8343
                15 blackout                 1               30  2018     110                   0.5437                -0.9563                 1.1487               0.6487
                15 blackout                 1               30  2019      92                   0.5604                -0.9396                 2.5594               2.0594
                15 blackout                 1               30  2020      78                   1.4326                -0.0674                 4.0592               3.5592
```

Midpoint returns do not establish executable triangular arbitrage; modeled costs are sensitivities rather than observed spreads.
