# Engine Audit

- Code reference: `trade_regime_tester.ipynb`
- Short command: `python forex/trade_regime_tester/_smoke_run_notebook.py`
- Full command: `python forex/trade_regime_tester/_smoke_run_notebook.py --full`
- Builder: Codex
- Reviewer: pending independent review

## Results

- EXP-0001 shortened run: passed all 26 code cells.
- EXP-0003 full-default run: passed all 26 code cells in 21.3 seconds.
- Full run loaded 4,085 train/test trades and 306,471 completed bars, fitted 82
  regime definitions, and reported `holdout_open=false`.
- Parquet reads predicate-filter trade and market rows before the 2024 holdout.
- Feature joins use completed timestamps no later than each decision; thresholds,
  GARCH parameters, imputation/scaling, and clusters are trained on training only.

## Exceptions and risks

- This audit verifies the analysis notebook, not the originating strategy's
  execution engine or fills.
- CSV macro and cross-asset adapters immediately filter active dates but cannot
  provide parquet-style predicate pushdown.
- Independent review is still pending.

## Verdict

Provisional pass for reusable notebook execution and holdout guards. No empirical
regime edge has been approved.
