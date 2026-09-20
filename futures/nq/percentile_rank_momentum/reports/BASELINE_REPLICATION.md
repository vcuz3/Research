# Baseline Replication

- Baseline experiment ID: EXP-0002 (local B0-B4 ladder)
- Source version: two-source synthesis; faithful paper replication not applicable
- Data scope/fingerprint: EXP-0001 `data_audit.json`
- Frozen config: `../experiments/configs/hyp_0001.json`
- Exact command: `python -m futures.nq.percentile_rank_momentum.experiments.run_hyp0001 --experiment-id EXP-0002`

## Claim results

| Claim ID | Published | Local | Tolerance | Status | Explanation/evidence |
| --- | ---: | ---: | ---: | --- | --- |
| CLM-001 | positive NQ B4 gross | -0.122 tick/trade | > 0 | failed | `../artifacts/runs/EXP-0002/ladder_NQ.csv` |
| CLM-002 | B4 beats matched B1 | -0.400 net tick/trade delta | > 0 | failed | `../artifacts/runs/EXP-0002/result.json` |
| CLM-003 | hysteresis improves direct rank | +0.858 net tick/trade; 771 fewer trades | positive delta and fewer trades | passed mechanically | still -0.260 net tick/trade |
| CLM-004 | ES gross sign transfer | opposite signs | same sign | failed | `../artifacts/runs/EXP-0002/ladder_ES.csv` |

## Verdict

Faithful replication: not applicable. Local synthesized strategy: rejected /
NO-GO. Independent review remains outstanding.
