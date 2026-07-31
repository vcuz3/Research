# NQ one-second clean data-quality report

Generated: 2026-07-27T14:56:03.235485+00:00

Source: `futures\data\databento\NQ_ohlcv-1s_NQv0_20100606_20260717.parquet`  
Clean output: `futures\nq\data\NQ_1s_clean.parquet`

## Verdict

PASS. The output preserves the raw sparse traded-second tape without filling or
dropping rows. Structural, source-checksum, roll, and one-minute aggregation
parity gates all pass. Absent seconds are expected because Databento emits an
OHLCV-1s bar only for seconds containing trades.

## Structure

| n_rows | first_ts | last_ts | unique_ts | instruments | rolls | null_ohlc | nonpositive | bad_ohlc | negative_volume |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 142481276 | 2010-06-07 00:00:00+00:00 | 2026-07-16 23:59:59+00:00 | 142481276 | 66 | 66 | 0 | 0 | 0 | 0 |

The out-of-core builder additionally hard-fails on adjacent duplicate or
out-of-order timestamps while reading each source row group and across row-group
boundaries; it found zero.

## Databento daily condition

| data_condition | n_rows | first_ts | last_ts |
| --- | --- | --- | --- |
| available | 136705729 | 2011-08-01 00:00:00+00:00 | 2026-07-16 23:59:59+00:00 |
| degraded | 605227 | 2014-06-11 00:00:00+00:00 | 2026-05-24 23:59:59+00:00 |
| unknown | 5170320 | 2010-06-07 00:00:00+00:00 | 2011-07-31 23:59:24+00:00 |

`unknown` is used for 2010-06-07 through 2011-07-31 because the supplied
condition history begins on 2011-08-01. Degraded rows remain present and are
explicitly labelled so each study can apply a documented exclusion policy.

## Source parity

| raw_rows | clean_rows | raw_hash | clean_hash | checksum_match |
| --- | --- | --- | --- | --- |
| 142481276 | 142481276 | 8308843276915678436 | 8308843276915678436 | True |

## RTH coverage by era

| era | sessions | bars | median_fill | mean_fill | min_fill | sessions_fill_ge_90pct | degraded_sessions | unknown_sessions |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 2010-2014 | 1164 | 14904275 | 0.5469 | 0.5472 | 0.0184 | 3 | 2 | 298 |
| 2015-2019 | 1288 | 21997669 | 0.7474 | 0.7299 | 0.0445 | 218 | 5 | 0 |
| 2020-2024 | 1291 | 28448420 | 0.9737 | 0.9417 | 0.1048 | 1186 | 4 | 0 |
| 2025-2026 | 396 | 8654731 | 0.9677 | 0.9340 | 0.1674 | 363 | 5 | 0 |

Fill is the fraction of the 23,400-second 09:30-16:00 ET grid containing a real
traded-second bar. No forward filling is performed in the clean dataset.

## RTH coverage by ET hour

| hr | sessions | bars | fill_rate |
| --- | --- | --- | --- |
| 9 | 4139 | 6894953 | 0.9255 |
| 10 | 4139 | 12843069 | 0.8619 |
| 11 | 4137 | 11771992 | 0.7904 |
| 12 | 4123 | 10647962 | 0.7174 |
| 13 | 4045 | 10134134 | 0.6959 |
| 14 | 4010 | 10419395 | 0.7218 |
| 15 | 4010 | 11293590 | 0.7823 |

Hour 09 uses the 09:30-09:59 half-hour denominator; hours 10-15 use 3,600
seconds per represented session.

## RTH gaps and rolls

| rth_rows | sessions | gap_events_gt_1s | max_gap_seconds | intra_rth_roll_flags |
| --- | --- | --- | --- | --- |
| 74005095 | 4139 | 10472333 | 875 | 0 |

Gaps longer than one second primarily measure sparse trading, not automatically
bad data. The maximum includes genuine market interruptions. There are zero
continuous-contract transitions during RTH.

## Canonical one-minute aggregation parity

| joined_minutes | only_1m | only_1s | mismatched_ohlcv |
| --- | --- | --- | --- |
| 5094910 | 0 | 0 | 0 |

Every overlapping minute aggregates exactly to `NQ_1m_clean.parquet` for open,
high, low, close, and volume.
