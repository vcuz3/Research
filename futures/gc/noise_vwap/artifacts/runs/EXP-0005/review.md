# EXP-0005 — Data-quality fix: relax noise-band `min_periods`; revised baseline

- Phase: data-quality fix + revised baseline
- Date: 2026-07-19
- Builder: claude
- Trigger: user found that on 2026-07-07 price was below the band and VWAP from
  ~15:00 ET but no short was taken until 15:30. Investigation traced it to the
  noise-band construction, not the decision clock.

## Change (single variable)

`core/data.py::noise_bands` and `core/session.py::_base_bands` built the
same-time-of-day sigma with `rolling(lookback, min_periods=lookback)`, requiring
**all** `lookback` prior sessions to have a bar at that exact minute. One missing
minute in the trailing window nulled the band, and the engine skips a decision
bar with no band → the late-day signal was silently under-sampled on GC's thin
afternoon (invisible on liquid NQ). Changed to
`min_periods = ceil(BAND_MIN_FRAC × lookback)` with `BAND_MIN_FRAC = 0.9`; the
mean is taken over the present prior sessions. Causal (still `move.shift(1)`,
still only prior `lookback` sessions). Rule 9a data-quality gate added:
`scripts/data_quality.py` → `reports/DATA_QUALITY.md`.

## Evidence

- `data_quality.txt`: **+2,149 decision points recovered**; strict rule was
  deleting up to **28% of 15:29** decisions at 99.6% raw coverage. Band coverage
  now uniform ~97.8% across all decision minutes (was 72–97.5%, time-of-day
  dependent). Timeline clean: 0 dup, 0 out-of-order, 0 intra-session rolls.
- `revised_baseline.txt`: full revised baseline run.
- Parity re-verified: `core.engine` vs `core.engine2`+numba both give 2692
  trades / gross 974.60 pt (bit-exact) under the relaxed bands.
- 2026-07-07 check: 14:59 band now defined; short taken at 15:00 open (+12.8 pt
  to EOD), as the user expected.

## Result — baseline moves slightly UP; verdict unchanged (NO-GO)

| Metric (0.50 tick/side) | old baseline (EXP-0000) | revised (EXP-0005) |
| --- | ---: | ---: |
| trades | 2641 | 2692 (+51) |
| band rows | 1,286,032 | 1,390,739 |
| gross pt/trade | +0.359 | +0.362 |
| net pt/trade | +0.214 | +0.217 |
| day $ net (1 ct) | +30.2 | +31.0 |
| day-net t | +1.25 | +1.30 |
| net daily Sharpe | 0.46 | 0.48 |
| gross daily Sharpe | 0.77 | 0.79 |
| gross day-$ t | +2.11 | +2.17 |

Long/short (net pt, 0.50 tick): L +0.326 (1382) / S +0.102 (1310) — the recovered
decisions are afternoon/short-heavy, and the short leg improves (+0.088 → +0.102).
Always-long drift control unchanged (−0.084 pt, Sharpe −0.10). Fill feasibility:
0 same-bar fills.

## Interpretation

The defect was **conservative** (deleted signals, no lookahead / fill / accounting
error), so it did not create the edge; correcting it nudges every metric up but
the strategy remains economically inert (net t≈1.3, and EXP-0001's vol-target
result — Sharpe 0.07 — is the binding NO-GO). The material point is a *methodology*
one: prior GC intraday-timing / time-of-day interpretations were made on a
late-session sample thinned by up to 28% in a time-of-day-dependent way. This is
now the frozen reference baseline; EXP-0000 numbers are superseded.

Note (not re-run here): EXP-0001–EXP-0004 all used the strict-band construction.
Their conclusions are directionally safe (the change is small and the verdicts are
REJECTs/NO-GO with margin), but any *future* re-open of those questions must
rebuild on the relaxed bands. Flagged in MEMORY.md.

## Review status

- Verdict: **ACCEPTED as revised baseline.** Bug fix, single variable, parity and
  causality preserved, data-quality gate committed.
- Reviewer: unassigned (independent review still open, as for EXP-0000–0004).
- Objections: none outstanding. Open item: BAND_MIN_FRAC = 0.9 is a chosen
  threshold; 97.8% uniform coverage confirms it is not sensitive at the margin
  (the residual 2.2% is warmup / current-day-minute, not the tolerance).
