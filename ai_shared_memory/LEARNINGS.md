# Shared Research Learnings

This file contains verified lessons that apply across more than one research
project. The mandatory backtesting rules live in `RULES.md`; project status and
project-only findings belong in each project's `MEMORY.md`.

## Entry criteria

Add a learning only when it is:

- supported by code, data, or a reproducible test;
- durable enough to matter in later sessions;
- useful beyond the project where it was discovered;
- linked to evidence in this workspace.

Use one of these statuses: `confirmed`, `provisional`, `invalidated`, or
`superseded`. Provisional items should include the test needed to confirm or
kill them.

## Learnings

### 2026-07-18 — Pin artificial opening sentinels in return-shuffle nulls

- Status: confirmed
- Applies to: session-level path reconstruction and path-preserving return
  shuffles
- Learning: when `link[0] = 0` is an artificial opening anchor, including it in
  the permutation and then re-anchoring the first open discards whichever real
  link lands at index 0. This changes the reconstructed session net move. Pin
  the complete opening atom, or use another construction whose claimed
  invariants are proved by tests.
- Evidence: `futures/nq/noise_vwap/tests/test_nulls.py` and
  `futures/vwap_mean_version/tests/test_nulls.py`
- Consequence: every path-reconstruction null must test its opening anchor,
  session net move, complete atom multiset, and path-continuity statistic across
  multiple seeds before its P&L distribution is interpreted.
- Origin: `futures/nq/noise_vwap/core/nulls.py` and
  `futures/vwap_mean_version/core/nulls.py`

<!--
Suggested entry format:

### YYYY-MM-DD — Short title

- Status: confirmed
- Applies to: project types, instruments, or methods
- Learning: one concise, atomic statement
- Evidence: relative/path/to/report.md or relative/path/to/test.py
- Consequence: what future work must do differently
- Origin: relative/path/to/project/MEMORY.md
-->
