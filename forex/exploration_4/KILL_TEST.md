# exploration_4 — Pre-registered Kill Test (FREEZE before the material run)

This file must be committed **before** the baseline run and must not be edited
after results are seen. It is the confirmatory contract for the frozen
mean-reversion baseline specified in `PROJECT_PLAN.md` §3.

## Thesis (one line)
A standardized-displacement fade (`|z| ≥ 2`, reversion-to-0 target, compulsory
1.5σ single-barrier stop) on 4 USD-major spot FX pairs has positive per-signal
net expectancy that is an *entry* effect, not exit geometry or a cost-model choice.

## Primary metric
Per-signal **mean net R**, with a **day/session block cluster-robust** SE and t.
Reported per pair, pooled, and by era. (Session-averaged R reported only to display
divergence — never as the verdict.)

## Decision threshold
GO requires per-signal mean net R > 0 with a cluster-robust CI excluding 0 at the
**base** cost scenario, AND survival of both mandatory diagnostics.

## NO-GO conditions (any one triggers NO-GO)
1. **Gross ≈ cost** — gross per-signal ≤ modeled base-scenario round-trip pip.
2. **Break-even win rate** — realized win rate ≈ algebraic `1/(1+RR)` of the frozen
   stop/target geometry (barriers efficient, no entry edge).
3. **Zero CI** — net mean-R cluster-robust CI includes 0.
4. **Diagnostic failure** — edge disappears under the symmetric-bracket OR
   fixed-horizon rerun (was exit geometry), OR fails to beat the random-exit null
   at matched exit rate.

## Controls / diagnostics that must run in the same pass
- Entry-information: symmetric bracket + fixed-horizon forward return (Rule 15).
- Random-exit control at matched exit rate (repeated draws vs the distribution).
- Cost curve: sweep scenario + vol term; report breakeven round-trip pip.
- News-blackout: entries vetoed; removed set separately quantified.

## Data scope
Consumed history for fit/inspection; **2024+ sealed**, reported once at the end.
Pairs: EURUSD, GBPUSD, AUDUSD, NZDUSD (midpoint 1m→5m; ~2 effective independent).

## Outcome recording
A NO-GO is a successful research outcome (Rule 25). Record verdict + evidence paths
in `MEMORY.md` and `reports/FINDINGS.md`; register the run (incl. failures) in
`experiments/ledger.csv`.

---
Frozen by: Codex   Date: 2026-08-08   Reviewer: pending independent review
