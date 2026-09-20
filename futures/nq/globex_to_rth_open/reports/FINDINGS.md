# Findings

All findings are provisional and exploratory. EXP-0003 is authoritative; the
full history and every sweep cell are consumed discovery data.

## Baseline

The one-contract baseline produced $60.61 net per trade, Sharpe 0.531, HAC(5)
t=2.244, and a -$97,010 maximum drawdown across 3,761 trades. Net mean was
positive in all four frozen eras, but the dollar effect was much larger after
2023. See `BASELINE_REPLICATION.md`.

## Moving-average sweep

| Gate | Trades | Net $/trade | Net ATR14 units | Sharpe | HAC(5) t | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| SMA5 | 2,266 | $44.42 | 0.01128 | 0.460 | 1.465 | -$53,960 |
| SMA10 | 2,372 | $11.53 | 0.00348 | 0.119 | 0.375 | -$87,935 |
| SMA20 | 2,512 | $30.50 | 0.00946 | 0.326 | 1.057 | -$87,680 |
| SMA50 | 2,680 | $48.85 | 0.01123 | 0.502 | 1.726 | -$56,160 |
| SMA100 | 2,875 | $64.47 | 0.01482 | 0.659 | 2.430 | -$52,620 |
| SMA200 | 2,993 | $76.28 | 0.02135 | 0.731 | 2.711 | -$38,195 |

SMA200 is the strongest MA cell and remains net-positive in all eras, with
Sharpe 1.056/0.588/0.857/1.005. It is not a confirmed improvement: six windows
were searched, the gate changes trade frequency, no matched-rate placebo or
full-family null has run, and the 2016-2019 normalized effect is slightly below
the unconditional baseline.

## VIX sweep

The high-VIX region is the clearest lead. VIX >=25 had 492 trades, $287.56 net
per trade, 0.05538 prior-ATR14 units, Sharpe 1.601, and HAC(5) t=2.429. Its
normalized mean was positive in all four eras (0.0305, 0.0488, 0.0567, 0.1141),
but era counts were only 113, 31, 308, and 40. VIX >=40 printed much larger
numbers but has only 50 trades and is dominated by crisis observations.

ATR normalization shows the VIX lead is not only a mechanical consequence of
larger point ranges. It still does not establish selection-adjusted predictive
information: 27 overlapping ranges were searched, thresholds select distinct
regimes and trade counts, and no full-sweep feature-date permutation null has
run.

## Sizing comparison on the unconditional baseline

| Sizing | Trades | Net $/trade | Sharpe | HAC(5) t | Max DD |
| --- | ---: | ---: | ---: | ---: | ---: |
| One contract | 3,761 | $60.61 | 0.531 | 2.244 | -$97,010 |
| Inverse ATR14 | 3,688 | $46.71 | 0.493 | 1.994 | -$85,567 |
| Inverse VIX | 3,702 | $37.02 | 0.390 | 1.583 | -$103,162 |
| Inverse prior-day ATR | 3,701 | $24.27 | 0.213 | 0.856 | -$139,157 |

No inverse-vol rule dominates one contract. ATR14 sizing modestly reduced the
full-sample drawdown, but it turned net negative in 2020-2022. Inverse VIX and
one-day ATR degraded both full-sample Sharpe and drawdown. This is useful
negative evidence against assuming volatility scaling is automatically safer.

## Required next evidence

1. Run selection-aware full-sweep nulls that permute causal filter state within
   suitable era/calendar blocks while preserving overnight returns and rerun
   the complete selection rule.
2. Add matched-rate/filter-complement comparisons and cost stress at the 18:00
   market open.
3. Independently review clocks, rolls, sparse-window dates, and artifacts.
4. Treat only future observations as a clean holdout.

## Externally specified volatility-target reproduction

EXP-0004 applies a single prespecified 10% annualized target to the overnight
leg using lagged 60-leg realized volatility, a 3x cap, and capped 0.5-bp/side
cost. It compounds to 214.68% net over 3,701 sized trades, equivalent to 8.12%
annualized, with 11.06% realized volatility, Sharpe 0.762, and -23.82% maximum
drawdown. Fourteen of sixteen calendar-year rows are positive; 2016 and 2022 are
negative. See `VOL_TARGET_FIGURE.md`. This is a deterministic specification
reproduction, not external numerical parity, because the reference values were
not supplied.

## LSE SMA200 parity result

EXP-0005 reproduces the disclosed Sharpe near 0.99: the primary result is 1.014,
a +0.024 difference inside the frozen +/-0.10 tolerance. Across 2,417
post-warm-up observations and 1,991 active trades, net return compounds to
144.85% (9.79% annualized), realized volatility is 9.67%, and maximum drawdown
is -15.36%. Nearby conventions range from Sharpe 0.917 for close-to-close vol
sizing to 1.139 before costs. See `LSE_SMA200_FIGURE.md`. Mechanical parity is
successful; execution remains provisional because LSE supplies no contract IDs
or roll map.
