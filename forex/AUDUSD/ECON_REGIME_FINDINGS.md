# AUDUSD Fundamental Economic-Strength Regime — Findings (Step 3b)

**Date:** 2026-07-10 · **Input:** `data/audusd_point_in_time_macro_factors.csv`
(point-in-time AU-minus-US macro factors, monthly). **Usable labelled sample:
2017-10 → 2026-06, 105 months** (ALFRED vintage coverage caps the well-populated
composite here — CLAUDE.md gotcha #1).

**Thesis tested:** *a currency reflects the relative strength of two economies —
so an AU-vs-US economic-strength regime, built from inflation / unemployment /
growth / rates, should line up with AUDUSD.*

**Verdict — the thesis is right about the LEVEL, wrong about the TIMING, and the
timing "edge" does NOT survive a cross-currency pressure test.**
AUDUSD genuinely trades **richer when the Australian economy is relatively strong**
(strength ↔ level correlation **+0.55**). Within the 2017–2026 AUD sample strength
looked like a *contrarian* forward signal (rich → mean-reverts; predictive
rank-IC −0.26 at 3m, −0.37 at 6m, fair-value residual stronger still) and a naïve
"buy strength" overlay lost money. **But** that rested on ~105 sticky months ≈
**one AUD cycle**, and a follow-up **AUD/NZD/CAD panel over 2004–2026 (below)
shows the mean-reversion does NOT replicate** — weak/insignificant for AUD over its
own longer history, absent for NZD, *reversed* (momentum) for CAD, and ≈ zero
pooled. **Bottom line: the LEVEL relationship is real and useful as context; the
fair-value mean-reversion is a one-cycle artifact, not a tradable edge.**

---

## What was built

| Output | File |
|---|---|
| Fundamental-strength classifier + `assign_econ_regimes(df, config)` | `macro_econ_regime.py` |
| End-to-end analysis (tables, charts, bootstrap tests) | `run_macro_econ_regime.py` |
| Labelled monthly dataset | `data/audusd_econ_regime_monthly.csv` |
| Behaviour / forward / IC / fair-value / transition / persistence tables | `results/econ_*.csv` |
| Charts (level+strength overlay, scatter, behaviour) | `results/figures/econ_*.png` |
| **Cross-currency robustness**: AUD/NZD/CAD panel downloader | `download_commodity_fx_panel.py` |
| **Cross-currency robustness**: fair-value replication test | `fairvalue_panel_test.py` |
| Panel IC / overlay tables + actual-vs-fair / IC charts | `results/fairvalue_panel_*.csv`, `results/figures/fairvalue_*.png` |

---

## Method

**Inputs are already the right shape.** `download_public_macro_factors.py`
produces AU-minus-US *relative* factors as **expanding, zero-neutral z-scores**
(scaled by an expanding std of past+current data only) — so a score dated
month-end *t* uses only data released by *t*. No look-ahead; the classifier is
causal by construction.

**Dimensions** (each component signed so **positive = AU relatively stronger /
AUD-supportive**):

| dimension | components |
|---|---|
| growth | GDP-growth trend, real consumption, mfg/business confidence, unemployment trend |
| monetary | relative real short rate (AU carry) |
| external | terms-of-trade dynamics (commodity basket) |
| inflation | excess core CPI, excess PPI, inflation expectations *(kept as its own axis)* |

**STRENGTH composite = mean(growth, monetary, external).** Inflation is held out
of the strength axis because its currency sign is ambiguous (hotter AU inflation
can be AUD+ via a hawkish RBA or AUD− via lost competitiveness); it is used only
for the growth×inflation quadrant.

**Regimes emitted:**
- `strength_regime` — **AU_strong** (strength z ≥ +0.4) / **balanced** / **AU_weak**
  (≤ −0.4).
- `gi_quadrant` — reflation / overheating / stagflation / slowdown
  (sign of growth × sign of inflation).

**Significance** uses a **moving-block bootstrap** (12-month blocks, 5,000 draws)
because the sample is short and macro regimes are sticky — naïve monthly t-stats
would be badly overstated.

---

## Results (2017-10 → 2026-06, 105 months)

### 1. The thesis holds at the LEVEL ✔
`corr(strength_z, AUDUSD level) = +0.55`. By regime:

| strength_regime | months | share | mean AUDUSD level | ann. vol |
|---|---:|---:|---:|---:|
| AU_strong | 25 | 24% | **0.719** | 7.9% |
| balanced | 67 | 64% | 0.695 | 10.6% |
| AU_weak | 13 | 12% | **0.656** | 10.8% |

AUDUSD sits ~6 big-figures higher when AU is fundamentally strong vs weak —
economically sensible, and visible in `results/figures/econ_level_and_strength.png`
(strength and AUDUSD both peak in the 2021 commodity boom and trough in 2024–25).

### 2. …but strength is a CONTRARIAN forward signal ✘ (the interesting part)
Forward returns, conditioned on the regime **known as of month t** (no look-ahead):

| strength_regime | fwd-1m (bp) | fwd-3m (bp) | fwd-6m (bp) | fwd-6m up-rate |
|---|---:|---:|---:|---:|
| **AU_strong** | −30 | **−177** | **−345** | **0.12** |
| balanced | −7 | +34 | +61 | 0.49 |
| AU_weak | +12 | −11 | −75 | — |

When AU looks strongest, AUDUSD is *richest* and then **falls hardest** (up only
12% of the time over the next 6 months). Predictive rank-IC of the continuous
strength score vs forward returns (block-bootstrap 90% CI):

| horizon | rank-IC | 90% CI | boot p | significant |
|---|---:|---:|---:|:--:|
| 1m | −0.11 | [−0.19, +0.01] | 0.13 | no |
| 3m | **−0.26** | [−0.38, −0.09] | 0.012 | **yes** |
| 6m | **−0.37** | [−0.52, −0.13] | 0.015 | **yes** |

### 3. Fair-value misalignment mean-reverts
A **causal** expanding OLS of log(AUDUSD) on the strength score gives a "fair"
level; residual = **rich/cheap vs fundamentals**. That misalignment predicts
forward returns **negatively** (rich → falls):

| horizon | IC(misalign, fwd) | 90% CI | boot p |
|---|---:|---:|---:|
| 1m | −0.24 | [−0.41, −0.21] | ~0 |
| 3m | −0.36 | [−0.65, −0.34] | ~0 |
| 6m | −0.54 | [−0.78, −0.43] | ~0 |

i.e. the deviation of price from strength-implied fair value reverts over 3–6
months — a classic valuation/mean-reversion pattern.

### 4. Direction of use matters: fade, don't follow
The naïve overlay (long AUD in AU_strong, short in AU_weak, hold 1m) **loses**:
annualised Sharpe **−0.19** (discrete) / **−0.38** (continuous tanh tilt), CI
straddling/negative. Following strength is wrong; the profitable reading is to
*fade* rich-vs-fair-value — but see the caveats before believing the magnitude.

### 5. Growth×inflation quadrant is degenerate here (but tells a story)
Only **stagflation (71%)** and **overheating (29%)** appear — over 2017–2026 AU
ran *relatively* weak-growth and hot-inflation vs the US almost throughout, which
is much of the narrative behind AUDUSD's secular slide from ~0.80 to ~0.65. The
axis is real but not discriminating in this one-cycle sample.

### 6. Persistence
Regimes are sticky (self-transition 0.76–0.88; AU_strong median run 3 months,
balanced 6). Sticky regimes + overlapping forward windows are exactly why the
bootstrap (not naïve t-stats) is used.

---

## Answers to the question

- **Can we classify AUDUSD by economic strength?** Yes — a clean, causal,
  explainable AU-vs-US strength regime, and it maps to the AUDUSD **level**
  (corr +0.55), confirming the "currency = relative economic strength" thesis
  *for valuation*.
- **Does strong AU economy ⇒ buy AUD?** **No — the opposite, for timing.** By the
  time AU looks strong the move is priced; strength is a **contrarian** forward
  signal (IC −0.26/−0.37 at 3m/6m) and price mean-reverts to strength-implied
  fair value. A momentum use of it loses money.

---

## Caveats — why this is a hypothesis, not an edge

1. **One cycle.** 105 sticky months (2017–2026) ≈ a single AUD swing (2018 high →
   2020 COVID → 2021 boom → 2024–25 low → 2026 bounce). The "mean reversion" may
   be that one arc, not a repeatable law. With ~9 independent 12-month blocks the
   bootstrap CIs are indicative, not authoritative.
2. **Mechanical-reversion risk.** Regressing a near-I(1) price on a slow
   fundamental and finding the residual reverts is partly mechanical; the
   fair-value IC magnitudes (−0.5+ at 6m) are almost certainly optimistic.
3. **PIT vintage limit.** The clean composite only starts ~2017 — earlier data is
   NaN by design (no look-ahead), so we cannot extend the sample without giving
   up point-in-time integrity.
4. **Monthly & fundamental** — this is a weeks-to-months valuation layer. It is
   **not** intraday-relevant (Step-2 already showed the monthly macro block adds
   nothing to 15-min prediction) and does not interact with the intraday edge.

---

## Robustness — cross-currency panel test (the one-cycle hypothesis, resolved)

To decide whether the fair-value mean-reversion is real or a single-AUD-swing
artifact, I rebuilt a **causal** fair-value model for **AUD, NZD and CAD** over a
longer, multi-cycle sample (**2004–2026, 270 months each**) and tested it pooled.
To keep construction uniform and PIT-safe across currencies, fair value uses the
two canonical commodity-FX fundamentals — both *observed, not revised*:
`log(FX) ~ rate_diff(country−US) + log(terms-of-trade basket)` (expanding OLS).
Built by `download_commodity_fx_panel.py` → `fairvalue_panel_test.py`.

**Result: it does NOT replicate. The Step-3b edge was largely a one-cycle AUD
artifact.**

| misalignment → fwd-return rank-IC | 1m | 6m | 12m | verdict |
|---|---:|---:|---:|---|
| **AUDUSD** (2004–26) | −0.10 *(p.02)* | −0.14 | −0.22 *(p.11)* | same sign, **much weaker** than 2017-26's −0.37/−0.54; only 1m significant |
| **NZDUSD** | −0.06 | −0.15 | −0.13 | same sign, **none significant** (p 0.26–0.34) |
| **CADUSD** | +0.07 | **+0.22** *(p.03)* | **+0.29** *(p.04)* | **opposite sign — momentum, not reversion** |
| **POOLED** | −0.035 | −0.019 | −0.013 | **≈ zero, insignificant** — AUD/NZD reversion and CAD momentum cancel |
| technical control (12m-MA dev) | −0.01 | +0.05 | +0.03 | pooled ≈ 0 too |

- Over AUD's **own longer history**, the mean-reversion is directionally present
  but weak and mostly insignificant — confirming the 2017–2026 magnitudes were
  **inflated by one cycle**.
- **CAD actively contradicts** the thesis (significant *momentum*): its
  fundamental driver is oil, which trends hard (2014-15 crash, 2020, 2022 spike),
  so CAD–fair-value gaps trend rather than revert.
- A **fade-richness monthly overlay** is not monetizable: pooled Sharpe **+0.06**
  (bootstrap CI [−0.12, +0.26]), no better than the technical control (+0.08),
  and negative for CAD. The `fairvalue_actual_vs_fair.png` chart shows why —
  AUD/NZD have sat *below* fair value since ~2021 (fundamentals say "cheap") for
  **years** without reverting; the gaps are persistent, not tradable.

**So the honest resolution:** the LEVEL relationship (fundamental strength ↔ where
the currency trades) is real and cross-sectionally sensible, but the
**mean-reversion of the misalignment is NOT a robust, repeatable edge** — it fails
to generalize across the commodity-FX complex and across cycles.

## Should it go into the strategy phase?

**No — not as a signal.** The pressure test retired the tradable claim: the
fair-value mean-reversion does not survive out-of-cycle or out-of-currency, and
the naïve strength-momentum overlay loses outright. What survives is only the
**descriptive** result — fundamental strength maps to a commodity currency's
valuation/level — which is useful context and a sanity check, **not** a timing
input. Keep it entirely out of the intraday layer. Reproduce the whole chain:
`python run_macro_econ_regime.py` (AUD Step-3b) · `python download_commodity_fx_panel.py`
then `python fairvalue_panel_test.py` (cross-currency robustness).
