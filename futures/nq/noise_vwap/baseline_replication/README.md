# Baseline Replication

The preserved baseline is the source-faithful strategy before improvement
ideas. This legacy project keeps executable code in its original locations:

- frozen reference description: `configs/faithful_config.json`
- baseline/ablation runner: `../scripts/forensic.py`
- simple baseline runner: `../scripts/run_baseline.py`
- primary report: `../FORENSIC.md`
- detailed plan: `../REPLICATION_PLAN.md`

The JSON is a reviewable specification snapshot, not yet a runtime configuration
consumed by the legacy scripts. If config loading is implemented later, parity
with the current explicit arguments must be tested before it becomes canonical.
