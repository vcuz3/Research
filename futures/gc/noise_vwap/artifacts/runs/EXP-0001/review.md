# EXP-0001 — GC baseline validation: Null-C + vol-target sizing

Validation of the EXP-0000 faithful baseline. Two tests: (1) does the positive
gross/timing edge survive a claim-matched Null-C; (2) does it produce a tradable
portfolio under the paper's vol-target sizing.

## Commands

```
python -m futures.gc.noise_vwap.scripts.run_nulls GC 90 30 0.25    # baseline_nullc.txt
python -m futures.gc.noise_vwap.scripts.run_portfolio GC 90 0.03 8 # vol_target_sizing.txt
```

## Null-C (30 draws, path-preserving return shuffle, 0.25 tick/side)

- Diffusivity gate PASSES: real 0.1000 = null median 0.1000 pt (exactly one gold
  tick). The shuffle preserves path geometry, so the null is valid (rule 17-bis).
- Real day-$net +19.57 vs null mean +2.98 (std 7.33). **z = +2.26, upper-tail
  p = 0.0645**; null captures only **15.2%** of the real P&L. Gross/trade: real
  +0.359 vs null mean +0.128.
- Interpretation: the per-trade timing signal is **not purely machinery** — it
  exceeds its own path-preserving noise with low capture. But the margin is
  marginal (p≈0.065 at light cost) and shrinks at realistic cost. At 0.50
  tick/side (see EXP-0002 equity re-run) the same test gives z=+2.66, p=0.048,
  because the null's P&L turns negative faster than the real edge under cost.

## Vol-target sizing (target 3% daily vol, 8x cap, 0.50 tick/side, 2011-2026)

- **CAGR 0.1%, ann vol 12.9%, Sharpe 0.07, maxDD -45.7%.** Final equity $101,298
  from $100,000 over 15.0 years.
- No year-to-year persistence: 2013 +26%, 2014 +22%, then 2015 -11%, 2017 -25%,
  2020 -5%, 2021 -20%. The marginal per-bet edge does not compound.
- Capital inefficiency: gold's ~$190k contract notional floors sizing to a median
  3.4x vol-mult but ~1-2 contracts at $100k equity (0% of days hit the 8x cap).

## Verdict

- Reviewer: claude (builder self-review; independent review outstanding)
- Date: 2026-07-19
- Decision: **baseline confirmed as a genuine-but-tiny, non-tradable signal.** The
  gross/timing edge is marginally real (beats Null-C, low machinery capture) but
  economically inert (Sharpe 0.07, 46% DD under sizing) and cost-fragile. NOT
  deployment evidence. This is the frozen reference the session-hours and any
  future variants are measured against.
- Objections / limits: 30 null draws give a coarse p; the edge's significance sits
  right at conventional thresholds and is cost-sensitive. One-contract per-trade
  Sharpe (0.46) overstates tradability versus the sized portfolio (0.07).
