# RSI/z fade — reversed high-ADX conditioner (FROZEN SPEC)

Preregistered 2026-08-05, before the confirmatory run. Screen on consumed history
(2012–2023); 2024+ remains sealed and is NOT opened by this work.

## Provenance — this is a POST-HOC direction, not a discovery

`RSI_EFFICIENCY_GATE_REPORT.md` preregistered "reversion is better in LOW-efficiency
(choppy) states" and **falsified it in the opposite direction**: fading `|z| >= 1.5`
reverts *better* when the recent path was directional, and the ADX/DI channel carried
a +0.0069 R (4/4 pairs) reversed signal. Per rule 26 that direction was chosen after
seeing the data, so it **cannot be credited from that run**. This spec exists to put
the reversed signal through the two tests that decide whether it is a real, independent
lever or an artefact:

1. a **selection-corrected, claim-matched donor null** whose search space is the WHOLE
   efficiency screen (both LOW and HIGH, ker and adx, all keeps) — because the argmax
   arm *and its direction* were both selected;
2. a **redundancy check against the already-confirmed volatility gate** (ATR-expansion
   top-40% AND RV(30) top-40%, +0.0137 R). ADX is built from True Range, so "high ADX
   reverts better" may simply be "high volatility reverts better", which the project
   already has. If high-ADX adds nothing *on top of* the vol gate, it is redundant.

## Mechanism (stated, not assumed true)

A clean directional over-extension to a `|z|` extreme snaps back; a choppy grind to the
same displacement is an already-balanced book with less to give. If real, high recent
directional strength (ADX) should raise reversion quality *independently* of how volatile
the state is.

## Engine — identical to the confirmed regime matrix (no moving part but the gate)

Event clock (first crossing), non-overlap (rule 13), compulsory single-barrier stop at
**2.0 R**, **1-pip** adverse slippage, **30-min** horizon. Primary at **delay 1** (the
honest, front-loaded-edge clock); delay 0 shown. sigma_pips = rv_30m·1e4·entry_open.
Same-slot z (`adx_z`, 90-session, prior sessions only) estimated on the full minute grid
and read at event rows (LEARNINGS 2026-08-04/2026-08-03). Cutpoints fitted on the EARLY
era only, applied unchanged to LATE.

## Arms

- **Reference:** the `|z| >= k` frontier (Z_GRID), for excess scoring.
- **Candidate:** `high_adx_z 20` (primary) and `high_adx_z 40` — fade only when adx_z is
  in the top keep-fraction within slot.
- **Confirmed baseline:** `vol_gate = vei_atr_z top-40% AND rv30_pct top-40%`.
- **Stack:** `vol_gate AND high_adx_z20` (both orders scored as frontier-excess).
- **Within-vol conditional:** among the vol_gate population, split by adx_z at its median
  and compare mean R / mean pips / risk unit of the two halves.
- **Null search space (for the MAX correction):** every non-frontier arm of the efficiency
  screen (low/high × ker/adx × {40,20,10}, low_ker_raw, withtrend, countertrend, combined).

## Null

Joint donor re-pairing of the efficiency features `(ker, ker_z, adx, adx_z, htf_slope)`
across dates within each `(session_minute, era)` cell, on the full minute grid.

- **PRESERVES:** every price path and each trade's P&L given entry; the `|z|` trigger and
  its depth; the event clock, non-overlap, stop, slippage; each efficiency feature's exact
  within-cell marginal (hence every gate's firing rate); their joint dependence (one
  permutation moves all five together); the same-slot seasonal structure.
- **DESTROYS:** only the contemporaneous link between the efficiency state and THIS
  decision's forward return — exactly the claim.

All four preservation claims are asserted in code before any draw is interpreted. Because
the argmax and direction were both selected, compare the **real MAX** over the search
against the **null MAX** distribution (rule 17), not one arm against its own null.

## Primary metric and kill test

The reversed high-ADX signal is credited as a **real, independent** conditioner only if
BOTH hold:

1. **Not selectivity/noise:** selection-corrected null passes — `frac(null MAX >= real MAX)
   <= 0.05` on **>= 3/4 pairs**.
2. **Not redundant with volatility:** high-ADX **stacks on** the vol gate — the within-vol
   conditional split has the high-adx half's mean R above the low-adx half on **>= 3/4
   pairs**, AND `excess(vol_gate AND high_adx20) - excess(vol_gate) >= 0` on >= 3/4 pairs.

If (1) fails → the reversed signal is not distinguishable from a selectivity dial: NO-GO,
log and move on. If (1) passes but (2) fails → real but **redundant** with the vol gate:
do not adopt as a separate lever, note it, move on. Only (1) AND (2) → preregister a
single frozen candidate and consider it for the sealed holdout — but even then, note the
economics are unchanged (magnitude ~half the vol gate, ~3.5× below the commission floor).

## Guardrails (rules 9a, 19)

- Report **mean R beside mean pips** and the **implied risk unit** (mean_pips/mean_R) on
  every arm; a win by shifting the risk unit is a volatility selector, not an ADX effect.
- Report feature coverage among base signals per era; a silent null is a reportable finding.
- Correlated pairs ≈ 2–3 effective tests; EURUSD is weakest and inverts to momentum at long
  horizon — never read a panel median without it.

## Files

`_run_rsi_adx_reversal.py`, reusing `_efficiency_features.add_efficiency_features`,
`_run_rsi_z_regime_matrix.{add_extra_features,early_cut,Z_GRID}`, and `_rsi_stop_engine`.
Outputs `rsi_adx_reversal_results.json` / `.csv`. Reproduce:
`python -u _run_rsi_adx_reversal.py`.
