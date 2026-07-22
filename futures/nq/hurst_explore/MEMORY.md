# Project Memory: Hurst Exploration (NQ/ES)

Concise handoff. Detailed evidence in `reports/FINDINGS.md` and
`artifacts/runs/EXP-*/`.

## Scope

- Objective: characterize the Hurst exponent of intraday NQ/ES as its own object
  (measurability + timescale structure) before any trading use. Follows the
  noise_vwap result that intraday H is a real per-trade quality signal that
  monetized as neither selection, exit, nor sizing.
- Instruments: NQ, ES (RTH). 1s data is NQ-only (ES 1s not in archive).
- Data: NQ/ES 1m clean 2011-08→2026-07 (3710 sess each); NQ 1s Databento
  2010→2026 (use fill≥0.90 & era≥2015 for scale work).
- Current phase: exploratory characterization (A-series). A1 + A2 corrected and
  validated in EXP-0003/0004; independent reviewer sign-off remains pending.

## Current status

- Verdict: two descriptive studies complete; no trading claim yet.
- Last verified: 2026-07-22.
- Estimator core: `core/hurst.py` (ghe q=1/q=2, R/S, DFA, ghe_spectrum, fBm
  Davies-Harte) validated in `tests/test_hurst.py` plus review regressions in
  `tests/test_analysis.py` (9 total tests pass via module runners).
- Reproduction: `python -u -m futures.nq.hurst_explore.scripts.{a1_measurement_floor,a2_timescale}`.
- Primary evidence: `reports/FINDINGS.md`.

## Confirmed findings

- **A1 (EXP-0001): an intraday H at a short window is mostly noise.** Synthetic
  std(Ĥ) for H=0.5 is 0.17–0.30 at n=30 bars (the window the noise_vwap Hurst
  filter STARTED from at its first 30-min decision), 0.04–0.09 at the full 1m day,
  0.015–0.04 at the full 1s day. Backs why that early-session H signal was
  real-but-marginal. 1s cuts the floor ~2–3× vs full 1m day.
- **A1 correction (EXP-0003): estimator bias explains much, not all, of the
  real-data split.** Executable inverse calibration gives NQ H=0.473–0.499 and
  ES H=0.466–0.485 across estimators. Report the panel as near-random-walk to
  mildly anti-persistent; do not collapse it to H=0.50. On 149 matched eligible
  dates, minute-plus GHE1 is 0.490 on 1s versus 0.471 on 1m.
- **A2 (EXP-0002, validated EXP-0004): Hurst term structure H(τ) declines with scale**, control-
  corrected: micro 1–8s ≈0.503, meso 2–30m ≈0.49, coarse 30–180m 0.462 (NQ) /
  0.468 (ES) = mild anti-persistence. Transfers NQ↔ES and 1s↔1m (meso agree to
  0.003 in overlap) = real structure. The RW control showed **~40% of the raw
  coarse anti-persistence (0.43) was finite-sample saturation artifact**. The
  full-sample coarse result has block-bootstrap CI NQ [0.432,0.490], ES
  [0.440,0.495], but recent-era and widest ES endpoint intervals include 0.5:
  retain it as mild and era-dependent, not a universal law.
- **A2: the prior micro-anti-persistence expectation was WRONG.** 1s OHLCV is too
  coarse to resolve the bid-ask bounce (needs true tick, not entitled — Databento
  trades ≈$1,140/16y). Micro H≈0.50.
- The A2 stationary-lag mean-reversion is a DIFFERENT object from the confirmed
  anchored-at-open morning super-diffusion (cone learning): time-of-day dispersion
  growth vs translation-invariant lag persistence. Reconcile in A3.

## Provisional hypotheses

- None promoted to a trading claim.

## Invalidated or superseded findings

- Superseded: EXP-0001's narrative “bias-corrected H≈0.49–0.50 on NQ and ES.”
  EXP-0003 executable calibration gives the wider/lower panel above.
- Superseded: EXP-0002 wording that cross-frequency/market agreement was
  independent proof of a structural law. It is useful corroboration, while
  EXP-0004 shows era dependence.

## Decisions and constraints

- A-series is descriptive (no Null-C). B-series (predictive) / C-series (strategy)
  MUST add a claim-matched null + fill feasibility; any 1s bracket/fade needs 1s
  intrabar resolution (GC coarse-bar-fill learning).
- 1s scale work: fill ≥ 0.90, era ≥ 2015; calibrate estimator bias explicitly.
- Hurst inputs require exact regular grids; 7 NQ and 4 ES incomplete 1m sessions
  are excluded and reported in EXP-0003 `data_quality_1m.csv`.

## Known risks and open questions

- Independent reviewer sign-off of corrected EXP-0003/0004 is pending.
- Five-session bootstrap block length and the RW control's omission of intraday
  volatility seasonality remain sensitivity questions.
- Sub-minute microstructure blocked by tick-data entitlement.

## Next actions

1. Independent review of EXP-0003/0004.
2. A3 (H by time of day: reconcile with the cone) and/or A4 (multifractality H(q)).
3. B1: does the coarse-scale exponent / H forecast forward realized range? (the
   dispersion-not-direction pivot) — this is where a tradable follow-on would start.
