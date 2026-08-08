# exploration_4 Findings — Frozen Mean-Reversion Baseline

> **Scope note (2026-08-08).** Everything in this file is **EXP-0001**, the stopped
> 5-minute baseline. It remains valid as reported, but it is **superseded as the
> project's reference book**: the constraint set changed (the compulsory stop was
> dropped), and the run-book arc restarted at Stage A. The current market map is
> `MARKET_CHARACTERIZATION.md` (EXP-0002); the current coverage gate is
> `DATA_QUALITY.md`, which EXP-0002 rewrote for the multi-grain work (the EXP-0001
> snapshot is preserved at `../artifacts/runs/EXP-0001/DATA_QUALITY.md`). No Stage-B
> reference book exists yet, so nothing here has been replaced by a newer *book*.

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
consumed    primary_gross_R 55958      3092 -0.0815 0.0073 -11.2381 -0.0957  -0.0673    0.4040
consumed primary_base_net_R 55958      3092 -0.3733 0.0075 -49.5796 -0.3880  -0.3585    0.3774
consumed  symmetric_gross_R 55958      3092 -0.0865 0.0052 -16.6587 -0.0967  -0.0763    0.5220
consumed fixed_stop_gross_R 55932      3092 -0.0899 0.0079 -11.4299 -0.1054  -0.0745    0.3656
consumed      raw_forward_R 55896      3092  0.0932 0.0117   7.9326  0.0702   0.1162    0.5410
 holdout    primary_gross_R 12669       660 -0.1775 0.0172 -10.3449 -0.2111  -0.1438    0.3871
 holdout primary_base_net_R 12669       660 -0.5045 0.0174 -28.9886 -0.5386  -0.4704    0.3569
 holdout  symmetric_gross_R 12669       660 -0.1648 0.0121 -13.6688 -0.1884  -0.1412    0.5037
 holdout fixed_stop_gross_R 12662       660 -0.1924 0.0176 -10.9540 -0.2269  -0.1580    0.3471
 holdout      raw_forward_R 12655       660  0.0123 0.0275   0.4484 -0.0415   0.0661    0.5118
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
  "observed_mean_gross_R": -0.08149078976399385,
  "null_mean": -0.09175712858071214,
  "null_sd": 0.00338670983783963,
  "null_q05": -0.09725885326280936,
  "null_q95": -0.08590018932191441,
  "one_sided_p": 0.001998001998001998,
  "passes": true,
  "preserves": "pair/hour exit-duration distribution, paths, entries, stops, costs",
  "destroys": "alignment between each path and its reversion-exit time"
}
```

## Cost economics by era

```text
    era    scenario  signals  gross_pips  cost_pips  net_pips
  early        base  40779.0     -0.2501     1.1231   -1.3732
  early  optimistic  40779.0     -0.2501     0.9962   -1.2463
  early pessimistic  40779.0     -0.2501     1.3346   -1.5847
holdout        base  12669.0     -0.5226     0.9429   -1.4655
holdout  optimistic  12669.0     -0.5226     0.8701   -1.3927
holdout pessimistic  12669.0     -0.5226     1.0644   -1.5870
   late        base  15179.0     -0.2272     0.9674   -1.1946
   late  optimistic  15179.0     -0.2272     0.8872   -1.1144
   late pessimistic  15179.0     -0.2272     1.1011   -1.3283
```

The full 24-hour table, including the expensive 21:00 UTC rollover and the
with/without-volatility cost sweep, is `artifacts/runs/EXP-0001/cost_by_era_hour.csv`.
For a constant round-trip pip charge, each cell's breakeven is its gross mean
pips. Modeled commission alone is 0.7 pip round trip for all four quote-USD pairs.

## Per-pair consumed-history result

```text
  pair     n    mean     se        t  ci_low  ci_high  hit_rate  session_mean_R  corr_block_mean_count
POOLED 55958 -0.3733 0.0075 -49.5796 -0.3880  -0.3585    0.3774         -0.3607                -0.0905
AUDUSD 15272 -0.4523 0.0125 -36.0415 -0.4769  -0.4277    0.3806         -0.4291                -0.0641
EURUSD 18258 -0.3565 0.0125 -28.5371 -0.3810  -0.3320    0.3775         -0.3433                -0.0450
GBPUSD 18455 -0.3055 0.0120 -25.3602 -0.3291  -0.2819    0.3722         -0.3107                 0.0186
NZDUSD  3973 -0.4618 0.0247 -18.7140 -0.5101  -0.4134    0.3894         -0.4089                -0.0735
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
NZDUSD                5710                  649                  5390                  4783               607
```

Stateful non-overlap was re-run for the unvetoed and vetoed books; the comparison
is not a post-hoc filter of completed trades.

## Portfolio risk and the three Sharpes

```text
   scope  zero_day_sharpe  trade_days_only_sharpe  vol_targeted_sharpe  business_days  active_days  worst_day_R  max_drawdown_R
     all         -13.5351                -13.6695             -13.3712           3795         3752     -48.3925      27276.0541
consumed         -13.1454                -13.2784             -12.9568           3129         3092     -39.3278      20884.5704
   early         -13.3036                -13.4607             -13.1473           2348         2316     -39.3278      15369.4116
    late         -12.8212                -12.8622             -12.4287            779          776     -36.0330       5514.6420
 holdout         -15.8643                -15.9607             -15.5366            664          660     -48.3925       6385.2144
```

Daily P&L is marked across UTC midnights and summed across pairs. `zero_day_sharpe`
includes zero-P&L business days; `trade_days_only_sharpe` excludes them;
`vol_targeted_sharpe` uses a causal trailing-20-business-day volatility estimate,
median target and leverage clipped to 0.25–4.0. All use 252-day annualization.

## Sealed 2024+ holdout — opened once at final reporting

```text
    n  clusters    mean     se        t  ci_low  ci_high  hit_rate
12669       660 -0.5045 0.0174 -28.9886 -0.5386  -0.4704    0.3569
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
NZDUSD                     17063
```

NZDUSD has recurring late-era 18:00–19:00 UTC gaps, so the conservative requirement
for a completely observed path to the session-boundary event removes many more NZD
candidates than for the other pairs. The exclusion is causal and fully enumerated
by era/hour in `reports/DATA_QUALITY.md`, but it limits claims about NZD. It cannot
explain the pooled NO-GO: each of EURUSD, GBPUSD, and AUDUSD is independently and
strongly negative at base costs.
