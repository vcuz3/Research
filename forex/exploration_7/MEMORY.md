# exploration_7 — FX weekend gap reversion

**State (2026-08-12): CLOSED, NO-GO as a tradable edge.** Both runs complete,
reports written, ledger current. Reviews are `pending` independent review.

## Position

The question: an earlier AUDJPY study reported that weekend gaps beyond some
size revert toward the gap. Tested on 9 pairs (EURUSD, AUDUSD, GBPUSD, NZDUSD,
USDJPY, AUDJPY, NZDJPY, EURJPY, GBPJPY), 782 weekends, 2011-07..2026-07.

**Answer: the claim does not replicate as stated, and the real effect
underneath it is not tradable.**

| | |
| --- | --- |
| Preregistered test (k=1.5, 1-day) | **FAIL** — mean R +0.531, clustered t +1.85 (bar was t≥2) |
| AUDJPY at 1 day | +0.692 sigma, t 1.35, n=88 — indistinguishable from zero |
| What is real | **1-hour** reversion: +0.292 sigma, t +4.22, **9/9 pairs positive**, hit rate 62.4% |
| Selection-aware null | Decisive: real max\|t\| 5.94 vs null p95 2.86, frac(null≥real) **0.0000** |
| Why NO-GO anyway | not weekend-specific + inside the spread + era-unstable |

Three disqualifiers, any one sufficient:

1. **Not weekend-specific.** A weeknight-break placebo at the same clock carries
   62% of it (+0.181 vs +0.292) and *exceeds* it at H=240. The mechanism is a
   noisy print across any thin session boundary, not weekend news.
2. **Inside the spread.** Pooled gross +3.97 pips; break-even round-trip ~4 pips
   (k=1.5) / ~5 (k=2.0). Net at a 1× reopen-range charge: 5/9 pairs positive;
   at 2×: 1/9. Gross ≈ modeled cost ⇒ Rule 20.
3. **Era-unstable.** 2019–22 +0.126 (t 1.06), 2011–14 +0.150 (t 1.36); carried
   by 2015–18 and 2023–26.

Also: the effect loses 44% of its size between a 1-min and a 60-min entry delay
(real effect + a boundary-noise component); the 4-hour cell **inverts** under a
60-min delay and is not robust at all.

## Do not redo

* Deeper thresholds (k≥2.5 loses significance as n falls), longer horizons
  (noise), per-pair selection (fitting the 9/9 table).
* The market-order form of this trade in any variant. The reopen spread is the
  binding constraint, not the signal.

## The one live variant

A **passive** version: the effect is that the reopen print is noisy, so paying
the reopen spread to trade it is self-defeating. A limit resting from before
Friday's close, at a level the reopen must gap through, earns the spread rather
than paying it. Blocked on data — needs L1 quotes at the reopen to model the
queue (Rule 4). Do not attempt on mid OHLC.

## Data caveat that outlived the study

`data/USDJPY_1m.parquet`, `data/NZDJPY_1m.parquet`, `data/EURJPY_1m.parquet`
carry **synthetic weekend bars** in 2021–2023 (NZDJPY: 181,699 Saturday bars,
uniform across all 24 hours; weekday bars rise to exactly 1440/day). Any study
touching session boundaries on those three files must impose an external
session calendar. The six other archives are clean. Full detail and the fix:
`reports/DATA_QUALITY.md`. This is now also a `LEARNINGS.md` entry.

## Where things are

| What | Path |
| --- | --- |
| Preregistration + kill test | `experiments/hypotheses/HYP-0001.md` (frozen before any outcome) |
| Result synthesis | `reports/FINDINGS.md` |
| Rule 9a gate | `reports/DATA_QUALITY.md` |
| Preregistered run | `artifacts/runs/EXP-0001/` |
| Discovery follow-up + review | `artifacts/runs/EXP-0002/review.md` |
| Library | `_gap_lib.py` (loading, break detection, event build) |
| Runners | `_run_data_quality.py`, `_run_gap_study.py`, `_run_gap_followup.py` |

## Corrections carried

EXP-0001 shipped two defective controls, both fixed in EXP-0002 and both
documented in `reports/FINDINGS.md`. Neither changed its verdict:

1. Its MDE gate injected an effect on top of the real one and declared
   detection when real+injected cleared t=2 (reported 0.05 sigma; the true MDE
   at 1 day is ~0.58 sigma, *larger* than the observed effect).
2. Its entry-delay control anchored exits at reopen+h, so delaying entry
   shortened the hold — at H=60, d=60 the trade had zero duration.

**Use EXP-0002's retention numbers, not EXP-0001's.**
