# 10% Volatility-Targeted Leg: Yearly Performance

Authoritative run: `EXP-0004`. The unfiltered 18:00-to-09:30 leg is sized to
10% annualized ex-ante volatility using its own prior 60 gross leg returns,
lagged one trade day, with a 3.0x leverage cap. Each side costs the smaller of
0.5 basis point of fill price or one NQ tick (0.25 point).

| Year | Trades | Gross return | Cost drag | Net return | Net vol | Sharpe | Max DD | Avg lev |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2011* | 45 | 3.95% | 0.31% | 3.65% | 9.15% | 2.239 | -4.00% | 0.655x |
| 2012 | 245 | 10.98% | 3.31% | 7.66% | 10.11% | 0.802 | -7.31% | 1.236x |
| 2013 | 245 | 23.28% | 4.51% | 18.77% | 9.59% | 1.893 | -4.79% | 1.523x |
| 2014 | 243 | 19.32% | 4.71% | 14.61% | 11.29% | 1.309 | -6.42% | 1.658x |
| 2015 | 253 | 6.03% | 3.14% | 2.90% | 12.26% | 0.294 | -12.57% | 1.188x |
| 2016 | 254 | -4.44% | 2.98% | -7.42% | 12.39% | -0.554 | -15.10% | 1.246x |
| 2017 | 253 | 39.20% | 6.70% | 32.51% | 10.25% | 2.787 | -4.71% | 2.227x |
| 2018 | 252 | 6.47% | 2.46% | 4.01% | 12.07% | 0.386 | -7.51% | 1.301x |
| 2019 | 254 | 15.05% | 2.01% | 13.05% | 9.64% | 1.311 | -12.52% | 1.069x |
| 2020 | 254 | 14.91% | 1.02% | 13.89% | 13.09% | 1.052 | -10.92% | 0.715x |
| 2021 | 254 | 8.96% | 1.04% | 7.92% | 10.17% | 0.795 | -6.75% | 1.101x |
| 2022 | 254 | -15.34% | 0.54% | -15.88% | 11.59% | -1.422 | -20.32% | 0.646x |
| 2023 | 253 | 4.03% | 0.94% | 3.09% | 9.15% | 0.377 | -7.51% | 1.043x |
| 2024 | 255 | 13.32% | 0.82% | 12.50% | 11.53% | 1.068 | -7.11% | 1.084x |
| 2025 | 252 | 8.15% | 0.58% | 7.57% | 10.72% | 0.734 | -10.87% | 0.980x |
| 2026** | 135 | 8.46% | 0.24% | 8.22% | 11.66% | 1.322 | -6.95% | 0.887x |

\* 2011 starts on 2011-10-26 after the 60-trade warm-up.  
\** 2026 ends on 2026-07-14.

## Full sample

- 3,701 sized trades; 60 warm-up trades excluded.
- Gross compound return: 329.79%; net compound return: 214.68%.
- Annualized net compound return: 8.12%.
- Realized annualized net volatility: 11.06%; Sharpe: 0.762.
- Maximum drawdown: -23.82%.
- Average/median/max leverage: 1.194x / 1.143x / 3.000x.
- The 3x cap bound on 11 days, all in 2017.
- The one-tick cost cap bound on 2,412 entries and 2,412 exits.

“Cost drag” is the difference between separately compounded gross and net yearly
returns, not the arithmetic sum of daily costs. The result cannot be checked for
numerical parity with the external figure until that figure's values and its
definition of “per-leg realized volatility” are supplied.

