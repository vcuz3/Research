# EXP-0004 Results Discussion

- Hypothesis: `HYP-0003` — Continuous (every-bar) stop transfers the NQ GO uplift to GC
- Status: completed
- Builder: claude
- Reviewer: unassigned
- Primary metric: per-day-clustered **net daily Sharpe** and **net day-$ t-stat**
- Kill test: Every-bar stop does not raise net daily Sharpe over the decision-clock
  baseline by >=+0.05, OR raises Sharpe only by inflating gross, OR the uplift fails
  a claim-matched Null-C.
- Verdict: **REJECTED — the NQ GO result does NOT transfer; it INVERTS on GC.**
- Data: GC RTH 2011-08-01..2026-07-16, 3647 sessions, `data/GC_1m_clean.parquet`.
- Reproduce: `python -m futures.gc.noise_vwap.scripts.hyp_0003_continuous_stop GC 90`.

## Result versus hypothesis

The hypothesis (ported from the NQ GO result) was: continuous stop = **same gross,
higher net Sharpe** via cutting losers sooner. On GC the opposite happens — gross
**collapses** and net Sharpe falls hard. Headline @ 0.50 tick/side:

| metric | decision (baseline) | every_bar (continuous) | delta |
| --- | --- | --- | --- |
| gross pt/trade | +0.3586 | +0.1265 | **−0.2321 (−65%)** |
| net pt/trade | +0.2136 | −0.0185 | −0.232 |
| net daily Sharpe | **+0.46** | **−0.06** | **−0.52** |
| net day-$ t | +1.25 | −0.17 | −1.42 |
| n_trades | 2641 | 3806 | +44% |

Every kill-test clause fires: net Sharpe does not rise (it drops −0.52, vs the
+0.05 target), and the change is NOT same-gross — gross itself is destroyed. This
is a clean NO-GO on the real pass alone.

Per the standing gate (memory `gate-nullc-on-success-metric`): the real pass fails
the primary metric decisively, so the claim-matched Null-C was **NOT run** — a
failing real pass is already a REJECT and the null would only be spent to describe
a dead effect.

## Gross, net, baseline, and null comparison

Net across the cost grid (both variants), decision → every_bar net daily Sharpe:

- 0.25 tick: 0.57 → 0.11
- 0.50 tick: 0.46 → −0.06
- 1.0 tick: 0.24 → −0.40

The every_bar variant is worse at every cost level and net-negative from 0.50 tick.
Gross (no cost): decision Sharpe 0.77 (day-$ t +2.11) vs every_bar 0.43 (t +1.16).

## Regimes, sensitivity, and alternative explanations — WHY it inverts

The loser-tail diagnostic confirms the every_bar stop *did* do what it does on NQ —
it cut the loser tail — but on GC that came at a fatal cost to the winners:

| | decision | every_bar |
| --- | --- | --- |
| reasons | stop 1779 / eod 857 / flip 5 | stop 3119 / eod 687 |
| stop_frac | 0.674 | **0.819** |
| worst loser (pt) | −87.9 | −81.0 |
| p05 net (pt) | −7.85 | −5.35 |
| loser mean ($) | −329.8 | −197.2 |
| long gross pt | +0.477 | +0.260 |
| short gross pt | +0.233 | **−0.015** |

The left tail shrank (loser mean −$330 → −$197, stop_frac 0.67 → 0.82), exactly the
NQ mechanism. But gross per trade fell 65% and the **short leg gross went to zero**,
because checking the band/VWAP stop every minute stops good trades out on transient
intraday pokes back through VWAP *before* the (already tiny) drift they ride
materializes. Entries still fire only on the 30-min clock, so after a premature
every-bar stop the strategy sits flat until the next :29/:59 and cannot re-enter —
the +1165 extra trades are mostly premature exits, not new opportunities.

Interpretation: the 30-min clock's *looseness* is load-bearing on gold. NQ's
intraday drift dominates its noise, so a tighter exit check harvests the same gross
with less variance. GC has **no positive intraday drift** and is noise-dominated at
the minute scale, so the same tightening is pure whipsaw — it clips winners more
than it saves losers. This is fully consistent with the existing GC verdict (real-
but-tiny, cost-fragile edge that tightening destroys) and with EXP-0002 (the edge
lives only in the equity cash session, riding a weak shared-drift signal that needs
room to develop).

## Artifact and implementation risks

- Single-variable change: `exit_check="decision"` → `"every_bar"` in
  `core.engine.run`; no other parameter touched. `noise_bands` already emits a band
  at every tod, so the every-bar branch has a valid stop reference each minute (not
  a carry-forward artifact).
- Fill feasibility asserted in-script: 0 same-bar fills in BOTH variants (all fills
  next-open, rule 1/2). The gross collapse is not a fill artifact — it is genuine
  premature exits at honest next-open prices.
- Trades persisted: `trades_decision.parquet`, `trades_everybar.parquet`.

## Builder interpretation

REJECT the transfer. Continuous stop is an adopted GO on NQ and a clear NO-GO on GC;
the result inverts because of the instrument's noise/drift ratio, not a bug. This is
a useful negative result: exit-timing granularity that helps a drift-dominated index
future actively harms a noise-dominated commodity future with no intraday drift.
Keep GC on the decision-clock stop. Do not tune the exit clock on consumed history
(Rule 26). The GC standalone verdict is unchanged (NO-GO); this closes the
continuous-stop idea and points remaining effort at the portfolio-leg question.

## Independent review

- Review status: pending (builder = claude; reviewer unassigned)
- Objections: pending
- Verdict: REJECTED (builder); awaiting independent confirmation

## Promotion decision

- `reports/FINDINGS.md`: record as a rejected transfer (negative evidence, Rule 25).
- `MEMORY.md`: updated — HYP-0003/EXP-0004 REJECTED, continuous stop inverts on GC.
- Shared `LEARNINGS.md`: **PROMOTED 2026-07-19** — exit-timing granularity value
  scales with the intraday drift/noise ratio. Confirmed on the third instrument the
  same day: ES continuous stop is a WASH (net Sharpe 0.928→0.920, −0.008;
  `futures/nq/noise_vwap/scripts/es_continuous_stop.py`), sitting between NQ's uplift
  (+0.145) and GC's inversion (−0.52). Gross drops ~30% on all three; only whether
  winners can afford the tighter leash differs.
