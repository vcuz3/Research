# LSE SMA200 Vol-Target Figure

Authoritative run: `EXP-0005`. Expected full-sample Sharpe was 0.99. The primary
result is 1.014, a +0.024 difference and inside the predeclared +/-0.10 tolerance.

## Primary yearly performance

Inactive post-warm-up dates are zero-return observations. Returns are net of
`min(0.5 bp, one tick)` per side.

| Year | Observations | Trades | Net return | Net vol | Sharpe | Max DD | Avg active leverage |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 2017* | 208 | 208 | 28.02% | 10.81% | 2.824 | -4.72% | 2.169x |
| 2018 | 256 | 209 | -2.14% | 10.04% | -0.162 | -9.04% | 1.374x |
| 2019 | 258 | 217 | 13.19% | 9.26% | 1.354 | -12.91% | 1.158x |
| 2020 | 254 | 232 | 6.61% | 11.49% | 0.611 | -12.25% | 0.751x |
| 2021 | 256 | 256 | 7.52% | 10.23% | 0.748 | -6.77% | 1.103x |
| 2022 | 256 | 16 | -3.40% | 2.86% | -1.178 | -4.68% | 1.071x |
| 2023 | 257 | 238 | 8.08% | 9.09% | 0.883 | -5.89% | 1.036x |
| 2024 | 259 | 258 | 19.18% | 11.26% | 1.573 | -6.88% | 1.065x |
| 2025 | 255 | 212 | 16.53% | 9.32% | 1.669 | -5.73% | 0.986x |
| 2026** | 158 | 145 | 3.89% | 9.82% | 0.668 | -7.38% | 0.826x |

\* Starts 2017-03-08 after SMA200 becomes available.  
\** Ends 2026-08-12.

## Full sample

- 2,417 portfolio observations and 1,991 active trades.
- Gross compound return 174.93%; net compound return 144.85%; compounded cost
  drag 30.08 percentage points.
- Annualized compound net return 9.79%.
- Realized net volatility 9.67%; Sharpe 1.014.
- Maximum drawdown -15.36%.
- Average active leverage 1.162x; average portfolio leverage 0.957x; cap bound
  on six dates.

## Difference attribution

| Convention | Sharpe | Net vol | Max DD |
| --- | ---: | ---: | ---: |
| Primary: entry-price SMA gate, zero inactive days, net | 1.014 | 9.67% | -15.36% |
| Gross before costs | 1.139 | 9.68% | -13.40% |
| Drop inactive days | 1.118 | 10.65% | -15.36% |
| Gate on prior RTH close instead of entry price | 1.044 | 9.68% | -13.16% |
| No SMA after the 200-day warm-up | 0.960 | 11.07% | -21.58% |
| Fixed 1x instead of vol targeting | 1.082 | 9.35% | -15.74% |
| Size from close-to-close rather than leg volatility | 0.917 | 5.28% | -9.03% |

The +0.024 difference from 0.99 is not material. The table shows why exact
parity can move by roughly 0.03-0.12 depending on cost, zero-day accounting,
gate clock, and volatility source.

## Data limitations

- The two tiles contain 3,556,402 unique ordered rows with no duplicate or
  invalid OHLC timestamps.
- They expose only the constant `NQ.F` symbol, so underlying contract changes
  and roll-crossing trades cannot be identified or excluded.
- 2,576 exact 18:00/09:30 candidates have the correct 15.5-hour duration. SMA200
  is unavailable for 159 of those candidates; 2,417 remain after warm-up.
- 756 candidates have an unprinted internal minute, but the median holding
  window has all 931 anchor-inclusive minutes. No internal prices are used.
- A 2020-03-01 to 2020-03-03 source outage creates the single open/prior-close
  link above 5%; it does not form an exact-clock trade across the gap.

