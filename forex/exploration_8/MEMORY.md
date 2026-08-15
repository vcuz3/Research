# Project Memory: AUD triangular pricing exploration

## Scope

- Objective: build editable exploratory and Pine-translation notebooks for AUDUSD versus AUDJPY/USDJPY triangular-pricing dislocations.
- Instruments or markets: AUDUSD, AUDJPY, USDJPY spot-FX midpoint OHLC.
- Data coverage: user-selected local window; exact source/aligned coverage is reported on every load.
- Current phase: exploratory workbench / paper intake.

## Current status

- Verdict: EXP-0001 is a KILL for a minute-capturable triangular-pricing edge; EXP-0002 confirms rollover dominates signal incidence but the blackout arm remains negative net at the assumed costs. Independent review pending.
- Last verified: 2026-08-13.
- Lifecycle phase: first registered decay diagnostic completed.
- Baseline replication: strategy contract transcribed; no empirical baseline run yet.
- Baseline tolerance and result: deterministic tests cover algebra, both rolling conventions, Wilder ATR, direction, next-bar timing, gap-through, adverse dual-touch, costs, and gap rejection.
- Engine audit: limited to the fixed-horizon and Pine-translation fixtures in `test_triangle.py` and `test_pine_translation.py`.
- Execution profile: completed bars, next-bar midpoint open, fixed-horizon close, optional two-bar embargo, non-overlapping events.
- Holdout status: 2024 onward locked by default; not claimed as pristine because related workspace research has inspected it.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction command: `python _build_notebook.py` and `python _build_pine_translation_notebook.py`.
- Primary evidence: `artifacts/runs/EXP-0001/`, both notebooks, `strategy/`, `backtest_engine/`, and deterministic tests.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`.
- Claims register: `paper/CLAIMS.md`.
- Baseline report: `reports/BASELINE_REPLICATION.md`.
- Engine audit: `reports/ENGINE_AUDIT.md`.
- Current findings: `reports/FINDINGS.md`.

## Confirmed findings

- The cross-rate algebra and causal implementation are covered by deterministic fixtures. No market edge is confirmed.
- EXP-0001 retained 610 signals across every minute-delay arm. Three-leg residual gross fell from +1.2429 bp at delay zero to +0.1221 bp at one minute and +0.0306 bp at five minutes; five-minute net was -1.4694 bp at 0.5 bp round-trip cost per leg.
- AUDUSD-only gross fell from +2.3043 bp at delay zero to +0.4856 bp after one minute; one-minute net was -0.0144 bp.
- Five-minute residual gross was negligible and residual net negative in every year from 2015 through 2020.
- The 15-minute ±3 Z-crossings are dominated by the New York rollover boundary: 17:00 ET has 1,054 signals across the inspected 2015--2020 sample and a 27.35% signal rate; the 17:00 slot itself has 752 crossings in 1,515 aligned observations (49.64%). The concentration follows 17:00 ET across daylight-saving changes (21:00 UTC in DST and 22:00 UTC otherwise), so it is a local-session effect rather than a fixed-UTC event.
- The rollover basis move is directional and source-specific: the mean 17:00 ET log-basis change is -1.0050 bp, with mean leg returns of AUDUSD -0.0875 bp, AUDJPY +0.0248 bp, and USDJPY -0.8927 bp. There are 629 negative-Z versus 123 positive-Z crossings in that slot. The 17:30 basis change averages +0.3001 bp and correlates -0.642 with the prior 17:00 change, consistent with partial reconciliation after the boundary.
- EXP-0002 applied an inclusive 16:45--18:00 America/New_York decision-time blackout. It removed 1,152 of 1,976 raw 15-minute crossings (58.3%). At the primary one-bar-delay/30-minute-hold setting, the rerun non-overlap sample changed from 1,100 to 786 events; residual gross changed from +1.0671 to +0.9954 bp and residual net from -0.4329 to -0.5046 bp at 0.5 bp round-trip cost per leg.
- With the same blackout and a two-bar entry delay, 15-minute/30-minute-hold residual gross was +0.0674 bp and net was -1.4326 bp. The surviving effect is therefore not robust to one additional bar of latency.

## Provisional hypotheses

- Hypothesis: large causal basis Z-scores predict subsequent convergence.
  - Kill test: no positive gross three-leg residual after the two-bar embargo, or result does not beat a claim-matched date-block/circular re-pairing null.
  - Evidence needed: frozen parameter set, registered run, null distribution, costed quote-level follow-up, and independent review.

## Invalidated or superseded findings

- None yet.

## Decisions and constraints

- Midpoint OHLC bars cannot establish true executable triangular arbitrage.
- The user can choose timeframe, Z lookback, and entry threshold in the first notebook configuration cell.
- Both the requested AUDUSD-only arm and the three-leg residual are reported.
- The notebook uses a fixed-horizon exit because the user did not specify an exit.
- The separate Pine translation preserves its state-based entries, Z-reversion exits, Wilder ATR brackets frozen from the signal close, fixed AUDUSD quantity, and next-bar market fills.

## Known risks and open questions

- Archives are from separate sources and may not be synchronized within a bar.
- Session calendars diverge at rollover. In 15-minute 2015--2020 data, AUDUSD and AUDJPY have no complete 17:15 ET bars, while USDJPY has 980; USDJPY also has materially fewer complete 17:30--18:00 bars. With right-labeled bars, 17:00 is the final pre-break interval. Treat the rollover cluster as a feed/calendar/marking artifact unless reproduced with synchronized same-venue bid/ask quotes.
- Midpoints omit spreads; cost inputs are sensitivities, not measured fills.
- Parameter selection inside the notebook is exploratory and consumes the viewed dates.
- The paired minute sample excludes most rollover signals without an exact continuous common one-minute path: 610 of 1,307 crossings survive all arms. The result applies to the continuously tradable midpoint sample.

## Next actions

1. Do not promote the current minute-bar result as a trading edge.
2. Obtain synchronized sub-minute bid/ask quotes only if testing whether the boundary effect is capturable within the first minute.
3. Add an ordinary AUDUSD mean-reversion benchmark before attributing any AUDUSD-only boundary return to the JPY cross signal.
4. Seek independent review of EXP-0001 before final closeout.

## Promotion candidates

- None yet.
