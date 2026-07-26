# EXP-0033 Results Discussion

- Hypothesis: `HYP-0023` — Selection-corrected fast Null C reproduces the reference and the one-minute execution proxy agrees with exact one-second minute-block null replay.
- Status: completed — implementation PASS; selection-corrected Null C confirms
  the EXP-0032 NO-GO
- Builder: Codex
- Reviewer: unassigned
- Primary metric: Exact reference parity, family-max Null-C p, one-minute versus one-second paired uplift error, and wall-clock speedup
- Kill test: Fast one-minute seeded daily PnL must match reference within 1e-10; exact one-second paired uplift must be within 0.03 Sharpe per draw and mean absolute difference <=0.02.

## Result versus hypothesis

All frozen implementation gates passed.

- `null_c_returns_fast` is bit-exact to the readable reference for OHLC, volume,
  VWAP, bar index, anchor, and session net move.  Maximum seeded error: 0.
- The fused daily engine matches the incumbent close-confirmed, N20/k1.5 scaled,
  and matched-fixed Sharpes within `2.2e-15`.
- The fast shuffle ran in 0.333s versus 5.270s (15.8x).  The fused engine ran the
  complete 60-variant scaled/fixed family in 5.307s versus 17.400s for only three
  variants through the reference engines.
- Exact one-second minute-block replay passed: maximum proxy uplift error 0.0046
  Sharpe and mean absolute error 0.0024 across three frozen seeds, versus gates
  of 0.03 and 0.02.

## Gross, net, baseline, and null comparison

The corrected 199-draw test repeats the complete Phase-1 selection rule: choose
the maximum scaled-Sharpe N-k cell, then compare that cell with close-confirmed
and its cell-specific draw-matched fixed buffer.

| selected-cell uplift | real | null mean | null sd | z | upper-tail p |
|---|---:|---:|---:|---:|---:|
| versus close-confirmed | +0.1319 | +0.1385 | 0.0793 | -0.08 | 0.510 |
| scaling versus fixed | +0.0850 | +0.0882 | 0.0741 | -0.04 | 0.525 |

The real improvements are almost exactly at the selection-corrected null center.
The original 30-draw fixed-cell inference was directionally correct but
understated the machinery/selection baseline.

## Regimes, sensitivity, and alternative explanations

The null preserves the complete minute atom set, opening anchor, session net
move, and diffusivity.  It changes order-dependent features as intended: body
lag-1 correlation moved 0.0079 to -0.0005, absolute-body lag-1 correlation
0.4642 to 0.3554, and the real/null time-of-day absolute-body profiles correlated
only 0.23.  Session high-low range is not invariant (median 91.75 real versus
90.50 null); prior wording that Null C preserved session range magnitude was
incorrect and is superseded.

## Artifact and implementation risks

- Exact one-second parity is validated on three prespecified draws, not all 199;
  the maximum error is small enough that it cannot plausibly bridge p=0.525.
- The full historical sample is consumed.  This validates machinery and the
  rejection; it does not create new deployment evidence.
- The fast daily runner intentionally emits P&L/count sufficient statistics, not
  full trade records.  The reference engines remain the audit path.
- `pytest` is unavailable in the workspace Python. Standard-library null tests
  and direct invocation of all pytest-style ATR tests passed.

## Builder interpretation

Accept the upgraded Null-C implementation.  The one-minute proxy is validated
for this exit-family null, and the selection-corrected result strengthens the
conclusion that the ATR buffer has not demonstrated incremental path information.
This remains distinct from whether a mechanical buffer may have acceptable
future deployment utility.

## Independent review

- Review status: builder validation complete; independent review pending
- Objections: none from executable validation
- Verdict: implementation PASS; research NO-GO confirmed

## Promotion decision

- `reports/FINDINGS.md`: not present; evidence remains in immutable run artifacts
- `MEMORY.md`: update EXP-0032 Null-C figures and correct the session-range claim
- Shared `LEARNINGS.md`: not eligible without cross-project verification
