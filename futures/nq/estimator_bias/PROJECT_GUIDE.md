# Estimator bias in short-window persistence statistics (NQ/ES) — Project Guide

## Objective and scope

- Research question: how large is the finite-sample bias of a persistence estimator at
  the window lengths this workspace actually uses, and **which published conclusions does
  it touch?** This is a cross-project **audit**, not an edge search.
- Instruments: **NQ** and **ES**, RTH 1-minute, plus synthetic AR(1) and fractional
  Brownian motion.
- Source paper: none. Origin is `research_papers/ALIGRITHM_HYPOTHESES_2026-08.md` item
  H-A2, derived from aligrithm.com *3.35 Trend and Reversion Are the Same, and OLS
  Understates Both* (2026-06-28) and *5.30 Order-Flow Autocorrelation: Why Buys Follow
  Buys* (2026-07-02). `paper/` is intentionally empty and the baseline-replication gate
  does not apply.
- Data source and coverage: `futures/nq/data/{NQ,ES}_1m_clean.parquet`, 2011-08 → 2026-07.
  Shared instrument data — do not copy into the project.

## Project map

| Concern | Location |
| --- | --- |
| Paper contract and claims | `paper/` — **not applicable**, no source paper |
| Faithful replication | `baseline_replication/` — **not applicable** |
| Execution/accounting | `backtest_engine/` — **not applicable**, nothing here trades |
| Estimators and diagnostics | `core/arbias.py` |
| Studies | `scripts/s{1,2,3}_*.py` |
| Hypotheses and run ledger | `experiments/` |
| Nulls/controls | `validation/` — controls live inside `scripts/s3_hurst_gate.py` |
| Immutable outputs | `artifacts/runs/` |
| Current reports | `reports/FINDINGS.md` |
| Durable handoff | `MEMORY.md` |

**Why there is no backtest engine.** Every result is a measurement of an estimator or of
an already-published statistic. There are no positions, fills, stops or P&L, so there is
nothing for a rule-1/2/3 execution model to adjudicate. If this project ever makes a
trading claim, that changes and this section must be revisited.

## Data and session conventions

- Timestamp source and timezone: `ts_utc` in the clean parquet, converted to
  `America/New_York`.
- Trading calendar/session: **RTH 09:30–16:00 ET**, `mfo` = minutes from 09:30 (0..389).
- Decision clock: 30-minute, `mfo` ∈ {29, 59, …, 389} — 13 decisions, matching
  `noise_vwap/core/session.py::decision_mfos(30, 389)`.
- Session eligibility differs by study **on purpose**: Study 2 uses
  `vei_exploration`'s loader (≥350 bars, 3,710 sessions) because it is auditing that
  project's number; Study 3 uses `hurst_explore`'s **complete-grid** rule (exactly 390
  slots; 3,703 NQ / 3,706 ES) because Hurst estimators require exact regular spacing.
- Instrument/roll convention: inherited from the clean 1-minute archives.
- Corporate actions or price adjustments: not applicable.
- Missing data policy: inherited from each loader; windowed features use the rule-9a
  fractional `min_obs` (**lookback=90, min_obs=45**), and Study 3 reports per-slot
  coverage of the same-slot z (measured spread 0.0000 — uniform).
- Holdout: **none exists and none is relevant.** Every input is already-consumed
  exploratory data or synthetic. Nothing here can consume a clean sample.

## Commands

```powershell
# Invariants (18 checks) — must pass before any run is registered
.\.venv\Scripts\python.exe -m futures.nq.estimator_bias.tests.test_core

# Study 1 — the window-length bias calibration table (synthetic only)
.\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s1_bias_table

# Study 2 (Cell B) — audit vei_exploration's pooled AC1
.\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s2_pooled_ac1 NQ
.\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s2_pooled_ac1 ES

# Study 3 (Cell A) — the expanding-window Hurst gate + both degenerate controls
.\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s3_hurst_gate NQ
.\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s3_hurst_gate ES
```

## Acceptance gates

- Baseline tolerance: **1e-4** on any number reproduced from another project's frozen
  artifact (rule 23; deterministic work on identical inputs). All 8 audited AC1 cells met
  it.
- Engine tests required: `tests/test_core.py` must pass **18/18**. It pins, among others,
  that OLS shrinks toward zero for **both** signs at small T, that Kendall's formula
  predicts the measured bias, that the two correctors agree at moderate T, that
  slot-demeaning kills a pure clock the pooled estimator reports as persistence, that
  `causal_slot_stats` is blind to the future under truncation, and — the guard that
  matters most here — that `LAGS`/`H_GRID` re-read from
  `noise_vwap/scripts/hyp_0017_hurst_filter.py` still match the copies in `core/arbias.py`.
- Minimum validation suite for any claim about a thresholded feature: **matched global
  selection rate on a common sample**, a **degenerate control whose true parameter is
  known** (`signflip` preferred over `fbm05` — it holds intraday volatility seasonality
  fixed), the **whole threshold profile rather than the argmax**, **both markets**, and a
  **rule-9a per-slot coverage report** for the comparator.
- Holdout protocol: not applicable.

## Standing cautions specific to this project

1. **`core/arbias.py::ghe1` is a verbatim copy of the audited script.** If the guard test
   fails, `noise_vwap` changed and this audit is measuring a ghost — re-run before citing
   anything.
2. **`pooled_lag1_slot_demeaned` uses the full-sample slot mean.** It is a diagnostic
   decomposition of a published descriptive statistic, **not a causal feature**. It must
   never be lifted into a strategy in that form.
3. **Read the per-window SD, not the mean.** The whole finding is a dispersion effect; the
   level barely moves. An audit that plots only the mean will see nothing.
4. **Below T ≈ 20 the analytic corrector is wrong.** Use `bootstrap_ar1_correct`, and
   always run both — their disagreement is the only signal that you are out of range.

A material experiment is complete only when its ledger row contains the config, data
scope, code reference, command, primary metric, result, artifact path, builder, reviewer,
and review status.
