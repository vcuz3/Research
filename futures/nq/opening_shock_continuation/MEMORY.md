# Project Memory: Opening Shock Continuation

## Scope

- Objective: test a causal, intraday NQ continuation rule based on overnight-gap
  and first-30-minute direction agreement; ES is a sibling transfer.
- Data: local Databento-derived NQ/ES one-minute signals and one-second execution,
  2011-08-01 through 2026-07-14.
- Current phase: preregistration and engine construction.

## Current status

- Verdict: provisional hypothesis; no validation result yet.
- Last verified: 2026-08-20.
- Baseline: paper contract transcribed; local futures transfer not yet run.
- Engine audit: implementation in progress.
- Execution: one-second first record after explicit activation, one tick adverse
  each side plus $4.50 round trip; every eligible flat day is retained.
- Holdout: globally consumed/future-only. Historical splits are pseudo-OOS.
- Experiment ledger: `experiments/ledger.csv`.
- Primary evidence: pending registered artifacts under `artifacts/runs/`.

## Authoritative artifacts

- Paper specification: `paper/PAPER_SPEC.md`
- Claims register: `paper/CLAIMS.md`
- Preregistrations: `experiments/hypotheses/HYP-0001.md` and `HYP-0002.md`
- Baseline report: `reports/BASELINE_REPLICATION.md`
- Engine audit: `reports/ENGINE_AUDIT.md`
- Findings: `reports/FINDINGS.md`

## Confirmed findings

- None yet; registered data-quality evidence is still pending.

## Provisional hypotheses

- Structural audit indicates raw cross-roll gaps are economically large, so
  cross-session features require exact instrument-ID continuity. Confirmation
  awaits the registered data-quality artifact.
- HYP-0001: Gao et al.'s closing-window sign rule persists in local NQ/ES.
- HYP-0002: gap/opening agreement identifies continuation after 10:00 ET.

## Invalidated or superseded findings

- Superseded before validation: a 10:00 one-minute-open fill and guaranteed
  15:59 close. Independent preregistration review required explicit latency and
  an attainable scheduled-exit convention; primary execution now uses seconds.

## Decisions and constraints

- Local-only data means the published 1993-2013 SPY result cannot be replicated.
- NQ and primary-cost zero-day daily Sharpe are the sole primary instrument and
  estimand. ES, gross results, and alternative costs are secondary.
- No historical segment is described as a clean holdout.

## Known risks and open questions

- One-second OHLCV proves a traded-price clock, not bid/ask, queue position, or
  market impact. Cost stress and, for any survivor, recent order-book calibration
  are required.
- The selected rule arose from a broad opening-feature screen. Full-family null
  correction and matched controls are mandatory.
- A future-only shadow period is required for confirmation even if all historical
  gates pass.

## Next actions

1. Close independent preregistration review and freeze exact null/control rules.
2. Pass unit tests and register/run the data-quality and baseline experiments.
3. Only then open the 2019-2026 strategy results and validation suite.

## Promotion candidates

- None.
