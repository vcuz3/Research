# Stage C axis 1 — Displacement depth (|z_slot|) overlay (EXP-0005)

Contract: `experiments/hypotheses/HYP-0005.md`, frozen before this run. Reproduce:
`python -u forex/exploration_4/_run_stage_c_depth.py`.

**Caveat:** the base ruler EXP-0004 has review corrections applied but *pending
re-verification*, and τ=5/H=240 are Stage-A consumed-history P&L-selected candidates. Stage C
proceeds at the user's direction; this result is conditional on the ruler holding.

Depth is the run-book's **first-and-alone** Stage-C axis: prior FX work found it a
near-sufficient statistic, so its gross-response curve is the **benchmark every later overlay
must beat at matched count**. The overlay is a **depth veto** on the frozen stateful, guarded,
delay-1 book, with the one-position non-overlap **re-applied after each veto** (Stage-B F1).

## Base book parity (t = 2.0 reproduces EXP-0004)

n=66,912, gross -0.0279 R_slot [-0.0832, 0.0274],
net -0.5653 R_slot [-0.6209, -0.5097] — matches the frozen book.

## Depth frontier (consumed; re-non-overlapped stateful book at each threshold)

```text
 depth_threshold     n  pairs  abs_z  gross_R_slot  gross_ci_low  gross_ci_high  gross_pips  cost_pips  net_R_slot  net_ci_low  net_ci_high  anchor_fill_rate
             2.0 66912      4 2.7708       -0.0279       -0.0832         0.0274     -0.1716     1.2340     -0.5653     -0.6209      -0.5097            0.6969
             2.1 60340      4 2.8912       -0.0260       -0.0854         0.0333     -0.1535     1.2330     -0.5655     -0.6252      -0.5058            0.6920
             2.2 54337      4 3.0114       -0.0191       -0.0823         0.0442     -0.1445     1.2322     -0.5611     -0.6248      -0.4974            0.6862
             2.3 48910      4 3.1313       -0.0187       -0.0865         0.0490     -0.1328     1.2314     -0.5631     -0.6313      -0.4950            0.6793
             2.4 43803      4 3.2581       -0.0230       -0.0965         0.0506     -0.1509     1.2319     -0.5701     -0.6440      -0.4962            0.6723
             2.5 39329      4 3.3832       -0.0148       -0.0930         0.0635     -0.1364     1.2324     -0.5649     -0.6435      -0.4864            0.6657
             2.6 35215      4 3.5092       -0.0179       -0.1031         0.0673     -0.1330     1.2334     -0.5708     -0.6563      -0.4853            0.6593
             2.7 31587      4 3.6405       -0.0072       -0.0995         0.0851     -0.1053     1.2343     -0.5631     -0.6556      -0.4706            0.6550
             2.8 28418      4 3.7651        0.0043       -0.0934         0.1020     -0.0385     1.2339     -0.5533     -0.6513      -0.4553            0.6510
             2.9 25493      4 3.8947        0.0075       -0.0983         0.1134     -0.0260     1.2347     -0.5520     -0.6581      -0.4459            0.6447
             3.0 22933      4 4.0257        0.0239       -0.0900         0.1378     -0.0030     1.2373     -0.5392     -0.6533      -0.4251            0.6400
             3.1 20522      4 4.1667        0.0581       -0.0659         0.1820      0.0797     1.2399     -0.5089     -0.6331      -0.3847            0.6356
             3.2 18446      4 4.3022        0.0289       -0.1056         0.1635     -0.0017     1.2408     -0.5398     -0.6745      -0.4051            0.6270
             3.3 16662      4 4.4401        0.0476       -0.0967         0.1919      0.0526     1.2419     -0.5226     -0.6670      -0.3783            0.6218
             3.4 15094      4 4.5757        0.0477       -0.1087         0.2042      0.0778     1.2427     -0.5253     -0.6818      -0.3689            0.6175
             3.5 13674      4 4.7180        0.0334       -0.1342         0.2010      0.0117     1.2457     -0.5422     -0.7098      -0.3746            0.6109
             3.6 12428      4 4.8560        0.0396       -0.1389         0.2181      0.0287     1.2478     -0.5385     -0.7169      -0.3600            0.6068
             3.7 11336      4 4.9910        0.0552       -0.1350         0.2453      0.0644     1.2486     -0.5241     -0.7143      -0.3340            0.6017
             3.8 10286      4 5.1395        0.0825       -0.1239         0.2890      0.1283     1.2508     -0.5001     -0.7067      -0.2935            0.5985
             3.9  9386      4 5.2823        0.0647       -0.1551         0.2846      0.0644     1.2521     -0.5207     -0.7405      -0.3010            0.5910
             4.0  8555      4 5.4339        0.0667       -0.1793         0.3128      0.1550     1.2513     -0.5191     -0.7652      -0.2729            0.5854
```

Full grid: `artifacts/runs/EXP-0005/depth_frontier.csv`. Gross depth slope:
**+0.0569 R_slot per unit of |z_slot|**
(deeper raises gross).

## Depth dose-response buckets (marginal, base book)

```text
       bucket     n  abs_z_mean  gross_R_slot  gross_pips  cost_pips  net_R_slot  net_ci_low  net_ci_high  anchor_fill_rate  sigma_slot_pips
 (-inf, 2.14] 13383      2.0672       -0.0574     -0.2515     1.2288     -0.5758     -0.6587      -0.4929            0.7297           2.9261
 (2.14, 2.33] 13382      2.2301       -0.0364     -0.2382     1.2283     -0.5569     -0.6456      -0.4682            0.7263           2.9224
 (2.33, 2.61] 13382      2.4591        0.0177     -0.0201     1.2249     -0.5084     -0.6052      -0.4116            0.7156           2.8960
(2.61, 3.133] 13382      2.8373       -0.0755     -0.3445     1.2312     -0.6179     -0.7185      -0.5173            0.6867           2.8377
 (3.133, inf] 13383      4.2602        0.0121     -0.0037     1.2567     -0.5674     -0.7296      -0.4052            0.6259           2.7285
```

## Decision

- Best deployable net (n ≥ 2000): depth ≥ 3.80, net -0.5001 R_slot CI [-0.7067, -0.2935], n=10,286, gross 0.128 pips vs 1.251 cost.
- Net clears zero at a deployable depth: **False**.
- Gated null: **primary did NOT clear at any deployable depth -> null unnecessary (gate-nullc-on-success-metric)**.


## Sealed holdout (2024+), opened once

Deepest deployable threshold ≥ 4.00:
net -1.0291 R_slot,
gross -0.806 pips, n=1,536. Read once.

## Verdict

**DEPTH REJECTED as a rescue: net R_slot never clears zero at a deployable depth; gross does order by depth (deeper = higher gross). The gross depth-response curve is retained as the Stage-C benchmark.**

Retained for Stage C: the **gross depth-response curve** (`depth_frontier.csv`) is the
matched-count benchmark. Later overlays (vol, cross-pair, session, exit-horizon) must beat this
curve at equal trade count and clear their own claim-matched null; if a later regime "helps",
first suspect it is just selecting deeper |z_slot|.

## Limitations

- Depth is the entry variable itself, so this is a benchmark, not an independent conditioner.
- Cost is modelled (no bid/ask); the guarded fill is a model; net grows σ-scaled cost with
  depth, which is why depth ordering gross need not order net.
- Conditional on EXP-0004 re-verification and the open Stage-A repairs.
