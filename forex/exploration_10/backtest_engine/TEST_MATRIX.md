# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | lagged features and next-open fixture | no same-candle fill | passed |
| Intrabar ambiguity | dual-touch fixture | adverse stop wins | passed |
| Gap handling | gap-through fixture | first tradable open | passed |
| Fees and slippage | exact cost fixture | one round-trip deduction | passed |
| Position state | overlapping-signal fixture | at most one position | passed |
| Calendars/missing data | data-quality report | no synthetic bars | passed with reported gaps |
| Metrics and units | hand calculation | exact R and pips | passed |
