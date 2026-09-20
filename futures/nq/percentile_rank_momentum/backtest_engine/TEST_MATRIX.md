# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | `tests/test_engine_adapter.py` | 10:00 close decision fills 10:05 open | passed |
| Intrabar ambiguity | unchanged close-signal/next-open `core.engine` | no high/low-dependent fill | passed |
| Fees and slippage | `tests/test_metrics.py` | 0.2375 NQ point/side; 1.9 ticks RT | passed |
| Position/accounting state | adapter fixture + inherited engine state | one position; exact +2-point trade | passed |
| Calendars/missing data | EXP-0001 data audit | 3,718 sessions; 7 missing 5m slots counted | passed |
| Metrics and units | ladder and `risk_reconciliation.csv` | ticks, points, dollars, daily/weekly/start-zero DD | passed |
| Engine parity | `noise_vwap.scripts.studies validate` | 2,923 trades and +4.945 gross points on both paths | passed |
| Generalized numba harness | `noise_vwap.scripts.bench_engine parity` | numerical comparison | blocked by inherited column-schema mismatch |
