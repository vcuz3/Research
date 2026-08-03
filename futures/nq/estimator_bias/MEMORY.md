# Project Memory: Estimator bias in short-window persistence statistics (NQ/ES)

Concise handoff. Detailed evidence in `reports/FINDINGS.md` and
`artifacts/runs/EXP-0001/review.md`.

## Scope

- Objective: a cross-project **audit**, not an edge search. Size the finite-sample bias
  of persistence estimators at the window lengths this workspace actually uses, and
  determine which published conclusions it touches. Origin: `research_papers/
  ALIGRITHM_HYPOTHESES_2026-08.md` H-A2, from aligrithm.com *3.35 Trend and Reversion Are
  the Same, and OLS Understates Both* (2026-06-28) and *5.30 Order-Flow Autocorrelation*
  (2026-07-02).
- Instruments: NQ, ES (RTH 1-minute), plus synthetic AR(1) and fBm.
- Data coverage: `futures/nq/data/{NQ,ES}_1m_clean.parquet`, 2011-08 -> 2026-07.
  3,710 sessions (VEI loader) / 3,703 NQ + 3,706 ES complete-grid (Hurst loader).
- **No holdout exists or is relevant** — this audits published results on
  already-consumed exploratory data.
- Current phase: EXP-0001 complete; independent review pending.

## Current status

- Verdict: **hypothesis NOT killed**; all three preregistered cells landed as predicted.
- Last verified: 2026-08-03
- Lifecycle phase: hypothesis/experiment loop, one experiment closed
- Baseline replication: **not applicable** — no source paper. `paper/` is empty by design.
- Engine audit: **not applicable** — no execution engine; nothing here trades.
- Holdout status: not applicable
- Experiment ledger: `experiments/ledger.csv` (EXP-0001, completed)
- Reproduction commands:
  ```powershell
  .\.venv\Scripts\python.exe -m futures.nq.estimator_bias.tests.test_core
  .\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s1_bias_table
  .\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s2_pooled_ac1 {NQ|ES}
  .\.venv\Scripts\python.exe -u -m futures.nq.estimator_bias.scripts.s3_hurst_gate {NQ|ES}
  ```
- Primary evidence: `reports/FINDINGS.md`, `artifacts/runs/EXP-0001/review.md`

## Authoritative artifacts

- Current findings: `reports/FINDINGS.md`
- Hypothesis: `experiments/hypotheses/HYP-0001.md`
- Run review: `artifacts/runs/EXP-0001/review.md`
- Core (tested): `core/arbias.py`; `tests/test_core.py` (18 checks, all passing)

## Confirmed findings

- **A. The small-sample bias is irrelevant to this workspace's INFERENCE and material to
  its FEATURES.** At T = 44,516 (the pooled AC1) max |bias| is **0.00025**; at T = 30 (the
  Hurst gate's first window) it is **0.122** and sd(phi_hat) is 0.163. Do not
  bias-correct our pooled IC/reversion statistics — the effort is wasted.
- **A1. Kendall's `-(1+3phi)/T` is accurate for T >= 30 and FAILS at T = 13** (predicts
  +0.0154 against a measured +0.0001 at phi = -0.4). **Below T ~ 20 use
  `bootstrap_ar1_correct`, not the closed form.** The two correctors agree to 0.03 at
  T = 60 and diverge to 0.12 at T = 13. Requiring two correctors is what surfaced this.
- **B. `vei_exploration`'s AC1 column reproduces exactly (8/8 cells to 1e-4) and is immune
  to the bias (max move 0.00006) — but roughly HALF of it is the intraday clock.**
  Slot-demeaning takes `wilder_10_50` from +0.4411 to +0.2198 (NQ) and +0.4036 to +0.2007
  (ES); `L:ema_10_50` from +0.1609 to +0.0048 / +0.1386 to +0.0002, i.e. entirely clock.
  The wilder > ema > sma **ranking survives**, so that project's estimator choice stands;
  its magnitude should be halved. Pooling across a deterministic profile INFLATES a
  persistence statistic — the opposite direction from small-sample bias.
- **C. The `noise_vwap` expanding-window Hurst gate is substantially a time-of-day
  selector.** Per-slot selection-rate CV vs a same-slot z at matched global rate:
  **NQ 2.88x-45.59x (median 23.93x), ES 5.90x-46.48x (median 21.75x)**, at all 7 published
  thresholds — kill threshold was 2.0x. At `H >= 0.55` the gate fires on **33.5% of 10:00
  decisions and 8.4% of 15:59 decisions on NQ** (31.7% -> 5.2% ES), monotonically.
- **C1. The mechanism is DISPERSION, not level.** Mean H moves 0.0225 (NQ) / 0.0203 (ES)
  across the 13 windows while sd compresses **3.80x / 3.54x**. The CV ratio is smallest at
  `H >= 0.50`, nearest the distribution's centre — the defect is worst exactly where a
  selective gate operates.
- **C2. A zero-memory path reproduces about half the gradient.** The `signflip` control
  (real |returns|, iid random signs — real volatility seasonality preserved, true
  H = 0.50) ramps 0.330 -> 0.141 (NQ) / 0.333 -> 0.161 (ES) by itself, and is still
  9.8-10.6x worse calibrated than a same-slot z. A constant-vol fBm control agrees, ruling
  out volatility seasonality as the driver.

## Provisional hypotheses

- **`noise_vwap`'s "Hurst LEVEL is a real per-trade quality signal (beats matched random
  NQ p=0.03)" is confounded with time of day and not separately established.** That null
  matched COUNT, not TIME OF DAY, and finding C shows the gate fires 4-6x more often in
  the morning — where `noise_vwap` separately documents super-diffusion and the strongest
  part of its own edge.
  - Kill test: re-run the per-trade comparison against a **slot-matched** random null, or
    against a same-slot z-scored H at matched selection rate. If the per-trade advantage
    survives, the claim stands as published.
  - Evidence needed: one run in `noise_vwap`; nothing new to build. Not urgent — the gate
    is already rejected as selection, exit and sizing, so nothing deployed depends on it.

## Invalidated or superseded findings

- None. Nothing in this project overturns a prior conclusion; finding B halves a
  magnitude and finding C re-opens a descriptive claim (see "Provisional").

## Decisions and constraints

- `core/arbias.py::ghe1` is copied **verbatim** from
  `noise_vwap/scripts/hyp_0017_hurst_filter.py`, including the `LAGS <= n // 2` cap, and
  is pinned by `test_ghe1_constants_still_match_the_audited_script`, which re-reads that
  file. If that script's `LAGS` or `H_GRID` ever change, the test fails and this audit
  must be re-run.
- `pooled_lag1_slot_demeaned` uses the FULL-SAMPLE per-slot mean on purpose. It is a
  diagnostic decomposition of a published descriptive statistic, **not a causal feature**,
  and must not be lifted into a strategy in that form.
- Studies 2 and 3 use different session gates by design (`vei_exploration`'s loader vs
  `hurst_explore`'s complete-grid rule, which Hurst estimators require). The 7-session
  difference cannot affect any conclusion here.

## Known risks and open questions

- **Declared deviation from the preregistration:** Cell C (`claude_exploration_1`'s
  reversion retention) was **bounded analytically rather than re-run**. Study 1 measures
  the maximum possible bias at T = 44,516 as 0.00025 — two to three orders of magnitude
  below the published effects and their CIs — so the verdict could not have changed. The
  direct reproduction was nevertheless not executed. A reviewer who disagrees should ask
  for it.
- One project on a **sibling pair**: NQ+ES agreement is cheap corroboration, not
  independent replication. The mechanism is arithmetic and durable; its SIZE on another
  instrument or estimator is not established.
- Independent reviewer sign-off is pending on all of the above.

## Next actions

1. Independent review of EXP-0001.
2. Close the provisional item: run the slot-matched null for `noise_vwap`'s per-trade
   Hurst claim (one run, in that project).
3. Optional, cheap: apply the finding-C diagnostic to any other thresholded feature whose
   estimation window varies — the FX projects' 46-slot clock is the obvious next host.

## Promotion candidates

- Promoted to `ai_shared_memory/LEARNINGS.md` on 2026-08-03 as **provisional**: the
  window-length mechanism, the DISPERSION-not-level reading, the `signflip` degenerate
  control, and the "two correctors disagree below T~20" methodological point. Named
  confirming test is in that entry.

## Memory maintenance

- Put run-level facts in the ledger and detailed analysis in reports.
- Label claims confirmed, provisional, invalidated, or superseded.
- Never relabel explored data as a sealed holdout.
