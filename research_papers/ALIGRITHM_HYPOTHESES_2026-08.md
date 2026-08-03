# Aligrithm intake — translated hypotheses (2026-08-03)

Source: `https://aligrithm.com`, posts from 2026-06-25 to 2026-07-31 (~160 posts; the
site backfilled ~120 of them on Jun 25 – Jul 2, then published roughly daily). Several
of the most interesting posts are **paywalled after the intro** — flagged below.

This document takes the *plumbing* from those posts and re-points it at instruments and
data this workspace already holds. Nothing here is a finding. Each entry is written so
it could be promoted to a `HYP-XXXX.md` with a preregistered kill test.

## Data actually in hand (verified 2026-08-03)

| Class | Products | Resolution / span |
|---|---|---|
| CME FX | 6A 6B 6C 6E 6J 6N 6S | 1m, 2010-06 → 2026-07 |
| CME equity index | ES NQ RTY YM | 1m 2010/2011 → 2026; **1s** for ES, NQ, YM |
| CME metals | GC SI HG PL PA MGC | 1m; **1s** for GC |
| CME energy | CL BZ NG HO RB MCL | 1m |
| **CME rates — never touched** | **ZT ZF ZN ZB UB SR3 ZQ** | **1m, 2010 → 2026** |
| NQ order book | NQ MBP-1 (L1) | 2025-07-22 → 2026-07-22, **1 full year** |
| Volatility | CBOE VIX | 15-min |
| FX spot | EURUSD GBPUSD AUDUSD NZDUSD (IBKR) | 1m |
| Crypto | BTCUSDT (Binance) | 1m |
| Synthetic | DXY (TVC 30m) + reconstructable from CME FX | — |

Two of those lines are the real headline: **40 CME products at 1-minute over 16 years is a
cross-section we have never built**, and **the rates complex is completely unexplored**.

---

## Tier 1 — run these first

### H-A1. The trend-following closed form as an instrument PRE-SCREEN
- **Source:** *6.48 Trend-Following P&L Is a Function of Autocorrelation (Closed Form)*, Jul 10 — Sepp & Lucic.
- **Plumbing:** a European trend-follower's cumulative P&L reduces to
  `F_T ∝ γ(0)·( [Σ_m ν^m ρ(m) − 1] + (ν/(1−ν))·SR² )`, and turnover
  `E[aU_t] = (2a/√π)·σ_target·√(1−ν)` depends **only on filter span**, never on the market.
  So: expected trend P&L is a weighted sum of lagged autocorrelations plus drift-squared,
  and cost is a pure function of your own parameter.
- **Translation:** we spent six projects discovering the transfer ladder empirically
  (NQ works → ES weaker → GC/YM cost-fragile → RTY no gross edge → FX negative gross).
  This formula claims to *predict* that ladder from two measurable quantities. Compute
  the predicted number per product per era across all 40 CME products, then check it
  against the realised P&L of a matched EWMA-crossover trend rule run through our own
  engine.
- **Assets:** all 40 databento products, daily and 30-minute clocks.
- **Kill test (preregister):** Spearman(predicted, realised) across ≥20 products must
  exceed +0.5 with a bootstrap CI excluding zero, **and** it must reproduce the known
  ordering NQ > ES > YM/GC > RTY. If it cannot rank results we already have, it is not a
  screen.
- **Why it is worth doing:** it turns "which market next?" from a 3-week port into a table.
- **Traps:** the derivation assumes a vol-targeted continuous position, not a barrier
  breakout — so benchmark it against a matched EWMA rule, *not* against `noise_vwap`.
  And the ρ(m) estimates feed straight into H-A2's bias problem.

### H-A2. OLS understates autocorrelation — audit every AR-based conclusion we hold

> **DONE 2026-08-03 → `futures/nq/estimator_bias` HYP-0001 / EXP-0001. Not killed on all
> three cells.** The source article's own claim turned out to be the *least* important of
> three effects. (1) Small-sample bias is negligible for our inference — 0.00025 at
> T=44,516 — so don't bias-correct our pooled statistics; it is a feature-construction
> problem (0.122 at T=30). (2) The real defect: a persistence estimate on a **growing**
> window has a sampling **sd** that compresses 3.8x, so a fixed threshold on it is a
> time-of-day selector — `noise_vwap`'s Hurst gate fires on 33.5% of 10:00 decisions vs
> 8.4% of 15:59 decisions, and a memoryless `signflip` control reproduces half of that
> ramp. (3) Opposite sign: **pooling** a lag-1 statistic across a deterministic intraday
> profile *inflates* it — `vei_exploration`'s AC1 halves under slot-demeaning.
> See `futures/nq/estimator_bias/reports/FINDINGS.md` and `ai_shared_memory/LEARNINGS.md`.
- **Source:** *3.35 Trend and Reversion Are the Same, and OLS Understates Both*, Jun 28;
  reinforced by *5.30 Order-Flow Autocorrelation*, Jul 2 (worked example: true φ = 0.85,
  OLS φ̂ = 0.70 — a run's half-life understated by >50%).
- **Plumbing:** `β̂ = Cov(m_t, m_{t−1})/Var(m_{t−1})` is biased toward zero for *both*
  signs, because the lagged regressor shares shock history with the target. Fix with a
  small-sample AR bias correction and/or block bootstrap.
- **Translation:** this is a measurement audit with unusually broad reach here. Conclusions
  currently resting on a measured autocorrelation include: `hurst_explore` A1 ("intraday H
  at n=30 is mostly noise; bias-corrected session H ≈ 0.50"), `claude_exploration_1` §(d)
  ("31–56% of measured reversion is the shared decision-bar artifact"), and the whole
  intraday-continuation ladder. Short windows → large bias.
- **Assets:** synthetic AR(1) at our actual window lengths first, then NQ/ES/GC 1m and 1s.
- **Kill test:** if bias-corrected estimates move any published conclusion by more than its
  own CI, that conclusion is re-opened; if none move, we bank a hardening result.
- **Cost:** very cheap. Highest ratio of "conclusions touched" to "lines of code" on this list.

### H-A3. Sign-asymmetric percentile ranking recovers the rank IC that pooled ranking destroys
- **Source:** *Percentile-Rank Momentum With Hysteresis: Low-Churn Signals*, Jul 17
  (the PDF is already in `research_papers/`). The author's own framing: "the engineering is
  the contribution" and "treat the crypto results with suspicion" — so take the engineering,
  discard the Sharpe-1.5 headline (no benchmark vs buy-and-hold, no drawdown, costs asserted
  not applied, 2018-2025 crypto).
- **Plumbing worth keeping:** (a) normalise the n-bar return by prior EWM vol; (b) **rank
  up-moves only against past up-moves and down-moves only against past down-moves**;
  (c) convex-weight several horizons into [0,1]; (d) hysteresis band, enter ≈0.85 exit ≈0.55
  (28 flips → 2 flips in the author's example cycle).
- **Translation — this is the creative one:** LEARNINGS 2026-07-31(a) established that on
  NQ/ES the *rank* IC is ≈ 0 while the *mean* q5−q1 spread is significantly positive,
  because equity intraday momentum lives in the tails and a rank statistic weights the
  median. Sign-asymmetric ranking is precisely a rank statistic that **does not pool the two
  tails**. Direct prediction: sign-asymmetric percentile rank shows non-zero rank IC on
  NQ/ES exactly where pooled ranking shows none.
- **Assets:** NQ, ES 1m (primary); 6E/6B for a sign check; BTCUSDT to test the author's own claim.
- **Kill test:** sign-asymmetric rank IC CI must exclude zero on both NQ and ES, and the
  mean-spread twin must be reported alongside it (mandatory per the same learning).
- **Second, separable arm:** drop the hysteresis band into the existing `noise_vwap` engine
  as a turnover reducer. Gate: ≥15% fewer round trips at equal-or-better net R.

### H-A4. Fill quality vs time-to-fill on the NQ MBP-1 year — build a calibrated passive-fill penalty
- **Source:** *9.28 Adverse Selection Is Adverse Selection: Porting Fast-Fills-Are-Bad-Fills
  to FX and Futures*, Jul 2; *9.18*, Jul 1.
- **Plumbing:** dimensionless fill quality `FQ = (p_exec − p_mid)/(p_ask − p_bid)`, bucketed
  by time-to-fill. Reported: market orders −0.72, sub-minute limit fills −0.31, 10-minute-plus
  limit fills +0.43. Markout = signed price change a few minutes after the fill.
- **Translation:** we have one untouched year of NQ MBP-1 and a scaffolded `futures/nq/orderflow`
  project with no data pulled. RULES.md rule 4 currently makes us fall back on a
  volatility-scaled trade-through heuristic that the rules themselves call "a heuristic, not a
  queue model". This measurement would replace it with **an empirically calibrated passive-fill
  penalty as a function of time-to-fill** — a workspace-wide tooling upgrade, not just a finding.
- **Assets:** NQ MBP-1 2025-07 → 2026-07.
- **Kill test:** markout at short time-to-fill must be significantly worse than at long
  time-to-fill **after conditioning on volatility** — fast fills happen in fast markets, and
  LEARNINGS 2026-07-31(c) says a time-of-day-matched split is not enough; match on volatility too.
- **Follow-on:** measure signed-flow AR(1) φ on the same tape (bias-corrected per H-A2) and test
  whether "am I posting into a same-signed run?" improves per-trade markout. Honest prior from
  our own NQ↔ES confirm result: expect quality-not-alpha. Preregister that.

---

## Tier 2 — cheap, high-information

### H-B1. Price-path CONVEXITY — the one thing every endpoint-return study throws away
- **Source:** *10.14 Price-Path Convexity: A New Cross-Sectional Anomaly*, Jul 9 (Gulen & Woeppel;
  paywalled beyond the intro). Claim: low-convexity (hump/fade) paths beat high-convexity
  (valley/recovery) paths by ~0.84%/month in US equities over 60 years, unexplained by standard factors.
- **Plumbing:** `C = [midpoint(first close, last close) − mean(all closes)] / midpoint(endpoints)`,
  using dollar changes not returns. It is a measure of **path shape holding the endpoint fixed**.
- **Translation:** our FX project's standing caution #1 is that any new feature must beat `past30`
  (the bare trailing return), not zero. Convexity has that control built in by construction — it is
  *orthogonal to the endpoint by design*. Two arms: (i) time-series intraday — convexity of the
  trailing 30-minute path predicting the next 30 minutes, partialling out the endpoint return;
  (ii) cross-sectional daily across the 40-product CME panel.
- **Assets:** NQ, ES, 6E, GC (intraday); all 40 products (daily cross-section).
- **Kill test:** partial rank IC controlling for endpoint return, CI excluding zero, on **both** an
  equity index and an FX product, **and** the mean-spread twin reported alongside.
- Genuinely orthogonal to everything this workspace has run. Cheap.

### H-B2. Amihud illiquidity as the "operative liquidity measure" the FX panel could not find
- **Source:** *2.81 Volume and Volatility Are the Same Feature*, Jun 28 — `|r| ∝ √v` mechanically,
  so feeding a model both is double-counting; keep one plus their **ratio** (Amihud `λ = |r|/v`),
  which "cancels the shared component and leaves liquidity". (No empirical backing in the post —
  it is a theory claim. Treat accordingly.)
- **Translation:** `vwap_exploration` finding H ended with exactly this sentence: *"Total contract
  volume is not the operative liquidity measure."* The mechanism behind finding C currently has
  **no live candidate** after EXP-0007 killed the home-market account wrong-signed. Amihud λ,
  same-slot z-scored, is an exogenous candidate computed from data already loaded.
- **Assets:** all 7 CME FX products, 46-slot clock.
- **Kill test:** pooled within-product Spearman(λ, per-block reversion) across the 7-product panel,
  with a circular-shift null (not a label shuffle — both series are autocorrelated on a cyclical index).
- **Two hard constraints, stated up front.** (1) The FX panel is **spent** — all seven products have
  been inspected. Per that project's own MEMORY.md this test would either be scored honestly as
  consumed-history, or run against the **sealed 2024-2026 holdout**. This is the strongest candidate
  yet for spending that holdout, but that is the user's call, not mine. (2) `|r|/v` built from 1-minute
  changes inherits coverage ≈ the *square* of per-minute coverage — the exact trap that deleted 29.7%
  of 6B's Asia decisions inside EXP-0004's control. Report per-block coverage before reading anything.

### H-B3. Signal averaging over the sweep, instead of argmax selection
- **Source:** *6.46 Signal Averaging: Killing Noise with Redundant Alphas*, Jun 29; supported by
  *10.8 Selection vs Diversification: Why |t|>3 Throws Away Alpha*, Jul 9.
- **Plumbing:** keep every lookback variant rather than picking the best; the average splits into
  (average of true parts) + (average of noise parts), noise variance → σ²/N. 20 variants ≈ 4.5×
  less noise sd → fewer noise-driven round trips → better *after-cost* return. Caveat the author
  gives: near-identical variants have correlated noise, so realised gain is between 0 and the full N.
- **Translation:** two arms on the existing audited `noise_vwap` engine.
  - *Lookback averaging:* average the band over {60, 90, 120, 150} instead of the fixed 90.
  - *Phase averaging:* average the signal across the five decision-clock phases.
- **Preregistered asymmetry — this is what makes it a real test:** EXP-0034 already showed that
  shifting the clock phase **lowers** gross/trade on every shift, i.e. :59/:29 is a genuine local
  optimum reflecting real intraday seasonality. So phase-averaging should **dilute and fail**, while
  lookback-averaging may pass. A result where both pass, or both fail, is informative either way.
- **Kill test:** net Sharpe uplift ≥ +0.05 **and** turnover down ≥15%, on NQ **and** ES, compared at
  matched trade count so it is not the width/capacity dial in disguise.

### H-B4. Our parameter sweeps were diagonals, not planes
- **Source:** *3.37 Collinearity in Parameter Sweeps: Plateaus, Not Peaks*, Jul 3.
- **Plumbing:** sweeping (50/200) → (60/210) → (70/220) holds the fast:slow *ratio* fixed — you slid
  one parameter set along a line and called it robustness. Three diagnostics: (a) break collinearity
  deliberately (fix fast, vary slow; then reverse); (b) correlation matrix on the winners — winners
  strung along one diagonal is collinearity; (c) overlay the top 10-15% equity curves — robust
  parameters look like siblings, not just matching final metrics.
- **Translation:** `vei_exploration` swept `wilder(10,50)` → `wilder(20,100)` — a fixed 1:5 diagonal.
  LEARNINGS 2026-07-26 already caught the centre-of-mass confound in that family; this is the other
  half of the same problem and it is currently unaddressed. Same question for the `noise_vwap` band
  lookback surface.
- **Kill test:** re-run on a full grid. If winners string along one diagonal, the standing robustness
  claim is withdrawn; if they spread across the plane, it is hardened.
- Uses existing scripts. Nearly free.

### H-B5. Seasonal-AR volatility with a WEEKLY term
- **Source:** *5.23 SAR: Seasonal Autoregressive Volatility Forecasting*, Jul 1 (explicitly "the toy
  version"; no backtest, illustrative coefficients only) + *5.22 Crypto Volatility Seasonality*.
- **Plumbing:** `σ̂²_t = α + β₁ε²_{t−1} + β₂ε²_{t−24} + β₃ε²_{t−168}` — one-lag clustering, daily
  seasonal, **weekly** seasonal.
- **Translation:** our causal same-slot trailing z-score is already the non-parametric β₂ term. The
  **β₃ weekly term is the part we have never used**, and there are obvious weekly structures on our
  clocks: thin Monday Asia, Wednesday FOMC, Thursday/Friday releases, month-end fix flow (which the
  6B fix result showed is 4× larger at month end).
- **Assets:** all 7 FX products (46-slot clock) + NQ/ES/GC (RTH clock).
- **Kill test:** out-of-sample QLIKE improvement over the same-slot empirical mean at matched degrees
  of freedom, holding on ≥4 of 7 FX products **and** on both NQ and ES.
- **Why it pays:** a better forward-vol forecast feeds the band width, the z-score denominator, and
  vol-targeted sizing — i.e. it improves machinery used in six projects, not one.

---

## Tier 3 — worth doing, but bigger or weaker prior

### H-C1. The rates complex as the next rung of the transfer ladder
- **Source:** synthesis of *6.47 Building a Trend Follower, Component by Component* (Jul 1) with our
  own ladder learning.
- **Idea:** don't port the strategy — port the **diagnostic**. Compute the unit-free
  forward-return-per-band-half-width number (NQ +0.030..+0.103, ES +0.026..+0.088, FX −0.062..+0.061
  with no reliable sign) across all 40 CME products including ZT/ZF/ZN/ZB/UB/SR3/ZQ. One table that
  says where the next three projects should go.
- **Extra structure rates give us that equities don't:** 08:30 ET releases, 14:00 ET FOMC, and
  **13:00 ET Treasury auction results** — published, dated, externally imposed event windows. That is
  exactly the setup where LEARNINGS 2026-08-02 says to check your measurement window against the
  institutional window *first*, and here we would get it right by construction rather than by autopsy.
- **Kill test:** preregister that ZN/ZB must exceed ES's band before any project is opened.

### H-C2. Get the TARGET right before touching features
- **Source:** *10.16 Getting the Target Right: The Transform That Beats 147 Features*, Jul 20
  (paywalled; 80,148 firms, 35 markets, 1994-2024; target transforms ≈ 0.9pp/mo vs feature transforms
  ≈ 0.4pp/mo) + *10.17 Ridge > Zero > Lasso*, Jul 21.
- **Translation:** `forex/AUDUSD` is the ideal host — Ridge/Logistic walk-forward pipeline already
  built and leakage-safe, and its verdict was "technical micro-IC t ≈ 3.8, not monetizable". Freeze
  features and models; vary only how the target is written (raw / demeaned / same-slot-vol-standardised
  / winsorised / rank / sign).
- **Kill test:** the grid must move **net-of-cost P&L**, not IC. An IC-only improvement is a confirmed
  non-result in that project already.
- **Free retrospective check:** *Ridge > Zero > Lasso* predicts our Lasso/elastic-net arms should have
  underperformed a zero forecast. Did they? Five minutes of looking, no new run.

### H-C3. Use SPX to time the VIX, not vice versa
- **Source:** *6.52 Chicken and Egg*, Jul 29. The article's own version is weak: RSI(2) is admittedly
  tuned, there is no walk-forward, all results stop at 2023, and the short-VX book is confounded by the
  structural VX downtrend (229.9 → 13.05 over the sample) — a short-anything book looks good against that.
- **What survives translation is the asymmetry claim only.** Replace RSI(2) — which our own EXP-0006
  proved is `50 + 50·A(dp)/A(|dp|)`, i.e. the trailing return re-normalised, whose fixed 70/30 cut is a
  time-of-day selector — with the project-standard same-slot z-score. That removes the article's largest
  weakness and reuses tested code.
- **Assets:** ES 1m (2011-2026) + VIX 15m. We hold no VX futures, so score this as an entry-information
  / forecast study, which suits our no-engine measurement mode.
- **Kill test — mandatory:** the **reverse-direction arm** (LEARNINGS 2026-07-31(b)). A genuine lead is
  asymmetric; if VIX→ES is as strong as ES→VIX, it is contemporaneous shared information and it dies.
  Frame against `vei_exploration`'s finding that intraday VIX is an **anchor, not an anticipator** for
  forward realised vol — this is the directional cousin of that result and should be read against it.

### H-C4. The rolling-window exit artifact, with a positive control
- **Source:** *5.25 The 24-Hour Rolling-Return Artifact*, Jul 2. Exchange 24h-change headlines jump when
  an old crash **exits the window**, not when price moves; naive flow chases the jump. Detect as a spike
  at lag 24 in an hourly autocorrelation scan; trade the sign of the return from 24h ago.
- **Why it is worth running despite being a folklore-shaped claim:** it has a clean **positive control /
  negative control** structure. BTCUSDT is where the mechanism should exist (we have the 1m archive);
  CME futures are where it should not (no single dominant retail headline; the displayed day-change
  resets at the 18:00 ET session boundary). Testing both is what makes it a test rather than a fishing trip.
- **Kill test:** a lag-24 spike must exceed the general same-slot autocorrelation baseline on BTCUSDT
  **and** be absent on NQ/6E. Either half failing kills it.

### H-C5. Regime gate by asymmetric variance, no factors — as a confirmatory NEGATIVE
- **Source:** *8.9 Regime-Switching That Works, Factors That Don't (MS-GARCH)*, Jul 10. Lumber futures
  2004-2023: EGARCH-GED gate → 158.3% vs 7.13% buy-and-hold; adding factors (commodity index, VIX,
  dollar, policy-uncertainty) **degraded** it to 123.5%. But: Sharpe 0.059, no fees on a weekly full flip
  of an illiquid contract, single commodity, in-sample model selection, and CME wound the contract down
  in 2023. The headline is not credible; the *transferable* claim is "put the effort into an asymmetric
  time-varying variance and resist feeding the model factors".
- **Translation:** our `vei_exploration` and `noise_vwap` EXP-0038/0039/0040 concluded the intraday
  vol channel is **closed** — vol sets *where* the edge is, but is neither gateable nor sizeable. So
  preregister this as a **confirmatory negative**: an EGARCH-GED regime gate on NQ/ES daily should fail
  the same way. If it doesn't, our standing "not gateable" conclusion is challenged and that is worth
  knowing. Preregistering an expected negative is legitimate and cheap.

### H-C6. A cross-sectional CME futures book (this is a PROJECT, not an experiment)
- **Source:** *6.51 Momentum Is a Ranking Problem: Learning-to-Rank vs Regress-then-Rank*, Jul 24 (the
  article itself reports the LTR advantage **collapses at weekly horizons where costs matter**) +
  *10.15 Network Momentum as a Cross-Asset Factor*, Jul 9 + *10.12 Factor Timing Mostly Fails*, Jul 9.
- **Idea:** we have 40 products × 16 years and have never built a cross-section. Rank-based TSMOM with
  vol-scaled weights across the panel.
- **Kill test:** preregister that the learning-to-rank vs regress-then-rank gap must **exceed cost** at
  our rebalance frequency; if it doesn't, adopt the simpler ranking and record that as the result. Also
  preregister *against* factor timing — 10.12's finding is that timing the rotation underperforms the
  equal-weight basket because estimation error dominates.
- Scope this honestly: it is a new project with a paper-intake gate, not a two-day experiment.

---

## Tooling, not hypotheses

- **Per-bar profit factor, not per-trade** (*Why You Compute Profit Factor Per Bar, Not Per Trade*,
  Jun 25) — log-return-based, avoids infinities, honest for continuously-held positions. Complements
  the standing "report three Sharpes" rule.
- **The trade-frequency floor** (*The Trade-Frequency Floor: Choosing a Threshold Honestly*, Jun 25) —
  set a minimum trade count *before* choosing a threshold, so a threshold cannot overfit to a handful
  of lucky bars, then permute to validate. Worth adding as a check in `tools/research_admin.py`.
- **Markout-curve edge-per-second normalisation** (*Layering Forecasts Across Horizons*, Jun 28;
  paywalled) — compare forecasts of different horizons as bps/second before blending
  (30bps/60s = 0.5 vs 2bps/1s = 2). Directly relevant once H-A4 gives us a markout curve on NQ MBP-1.

## Explicitly NOT translating

- **Fair Value as an Adaptive Low-Pass Filter (LAFO)**, Jul 31 — reported Sharpe 11.05 on two months of
  2-minute ES with all hyperparameters tuned on the identical window and no out-of-sample. The author
  says so himself. The only durable claim ("simpler models beat complex ones on 6,000 samples") we
  already act on.
- **Crypto TSMOM Lives in Volume-Weighted Returns**, Jul 22 — the interesting part is that the *index
  construction* carries the result (volume-weighted +0.94%/day vs equal-weighted −1.19%/day on the same
  signal), which is a warning about weighting schemes, not a strategy. We have one crypto symbol; there
  is no cross-section to weight.
- **Harvesting the VRP by Hour**, Jul 1 — author's own numbers: ~14bps gross round trip against four
  taker fills, "a few bps on a good day and negative on a normal one". Same shape as every sub-cost
  result in this workspace.
- **Bitcoin's Overnight Returns Forecast the VIX**, Jul 30 — t = −2.49 on a researcher's chosen cut of a
  24/7 series, 13% of a VIX-change sd, information ratio partly inherited from the structural bleed of
  the VIX ETFs used as the vehicle. We hold BTCUSDT and VIX 15m so it is *runnable*, but the prior is poor.
- **Prediction-market series (9.x, ~40 posts)** — well-written and mostly about Polymarket geometry,
  Kelly, and arbitrage solvers. Relevant to `polymarket_weather` if that project resumes; not to futures.

---

## Recommended order

1. **H-A2** (OLS bias audit) — cheapest, touches the most existing conclusions.
2. **H-A4** (NQ MBP-1 fill quality) — the year of L1 data is idle, and the output is reusable machinery.
3. **H-A3** (sign-asymmetric ranking) — sharpest single prediction on this list, and it is a direct
   consequence of a learning we already own.
4. **H-B1** (path convexity) — cheap and genuinely orthogonal to everything run so far.
5. **H-A1** (trend closed form) — highest leverage on "where do we go next", and it is falsifiable
   against six projects' worth of results we already have.

`H-B4` (collinear sweeps) and `H-B3` (signal averaging) are near-free add-ons to existing scripts and
can ride alongside any of the above.
