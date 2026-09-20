# Baseline Replication

- Experiment: EXP-0001
- Source: user request dated 2026-09-19.
- Data: four clean 1-minute midpoint archives; fingerprints in
  `artifacts/runs/EXP-0001/data_quality.csv`.
- Frozen config: `baseline_replication/configs/baseline.json`.
- Command: `python run_backtest.py --config baseline_replication/configs/baseline.json --output artifacts/runs/EXP-0001`.

## Claim results

| Claim | Result | Status |
| --- | --- | --- |
| Causal implementation on all four pairs | 7 tests pass; all pairs have valid feature/trade coverage | passed |
| Positive gross expectancy | +0.0413 R, bootstrap 95% CI [+0.0234,+0.0592], 4/4 pairs positive | passed, exploratory |

The baseline meets the frozen gross kill test. It does not establish a tradable
edge because 0.5 pip round-trip cost makes pooled expectancy slightly negative.
