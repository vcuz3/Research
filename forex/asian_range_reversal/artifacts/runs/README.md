# Immutable Run Artifacts

Use one directory per experiment ID. Each run should contain a manifest with the
experiment ID, UTC timestamp, config hash/path, code reference, data fingerprint
and scope, exact command, environment, and output inventory. Store metrics,
trades, figures, and review notes as applicable. Never overwrite a completed run.

Every run directory includes `review.md`. That is where results are discussed;
only reviewed synthesis is promoted to `reports/FINDINGS.md` and durable state.
