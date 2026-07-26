# 14 — Reference card

One page. Formulas, thresholds, checklists, failure signatures.

---

## Formulas

### Returns
```
simple    r = p_t/p_{t-1} - 1          (additive across ASSETS)
log       r = ln(p_t/p_{t-1})          (additive across TIME)
R         R = (exit - entry)*side / risk_at_entry      risk FROZEN at entry
```

### Performance
```
CAGR              = (E_T/E_0)^(periods_per_year/n) - 1
Sharpe            = mean(r)/std(r, ddof=1) * sqrt(252)
Sortino           = mean(r - target) / sqrt(sum(min(r-target,0)^2)/N) * sqrt(252)
                    ^ divide by FULL N, not the count of negatives
Calmar            = CAGR / |maxDD|        (classically trailing 36m; else call it MAR)
max drawdown      = min(E/cummax(E) - 1)          [additive form for R: min(cum - cummax)]
Ulcer index       = sqrt(mean(DD^2))
hit ratio         = #(pnl>0)/n
payoff ratio      = |mean(win)/mean(loss)|
BREAK-EVEN HIT    = 1/(1+payoff)          <- always quote next to hit ratio
expectancy        = hit*avg_win + (1-hit)*avg_loss = mean(pnl)
profit factor     = sum(wins)/|sum(losses)|
net R             = sum(net_pts/atr)
expected R        = mean(net_pts/atr)
```

### Statistics
```
day-clustered t   = mean(day_pnl) / (std(day_pnl,ddof=1)/sqrt(n_days))
Sharpe SE (iid)   = sqrt((1 + 0.5*SR^2)/n)                    [per-period SR]
Sharpe SE (fat)   = sqrt((1 + 0.5*SR^2 - skew*SR + (kurt-3)/4*SR^2)/n)
effective n       = n / (1 + 2*sum_k (1-k/n)*rho_k)
variance ratio    = Var(q-period)/(q*Var(1-period))    >1 trend, <1 revert
permutation p     = (#(null >= real) + 1)/(n_draws + 1)       <- never p=0
Newey-West lag    = floor(4*(n/100)^(2/9)), or >= h-1 for h-overlapping returns
```

---

## The invariants (violate none)

1. Every fill must have been **attainable after the order became active**.
2. **Bar-close information cannot trade earlier in the same bar.** Next-bar open.
3. **Include the fill bar**; resolve unresolved path ambiguity **adversely**.
4. **Passive fills need queue evidence.** Guards volatility-scaled, never ticks.
5. **Gap-through orders fill at the first tradable post-trigger price.**
6. **Cost stress is not fill validation.** Feasibility first, costs second.
7. Features use only quantities **available at decision time**.
8. Universe and filter selection must be **causal**.
9. Verify coverage, missingness, joins, survivorship, timestamp alignment.
9a. **Run an executable data-quality test at every data/feature stage and report
    it.** A silently-nulled feature is a reportable finding.
10. Point-in-time **vintages** for revisable data.
11. Rolls, symbols, splits, contract economics handled **causally**.
12. The **estimand must match a deployable, causal allocation policy**; inference
    must reflect dependence.
13. Day P&L is the **sum** of positions, never the mean of trades.
14. Exits **causal, prespecified, simulated exactly**; brackets frozen at entry.
15. **Isolate the exit geometry's contribution** — asymmetric barriers ≠ entry edge.
16. **No algebraic or non-re-executed "controls."**
17. **Run a claim-matched null through the COMPLETE pipeline**, with repeated
    draws, validated invariants, and the full search reproduced.
18. Choose controls that target the **thesis**; rerun stateful machinery.
19. Report effects in **normalized AND tradable units, by era**.
20. **Report gross alongside net.**
21. State frequency, capacity, turnover, exposure, risk unit.
22. Measure risk at the horizon where **capital accumulates**.
23. **Reproduce before auditing.** Declare a tolerance.
24. **Write the kill test before the material run.**
25. **A NO-GO is a successful outcome.** Preserve negative evidence.
26. **Never promote a screen quietly into a conclusion.**

---

## Decision gates

| Gate | Threshold |
|---|---|
| Adopt a variant | Δ daily Sharpe ≥ **+0.10** AND net R ≥ baseline |
| Label as capacity/turnover lever | Δ Sharpe ≥ +0.05, gross/trade ↑, net R ↓ → **default OFF** |
| Null-C pass | `p = (k+1)/(n+1) < 0.05` AND `z ≥ 2` AND null center not positive |
| Matched-count random-drop | `frac(random ≥ real) < 0.05` |
| Cost robustness | survives **1 tick/side**, ideally 2 |
| Era consistency | ≥ 3 of 4 eras improve net R **and** drawdown |
| Cross-market | sign transfers to the sibling |
| Parameter robustness | **plateau**, not a spike |
| Deflated Sharpe | DSR > 0.95 (and it still does not validate fills) |
| PBO / CSCV | < 0.10 good, > 0.50 your selection is worse than random |
| Deploy capital | all of the above **+ a passed future-only shadow period** |

**Standing efficiency rule:** gate the expensive null on the primary metric. A
failing real pass is already a REJECT.

---

## Sanity anchors (intraday futures, real costs)

| Metric | Plausible | Suspicious → go find the bug |
|---|---|---|
| Daily Sharpe (net, zeros in) | 0.8 – 1.5 | > 2.5 |
| Expected net R/trade | 0.01 – 0.06 | > 0.2 |
| Hit ratio (trend system) | 0.35 – 0.45 | > 0.6 with payoff > 1 |
| Profit factor | 1.05 – 1.35 | > 2.0 |
| Max DD | 4 – 10 R | < 2R over 15 years |
| Gross/net ratio | 1.1 – 1.6 | > 5 (cost-dominated) |
| Trades/year | 100 – 1000 | 5 (no power), 100k (no capacity) |
| Rank IC (cross-sectional) | 0.02 – 0.05 | > 0.15 |
| Hurst estimator SD at n=30 | **0.17 – 0.30** | any level claim at that n |

---

## Failure signatures — learn to read these from the panel alone

| Signature | Diagnosis |
|---|---|
| Sharpe ↑, gross/trade ↓ | **Rarity filter** — selecting worse trades |
| Sharpe ↑, null centers **positive** | **Variance amplifier** — noise gets the same benefit |
| gross/trade ↑, net R ↓, Sharpe flat | **Capacity/turnover lever**, not alpha |
| Residual vs baseline **flat** across slots | You only changed **width**, not shape |
| Effect in $, vanishes in R | **Vol-era weighting** |
| Effect in R, vanishes in $ | Too small to pay costs |
| Random dropping **beats** the filter | **Anti-selection** |
| Effect dies under symmetric bracket | **Exit geometry**, not entry information |
| Effect dies at finer bar resolution | **Coarse-bar fill artifact** |
| Win rate == 1/(1+RR) | Barriers are **efficient**; no edge |
| stop_frac ↑, hold ↓, gross ↓ | You **tightened the leash**; variance reduction |
| Sibling market **inverts** | Stated mechanism **falsified** |
| Sharpe > 2.5 on simple technicals | **Bug.** Find it before celebrating. |

---

## Pre-flight (before believing any result)

**Execution**
- [ ] Fill prices within their bars (assertion, every trade)
- [ ] `entry_mfo > signal_mfo` (assertion)
- [ ] `signal_close` ablation run; artifact size reported
- [ ] Stops not credited at stale/gapped-through levels
- [ ] Both-barriers bars resolved adversely, or finer data used
- [ ] Guards volatility-scaled
- [ ] Cost ladder run; gross reported

**Information**
- [ ] `test_indicator_is_causal` passes on every feature builder
- [ ] No full-sample mean/std/quantile anywhere
- [ ] No session/period total used before it exists
- [ ] `.shift(1)` present and visible on every trailing statistic
- [ ] Point-in-time vintages; causal universe; causal rolls
- [ ] Data-quality gate run; feature coverage uniform by time-of-day

**Accounting**
- [ ] Day P&L = sum of positions
- [ ] Estimand causally implementable
- [ ] Inference clustered by session / HAC / block bootstrap
- [ ] Non-overlap enforced or overlap modelled

**Interpretation**
- [ ] Naive/unconditional control run
- [ ] Gross-per-trade on kept trades read
- [ ] Matched-count random-drop null run
- [ ] Null re-runs the **full pipeline** with features rebuilt
- [ ] Null invariants tested incl. **diffusivity gate**
- [ ] Null **center sign** interpreted
- [ ] Family size `N` declared; family-max corrected
- [ ] Sibling market run
- [ ] Era split reported
- [ ] Result labelled DISCOVERY / SEARCHED / CONFIRMATORY / CONSUMED

---

## Code idioms

```python
# causal same-time-of-day statistic
cm    = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")
sigma = (cm.div(cm[0], axis=0) - 1).abs().shift(1).rolling(90, min_periods=81).mean()

# the ONLY fill function
def fill(i):
    return (opn[i+1], mfo[i+1]) if i + 1 <= flat_i else (None, None)

# day P&L
day = trades.groupby("date").net_pts.sum() * POINT_VALUE[inst]

# clustered t
m, t = day.mean(), day.mean() / (day.std(ddof=1) / np.sqrt(len(day)))

# permutation p (never zero)
p = ((null_stats >= real).sum() + 1) / (len(null_stats) + 1)

# paired block bootstrap index
idx = (rng.integers(0, n, nb)[:,None] + np.arange(block)[None,:]).ravel()[:n] % n

# default-off parity (run on EVERY new knob)
pd.testing.assert_frame_equal(engine.run(**BASE), engine.run(**BASE, new_knob=0.0))
```

---

## Conventions to fix once and never change

| Choice | Fix it as |
|---|---|
| Bar timestamp | **Open**-labelled, UTC stored, ET reasoned |
| Intraday coordinate | `mfo` from a **fixed clock anchor** |
| Signal → fill | close → **next open** |
| `ewm` | `adjust=False`; Wilder = `alpha=1/n` |
| Zero-trade days | **Included** in the daily series |
| `ddof` | **1** everywhere |
| Risk-free | 0 for intraday-flat strategies (state it) |
| Annualisation | 252, on a series reindexed over all business days |
| Risk unit | `R = net_points / ATR` (state the ATR definition) |
| Costs | applied **downstream**, gross always reported |
| Day P&L | **sum** |
| Prices | float64 |
| Evidence | committed scripts, never notebooks |

---

## Failures this workspace paid for (so you don't have to)

| Cost | Cause |
|---|---|
| Sharpe **2.07**, t 9.5, OOS-validated | Stop filled at a level price had already passed |
| ~2/3 of a Sharpe **1.8** headline | Same-bar fill on a close-based signal |
| Gross Sharpe **+0.57 → +0.08** | 1-minute bars over-crediting intrabar paths |
| **+0.27R at t=31 on pure noise** | Raw bar-shuffle null (price teleports; free TP hits) |
| Sharpe **6.3** from a negative strategy | Averaging 61 overlapping positions per day |
| t **−1.1 → −12.4** | Retrospective session weighting |
| ~28% of one time slot silently deleted | `rolling(90, min_periods=90)` on a thin instrument |
| A monotone fake "high-vol edge" | Fixed-tick fill guard instead of ATR-scaled |
| A near-false "your edge is machinery" verdict | Null destroyed the reference the strategy is defined against |
| ~8 rejected "improvements" | Fewer trades → higher Sharpe; null centered positive |
| A falsified mechanism that passed its null | Never tested the sibling market |
| DSR **1.000** on an ~80% fake edge | DSR cannot see fill artifacts |

---

## The five habits

1. **Assert fill feasibility in code**, on every trade, before any statistic.
2. **Write the kill test before the run.** In a file. With a date.
3. **Run the claim-matched null through the complete pipeline** — and read its
   **center**, not just its tail.
4. **Gate the expensive null on the primary metric.**
5. **Write up the NO-GOs with the same care as the GOs.** They are where the
   durable knowledge lives.

---

Back to [00 — Start here](00_START_HERE.md)
