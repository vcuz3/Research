# Data Quality Report — Rule 9a (Stage A / EXP-0002)

Written by `python -u forex/exploration_4/_run_stage_a.py` **before** any Stage-A
statistic was interpreted. This supersedes the EXP-0001 version of this file for the
multi-grain work; the EXP-0001 snapshot is preserved at
`artifacts/runs/EXP-0001/DATA_QUALITY.md`.

Source fields are **midpoint OHLC only**: there is no `volume` column and no bid/ask.
Every cost figure in this project is therefore a modelling assumption and a
breakeven-pip curve, never a measured spread.

## Reporting gate

Unenumerated coverage rules: **none — every coverage rule below writes its own per-cell exclusion count**.

A coverage hole is a *finding* and is reported. A coverage hole that is not counted
is a *defect* and fails this gate.

## 1. Source integrity

```text
  pair  rows_raw               start                 end  duplicate_timestamps  out_of_order volume_field bid_ask
EURUSD   5536573 2011-07-19 00:00:00 2026-07-17 20:59:00                     0             0       absent  absent
GBPUSD   5536355 2011-07-19 00:00:00 2026-07-17 20:59:00                     0             0       absent  absent
AUDUSD   5536530 2011-07-19 00:00:00 2026-07-17 20:59:00                     0             0       absent  absent
NZDUSD   5437296 2011-12-06 20:00:00 2026-07-17 20:59:00                     0             0       absent  absent
```

## 2. Grain construction, per pair × grain × era

A τ-bar is tradable only when **all τ source minutes exist**; incomplete bars are
nulled, never forward-filled. `sigma` uses a **fixed 28,800-minute
(20-day) time window** at every rung — `window_bars` × τ = 28,800
for all τ — with a **fractional** `min_periods` floor of
0.9·window. A strict `min_periods == window` floor is what
turns one missing bar into a silent, time-of-day-dependent deletion of decisions; it
is deliberately not used.

```text
  pair  tau     era  eligible_bars  incomplete_bins  sigma_underpopulated  z_unavailable  window_bars  min_periods  z_available_share
AUDUSD    5   early         663979           282965                     0           2333         5760         5184             0.9965
AUDUSD    5 holdout         187929            79587                     0            660         5760         5184             0.9965
AUDUSD    5    late         221547            93813                     0            778         5760         5184             0.9965
AUDUSD   15   early         221322            94326                     0           2333         1920         1728             0.9895
AUDUSD   15 holdout          62643            26529                     0            660         1920         1728             0.9895
AUDUSD   15    late          73848            31272                     0            778         1920         1728             0.9895
AUDUSD   30   early         109514            48310                     0           2333          960          864             0.9787
AUDUSD   30 holdout          30995            13591                     0            660          960          864             0.9787
AUDUSD   30    late          36539            16021                     0            778          960          864             0.9787
AUDUSD   60   early          53605            25307                     0           2333          480          432             0.9565
AUDUSD   60 holdout          15171             7122                     0            660          480          432             0.9565
AUDUSD   60    late          17884             8396                     0            778          480          432             0.9565
AUDUSD  120   early          25634            13822                     0           2333          240          216             0.9090
AUDUSD  120 holdout           7258             3889                     0            660          240          216             0.9091
AUDUSD  120    late           8552             4588                     0            778          240          216             0.9090
EURUSD    5   early         663984           282960                     0           2333         5760         5184             0.9965
EURUSD    5 holdout         187929            79587                     0            660         5760         5184             0.9965
EURUSD    5    late         221547            93813                     0            778         5760         5184             0.9965
EURUSD   15   early         221316            94332                     0           2333         1920         1728             0.9895
EURUSD   15 holdout          62643            26529                     0            660         1920         1728             0.9895
EURUSD   15    late          73848            31272                     0            778         1920         1728             0.9895
EURUSD   30   early         109514            48310                     0           2333          960          864             0.9787
EURUSD   30 holdout          30995            13591                     0            660          960          864             0.9787
EURUSD   30    late          36539            16021                     0            778          960          864             0.9787
EURUSD   60   early          53605            25307                     0           2333          480          432             0.9565
EURUSD   60 holdout          15171             7122                     0            660          480          432             0.9565
EURUSD   60    late          17884             8396                     0            778          480          432             0.9565
EURUSD  120   early          25634            13822                     0           2333          240          216             0.9090
EURUSD  120 holdout           7258             3889                     0            660          240          216             0.9091
EURUSD  120    late           8552             4588                     0            778          240          216             0.9090
GBPUSD    5   early         663964           282980                     0           2333         5760         5184             0.9965
GBPUSD    5 holdout         187929            79587                     0            660         5760         5184             0.9965
GBPUSD    5    late         221547            93813                     0            778         5760         5184             0.9965
GBPUSD   15   early         221315            94333                     0           2333         1920         1728             0.9895
GBPUSD   15 holdout          62643            26529                     0            660         1920         1728             0.9895
GBPUSD   15    late          73848            31272                     0            778         1920         1728             0.9895
GBPUSD   30   early         109511            48313                     0           2333          960          864             0.9787
GBPUSD   30 holdout          30995            13591                     0            660          960          864             0.9787
GBPUSD   30    late          36539            16021                     0            778          960          864             0.9787
GBPUSD   60   early          53605            25307                     0           2333          480          432             0.9565
GBPUSD   60 holdout          15171             7122                     0            660          480          432             0.9565
GBPUSD   60    late          17884             8396                     0            778          480          432             0.9565
GBPUSD  120   early          25634            13822                     0           2333          240          216             0.9090
GBPUSD  120 holdout           7258             3889                     0            660          240          216             0.9091
GBPUSD  120    late           8552             4588                     0            778          240          216             0.9090
NZDUSD    5   early         669519           277425                    25            514         5760         5184             0.9992
NZDUSD    5 holdout         189339            78177                     0            137         5760         5184             0.9993
NZDUSD    5    late         223434            91926                     0            156         5760         5184             0.9993
NZDUSD   15   early         223172            92476                    13            502         1920         1728             0.9978
NZDUSD   15 holdout          63113            26059                     0            137         1920         1728             0.9978
NZDUSD   15    late          74478            30642                     0            156         1920         1728             0.9979
NZDUSD   30   early         111355            46469                    13            502          960          864             0.9955
NZDUSD   30 holdout          31491            13095                     0            137          960          864             0.9956
NZDUSD   30    late          37164            15396                     0            156          960          864             0.9958
NZDUSD   60   early          55446            23466                    13            502          480          432             0.9909
NZDUSD   60 holdout          15680             6613                     0            137          480          432             0.9913
NZDUSD   60    late          18507             7773                     0            156          480          432             0.9916
NZDUSD  120   early          27477            11979                    13            502          240          216             0.9817
NZDUSD  120 holdout           7774             3373                     0            137          240          216             0.9824
NZDUSD  120    late           9175             3965                     0            156          240          216             0.9830
```

### Worst 25 (pair × grain × era × UTC-hour) cells by unavailable-z share

```text
  pair  tau     era  utc_hour  eligible_bars  z_unavailable  share
AUDUSD   60   early        22           1524           1524 1.0000
AUDUSD  120   early        22           1524           1524 1.0000
AUDUSD   60    late        22            506            506 1.0000
AUDUSD  120    late        22            506            506 1.0000
AUDUSD  120 holdout        22            433            433 1.0000
GBPUSD   60   early        22           1524           1524 1.0000
EURUSD  120   early        22           1524           1524 1.0000
EURUSD   60   early        22           1524           1524 1.0000
EURUSD   60 holdout        22            433            433 1.0000
EURUSD   60    late        22            506            506 1.0000
GBPUSD  120    late        22            506            506 1.0000
GBPUSD  120 holdout        22            433            433 1.0000
GBPUSD   60 holdout        22            433            433 1.0000
GBPUSD   60    late        22            506            506 1.0000
GBPUSD  120   early        22           1524           1524 1.0000
AUDUSD   60 holdout        22            433            433 1.0000
EURUSD  120    late        22            506            506 1.0000
EURUSD  120 holdout        22            433            433 1.0000
EURUSD   30   early        21           3092           1520 0.4916
AUDUSD   30   early        21           3092           1520 0.4916
GBPUSD   30   early        21           3090           1518 0.4913
GBPUSD   30 holdout        21            883            433 0.4904
EURUSD   30 holdout        21            883            433 0.4904
AUDUSD   30 holdout        21            883            433 0.4904
GBPUSD   30    late        21           1037            505 0.4870
```

## 3. What each coverage rule removes, per pair × grain × era

`signals` counts first-crossing events at all four `k` thresholds pooled.
`news_vetoed` is the standing ±30-minute high-impact
blackout. `path_incomplete_H` is the strict requirement that every one-minute bar in
`[entry, entry+H]` exists. `friday_truncated_H` counts entries whose H-window would
run past the Friday 16:55 New York flat rule.

```text
  pair  tau     era  signals  news_vetoed  path_incomplete_15  path_incomplete_30  path_incomplete_60  path_incomplete_120  path_incomplete_240  path_incomplete_480  friday_truncated_15  friday_truncated_30  friday_truncated_60  friday_truncated_120  friday_truncated_240  friday_truncated_480
AUDUSD    5   early    94898        11985                 268                 531                1157                 3281                 8109                33346                   87                  153                  272                   607                  1263                  7081
AUDUSD    5 holdout    26048         3026                  42                  79                 221                  776                 2355                10776                   18                   22                   47                   111                   371                  2263
AUDUSD    5    late    32855         3616                  26                  54                 164                  801                 2539                13667                   14                   24                   53                   145                   404                  3058
AUDUSD   15   early    32721         4453                 101                 158                 401                 1172                 2912                11724                   18                   28                   75                   181                   411                  2465
AUDUSD   15 holdout     8947         1156                  10                  36                  96                  305                  928                 3895                    5                   10                   20                    41                   127                   797
AUDUSD   15    late    11230         1344                   7                  13                  50                  274                  918                 4697                    1                    4                   16                    46                   113                   953
AUDUSD   30   early    16828          776                   0                  62                 211                  610                 1506                 6672                    0                    6                   24                    83                   183                  1612
AUDUSD   30 holdout     4470          189                   0                  17                  59                  198                  520                 2195                    0                    0                    7                    19                    65                   485
AUDUSD   30    late     5637          246                   0                   3                  37                  162                  483                 2730                    0                    1                    9                    25                    64                   592
AUDUSD   60   early     8588          210                   0                   0                 163                  543                  903                 3718                    0                    0                   14                    47                   109                   927
AUDUSD   60 holdout     2285           55                   0                   0                  49                  141                  269                 1218                    0                    0                    5                     9                    30                   265
AUDUSD   60    late     2854           76                   0                   0                  52                  181                  335                 1541                    0                    0                    5                    10                    44                   354
AUDUSD  120   early     4019          161                   0                   0                   0                   94                  354                 1771                    0                    0                    0                     6                    40                   483
AUDUSD  120 holdout     1074           58                   0                   0                   0                   30                  106                  618                    0                    0                    0                     4                    18                   147
AUDUSD  120    late     1327           56                   0                   0                   0                   49                  121                  767                    0                    0                    0                     6                    25                   191
EURUSD    5   early    94979        12502                 224                 411                1008                 3083                 9407                41862                   87                  152                  298                   607                  1553                  9039
EURUSD    5 holdout    25830         3095                  64                 110                 272                  824                 2368                11936                   35                   47                   89                   149                   407                  2519
EURUSD    5    late    32262         3653                  22                  48                 205                  731                 2426                14554                   13                   19                   61                   109                   345                  3014
EURUSD   15   early    32882         4310                  73                 111                 300                 1047                 3290                14653                   22                   26                   72                   179                   517                  3081
EURUSD   15 holdout     8783         1146                  13                  40                 109                  307                  910                 4103                    3                    5                   21                    47                   117                   821
EURUSD   15    late    11127         1315                   4                  14                  54                  265                  851                 5214                    3                    4                   11                    34                   115                  1047
EURUSD   30   early    16726         1070                   0                  50                 158                  518                 1785                 8356                    0                    5                   30                    88                   287                  1897
EURUSD   30 holdout     4437          281                   0                  11                  47                  200                  483                 2367                    0                    1                    7                    19                    52                   507
EURUSD   30    late     5532          321                   0                   7                  36                  169                  477                 2932                    0                    1                    3                    21                    61                   648
EURUSD   60   early     8425          509                   0                   0                 146                  529                 1105                 4768                    0                    0                   27                    64                   150                  1125
EURUSD   60 holdout     2298          130                   0                   0                  48                  146                  290                 1381                    0                    0                    6                    10                    38                   288
EURUSD   60    late     2783          135                   0                   0                  37                  143                  297                 1673                    0                    0                    5                    10                    38                   371
EURUSD  120   early     3931          312                   0                   0                   0                  105                  436                 2308                    0                    0                    0                    17                    69                   587
EURUSD  120 holdout     1100           74                   0                   0                   0                   20                   98                  690                    0                    0                    0                     5                    24                   152
EURUSD  120    late     1335           78                   0                   0                   0                   32                  117                  816                    0                    0                    0                     5                    27                   210
GBPUSD    5   early    99447        14567                 337                 563                1148                 2846                 8386                39704                  143                  216                  379                   661                  1483                  8338
GBPUSD    5 holdout    27232         3503                  53                 101                 249                  756                 2378                12290                   28                   39                   65                   127                   416                  2512
GBPUSD    5    late    33393         3883                  34                  56                 189                  712                 2284                14259                   25                   36                   83                   142                   381                  3099
GBPUSD   15   early    34646         5200                  87                 137                 350                  895                 2819                13879                   28                   41                  104                   186                   460                  2894
GBPUSD   15 holdout     9287         1346                  11                  27                  88                  277                  874                 4246                    1                    6                   19                    35                   116                   859
GBPUSD   15    late    11269         1366                   2                   7                  42                  230                  799                 4923                    0                    2                   12                    31                   107                  1020
GBPUSD   30   early    17757         1256                   0                  56                 163                  464                 1522                 7836                    0                    7                   35                    73                   226                  1758
GBPUSD   30 holdout     4626          274                   0                   8                  49                  171                  453                 2333                    0                    0                   11                    19                    59                   495
GBPUSD   30    late     5648          318                   0                   2                  33                  122                  435                 2755                    0                    0                    5                    16                    53                   625
GBPUSD   60   early     9027          381                   0                   0                 105                  434                  909                 4266                    0                    0                   18                    42                   124                   971
GBPUSD   60 holdout     2381          121                   0                   0                  45                  137                  255                 1341                    0                    0                    6                    11                    34                   303
GBPUSD   60    late     2817          134                   0                   0                  34                  130                  277                 1546                    0                    0                    5                     9                    37                   346
GBPUSD  120   early     4167          219                   0                   0                   0                   66                  356                 2030                    0                    0                    0                     9                    62                   509
GBPUSD  120 holdout     1146           56                   0                   0                   0                   20                  101                  687                    0                    0                    0                     2                    19                   163
GBPUSD  120    late     1318           67                   0                   0                   0                   31                  100                  767                    0                    0                    0                     4                    32                   208
NZDUSD    5   early    96663        10560                 168                 249                 443                  826                 1618                 7711                  157                  236                  413                   762                  1479                  7368
NZDUSD    5 holdout    26298         2830                  15                  22                  36                  101                  355                 2117                   13                   20                   33                    89                   319                  2059
NZDUSD    5    late    33328         3369                   9                  15                  41                  149                  435                 2959                    9                   15                   39                   148                   433                  2954
NZDUSD   15   early    32728         3944                  18                  35                  91                  200                  470                 2555                   16                   33                   83                   183                   420                  2439
NZDUSD   15 holdout     9052         1130                   7                  11                  16                   37                  118                  719                    7                   11                   16                    34                   110                   709
NZDUSD   15    late    11374         1273                   2                   8                  14                   61                  142                  987                    2                    8                   14                    58                   141                   985
NZDUSD   30   early    16949         1115                   0                  17                  45                   99                  233                 1678                    0                   16                   39                    90                   214                  1621
NZDUSD   30 holdout     4520          240                   0                   0                   4                   12                   46                  450                    0                    0                    4                    12                    41                   443
NZDUSD   30    late     5812          293                   0                   1                   3                   31                   78                  617                    0                    1                    3                    29                    77                   616
NZDUSD   60   early     8917          606                   0                   0                  20                   60                  128                  984                    0                    0                   15                    53                   115                   950
NZDUSD   60 holdout     2438          129                   0                   0                   4                    5                   23                  250                    0                    0                    4                     5                    22                   249
NZDUSD   60    late     2997          168                   0                   0                   3                   12                   39                  348                    0                    0                    3                    12                    39                   348
NZDUSD  120   early     4784          355                   0                   0                   0                    6                   58                  533                    0                    0                    0                     5                    54                   521
NZDUSD  120 holdout     1320           93                   0                   0                   0                    5                   19                  150                    0                    0                    0                     2                    16                   147
NZDUSD  120    late     1574           93                   0                   0                   0                    6                   27                  210                    0                    0                    0                     6                    27                   210
```

### Where the long-horizon path rule bites, by UTC hour

The `H = 480` completeness rule removes a **third to two-fifths** of all signals, and
it does not remove them evenly. Any 8-hour window that spans the weekend, or the
archive's daily ~21:00–22:00 UTC rollover hole, is excluded. That matters here because
the conditional reversion in `MARKET_CHARACTERIZATION.md` §2 concentrates in exactly
those thin hours, so **the common (H = 480-complete) sample is biased away from the
hours where the effect is largest**. Both the common and the maximal-sample surfaces
are reported for that reason; read them together.

Share of signals excluded at H = 480, by UTC hour and grain:

```text
 utc_hour  tau_5  tau_15  tau_30  tau_60  tau_120
        0  0.000   0.000   0.000   0.000    0.000
        1  0.000   0.000   0.000   0.000      NaN
        2  0.000   0.000   0.000   0.000    0.000
        3  0.000   0.000   0.000   0.000      NaN
        4  0.000   0.000   0.000   0.000    0.000
        5  0.000   0.000   0.000   0.000      NaN
        6  0.000   0.000   0.000   0.000    0.000
        7  0.000   0.000   0.000   0.000      NaN
        8  0.000   0.000   0.001   0.000    0.000
        9  0.000   0.000   0.000   0.000      NaN
       10  0.001   0.000   0.001   0.000    0.000
       11  0.000   0.000   0.000   0.000      NaN
       12  0.000   0.000   0.000   0.001    0.000
       13  0.557   0.539   0.666   0.709      NaN
       14  0.823   0.819   0.824   0.833    0.835
       15  0.829   0.831   0.822   0.816      NaN
       16  0.830   0.836   0.847   0.834    0.811
       17  0.829   0.828   0.833   0.835      NaN
       18  0.790   0.785   0.788   0.799    0.811
       19  0.753   0.759   0.776   0.769      NaN
       20  0.742   0.721   0.703   0.747    0.489
       21  0.266   0.348   0.437   0.514      NaN
       22  0.000   0.000   0.000   0.000    0.000
       23  0.000   0.000   0.000   0.000      NaN
```

## 4. NZDUSD-specific exclusion (known late-era 18:00–19:00 UTC holes)

NZD's coverage limits NZD-specific claims. It is enumerated rather than summarized —
worst 20 cells by excluded share at H = 480:

```text
    era  utc_hour  signals  path_incomplete  excluded_share
  early        14    14404             3600          0.2499
   late        14     6864             1679          0.2446
  early        15    12153             2943          0.2422
  early        16     8165             1971          0.2414
holdout        15     3681              861          0.2339
   late        16     2574              583          0.2265
holdout        16     2202              495          0.2248
   late        15     4701             1038          0.2208
holdout        14     4694             1033          0.2201
holdout        17     1337              283          0.2117
  early        17     3954              806          0.2038
   late        17     1358              273          0.2010
  early        13    11475             2135          0.1861
   late        13     5299              958          0.1808
  early        20     3757              620          0.1650
holdout        13     3774              609          0.1614
holdout        18     1366              216          0.1581
  early        18     4602              663          0.1441
   late        18     1802              259          0.1437
   late        20      867              123          0.1419
```

## 5. Weekend / long-gap jump distribution (gaps ≥ 120 minutes)

The weekend-flat constraint exists because these jumps are unhedgeable. Jump is
`(first open after the gap − last close before it)` in pips.

```text
  pair     era  count   mean    std     min      5%   50%    95%    max
AUDUSD   early  504.0 -1.626 16.998  -83.25 -27.962 -1.80 21.590 105.00
AUDUSD holdout  137.0 -1.641 15.519  -69.75 -24.350 -0.60 22.700  46.15
AUDUSD    late  156.0 -1.103 10.336  -47.65 -17.887 -0.20 12.325  38.95
EURUSD   early  504.0 -1.530 22.884 -178.85 -30.485 -0.55 23.143 178.25
EURUSD holdout  137.0 -2.759 20.191 -111.20 -36.880 -0.70 24.980  58.15
EURUSD    late  156.0 -0.078 14.019 -120.00 -14.050  0.25 13.025  53.25
GBPUSD   early  504.0 -1.827 23.357 -227.30 -28.682 -0.20 23.167 119.60
GBPUSD holdout  137.0 -3.895 19.082  -83.45 -41.210 -0.75 16.140  60.55
GBPUSD    late  156.0 -0.020 15.668  -77.45 -20.175 -0.10 15.875  82.20
NZDUSD   early  484.0 -1.995 14.723  -65.40 -23.250 -1.50 18.181  88.00
NZDUSD holdout  137.0 -0.334 15.640  -52.10 -21.750 -0.90 19.970 116.05
NZDUSD    late  156.0 -1.708 11.153  -63.80 -16.700 -0.75 12.612  54.25
```

## 6. Known limitations carried forward

- The exact 17:00 New York rollover bar is unavailable in this archive; 16:55 is the
  last attainable open, and the Friday-flat minute is set there.
- Midpoint-only data means the spread is unmeasured; all "net" figures are
  assumption-driven and are always shown beside gross and a breakeven pip.
- Session labels use each venue's own timezone with real DST, not fixed UTC blocks.
