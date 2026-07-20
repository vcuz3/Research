# NQ Data-Quality Gate — Continuous Stop (RULES.md rule 9a)

Reproduce: `python -m futures.nq.noise_vwap.scripts.data_quality NQ 90`
Source: `scripts/data_quality.py` · Run date: 2026-07-19 · Data through 2026-07-14.

## Why this exists

`core/data.py:96` builds the noise band with `rolling(90, min_periods=90)` —
strict: every one of the prior 90 sessions must have a bar at that exact minute
or the band is null for that `(date, tod)`. On GC this silently deleted up to 28%
of late-day decisions (`futures/gc/noise_vwap/reports/DATA_QUALITY.md`). The
shared learning predicted NQ "barely bites" because it is liquid; this gate
quantifies it, and does it for the surface the **continuous (every-bar) stop**
actually touches.

The continuous stop widens the rule-9a surface: `engine.simulate_session` does
`band = band_map.get(t); if band is None: continue` (`engine.py:108-110`). With
`exit_check="every_bar"` the stop is checked at **every** RTH minute a position
is open, so a strict-nulled band at any intermediate minute silently **skips the
stop check there** — the position rides to the next valid-band minute unprotected.
Relevant coverage is therefore all RTH minutes 09:59–15:58, not just the 12
entry decision tods.

## Findings (NQ, 3,718 sessions, 2011-08-01 → 2026-07-14)

| Check | Result |
| --- | --- |
| Duplicate `(date,tod)` | 0 |
| Out-of-order bars within a session | 0 |
| Sessions spanning a contract roll | 0 |
| Sessions with ≥1 missing RTH minute | 7 (0.2%), max 14 missing; median session complete (390/390) |
| Raw per-minute coverage | 100.0% at every entry tod |

**Band coverage — the rule-9a bite is small and conservative:**

- Uniform **warm-up floor** of 2.4% across every tod = the first ~90 sessions
  have no band yet (90/3718 ≈ 2.4%). Not a defect: entries also need a band, so
  no position is open then and nothing is skipped.
- **One genuine trailing-window gap bite:** 12:59 ET (tod 779) strict coverage
  95.2% vs 97.8% for the neighbours — an **extra 2.4%** of 12:59 entries nulled
  because a single missing minute in the trailing 90-session window (concentrated
  in the thin ~12:56–12:59 lunch patch) nulls the whole band cell. Relaxing to
  `min_periods = ceil(0.9·90) = 81` recovers **+207 entry decisions** total and
  levels all tods to a uniform 97.8%.
- **Continuous-stop skip:** genuine gap-nulls (history exists, strict window has
  a hole) affect **0.38% of live band cells** (4,950 bar-minutes), concentrated
  at lunch. The 2.55% figure that includes warm-up is an upper bound and not a
  real skip.

## Verdict

NQ passes the gate. Timeline integrity is perfect and completeness is 99.8%.
The strict `min_periods` defect that severely bit GC is present but **barely
bites NQ**: one lunch-hour minute (12:59) loses an extra ~2.4% of entries and
the continuous stop skips ~0.38% of live checks, both **conservative** (delete a
signal / skip one stop-check bar; no lookahead, no fill inflation), so neither
inflates the edge. It does under-sample the 12:59 slot and would corrupt any
time-of-day interpretation there.

**Recommendation:** if the continuous stop is relied on into the lunch window, or
any 12:59-specific claim is made, switch `core/data.py` to
`min_periods = ceil(0.9·lookback)` (still causal, `move.shift(1)`), which the GC
core already uses (`BAND_MIN_FRAC`). Otherwise the bite is immaterial to the
aggregate NQ result and can be left as a documented, quantified limitation.
