# 02 — Indicators, causally and correctly

Every indicator below is given with (a) the definition, (b) vectorised code,
(c) **the causality trap specific to it**. The traps are the point of this
lesson; the formulas are in any textbook.

Convention throughout: `df` is one instrument, sorted by time, with columns
`sdate, mfo, open, high, low, close, volume`.

---

## 2.0 The two rules every indicator must satisfy

1. **Availability.** The value at row `i` may use only data whose information
   time is `<= close time of bar i`. If you use bar `i`'s close, you may not
   act until bar `i+1`.
2. **One-sidedness.** No full-sample statistic. No `df.close.mean()` as a
   threshold. No `scipy.signal.filtfilt`. No `.rolling(center=True)`. No
   `.interpolate()` over gaps (it fills backwards). No `zscore` against a
   full-sample mean/std.

A single helper makes rule 1 auditable:

```python
def causal(s: pd.Series, by=None) -> pd.Series:
    """Shift a signal by one bar so it can only be acted on at the next bar."""
    return s.groupby(by).shift(1) if by is not None else s.shift(1)
```

Put `causal()` at the boundary between *feature* and *signal*, and make it the
only place a shift happens. Scattered `.shift(1)` calls are how off-by-one
errors survive review.

---

## 2.1 Moving averages

### SMA
```python
df["sma20"] = df.close.rolling(20, min_periods=20).mean()
```

### EMA
```python
df["ema200"] = df.close.ewm(span=200, adjust=False, min_periods=200).mean()
```

`adjust=False` gives the recursive form `e_t = α·x_t + (1−α)·e_{t−1}` with
`α = 2/(span+1)` — this is what every charting platform means by EMA. With
`adjust=True` (the pandas default!) you get a different, weight-renormalised
series that does not match TradingView/your broker. **Always pass
`adjust=False`.**

**Trap — the warmup leak.** Without `min_periods`, `ewm` returns a value from
bar 1, computed from one observation. That "EMA200" at bar 5 is not an EMA200.
It is not lookahead, but it is a different indicator in the early sample, and if
your strategy's early years are its best years, this is why.

**Trap — cross-session contamination.** For intraday work decide explicitly
whether an EMA continues across the overnight gap. If it should reset each
session:

```python
df["ema20"] = df.groupby("sdate").close.transform(
    lambda s: s.ewm(span=20, adjust=False, min_periods=20).mean())
```

In `futures/nq/noise_vwap` the 200-period trend EMA is deliberately built on the
**ETH** (continuous) session and aligned as-of each RTH bar — a strictly-prior
value. That's a design decision that must be written down, not discovered later.

---

## 2.2 True Range and ATR

### True range
```python
prev_close = df.close.shift(1)
tr = pd.concat([
    df.high - df.low,
    (df.high - prev_close).abs(),
    (df.low  - prev_close).abs(),
], axis=1).max(axis=1)
```

### Wilder ATR (the standard)
```python
# Wilder smoothing == EMA with alpha = 1/n
df["atr14"] = tr.ewm(alpha=1/14, adjust=False, min_periods=14).mean()
```

Note `ewm(alpha=1/n)` ≠ `ewm(span=n)`. Wilder's is `alpha = 1/n`, i.e.
`span = 2n − 1`. Using `span=14` gives you a materially faster ATR than every
chart you'll compare against.

### The session-level ATR used in this workspace

For a strategy that decides once per session, a *per-bar* ATR is the wrong
scale. `core/session.py` uses a **causal prior-session mean RTH range**:

```python
rth = df[df.is_rth]
rng = rth.groupby("sdate").high.max() - rth.groupby("sdate").low.min()
atr = rng.sort_index().shift(1).rolling(14, min_periods=14).mean()
df["atr"] = df.sdate.map(atr).to_numpy()     # constant within a session
```

Read the `.shift(1)`: **today's ATR uses only sessions strictly before today.**
Without it, today's own range is in today's volatility scale — a classic,
subtle, and very profitable-looking leak, because your stop widens exactly on
the days that turn out to be wide.

**Why ATR at all?** It is the *volatility unit*. Rule 4/19 in this workspace:
never express a buffer, guard, or stop in **ticks** across changing volatility
regimes — a fixed 2-tick guard is enormous in 2013 and trivial in 2020, which
manufactures a monotone "high-volatility edge". Use `k × ATR`.

---

## 2.3 VWAP (session-anchored, cumulative)

```python
tp = (df.high + df.low + df.close) / 3.0            # typical price
v  = df.volume.astype("float64")
g  = df.groupby("sdate", sort=False)
cum_v   = g.volume.cumsum().astype("float64")
cum_tpv = (tp * v).groupby(df.sdate).cumsum()
df["vwap"] = cum_tpv / cum_v
```

**Trap — the anchor.** "VWAP" is meaningless without an anchor. Session VWAP,
weekly VWAP, and anchored-from-an-event VWAP are different indicators. State it.

**Trap — VWAP includes the current bar.** `cumsum` at bar `i` includes bar `i`'s
own volume and typical price. That is fine (it's known at bar `i`'s close) — but
it means comparing `close[i] > vwap[i]` is a *contemporaneous* comparison, and
you must still act at `i+1`.

### VWAP σ-bands (volume-weighted std about VWAP)

```python
cum_tp2v = ((tp**2) * v).groupby(df.sdate).cumsum()
var_vw = cum_tp2v / cum_v - df.vwap**2
df["sig_vw"] = np.sqrt(var_vw.clip(lower=0))
df["vwap_up"] = df.vwap + 2.0 * df.sig_vw
```

Computed this way it is a one-pass cumulative statistic — no lookahead, no
rolling window. The `clip(lower=0)` handles the float cancellation that makes
`E[X²] − E[X]²` go slightly negative.

**Finding from this workspace:** VWAP σ-bands are *efficient* on NQ and GC —
fading them has no gross edge once fills are honest
(`futures/nq/vwap_band...`, `futures/gc/vwap_reversion`). Don't spend six weeks
rediscovering that.

---

## 2.4 The same-time-of-day "noise band" (worked in full)

This is the load-bearing feature of the flagship project here, and it's a
perfect teaching example of a causal cross-sectional-in-time feature.

Definition:
```
move[d, mfo]  = |close[d, mfo] / open[d, 0] − 1|
sigma[d, mfo] = mean of move[·, mfo] over the prior `lookback` sessions
upper[d, mfo] = max(open[d,0], prior_close[d]) × (1 + sigma[d, mfo])
lower[d, mfo] = min(open[d,0], prior_close[d]) × (1 − sigma[d, mfo])
```

```python
def noise_bands(df: pd.DataFrame, lookback: int, min_frac: float = 0.9):
    opens = df[df.mfo == 0].set_index("sdate")["open"]
    last  = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df.sdate.drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)                       # causal

    # sessions x slots matrix: the key vectorisation move
    cm = df.pivot_table(index="sdate", columns="mfo", values="close",
                        aggfunc="last").reindex(dates)
    o0 = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()

    mp = int(np.ceil(min_frac * lookback))
    sigma = move.shift(1).rolling(lookback, min_periods=mp).mean()   # STRICTLY PRIOR

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate", "mfo", "sigma"]
    long = (long.merge(o0.rename("rth_open"), on="sdate")
                .merge(prior_close.rename("prior_close"), on="sdate")
                .dropna(subset=["rth_open", "prior_close", "sigma"]))
    hi = np.maximum(long.rth_open, long.prior_close)
    lo = np.minimum(long.rth_open, long.prior_close)
    long["upper"] = hi * (1 + long.sigma)
    long["lower"] = lo * (1 - long.sigma)
    return long
```

Four things to internalise:

1. **`pivot_table` to a `sessions × slots` matrix** turns "rolling over the same
   minute across days" into one vectorised `.rolling()` on columns. This is the
   single most useful pandas move for intraday seasonality features.
2. **`.shift(1)` on the matrix** shifts along *sessions*, so slot `mfo` on day
   `d` uses only days `< d`. This is the causality guarantee, and it is one
   character away from being wrong.
3. **`min_periods` fraction** — lesson 01 §1.5.
4. The band is anchored at the **session open**, a fixed point. When this
   workspace tried re-anchoring it on the (moving) VWAP, the edge **vanished** —
   the strategy monetises *displacement from a fixed anchor*, and a chasing
   anchor absorbs exactly the drift it rides.

---

## 2.5 RSI

```python
def rsi(close: pd.Series, n: int = 14) -> pd.Series:
    d = close.diff()
    up = d.clip(lower=0)
    dn = (-d).clip(lower=0)
    ru = up.ewm(alpha=1/n, adjust=False, min_periods=n).mean()   # Wilder
    rd = dn.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    rs = ru / rd.replace(0, np.nan)
    return (100 - 100 / (1 + rs)).fillna(100.0)
```

**Trap:** RSI is bounded, so "RSI < 30" looks like a stationary, comparable
condition across eras. It is not — the *frequency* of RSI<30 varies hugely with
volatility regime and with your bar size. Always report how many signals per
year each threshold produces, per era.

---

## 2.6 Bollinger / rolling z-score

```python
m = df.close.rolling(n, min_periods=n).mean()
s = df.close.rolling(n, min_periods=n).std(ddof=1)
df["bb_up"], df["bb_dn"] = m + k*s, m - k*s
df["z"] = (df.close - m) / s
```

**Trap — the "z-score" leak.** The single most common leak in retail-style
research:

```python
df["z"] = (df.close - df.close.mean()) / df.close.std()   # WRONG. Full sample.
```

That uses the whole sample's mean and std at every row. It is lookahead, it is
invisible, and it makes any mean-reversion strategy look excellent because the
mean is *by construction* the level price returns to.

The rolling version above is correct. An **expanding** version is also correct
and often better for a threshold you want stable:

```python
df["z_exp"] = (df.close - df.close.expanding(min_periods=250).mean().shift(1)) \
              / df.close.expanding(min_periods=250).std().shift(1)
```

---

## 2.7 ADX / directional movement

```python
def adx(df, n=14):
    up = df.high.diff()
    dn = -df.low.diff()
    plus_dm  = np.where((up > dn) & (up > 0), up, 0.0)
    minus_dm = np.where((dn > up) & (dn > 0), dn, 0.0)
    prev_close = df.close.shift(1)
    tr = pd.concat([df.high - df.low,
                    (df.high - prev_close).abs(),
                    (df.low - prev_close).abs()], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1/n, adjust=False, min_periods=n).mean()
    pdi = 100 * pd.Series(plus_dm,  index=df.index).ewm(alpha=1/n, adjust=False).mean() / atr
    mdi = 100 * pd.Series(minus_dm, index=df.index).ewm(alpha=1/n, adjust=False).mean() / atr
    dx  = 100 * (pdi - mdi).abs() / (pdi + mdi)
    return dx.ewm(alpha=1/n, adjust=False, min_periods=n).mean(), pdi, mdi
```

**Finding from this workspace (AUDUSD, step 4):** ADX/Hurst/vol daily regime
classifiers are valid *descriptive* tools and useful for **sizing and vetoing**,
but they were **not** a momentum-vs-mean-reversion *selector* — daily AUDUSD
faded in every regime. Don't assume a regime tag switches your strategy's sign.

---

## 2.8 Realized volatility, Parkinson, Garman–Klass

```python
r = np.log(df.close).diff()
rv   = r.rolling(n).std(ddof=1) * np.sqrt(ann)                       # close-to-close
park = np.sqrt((np.log(df.high/df.low)**2).rolling(n).mean() / (4*np.log(2)))
gk   = np.sqrt((0.5*np.log(df.high/df.low)**2
                - (2*np.log(2)-1)*np.log(df.close/df.open)**2).rolling(n).mean())
```

Parkinson/Garman–Klass are 4–8× more efficient estimators than close-to-close
for the same window — use them when your window is short. All three are causal
as written (trailing windows). Remember `ann = sqrt(bars per year)`.

---

## 2.9 Efficiency Ratio and KAMA

```python
def efficiency_ratio(close: pd.Series, n: int) -> pd.Series:
    direction = (close - close.shift(n)).abs()
    volatility = close.diff().abs().rolling(n).sum()
    return direction / volatility          # 0 = pure chop, 1 = straight line

def kama(close, n=10, fast=2, slow=30):
    er = efficiency_ratio(close, n)
    sc = (er * (2/(fast+1) - 2/(slow+1)) + 2/(slow+1)) ** 2
    out = np.full(len(close), np.nan); c = close.to_numpy(); s = sc.to_numpy()
    start = n
    out[start] = c[start]
    for i in range(start+1, len(c)):
        out[i] = out[i-1] + (s[i] if np.isfinite(s[i]) else 0.0) * (c[i] - out[i-1])
    return pd.Series(out, index=close.index)
```

**Finding from this workspace:** the efficiency ratio on the signal bar *is* a
real in-sample per-trade predictor (+0.76R, t = 3.07). It **did not monetise** —
gating on it was a rarity filter that helped *more* on shuffled noise than on
the real tape. This is the archetype of lesson 11: *a signal that predicts
per-trade outcome is not automatically a tradable filter.*

---

## 2.10 Hurst exponent (structure-function estimator)

```python
def hurst(x: np.ndarray, lags=(1,2,3,4,5,7,10,15,20)) -> float:
    """Order-1 generalized Hurst: E|X(t+tau) - X(t)| ~ tau^H, log-log slope."""
    x = np.asarray(x, float)
    n = len(x)
    ls, ys = [], []
    for tau in lags:
        if tau > n // 2:
            break
        d = np.abs(x[tau:] - x[:-tau])
        m = d.mean()
        if m > 0:
            ls.append(np.log(tau)); ys.append(np.log(m))
    if len(ls) < 3:
        return np.nan
    return float(np.polyfit(ls, ys, 1)[0])
```

Validate it before you use it: a pure trend must return ≈1.0, a random walk
≈0.5. (In this workspace: trend → 0.99, RW → 0.49.)

**Traps, all found the hard way here:**

- **Short-window Hurst is mostly noise.** At `n = 30` intraday points, the
  estimator's own standard deviation is **0.17–0.30**. Any "H = 0.58 means
  trending" claim at that window is reading its own error bar. Always simulate
  the estimator's null distribution at *your* sample size before interpreting a
  level.
- **Estimator disagreement is bias, not signal.** R/S, DFA, structure-function,
  and wavelet estimators disagree systematically at small `n`. That disagreement
  is measurement bias, not regime information.
- **Bias-correct against a matched random walk.** Estimate `H` on synthetic RW
  paths of the same length and subtract the mean. In this workspace that turned
  an apparent intraday anti-persistence into ≈0.50 (i.e. nothing), and killed
  ~40% of an apparent coarse-scale effect as saturation artifact.
- Compute it **session-to-date**, anchored at the same open your other features
  use, if you want it causal.

---

## 2.11 Rolling percentile rank (causal)

Useful for making any raw feature comparable across eras:

```python
def causal_pct_rank(s: pd.Series, window: int) -> pd.Series:
    """Rank of the current value within the STRICTLY PRIOR `window` values."""
    return s.rolling(window, min_periods=window//2) \
            .apply(lambda w: (w[:-1] < w[-1]).mean(), raw=True)
```

`.rolling().apply()` is slow — see [03](03_vectorisation.md) §3.6 for the fast
version. Note `w[:-1]`: ranking against a window that *includes* the current
value is a mild but real leak of its own magnitude.

---

## 2.12 Indicator audit test (write this once, run always)

```python
def test_indicator_is_causal(build_fn, df):
    """Truncating the future must not change any past value."""
    full = build_fn(df)
    cut  = len(df) // 2
    part = build_fn(df.iloc[:cut].copy())
    pd.testing.assert_frame_equal(
        full.iloc[:cut][part.columns].reset_index(drop=True),
        part.reset_index(drop=True),
        check_exact=False, rtol=1e-10,
    )
```

**This test finds nearly every lookahead bug in feature code.** If a value
computed with future data present differs from the same value computed without
it, the feature is not causal. Run it against every feature builder you write.

The only legitimate failures are warmup edges (`min_periods`), which you should
handle by comparing only `iloc[warmup:cut]`.

---

## Checklist

- [ ] Every indicator has an explicit `min_periods`.
- [ ] `ewm(..., adjust=False)` wherever you mean "the EMA".
- [ ] Wilder smoothing is `alpha=1/n`, not `span=n`.
- [ ] Every cross-session/rolling statistic has a visible `.shift(1)`.
- [ ] No full-sample mean/std/quantile anywhere.
- [ ] Volatility-scaled units (ATR), never fixed ticks, for anything compared
      across eras.
- [ ] `test_indicator_is_causal` passes for every feature builder.
- [ ] Any estimator with meaningful small-sample bias (Hurst, skew, kurtosis,
      correlation) has its null distribution simulated at *your* sample size.

Next: [03 — Vectorisation & performance](03_vectorisation.md)
