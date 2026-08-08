# exploration_4 Findings — Frozen Mean-Reversion Baseline

## Verdict: **NO-GO**

This was one pre-specified baseline, not a sweep. The headline is per-signal
base-cost net R with UTC-day clustered uncertainty. Costs are modeled because
the midpoint archive has neither bid/ask nor volume; the breakeven round-trip is
therefore reported rather than presented as a measured spread.

Kill-test conditions (`true` means the NO-GO condition fired):

```json
{
  "gross_le_base_cost": true,
  "win_rate_near_geometry_break_even": false,
  "base_net_not_strictly_positive": true,
  "symmetric_diagnostic_fails": true,
  "fixed_horizon_diagnostic_fails": true,
  "random_exit_null_fails": false
}
```

## Headline and mandatory entry diagnostics

```text
   scope            outcome     n  clusters    mean     se        t  ci_low  ci_high  hit_rate
consumed    primary_gross_R 67871      3092 -0.0791 0.0068 -11.5951 -0.0925  -0.0657    0.4088
consumed primary_base_net_R 67871      3092 -0.3937 0.0071 -55.0991 -0.4077  -0.3797    0.3785
consumed  symmetric_gross_R 67871      3092 -0.0843 0.0049 -17.2354 -0.0939  -0.0747    0.5241
consumed fixed_stop_gross_R 67845      3092 -0.0900 0.0074 -12.2398 -0.1044  -0.0756    0.3695
consumed      raw_forward_R 67809      3092  0.0962 0.0110   8.7226  0.0746   0.1178    0.5412
 holdout    primary_gross_R 15367       660 -0.1829 0.0162 -11.2937 -0.2147  -0.1512    0.3911
 holdout primary_base_net_R 15367       660 -0.5356 0.0165 -32.4145 -0.5680  -0.5032    0.3560
 holdout  symmetric_gross_R 15367       660 -0.1659 0.0112 -14.7444 -0.1879  -0.1438    0.5055
 holdout fixed_stop_gross_R 15360       660 -0.1957 0.0169 -11.6108 -0.2287  -0.1627    0.3505
 holdout      raw_forward_R 15353       660  0.0093 0.0260   0.3568 -0.0417   0.0603    0.5101
```

The symmetric bracket uses the same session-boundary event as the main book,
with target and stop both at 1.5 frozen sigma. The fixed-horizon arm uses six
5-minute bars and retains the compulsory stop. `raw_forward_R` additionally shows
the unstopped next-open-to-next-open return. A diagnostic only passes the frozen
kill rule when its consumed-history 95% clustered CI is strictly above zero.

## Matched-rate random-exit control

The null preserves each pair/hour exit-duration distribution, identical entries,
price paths, compulsory stop and costs, while randomly re-pairing exit durations
to destroy alignment between path and reversion timing. It used
1,000 seeded draws.

```json
{
  "observed_mean_gross_R": -0.07910276760570024,
  "null_mean": -0.0927850970074646,
  "null_sd": 0.0030079820143727623,
  "null_q05": -0.09779302337959599,
  "null_q95": -0.08777849213111777,
  "one_sided_p": 0.000999000999000999,
  "passes": true,
  "preserves": "pair/hour exit-duration distribution, paths, entries, stops, costs",
  "destroys": "alignment between each path and its reversion-exit time"
}
```

## Cost economics by era

```text
    era    scenario  signals  gross_pips  cost_pips  net_pips
  early        base  49265.0     -0.2293     1.1898   -1.4192
  early  optimistic  49265.0     -0.2293     1.0429   -1.2722
  early pessimistic  49265.0     -0.2293     1.4347   -1.6641
holdout        base  15367.0     -0.5230     0.9796   -1.5026
holdout  optimistic  15367.0     -0.5230     0.8957   -1.4187
holdout pessimistic  15367.0     -0.5230     1.1194   -1.6424
   late        base  18606.0     -0.2325     1.0089   -1.2414
   late  optimistic  18606.0     -0.2325     0.9162   -1.1487
   late pessimistic  18606.0     -0.2325     1.1633   -1.3958
```

The full 24-hour table, including the expensive 21:00 UTC rollover and the
with/without-volatility cost sweep, is `artifacts/data_repair/NZDUSD_LSE_REPAIR_20260808/cost_by_era_hour.csv`.
For a constant round-trip pip charge, each cell's breakeven is its gross mean
pips. Modeled commission alone is 0.7 pip round trip for all four quote-USD pairs.

## Per-pair consumed-history result

```text
  pair     n    mean     se        t  ci_low  ci_high  hit_rate  session_mean_R  corr_block_mean_count
POOLED 67871 -0.3937 0.0071 -55.0991 -0.4077  -0.3797    0.3785         -0.3790                -0.1223
AUDUSD 15272 -0.4523 0.0125 -36.0415 -0.4769  -0.4277    0.3806         -0.4291                -0.0641
EURUSD 18258 -0.3565 0.0125 -28.5371 -0.3810  -0.3320    0.3775         -0.3433                -0.0450
GBPUSD 18455 -0.3055 0.0120 -25.3602 -0.3291  -0.2819    0.3722         -0.3107                 0.0186
NZDUSD 15886 -0.4826 0.0125 -38.5951 -0.5071  -0.4580    0.3849         -0.4589                -0.0674
```

`session_mean_R` is shown only as the requested warning diagnostic. It is not the
estimand. `corr_block_mean_count` quantifies the dependence that makes retrospective
session averaging unsafe.

## News blackout accounting

```text
  pair  feasible_crossings  near_news_crossings  unvetoed_book_trades  headline_book_trades  book_trade_delta
AUDUSD               22560                 2642                 21246                 18839              2407
EURUSD               26148                 2511                 24706                 22397              2309
GBPUSD               26807                 2905                 25255                 22608              2647
NZDUSD               22790                 2275                 21494                 19394              2100
```

Stateful non-overlap was re-run for the unvetoed and vetoed books; the comparison
is not a post-hoc filter of completed trades.

## Portfolio risk and the three Sharpes

```text
   scope  zero_day_sharpe  trade_days_only_sharpe  vol_targeted_sharpe  business_days  active_days  worst_day_R  max_drawdown_R
     all         -14.9047                -15.0661             -14.7172           3795         3752     -51.9560      34947.7387
consumed         -14.4920                -14.6517             -14.2661           3129         3092     -51.9560      26716.9256
   early         -14.6286                -14.8165             -14.4543           2348         2316     -51.9560      19658.8270
    late         -14.2308                -14.2805             -13.7468            779          776     -45.1637       7061.6018
 holdout         -17.5841                -17.7033             -17.0844            664          660     -48.3993       8224.8816
```

Daily P&L is marked across UTC midnights and summed across pairs. `zero_day_sharpe`
includes zero-P&L business days; `trade_days_only_sharpe` excludes them;
`vol_targeted_sharpe` uses a causal trailing-20-business-day volatility estimate,
median target and leverage clipped to 0.25–4.0. All use 252-day annualization.

## Sealed 2024+ holdout — opened once at final reporting

```text
    n  clusters    mean     se        t  ci_low  ci_high  hit_rate
15367       660 -0.5356 0.0165 -32.4145  -0.568  -0.5032     0.356
```

The holdout is reported separately and does not rescue a historical kill-test
failure. All available 2024-01-01 through the source end are included.

## Scope boundary

No regimes, alternative thresholds, clocks, anchors, pair features, or model
layers were tested. Independent review remains pending; this builder run must not
be treated as deployment approval even if the mechanical verdict were GO.

## Coverage limitation

```text
  pair  candidate_paths_excluded
EURUSD                       128
GBPUSD                       130
AUDUSD                       101
NZDUSD                       140
```

This repaired-data sensitivity leaves only 140 NZD path exclusions, versus
17,063 in frozen EXP-0001. The exclusion is causal and fully enumerated by
era/hour in this run's `DATA_QUALITY.md`. Restored NZD coverage does not rescue
the result: NZD and the pooled book remain negative at gross and base costs.
