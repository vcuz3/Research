# 06 — Lookahead, leakage, and the traps that produce convincing false results

Every trap below has produced a **convincing, statistically significant, out-of
-sample-validated false result** in this workspace or in the published
literature. Each entry gives the mechanism, the tell, and the assertion that
catches it.

---

## Part A — Execution and fill feasibility

> Validate execution **before** statistics. No test in lesson 09 can detect a
> fill artifact. DSR, bootstrap, and multiple-testing corrections address
> *selection and uncertainty*; they are blind to an impossible counterfactual.

### A1. The stale stop-price fill ★ the worst one

**Mechanism.** You place a stop at a level price has *already passed*. The
backtest credits you the stop level. In reality the order is marketable at
placement and fills at the current price, points away.

**Real cost here.** `futures/nq/vwap_std_breakout_1`: Sharpe **2.07**, t = 9.5,
positive in every era, validated on a frozen OOS holdout. Roughly **11 points of
unavailable price improvement on 35% of trades.** The entire edge.

**The tell.** A dose-response between "how far past the level price was" and
per-trade P&L. Plot it — the impossible-fill rate *is* the edge curve.

```python
def audit_stop_feasibility(trades, bars):
    """A stop already crossed at placement is MARKETABLE — no stale price."""
    for t in trades.itertuples():
        px_at_placement = bars.at[(t.date, t.signal_mfo), "close"]
        if t.side == 1:
            assert px_at_placement <= t.stop_level, (
                f"stop at {t.stop_level} already crossed (price {px_at_placement}) "
                f"-> must fill at market, not the stop level")
```

### A2. The same-bar fill

**Mechanism.** The signal uses bar `i`'s completed OHLC and the fill is credited
at a price inside bar `i`. You used the bar's outcome to trade its interior.

**Real cost here.** Most of a reported Sharpe-1.8 "magic hour" edge; on
re-audit with honest 1-minute fills the honest effect was ~+0.04–0.05R with a
confidence interval including zero.

**The assertion.** `assert (trades.entry_mfo > trades.signal_mfo).all()` — and
run the `signal_close` ablation to *measure* how big the artifact would have
been. If it's large, your strategy is fill-sensitive and every fast-clock
variant needs re-auditing.

### A3. Intrabar path over-crediting

**Mechanism.** Both stop and target are reachable within one bar; you credit the
target. OHLC cannot order the two touches.

**Real cost here.** The GC ±2σ VWAP fade at 2:1 RR: 1-minute gross Sharpe
**+0.57 (t = 2.16)** → 1-second **+0.08 (t = 0.32)**. Win rate 35.6% → 33.4%,
i.e. exactly the algebraic break-even. 100% artifact.

**Direction of the bias:** coarse bars **flatter** any bracket whose stop is
nearer than its target — which is the common case.

**Fix.** Adverse default, or finer data, or reported bounds. And note the
subtlety: the adverse rule only fires when a bar can reach *both* levels. A bar
whose range spans the target but not the further stop looks like a clean win
even when a finer path shows an earlier stop touch. **Only finer data resolves
that one.**

### A4. Free passive fills

**Mechanism.** A print at your limit price is credited as a fill. Queue
position, volume ahead, and cancellations are ignored.

**Real cost here.** Fixed-tick wick capture manufactured a monotone
"high-volatility edge" in the NQ VWAP pullback — because a fixed 2-tick
trade-through guard is a *tighter* requirement in low vol and a *looser* one in
high vol.

**Fix.** Volatility-scaled trade-through guard (`0.1 × ATR`, not `2 ticks`),
plus a sensitivity test. Understand that this is still a heuristic, not a queue
model. With real L2 data, model price-time priority, volume ahead, and depth.

**Polymarket lesson from this workspace:** moving from "print at price = fill"
to a real queue-position model collapsed significance from t = 3.6 to t = 1.6
while dollar ROI held. Queue realism is not a haircut; it is a different result.

### A5. Gap-through fills

A stop triggered by a gap does **not** fill at the stop level. It fills at the
first tradable post-trigger price. On an overnight gap that can be 50 points.

```python
if side == 1 and bar.open < stop:     # gapped through
    exit_px = bar.open                # NOT stop
```

### A6. Cost stress is not fill validation

Reordering these is the most common process error. Validate causality → trigger
feasibility → price availability → queue assumptions. **Then** stress spread,
fees, slippage, impact.

---

## Part B — Lookahead and leakage

### B1. Full-sample statistics in a feature

```python
df["z"] = (df.close - df.close.mean()) / df.close.std()      # WRONG
thresh = df.ret.quantile(0.95)                                # WRONG
scaler.fit(X); X = scaler.transform(X)                        # WRONG (fit on all)
```

Every one of these uses the whole sample at every row. Mean-reversion strategies
built on a full-sample mean are *guaranteed* to work, because the mean is by
construction the level prices return to.

**Catch-all test** (from lesson 02 — run it on every feature builder):

```python
def test_indicator_is_causal(build_fn, df):
    full = build_fn(df)
    cut = len(df) // 2
    part = build_fn(df.iloc[:cut].copy())
    pd.testing.assert_frame_equal(full.iloc[warmup:cut], part.iloc[warmup:],
                                  check_exact=False, rtol=1e-10)
```

### B2. Session/period totals used before they exist

Session volume, daily range, RVOL against the *full day's* volume, "the day's
VWAP" — none of these are known at 10:00. Use **elapsed-to-date** quantities,
causally-estimated expectations, or **prior-period** statistics.

Prior totals and totals already known at decision time are fine. `RVOL =
volume_to_date / mean(volume_to_date at the same mfo over prior 90 sessions)` is
correct. `volume_to_date / today's_total_volume` is not.

### B3. The one-character `.shift(1)`

```python
sigma = move.rolling(90).mean()             # includes TODAY
sigma = move.shift(1).rolling(90).mean()    # strictly prior — correct
```

That is the entire difference between a causal band and a leaking one. Make it
visible, put it in one place, and test it.

### B4. Non-causal universe or filter selection

Do not use future membership, full-sample medians, survival, or later liquidity
to decide what was tradable. Reconstruct the observable universe as of each
decision time.

**Real failure here (Polymarket phase 14g):** "bid-only universe filters" turned
out to be two-sided/lookahead artifacts — a `spread > 10c` filter computed from a
*token-level median over the token's whole life* is a volume dial, not a causal
gate. The fix was a **causal current-quote gate**.

### B5. Point-in-time data

Macro releases, fundamentals, classifications, index membership, analyst
forecasts, and corporate actions are **revised**. Use the vintage available at
the decision time, with the correct publication latency. A GDP print you
"observed" on the release date but used the current revised value for is a leak
that looks like macro skill.

### B6. Roll and contract leakage

Do not choose the front contract using future volume. Do not let a synthetic
roll jump occur inside a simulated trade. Map signals and P&L to the contracts,
multipliers, and tick values that were actually tradable at that time.

### B7. Survivorship and delisting

Backtesting today's index constituents over 15 years is a study of what worked
for companies that survived. In futures this shows up as testing only the
contracts that still trade.

### B8. The silent data-quality filter

Covered in lesson 01 §1.5: `rolling(90, min_periods=90)` on a thin instrument
deleted ~28% of one time slot's decisions. Not lookahead, but a hidden,
time-of-day-dependent sample filter that corrupts every interpretation built on
it.

---

## Part C — Estimand and accounting traps

### C1. Averaging overlapping positions

**Real cost here:** averaging 61 overlapping positions per day produced Sharpe
**6.3** from a strategy with negative per-trade expectancy.

Daily P&L is the **sum** of position-level realized and marked P&L. Never the
mean of that day's trades.

### C2. Retrospective session weighting

**Real cost here:** per-bet t = **−1.1** became session-weighted t = **−12.4**.
(Note: it made the *negative* result look more significant — the mechanism is
sign-agnostic and would do the same to a positive one.)

Session weighting is invalid when it implicitly requires the final number of
signals, which is unknown at allocation time. Default to equal-weighted per-bet
for equal-risk bets; report portfolio results *additionally*.

### C3. Ignoring dependence in inference

Trades on the same day share the same market. Naive per-trade t-stats treat them
as independent and inflate significance by roughly `√(trades per day)`.

Use session clustering, HAC, or block resampling. This workspace's default:

```python
def cluster_t(day_pnl):
    x = day_pnl.to_numpy(float); n = len(x)
    m = x.mean(); se = x.std(ddof=1) / np.sqrt(n)
    return m, (m / se if se > 0 else 0.0)
```

The day is the risk unit; compute the t-stat on the per-day series.

### C4. Exit geometry masquerading as entry edge

**Rule 15, and the first knife to use on any "tight stop, wide target" claim.**

An asymmetric bracket produces a distinctive P&L distribution *regardless of
whether the entry carries information*. A 1:5 bracket on random entries gives
you many small losses and rare large wins, an equity curve that looks like
"letting winners run", and positive expectancy if and only if the win rate
exceeds `1/(1+RR)`.

**The diagnostic:** re-run with a **symmetric** bracket, or measure a
**fixed-horizon forward return** from the entry. If the effect disappears, the
edge is in the exit design, not the entry information. Report when the
conclusion changes under that diagnostic.

This does not make asymmetric exits invalid — it means you must show **where**
the expectancy comes from: entry, exit, or their interaction.

### C5. Adaptive exits with a non-causal update clock

A trailing stop is fine. A trailing stop whose update uses the bar's high/low
at a moment you would not yet have seen them is not. State the update clock, the
information set, and the order behaviour explicitly.

---

## Part D — Selection and interpretation traps

### D1. Non-re-executed "controls"

**Rule 16.** These prove nothing:

- Mirroring long/short P&L on the same fills — may sum to zero **by identity**.
- Multiplying realized P&L by a random sign — never retests the fill.
- Filtering a completed trade list instead of re-running the stateful engine —
  the engine's *state* (what position it was in, what it would have flipped
  into) is exactly what the filter changes.

Any control that changes what the strategy *does* must **re-run the machinery**.

### D2. The mirror trap (sign-flip rescue)

"This direction-conditioner is net-negative, so let's flip it."

**Real failure here (GC):** `es_dir` was net Sharpe −0.56. But its **gross** was
+0.039 pt against a 0.145 pt round-trip cost — the loss was *cost*, not
direction. Flipping to `es_opp` gave gross −0.047 with the same cost: Sharpe
**−1.03**, worse.

**Always read gross before flipping.** If gross ≈ 0, the conditioner carries no
directional content in either sign and no flip helps.

### D3. The rarity filter

Any filter that trades less will usually raise Sharpe by cutting variance. That
is not information.

**The discriminator** — read gross-per-trade on the **kept** trades:
- gross/trade **rises** → the filter carries real per-trade information;
- gross/trade **falls** while Sharpe rises → it is selecting the *worse* trades
  and only helping via reduced exposure = rarity filter.

**And the second discriminator** — a **matched-count random-drop null**: drop
the same number of signals at random, 200 times. If random dropping does as
well, your filter is rarity.

**Real cost here:** at least six filters (KAMA efficiency-ratio regime, gap
veto, RVOL veto, Hurst gate, cross-market confirmation, VWAP-touch exit) all
raised Sharpe, all had plausible mechanisms, all died to this pair of checks.

### D4. "Fewer trades → higher Sharpe" exits

A looser stop reduces trade count and raises Sharpe. Three separate exit
"improvements" here (VWAP-touch exit, narrow-exit-band, RR ladder) all showed
this and all failed their null — **with the null's mean uplift positive**, i.e.
noise got the same benefit.

**The sign of the null's center is the discriminator:**
- null centers **positive** → variance amplification, your "improvement" is
  machinery;
- null centers **negative** → the real effect is genuinely tied to the specific
  thing you cut.

### D5. Multiple testing and the family-max

Swept 3 signals × 2 directions × 7 thresholds = 42 cells. The best cell's t-stat
is **not** a t-stat; it is a maximum of 42 t-stats. Report the family-max and
correct for it (lesson 09).

Worse: you must count the **cells you looked at and abandoned**, across the whole
project, not just the ones in this script. This is why `IDEA_BACKLOG.md` and the
ledger matter.

### D6. DSR / bootstrap / OOS as false comfort

They address selection and uncertainty. **They do not detect lookahead,
accounting, estimator, or fill artifacts.** In this workspace a strategy passed
era stability, DSR = 1.000, and a frozen OOS holdout — and was ~80% fake.

### D7. Regime concentration on consumed data

An effect that lives entirely in 2023+ on data you have already inspected is a
forward-watch candidate, not an edge. Report the era split always.

### D8. Cross-market claims without a re-pairing null

If your claim is "instrument A's signal is confirmed by instrument B", the null
must destroy the *contemporaneous cross-information* while preserving each leg's
own dynamics — i.e. re-pair A's days with B's days from other dates, matched on
era/calendar/regime.

**Real result here:** the "one leg touches 2.5σ, the other doesn't → fade"
divergence strategy printed exactly the same on re-paired days as on real ones.
Pure rarity filter, zero cross-information.

**And read the null's CENTER, not just its tail:** a re-pairing null centered at
~0 means there *is* real cross-information (random dropping wouldn't reproduce
it); a null centered at the real uplift means rarity.

---

## Part E — The mechanism test

> **A single-market null pass does not validate a mechanism that predicts
> cross-market transfer.**

If your stated mechanism is a broad structural force — MOC imbalances, passive
rebalancing, 0DTE gamma, a pan-index effect — it makes a **falsifiable
prediction about sibling instruments**. Test them.

**Real case here.** An early-flat-before-close cutoff on NQ passed its
drift-preserving null convincingly (real +0.101 vs null mean −0.048, p = 0.032,
0/30 draws beat real, and the null centered *negative*). The stated mechanism
(3:45pm MOC imbalance reveal, passive close rebalancing, 0DTE gamma) bears at
least as heavily on the S&P as on the Nasdaq-100. **ES inverted**: early-flat
was worse than baseline and worse than its own null.

Conclusion: the NQ effect is real but the **mechanism is falsified**. It is an
NQ-tape-specific artifact of unknown cause, i.e. a forward-shadow candidate, not
a structural edge.

The sibling market is the cheapest mechanism test you will ever run. Use it.

---

## The pre-flight checklist

Run this before you believe any result:

**Execution**
- [ ] Every fill price lies within its bar's range. (assertion)
- [ ] No same-bar fill on a close-based signal. (assertion)
- [ ] `signal_close` ablation run; the artifact size is reported.
- [ ] Stops: not credited at stale/gapped-through levels.
- [ ] Both-barriers-reachable bars resolved adversely, or finer data used.
- [ ] Passive fills have queue evidence; guards are volatility-scaled.
- [ ] Cost ladder run; gross reported alongside net.

**Information**
- [ ] `test_indicator_is_causal` passes on every feature builder.
- [ ] No full-sample statistic anywhere.
- [ ] No session/period total used before it exists.
- [ ] Point-in-time vintages for revisable data.
- [ ] Universe/filter selection is causal.
- [ ] Rolls causal; no roll jump inside a trade.
- [ ] Data-quality gate run and reported; feature coverage uniform.

**Accounting**
- [ ] Day P&L is a sum of positions, not a mean of trades.
- [ ] Estimand matches a deployable, causally-implementable allocation policy.
- [ ] Inference clusters by session / uses HAC / block bootstrap.
- [ ] Non-overlap enforced, or overlap modelled explicitly.

**Interpretation**
- [ ] Symmetric-bracket or fixed-horizon diagnostic run (exit-geometry knife).
- [ ] Gross-per-trade on kept trades read for every filter.
- [ ] Matched-count random-drop null run for every filter.
- [ ] Claim-matched null run through the **complete pipeline**.
- [ ] Null's center sign interpreted, not just its tail.
- [ ] Family size declared; family-max reported and corrected.
- [ ] Sibling market run as the mechanism test.
- [ ] Era split reported; concentration flagged.

Next: [07 — Performance metrics](07_performance_metrics.md)
