# HYP-0001 Data Quality and Feature-Coverage Gate

- Experiment: `EXP-0001`
- Gate verdict: **PASS**
- Scope: Rule-9a data and feature construction only; no prices, fills, or P&L were scored.

## Outcome

The user-amended 40%-of-W same-sign floor is feasible on every preregistered window. The Rule-9a gate passes on the audited canonical one-minute archive resampled to five-minute RTH bars.

The legacy five-minute file remains a data-contract warning because its timestamp is timezone-naive. It is not used for signals; the effective source is the timezone-aware archive already audited by `nq.noise_vwap`.

## Declared data contract

- File: `C:/Users/VuDoa/Research/futures/nq/data/nq_5m_clean.parquet`
- Rows: 1,017,752; timestamps: 2012-01-04 04:40:00 to 2026-06-19 11:30:00
- Timestamp dtype: `datetime64[ns]`; timezone-aware: `False`
- Duplicate timestamps: 0; out-of-order transitions: 0
- Contract status: **FAIL** — HYP-0001 declares this timestamp UTC, but the parquet column is timezone-naive.

## Effective audited source

Five-minute RTH bars are derived from the audited timezone-aware `NQ_1m_clean.parquet`, as recorded in the pre-run user amendment. The legacy file is audited above but never used for signals.

- Eligible sessions: 3,718 (2011-08-01 to 2026-07-14)
- Five-minute rows: 289,997; expected-slot misses: 7
- Bars/session: 76 to 78
- Raw duplicate timestamps: 0; raw out-of-order transitions: 0
- One-minute within-session gap transitions: 11
- RTH roll rows: 0; multi-symbol RTH sessions: 0

## Feature gate

| W sessions | Required same-sign | Observed maximum | Eligible composite decisions | Coverage |
| ---: | ---: | ---: | ---: | ---: |
| 60 | 24 | 48 | 240767 | 89.9% |
| 90 | 36 | 67 | 239225 | 89.4% |
| 120 | 48 | 86 | 237422 | 88.7% |
| 252 | 101 | 164 | 228754 | 85.5% |

The first six decision slots (10:00–10:25 ET) cannot populate the 60-minute RTH horizon and are therefore dropped and counted. The headline clock-placebo CV is coverage-matched: fires divided by eligible decisions for slots with eligible observations. The unconditional all-slot CV is retained as a diagnostic so this structural warm-up is not hidden.

## Reproduction

`python -m futures.nq.percentile_rank_momentum.validation.coverage_report --experiment-id EXP-0001`

Detailed evidence is in the immutable run directory: `data_audit.json`, `feature_summary.csv`, `sign_counts_by_window_horizon_era_slot.csv`, `decision_coverage_by_window_era_slot.csv`, and `bar_coverage_by_era_slot.csv`.
