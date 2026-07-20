# EXP-0020 — Diffusion-cone recast of the Noise Area (HYP-0012)

- Hypothesis: `experiments/hypotheses/HYP-0012.md`
- Builder: Claude (Opus 4.8), 2026-07-20
- Phase: experiment
- Status: completed — REJECT (cross-market NO-GO as a band replacement)
- Command:
  - `python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real NQ`
  - `python -m futures.nq.noise_vwap.scripts.hyp_0012_diffusion_cone real ES`
- Evidence: `cone_nq.txt`, `cone_es.txt` (this directory)
- Code: `core/bands.py` (`session_vol`, `noise_bands_cone`),
  `scripts/hyp_0012_diffusion_cone.py`, `tests/test_bands.py`

## What was tested

Swap ONLY the noise-area band construction, everything else held at the working
baseline (lookback 90, 30-min RTH decision clock, VWAP gate, every-bar band/VWAP
stop, next-open fills, explicit costs):

- Baseline: `core/session.py::noise_bands` — per-slot empirical mean of
  same-time-of-day |close/open − 1| over the prior 90 sessions.
- Treatment: `core/bands.py::noise_bands_cone` — `sigma[d,mfo] =
  sigma_session[d]·√(mfo/M)`, one causal per-session vol scalar
  (mean prior-90 `|session_close/session_open − 1|`) × a √t profile. Calibrated so
  it equals the baseline's final-slot sigma → matched end-of-day width, isolating
  intraday SHAPE not width.

## Result (both markets)

| market | ΔSharpe | ΔnetR | Δtrades | net pt/trade (base→cone) | verdict |
|--------|---------|-------|---------|--------------------------|---------|
| NQ | −0.101 | −1.4R | +705 | 3.159 → 2.530 | REJECT |
| ES | −0.125 | −7.5R | +436 | (see cone_es.txt) | REJECT |

The cone is WORSE, not equal — so neither the alpha gate (ΔSharpe ≥ +0.10 & netR ≥
baseline) nor the simplification outcome (|ΔSharpe| ≤ 0.05 & coverage win) is met.
Per the standing rule, a real pass that fails the primary metric is already a
REJECT and spends no Null C.

## Why — the residual m(mfo) (positive finding)

`m(mfo) = mean_empirical_sigma / mean_cone_sigma` per decision slot:

| mfo (ET) | NQ ratio | ES ratio |
|----------|----------|----------|
| 29 (09:59) | 1.544 | 1.352 |
| 59 (10:29) | 1.391 | 1.261 |
| 89 (10:59) | 1.308 | 1.201 |
| 149 (11:59) | 1.178 | 1.101 |
| 209 (12:59) | 1.079 | 1.021 |
| 269 (13:59) | 1.011 | 0.969 |
| 389 (15:59) | 1.000 | 1.000 (calib) |

On BOTH markets the empirical band is ~1.35–1.55× WIDER than the √t cone in the
first hour and converges to 1.0 at the close. Real intraday displacement is
**super-diffusive in the morning** (an opening-volatility bulge wider than a
driftless random walk). The end-of-day-calibrated cone is therefore too narrow
early, admits noisier morning breakouts (+705 NQ / +436 ES trades), and dilutes
per-trade quality. The per-slot empirical shape is load-bearing — specifically the
morning — and the effect transfers across the sibling pair, so it is a real
property of the index tape, not machinery. This answers HYP-0012's core question
("is any per-slot shape needed?") = YES.

## Coverage (Rule-9a)

The cone recovers only 90 decision points (0.2%, all at mfo 209 ≈ 13:29 ET, ~lunch)
on both NQ and ES. The coverage win is real but negligible on liquid index futures —
consistent with the prior learning that the strict `min_periods` deletion bites
THIN markets (GC/YM/RTY), not NQ/ES. On a thin instrument the cone's coverage
robustness would matter more, but it does not rescue the morning super-diffusion
mis-shaping.

## Alternative explanations considered

- Is the loss just "cone trades more" (a capacity/width artifact)? No — width is
  matched at end of day by construction; the extra trades are a direct consequence
  of the too-narrow morning band, i.e. the shape defect itself, and per-trade
  quality falls (not just trade count).
- Is it NQ-tape-specific? No — ES reproduces both the sign and the residual shape.

## Verdict

REJECT the diffusion cone as a replacement for the empirical band. Retain
`core/session.py::noise_bands`. Bank the super-diffusive-open residual as a
cross-market structural finding that should shape transform 2 (quantile) and
transform 3 (asymmetric): any parsimonious re-cast must reproduce the morning
excess width, not assume √t. The cone code stays in `core/bands.py` as reusable,
tested machinery and as the reference "pure-diffusion" benchmark.

## Reviewer

- Reviewer: Claude (Opus 4.8), 2026-07-20
- Decision: REJECT confirmed — concur with builder; cross-market NO-GO, no Null C
  warranted (real pass fails the primary metric).
- Objections: none blocking.
