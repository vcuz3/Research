# RSI/z fade — directional-EFFICIENCY conditioner (FROZEN SPEC)

Frozen 2026-08-05, before the material run. Preregisters the primary metric, the
kill test, the controls, and the data scope (rule 24). This is a **screen** on
consumed history (2012–2023); the 2024+ holdout stays sealed (rule 26).

## Question / mechanism

The RSI/z mean-reversion fade's fatal component is the non-reverting tail (6–7.5%
of signals remove 52–79% of gross). Mechanistically those are the cases where a
`|z| >= 1.5` extreme is the **start of a directional run**, not a stretched-and-
snapping-back move. A **directional-efficiency** conditioner measures exactly that,
and — unlike every conditioner tested so far — it is a different variable from both
the displacement magnitude (`|z|`, RSI: the *same* variable, Spearman 0.97) and the
volatility level (`abs_sigma`, `rv30_pct`, `vei_atr_z`). That orthogonality is the
whole point: only a variable independent of `|z|` and of σ can clear the frontier-
excess bar for a reason other than selectivity or a volatility tilt.

**Preregistered direction (must not be flipped post hoc):** reversion is BETTER in
LOW-efficiency (choppy, range-bound) states and WORSE in HIGH-efficiency (trending)
states. A gate that keeps the LOW-efficiency fraction should raise entry quality.

## Features (causal, full minute grid)

- **KER** — Kaufman Efficiency Ratio over `KER_WIN = 30` min:
  `|logc_t − logc_{t−30}| / Σ_{i} |logc_{t−i+1} − logc_{t−i}|`, both terms
  exact-contiguous (defined only when the trailing 30 min are gap-free, exactly as
  `rv_30m`). Range [0,1]; ~1 = straight-line move (efficient/trending), ~0 = chop.
- **ADX** — Wilder ADX(14), intraday, session-reset, SMA-seeded Wilder smoothing
  (same estimator family as `vei_atr`). High = trending, low = ranging. DX is NaN
  during the per-session warmup, so the ADX smoother seeds from the first `length`
  *valid* DX values of each session (never resets across the rollover gap).
- **HTF slope** — `htf_slope = logc_t − logc_{t−120}` (exact-contiguous, `HTF_WIN =
  120` min). Sign only is used, to test with-trend vs counter-trend fades.

**Normalisation.** The primary gate uses the causal **same-slot z-score** of KER
and ADX (`slot_z`, 90-session, prior sessions only), NOT a fixed cut on the raw
feature. This is mandatory here: KER/ADX carry a deterministic per-slot level drift
(session-reset warmup + time-of-day liquidity), and a fixed cut on such a feature is
a known time-of-day selector in this workspace (LEARNINGS 2026-07-27, 2026-08-03).
A **fixed-cut-on-raw-KER** arm is also run, but only as a transparency contrast; the
slot-z gate is the arm that is read.

## Engine / estimand (identical to the confirmed regime-matrix setup)

- Event clock (first crossing of `|z| >= 1.5`), non-overlap (rule 13), single
  compulsory stop at `STOP_K = 2.0` R, `SLIPPAGE = 1.0` pip, `HORIZON = 30` min.
- Delays 0 and 1; **delay 1 is the honest primary** (edge is front-loaded).
- Gate cutpoints fitted on the EARLY era only (`early_cut` / a low-side twin),
  applied unchanged to the late era.
- Low-side keep fractions {0.40, 0.20, 0.10}. Each arm gates the `z1.5` base.

This deliberately matches `RSI_Z_REGIME_MATRIX_SPEC.md` (2R, 30 min, event clock) so
the ONLY moving part vs the confirmed regime family is the conditioning variable. If
low-efficiency clears here, a follow-up tests whether it STACKS on the 240-min
`abs_sigma` candidate (3R); that is out of scope for this screen.

## Primary metric & KILL TEST

Primary = **excess mean R over the `|z| >= k` frontier**, linearly interpolated in
log(signals/year) to each arm's own rate (an arm ON the frontier added nothing but
selectivity). Reported at delay 1, median across the four pairs, mean R beside mean
pips.

- **SUPPORTED** if median excess ≥ **+0.005 R** AND ≥ **3/4 pairs** positive AND the
  effect survives at delay 1 (not just delay 0). Then, and only then, run a
  claim-matched donor-matched permutation null (separate script) before any
  confirmatory reading (rules 16–18).
- **REJECTED (worse than frontier)** if median excess ≤ −0.005 R.
- **REJECTED (selectivity dial)** if |median excess| < 0.005 R.
- **DIRECTIONAL KILL:** the LOW-efficiency gate must beat its HIGH-efficiency
  mirror. If HIGH-efficiency ≥ LOW-efficiency, the choppiness→reversion thesis is
  falsified regardless of any excess (the excess would then be a volatility/rate
  artefact, not directional efficiency).

## Guardrails (reported on every arm)

- **mean R beside mean pips**, and the **implied risk unit** (`mean_pips/mean_R`) —
  if the low-efficiency gate wins by shifting the risk unit (selecting a different
  volatility), it is a σ selector, not an efficiency effect (rule 19; LEARNINGS
  2026-08-04). A genuine efficiency effect should leave the risk unit ~unchanged.
- **Feature-coverage report:** how many `z1.5` base signals are dropped per era for
  a not-yet-defined KER/ADX (rule 9a); confirm the deletion is not time-of-day
  selective.
- **HTF with-trend vs counter-trend** arms report both sides so an asymmetry cannot
  be read as an entry edge (rule 15).
- Correlated pairs ≈ 2–3 effective tests; EURUSD is the weakest member and inverts
  to momentum at long horizon — never read a panel median without it.

## Arms

Frontier: `z ∈ {1.0,1.25,1.5,1.75,2.0,2.25,2.5,3.0}` (reference curve).
Gates on the `z1.5` base, event clock, 2R stop:

- `low_ker_z {40,20,10}` — keep the LOWEST slot-z KER (choppiest). PRIMARY.
- `high_ker_z {40,20,10}` — mirror (keep the HIGHEST; trending). DIRECTIONAL KILL.
- `low_adx_z {40,20,10}` / `high_adx_z {40,20,10}` — ADX sibling + its mirror.
- `low_ker_raw {40,20,10}` — fixed low-side cut on raw KER (transparency contrast).
- `withtrend` — fade only when side agrees with sign(htf_slope) (dip-in-uptrend).
- `countertrend` — mirror (fade only counter-trend extremes). Control for `withtrend`.
- `low_ker_z20 AND low_adx_z20` — combined (do the two independent axes stack?).

## Reproduce

```
python -u _test_efficiency_features.py
python -u _run_rsi_efficiency_gate.py
```

Outputs: `rsi_efficiency_gate_results.json`, `rsi_efficiency_gate.csv`, and the
report `RSI_EFFICIENCY_GATE_REPORT.md`.
