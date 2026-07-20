# GC Noise-Area + VWAP — Data-Quality Report (rule 9a)

Executable gate: `python -m futures.gc.noise_vwap.scripts.data_quality GC 90`.
This report is the mandated data-quality test for the data-load / feature-
construction stage (RULES.md rule 9a). It exists because a silent
feature-construction defect (below) was found only by manual inspection of a
single session, and must never again hide inside the band construction.

Data: Databento `GC.v.0` raw continuous 1-minute, 2011-08-01 → 2026-07-16,
built to `data/GC_1m_clean.parquet`. 3647 usable RTH sessions (≥350 bars).

## Timeline integrity — clean

- Duplicate `(date, tod)` rows: **0**.
- Out-of-order bars within a session: **0**.
- Sessions spanning >1 contract symbol (intra-session roll): **0** (rule 11 OK).
- RTH completeness: full session = 390 minutes; **median present = 390**;
  479 sessions (13.1%) miss ≥1 minute; mean missing = 0.43/session, max = 39.
  Missing minutes are genuinely no-trade minutes (thin GC electronic afternoon),
  not a build error — raw per-minute coverage is ~100% (see below).

## The defect this gate surfaced — strict noise-band `min_periods`

The same-time-of-day noise band uses
`sigma[date, tod] = mean over the prior 90 sessions of |close/open − 1|`.
The original construction (verbatim NQ port) built it with
`rolling(90, min_periods=90)`, which requires **all 90** prior sessions to have a
bar at that exact minute. A single missing minute anywhere in the trailing
window nulled the band for that `(date, tod)`, and the engine **skips a decision
bar whose band is undefined** (`engine.py:108`). This is invisible on liquid NQ
(every RTH minute is present) but bites hard on GC's thinner post-COMEX-floor
(13:30 ET) afternoon.

Per-decision-minute coverage — RAW coverage is ~100% everywhere, but the STRICT
band coverage collapses in the afternoon; the relaxed rule
(`min_periods = ceil(0.90 × 90) = 81`, mean taken over the present prior
sessions) restores a uniform ~97.8% that no longer depends on time-of-day:

| decision (ET) | raw cov | strict band | relaxed band | decisions recovered |
| --- | ---: | ---: | ---: | ---: |
| 09:59–11:59 | 100% | 97.5% | 97.8% | +9 each |
| 12:29 | 99.9% | 90.1% | 97.8% | **+279** |
| 13:59 | 100% | 95.1% | 97.8% | +99 |
| 14:29 | 99.9% | 88.9% | 97.8% | **+322** |
| 14:59 | 99.9% | 88.1% | 97.8% | **+353** |
| **15:29** | 99.6% | **72.2%** | 97.8% | **+934** |
| 15:59 | 100% | 95.1% | 97.8% | +99 |

**Total: +2,149 decision points recovered.** The strict rule was deleting up to
**28% of the 15:29 decisions** despite 99.6% raw coverage — a hidden,
time-of-day-dependent filter on the strategy's latest (and short-heavy) signals.

### Worked example — 2026-07-07

Price was below VWAP and the lower band from ~15:00 ET, but no short was taken
until 15:30. Cause: the 14:59 decision bar's band was `NaN` because one session
in the trailing 90 (2026-03-27) lacked a 14:59 bar (89/90 present). The engine
skipped 14:59 and only fired at 15:29 → fill 15:30. Under the relaxed rule the
14:59 band is defined (upper 4204.19 / lower 4149.12) and the short is taken at
the 15:00 open (+12.8 pt to EOD), as intended.

## Fix

`core/data.py` and `core/session.py` now build sigma with
`min_periods = ceil(BAND_MIN_FRAC × lookback)`, `BAND_MIN_FRAC = 0.9`. The change
is causal (still `move.shift(1)`, still only the prior `lookback` sessions;
`rolling.mean()` already averages over present sessions only) and identical in
both the audited engine and the numba fast path (parity re-verified: 2692
trades, gross 974.60 pt, both paths). Revised baseline: see `reports/BASELINE.md`
and `artifacts/runs/EXP-0005/`.

## Verdict

No lookahead, no fill artifact, no accounting error — the defect was
**conservative** (it deleted signals). It did not create the edge and does not
overturn the standing NO-GO. But it silently under-sampled the late-session leg
by up to 28%, so any prior interpretation of intraday timing / time-of-day
behaviour on GC was made on a thinned, time-of-day-biased sample. The revised
baseline is the correct reference going forward.
