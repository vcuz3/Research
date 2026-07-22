# EXP-0024 — Symmetric overnight-gap MAGNITUDE whole-day veto (HYP-0015)

Builder: Claude (Opus 4.8). Date: 2026-07-21. Consumed historical sample.

## Change tested

User idea: instead of the previously-tried gap/RVOL **scaling** (EXP-0017,
rejected), just **don't trade** on a gapped day — a hard symmetric magnitude
gate. Per day: `gap_atr = |rth_open - prior_close| / atr_pts` (all causal). Skip
EVERY entry that day if `gap_atr > T`, T ∈ {0.50, 0.75, 1.00, 1.50, 2.00} ATR.
Frozen baseline = NQ/ES continuous-stop (lb90, RTH, 30-min, VWAP gate, every-bar
stop, next-open fills). Primary: family-max daily Sharpe uplift + net-R gate.

Distinct from prior gap work: symmetric in gap sign (not gap-vs-signal), no RVOL
term, whole-day (not per-signal). Mechanism claim: a big gap mis-anchors the
same-slot band / VWAP the breakout is measured against.

Implementation note (verified in code): a whole-day skip is EXACTLY equivalent to
dropping that day's trades from the ungated baseline, because sessions are
independent (each flattens at the close, no cross-day state). `_verify_equivalence`
asserts the engine `entry_gate` path and the trade-filter path are trade-for-trade
identical at T=1.0 (assert passed). All sweeps/nulls therefore filter the frozen
baseline trade set — no per-cell engine re-runs.

## Result — REJECT on both markets, and it fails INVERTED

Every threshold LOWERS both net R and daily Sharpe, monotonically (skip more →
lose more), on NQ and ES:

| T | NQ days skip | NQ dSumR | NQ dSharpe | ES days skip | ES dSumR | ES dSharpe |
|---|---|---|---|---|---|---|
| 0.50 | 971 (26.8%) | −32.95 | −0.245 | 1039 (28.6%) | −27.49 | −0.498 |
| 0.75 | 430 | −18.57 | −0.155 | 486 | −10.85 | −0.137 |
| 1.00 | 194 | −14.35 | −0.152 | 224 | −6.19 | −0.077 |
| 1.50 | 47 | −4.61 | −0.043 | 57 | −7.43 | −0.124 |
| 2.00 | 17 | −1.44 | −0.019 | 17 | −1.86 | −0.030 |

Baseline: NQ Sharpe 1.7175 / netR 91.20 (4209 trades); ES 0.4892 / 27.15 (4326).
The family-best cell (T=2.0, barely skips anything) is still net-negative. Real
gate (dSharpe ≥ +0.10 AND netR ≥ base): **REJECT** on both. No Null-C spent
(standing rule: real pass fails the primary metric).

### Why it fails — gap days are the BEST days for a breakout system

- **Removed trades are PROFITABLE.** NQ removed-trade mean R +0.206 vs kept
  +0.021; the removed *early* (≤ mfo 149) trades average **+0.367 R** — the most
  profitable slice of the tape. The anchor-contamination mechanism is not absent,
  it is **inverted**: a large overnight gap is a strong directional open the
  momentum breakout RIDES, not mis-sized noise. (ES aggregate the same: removed
  +0.124 > kept +0.006; its early/late split differs from NQ — early −0.257 /
  late +0.378 — so the "early-slot contamination" sub-prediction does not even
  reproduce on the sibling, further killing the mechanism.)
- **Worse than a random drop (anti-selection).** Matched-count random-day-drop
  null (200 draws, drop the same k days at random): random dSumR mean ≈ −0.49
  (NQ) / −0.15 (ES) ≈ neutral, but the real gap-gate dSumR (−1.44 / −1.86) sits
  at frac(random ≥ real) = **0.805 (NQ) / 0.870 (ES)** — random dropping beats
  the gap gate ~80–87% of the time. The gap gate is not merely a rarity filter
  (Sharpe-neutral exposure cut); it is *anti*-selection, systematically removing
  better-than-average days.
- **Gross/trade barely moves** (NQ 3.51 → 3.51–3.65) while net R collapses — the
  loss is purely from deleting profitable *days*, confirming the removed days
  carry the strategy's directional pay, not excess cost or noise.

## Verdict

Cross-market NO-GO. A symmetric overnight-gap magnitude gate degrades the
continuous-stop baseline at every threshold on both NQ and ES, because a large
gap is a directional-conviction signal this momentum family already monetizes
(cf. EXP-0022: the up/down band asymmetry is drift the strategy already rides;
gating on it double-counts). Same theme as the volatility-independence finding —
gap size is orthogonal-to-adverse for the edge, so gating on it is anti-selection.
Retain the unconditioned baseline; do not trade a gap veto in any direction.

Artifacts: `real_sweep_{NQ,ES}.csv`, `random_day_null_{NQ,ES}.csv`,
`removed_by_slot_{NQ,ES}.csv`, `verdict_{NQ,ES}.json`. Reproduce:
`python -m futures.nq.noise_vwap.scripts.hyp_0015_gap_magnitude_veto real {NQ|ES}`.

Metric caveat: `score()` daily Sharpe is over trade-days only (zero-trade
eligible sessions excluded), so the absolute Sharpe (1.72) is higher than the
canonical zero-day baseline (~1.29); the DELTA sign and the net-R result are
accounting-independent and unambiguous.

## Review

- Reviewer: unassigned (pending independent review)
- Decision: REJECT (builder); cross-market, inverted mechanism, no Null-C owed.
