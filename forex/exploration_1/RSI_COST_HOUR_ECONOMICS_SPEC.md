# Frozen spec — cost-hour economics (Workstream A, D1 + D2)

Frozen before the run. Reproduce: `python -u _run_cost_hour_economics.py`.

## Question

The project has never had a real spread; every economic verdict has been a
hypothetical flat-cost stress (0.2 / 0.5 / 1.0 pip). This run replaces the flat
stress with a **modelled, causal, time-of-day + era + volatility-conditioned
round-trip cost** (`_cost_model.py`, unit-tested in `_test_cost_model.py`) and asks:

1. **D1** — under a modelled FTMO-style cost (raw spread that widens off the
   London/NY overlap and with volatility, plus a per-lot commission), what is the
   **net mean R and net pips**, overall and **by UTC hour and era**, for the
   current best cell and the ungated base?
2. **D2** — the project's edge concentrates in the 16:00–24:00 UTC block, which the
   cost model prices as expensive. **Restricted to the liquid overlap hours**
   (12:00–16:00 UTC) and the broader London/NY window (07:00–20:00 UTC), does a
   smaller but genuinely net-positive edge survive?

## Arms (reuse `_rsi_stop_engine.py` verbatim)

- **Best cell:** `z1.5 + ATR expansion top-40% AND RV(30) pct top-40%`, the combined
  regime gate confirmed real vs a claim-matched null (`RSI_GATE_NULL_REPORT.md`).
  Gate cutpoints fitted on the **early era only** (`early_cut`), applied unchanged.
- **Ungated base:** `zonly`, `|z| >= 1.5`, no gate.
- Both under the **widest sensible compulsory stop (3.0 R)** — the established
  recommendation — with **1 pip stop slippage**, event clock, non-overlap.
- Reported at **delay 0 and delay 1** (the mandatory one-minute-delay arm).

## Cost scenarios (from `_cost_model.CostParams`)

`optimistic`, `base`, `pessimistic`; each with commission on, and a
`base_no_commission` variant to isolate how much of the verdict is the commission
versus the spread. Per-trade `vol_ratio = sigma_pips / pair-median sigma_pips`.

## Primary metric

**Net mean R** per bet (net pips / `sigma_pips`), with a session-cluster t and net
annual pips/pair/yr. Report **mean R beside mean pips** everywhere (project mandate:
a pips ranking is usually a risk-unit ranking). Also report the **breakeven flat
round-trip pip** = mean gross pip: the largest flat cost the arm survives.

## Preregistered kill test

For the modelled **base** scenario with commission:

- **NO-GO (spread-taking version)** if net mean R <= 0 overall for the best cell at
  delay 1, AND the only UTC hours with positive net mean R are hours where the
  modelled round-trip cost exceeds the hour's gross pips (i.e. the positive-net
  hours are an artefact of the model pricing them cheap, not of a real edge that
  clears its own cost). In that case the spread-taking route is dead and the project
  pivots to the deferred D5 (passive/limit entry) as the only remaining cost lever.
- **SURVIVES-IN-LIQUID-HOURS** if, restricted to 07:00–20:00 UTC (or the 12:00–16:00
  overlap), net mean R > 0 at delay 1 in >= 3/4 pairs under the base scenario.
- Otherwise **INCONCLUSIVE / cost-scenario-dependent**, reported as the net-vs-cost
  curve with the breakeven pip.

EURUSD is the weakest member; never read panel medians without it. Correlated pairs
are ~2–3 effective tests, not 4. Consumed history only; the 2024+ holdout stays sealed.
