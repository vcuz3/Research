# Data audit — migration from the old vendor xlsx to Databento 1-min

**Motivation.** The old vendor ("Nearest" continuous xlsx) series had two defects the
user found: (a) the RTH hours were mis-aligned in recent years, and (b) some days
had PnL spikes from missing data. We replaced it with Databento `GLBX.MDP3`
`ohlcv-1m` continuous futures (NQ.v.0 / ES.v.0), 2011-08-01 → 2026-07-14, and
re-ran the whole pipeline. Audit script: `scripts/audit_data.py`
(report: `outputs/audit_data_report.txt`).

## Which Databento file we use, and why
We use the **RAW (unadjusted continuous)** file, not the back-adjusted-additive one:

* The strategy's economics are **intraday percentage moves** (`close/open − 1`) and
  the **session VWAP**, both computed WITHIN a single RTH session. Rolls happen at
  UTC-midnight (between RTH sessions), so no session / VWAP / trade ever spans a
  roll, and the raw within-session move is the *real contract's* true move.
* Additive back-adjustment shifts every historical price by a constant, which
  **distorts the intraday ratio** `close/open − 1` — exactly the quantity the
  Noise-Area bands are built on. Raw is therefore the faithful choice and matches
  the original "Nearest" (unadjusted continuous) methodology.
* The only raw artifact is a ~1-tick roll gap in the cross-session `prior_close` /
  daily close-to-close return on the ~60 roll days over 15y — immaterial (it moves
  a band reference or a vol-target input by <0.2% on 60/3839 sessions).

Timestamps: Databento ships a true UTC `ts_event`, so the ET session clock is
unambiguous — we convert **UTC → America/New_York directly** (DST handled by the tz
database), with no lossy Chicago round-trip and no ambiguous-hour NaT drops. This is
what structurally fixes the "hours" defect. New clean schema
(`../data/<inst>_1m_clean.parquet`): `ts_utc | symbol | open | high | low | close |
volume | is_roll` (`symbol` = underlying `instrument_id`; `is_roll` = contract change).

## New data is structurally pristine (NQ & ES, ~5.1–5.2M bars each)
* Monotonic timestamps; **0** duplicate minutes; **0** OHLC violations
  (`high<low`, `high<max(o,c)`, `low>min(o,c)`); **0** NaN; **0** non-positive prices.
* **Timezone correct in every era.** RTH (09–15h ET) volume share is 79–85% in
  2011-15, 2016-20 *and* 2021-26, peak hours 9/10/11…15 ET throughout — no recent-
  years drift.
* **No missing-data spikes.** Largest intraday gaps are the 14–15 min COVID
  circuit-breaker halts (Mar 2020) and legitimate half-day holidays (<350 bars =
  July 4, day-after-Thanksgiving, Christmas Eve). Every top-10 1-min "spike" is a
  real event (COVID crash, Apr-2025 tariffs) on contiguous bars — not a bad print.
* 3839 RTH sessions; median 390 bars/session; 3711 (NQ) / 3714 (ES) full 390-bar
  sessions; 121 short sessions (half-days). ~22k "missing" minutes total ≈ the
  half-day shortfalls, not intraday holes.

## The corpse: what was wrong with the old data (old vs new, per RTH session)
For each common session we compared the price of the bar labelled **09:30 ET**.
A timezone/hours slip shifts the whole session, so the "09:30 open" in the old
frame is a *different minute's* price. Mismatch rate by year:

| year | NQ old-vs-new 09:30 mismatch | ES old-vs-new 09:30 mismatch |
|---|---|---|
| 2011 | 24% | 16% |
| 2017 | 7% | 6% |
| 2018 | **25%** | **20%** |
| 2020 | 6% | 3% |
| 2022 | 5% | 4% |
| **2023** | 7% | **44%** |
| **2024** | 7% | **100%** |
| **2025** | 5% | **100%** |
| **2026** | 8% | **89%** |

**ES's old data had the RTH session mis-timed on essentially every day in 2024–25**
(and 44% of 2023, 89% of 2026). NQ's old data was far less broken (5–9% in recent
years, with a 2018 spike). This is a direct, quantified explanation of the memory's
long-standing puzzle — *"ES does not replicate"* — and of the recent-year decay:
the recent ES tape the strategy was being judged on was largely mislabeled bars.
NQ was mostly fine, which is why NQ replicated and ES did not.

## Consequence for the results
* NQ full-sample headline is essentially unchanged (its data was mostly clean):
  28.3%/1.31 vs the old 28.1%/1.31.
* ES full-sample moves to a clean 15.5%/**0.81** (old 17.2%/0.87) — the old ES
  number was computed partly on corrupted 2024–25 bars and should not be trusted;
  0.81 is the honest full-sample figure.
* The `engine2 == core.engine` invariant (rule 23) still holds to the digit, and
  fill-feasibility asserts (0 same-bar fills) pass on both instruments.
