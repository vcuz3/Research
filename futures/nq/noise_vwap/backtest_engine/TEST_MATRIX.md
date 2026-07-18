# Engine Test Matrix

| Concern | Current implementation or check | Status |
| --- | --- | --- |
| Decision-to-fill causality | `core/engine.py` next-open path | implemented |
| Same-close sensitivity | `fill_mode="signal_close"` | ablation only |
| Faithful/generalized parity | `scripts/bench_engine.py parity` | required before engine2 acceptance |
| Validation suite | `scripts/studies.py validate` | required |
| Gross versus net costs | caller-visible points and explicit costs | implemented |
| Session-valid null | `core/nulls.py`, `tests/test_nulls.py` | anchor/net-move/atom/diffusivity invariants tested; faithful rerun outstanding |
| Metric units | `core/metrics.py` | implemented; preserve per-trade/per-day distinction |
| Clean data/session audit | `DATA_AUDIT.md`, `core/build_clean.py` | documented |
| Missing/short/holiday sessions | data audit and session filters | review whenever data changes |

This matrix is an index, not proof. Commands, fixtures, and reports are the
evidence. Update it when the engine contract changes.
