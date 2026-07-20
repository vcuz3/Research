# YM Noise VWAP Claude instructions

@PROJECT_GUIDE.md
@MEMORY.md

The workspace `CLAUDE.md` imports the global rules, learnings, and research
workflow. This project is a port of `futures/nq/noise_vwap` (via the GC port) to
YM (E-mini Dow): preserve the faithful baseline, keep `core/engine.py` and
`core/metrics.py` in parity with the audited NQ engine, use the audited engine for
execution, register material runs in `experiments/ledger.csv`, and keep durable
project state in `MEMORY.md`.
