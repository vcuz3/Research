# Baseline Replication — NOT APPLICABLE

There is no source paper and no published backtest to replicate. H-A1 comes from
a blog post that states formulae and reports no numbers, so `paper/PAPER_SPEC.md`
is empty by design and `paper/CLAIMS.md` tests the formulae directly.

The equivalent gate is the **identity check** in `artifacts/runs/EXP-0001/`:
predicted P&L from the closed form must equal the engine's realised P&L at the
same execution lag. Declared tolerance 1e-9; achieved **4.16e-17** over 30
products x 2 lags. A failure halts the run in code (`scripts/s1_screen.py`).

See `reports/FINDINGS.md` and `paper/CLAIMS.md`.
