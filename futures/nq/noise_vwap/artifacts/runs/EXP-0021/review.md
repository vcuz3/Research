# EXP-0021 — Quantile envelope vs the mean noise band (HYP-0013)

- Hypothesis: `experiments/hypotheses/HYP-0013.md`
- Builder: Claude (Opus 4.8), 2026-07-20
- Phase: experiment
- Status: completed — REJECT (cross-market NO-GO as a band replacement)
- Command:
  - `python -m futures.nq.noise_vwap.scripts.hyp_0013_quantile_band real NQ`
  - `python -m futures.nq.noise_vwap.scripts.hyp_0013_quantile_band real ES`
- Evidence: `quant_nq.txt`, `quant_es.txt` (this directory)
- Code: `core/bands.py::noise_bands_quantile`, `scripts/hyp_0013_quantile_band.py`,
  `tests/test_bands.py`

## What was tested

Swap ONLY the per-slot dispersion statistic: baseline MEAN of |move|
(`core/session.py::noise_bands`) vs qth PERCENTILE
(`core/bands.py::noise_bands_quantile`), q ∈ {0.50, 0.65, 0.80, 0.90}. Everything
else fixed (lookback 90, 30-min RTH clock, VWAP gate, every-bar stop, next-open
fills, costs). Two views:

- RAW (scale 1.0): exposes the width/capacity dial (a higher q is a wider band).
- MATCHED: each q rescaled by a fixed constant so its median sigma equals the mean
  band's, isolating the distribution-SHAPE effect (robustness to outlier trend days)
  from width.

## Result

| market | best MATCHED q | ΔSharpe | ΔnetR | verdict |
|--------|----------------|---------|-------|---------|
| NQ | 0.90 | +0.032 | +1.4R | REJECT (< +0.10 gate) |
| ES | 0.90 | +0.067 | +5.2R | REJECT (< +0.10 gate) |

At matched width every quantile cell collapses onto the mean band. No Null C spent
(matched real pass fails the primary metric).

## Decisive diagnostic — residual quant/mean by slot ≈ 1.0

The best matched q=0.90 residual (mean_quantile_sigma / mean_mean_sigma) by decision
slot is 0.96–1.01 across the whole day on BOTH markets. The matched quantile band is
just the mean band RESCALED — it does not reshape the intraday profile. So the
per-slot |move| distribution's SHAPE carries no exploitable information beyond its
LEVEL; the mean is a sufficient statistic for the band at fixed width.

## The RAW "win" is the capacity dial, not the quantile

In the RAW view, q0.50 (the median — narrower than the mean ≈ q0.57) trades MORE
(NQ 5175 vs 4209) and books more money (NQ netR 101.9 vs 91.2, Sh 1.34; ES netR 53.8
vs 51.5). This is the width/capacity dial (a narrower band = more exposure to the
intraday drift), already understood as a turnover/capacity lever (cf. the
k-multiplier WFO, EXP-0010/0012), NOT a quantile effect. It appears and disappears
purely with band width, and vanishes in the MATCHED view.

## Synthesis with EXP-0020

- Cone (EXP-0020): a √t SHAPE reshape is worse — the empirical per-slot shape
  (super-diffusive morning) is load-bearing.
- Quantile (EXP-0021): a distributional reshape at fixed width adds nothing — the
  per-slot LEVEL is a sufficient statistic.
Together: the noise-area dispersion is fully summarized by its per-slot LEVEL/WIDTH.
The remaining untested lever in the programme is the ANCHOR/symmetry (transform 3,
asymmetric/directional), not the dispersion statistic.

## Reviewer

- Reviewer: Claude (Opus 4.8), 2026-07-20
- Decision: REJECT confirmed — concur with builder; cross-market NO-GO, no Null C
  warranted.
- Objections: none blocking.
