# forex/noise_vwap — agent instructions

Read `PROJECT_GUIDE.md` (operating manual), `MEMORY.md` (current state and
verdict), and `reports/FINDINGS.md` before changing anything. The workspace root
loads `ai_shared_memory/RULES.md`, `LEARNINGS.md` and `RESEARCH_WORKFLOW.md`.

## Status

**This project is CLOSED as a NO-GO** (2026-08-01, EXP-0001 + EXP-0002). The
Noise-Area + VWAP strategy loses at the gross level on all four FX majors. Do
not reopen it with parameter variations; `reports/FINAL_REVIEW.md` records what
is and is not worth doing next.

## Commands

```powershell
python -u -m forex.noise_vwap.core.build_clean            # CSV -> clean parquet
python -u -m forex.noise_vwap.scripts.data_quality        # rule-9a gate
python -u -m forex.noise_vwap.tests.test_core             # 22 invariants
python -u -m forex.noise_vwap.tests.test_parity           # 400-config engine parity
python -u -m forex.noise_vwap.scripts.run_grid            # EXP-0001
python -u -m forex.noise_vwap.scripts.entry_information   # EXP-0002
```

Run from the workspace root (`C:\Users\VuDoa\Research`) so the package path
resolves.

## Conventions that must not drift

- `core/engine.py` is the readable DEFINITION of the trading rules.
  `core/engine_nb.py` is a numba kernel that must stay trade-level identical to
  it; `tests/test_parity.py` is the gate and must pass before any result is
  interpreted.
- There is no volume in this data. The anchor is the session TWAP, which is the
  VWAP formula at constant weights — not a heuristic. Never reintroduce a volume
  column; `core/build_clean.py` drops the constant `-1` deliberately so nothing
  can silently weight by it.
- The `fxday` anchor (17:15 ET) and the ET-wall-clock decision grid (`:29`/`:59`)
  exist to neutralise a measured archive defect. Changing either requires
  re-running `scripts/data_quality.py` and re-reading `reports/FINDINGS.md` §E.
- Report gross before net. Report per-signal effects with session cluster-robust
  inference, never session-averaged — `reports/FINDINGS.md` §D shows the two
  disagree in sign on this data and on NQ/ES.
- Null C (`core/nulls.py`) is spent only after a real pass clears its primary
  metric.
- Register every material run in `experiments/ledger.csv` and write its
  `artifacts/runs/EXP-XXXX/review.md`. Use `python tools/research_admin.py`.
