# Immutable Run Artifacts

Create one directory per new material run:

```text
artifacts/runs/EXP-0007/
  manifest.json
  metrics.json
  trades.parquet
  figures/
  review.md
```

At minimum, `manifest.json` should identify the experiment ID, UTC run time,
config path/hash, code commit or module reference, data scope/fingerprint, exact
command, environment summary, and output files. Never overwrite a completed run;
allocate a new experiment ID for a rerun with changed inputs or code.
