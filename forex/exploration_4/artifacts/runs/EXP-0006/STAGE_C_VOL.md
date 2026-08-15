# Stage C axis 2 — Volatility regime (compression vs expansion) overlay (EXP-0006)

Contract: `experiments/hypotheses/HYP-0006.md`, frozen before this run. Reproduce:
`python -u forex/exploration_4/_run_stage_c_vol.py`.

**Caveat:** the base ruler EXP-0004 has review corrections applied but *pending
re-verification*, and τ=5/H=240 are Stage-A consumed-history P&L-selected candidates. Stage C
proceeds at the user's direction; this result is conditional on the ruler holding.

The overlay is a **regime veto** on the frozen stateful, guarded, delay-1 book. The regime
feature `vr_z` is the **same-slot z-score of `sigma_abs`** (the slow all-hours 28,800-min
volatility — deliberately not `sigma_slot`, which is depth's denominator). Two symmetric arms
are swept and both reported: **compression** (keep lowest `vr_z`) and **expansion** (keep
highest `vr_z`), each re-non-overlapped after the veto (Stage-B F1). The decision is **excess
over the EXP-0005 depth benchmark at matched count**, not versus zero.

## Depth confound (the central control)

- **corr(vr_z, |z_slot|) on consumed eligible trades = +0.1337.** A regime veto that
  changes the kept set's mean |z_slot| is (partly) a depth cut in disguise; the "excess over
  depth at matched count" columns below are the quantitative version of this control.
- Base book (all vr_z-available trades, re-non-overlapped): n=66,796,
  gross -0.0275 R_slot, net -0.5648 R_slot.

## Compression arm frontier (consumed)

```text
 keep_fraction     n  abs_z  gross_R_slot  gross_pips  cost_pips  net_R_slot  net_ci_low  net_ci_high  bench_net_R_slot  excess_net_R_slot  excess_gross_R_slot
          0.10  8026 2.6620       -0.0194     -0.2128     1.2445     -0.5656     -0.6832      -0.4479           -0.5191            -0.0465              -0.0861
          0.15 11869 2.6706        0.0184     -0.0583     1.2485     -0.5263     -0.6274      -0.4251           -0.5236            -0.0027              -0.0369
          0.20 15599 2.6716        0.0050     -0.0999     1.2445     -0.5367     -0.6262      -0.4471           -0.5148            -0.0218              -0.0521
          0.25 19301 2.6782        0.0021     -0.1231     1.2456     -0.5394     -0.6211      -0.4576           -0.5264            -0.0130              -0.0394
          0.30 22974 2.6820       -0.0202     -0.1697     1.2446     -0.5612     -0.6380      -0.4843           -0.5392            -0.0220              -0.0441
          0.35 26549 2.6889       -0.0318     -0.1923     1.2456     -0.5743     -0.6469      -0.5017           -0.5469            -0.0274              -0.0440
          0.40 30022 2.6929       -0.0385     -0.2129     1.2468     -0.5839     -0.6519      -0.5159           -0.5639            -0.0200              -0.0313
          0.45 33413 2.6946       -0.0297     -0.1856     1.2446     -0.5759     -0.6424      -0.5095           -0.5735            -0.0024              -0.0104
          0.50 36808 2.6995       -0.0343     -0.2177     1.2405     -0.5798     -0.6436      -0.5160           -0.5695            -0.0103              -0.0160
          0.55 40262 2.7040       -0.0181     -0.1657     1.2386     -0.5608     -0.6224      -0.4992           -0.5649             0.0041              -0.0033
          0.60 43535 2.7082       -0.0140     -0.1583     1.2372     -0.5554     -0.6149      -0.4958           -0.5701             0.0147               0.0090
          0.65 46738 2.7115       -0.0122     -0.1525     1.2365     -0.5529     -0.6108      -0.4949           -0.5700             0.0171               0.0124
          0.70 49968 2.7150       -0.0143     -0.1591     1.2362     -0.5542     -0.6107      -0.4977           -0.5631             0.0089               0.0044
          0.75 53176 2.7196       -0.0121     -0.1629     1.2354     -0.5508     -0.6062      -0.4954           -0.5611             0.0103               0.0069
          0.80 56389 2.7237       -0.0135     -0.1541     1.2350     -0.5515     -0.6054      -0.4976           -0.5611             0.0096               0.0070
          0.85 59446 2.7294       -0.0021     -0.1171     1.2328     -0.5392     -0.5924      -0.4859           -0.5655             0.0264               0.0239
          0.90 62255 2.7379       -0.0019     -0.1116     1.2331     -0.5389     -0.5916      -0.4862           -0.5689             0.0301               0.0285
```

## Expansion arm frontier (consumed)

```text
 keep_fraction     n  abs_z  gross_R_slot  gross_pips  cost_pips  net_R_slot  net_ci_low  net_ci_high  bench_net_R_slot  excess_net_R_slot  excess_gross_R_slot
          0.10  4629 3.2496       -0.3808     -0.9819     1.2365     -0.9230     -1.2531      -0.5928           -0.5191            -0.4039              -0.4476
          0.15  7429 3.1161       -0.2484     -0.6164     1.2357     -0.7875     -1.0192      -0.5559           -0.5191            -0.2685              -0.3152
          0.20 10529 3.0385       -0.1041     -0.2633     1.2239     -0.6374     -0.8206      -0.4541           -0.5001            -0.1372              -0.1867
          0.25 13738 2.9794       -0.0838     -0.1942     1.2241     -0.6160     -0.7658      -0.4662           -0.5422            -0.0738              -0.1172
          0.30 16957 2.9434       -0.0657     -0.1965     1.2245     -0.5955     -0.7240      -0.4671           -0.5226            -0.0729              -0.1133
          0.35 20188 2.9139       -0.0621     -0.2082     1.2259     -0.5920     -0.7056      -0.4785           -0.5089            -0.0831              -0.1201
          0.40 23438 2.8927       -0.0625     -0.2121     1.2260     -0.5921     -0.6968      -0.4874           -0.5392            -0.0529              -0.0864
          0.45 26712 2.8762       -0.0476     -0.1878     1.2248     -0.5769     -0.6733      -0.4806           -0.5469            -0.0300              -0.0598
          0.50 30156 2.8635       -0.0244     -0.1157     1.2242     -0.5517     -0.6415      -0.4620           -0.5639             0.0121              -0.0172
          0.55 33570 2.8520       -0.0238     -0.1441     1.2216     -0.5521     -0.6353      -0.4689           -0.5735             0.0214              -0.0045
          0.60 36965 2.8386       -0.0160     -0.1254     1.2223     -0.5466     -0.6256      -0.4676           -0.5695             0.0229               0.0024
          0.65 40445 2.8281       -0.0224     -0.1503     1.2251     -0.5562     -0.6314      -0.4810           -0.5576             0.0014              -0.0131
          0.70 43985 2.8191       -0.0307     -0.1654     1.2274     -0.5662     -0.6377      -0.4947           -0.5701             0.0039              -0.0077
          0.75 47692 2.8107       -0.0381     -0.1853     1.2282     -0.5739     -0.6419      -0.5058           -0.5631            -0.0107              -0.0194
          0.80 51371 2.8026       -0.0405     -0.1994     1.2299     -0.5764     -0.6418      -0.5110           -0.5591            -0.0173              -0.0250
          0.85 55095 2.7947       -0.0359     -0.1868     1.2298     -0.5716     -0.6341      -0.5092           -0.5611            -0.0106              -0.0169
          0.90 58905 2.7872       -0.0245     -0.1502     1.2318     -0.5607     -0.6207      -0.5008           -0.5655             0.0048               0.0015
```

Full grids: `artifacts/runs/EXP-0006/regime_frontier_{compression,expansion}.csv`.
`excess_net_R_slot` = this arm's net minus the depth benchmark's net at the nearest matched
count (read from the swept `depth_frontier.csv`, never interpolated). A **positive** excess is
the only way a regime beats simply ranking by depth.

## Regime dose-response buckets (marginal, base book, by vr_z quantile)

```text
          bucket     n  vr_z_mean  abs_z_mean  gross_R_slot  gross_pips  cost_pips  net_R_slot  net_ci_low  net_ci_high  sigma_abs_pips  sigma_slot_pips
  (-inf, -1.096] 13360    -1.6557      2.6710       -0.0006     -0.1015     1.2479     -0.5442     -0.6403      -0.4481          2.9466           2.8537
(-1.096, -0.395] 13359    -0.7407      2.7074       -0.0564     -0.2560     1.2428     -0.5976     -0.6969      -0.4983          3.1299           2.8858
 (-0.395, 0.448] 13359     0.0153      2.7321       -0.0036     -0.1611     1.2255     -0.5469     -0.6506      -0.4432          3.3243           2.8422
  (0.448, 1.658] 13359     0.9892      2.7682       -0.0010     -0.1593     1.2255     -0.5268     -0.6333      -0.4204          3.7209           2.8805
    (1.658, inf] 13359     2.7372      2.9766       -0.0758     -0.1714     1.2242     -0.6085     -0.7617      -0.4552          4.2320           2.8450
```

Read `abs_z_mean` across buckets: if it trends with `vr_z`, the regime is entangled with depth.

## Decision

- **compression:** best net -0.5263 R_slot CI[-0.6274,-0.4251] at keep=0.15 (n=11,869, mean |z_slot|=2.671); depth benchmark net -0.5236 at matched count -> **excess -0.0027** (clears0=False, beats-depth=False).
- **expansion:** best net -0.5466 R_slot CI[-0.6256,-0.4676] at keep=0.60 (n=36,965, mean |z_slot|=2.839); depth benchmark net -0.5695 at matched count -> **excess +0.0229** (clears0=False, beats-depth=True).

- Gated null: **primary did NOT clear on either arm (net<=0 or fails to beat depth at matched count) -> null unnecessary (gate-nullc-on-success-metric)**.


## Sealed holdout (2024+), opened once

Read arm=compression keep=0.15: net -0.7873 R_slot, gross -0.279 pips, n=2794.

## Verdict

**VOL REGIME REJECTED as a rescue: on both arms, net R_slot never clears zero at a deployable count and/or fails to beat the EXP-0005 depth benchmark at matched count (i.e. any gross ordering is consistent with re-selecting depth). compression: best net -0.526 R_slot CI[-0.627,-0.425] (clears0=False), excess vs depth net -0.003 (beats=False) | expansion: best net -0.547 R_slot CI[-0.626,-0.468] (clears0=False), excess vs depth net +0.023 (beats=True)**

Interpretation: this is the expected outcome under the honest prior (run-book §7) if it
rejects — the ambient-vol regime does not separate capturable from un-capturable reversion
beyond what depth already does, and the ~1.25-pip modelled cost dwarfs any gross ordering. If
a regime "helped", the confound control above is where to look first.

## Limitations

- `vr_z` is built on `sigma_abs`; a regime measured on a shorter ambient window is a distinct,
  untested feature. Cost is modelled (no bid/ask); the guarded fill is a model.
- The keep-fraction cut uses the consumed vr_z sample quantile (a two-sided sample statistic);
  the holdout applies the consumed-frozen threshold.
- Conditional on EXP-0004 re-verification and the Stage-A repairs.
