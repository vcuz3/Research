# Paper Specification

This project is a **synthesis of two sources**, not a replication of one. It
combines the *decision-theoretic readout* of source (1) with the *self-ranking
feature* of source (2), applied to a single instrument. Neither source is
reproduced faithfully; only the transferable machinery is imported. The
performance numbers in both sources are treated as **hypotheses, not results**
(see "Evidence posture" below).

## Source

- (1) **Bimodal Characteristic Returns and Predictability Enhancement via ML** —
  Chulwoo Han (Durham University). Local: `research_papers/Bimodal Characteristic
  Returns and Predictability Enhancement via ML.pdf`.
  - Keeper imported: a classifier emits a probability vector over forward-return
    bins; **rank/act on the expected value `E[r] = Σ_k P(k)·μ_k`, not the argmax
    bin.** Correct decision theory for a multi-modal predictive distribution.
  - NOT imported: the cross-sectional decile long/short portfolio, the stock-level
    mean-variance optimizer, and the cross-sectional "bimodality-as-riskiness"
    construction (bimodality is a *cross-sectional dispersion* fact; it may not
    survive on a single instrument — this is itself a test, not an assumption).
- (2) **Percentile-Rank Momentum With Hysteresis: Low-Churn Signals** — Aligrithm
  (Ali H. Askar), summarizing Francesco Landolfi (2025) working paper. Local:
  `research_papers/percentile rank momentum with hysteresis low churn signals.pdf`;
  URL: https://aligrithm.com/percentile-rank-momentum-with-hysteresis-low-churn-signals/
  - Keepers imported: (a) vol-normalized, **sign-asymmetric percentile-rank** of
    momentum against the instrument's **own past** — the bridge that turns a
    cross-sectional method single-instrument; (b) the **hysteresis (Schmitt-trigger)
    entry/exit band** as a turnover weapon.
  - NOT imported: the crypto equity curves (2018–2025 bull, no benchmark, no
    applied cost model, single timeline — the author himself says "treat the Sharpe
    of 1.5 as a hypothesis, not a result").

## Universe and data

- Instruments: **NQ** (E-mini Nasdaq-100) primary; **ES** held for a sibling-market
  transfer test only (not for tuning).
- Date range: full local archive (`futures/nq/data/NQ_1m_clean.parquet`).
- Frequency and fields: 1-minute OHLCV, Regular Trading Hours (RTH). A 1s archive
  (`NQ_1s_clean.parquet`) exists for any fill-feasibility re-resolution.
- Sessions/calendar/timezone: NQ archive is `datetime64[ns, UTC]` (per shared
  LEARNINGS — do NOT hard-code an ns divisor elsewhere; FX archives are `[us]`).
  RTH session; decision clock pinned to the wall clock.
- Adjustments/rolls: use the existing cleaned/continuous NQ series and its roll
  convention as already audited in `futures/nq/noise_vwap` / `futures/nq/data`.

## Strategy contract (the synthesized method)

### Decision grain and tradable window

- **5-minute bars, RTH only** (09:30–16:00 ET, 78 bars/session). 1m/1s kept only
  for fill re-resolution. Reuse `nq_5m_clean.parquet`.
- **Trade only AFTER the first 30 minutes** — decision bars from **10:00 ET**
  onward. 09:30–10:00 is warm-up: it (a) forms the opening-30m vol input below and
  (b) is the loud, artifact-prone open we deliberately skip. The first tradable
  signal is the first 5m bar at/after 10:00.

### Vol normalizer — previous-day + opening-30m (session-level scalar)

A single causal scalar per session `σ_day`, known by 10:00 (constant for the rest
of the session), predicting rest-of-session dispersion:

- `RV_prev` = realized vol of the **prior** RTH session (sum of squared 5m log
  returns).
- `RV_open` = realized vol of **today's first 30 min** (09:30–10:00, six 5m returns).
- **Primary:** `σ_day = sqrt( α·RV_prev + (1−α)·RV_open )`, `α` a swept blend weight
  (center 0.5). **Sweep alternative:** replace `RV_prev` with a HAR daily mix
  {1d,5d,22d} — shared LEARNINGS §4 found a lone trailing day underperforms HAR, and
  the opening-30m is the biggest single add on top of HAR.
- Rationale for this exact pair: shared LEARNINGS §4 (`nq-noise-vwap-vol-target-sizing`
  / `forex/noise_vwap`) — first-30-min realized vol + a daily term is a validated
  causal predictor of rest-of-session vol. Normalize each raw `n`-bar return:
  `r̃_n[t] = r_n[t] / σ_day`.

### Feature — sign-asymmetric, SAME-SLOT, rolling percentile rank

1. Horizons `n` in **time units**: {15m, 30m, 60m} (= 3/6/12 bars at 5m); optional
   120m slow anchor. Raw `n`-bar return `r_n[t]`, then `r̃_n[t] = r_n[t]/σ_day`.
2. **Same-slot** percentile rank: for each 5m slot `s` (10:00, 10:05, … 15:55), rank
   today's `r̃_n[s]` against the trailing `W` **prior sessions'** values of `r̃_n` at
   the **same slot `s`**, split by **sign**:
   - `rank⁺_n[s] = #{prior sessions d in W : r̃_n[d,s] > 0 and r̃_n[d,s] ≤ r̃_n[today,s]} / #{d in W : r̃_n[d,s] > 0}`
   - short side symmetric on magnitudes of negative moves.
   - Strictly causal: prior sessions only; today's slot never in its own reference.
   - **Rolling, not expanding**: fixed-length W keeps reference sample size constant,
     so the percentile's sampling precision does not drift (shared LEARNINGS §1).
   - **Why same-slot AND σ_day** (not redundant): `σ_day` removes the cross-DAY
     regime scale ("is the whole session hot"); same-slot ranking removes the
     within-day time-of-day profile ("is 10:35 normally louder than 14:00"). Together
     the rank reads **slot-level surprise conditional on the day's regime**, which is
     the intended signal. VEI experiment showed vol expansion/compression is
     time-of-day-structured — hence same-slot, not pooled.
3. Composite score per side: convex blend across horizons,
   `S[t] = Σ_i w_i · rank_{n_i}[t]`, `w_i ≥ 0`, `Σ w_i = 1`, shorter horizons
   weighted more. Bounded in [0,1].

### Model — forward-return-bin distribution + expected-value readout

- Classifier (start simple: multinomial/ordinal logistic or a small GBT; DNN only
  if justified) maps the feature set at `t` to `P(forward-return bin k)` over K bins.
- **Readout: `E[r] = Σ_k P(k)·μ_k`**, where `μ_k` is the **causal trailing** mean
  return of bin k estimated on data before `t` (rolling, not full-sample — the one
  place source (1) uses a 20-year trailing mean; keep it strictly backward-looking).
- Decompose (mandatory ablations): (a) direct ranking on `S[t]` with **no ML**
  (matched trade count) — if the ML `E[r]` does not beat this, the ML adds nothing;
  (b) argmax-bin readout vs `E[r]` readout — isolates source (1)'s keeper.

### Execution — hysteresis-gated

- Enter long when composite (or `E[r]`) rises above high quantile `q_e`; exit only
  when it falls below lower quantile `q_x < q_e`, or a max-hold cap forces out.
  Short side symmetric. The `q_e − q_x` gap is the hysteresis.
- Ablation: hysteresis-OFF (single threshold) — quantifies the turnover/cost saving
  the band is responsible for (source (2)'s load-bearing claim).

### Fills, costs, accounting, metrics

- Fill convention: **next-bar open** after a bar-close signal (RULES §A.2). No
  same-bar execution of bar-close information. Re-resolve on 1s if any bracket
  ordering is ambiguous.
- Costs: model spread + fees + slippage in the audited engine; report **gross AND
  net**, by era (RULES §E). Read gross per-trade FIRST — negative gross is a clean
  NO-GO no cost tweak rescues.
- Accounting/metrics: route through the audited engine (reuse `futures/nq/noise_vwap`
  engine where possible). Report per-trade net expectancy (ticks) with
  session-cluster-robust t, and **three Sharpes** (zero-day, trade-days-only,
  vol-targeted).

## Ambiguities and resolutions

| Ambiguity | Chosen interpretation | Alternative / sensitivity | Evidence |
| --- | --- | --- | --- |
| Pooled vs same-slot reference | **Same-slot** (rank vs same time-of-day history) | — resolved, not swept | VEI experiment: vol expansion/compression is time-of-day-structured; LEARNINGS §1 |
| Reference window `W` | **Rolling, fixed length**, sweep **{60, 90, 120, 252} sessions** | clock-placebo: per-era, per-slot firing-rate CV must be flat | Shared LEARNINGS §1; same-slot needs a long window to feed its thin sign-split tail |
| Window / lookback units | **Time units (sessions / minutes), not bars** | re-check against session coverage | LEARNINGS §2 (bar-unit lookbacks multiply on resample) |
| Same-slot coverage floor | Require ≥ `f·W` sign-consistent same-slot obs (f≈0.9); else DROP the decision and **COUNT the drop per slot per era** | report per-slot coverage; expect W=60 tail to be thin/noisy | RULES §9a; LEARNINGS §2 (strict min_periods = hidden time-of-day filter) |
| Vol normalizer | **prev-day RV + opening-30m RV** (blend α, center 0.5) | HAR{1d,5d,22d}+opening-30m | LEARNINGS §4 (user-cited experiment) |
| Tradable window | **After first 30 min (≥10:00 ET)** | — resolved | opening-30m is a normalizer input; skips loud open |
| Bin mean `μ_k` estimation | **Causal trailing** (backward-only) | Full-sample μ_k = lookahead → forbidden | RULES §B.7 |
| Does forward-return bimodality exist on ONE instrument? | **Open question, tested — not assumed** | If unimodal, source (1)'s motivation drops and only the mean-readout survives | Bimodality is a cross-sectional dispersion fact in source (1) |
| Decision clock | **Wall clock**, RTH, 5m | Phase-shift robustness | LEARNINGS §2; `nq-noise-vwap-decision-clock-robustness` |

## Evidence posture

Both sources are weakly evidenced (source 1: illiquid small-cap short leg + likely
1-month reversal engine, no clean holdout; source 2: single crypto bull timeline,
no benchmark). This project imports only the **machinery** and re-earns any edge
from scratch on NQ, under the workspace RULES, with the kill tests in HYP-0001.
