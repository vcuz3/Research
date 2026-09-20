# Project Memory: NQ Asia Session Range Expansion

## Scope

- Objective: test the "Asia session expansion 1.5x" signal reported by aligrithm.com
  ("The Signal Ceiling", retrieved 2026-08-26) as T = -10.96 and described there as
  "worse than useless".
- Data: NQ 1-minute Databento archive, 3,842 Asia sessions (18:00-03:00 ET),
  2011-08-01 -> 2026-07-15. The article's own window is 2021-12 -> 2025-08 (968 sessions).
- Current phase: exploratory study complete. Independent review not started.

## Current status

- Verdict: **NO-GO as a trade. The source's directional claim is separately REJECTED.**
- Last verified: 2026-08-26.
- Authoritative runs: `artifacts/runs/EXP-0001` (surface), `artifacts/runs/EXP-0002`
  (cost decomposition — the load-bearing result).
- Engine audit: 8 builder tests pass (`python futures\nq\asia_expansion\tests\test_engine.py`);
  independent review pending.
- Reproduce: `python futures\nq\asia_expansion\scripts\run_exp0001.py` and `..\run_exp0002.py`.
- Holdout: consumed. All historical data inspected; only future observations are clean.

## Confirmed findings

- **The reported T = -10.96 is a cost statistic, not a signal statistic.** On the article's
  own window, firing bars and 2.00-point charge, a coin-flip direction (zero directional
  information by construction, 400 draws) prints net t **-15.18 [-17.33, -13.05]** — more
  negative than -10.96. Evidence: EXP-0002. General form: net t after a fixed per-trade
  charge c is approximately `(mu - c)*sqrt(N)/sd`, so the `-c` term dominates at any
  realistic N. Never read such a t as a directional finding.
- **Gross continuation is weakly POSITIVE, never negative**: +0.0655 pt/signal
  (cluster-robust t +1.45, n=56,844) full archive; +0.0675 (t +0.50) in the article's
  window; positive at every k, every horizon, every Asia-window definition. The article's
  "you are buying the top of a spike that is already reversing" is contradicted by its own
  construction. Evidence: EXP-0001.
- **The trading conclusion nevertheless stands.** Net is negative on all four cost rungs.
  The best real gross cell (k=2.5, H=3: +0.302 pt, t +2.50, beats 400/400 coin flips) nets
  **-0.033 pt** even on the full NQ contract at a 1-tick spread.
- **Data quality passes (Rule 9a):** 99.68% bar coverage, flat by slot, 0 duplicates,
  **0 sessions mixing two contracts** so no signal-to-exit span crosses a roll. Reportable
  defect: 19.1% of 5-min bars are built from <5 one-minute bars (genuine Asia thinness);
  this biases the range denominator down and would matter to any future study reading the
  range distribution itself.
- **The 1.5x trigger is a strong time-of-day selector** (LEARNINGS #1): fire-rate CV
  **0.562**, max/min **9.28x**, spiking to 50% at 20:00 ET (Tokyo cash open) and 65% at
  02:00 ET (European pre-open). The gross P&L is *not* concentrated in those slots, so the
  selector does not explain the sign — but no conditional result off this signal may be
  read at unmatched fire rate.

## Provisional findings

- **On MNQ the binding cost is fees, not spread.** Round-trip spread at 1 tick = 0.25 pt;
  $1.70 round-turn fees / $2.00 per point = **0.85 pt**. The identical fee on the full NQ
  contract is 0.085 pt — 10x cheaper in points. Switching contract closes ~77% of the
  gross-to-breakeven gap at the primary cell but does not cross zero. So the article's
  "signal ceiling" survives, but roughly three quarters of its magnitude is a consequence
  of trading a $2/point contract rather than a law of market efficiency.
- **Enforcing one position at a time collapses gross from +0.066 to +0.003** (t +0.05,
  33,447 trades). The per-signal positive gross lives in clustered signal bursts. Any
  tradable claim would have to use the no-overlap arm. Rule 12 endogenous-count problem
  appearing as a magnitude collapse rather than a sign flip.
- Gross by year is unstable: 2023 -0.433 (t -3.16) vs 2024 +0.516 (t +1.77); 11 of 16
  years inside |t| < 1.1.

## Invalidated or superseded findings

- The builder's initial chat-level estimate that the article's 2.00-point charge was
  "roughly 2x too pessimistic" was **wrong** and is retracted: it understated MNQ fees,
  which are the dominant term. 2.00 pt is conservative but defensible; 1.10-1.35 pt is the
  realistic band. Corrected in `reports/FINDINGS.md` section F.

## Decisions and constraints

- No path-preserving return-shuffle null was purchased. The primary metric fails the net
  gate by ~1.3 pt/trade, and the gate rule says not to buy the expensive null until the
  real pass clears the success metric. The coin-flip control is a direction calibrator, not
  a substitute for that null, and is not claimed to be.
- 28 cells searched (4 k x 7 H) plus 3 lookbacks, 4 windows, 2 overlap policies. The single
  positive-net cell (k=2.5, H=18, +0.046 pt on the full contract, t 1.55) is the grid
  maximum and is reported as such. Nothing promoted, so no selection correction applied.

## Known risks and next actions

1. Obtain independent code/artifact review (both run reviews are builder-only).
2. Unresolved discrepancy: the article reports +1.06 gross for its 2.5x variant where this
   study measures +0.30. The article does not define its holding period or Asia window, so
   this study reproduces its *conclusion*, not its arithmetic. Carried as a limitation.
3. If the continuation effect is ever revisited, the honest next step is the full NQ
   contract at k>=2.5 with H>=18, run as a no-overlap book, with a selection-aware null
   over the reproduced 28-cell search. Prior is low: net is at best ~+0.05 pt.

## Promotion candidates

- One transferable lesson, proposed for `ai_shared_memory/LEARNINGS.md`: a t-stat computed
  on P&L net of a fixed per-trade charge is not a statement about signal direction;
  calibrate it with a coin-flip-direction control on identical fills and always print gross
  first. Origin: EXP-0002.
