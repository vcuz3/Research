# 04 — Exploratory analysis for momentum and mean-reversion

Exploration is where edges are found **and** where samples are destroyed. This
lesson covers both: the measures that actually discriminate, and the protocol
that stops exploration from silently becoming a conclusion.

---

## 4.0 The governing constraint

> **Exploration may generate a hypothesis. It can never retroactively
> preregister its test.** (Rule 24.)
>
> Once you have looked at historical data, it is **consumed**. Only future
> observations are a clean new holdout. (Rule 26.)

So the order is fixed:

1. **Look** at a *deliberately limited* slice, to generate a mechanism.
2. **Write** the hypothesis file: mechanism, exact change, primary metric, kill
   test, controls, data scope — **before** the material run.
3. **Run** it once through the full pipeline.
4. **Report** the verdict, including NO-GO.

Skipping step 2 is the single most expensive mistake in the discipline. It is
also almost undetectable after the fact, which is why the file has to exist with
a timestamp.

---

## 4.1 First question: is this tape trending or reverting, and at what scale?

Answer this **before** designing anything. It is a property of the instrument
and the timescale, not of your strategy.

### Variance ratio (the cleanest single test)

Under a random walk, variance scales linearly with horizon. Deviations tell you
which regime you are in.

```python
def variance_ratio(r: np.ndarray, q: int) -> float:
    """VR(q) = Var(q-period return) / (q * Var(1-period return)).
    >1 trending/persistent, <1 mean-reverting, =1 random walk."""
    r = r[np.isfinite(r)]
    n = len(r) - len(r) % q
    r = r[:n]
    v1 = r.var(ddof=1)
    vq = r.reshape(-1, q).sum(axis=1).var(ddof=1)
    return float(vq / (q * v1))

def vr_stat(r, q):
    """Lo-MacKinlay heteroskedasticity-robust z-stat for VR(q)=1."""
    r = r[np.isfinite(r)]; n = len(r)
    mu = r.mean(); d = (r - mu) ** 2
    denom = d.sum() ** 2
    theta = 0.0
    for k in range(1, q):
        num = np.sum(d[k:] * d[:-k])
        delta = n * num / denom
        theta += ((2 * (q - k) / q) ** 2) * delta
    vr = variance_ratio(r, q)
    return (vr - 1) / np.sqrt(theta) if theta > 0 else np.nan
```

Run it across a **ladder of horizons** and report the profile, not one number:

```python
for q in (2, 5, 10, 30, 60, 120, 390):
    print(f"q={q:4d}  VR={variance_ratio(r, q):.3f}  z={vr_stat(r, q):+.2f}")
```

A flat VR≈1 across all q means there is nothing to trade with a
momentum/reversion thesis at any of those horizons. Learn that in an hour
instead of three months.

### Autocorrelation of returns

```python
from statsmodels.tsa.stattools import acf
ac, ci = acf(r[np.isfinite(r)], nlags=30, alpha=0.05, fft=True)
```

Read the **sign pattern**, not individual bars. Negative lag-1 on 1-minute data
is usually bid-ask bounce (microstructure), not tradable reversion — it
disappears the moment you cross the spread. Positive autocorrelation at 30–120
minutes with negative at 1 minute is the classic intraday-momentum signature.

### Hurst by timescale

From `futures/nq/hurst_explore`: compute H at each of several sampling
intervals, and **always run a matched random-walk control**:

```python
scales = [1, 5, 15, 30, 60, 180]   # minutes
for s in scales:
    x  = close.resample(f"{s}min").last().dropna().pipe(np.log).to_numpy()
    h_real = hurst(x)
    h_null = np.mean([hurst(np.cumsum(rng.standard_normal(len(x))))
                      for _ in range(200)])
    print(f"{s:3d}m  H={h_real:.3f}  RW-control={h_null:.3f}  "
          f"bias-corrected={h_real - h_null + 0.5:.3f}  n={len(x)}")
```

The RW control killed ~40% of an apparent effect in this workspace as a pure
estimator-saturation artifact. **Never interpret a raw H level without it.**

---

## 4.2 The core exploratory measure: conditional forward return

Everything else is a variation on this.

```python
def forward_returns(df, horizons=(5, 15, 30, 60, 120)):
    """Forward log return over each horizon, in ATR units (comparable across eras)."""
    out = {}
    for h in horizons:
        fwd = np.log(df.close.shift(-h) / df.close)
        # ATR-normalise: rule 19, otherwise high-vol eras dominate everything
        out[f"fwd{h}"] = fwd * df.close / df.atr
    return pd.DataFrame(out, index=df.index)
```

**Always normalise by contemporaneous volatility.** An un-normalised forward
return study is a study of *when volatility was high*, and the answer is always
2008/2020.

Now bin your feature and read the response:

```python
def dose_response(feature: pd.Series, fwd: pd.Series, n_bins=10) -> pd.DataFrame:
    d = pd.DataFrame({"f": feature, "y": fwd}).dropna()
    d["bin"] = pd.qcut(d.f, n_bins, labels=False, duplicates="drop")
    g = d.groupby("bin")
    r = g.agg(n=("y","size"), f_mid=("f","median"),
              mean=("y","mean"), med=("y","median"), sd=("y","std"))
    r["t"] = r["mean"] / (r.sd / np.sqrt(r.n))
    r["hit"] = g.y.apply(lambda s: (s > 0).mean())
    return r
```

### What you are looking for — in priority order

1. **Monotonicity.** A clean, ordered response across bins is far stronger
   evidence than one extreme bin. One hot bin out of ten is what noise looks
   like when you have run ten tests.
2. **Symmetry.** Does the reverse condition give the reverse sign? If "high
   feature → up" but "low feature → also up", you have found *volatility* or
   *drift*, not direction.
3. **Magnitude vs cost.** Express the effect in **ticks and dollars** at the
   contemporaneous contract spec, not just in σ. An effect of 0.05σ at NQ 2013
   volatility is below the spread; the same 0.05σ in 2020 is tradable. This is
   Rule 19 and it flips conclusions.
4. **Era stability.** Split by year and re-read. A response that lives entirely
   in 2020 is a regime story, not an edge.
5. **Count.** How many observations per bin, per era? Ten bins × 15 years
   sounds like a lot until you realise the extreme bin has 40 non-overlapping
   events.

### The overlap trap

`fwd60` on 1-minute bars gives you 60× overlapping observations. Your `n` is
inflated ~60× and your t-stat ~7.7×. **Either** sample non-overlapping, **or**
cluster/HAC your inference (lesson 09), **or** report the effect at the
event level only. Never quote a naive t-stat on overlapping forward returns.

---

## 4.3 Information Coefficient (for continuous signals)

```python
from scipy.stats import spearmanr

def ic_by_period(feature, fwd, period_key):
    """Rank IC computed WITHIN each period, then averaged. Never pooled."""
    d = pd.DataFrame({"f": feature, "y": fwd, "p": period_key}).dropna()
    per = d.groupby("p").apply(lambda g: spearmanr(g.f, g.y).statistic
                               if len(g) > 5 else np.nan).dropna()
    ic, sd, n = per.mean(), per.std(ddof=1), len(per)
    return dict(ic=ic, ic_sd=sd, n=n,
                t=ic / (sd / np.sqrt(n)),
                ir=ic / sd)                     # information ratio of the IC
```

Compute IC **within a period and then average across periods** (the
Newey-adjusted "IC series" approach). Pooling all observations conflates
cross-sectional and time-series information and inflates significance badly.

**Reality check on magnitudes:** a mean rank-IC of 0.03 is a genuinely useful
institutional equity signal. A reported IC of 0.4 on a technical feature means
you have a bug — go find it. In this workspace a technical micro-IC of t≈3.8 on
AUDUSD was **real and completely non-monetizable**.

---

## 4.4 Exploring a momentum thesis

The specific diagnostics that discriminate:

### a) Does the breakout continue, conditional on having occurred?

```python
sig = (df.close > df.upper) & (df.close > df.vwap)      # the breakout condition
d = pd.DataFrame({"y": fwd["fwd60"]})[sig.values]
print(d.y.describe(), "\nt =", d.y.mean() / (d.y.std() / np.sqrt(len(d))))
```

### b) Compare against the unconditional drift

**Critical and constantly skipped.** If the instrument drifts up 0.3σ/day, a
long-biased momentum system will look great and have found nothing. Run the
**always-long control**:

```python
naive_long = fwd["fwd60"].mean()               # every bar, no condition
conditional = fwd["fwd60"][sig.values].mean()
print(f"naive={naive_long:+.4f}  conditional={conditional:+.4f}  "
      f"lift={conditional - naive_long:+.4f}")
```

This is how the RTY port was killed in an afternoon here: gross was −0.253 pt/
trade **and** the always-long drift control was also negative — the small-cap
tape had no positive intraday drift, so a breakout system had no backdrop to
ride. Clean NO-GO, no further work required.

### c) Time-of-day profile

```python
prof = pd.DataFrame({"y": fwd["fwd60"], "mfo": df.mfo})[sig.values] \
         .groupby(pd.cut(df.mfo[sig.values], bins=13)).y.agg(["mean","size"])
```

An edge concentrated in one 30-minute slot out of thirteen is 1 test out of 13.
Apply a multiple-testing correction (lesson 09) before believing it.

### d) Do longs and shorts behave symmetrically?

Report `n_long, n_short, mean_long, mean_short` separately, always. A "momentum
edge" that is entirely long-side on an instrument with positive drift is drift.

---

## 4.5 Exploring a mean-reversion thesis

### a) The barrier break-even is the first thing to check

For a fixed `RR:1` bracket, a **zero-edge** strategy wins at exactly
`p* = 1/(1+RR)`. Before anything else:

```python
RR = 2.0
print("break-even win rate:", 1/(1+RR))       # 0.3333
print("observed win rate  :", win_rate)
```

If your observed win rate sits at `p*`, the barriers are efficient and you have
no edge — regardless of what the equity curve looks like. This is exactly how
the GC VWAP fade died: 33.4% observed vs 33.3% break-even.

### b) Half-life of reversion (Ornstein–Uhlenbeck fit)

```python
def half_life(s: pd.Series) -> float:
    y = s.diff().dropna()
    x = s.shift(1).dropna().loc[y.index]
    beta = np.polyfit(x, y, 1)[0]
    return -np.log(2) / beta if beta < 0 else np.inf
```

If the half-life is 400 bars and you are holding for 30, the reversion is real
but you cannot capture it. If it is 0.8 bars, it is microstructure noise and the
spread eats it. You want half-life comfortably inside your holding period and
comfortably longer than one bar.

### c) The extremes trap

A mean-reversion signal is defined **against** a reference level (a band, a
mean, an opening range). Two failure modes:

1. **The reference leaks.** `(close − full_sample_mean)/full_sample_std` is
   guaranteed to revert. See lesson 02 §2.6.
2. **The reference is what your null destroys.** If you shuffle sessions to
   build a null, and the shuffle scrambles the opening range that the strategy
   is defined against, your null tests the wrong thing. See lesson 10 — this
   nearly produced a false "your edge is machinery" verdict here.

### d) Check whether the tape actually reverts at extremes

```python
q = feature.rank(pct=True)
for lo, hi, name in [(0.0,0.05,"bottom 5%"), (0.95,1.0,"top 5%")]:
    m = (q >= lo) & (q < hi)
    print(name, fwd["fwd30"][m].mean(), (fwd["fwd30"][m] > 0).mean(), m.sum())
```

Finding from this workspace: **NQ 5-minute is a CONTINUATION tape at extremes.**
Every naive fade there loses. Establish this per-instrument before designing.

---

## 4.6 The exploration measures worth computing, ranked

| Measure | What it tells you | Watch out for |
|---|---|---|
| Variance ratio profile | trending vs reverting, by horizon | needs non-overlapping windows |
| Autocorrelation | same, finer resolution | lag-1 negative = bid-ask bounce |
| Bias-corrected Hurst | persistence at a scale | huge small-sample bias; needs RW control |
| Dose-response bins | monotonicity, effect shape | one hot bin ≠ signal |
| Conditional vs unconditional | is it the signal or the drift? | the most-skipped check |
| Effect in ticks/$ vs cost | tradability | σ-units flatter high-vol eras |
| Era split | regime dependence | 4 eras = 4 tests |
| Long/short split | symmetry | drift masquerading as edge |
| Time-of-day profile | when it lives | 13 slots = 13 tests |
| Half-life | can you hold long enough? | |
| Barrier break-even | is the bracket efficient? | |
| Signal count/year | capacity, and test count | |

---

## 4.7 Discovery hygiene: the honest way to explore

**Split your data before you look.**

```
2011–2019   discovery       — look freely, form mechanisms
2020–2023   confirmation    — ONE run per preregistered hypothesis
2024+       held             — do not touch until final validation
future      shadow           — the only truly clean holdout you will ever get
```

Rules for this split:

- Every time you run a confirmation on the middle block, that block is a little
  more consumed. Count the runs. After ~5 hypotheses it is discovery data too.
- The held block is spent **once**, at the end, and the result is the result.
- After you have inspected everything, say so plainly in `MEMORY.md`:
  *"Holdout status: consumed. Only future shadow data can be clean holdout
  evidence."* This workspace does exactly that. It is uncomfortable and correct.

**Log every screen.** Keep an `IDEA_BACKLOG.md` and count the configurations you
have looked at. When you finally report a result, the multiple-testing
correction needs `N` = the number of *effective* trials, and you cannot
reconstruct it from memory. Underreporting `N` is the mechanism behind most
published backtest overfitting.

**Label everything.** In every report, mark each result as one of:
- `DISCOVERY` — found by looking, no preregistration, not evidence;
- `SEARCHED` — one cell of a swept family, report the family-max;
- `CONFIRMATORY` — preregistered, single run, clean;
- `CONSUMED-HOLDOUT` — was clean, now spent.

Never let a `DISCOVERY` row appear in a summary table next to a `CONFIRMATORY`
row without the label.

---

## 4.8 Exploration → hypothesis: the handoff

An idea is ready to promote when you can fill in all of this **without running
anything new**:

```markdown
# HYP-0001 — <one-sentence testable claim>

- Proposed mechanism: WHY this should work. A causal story about market
  participants, structure, or constraints. "The backtest showed it" is not a
  mechanism.
- Exact change: the single variable that differs from the frozen baseline.
- Frozen baseline: the exact config the delta is measured against.
- Primary metric: ONE number, with the aggregation and risk unit stated.
- Kill test: the result that REJECTS. Written as a threshold, decided now.
- Required controls: which nulls, which sibling markets, which diagnostics.
- Data scope: instruments, dates, and whether the sample is consumed.
- Multiple-testing note: how many cells in the family; family-max reported.
```

If you cannot state the **mechanism** and the **kill test**, you do not have a
hypothesis. You have a pattern. Put it back in the backlog.

A real example is in `futures/nq/noise_vwap/experiments/hypotheses/HYP-0017.md`
— note that it includes an explicit *prior*: "strong NO-GO PRIOR: every
'more-selective → higher Sharpe' filter tested here has been a variance/rarity
amplifier." Writing your prior down before the run is how you stop yourself
being surprised into believing a marginal result.

---

## 4.9 The two exploration results that generalise

From this workspace, both worth internalising:

1. **A signal that predicts per-trade outcome is not a tradable filter.** The
   efficiency ratio, the Hurst level, and ES cross-confirmation all *genuinely*
   ranked per-trade quality (gross/trade rose monotonically with the feature,
   cross-market, mechanism-consistent). All three failed to monetise, because
   they raised per-trade quality while cutting exposure ~30–40%. Better
   selection + less exposure = no risk-adjusted gain. **Read total net R and
   daily Sharpe, not just per-trade metrics.**

2. **A real structural residual is not automatically a lever.** The noise band
   has a genuine, sibling-confirmed up/down asymmetry. Acting on it *hurt*,
   because the asymmetry merely restates the drift the strategy already
   monetises downstream. Exploiting a feature upstream that you already capture
   downstream double-counts and mis-selects.

---

## Checklist

- [ ] Variance ratio / autocorrelation / bias-corrected Hurst profile computed
      before any strategy design.
- [ ] Every forward-return study ATR-normalised and reported in ticks/$ too.
- [ ] Unconditional (naive always-long / always-in) control run alongside every
      conditional result.
- [ ] Dose-response read for monotonicity, not for the best bin.
- [ ] Overlapping-window inflation handled (non-overlap, or HAC/cluster).
- [ ] Era split and long/short split reported.
- [ ] Number of screens/configurations examined is logged.
- [ ] Every result labelled DISCOVERY / SEARCHED / CONFIRMATORY.
- [ ] Hypothesis file written and committed **before** the material run.

Next: [05 — Writing the simulation engine](05_engine_design.md)
