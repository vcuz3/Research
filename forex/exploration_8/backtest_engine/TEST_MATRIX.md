# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | `test_next_bar_entry_and_cost_accounting` | completed-bar signal uses later bar open | pass |
| Lagged feature construction | `test_normalizer_is_strictly_lagged` | shock is absent from its own rolling mean | pass |
| Direction convention | `test_rich_actual_produces_short_signal` | rich actual AUDUSD maps to short residual | pass |
| Fees and slippage | `test_next_bar_entry_and_cost_accounting` | one-leg and three-leg cost deductions reconcile | pass |
| Calendars/missing data | `test_event_cannot_cross_a_gap` | event crossing a missing bar is rejected | pass |
| Cross-rate algebra | `test_synthetic_identity_and_zero_basis` | constructed identity has zero basis | pass |
| Intrabar ambiguity | fixed-horizon close only; no bracket orders | not applicable to this engine | N/A |
| Portfolio capital/accounting | unit event returns only | required before a deployable portfolio claim | open |
| Quote-level execution | midpoint archives have no bid/ask | required before an arbitrage claim | open |
| Engine parity | one implementation | second implementation not warranted at exploratory stage | N/A |
| Pine rolling convention | `test_pine_zscore_includes_current_bar_and_uses_population_std` | current bar and `ddof=0` preserved | pass |
| Wilder ATR seed | `test_wilder_rma_uses_sma_seed` | first value is period-SMA seed | pass |
| Pine entry-bar bracket | `test_entry_is_next_bar_and_dual_touch_is_stop_first` | next-open entry; stop wins ambiguous minute | pass |
| Pine Z exit | `test_z_reversion_exits_at_following_bar_open` | reversion close fills at next open | pass |
| Pine gap-through | `test_gap_through_stop_fills_at_minute_open` | stop fills at first tradable open | pass |
| Minute-delay clock | `test_delay_clock_and_constant_holding_period` | exact delay and constant 30-minute hold | pass |
| Paired decay coverage | `test_gap_removes_signal_from_every_arm` | invalid signal removed from every arm | pass |
| Decay costs/identity | `test_cost_units_and_residual_identity` | one-leg and three-leg costs reconcile | pass |
| Decay inference | `test_summary_uses_all_observed_days_and_paired_difference` | zero days and paired changes represented | pass |
