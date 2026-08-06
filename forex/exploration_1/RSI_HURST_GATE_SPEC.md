# RSI/z fade — Hurst-exponent regime conditioner (FROZEN SPEC)

Preregistered 2026-08-05, before the run. Screen on consumed history (2012–2023);
2024+ sealed and NOT opened by this work.

## Question

Does the recent path's **self-similarity / persistence regime**, measured by a Hurst
exponent, condition the quality of a `|z| >= 1.5` mean-reversion fade — and does it add
anything **beyond** the ADX/KER directional axis already tested and the confirmed
volatility gate?

## Estimator — built to avoid the known landmine (LEARNINGS 2026-08-03)

A persistence estimate on a GROWING (session-to-date) window has a sampling SD that
shrinks through the session, and a fixed threshold on it is a time-of-day selector (this
is the exact defect in `noise_vwap`'s Hurst gate). This spec avoids it:

- **Fixed-length trailing window** `HURST_WIN = 120` one-minute bars (constant sampling
  dispersion across the session), exact-contiguous and causal (defined only when the
  trailing 120 bars are gap-free, exactly like `z` and `rv_30m`; every value uses bars
  `<= t`).
- **Generalized Hurst exponent, order 1:** `H = OLS slope of log <|logc(s) − logc(s−tau)|>
  vs log(tau)` over `TAUS = (1, 2, 4, 8, 16)`, the average taken over the trailing window.
  H ≈ 0.5 random walk, H > 0.5 persistent/trending, H < 0.5 anti-persistent/mean-reverting.
- **Same-slot z-score** `hurst_z = slot_z(hurst)` (90-session, prior sessions only,
  estimated on the full minute grid, read at event rows) — removes any residual per-slot
  level/scale drift so a fixed cut on `hurst_z` is NOT a clock.

## Engine — identical to the confirmed regime matrix (only the gate moves)

Event clock (first crossing), non-overlap (rule 13), compulsory 2.0 R single-barrier
stop, 1-pip adverse slippage, 30-min horizon. Primary at delay 1; delay 0 shown.
Cutpoints fitted on the EARLY era only, applied unchanged to LATE. Every arm scored as
**excess mean R over the `|z|` frontier** interpolated in log(signals/year) to its own
rate — an arm on the frontier added nothing but selectivity.

## Direction — both sides run; the kill test decides (no post-hoc flip)

Primary hypothesis is the **classical** one: LOW Hurst (anti-persistent, mean-reverting
regime) → better reversion. But the just-confirmed ADX result (HIGH directional strength
→ better reversion) predicts the OPPOSITE, so BOTH `low_hurst_z` and `high_hurst_z` gates
are run at keeps {40, 20, 10} and the directional kill (low vs high mirror) decides.
Because both directions are searched, any survivor's confirmatory null (step 2) corrects
selection over BOTH directions × all keeps (rule 17).

## Metric and staged kill test

**Screen (this run):** an arm is SUPPORTED iff median excess `>= +0.005 R` AND `>= 3/4`
pairs positive at delay 1, and delay 0 does not contradict.

- If NO arm is supported → **NO-GO**, log the negative result (rule 25), done.
- If an arm is supported → it is a screen-generated candidate only. Step 2 (a separate
  run) must clear BOTH: (1) a selection-corrected claim-matched donor null over the whole
  Hurst search; and (2) a **redundancy check against the ADX/KER axis AND the vol gate** —
  correlation, a within-population conditional split, and whether Hurst stacks. Hurst is a
  priori likely correlated with ADX/KER (same trending-vs-reverting axis); if it carries
  no independent information beyond them it is redundant even if it clears the null.

## Guardrails (rules 9a, 19)

- Report **mean R beside mean pips** and the **implied risk unit** on every arm; a win by
  shifting the risk unit is a volatility selector, not a Hurst effect.
- Report `hurst_z` coverage among base signals per era. The 120-bar window nulls the first
  ~136 min of each session, but the base `z` signal already excludes the first 120 min, so
  the incremental deletion is a thin session-open sliver — quantify it, confirm it is not a
  hidden time-of-day filter.
- **Redundancy preview in this run:** report Spearman(hurst_z, {adx_z, ker_z, vei_atr_z,
  rv30_pct}) on traded rows, so redundancy with the directional/vol axes is visible
  immediately even before step 2.
- Correlated pairs ≈ 2–3 effective tests; EURUSD weakest, inverts to momentum long-horizon.

## Files

`_hurst_feature.py` (+ `_test_hurst_feature.py`), `_run_rsi_hurst_gate.py`, outputs
`rsi_hurst_gate_results.json` / `.csv`. Reproduce: `python -u _run_rsi_hurst_gate.py`.
