# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | `tests/test_engine.py`, `tests/test_data_calendar.py` | actual one-second timestamps cannot precede activation; dates and symbols match | passed |
| Intrabar ambiguity | fixed-horizon strategy has no stop/target; `test_one_second_execution_uses_first_record_at_or_after_each_activation` | first attainable one-second record, then adverse slippage | passed / not applicable to exits within a bar |
| Fees and slippage | NQ/ES hand fixtures in `tests/test_engine.py` | exact multiplier, tick, fee, long/short, and bps reconciliation | passed |
| Position/accounting state | long/short/flat and missing-unused-price fixtures | one contract or flat; every flat eligible day has explicit zero P&L/cost | passed |
| Calendars/missing data | `tests/test_data_calendar.py` | ET/DST-safe session dates, holidays/early closes, prior expected session, roll mask, missing exit hard failure | passed |
| Metrics and units | `tests/test_metrics.py`, `tests/test_power.py` | zero-day Sharpe, HAC, drawdown, grouped alignment, and MDE units reconcile | passed |
| Engine/vectorized-null parity | `test_vectorized_candidate_pnl_matches_audited_engine_cost_algebra` | identical one-contract net dollars for every candidate side | passed |
| Candidate selection and nulls | `tests/test_pipeline.py`, `tests/test_nulls.py` | full 23-arm pipeline, paired donors, threshold refit, nonidentity, finite fixed draw count | passed |
| Simultaneous controls | `tests/test_controls.py` | five jointly resampled A/B comparisons and max-error lower bounds match hand reconstruction | passed |
| Injected power | `tests/test_baseline_validation.py`, `tests/test_power.py` | target Sharpe is reached exactly and known-real null machinery rejects | passed |

Latest synthetic command: `python -m pytest futures/nq/opening_shock_continuation/tests -q`.
Registered source-level data QA remains a separate pre-result gate.
