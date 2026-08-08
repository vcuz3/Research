# Project Memory: Reusable Trade Regime Tester

Keep this concise. Link to reports and immutable artifacts instead of copying
their contents.

## Scope

- Objective: Reusable, strategy-agnostic regime attribution for frozen completed
  FX trades, with causal as-of joins and honest train/test/holdout separation.
- Instruments or markets: One configurable FX pair; default validated adapter is
  AUDUSD with NZDUSD as benchmark.
- Data coverage: Configurable. Notebook defaults to pre-2020 training,
  2021-2023 test, 2020 embargo, and sealed 2024+ holdout.
- Current phase: validation utility built; default AUDUSD and user-selected EURUSD executions passed.

## Current status

- Verdict: provisional
- Last verified: 2026-08-08
- Lifecycle phase: engine/validation
- Baseline replication: not applicable; no paper baseline
- Baseline tolerance and result: supplied-trade unconditional metrics are the
  reference; shortened smoke executed without discrepancy.
- Engine audit: provisional shortened and full default execution validation passed
- Execution profile: consumes authoritative completed trades; does not implement
  strategy entries, fills, exits, costs, or sizing.
- Holdout status: sealed in this project; 2024+ trade and market rows are
  excluded by read predicates unless explicit confirmation is entered. The
  source strategy project may have a different holdout status and must not be
  relabelled.
- Experiment ledger: `experiments/ledger.csv`
- Reproduction command: `python forex/trade_regime_tester/_smoke_run_notebook.py --full`
- Primary evidence: `trade_regime_tester.ipynb`; `experiments/ledger.csv`;
  `artifacts/runs/EXP-0001/`; `artifacts/runs/EXP-0003/`;
  `artifacts/runs/EXP-0004/`.

## Authoritative artifacts

- Notebook: `trade_regime_tester.ipynb`
- Input and workflow guide: `README.md`, `PROJECT_GUIDE.md`
- Hypothesis: `experiments/hypotheses/HYP-0001.md`
- Experiment ledger: `experiments/ledger.csv`
- Validation record: `artifacts/runs/EXP-0001/`
- Full-default validation record: `artifacts/runs/EXP-0003/`
- EURUSD exact-config validation record: `artifacts/runs/EXP-0004/`

## Confirmed findings

- The shortened 2019-train/2021-test default adapter executed all notebook code
  cells successfully with the 2024+ holdout sealed. Evidence: EXP-0001 ledger
  entry and the reproduction command above.
- The full default run executed 26 code cells in 21.3 seconds on 4,085 frozen
  trades and 306,471 completed bars, fitting 82 regime definitions with the
  2024+ holdout sealed. Evidence: EXP-0003 ledger entry.
- The notebook accepts a generic trades-frame mapping and automatically applies
  train-only thresholds, GARCH fit, preprocessing, clustering, coverage audits,
  fixed test contrasts, circular-shift nulls, FDR adjustment, interactions,
  persistence diagnostics, and trade visualisation.
- EXP-0004 passed all 26 cells on 2,611 EURUSD SMA200/Z2/arm30/ATR14x3/R1.5
  train/OOS trades, fitting 76 applicable regime definitions with 2024+ sealed. The loader
  now handles single-pair files without `pair` metadata explicitly and treats
  only decision time/outcome as mandatory mapped columns.

## Provisional hypotheses

- Hypothesis: One or more causal regime contrasts for a frozen strategy will
  retain sign and economic size out of sample.
  - Kill test: the fixed train contrast reverses in test, is sparse/stale, or
    fails the circular-shift null after multiplicity control.
  - Evidence needed: one predeclared candidate from a future strategy/config,
    re-run through the authoritative stateful portfolio engine.

- Default-screen result: zero features met the notebook's dual train/test 10%
  FDR confirmation rule under the configured 500 circular-shift nulls. This is
  provisional to the default frozen artifact and parameterization, not a claim
  that regimes never matter. Evidence: EXP-0003 ledger entry.

- EURUSD-screen result: zero features met the same dual train/test FDR rule for
  the frozen EXP-0002 trades. This is provisional screen evidence, not proof
  that no useful regime exists. Evidence: EXP-0004 ledger entry.

## Invalidated or superseded findings

- None yet.

## Decisions and constraints

- Strategy logic remains outside this project; the trades table is authoritative.
- Training defines all regime cut points and learned models. Test validates them.
- Default macro observation dates receive a conservative 45-day publication lag.
- Interactions are limited to a predeclared list and remain exploratory.
- Diagnostic gated equity is not exact portfolio accounting when trades overlap.

## Known risks and open questions

- Archived macro factors are point-in-time vintages but exact release timestamps
  are not present; the conservative lag is a proxy and macro conclusions remain
  provisional.
- True liquidity, positioning, options, and macro-surprise regimes require new
  timestamped data adapters; OHLC gap/coverage fields are only proxies.
- No specific regime gate has been validated or promoted.

## Next actions

1. Run the notebook on the user's chosen pair and exact frozen configuration.
2. Register at most one promoted gate with a directional prediction and kill test.
3. Re-run that gate in the authoritative portfolio engine before any holdout use.

## Promotion candidates

- None yet. Promote only findings verified and reusable across projects.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
