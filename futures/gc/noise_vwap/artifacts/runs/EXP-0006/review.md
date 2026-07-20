# EXP-0006 review — HYP-0004 exit system (partial-TP + looser clock) on GC

- Builder: claude
- Reviewer: claude
- Date: 2026-07-19
- Verdict: **REJECTED** (real pass sub-threshold; Null-C not run, per gate)
- Hypothesis: `experiments/hypotheses/HYP-0004.md`
- Run: `python -m futures.gc.noise_vwap.scripts.hyp_0004_exit_mgmt real`
- Frozen baseline: EXP-0005 (relaxed bands, 2692 trades, gross +0.362 / net +0.217
  pt/trade @0.50tick, net Sharpe 0.475, net day-$ t=+1.30).

## Setup

Single-variable EXIT changes on top of the frozen baseline; entries (30-min
Concretum clock + VWAP gate), bands (lookback 90, k=1.0), and honest next-open
fills identical across all variants. Engine `core/engine2.py`; **parity asserted to
the digit** vs the audited `core/engine.py` at (30-min clock, decision stop, no TP):
n=2692, gross_pt agree. Primary metric: per-day-clustered net daily Sharpe @0.50
tick; gross reported alongside (rule 20). Fill-feasibility: 0 same-bar fills in
every variant; TP next-open-vs-signal-close artifact +0.009…+0.016 pt (small, and
next-open is the conservative side).

Note: fixed a pre-existing broken data path — the GC parquet had been relocated to
the shared instrument parent `futures/gc/data/` (per RESEARCH_WORKFLOW) but
`core/data.py` and `core/session.py` still pointed at the missing `noise_vwap/data`.
Repointed both to `parents[2]/data`. Data content unchanged; baseline parity
re-confirmed, so no effect on prior results.

## Results (net daily Sharpe @0.50 tick, 3566 sessions incl. zero-trade days)

| variant | n | win% | grossPt | netPt | netSh | dΝetSh | day-$ t |
|---|---|---|---|---|---|---|---|
| **baseline_30** | 2692 | 33.6 | +0.3620 | +0.2170 | +0.475 | — | +1.30 |
| tp0.75_50 | 2692 | 34.0 | +0.3493 | +0.2043 | +0.468 | −0.007 | +1.28 |
| tp0.75_67 | 2692 | 34.0 | +0.3449 | +0.1999 | +0.461 | −0.014 | +1.26 |
| tp1.0_50 | 2692 | 33.8 | +0.3655 | +0.2205 | +0.493 | +0.018 | +1.35 |
| tp1.0_67 | 2692 | 33.8 | +0.3667 | +0.2217 | +0.498 | +0.023 | +1.36 |
| tp1.25_50 | 2692 | 33.7 | +0.3687 | +0.2237 | +0.489 | +0.014 | +1.34 |
| tp1.5_50 | 2692 | 33.6 | +0.3748 | +0.2298 | +0.496 | +0.021 | +1.36 |
| clock_60 | 1893 | 36.8 | +0.2905 | +0.1455 | +0.258 | −0.217 | +0.65 |

Deltas are stable across the 0.25/0.50/1.0-tick cost grid (partial-TP band
d≈+0.01…+0.03; clock_60 d≈−0.18…−0.24).

## Interpretation

1. **Kill test met → REJECT.** The best exit variant (tp1.0_67 / tp1.5_50) lifts net
   daily Sharpe by only **+0.023 / +0.021**, below the pre-declared **+0.05** gate.
   Per `gate-nullc-on-success-metric` a real pass that fails the primary metric is
   already a REJECT, so the claim-matched Null-C was **not** run.

2. **But partial-TP is BENIGN on GC — the mechanism thesis is directionally
   confirmed.** This is the important qualitative contrast with EXP-0004: the
   continuous stop *inverted* (gross +0.359→+0.127, −65%; net Sharpe +0.46→−0.06)
   because tightening the runner's stop clips winners on a no-drift tape.
   Partial-TP does the opposite — it *banks* the favourable extension and lets the
   runner keep the loose decision-clock stop — so gross is **held or nudged up**
   (+0.362→+0.375 at tp1.5_50) and win% rises 33.6→34.0. The HYP-0004 premise (that
   an extension-banking exit is aligned with gold's give-back, unlike stop-
   tightening) is borne out in sign; it is simply **too small to clear the bar**.

3. **The tp ordering INVERTS vs NQ — consistent with gold needing more room.** On
   NQ the tightest TP was best (tp0.75_67 top of the plateau). On GC the tightest TP
   (tp0.75) *hurts* (−0.007…−0.014) and value only appears at tp≥1.0, rising to
   tp1.5. Banking too early on gold forfeits the move; you must let it run ~1–1.5
   ATR first. Same theme as EXP-0004 / the 60-min result — gold's minute-scale
   moves want a looser leash, not a tighter one.

4. **Looser clock (60 min) is harmful, not helpful.** EXP-0004's "the 30-min clock's
   looseness is load-bearing" does **not** extrapolate to "looser is better": the
   60-min clock halves net Sharpe (0.475→0.258) and enlarges the average loser
   (−3.24→−3.92 pt) because the delayed stop check admits bigger adverse excursions.
   30 min sits near a local optimum; both directions (continuous / 60-min) are worse.

## Caveats / scope

- All GC history is consumed; a sub-threshold-but-positive partial-TP is a paper
  observation, not deployable, and is moot under the standing EXP-0001 sizing NO-GO
  (vol-target Sharpe 0.07). Not tuned further (tp2.0+ would only approach baseline);
  extending the grid would be fishing on consumed history (rule 26).
- tp_atr/tp_frac are a-priori params carried from NQ, not fit to GC.

## Artifacts

`trades_{baseline_30,tp0.75_50,tp0.75_67,tp1.0_50,tp1.0_67,tp1.25_50,tp1.5_50,clock_60}.parquet`
in this directory.
