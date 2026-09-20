# Claims Register

| Claim ID | Claim and source | Published value | Tolerance | Local result | Status | Evidence |
| --- | --- | ---: | ---: | ---: | --- | --- |
| CLM-001 | HYP-0001: NQ B4 expected-value readout has positive gross expectancy | n/a — local synthesis | > 0 gross tick/trade | -0.122 | failed | `../artifacts/runs/EXP-0002/ladder_NQ.csv` |
| CLM-002 | HYP-0001: B4 beats direct B1 at matched trade count | n/a — local synthesis | positive net ticks/trade delta | -0.400 | failed | `../artifacts/runs/EXP-0002/result.json` |
| CLM-003 | Source-2 keeper: hysteresis reduces churn and improves direct-rank retention | qualitative | fewer trades and higher net expectancy than B1 | 7,830→7,059 trades; -1.118→-0.260 net ticks/trade | passed mechanically; still non-tradable | `../artifacts/runs/EXP-0002/ladder_NQ.csv` |
| CLM-004 | HYP-0001: B4 gross sign transfers from NQ to ES | n/a — local synthesis | same nonzero gross sign | NQ -0.122; ES +0.331 | failed | `../artifacts/runs/EXP-0002/ladder_ES.csv` |
