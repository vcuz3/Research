# Experiment Ledger Schema

Each project keeps an append-only `experiments/ledger.csv`. One row represents
one material research run or decision-relevant analysis.

## Required columns

| Column | Meaning |
| --- | --- |
| `experiment_id` | Stable unique ID such as `EXP-0007`. |
| `declared_date` | Date the hypothesis or reconstruction was recorded. |
| `phase` | `baseline`, `engine`, `experiment`, `validation`, or `shadow`. |
| `status` | `planned`, `running`, `completed`, `failed`, or `abandoned`. |
| `hypothesis` | Falsifiable claim or purpose of the run. |
| `kill_test` | Predeclared evidence that rejects the hypothesis. |
| `config_path` | Frozen configuration, or `legacy-not-frozen`. |
| `data_scope` | Instruments and date range used. |
| `code_ref` | Commit hash when available; otherwise a precise module path. |
| `run_command` | Reproduction command. |
| `primary_metric` | Predeclared decision metric. |
| `result_summary` | Concise result, including adverse results. |
| `artifact_path` | Immutable run directory or authoritative report. |
| `builder` | Human/model that implemented or ran it. |
| `reviewer` | Independent reviewer, or `unassigned`. |
| `review_status` | `pending`, `passed`, `issues`, or `not-reviewed`. |
| `notes` | Caveats, supersession links, or reconstruction status. |

## Ledger rules

- Add the row before running whenever practical; update that same row on finish.
- Never delete losing, failed, or abandoned experiments.
- Never reuse an experiment ID or overwrite another run's artifact directory.
- Use CSV-safe quoting. Put long reasoning in a linked Markdown report.
- Mark reconstructed legacy entries as such; do not imply they were predeclared.
- If a result is superseded, preserve it and name the superseding experiment.
- Discuss a run in `artifacts/runs/<experiment_id>/review.md`; synthesize only
  reviewed results in `reports/FINDINGS.md`.
- Use `python tools/research_admin.py` for ID allocation and ledger updates.
