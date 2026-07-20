# EXP-0022 review — Asymmetric (per-side) noise band (HYP-0014, transform 3)

- Date: 2026-07-20
- Builder: Claude (Opus 4.8)
- Hypothesis: `experiments/hypotheses/HYP-0014.md`
- Band code: `core/bands.py::noise_bands_asymmetric` (tested, `tests/test_bands.py`)
- Script: `scripts/hyp_0014_asymmetric_band.py`
- Evidence: `asym_nq.txt`, `asym_es.txt`
- Reproduce:
  `python -m futures.nq.noise_vwap.scripts.hyp_0014_asymmetric_band real {NQ|ES}`

## What was tested

Transform 3 (anchor/symmetry) of the noise-area recast programme, and the last
remaining lever after EXP-0020 (cone) and EXP-0021 (quantile) showed the dispersion
is fully summarized by its per-slot LEVEL. The baseline sizes BOTH band edges from
one symmetric statistic sigma = mean(|move|). The asymmetric band splits it into a
separate up and down half-width from the causal semi-means:

    move = close/open0 - 1  (signed)
    up   = mean_{prior 90} max(move, 0)      dn = mean_{prior 90} max(-move, 0)
    up + dn == sigma  (identically, same window)

    sig_up   = sigma + tilt*(2*up - sigma)      sig_dn = sigma + tilt*(2*dn - sigma)
    sig_up + sig_dn == 2*sigma   for EVERY tilt

tilt=0 is the baseline bit-exact; tilt=1 is the full empirical split (sig_up=2*up,
sig_dn=2*dn); tilt=1.5 over-tilts. Everything else is the faithful working config
(lookback 90, 30-min RTH clock, VWAP gate, every-bar band/VWAP stop, next-open
fills, explicit costs). Grid {0.5, 1.0, 1.5}. NQ primary + ES sibling on the common
post-lookback-90 date set (consumed).

## No width-dial confound (the trap that killed EXP-0010/0012/0021)

Unlike every prior "looser band → higher Sharpe" study, this construction conserves
the TOTAL half-width budget for every tilt (`sig_up + sig_dn == 2*sigma`, proved in
`tests/test_bands.py::test_total_halfwidth_conserved`). So the change is a PURE
up/down REDISTRIBUTION of the baseline width, never a capacity dial — no RAW-vs-
MATCHED split is needed. Coverage is identical to the baseline (same per-slot
`min_periods=90`), so this is not a Rule-9a deletion effect either.

## Result — REJECT on both markets (no Null C spent)

NQ (baseline Sh 1.29, netR +91.2R):

| band       |    n | grossR | netR | net_pt/t |   Sh |   dSh | maxDD | 23+Sh |
|------------|------|--------|------|----------|------|-------|-------|-------|
| mean(base) | 4209 | +111.2 | +91.2| +3.159   | 1.29 | +0.000| 4.7   | 1.10  |
| tilt 0.5   | 4183 | +105.6 | +85.8| +3.035   | 1.22 | −0.065| 5.1   | 1.04  |
| tilt 1.0   | 4193 | +103.7 | +83.7| +3.107   | 1.19 | −0.095| 5.5   | 1.13  |
| tilt 1.5   | 4251 | +103.7 | +83.4| +3.102   | 1.18 | −0.110| 6.3   | 1.07  |

Monotonically WORSE in tilt; best tilt 0.5 dSharpe −0.065 and netR −5.4R. Gate FAIL.

ES (baseline Sh 0.70, netR +51.5R):

| band       |    n | grossR | netR | net_pt/t |   Sh |   dSh | maxDD | 23+Sh |
|------------|------|--------|------|----------|------|-------|-------|-------|
| mean(base) | 4326 | +90.2  | +51.5| +0.515   | 0.70 | +0.000| 7.4   | 0.80  |
| tilt 0.5   | 4357 | +89.6  | +50.8| +0.493   | 0.68 | −0.013| 6.9   | 0.61  |
| tilt 1.0   | 4312 | +91.7  | +53.4| +0.491   | 0.72 | +0.023| 7.0   | 0.63  |
| tilt 1.5   | 4405 | +84.6  | +45.1| +0.449   | 0.60 | −0.093| 12.9  | 0.60  |

Best tilt 1.0 dSharpe +0.023 / dNetR +1.9R — far below the +0.10 gate; tilt=1.5
collapses (maxDD 7.0→12.9R). Gate FAIL.

Per the standing rule (a real pass failing the primary metric is already a REJECT),
no Null C was spent on either market.

## Decisive diagnostic — the tape IS asymmetric, but acting on it hurts

The per-side residual at tilt=1 (sig_up/sigma, sig_dn/sigma by decision slot) is the
same structural signature on BOTH markets: the up-edge is ~2–5% WIDER than symmetric
and the down-edge ~2–5% NARROWER, consistently across ALL 13 slots, largest mid-day
(mfo 329–359, up/dn ≈ 1.09–1.10 NQ / 1.10 ES), minimal at mfo 89 (up/dn ≈ 1.00 — the
one slot where the trailing window's up and down magnitudes balance). That up-tilt is
exactly the index up-drift showing in the up semi-mean, and it transfers NQ↔ES = real
tape structure, not estimation machinery.

But it is SMALL (~4–10%), and monetizing it via band width degrades performance:
- On NQ (strong drift) it actively HURTS. A momentum breakout system WANTS to catch
  the drift-driven up-breakouts; widening the up-threshold (sig_up up) makes those
  breaks harder and rejects the trades that carry the edge, while narrowing the
  down-threshold (sig_dn down) admits more counter-drift down-breaks. The symmetric
  band is not merely adequate — it is actively BETTER than sizing to the empirical
  asymmetry, because that asymmetry is a DRIFT property the strategy already
  monetizes (VWAP gate + ride-to-close); re-sizing the band to it double-counts and
  mis-selects. Gross/trade falls (3.159→3.107) and maxDD worsens (4.7→5.5R).
- On ES (weak drift) it is a wash within noise (best +0.023, well inside the gate).

## Synthesis — the recast programme is exhausted

Transforms 1–3 all reject as risk-adjusted improvements:
- 1 (cone, EXP-0020): a √t reshape of the intraday time profile — WORSE (the
  empirical super-diffusive morning is load-bearing).
- 2 (quantile, EXP-0021): a per-slot distributional reshape — inert at matched width
  (the mean is a sufficient statistic for the band).
- 3 (asymmetric, EXP-0022): an up/down redistribution at conserved total width —
  inert-to-harmful (the up/down asymmetry is a drift property already monetized).

Neither the dispersion's time-profile shape, nor its per-slot distributional shape,
nor its up/down symmetry adds value. The noise-area band is fully summarized by its
per-slot SYMMETRIC LEVEL/width. Retain the faithful mean band.

## Verdict

- Decision: REJECT (cross-market NO-GO). No Null C spent (both real passes fail the
  primary metric).
- Reviewer: Claude (Opus 4.8), 2026-07-20. REJECT confirmed; no blocking objections.
  The width-conservation invariant (tested) rules out a capacity-dial confound; the
  persistent up-tilt residual is a recorded real tape property, not machinery.
- Retain: `core/session.py::noise_bands` (symmetric mean band). The asymmetric band
  stays in `core/bands.py` as tested reusable machinery / the per-side benchmark.
