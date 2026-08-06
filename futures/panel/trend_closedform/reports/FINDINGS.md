# Findings — trend-following closed form as an instrument pre-screen

Synthesis across reviewed runs. Run-level evidence lives in
`artifacts/runs/EXP-XXXX/review.md`; project state lives in `MEMORY.md`.

Source: `research_papers/ALIGRITHM_HYPOTHESES_2026-08.md` item **H-A1**, from
aligrithm.com *6.48 Trend-Following P&L Is a Function of Autocorrelation (Closed
Form)*, 2026-07-10 (Sepp & Lucic plumbing).

Panel: 30 distinct CME products, Databento `GLBX.MDP3` `ohlcv-1m` volume-ranked
continuous front, **unadjusted**, 2010-06-07 .. 2026-07-28. Daily clock primary,
30-minute ET wall-clock secondary. Everything in **risk units**
(`x = dp / causal trailing scale`), so a 30-product panel spanning 1/256 of a
Treasury point to a dollar of crude is comparable.

---

## A. The closed form is exact, and that is why it cannot screen. (EXP-0001, confirmed)

Generalised to an arbitrary return-weight kernel and an execution lag `L`:

    PHI(w, L) = sum_{m>=1} w_m rho(m+L)  +  SR^2 * sum_{m>=1} w_m

Predicted P&L `= Var(x) * PHI / position_scale(w)` matches the engine's realised
gross P&L to **4.16e-17** over 30 products × 2 lags, and `tests/test_core.py`
pins the identity at 1e-10 including through dropped rolls and for the EWMA
crossover.

The consequence is the finding. **`PHI` over a window is that window's in-sample
trend P&L plus a drift term.** So the "closed form" and "just run the backtest"
are not two screens — measured within year across the panel they correlate at
**Spearman +0.9808** (daily) / **+0.9868** (intraday). The formula does not add
information to a backtest; it *is* the backtest, written in closed form. Its
value is analytic insight and speed, not independent predictive content.

## B. The headline in-sample number is +0.87 and means almost nothing. (EXP-0001, confirmed)

Daily clock, span 32, `PHI` at the article's published lag 0 against realised
gross P&L of the executable lag-1 rule, 30 products:

| arm | Spearman | cluster CI | re-pairing null |
|---|---|---|---|
| **PHI0 → gross (primary)** | **+0.8656** | [+0.6853, +0.9333] | 0.0000 |
| PHI0 → net | +0.8857 | [+0.6966, +0.9533] | 0.0000 |
| PHI0 → net, cost stress 1.0 increment | +0.8759 | [+0.6510, +0.9290] | 0.0000 |
| de-duplicated (no MGC/MCL) | +0.9009 | [+0.7132, +0.9748] | 0.0000 |
| heavy-roll products removed | +0.8449 | [+0.5490, +0.9325] | 0.0000 |

Leave-one-asset-class-out spans only +0.829 to +0.896. This clears the
preregistered +0.50 gate on every arm and every robustness cut.

**It is still not evidence.** `PHI` at the executable lag correlates with
realised gross at **+0.9804** — by construction, per finding A — and the
published lag-0 form shares 159 of its 160 weighted lags with it (`PHI0` vs
`PHI1`: +0.8990). K1 measures only whether the one-lag execution offset and the
cost break the identity. They do not. Presenting it as validation would be the
rule-16 failure mode: an algebraic relation dressed as a test.

The span ladder confirms the mechanism rather than the market: K1 rises
monotonically with span — 8: +0.693, 16: +0.747, 32: +0.866, 64: +0.928, 128:
+0.941, crossover 16/64: +0.963 — because a longer span shrinks ρ(1)'s share of
`PHI0` and drives it toward the realised statistic itself.

## C. Out of sample it fails, and does not beat "just run the backtest". (EXP-0001, confirmed)

Daily clock. `PHI` estimated on one window, scored on the next, against the
degenerate screen (that same window's realised P&L, no theory at all):

| arm | PHI | degenerate | difference |
|---|---|---|---|
| era *k* → *k+1*, pooled (n=79) | +0.0620 | +0.0026 | — (all transition CIs span zero) |
| annual, 4-year windows, pooled (n=374) | +0.0268 [−0.0210, +0.1149] | +0.0196 [−0.0428, +0.1031] | **+0.0072 [−0.0083, +0.0492]** |

The difference is the decision statistic and it **spans zero**. Per-year scores
swing from +0.365 (2023) to −0.364 (2025).

## D. The mechanism: a stable predictor of an unstable target. (EXP-0001, confirmed)

Three one-line diagnostics settle *why*, and the answer is not the one a failed
screen usually has.

- rank persistence of `PHI` itself, year to year: **+0.7133**
- rank persistence of **realised** trend P&L, year to year: **−0.0045**

The predictor is not noisy — it is very stable (partly mechanically: consecutive
4-year windows overlap by three years). The **target** has no persistence at all.
That is the worst available combination: any screen with a multi-year estimation
window produces a confident, smooth, repeatable ranking that is uncorrelated with
next year, and the per-year swings in finding C are exactly what that looks like.

**This generalises past the formula.** With year-to-year rank persistence of
realised trend P&L at zero across 30 CME products over 16 years, no screen of any
construction can rank next year's trend P&L on this panel. The binding constraint
is the stability of the autocorrelation function, not the choice of estimator.
The "which market next?" question H-A1 was raised to answer is closed — not with
a table, but with the result that no table can exist at this horizon.

## E. What the article gets right. (EXP-0001, confirmed)

Two of its claims survive, and one contradicts the preregistered prior.

1. **Turnover really is market-independent.** `E|Δp| = (2/√π)·√(1−ν)` predicts
   0.2778 at span 32; measured risk-unit turnover is **0.257–0.278 on 28 of 30
   products**. The two exceptions are explained: `SR3` (0.211) and `ZQ` (0.199)
   have 33% / 38% of their returns dropped as contract substitutions, which are
   zeroed inside the filter and damp the position.
2. **Autocorrelation, not drift, carries the cross-product variation.** HYP-0001
   named the opposite as the sharpest risk — that `PHI` would be `SR²` in
   disguise. It is not: the autocorrelation term alone scores **+0.8563**
   [+0.6278, +0.9219], the drift term alone **−0.2632** [−0.6803, +0.2740] with
   null frac 0.92, and bare `SR` **−0.1128**. The drift term's spread across
   products (0.0000–0.0432) is a quarter of the autocorrelation term's.
   And it is not one lag: **bare ρ(1) scores +0.0024** [−0.3009, +0.3262]. The
   structural claim — trend P&L is the *whole weighted autocorrelation function*
   — holds.

## F. On an intraday clock the published form measures bid-ask bounce. (EXP-0001, confirmed)

The 30-minute arm behaves differently, and worse.

- `PHI0` vs `PHI1` falls to **+0.4296** (daily +0.8990), because ρ(1) is large
  relative to the rest of the kernel on an intraday clock. The published lag-0
  form therefore contains a big term **no executable rule can reach**, and K1 on
  gross drops to **+0.3806 [−0.0386, +0.7513]** — failing its own gate.
- K1 on *net* looks better (+0.7046) and is **a liquidity ranking, not a trend
  result**. Bid-ask bounce makes ρ(1) negative in proportion to
  tick-over-volatility, and that same ratio is the cost:
  `Spearman(ρ1, cost) = −0.514`, `Spearman(PHI0, cost) = −0.551`,
  **`Spearman(cost, net) = −0.863`**. `PHI0` and net share a driver that has
  nothing to do with trend. On the daily clock the confound is weak
  (`Spearman(cost, net) = −0.125`), so the daily primary is not affected.
- Out of sample, the difference against the degenerate screen is
  **−0.0033 [−0.0421, −0.0085]**. Read as "no evidence the theory beats the
  benchmark", not as a signed result: the percentile interval does not bracket
  its own point estimate, which indicates bootstrap bias from re-grouping the
  resampled clusters. The daily interval does bracket its point.

## G. Side result: the equity ladder is a property of the CLOCK, not the strategy family. (EXP-0001, provisional)

H-A1's kill test asks the ranking to reproduce `NQ > ES > YM/GC > RTY`, which is
`noise_vwap`'s ladder — an intraday **barrier breakout** result — while the same
item's traps section says to benchmark against a matched EWMA rule and
explicitly *not* against `noise_vwap`. Decomposed:

| clock | realised EWMA ordering | vs declared ladder | does PHI reproduce the realised ordering? |
|---|---|---|---|
| daily | **RTY > YM > ES > NQ** | 0/3 adjacent pairs | 3/3 |
| 30-minute | **NQ > YM > ES > RTY** | 2/3 adjacent pairs | 3/3 |

So `PHI` ranks the equity complex correctly in-sample on both clocks, and the
ladder itself **inverts between clocks**: NQ is the best of the four intraday
and the worst daily, because NQ's daily returns are the most mean-reverting at
trend-relevant lags in the panel (`PHI0_ac` −0.111, the most negative of 30).
A screen for an intraday strategy is not a screen for a daily one on the same
instrument. Provisional: one panel, one strategy family per clock.

## H. Neither matched EWMA trend rule is tradable on this panel. (EXP-0001, confirmed)

Reported because rule 20 requires gross and net side by side, and because it is
the honest context for everything above. Cost = half a **measured** price
increment one way (the effective traded grid per product per year, not the
exchange minimum), which is an optimistic floor.

| clock | median annualised gross Sharpe | median net | products net > 0 | cost as share of gross |
|---|---|---|---|---|
| daily, span 32 | +0.057 (best RB +0.662, worst 6S −0.377) | +0.027 | **17 / 30** | 0.17 median |
| 30-minute, span 32 | −0.222 (best NQ +0.096, worst PA −1.058) | −0.860 | **0 / 30** | 23.2 median |

Net-positive counts sit at 15–17 of 30 at *every* daily span and 0–3 of 30 at
every intraday span. Consistent with the workspace's existing transfer ladder:
the daily result is best in energy (`RB` +0.073/day risk units, `HO` +0.050,
`BZ` +0.037, `CL` +0.031) and rates, and negative across equity index — the
familiar CTA pattern.

---

## Data-quality findings (rule 9a)

- **Ten of 30 products changed their effective price increment mid-sample**, at
  ten different dates, measured from the price grid rather than assumed. A cost
  quoted in ticks across 2010-2026 is wrong for part of the sample on a third of
  the panel. See `reports/DATA_QUALITY.txt`.
- **Heavy-roll products.** `BZ` 13.1%, `SR3` 33.3%, `ZQ` 37.5% of daily returns
  are contract substitutions rather than returns, because the volume-ranked
  continuous front flickers with no dominant leg. Every headline is repeated
  without them.
- **A strict `min_periods` deleted 100% of six products** in this project's own
  first build — the LEARNINGS 2026-07-19 defect, reproduced here. With rolls at
  ~5% of `CL`'s rows, `min_periods == vol_window` required all 63 trailing
  sessions to be roll-free and essentially never got it, so the daily risk unit
  was defined nowhere for all six energy products. Fixed with a 2/3 fractional
  floor; pinned by a test.
- Intraday coverage is uniform (across-slot deletion spread ≤ 0.012) for 24 of
  30 products; the exceptions are `ZQ` 0.231, `SR3` 0.157, `BZ` 0.059.
