# DATA_QUALITY — weekend gap study (Rule 9a gate)

Run: `python _run_data_quality.py` → `artifacts/runs/EXP-0001/data_quality.csv`
Date: 2026-08-12. Status: **PASS, with one material finding that changed the
study design.**

---

## Finding 1 (material) — three archives carry synthetic weekend bars

`data/USDJPY_1m.parquet`, `data/NZDJPY_1m.parquet` and `data/EURJPY_1m.parquet`
contain **Saturday bars**, which cannot exist in spot FX.

| Pair | Saturday bars | Concentrated in | Zero-range fraction |
| --- | --- | --- | --- |
| NZDJPY | 181,699 | 2021–2023 | 1.5% |
| EURJPY | 11,457 | 2021–2023 | 58.5% |
| USDJPY | 761 | 2011, 2021–23 | 97.5% |
| EURUSD, AUDUSD, GBPUSD, NZDUSD, AUDJPY, GBPJPY | **0** | — | — |

NZDJPY's Saturday coverage in 2021–2023 is **uniform across all 24 hours**
(~7,500 bars in every hour), and its weekday bar count rises to exactly 1,440
per day in those years against ~1,400 elsewhere. That vintage is gap-filled: a
padded series, not observed quotes. USDJPY's are almost all zero-range, i.e.
stale padding rather than fabricated movement.

Weekday coverage is otherwise uniform across all years for all pairs
(~1,395–1,440 bars/day, no year-on-year step), so **only the boundary is
affected** — but the boundary is the entire object of this study.

### Consequence

The naive definition of a weekend gap — "the price change across the ≥24 h
break in this pair's own series" — silently failed on exactly these pairs,
because the padding means no ≥24 h break exists. Detected weekends: NZDJPY
637 and EURJPY 653 against 782 expected (capture 0.78/0.80). Those ~145
missing weekends were **not** random: they were the padded era. Left alone,
the study would have compared pairs on different weekend windows and silently
dropped one era from two pairs.

### Fix adopted

A **canonical weekly session calendar** is derived from EURUSD (clean, longest,
most liquid) and imposed on all nine pairs: `week_close` = last EURUSD minute
before the break, `week_open` = first EURUSD minute after. Each pair's Friday
close and reopen are then snapped to its own nearest real bar, with a ±60 min
tolerance and the achieved lag recorded.

Post-fix: **782 weekends, boundary_ok = 100% for every pair**, max snap lag
30 min (GBPUSD/AUDJPY) and 26 min (USDJPY). Entry coverage 100% at all four
delays; exit coverage ≥98.2% at every horizon out to 5 days.

This also removes a confound the study would have had regardless: without one
calendar, cross-pair comparisons would have been run on slightly different
weekend windows.

### Residual limitation

For the padded pairs in 2021–2023 the boundary timestamps are real, so the
prices read at them are real (any interpolation lies strictly *between* the
Friday close and the Sunday open). The era is nevertheless reported separately
in EXP-0001 §C4: padded JPY 2021–23 mean R +0.202, t +0.47, n=69 — no
distortion of the headline, and no era is carrying it.

## Finding 2 — a mixed datetime storage unit, caught by the gate

`forex/data/**` stores `datetime64[us]`; the JPY parquets store
`datetime64[us, UTC]`. The first version of the event builder computed
timestamp lags with a hard-coded nanosecond divisor. The gate caught it
immediately: **exit coverage printed 0.0% for every pair at every horizon**,
while entry coverage printed a vacuous 100% because the same corrupted lag
passed a one-sided `<= 60` test.

This is the LEARNINGS §5 hazard exactly (a unit-dependent int64 divisor that is
right on one archive and 1000× wrong on another). All lag arithmetic now
subtracts `DatetimeIndex` objects, which is exact at any storage unit, and
whole-minute alignment is asserted per pair at load.

## Standing checks (all pass)

| Check | Result |
| --- | --- |
| Duplicate timestamps | 0 on all 9 pairs |
| Monotonic index | True on all 9 |
| NaN or non-positive OHLC | 0 on all 9 |
| Whole-minute timestamps | asserted at load, all 9 |
| Weekends with all 9 pairs present | 565 of 782 (GBPJPY starts 2015-08, NZDUSD 2011-12) |
| Weekends with ≥4 pairs | 782 of 782 |
| Reopen hour (UTC) | 21:00 (498) / 22:00 (261) / 23:00 (9) / 00:00 (13) — the DST split, identical across pairs after the calendar fix |

## Coverage caveat carried into the result

`sigma` requires 8 prior weekends, so the first ~8 weekends of each pair are
dropped (774 usable of 782 for the full-span pairs, 560 for GBPJPY). This is a
warm-up, not a time-of-day filter, and it is uniform across pairs.
