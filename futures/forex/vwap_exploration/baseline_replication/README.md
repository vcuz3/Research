# Baseline Replication

Implement only the source-faithful strategy here. Freeze its configuration under
`configs/`, keep baseline-specific tests under `tests/`, and write exact outputs
to `artifacts/` or the registered immutable run directory.

Do not add performance improvements until the claims register is passed, failed,
or explained within declared tolerances. Document the result in
`../reports/BASELINE_REPLICATION.md` and register the baseline run in the ledger.

---

**NOT APPLICABLE for this project.** No source paper, therefore no faithful
baseline to replicate. The frozen reference each experiment measures against is
declared in its hypothesis file and pinned by the `code_ref` in its
`experiments/ledger.csv` row.
