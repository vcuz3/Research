# Data Quality

Authoritative executable report:
`../artifacts/runs/EXP-0003/data_quality.json`; minute coverage is in
`coverage_by_minute.csv` in the same directory.

## NQ minute source

- 5,094,910 rows from 2011-08-01 through 2026-07-14 UTC.
- Zero duplicate timestamps, out-of-order rows, or invalid OHLC rows.
- 61 contract segments and 61 roll flags.
- 3,831 exact 18:00 rows and 3,839 exact 09:30 rows.
- There are 109,146 gaps longer than one minute in the sparse traded-bar source;
  many occur during scheduled closures or quiet older periods, so this raw count
  is reported rather than interpreted as missing tradable bars.

## Daily and trade construction

- 3,839 RTH sessions; median 390 bars.
- 128 sessions have fewer than 390 RTH bars; 121 lack 15:59, largely shortened
  sessions. The last observed RTH close is used and remains known before 18:00.
- 3,821 entry/exit anchor pairs matched. Sixty crossed a continuous-contract
  roll and were excluded, leaving 3,761 valid executions.
- No matched pair had the wrong 15.5-hour holding duration.
- 2,008 valid pairs have at least one unprinted minute inside the window. The
  median window has 930 of 931 possible anchor-inclusive minutes; the worst has
  169 rows (trade date 2020-03-16). No internal price is used or imputed because
  the strategy depends only on exact endpoint opens, but the worst gaps should
  be independently checked against granular source condition data.

## Rolling features and VIX

- Strict warm-up removals: SMA5/10/20/50/100/200 remove 4/9/19/49/99/199 early
  daily rows; ATR14 removes 14; ATR14 sizing removes 74; prior-day-ATR sizing
  removes 61.
- Daily VIX has 4,261 unique, ordered, valid rows from 2009-10-14 to 2026-08-21.
- All 3,821 matched candidates found an NQ daily feature and VIX close inside
  the four-day bound. Most joins use the same calendar date or prior Friday.
- VIX rolling reference has 60 expected warm-up nulls and is strictly lagged.

## Verdict

The exact anchors and causal features have adequate coverage for this endpoint
study. Internal sparse-bar gaps are visible and non-load-bearing for arithmetic,
but remain a review item before any stronger execution claim.

## LSE tiles used by EXP-0005

- Two non-overlapping files combine to 3,556,402 unique, ordered rows from
  2016-05-29 through 2026-08-12, with zero invalid OHLC rows.
- There are 2,587 exact entry anchors, 2,620 exact exit anchors, and 2,576
  matched 15.5-hour candidates.
- SMA200 is unavailable on 159 candidate dates; 2,417 post-warm-up observations
  remain, of which 1,991 pass the entry-price gate.
- The constant `NQ.F` identifier supplies no roll map. Roll-crossing exclusion
  is therefore impossible on this source.
- 756 candidates have an internal unprinted minute; median coverage is the full
  931 anchor-inclusive minutes.
- The only open/prior-close link above 5% follows a source outage from
  2020-03-01 23:59 UTC to 2020-03-03 14:40 UTC. No exact candidate bridges it.

Executable evidence: `../artifacts/runs/EXP-0005/data_quality.json` and
`coverage_by_minute.csv`.
