# Frozen specification — trigger redundancy (RSI on top of z) and the unapplied regime filters

Written before the run. Follow-up to `RSI_COHERENCE_TIMEEXIT_SPEC.md`, same event clock,
same non-overlap rule, same compulsory stop. Two questions, one machinery.

## Motivation, stated honestly before the run

1. **`RSI_COHERENCE_TIMEEXIT_REPORT.md` applied only ONE of this project's three
   documented regime survivors** — the ATR(14)/ATR(50) same-slot expansion gate. The
   RV-percentile family (`rv_30m_pct_90d`, `rv_5m_pct_90d`) passed its own frozen
   clock-and-delay kill test in `RSI_RV_CLOCK_REGIME_REPORT.md` and has never been run
   on an event clock, nor combined with the expansion gate.
2. **The proposal to require RSI *and* `z` together has a strong prior against it**:
   measured before the run on 4.21M EURUSD minutes, **Spearman(z, RSI14) = 0.9684**,
   `P(z <= -1.5 | RSI <= 30) = 0.821`, and there are **zero** minutes where the two
   disagree on direction. So the conjunction is expected to be mostly a selectivity
   dial. That prior is recorded here so the run cannot be presented as a discovery
   either way.

## Common construction

Unchanged from `RSI_COHERENCE_TIMEEXIT_SPEC.md`: event clock (first minute the
condition becomes true), non-overlap 30 minutes, entry `open(i+1)`, exit `open(i+31)`,
compulsory stop **2.0 R with 1.0 pip slippage** (R = trailing RV(30) in pips at entry),
delays 0 and 1, era split 2021-01-01, 2012-2023 only, **2024+ sealed**.

All gate cutpoints are fitted on the **early era only** and applied unchanged to the
late era. All regime features are causal same-slot statistics estimated on the **full
minute grid**, never on the event sample (`RSI_COHERENCE_TIMEEXIT_REPORT.md` recorded
that estimating them on events populates 3.5% of signals and reconstructs the round
clock).

## The reference frontier, and why the comparison must use it

Every rule below changes **how many signals per year** it fires, and this project has
already established twice that depth alone raises profit per signal. So no arm may be
compared against another at its own natural rate.

The **`|z| >= k` sweep is the reference frontier**: `k` in
{1.0, 1.25, 1.5, 1.75, 2.0, 2.25, 2.5, 3.0}, giving (signals/year, mean R) pairs. Every
other arm is scored as

  `excess = arm mean R  -  (z-frontier mean R linearly interpolated in log signals/year
                             to that arm's own rate)`

An arm that lies **on** the frontier has added nothing except selectivity. This is the
generalisation of the rate-matching device in `RSI_THRESHOLD_FRESHNESS_SPEC.md`, and it
is declared as the primary metric for every arm here.

## Arms

**A. Trigger redundancy**

- `rsi_t` for thresholds 35/65, 30/70, 25/75, 20/80, 15/85 — does the RSI family lie on
  the `z` frontier?
- `z1.5 AND rsi30`, `z1.5 AND rsi25` — the user's proposal, requiring the same side.
- `rsi30 AND z2.0` — the mirror ordering, to check the conjunction is not just the
  deeper of its two legs.

**B. Regime filters, on the fixed `|z| >= 1.5` base**

- `+ ATR expansion top 40%` (the currently deployed gate)
- `+ rv_30m_pct_90d top 40%` (never applied on an event clock)
- `+ rv_5m_pct_90d top 40%` (never applied on an event clock)
- `+ rv_30m_pct_90d top 20%` (a deeper cut, to separate dose from presence)
- `+ ATR expansion top 40% AND rv_30m_pct_90d top 40%` (do they add?)

## Kill tests

Primary metric: **excess mean R over the interpolated `z` frontier at the arm's own
signals/year**, under the compulsory stop, delay 0, per pair.

- **An arm is SUPPORTED** if its excess is **>= +0.005 R on at least 3 of 4 pairs** with
  a median excess **>= +0.005 R**. (Base mean R at this stop is about 0.034, so +0.005
  is a ~15% relative improvement — small enough to be reachable, large enough to matter.)
- **An arm is REJECTED as a selectivity dial** if its median excess falls within
  **±0.005 R** of the frontier.
- **An arm is REJECTED outright** if its median excess is **<= -0.005 R**.
- Any supported arm must **also** retain a positive excess at **delay 1** and a positive
  excess in the **late era**, or it is recorded as supported-but-fragile and not
  promoted.

Reported alongside, not as criteria: mean pips and the implied risk unit
(`mean_pips / mean_R`) for every arm, per `LEARNINGS.md` 2026-08-04 — an arm whose pips
and R rankings disagree is reported as a risk-unit difference, not an edge difference.

## Out of scope

- No null is run (rule 17). The frontier interpolation is the degenerate control and
  this is declared, not discovered.
- The bid/ask spread remains unmeasured; no net tradability claim is permitted.
- 2024+ is not opened.
