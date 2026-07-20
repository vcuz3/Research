# Claims Register

No external paper; the "claim" is the user's baseline hypothesis and its kill test.
kb=2, ks=3, window 10:00–15:00, 15m gap are prespecified, NOT searched — any later
sweep is discovery on consumed history and must be labelled (rule 26).

| Claim ID | Claim | Metric | Threshold | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| CLM-001 | The ±2σ VWAP fade with a fixed 2RR bracket is net-profitable on GC under honest fills | net expectancy/trade @0.5 tick/side | > 0 | **FAIL** (−0.132 pt, Sh −0.82) | `reports/BASELINE_REPLICATION.md` |
| CLM-002 | Any edge does not depend on optimistic intrabar path assumptions | net @0.5 tick: adverse vs same-bar-target | sign stable | FAIL (gross ≈ 0 both) | same |
| CLM-003 | Any edge survives realistic entry-queue friction | net @0.5 tick under strict +1-tick trade-through entry | > 0 | **FAIL** (−0.197 pt) | same |
