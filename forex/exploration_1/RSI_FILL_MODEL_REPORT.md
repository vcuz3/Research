# RSI/z fade — seconds-scale FILL MODEL (REPORT)

Run 2026-08-06. Frozen spec: `RSI_FILL_MODEL_SPEC.md`. Reproduce:
`python -u _run_rsi_fill_model.py` (loads the 1-second LSE mid tape, ~111 M rows/pair).
Consumed history only (early era 2012–2020, see coverage). 2024+ sealed.

## Question

Does the engine's `delay=1` (fill at the open of *t+2*, a full 60-second latency) over-penalise
a strategy whose real decision+route latency is ~1.5 s? Is a fill at the **next candle open**
(`delay=0`) defensible once the true sub-second path is inspected, with the spread the only
remaining charge?

## Verdict — YES, delay-0 is defensible; the sub-second fill cost is ~0.02–0.04 pip. The full-minute delay-1 penalty was far too conservative. Economics are UNCHANGED (this settles timing, not spread).

## Panel (1-second mid tape; vol-gate cell = |z|≥1.5 ∧ vei_atr_z≥early-40% ∧ rv30 pctile≥0.60)

Adverse selection = `side·(fill_L − fill_0)/pip`, the extra cost of filling L seconds late vs
the bar boundary. Gross = entry at the 1s fill, exit at the fixed 30-min minute horizon.

| pair | cell | gross@0s (pip) | **gross@1.5s** | asel@1.5s (pip) | gross@60s | 2.0R-stop R @0s→1.5s |
|---|---|---|---|---|---|---|
| EURUSD | base | 0.309 | 0.291 (94%) | +0.018 | 0.274 | — |
| EURUSD | vol-gate | 0.413 | **0.375 (91%)** | **+0.039** | 0.294 (71%) | 0.0418 → 0.0366 |
| GBPUSD | base | 0.430 | 0.405 (94%) | +0.026 | 0.361 | — |
| GBPUSD | vol-gate | 0.536 | **0.502 (94%)** | **+0.034** | 0.352 (66%) | 0.0526 → 0.0497 |
| AUDUSD | base | 0.228 | 0.212 (93%) | +0.015 | 0.191 | — |
| AUDUSD | vol-gate | 0.418 | **0.388 (93%)** | **+0.030** | 0.311 (74%) | 0.0437 → 0.0397 |
| NZDUSD | base | 0.272 | 0.263 (97%) | +0.009 | 0.225 | — |
| NZDUSD | vol-gate | 0.523 | **0.500 (96%)** | **+0.023** | 0.352 (67%) | 0.0580 → 0.0548 |

## What it establishes

- **At a realistic 1.5 s latency the fill costs 0.02–0.04 pip** (vol-gate), i.e. 4–9% of gross.
  The delay-0 open-mid is very close to a real market-order fill. The `delay=1` full-minute
  convention removes **0.12–0.18 pip (25–34% of gross)** — an over-penalty of roughly an order
  of magnitude relative to the true 1.5 s cost.
- **The sub-second decay is front-loaded in the first ~5–15 s, then plateaus.** Adverse
  selection runs 0 → ~0.03 (1.5 s) → ~0.10 (5 s) → flat to 60 s. At 1.5 s you have eaten less
  than half the eventual sub-minute fill cost, so a fast decision loop is genuinely worth it —
  1.5 s beats 5 s beats 15 s, and all three beat the full minute.
- **The user's Case-A/Case-B (knife-catch) split is near-empty at 1.5 s:** 94–99% of signals
  move <1 pip in 1.5 s, with ~1–4% extending and ~1–4% reverting ≥1 pip, roughly cancelling
  (a slight reversion tilt, consistent with the edge). Price simply does not travel far in
  1.5 s, so the fill is dominated by a tiny mid-bucket drift, not by adverse selection on the
  fast reverters.

## What it does NOT establish (the caveats that keep the economics unchanged)

- **Mid-only data settles TIMING, not SPREAD.** The +0.03 pip latency cost is trivial beside
  the ~0.70 pip commission-plus-spread floor, which is untouched. Dropping the delay-1 penalty
  does **not** make the edge economic: vol-gate at 1.5 s is still ~0.44–0.63 R / 0.39–0.50 pip
  gross, well under the floor. Good news for the fill assumption; neutral for deployability.
- **Coverage 67–80%; the uncovered ~20–33% are the illiquid signals** (no 1s print within
  120 s of the boundary — rollover/Asia hours). That is exactly where the edge's IC
  concentrates and where real spreads are widest, so the benign +0.03 pip is an optimistic,
  liquid-hours figure; the illiquid tail is unmeasured and would be worse.
- **Early-era only.** The 1s tapes end 2020-07 (EUR/GBP) … 2021-11 (NZD), so late-era (2021–23)
  coverage is ≈0 (EUR/GBP 0.000, AUD 0.008, NZD 0.075). This is a 2012–2020 statement.

## Consequence for the project

Replace the crude 0-vs-1-minute delay knob with a **measured seconds-scale fill**: for Workstream
C, price entries at the next-open mid **plus a ~0.03 pip liquid-hours latency haircut** (and a
larger, unmeasured haircut for illiquid-hour signals), then apply the Workstream-A spread/
commission cost on top. The delay-1 convention that made the freshness increment look 85%-fragile
was over-stating the latency cost; the true 1.5 s cost is small, but the spread floor — not the
fill timing — remains the binding constraint.

## Files

`RSI_FILL_MODEL_SPEC.md`, `_run_rsi_fill_model.py`, `rsi_fill_model_results.json`.
