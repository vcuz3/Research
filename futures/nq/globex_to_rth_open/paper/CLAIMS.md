# Claims Register

There is no published performance claim. The study estimates, rather than
assumes, the following user-defined quantities.

| Claim ID | Quantity | Acceptance/tolerance | Local result | Status | Evidence |
| --- | --- | --- | --- | --- | --- |
| CLM-001 | Baseline 18:00-to-09:30 gross and net performance | Exact reconciliation to bar anchors and cost formula | 3.7805 points gross, $60.61 net/trade | passed | `reports/BASELINE_REPLICATION.md` |
| CLM-002 | MA sweep uses no current/future RTH close | Feature date <= entry date in every used row | invariant passed | passed | `reports/ENGINE_AUDIT.md` |
| CLM-003 | VIX gate uses only a prior available daily close | VIX date <= entry date and staleness <= 4 days | invariant passed; no missing joins | passed | `reports/DATA_QUALITY.md` |
| CLM-004 | Four sizing variants reconcile to their stated proxies | Hand fixtures exact to 1e-12 | 5-test suite passed | passed | `tests/test_study.py` |
| CLM-005 | 10% target uses a strictly lagged 60-leg volatility estimate, 3x cap, and capped 0.5-bp/side costs | Hand fixtures exact and 60 warm-up trades reported | 8-test suite passed; 60 warm-up, 11 cap-bind days | passed | `tests/test_vol_target.py`, `reports/VOL_TARGET_FIGURE.md` |
| CLM-006 | LSE SMA200 reproduction reaches approximately 0.99 full-sample Sharpe under zero-return accounting on inactive days | tolerance +/-0.10; diagnose if outside | 1.014, difference +0.024 | passed | `reports/LSE_SMA200_FIGURE.md` |
| CLM-007 | LSE-versus-Databento yearly differences are measured under identical SMA200, volatility-targeting, cost, and inactive-day accounting | exact specification parity plus common-date attribution | Gate agrees on all 2,357 common dates; 2023-25 residual is concentrated in quarterly LSE contract splices | passed | `reports/LSE_DATABENTO_COMPARISON.md` |
