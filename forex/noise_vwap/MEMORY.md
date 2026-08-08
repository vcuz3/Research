# Project Memory: Forex Noise Area TWAP

Concise handoff. Detailed evidence lives in `reports/` and
`artifacts/runs/EXP-XXXX/`.

## Scope

- Objective: port the Zarattini / Quantitativo Noise-Area + VWAP intraday
  momentum strategy (`futures/nq/noise_vwap`) to spot FX, and — because IBKR
  cash FX publishes no size — decide what replaces the VWAP in its two roles
  (entry gate, trailing-stop reference).
- Instruments: EURUSD, GBPUSD, AUDUSD, NZDUSD spot, 1-minute IBKR midpoint.
- Data coverage: 2011-07-20 → 2026-07-17 (NZDUSD from 2011-12-07); 3,782–3,887
  sessions per pair per session definition. Source `forex/data/*.csv`, cleaned
  to `forex/data/clean/{PAIR}_1m_clean.parquet`.
- Current phase: closed out as a NO-GO after two registered experiments.

## Current status

- **Verdict: NO-GO.** The strategy loses at the GROSS level on all four pairs,
  in both session definitions, in 88 of 96 declared cells. Both preregistered
  kill-test gates fail. This is a rule-25 successful negative result, not an
  unfinished investigation.
- Last verified: 2026-08-01 (EXP-0001, EXP-0002).
- Lifecycle phase: closeout.
- Baseline replication: N/A — this is a cross-instrument port, not a paper
  replication. The external reference is `futures/nq/noise_vwap`.
- Engine audit: `core/engine.py` is the readable reference; `core/engine_nb.py`
  is a numba kernel with **trade-level exact parity on 400 configurations**
  (`tests/test_parity.py`). 22 core invariants pass (`tests/test_core.py`).
- Execution profile: signal on the decision bar's close, fill at the next
  1-minute bar's open, forced flatten at the session close. No fill at the
  signal close or at a band/stop level — both asserted in code.
- Costs: headline 0.50 pip/side on midpoint data; 0.25 and 1.00 also reported.
  Gross always reported separately.
- Holdout status: consumed. Only future observations can be clean holdout
  evidence.
- Experiment ledger: `experiments/ledger.csv`.
- Reproduction:
  - `python -u -m forex.noise_vwap.core.build_clean`
  - `python -u -m forex.noise_vwap.scripts.data_quality`
  - `python -u -m forex.noise_vwap.tests.test_core`
  - `python -u -m forex.noise_vwap.tests.test_parity`
  - `python -u -m forex.noise_vwap.scripts.run_grid`
  - `python -u -m forex.noise_vwap.scripts.entry_information`
- Primary evidence: `reports/FINDINGS.md`, `artifacts/runs/EXP-0001/review.md`,
  `artifacts/runs/EXP-0002/review.md`.

## Authoritative artifacts

- Specification: `paper/PAPER_SPEC.md`
- Data quality (rule 9a): `reports/DATA_QUALITY.md`
- Findings synthesis: `reports/FINDINGS.md`
- Hypotheses: `experiments/hypotheses/HYP-0001.md`, `HYP-0002.md`
- Runs: `artifacts/runs/EXP-0001/`, `artifacts/runs/EXP-0002/`

## Confirmed findings

- **A — NO-GO on all four pairs (EXP-0001).** Median gross −0.548 pips/trade
  (`fxday`) / −0.455 (`active`); best of 96 cells +0.241 pips against a 1.0 pip
  round trip; 0/4 pairs reach the +0.30 Sharpe bar (best −0.356). Null C not
  spent (gate rule: a real pass failing its primary metric is already a reject).
  Places FX at the far end of the workspace transfer ladder, past RTY.
- **B — the missing volume is NOT the cause (EXP-0001).** The fully volume-free
  `band` stop matches or beats the published `max(upper, twap)` rule on all
  eight pair/session combinations (Sharpe +0.09..+0.41 better, net pips/trade
  within ±0.13). The anchor's real role in this construct is the ENTRY GATE
  (+0.068..+0.164 Sharpe on all eight), not the stop. `anchor`-only has the
  least-bad Sharpe purely by trading 47% less while per-trade quality falls —
  the familiar turnover lever.
- **C — the failure is an absence of directional information, not an inverted
  edge (EXP-0002).** Exit-neutral forward returns through the identical code
  path: NQ +0.030..+0.103 band-widths (cluster-t up to +4.01), ES
  +0.026..+0.088, FX −0.062..+0.061 with no reliable sign. The preregistered
  inversion bar failed (2/4 pairs). The real residual is a weak short-horizon
  AUD/NZD reversion (−0.09..−0.19 pips, t −2.4..−4.4) that is 5–11x smaller
  than the round-trip cost, and it is concentrated in the thin Asia hours where
  the cost assumption is least defensible. Momentum direction SIGN-FLIPS
  between the two session definitions for EURUSD and GBPUSD.
- **D — per-signal and session-averaged estimands disagree in SIGN
  (EXP-0002).** GBPUSD `fxday` to-close: +0.010 pips (cluster-t +0.01)
  per-signal vs −9.655 pips (t −16.70) session-averaged. Cause: signal count is
  endogenous to the outcome (Q1 3.7 signals/session → −22.3 pips each; Q4 32.7
  → +13.2; corr +0.41). Correcting the inference **flipped EXP-0002's verdict**,
  and the same reversal appears on NQ/ES. **Promotion candidate.**
- **E — the FX archive's gaps are a download artifact (rule 9a).** Every
  sub-98% window starts on the hour and runs 15 minutes. Fixed by anchoring the
  FX day at 17:15 ET (not the nominal 17:00 roll, which gave NZDUSD a
  session-varying open) and pinning the decision clock to the ET wall clock
  (`:29`/`:59`), which cannot land in a hole. Both asserted in tests.
- **E update (2026-08-08):** fresh IBKR queries reproduced the NZD intervals,
  locating the defect in IBKR's historical archive rather than local chunking.
  The shared canonical NZD file is now a documented IBKR/LSE hybrid repair;
  rerun data quality reports show no sub-98% fixed windows. The 17:15 session
  anchor and ET decision clock remain frozen for experiment reproducibility.

## Provisional hypotheses

- None. Both registered hypotheses are resolved.

## Invalidated or superseded findings

- HYP-0001 (the strategy ports to FX with a TWAP anchor): **rejected**,
  EXP-0001, on the preregistered gross gate.
- HYP-0002 (the FX failure is an inverted entry): **rejected**, EXP-0002, at the
  preregistered bar (2/4 pairs). Note that the first pass of EXP-0002, using a
  session-averaged estimand, would have reported it as CONFIRMED; that reading
  is invalid and must not be cited.
- HYP-0002 criterion 3 ("fade beats momentum on gross") was **badly specified
  by the builder** and carries no information: in the exit-neutral cell the fade
  is the exact algebraic negation of the momentum version (same entries, same
  fills), so it can only ever return 4/4 or 0/4. Recorded rather than dropped.
  No verdict rests on it.

## Decisions and constraints

- TWAP is the VWAP formula under constant volume, not a new indicator; both
  directions of that claim are pinned in `tests/test_core.py`.
- `core/engine.py` is the definition of the rules. `core/engine_nb.py` must
  never diverge from it; `tests/test_parity.py` is the gate.
- The `fxday` session anchor is 17:15 ET and the decision clock is on the ET
  wall clock. Neither may be changed without re-running
  `scripts/data_quality.py` — both exist to neutralise a measured archive
  defect.
- 0.5 pip/side is optimistic for the `fxday` session (Asia hours and the daily
  roll). Any future `fxday` result must carry a wider cost assumption.

## Known risks and open questions

- Independent review of EXP-0001 and EXP-0002 is outstanding.
- The IBKR midpoint feed has no bid/ask, so the cost model is an assumption
  rather than a measurement. This does not threaten the NO-GO (gross is
  negative), but it would matter for any future FX work here.
- Finding D should be checked against the NQ/ES project's own headline
  statistics before it is promoted to `ai_shared_memory/LEARNINGS.md` as
  confirmed rather than provisional.

## Next actions

1. Obtain independent review of EXP-0001 and EXP-0002.
2. Do not spend further effort on this construct for FX. The recommended
   next steps for FX intraday research are recorded in `reports/FINAL_REVIEW.md`.
3. Consider promoting finding D after a second-project confirmation.

## Promotion candidates

- **Finding D** (per-signal vs session-averaged estimand sign disagreement when
  signal count is endogenous) — filed to `ai_shared_memory/LEARNINGS.md` as
  provisional.
- **Finding B** (substitute TWAP and use a no-anchor degenerate control to
  decide whether missing volume is actually the binding constraint) — filed as
  part of the same entry.

## Memory maintenance

- Run-level facts belong in the ledger; detailed analysis in `reports/`.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
