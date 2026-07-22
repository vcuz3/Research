# Engine Test Matrix

| Invariant | Test |
| --- | --- |
| Close-only EMA trail ignores wicks | `test_trail_is_close_only_wick_immune` |
| 1s path orders stop and target | `test_stop_before_target_on_1s_path`, `test_target_before_stop_on_1s_path` |
| Gap-through stop fills adversely | `test_gap_through_stop_fills_at_open` |
| Stop/target geometry | `test_risk_and_target_geometry` |
| EMA20 final-leg tightening | `test_ema20_tightens_after_2_5r` |
| Session close liquidation | `test_forced_flat_last_bar` |
