# Stage B — Frozen Reference Book (EXP-0004)

Contract: `experiments/hypotheses/HYP-0004.md` and `artifacts/runs/EXP-0004/KILL_TEST.md`
(frozen before the run). Reproduce: `python -u forex/exploration_4/_run_stage_b.py`;
tests `python -m pytest forex/exploration_4/test_stage_b.py -q`.

**This version incorporates the corrections from Codex's independent review**
(`artifacts/runs/EXP-0004/independent_review_codex.md`); the point-by-point response is in
`artifacts/runs/EXP-0004/review.md`. The book is the **ruler** Stage C's overlays are measured
against; whether it is GO or NO-GO is not the point (Rule 25).

## The frozen book

- τ=5 same-slot z `(ret_5−μ_slot)/σ_slot` (90 prior sessions, `min_periods=60`, prior only).
- Entry: fade **|z_slot| ≥ 2.0**, first crossing; fill **delay-1** (two bars
  after the signal bar); delay-0 is a diagnostic.
- **No-entry rule (causal):** reject signals whose anchor is already crossed at entry.
- Exit (frozen): **guarded anchor-retrace** — limit at the anchor, credited only on a
  **0.25·σ_slot trade-through**, filled at the anchor price. **No stop.**
- Vetoes: news ±30 min; force-flat Friday 16:55 NY.
- **Estimand: the stateful one-position-per-pair book** (greedy non-overlap, Rule 13). The
  all-signal per-signal mean is reported only as a **diagnostic**.
- **Inherited grain is not confirmed:** τ=5 / H=240 were selected on Stage-A *consumed-history
  gross P&L* (Stage-A review F1). They are a frozen candidate, not an untuned or confirmed
  choice; Stage B adds no new P&L tuning.
- Units: `R_slot` (σ_slot, the sizing unit) headline; `R_abs` yardstick; pips physical.

> **On the exit comparators:** the `touch` and `time` arms are **diagnostics, not payoff
> bounds** — `touch` maximises the *chance of an anchor fill*, not P&L, and a missed fill can
> outperform a fill if price keeps going. Guarded gross sits *below* both here, so neither
> brackets it. No floor/ceiling language is used.

## 1. Coverage funnel (Rule 9a) — how signals become book trades

Per delay (both entry arms), pooled over pairs and eras:

```text
 delay  signals_pre_veto  news_vetoed  zero_cap_friday  no_entry_already_crossed  incomplete_path  book_eligible  friday_shortened
     0            198812        15471                0                         8            16337         166996              5365
     1            198812        15471              211                      7105            15985         160040              5053
```

Primary-arm (delay-1) book-eligibility by UTC hour (the post-news path loss is not
hour-neutral):

```text
 utc_hour  signals_pre_veto  news_vetoed  no_entry_already_crossed  incomplete_path  book_eligible
        0              8487          435                       368                0           7684
        1              8391          504                       281                0           7606
        2              8161          215                       258                0           7688
        3              8150          180                       297                0           7673
        4              8382          157                       364                0           7861
        5              8795           66                       356                0           8373
        6              8948          115                       333                0           8500
        7              8798          214                       243                0           8341
        8              8808          541                       243                0           8024
        9              8699          517                       265                0           7917
       10              8628          170                       247                0           8211
       11              8502          190                       268                0           8044
       12              8724         3012                       188                1           5523
       13              8500         2484                       202                0           5814
       14              8831         2206                       219                4           6402
       15              8953         1118                       279                2           7554
       16              8871          261                       315                9           8286
       17              8558          296                       316             2794           5152
       18              7237         1287                       241             3445           2264
       19              7281          702                       275             3901           2403
       20              8157          184                       386             4489           2957
       21              5853          220                       320             1340           3903
       22              6594          253                       403                0           5938
       23              8504          144                       438                0           7922
```

Full per-pair/era/hour funnel: `artifacts/runs/EXP-0004/exclusion_funnel.csv`. Non-overlap
(one-position) then reduces book-eligible to executed trades:

```text
  pair treatment  eligible  book_trades  occupancy_drop_pct
AUDUSD   guarded     38306        19368               49.44
AUDUSD      time     38306        12131               68.33
AUDUSD     touch     38306        20118               47.48
EURUSD   guarded     38043        19398               49.01
EURUSD      time     38043        11998               68.46
EURUSD     touch     38043        20072               47.24
GBPUSD   guarded     38667        19860               48.64
GBPUSD      time     38667        12234               68.36
GBPUSD     touch     38667        20659               46.57
NZDUSD   guarded     45024        22073               50.98
NZDUSD      time     45024        13550               69.90
NZDUSD     touch     45024        22899               49.14
```

## 2. Gross first — does the bare entry revert? (stateful book, pooled, consumed)

All exit arms, both entry arms; `gross_R_slot` is per-signal mean over the **non-overlap
book** with a UTC-day cluster-robust CI. Positive reversion is **established only if the CI
excludes zero on the positive side**.

```text
 delay treatment     n  gross_R_slot  gross_R_slot_ci_low  gross_R_slot_ci_high  gross_R_abs  gross_pips  cost_pips_base  anchor_fill_rate  timeout_rate  win_rate  mean_hold_min
     0   guarded 68947        0.0630               0.0096                0.1165       0.0113      0.0350          1.2386            0.7085        0.2915    0.7425       107.5915
     0      time 41914        0.3127               0.2073                0.4181       0.1989      0.7472          1.2424            0.0000        1.0000    0.5191       235.2213
     0     touch 71704        0.2410               0.1897                0.2922       0.1604      0.5408          1.2376            0.7363        0.2637    0.7634        98.7452
     1   guarded 66912       -0.0279              -0.0832                0.0274      -0.0503     -0.1716          1.2340            0.6969        0.3031    0.7412       109.4140
     1      time 41386        0.2583               0.1519                0.3647       0.1540      0.6275          1.2394            0.0000        1.0000    0.5143       235.4640
     1     touch 69488        0.1563               0.1032                0.2093       0.1027      0.3476          1.2334            0.7259        0.2741    0.7625       100.4027
```

**Primary arm (delay-1, guarded, stateful):** gross **-0.0279 R_slot**
CI [-0.0832, 0.0274];
**-0.0503 R_abs**; **-0.172 pips**. Anchor-fill rate
0.697, timeout 0.303, mean hold
109.4 min, mean |z| 2.77, n=66,912.

Positive gross reversion established at delay-1: **False**.
(All-signal diagnostic, same arm: gross -0.0205 R_slot, n=132,614 —
larger n, but not the deployable one-position estimand.)

## 3. Cost and net (primary stateful arm)

Gross **-0.172 pips** vs modelled base round trip **1.234**
pips; gross covers cost: **False** (gross is negative: a 0.172-pip rebate would be needed to reach zero).

```text
   scenario     n  net_R_slot  ci_low  ci_high  mean_cost_pips  mean_gross_pips
 optimistic 66912     -0.4946 -0.5502  -0.4391          1.0738          -0.1716
       base 66912     -0.5653 -0.6209  -0.5097          1.2340          -0.1716
pessimistic 66912     -0.6830 -0.7388  -0.6273          1.5010          -0.1716
```

Net by era (both units):

```text
     era     n  gross_R_slot  gross_pips  cost_pips_base  net_R_slot  net_R_slot_ci_low  net_R_slot_ci_high  net_R_abs
consumed 66912       -0.0279     -0.1716          1.2340     -0.5653            -0.6209             -0.5097    -0.4448
   early 49268       -0.0185     -0.1459          1.2887     -0.5663            -0.6309             -0.5017    -0.4484
 holdout 13787       -0.0964     -0.2550          1.0484     -0.6921            -0.8188             -0.5653    -0.5352
    late 17644       -0.0540     -0.2435          1.0812     -0.5625            -0.6716             -0.4533    -0.4349
```

Net CI excludes zero on the positive side: **False**.

## 4. Per pair (consumed, primary stateful arm)

```text
  pair     n  gross_R_slot  gross_R_slot_ci_low  gross_R_slot_ci_high  gross_R_abs  gross_pips  net_R_slot
AUDUSD 16134       -0.0782              -0.1627                0.0063      -0.0816     -0.2463     -0.6416
EURUSD 16095       -0.0097              -0.1036                0.0842      -0.0308     -0.1156     -0.4611
GBPUSD 16365       -0.0231              -0.1192                0.0730      -0.0725     -0.2975     -0.4535
NZDUSD 18318       -0.0038              -0.0814                0.0737      -0.0199     -0.0425     -0.6895
```

## 5. Per session (consumed, primary stateful arm) — descriptive only

EXP-0003 retracted the thin-hours localisation, and same-slot sizing makes net tilt toward
busy hours **structurally** (σ_slot ~2.2× larger at 21:00 than 13:00). Descriptive only; **no
session overlay is built on it in Stage B**.

```text
session     n  gross_R_slot  gross_R_abs  gross_pips  cost_pips_base  net_R_slot  net_R_abs
   asia 18302       -0.0264      -0.0240     -0.0414          1.3526     -0.6655    -0.4561
 london 15314       -0.1767      -0.1730     -0.6248          1.0460     -0.5310    -0.5055
     ny  7744        0.1392       0.0905      0.3416          1.1679     -0.4062    -0.2972
    off 14813        0.1230       0.0606      0.2203          1.4561     -0.6549    -0.4022
overlap 10739       -0.1469      -0.1746     -0.6579          1.0412     -0.4344    -0.5045
```

## 6. Three Sharpes (stateful one-position book, primary arm)

```text
     era basis  trades  mean_R_slot  sharpe_zero_day  sharpe_trade_days  sharpe_vol_targeted
consumed gross   66912       -0.028           -0.237             -0.258               -0.143
consumed   net   66912       -0.565           -4.715             -5.167               -4.752
 holdout gross   13787       -0.096           -0.780             -0.846               -0.674
 holdout   net   13787       -0.692           -5.445             -5.967               -5.289
```

## 7. Sealed holdout (2024+), opened once

Delay-1 guarded, pooled, stateful: gross **-0.0964 R_slot**
CI [-0.2227, 0.0299],
-0.255 gross pips, net
**-0.6921 R_slot**. Reported once; informed no frozen choice.

## Verdict

**reference book frozen (stateful one-position); positive gross reversion NOT established (CI includes 0); NET negative; gross -0.172 pips vs 1.234 modelled cost (gross negative: a 0.172-pip rebate would be needed to reach zero).**

The book is frozen and registered as the Stage-C ruler. A negative reference book is a valid
ruler (Rule 25): overlays are scored as excess over THIS stateful book at matched count, and —
because an overlay changes exits and therefore occupancy — each overlay must be re-run through
the same non-overlap machinery, never by filtering a completed-trade list.

## Limitations

- Midpoint OHLC only — no bid/ask. Cost is a modelled curve; the guarded-anchor fill is a
  **model**. The `time` comparator needs no fill assumption and is itself far below cost.
- The guard g=0.25σ_slot is a frozen fiat choice, not optimised.
- τ=5/H=240 are consumed-history P&L-selected (Stage-A review F1); a selection-aware null
  would be needed for any inferential claim about the selected maximum.
- UTC slots do not track DST. 2024+ read once, at the end.
