# LSE versus Databento yearly comparison

Run: EXP-0006, verified 2026-08-25.

## Result

The previously reported LSE and Databento tables were not comparable: LSE used
the SMA200 gate while Databento EXP-0004 was unfiltered. After applying the
identical SMA200/10%-vol-target rules, the 2022 gap nearly disappears. The large
remaining LSE advantage in 2023-2025 is concentrated in quarterly continuous-
contract splices inside the LSE overnight holding window.

Source-own-history figures are below. Returns are compounded net returns after
the specified costs. LSE 2026 ends 12 August; Databento ends 14 July.

| Year | LSE return | DB matched return | LSE Sharpe | DB matched Sharpe | Old DB unfiltered return |
| ---: | ---: | ---: | ---: | ---: | ---: |
| 2017 | 28.02% | 32.51% | 2.824 | 2.787 | 32.51% |
| 2018 | -2.14% | -3.88% | -0.162 | -0.340 | 4.01% |
| 2019 | 13.19% | 11.03% | 1.354 | 1.184 | 13.05% |
| 2020 | 6.61% | 7.28% | 0.611 | 0.663 | 13.89% |
| 2021 | 7.52% | 7.92% | 0.748 | 0.795 | 7.92% |
| 2022 | -3.40% | -3.35% | -1.178 | -1.178 | -15.88% |
| 2023 | 8.08% | 4.36% | 0.883 | 0.520 | 3.09% |
| 2024 | 19.18% | 10.97% | 1.573 | 0.956 | 12.50% |
| 2025 | 16.53% | 11.88% | 1.669 | 1.248 | 7.57% |
| 2026 | 3.89% | 2.14% | 0.668 | 0.445 | 8.22% |

## Attribution

### 1. Strategy mismatch in the earlier comparison

The SMA gate is economically important in some years. In 2022 it permits only
16 trades: matched Databento is -3.35%, almost exactly LSE's -3.40%, instead of
the old unfiltered Databento result of -15.88%. This is a strategy-definition
difference, not a feed difference.

### 2. LSE continuous-contract roll splices

The two pipelines make the same SMA decision on every one of 2,357 common
dates. However, LSE contains only the constant symbol `NQ.F`; it supplies no
underlying contract or roll flag. Fifteen common dates have an absolute LSE-
Databento overnight-return disagreement of at least 50 bp. They occur in
quarterly roll windows. Ten are active strategy dates.

For example, on trade date 2024-03-11 both feeds enter at 18,056.00. LSE exits
at 18,224.50 while Databento exits its same contract at 17,976.25, producing a
137.49 bp return disagreement. The LSE minute series jumps 247.50 points at
20:00 New York on Sunday 10 March, inside the position. Similar internal jumps
occur at quarterly roll windows in June, September, and December. The LSE
backtest therefore books part of the calendar spread as an overnight trading
gain. Databento retains contract identity and rejects true roll-crossing legs.

On common dates, removing only the >=50 bp mismatch observations gives:

| Year | Suspect dates | LSE return | DB return | LSE minus DB |
| ---: | ---: | ---: | ---: | ---: |
| 2022 | 2 | -3.40% | -3.35% | -0.05% |
| 2023 | 4 | 2.72% | 3.03% | -0.31% |
| 2024 | 4 | 12.55% | 12.36% | 0.19% |
| 2025 | 4 | 9.28% | 9.62% | -0.35% |
| 2026 | 1 | 2.21% | 2.14% | 0.08% |

Across all common dates after this diagnostic exclusion, LSE Sharpe is 0.851
and Databento Sharpe is 0.819. Thus the reproduced LSE Sharpe near 0.99 is
materially helped by its roll construction; it is not a clean same-contract
strategy estimate.

### 3. Coverage and endpoints

Databento has 49 additional 2017 observations before the LSE post-SMA warm-up
begins on 8 March. On the 204 common 2017 dates, returns are 29.79% LSE and
29.39% Databento, so the apparent 28.02% versus 32.51% own-history gap is mainly
calendar coverage. From 2017 through 2025, LSE also has roughly four dates per
year that Databento excludes around its own contract roll. In 2026, LSE has 23
additional observations after Databento ends; on dates common through 14 July,
the figures are 2.21% and 2.14%.

### 4. Ordinary bar differences

Outside the large roll mismatches, recent feeds are extremely close: mean
absolute overnight-return differences are 0.04 bp in 2024 and 0.04 bp in 2025.
The older 2018 and 2019 tiles differ more, averaging 0.84 and 0.60 bp absolute
per date. The gate never disagrees, and the common-date attribution assigns the
remaining 2018/2019 return gaps primarily to these source bar differences, not
to SMA signals or volatility sizing.

## Evidence

- Full yearly panel: `artifacts/runs/EXP-0006/yearly_side_by_side.csv`
- Common-date attribution: `artifacts/runs/EXP-0006/common_date_yearly_attribution.csv`
- Per-year source diagnostics: `artifacts/runs/EXP-0006/common_date_diagnostics.csv`
- Roll-mismatch dates: `artifacts/runs/EXP-0006/roll_mismatch_suspects.csv`
- Coverage: `artifacts/runs/EXP-0006/coverage_by_year.csv`
- Reproduction: `python futures\nq\globex_to_rth_open\scripts\compare_lse_databento.py`

The 50 bp cutoff is a post-run diagnostic used to isolate visually obvious
contract-splice observations, not a proposed trading rule.
