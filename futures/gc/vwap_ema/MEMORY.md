# Project Memory: GC VWAP-EMA Paper Validation

## Scope

- Objective: historical validation of SSRN 6650958's quantified gold strategy.
- Instrument: GC futures treated as an XAU/USD proxy by user instruction.
- Primary data scope: 2024; contextual history 2011-2026.
- Current phase: Stage 1 closeout.

## Current status

- Verdict: **NO-GO**.
- Last verified: 2026-07-22.
- Baseline replication: failed the paper claims and passed the NO-GO kill test.
- Baseline tolerance/result: 17 historical trades versus 247 synthetic; gross
  +0.1176R, net -0.1224R at 0.24R; 1%-risk return -2.14%.
- Engine audit: passed; nine deterministic fixtures.
- Holdout status: consumed; future-only.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction: see `PROJECT_GUIDE.md`.
- Primary evidence: `artifacts/runs/EXP-0003/` and
  `reports/BASELINE_REPLICATION.md`.

## Confirmed findings

- The paper's 247 trades are a chosen Monte Carlo sample size, not the number of
  historical signals found in 2024. Source: paper sections 6.1 and 7.2.
- The source is internally inconsistent about NY-local versus fixed-UTC session
  time and about a post-entry favourable VWAP milestone after requiring entries
  already beyond VWAP. Resolutions are recorded in `paper/PAPER_SPEC.md`.
- The historical 2024 proxy generates 18 signals and 17 trades, not 247. At the
  requested cost it loses -0.1224R/trade; the 2011-2026 context also fails gross
  (-0.0292R/trade). Stage 1 is therefore NO-GO.

## Known risks and open questions

- GC traded volume and futures basis/rolls are only a proxy for XAU/USD tick
  volume. Paper-level numerical replication is impossible without the paper's
  unpublished Monte Carlo seed/outcome sample.
- The discretionary news-event swing-stop override is not machine-testable.

## Next actions

1. Obtain an independent second-model review if desired; otherwise close the
   project. Do not tune the consumed history to match the synthetic trade count.
