# Engine Test Matrix

| Concern | Test/fixture | Expected result | Status |
| --- | --- | --- | --- |
| Signal/fill causality | notebook entry/exit delay assertions | exact next-minute open; no same-bar fill | passed EXP-0001 |
| Intrabar ambiguity | decisions use closes; EOD uses final close proxy | no OHLC touch-order assumption | passed with EOD proxy caveat |
| Fees and slippage | per-trade `net = gross - 2 * cost_bps / 10,000` | exact 10 bps at default | passed EXP-0001 |
| Position/accounting state | chronological one-position loop and overlap assert | zero overlap; daily P&L sums trades | passed EXP-0001 |
| Calendars/missing data | ET session audit and exact-next-minute guard | report gaps; no fills; reject deficient sessions | passed EXP-0001 |
| Metrics and units | fixed-notional simple returns and explicit annualizer | gross/net, session risk, and dollars visible | provisional; hand fixture open |
| Engine parity | direct translation of audited NQ state rules | behavioral parity; asset economics intentionally differ | passed by inspection; independent review open |
