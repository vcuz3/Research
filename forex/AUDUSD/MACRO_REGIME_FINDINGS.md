# AUDUSD Macro-Driver Regime Classifier — Findings (Step 3)

**Date:** 2026-07-09 · **Inputs:** `data/raw_market_levels_daily.csv` (daily
levels, 1999→2026) for the classifier; `data/audusd_intraday_modeling_panel.csv`
(332,453 × 15-min bars, 2013→2026) for the baseline-by-regime test.

**Verdict — a usable *descriptive* layer, a marginal *conditioning* layer, NOT a
standalone edge.** The classifier cleanly and explainably labels which external
driver owns AUDUSD, and the labels are economically sensible and moderately
persistent. Conditioning the Step-2 baseline on the regime *does* change its
behaviour — it isolates one regime the model should **avoid** (commodity-driven,
where the technical signal is *inverted*, IC t≈−2.2) and one where the tiny edge
is least-bad (quiet / `low_signal`). But no regime turns the NO-GO baseline into
a clear net-of-cost edge. **Take the regime layer forward as a conditioning /
veto feature and a research lens, not as a trade trigger.**

This step classifies the *market environment*; it is not itself a strategy.

---

## What was built

| Output | File |
|---|---|
| Explainable classifier module + `assign_macro_regimes(df, config)` | `macro_regime.py` |
| IBKR bond-futures downloader (daily AU/US yields → AU–US differential) | `download_rates_futures_ibkr.py` |
| End-to-end driver → labelled dataset, tables, charts | `run_macro_regime.py` |
| Baseline-model-performance-by-regime test | `regime_vs_baseline.py` |
| Regime-labelled daily dataset (full history) | `data/audusd_macro_regime_daily.csv` |
| Behaviour / forward / driver-strength / transition / persistence tables | `results/regime_*_*.csv` |
| Baseline metrics split by regime | `results/baseline_by_*_{h1h,h1d}.csv` |
| Charts (price-by-regime, frequency, dashboard, baseline-Sharpe-by-regime) | `results/figures/*.png` |

---

## Method (the explainable primary model)

**Substrate.** Macro drivers are daily at best, so the classifier runs on the
**daily** driver-return panel and is designed to be forward-filled (lagged one
business day) onto intraday bars — the same frequency-layer discipline the panel
already uses.

**Drivers (genuinely daily, full 2013+ coverage).** DXY-broad (USD), USDCNY
(China/CNH), NZDUSD (regional commodity-bloc FX), WTI oil (commodity/terms-of-
trade proxy), S&P 500 + VIX (risk), and the **rates** channel (see below).
**Iron ore, copper and FRED AU yields are excluded as daily regressors** — they
are monthly series forward-filled onto the daily grid and change on only ~4.6% of
days, so their daily "returns" are structurally zero and would corrupt any
rolling regression (CLAUDE.md gotchas #1/#5). The commodity channel is therefore
an *oil* proxy; that limitation is flagged, not faked.

**Rates channel — now a genuine AU–US differential from bond futures.** The
original blocker was that FRED serves AU yields only monthly, so no honest daily
AU–US spread existed and rates was a US-2Y-only proxy. `download_rates_futures_ibkr.py`
pulls daily **bond-futures** yields from IBKR — AU 3Y/10Y (ASX/SNFE, yield =
100 − price) and US 2Y/10Y (CME yield futures) — and `build_driver_panel` builds
`rate_diff_10y` = Δ(AU10Y − US10Y), the daily change in the spread (AUD carries a
tailwind when the spread widens → sign +1). The classifier **auto-detects** the
futures file: with it, rates becomes the real differential; without it, rates
falls back to the US-2Y proxy (the panel is tagged `rates_source`). Numbers in
this report are the **fallback (US-2Y proxy)** run; once the futures pull is run,
re-running lifts the rates regime materially (offline wiring test: rates share
8% → ~15%, reclaiming days from `low_signal`).

**Rolling regression.** For each day *t* and window (20 / 60 / 120 trading days;
60 is primary), a standardized multivariate OLS of the AUDUSD daily log-return on
the driver returns gives, per driver: standardized β, OLS t-stat, correlation,
and a **Pratt product-measure contribution** cᵢ = βᵢ·rᵢ (Σcᵢ = R²) — that
driver's signed share of the window R². The window ends *at* t, so the label is
known at t's close; it is contemporaneous with return_t (fine for description)
and is **shifted +1 business day before any predictive use** (`shift_for_prediction`).
No future returns ever enter a window.

**The NZD problem, handled honestly.** AUD and NZD co-move ~0.8, so NZDUSD
mechanically eats most of the window R² and a naïve contest labels ~75% of days
"regional FX" and never surfaces China / commodity / risk / rates. NZD is a
co-moving *twin*, not an external driver; likewise DXY vs a USD pair is near-
tautological. So two complementary labels are emitted:

- **`macro_regime`** (full contest) — the dominant *explainer*. Answer: AUDUSD is
  overwhelmingly commodity-bloc FX + broad USD (see below). Structural, not
  discriminating.
- **`idio_regime`** (idiosyncratic contest) — **net of USD and the NZD bloc**
  (partial contributions, controlling for both), which AUD-specific driver
  (China / commodity / risk / rates) leads, else `low_signal`. This is the
  discriminating layer used for all behaviour analysis.

**Comparison methods** (secondary cross-checks, all in `macro_regime.py`):
rolling correlation dominance, rolling-PCA dominance, transparent rules-based
classification, and KMeans on the rolling driver-strength features.

---

## Results (2013+)

### 1. Which driver dominates AUDUSD?

**Full contest** — `regional_fx` **75.1%**, `usd` **24.9%**, nothing else. Mean
window R² ≈ **0.76**, of which NZD alone contributes **~0.47** on average. AUDUSD
is, first and foremost, a commodity-bloc FX instrument trading off the broad
dollar. This is the honest answer to "which driver dominates most often," and it
already tells you the macro-regime layer has limited discriminating power at the
top level.

**Idiosyncratic contest** (net of USD + bloc):

| regime | share | median run (days) | self-transition |
|---|---:|---:|---:|
| risk | 30.6% | 3 | 0.92 |
| low_signal | 30.0% | 4 | 0.89 |
| commodity | 16.9% | 2 | 0.89 |
| china | 14.4% | 2 | 0.89 |
| rates | 8.1% | 3 | 0.86 |

So *when* an AUD-specific driver is identifiable, it is most often **risk
sentiment**, then commodity and China, with rates least common — exactly the
profile of a risk-sensitive commodity currency. The driver-strength table
(`results/regime_driver_strength_idio_regime.csv`) confirms the labels are
explainable: in every regime USD (~0.25) and NZD (~0.45) carry the bulk of R²,
and the *named* idiosyncratic driver lights up only on its own diagonal
(china 0.058 in China, commodity 0.051 in commodity, risk 0.064 in risk,
rates 0.039 in rates).

### 2. Does AUDUSD behave differently across regimes? (contemporaneous)

| idio_regime | mean daily ret (bp) | ann. vol (%) | up-day share |
|---|---:|---:|---:|
| rates | **−7.0** | 9.5 | 0.42 |
| china | **−3.6** | 8.9 | 0.46 |
| risk | −1.4 | 9.0 | 0.48 |
| commodity | 0.0 | **11.1** | 0.49 |
| low_signal | **+1.2** | 10.7 | 0.48 |

Yes — behaviour differs materially. Rate-driven and China-driven days are
sharply **AUD-bearish**; commodity-driven days are the **most volatile**;
`low_signal` (no macro driver) is the only mildly positive bucket. (AUD fell
over 2013–2026, so all buckets tilt negative; the *cross-sectional* ordering is
the signal.)

### 3. Are some regimes more predictable / better for long vs short? (forward, causal)

Using the regime *as of t* to predict forward returns (non-overlapping t-stats):

| idio_regime | fwd-1d mean (bp) | fwd-1d t | fwd-5d mean (bp) | fwd-5d t |
|---|---:|---:|---:|---:|
| rates | −6.2 | −1.70 | −20.8 | −1.29 |
| china | −2.5 | −1.03 | −12.9 | −1.01 |
| commodity | −0.2 | −0.07 | −11.0 | −1.15 |
| risk | −0.2 | −0.14 | +1.5 | +0.17 |
| low_signal | −0.6 | −0.28 | −3.0 | +0.27 |

There is a **directional tilt** — rate- and China-driven regimes lean AUD-short
forward — but **none of it is statistically significant** (all |t| < 2 on
honest non-overlapping samples). Much of the forward drift is just persistence of
the same contemporaneous move (the regimes are sticky). So: a describable
short-bias in rates/China regimes, not a reliable forecast.

### 4. Persistence & transitions

Regimes are **moderately persistent** (self-transition 0.86–0.92; risk
stickiest). Transitions overwhelmingly route through `low_signal` (the
`results/regime_transition_idio_regime.csv` off-diagonal mass concentrates in the
low_signal column), i.e. the market decays to "no dominant driver" between
episodes rather than jumping driver-to-driver. Median run lengths are short (2–4
days) with long tails (max runs 33–107 days) — usable for a slow conditioning
feature, too noisy for a fast switch.

### 5. Comparison methods

Agreement with the primary `idio_regime` label: corr-dominance 38%, KMeans 42%,
PCA 37%, rules-based 7%. The methods **broadly concur on the driver set**
(risk / China / commodity are the recurring players) but the **exact daily label
is method-sensitive** — the regime boundaries are fuzzy. PCA collapses to "risk"
(the S&P/VIX pair is the highest-variance common factor) — a known artifact, and
a caution against over-trusting any single-day label. This fuzziness is itself a
reason to use the regime as a slow *tilt/veto*, not a precise switch.

### 6. Does the regime layer improve the Step-2 baseline? (the key test)

Re-ran the leakage-safe **technical Ridge** walk-forward (the only Step-2 set
with signal), attached the daily regime with a strict 1-business-day lag, and
recomputed overlap-aware metrics **within each regime**
(`results/baseline_by_idio_regime_*.csv`).

**1-hour horizon** (overall rank IC 0.012, t≈2.6 — matches the baseline):

| idio_regime | rank IC | IC t | net Sharpe @0.5pip | read |
|---|---:|---:|---:|---|
| low_signal | +0.023 | **+4.7** | **+0.36** | model works best when no macro driver dominates |
| risk | +0.021 | +5.1 | −0.08 | detectable IC, still unprofitable |
| china | +0.013 | +2.2 | −0.14 | weak |
| **commodity** | **−0.020** | **−2.2** | **−1.56** | **model is INVERTED — avoid** |
| rates | +0.001 | +0.1 | +0.39 | Sharpe is directional luck (IC≈0, tiny n) |

**1-day horizon** (overall IC ≈ 0): the only positive cells are `rates`
(net Sharpe +0.85) and the `usd` macro-regime (+0.82) — but each rests on
<900 non-overlapping samples with rank-IC t ≈ 1.6 (insignificant); the Sharpe
comes from leaning short into AUD's drift in those regimes, not from model skill.

**Interpretation.** The regime layer genuinely **modulates** the baseline:
- a clear **veto** signal — the technical model's sign flips in the
  commodity-driven regime (IC t = −2.2), so trading it there loses money;
- a mild **green-light** — the edge is least-bad / marginally positive in the
  quiet `low_signal` and `risk` regimes (net Sharpe +0.36 at 1h, the most robust
  positive cell, on the largest sample);
- but the best honest net Sharpe (~0.36) is **modest, on placeholder costs, and
  found by slicing many cells** (5 regimes × 2 horizons × 2 layers → multiple-
  testing risk). It does not clear the bar for a tradable edge.

---

## Answers to the required research questions

1. **Which driver dominates most often?** Broad **USD + commodity-bloc (NZD)**
   co-movement, always (R²≈0.76). Net of those, the most common *idiosyncratic*
   driver is **risk sentiment** (31%), then commodity (17%) and China (14%).
2. **Does AUDUSD behave differently across regimes?** Yes — rate/China regimes
   are AUD-bearish, commodity regimes most volatile, `low_signal` mildly
   positive (§2).
3. **Are some regimes more predictable?** Weakly. Rate/China regimes carry a
   forward short-tilt but **not significant** (|t|<2). The *baseline model* is
   more predictable in `low_signal`/`risk` (IC t 4.7/5.1) and **anti-predictable
   in commodity** (t −2.2).
4. **Better for long vs short?** All regimes tilt short over this sample; the
   *relative* short-bias is strongest in **rates** and **china** regimes. No
   regime gives a significant long signal.
5. **Does the baseline do better in some regimes?** Yes — materially. Best in
   `low_signal` (net Sharpe +0.36 @1h), reliably **worst/inverted in commodity**
   (−1.56). This is the layer's most useful output.
6. **Regimes to avoid?** **Commodity-driven** regime for the technical model
   (signal inverts). Also `rates`/`usd` "wins" at 1d should be distrusted
   (tiny-n directional drift).
7. **Stable enough for live trading?** As a **slow conditioning tilt/veto**, yes
   (moderate persistence, explainable). As a **precise daily switch**, no —
   method agreement is only ~40% and single-day labels are fuzzy.

---

## Caveats / honesty notes

- **Costs are a placeholder** (0.5-pip one-way); the BID_ASK IBKR pass
  (CLAUDE.md #2) is still required before any PnL is trusted. At 1h, cost drag
  dominates — the low_signal +0.36 net Sharpe is the *least* cost-fragile
  positive but still unproven.
- **Multiple testing.** Many regime × horizon cells were examined; treat any
  single significant cell as a hypothesis, not a result. The two findings I'd
  stake are the *commodity inversion* (economically coherent — the technical
  mean-reversion model fights strong commodity-driven trends) and the
  *low_signal green-light* (technicals work in range-bound, driver-less tape).
- **Contemporaneous ≠ predictive.** Forward regime tilts are largely persistence
  of the current move; the non-overlapping t-stats keep this honest.
- **Commodity channel is oil-only** (SGX iron-ore futures, an external vendor
  per `external_data_registry.csv`, would sharpen the commodity regime).
- **Rates channel** is upgraded from a proxy to a genuine daily AU–US 10Y
  differential via bond futures (`download_rates_futures_ibkr.py`); the reported
  numbers are still the pre-pull US-2Y fallback. Two caveats on the futures build:
  continuous-future splicing adds a small (~few-bp) yield jump at quarterly rolls,
  and the US yield-future leg (2YY/10YY) only lists from ~Aug-2022, so the
  long-history differential uses FRED US-10Y for the US leg and reserves the US
  yield futures for a recent pure-futures cross-check. A *rate-path* differential
  (RBA/Fed OIS/STIR) is still not built.
- **NZD dual role.** Keeping NZD in the regression (partial betas) is the right
  call for isolating idiosyncratic drivers, but it means "commodity/risk/china"
  are *marginal-of-the-bloc* effects — small by construction.

---

## Should the regime layer go into the next (strategy) phase?

**Yes, in a specific, limited role:**
1. as a **veto / tilt feature** — stand down (or down-weight) the technical model
   in the **commodity-driven** regime; allow it in `low_signal`/`risk`;
2. as a **conditioning input** to the sequential regression-learning strategy
   (the actual next task), interacted with the technical features rather than
   added linearly (the Step-2 macro block added linearly was ~0 and dilutive);
3. as a **research/reporting lens** — PnL-by-regime is now a first-class
   diagnostic.

**Not** as a standalone signal or a precise switch. Reproduce end-to-end:
`python run_macro_regime.py` then `python regime_vs_baseline.py`.
