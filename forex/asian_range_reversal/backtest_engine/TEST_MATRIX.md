# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
|---|---|---|---|
| Intrabar ambiguity | `test_same_minute_stop_target_is_adverse_for_long` | stop wins | automated |
| Fill-bar processing | `test_first_entry_bar_is_processed` | entry-bar stop seen | automated |
| Stale/marketable target | `test_target_already_marketable_is_skipped` | trade skipped | automated |
| Indicator causality | `test_wilder_indicators_on_monotone_path` | warm-up and Wilder state | automated |
| Bounded RSI and daily cap | `test_bounded_rsi_and_one_trade_daily_cap_are_stateful` | one entry; later eligible signal suppressed | automated |
| Cost reconciliation | `core.metrics.summarize` output | net = gross - round trip | run artifact |
| Stateful accounting | `daily_audit.csv`, daily P&L | signals discarded while open | run artifact |
| Missing data | `data_quality.json` | exclusions quantified | run artifact |
