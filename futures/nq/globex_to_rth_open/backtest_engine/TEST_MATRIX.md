# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | `test_exact_next_date_anchors_and_fixed_clock_pnl` | exact 18:00/09:30 anchors, prior features | passed |
| Intrabar ambiguity | Fixed bar-open orders, no bracket | not applicable | passed |
| Fees and slippage | `test_costs_reconcile_exactly_for_one_contract` | $15 round trip, exact net | passed |
| Position/accounting | one anchor pair per trade date | at most one position | passed |
| Calendars/missing data | exact-clock pairing and bounded joins | no late-bar substitution | passed |
| Rolls | `test_roll_inside_holding_interval_is_excluded` | roll-crossing trade excluded | passed |
| Sizing | `test_inverse_sizing_uses_reference_over_current_and_caps` | exact inverse ratios and cap | passed |
| VIX causality | `test_daily_vix_reference_is_strictly_lagged` | reference excludes current row | passed |
| Metrics/units | hand cost/P&L fixture | exact points-to-dollars conversion | passed |

