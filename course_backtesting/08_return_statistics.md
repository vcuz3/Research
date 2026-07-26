# 08 — Statistical properties of returns

Before you test whether a strategy's returns are significant, you must know what
kind of distribution you are testing. Nearly every standard test assumes
properties that financial returns do not have.

---

## 8.1 Which return, exactly?

```python
simple = px.pct_change()                 # p_t/p_{t-1} - 1   (aggregates across ASSETS)
log    = np.log(px).diff()               # ln(p_t/p_{t-1})   (aggregates across TIME)
```

- **Log returns** are additive over time: `r_{1:n} = Σ r_i`. Use them for
  time-series work, volatility scaling, and anything you sum.
- **Simple returns** are additive across a portfolio: `r_p = Σ w_i r_i`. Use
  them for cross-sectional aggregation.
- They differ by `r_log ≈ r_simple − r²/2`. Immaterial at 1-minute scale, very
  material for daily returns of a leveraged or volatile series.
- **Never mix them in one analysis.** Compounding log returns as if simple
  overstates; summing simple returns as if log understates.

For a futures strategy with no capital base, work in **points** or **R**, not
returns, and be explicit about it. `R` is the right cross-era unit (lesson 07).

---

## 8.2 The four moments, and their standard errors

```python
from scipy import stats

def moments(x: pd.Series) -> dict:
    x = x.dropna().to_numpy()
    n = len(x)
    return dict(
        n=n,
        mean=x.mean(),
        se_mean=x.std(ddof=1)/np.sqrt(n),
        var=x.var(ddof=1),
        sd=x.std(ddof=1),
        skew=stats.skew(x, bias=False),
        se_skew=np.sqrt(6*n*(n-1)/((n-2)*(n+1)*(n+3))),
        kurt=stats.kurtosis(x, fisher=True, bias=False),   # EXCESS kurtosis
        se_kurt=2*np.sqrt(6*n*(n-1)/((n-2)*(n+1)*(n+3)))*np.sqrt((n**2-1)/((n-3)*(n+5))),
        median=np.median(x),
        iqr=np.subtract(*np.percentile(x, [75, 25])),
        min=x.min(), max=x.max(),
        p01=np.percentile(x, 1), p99=np.percentile(x, 99),
    )
```

**Always print the standard errors.** Skew and kurtosis are catastrophically
noisy in small samples: with `n = 250` daily observations, the SE of skew is
~0.15 and of excess kurtosis ~0.31, and both are heavily biased by a single
outlier. A reported skew of −0.4 on a year of data is not distinguishable from
zero.

**Use `bias=False`** — scipy defaults to the biased (population) estimators.

---

## 8.3 The stylised facts you must assume are present

| Fact | Consequence for your testing |
|---|---|
| **Fat tails** — excess kurtosis 3–20 at daily, 10–100+ at 1-minute | Normal-theory t-tests understate tail risk; VaR from a normal is badly wrong |
| **Negative skew** in index returns | Sharpe rewards a strategy for selling tails; Sortino flatters it further |
| **Volatility clustering** (GARCH) | Returns are not i.i.d. → block bootstrap, not i.i.d. bootstrap |
| **Near-zero return autocorrelation, high |return| autocorrelation** | Prices ≈ unforecastable, volatility very forecastable |
| **Aggregational Gaussianity** | Fat tails shrink as you aggregate; monthly is much closer to normal than 1-minute |
| **Leverage effect** | Volatility rises more after down moves; a symmetric vol model mis-sizes |
| **Non-stationarity across regimes** | Full-sample statistics describe no actual period |

The practical summary: **the mean is the hardest thing to estimate and the only
thing you care about.** Standard error of the mean scales as `σ/√n`; with fat
tails and clustering, the *effective* `n` is far below your nominal `n`.

---

## 8.4 Testing normality (and why you'll fail)

```python
from scipy import stats
print(stats.jarque_bera(x))       # joint skew+kurtosis test
print(stats.shapiro(x[:5000]))    # more powerful, n <= 5000
```

You will reject normality on essentially any financial return series. That is
expected and not itself a problem. What matters is **which of your methods
depend on normality**:

| Method | Normality needed? |
|---|---|
| Sample mean, t-stat (large n) | No — CLT, but n must be *effectively* large |
| Sharpe ratio point estimate | No |
| Sharpe **standard error** (Lo's formula) | Yes, unless you use the non-IID version |
| Deflated Sharpe Ratio | Explicitly corrects for skew/kurtosis |
| Normal VaR / parametric tail risk | Yes — and it will badly understate |
| Bootstrap / permutation tests | **No** — this is why they are preferred here |

**Practical rule:** when fat tails matter, use resampling (lesson 09), not a
parametric formula.

---

## 8.5 Autocorrelation and effective sample size

```python
from statsmodels.tsa.stattools import acf
from statsmodels.stats.diagnostic import acorr_ljungbox

ac = acf(x, nlags=20, fft=True)
print(acorr_ljungbox(x, lags=[5, 10, 20], return_df=True))   # joint test

# Volatility clustering: autocorrelation of ABSOLUTE returns
ac_abs = acf(np.abs(x), nlags=20, fft=True)
```

You will typically see `ac ≈ 0` and `ac_abs` strongly positive and slowly
decaying. That is volatility clustering.

### Effective sample size

Positive autocorrelation means your `n` observations contain less information
than `n` independent ones:

```python
def effective_n(x, max_lag=50):
    r = acf(x, nlags=max_lag, fft=True)[1:]
    n = len(x)
    denom = 1 + 2 * sum((1 - k/n) * r[k-1] for k in range(1, max_lag+1))
    return n / max(denom, 1e-9)
```

If `effective_n` is half your nominal `n`, every t-stat you computed is inflated
by `√2 ≈ 1.41`. Compute it; it is one line and it recalibrates your intuition
permanently.

---

## 8.6 Heteroskedasticity and why you should normalise

Volatility varies by a factor of 5–10 across eras. Consequences:

1. **Un-normalised P&L is dominated by high-vol periods.** A "full sample"
   result is often a 2008/2020 result.
2. **A t-test on raw P&L is inefficient** — it weights noisy periods equally
   with informative ones.
3. **Fixed costs bite differently** — this is Rule 19, and it cuts the other
   way: σ-normalising makes high-vol eras look *better* net of a fixed tick
   cost, because the cost is a smaller fraction of σ.

Because (1) and (3) point in opposite directions, **report both**:

```python
day_usd = trades.groupby("date").net_pts.sum() * POINT_VALUE
day_R   = trades.groupby("date").R_net.sum()
```

If a result exists in dollars and vanishes in R, it is vol-era weighting. If it
exists in R and vanishes in dollars, it is too small to pay costs. Both are
rejections; they just have different write-ups.

---

## 8.7 Stationarity

```python
from statsmodels.tsa.stattools import adfuller, kpss
print(adfuller(x, autolag="AIC"))     # H0: unit root (non-stationary)
print(kpss(x, regression="c", nlags="auto"))  # H0: stationary
```

Use both — they have opposite nulls, and agreement is informative:

| ADF | KPSS | Conclusion |
|---|---|---|
| reject | fail to reject | stationary ✔ |
| fail | reject | unit root / non-stationary |
| fail | fail | not enough information — inconclusive |
| reject | reject | likely fractionally integrated / structural break |

**Prices are non-stationary. Returns are approximately stationary in level but
not in variance.** Never build a feature on raw prices without differencing,
ratioing, or normalising — a linear model on price levels finds the trend and
nothing else.

---

## 8.8 Aggregation: how the distribution changes with horizon

```python
for k in (1, 5, 20, 60):
    agg = x.rolling(k).sum().dropna()[::k]      # NON-OVERLAPPING
    print(f"h={k:3d} n={len(agg):5d} mean={agg.mean():+.5f} "
          f"sd={agg.std(ddof=1):.5f} skew={stats.skew(agg):+.2f} "
          f"exkurt={stats.kurtosis(agg):+.2f}")
```

Note `[::k]` — **non-overlapping**. Overlapping aggregation inflates `n` by `k`
and understates the standard error by `√k`. This is one of the most common
errors in horizon studies.

Under i.i.d., mean scales with `k` and sd with `√k`. Deviations from that are
exactly the variance-ratio signal from lesson 04. Excess kurtosis should shrink
roughly as `1/k` (aggregational Gaussianity); if it doesn't, you have persistent
jumps.

---

## 8.9 Tail risk

```python
def tail_stats(x, alpha=0.05):
    x = np.sort(x.dropna().to_numpy())
    k = max(1, int(alpha * len(x)))
    var  = x[k-1]                                # historical VaR (a quantile)
    cvar = x[:k].mean()                          # expected shortfall / CVaR
    return dict(VaR=var, CVaR=cvar,
                worst=x[0], worst5=x[:5].tolist(),
                normal_VaR=x.mean() + stats.norm.ppf(alpha)*x.std(ddof=1))
```

Compare `VaR` to `normal_VaR`: the gap is your fat-tail penalty, and on daily
strategy P&L it is typically 20–50%.

**Rule 22: measure risk at the horizon where exposure and capital accumulate.**
Per-trade risk alone is insufficient because losses cluster. Report:

```python
worst_day   = day_pnl.min()
worst_week  = day_pnl.resample("W").sum().min()
worst_month = day_pnl.resample("ME").sum().min()
max_consecutive_losing_days = ...
concentration = trades.nlargest(10, "net_pts").net_pts.sum() / trades.net_pts.sum()
```

That last one — **top-10 concentration** — is the most under-reported diagnostic
in the discipline. If 10 trades out of 4000 produce 60% of the P&L, your Sharpe
is describing a lottery, and the standard error on your mean is far larger than
the formula suggests.

---

## 8.10 Regime and stability diagnostics

```python
# rolling Sharpe: the single most informative strategy plot
roll_sh = (day_pnl.rolling(252).mean() /
           day_pnl.rolling(252).std(ddof=1) * np.sqrt(252))

# cumulative t-stat: does significance accumulate steadily or in one burst?
cum_mean = day_pnl.expanding().mean()
cum_se   = day_pnl.expanding().std(ddof=1) / np.sqrt(np.arange(1, len(day_pnl)+1))
cum_t    = cum_mean / cum_se
```

Read the cumulative t-stat curve:
- **Steadily rising** → the effect accumulates across the sample. Good.
- **One vertical jump then flat** → one event produced your significance.
- **Rising then declining** → the effect decayed. This is the *normal* fate of a
  published edge, and it is what was observed for the NQ strategy here after
  publication (genuine decay, confirmed, not a bug).

Also run a formal break test if the visual suggests one:

```python
# Chow-style: split at a candidate date, compare means with a Welch t-test
a, b = day_pnl[:split], day_pnl[split:]
print(stats.ttest_ind(a, b, equal_var=False))
```

But note: choosing the split **by looking at the data** makes the p-value
meaningless. Either preregister the split date (e.g. publication date) or use a
sup-Wald test that corrects for the search.

---

## 8.11 Distribution of the metric, not just of the returns

The distribution you actually need is not the return distribution — it is the
**sampling distribution of your metric** under your data's dependence structure.
Get it by block bootstrap:

```python
def block_bootstrap(x, stat_fn, block=20, n_boot=2000, seed=0):
    """Stationary/circular block bootstrap: preserves local dependence."""
    rng = np.random.default_rng(seed)
    x = x.dropna().to_numpy(); n = len(x)
    nb = int(np.ceil(n / block))
    out = np.empty(n_boot)
    for b in range(n_boot):
        starts = rng.integers(0, n, size=nb)
        idx = (starts[:, None] + np.arange(block)[None, :]).ravel()[:n] % n
        out[b] = stat_fn(x[idx])
    return out

boot = block_bootstrap(day_pnl, lambda v: v.mean()/v.std(ddof=1)*np.sqrt(252))
print(f"Sharpe {sharpe:.2f}  95% CI [{np.percentile(boot,2.5):.2f}, "
      f"{np.percentile(boot,97.5):.2f}]  P(Sharpe<=0)={np.mean(boot<=0):.3f}")
```

**Choosing the block length:** roughly the horizon over which your returns are
dependent — the lag at which `|return|` autocorrelation decays, or `n^{1/3}` as
a default. Too short destroys clustering (and understates uncertainty); too long
gives you too few independent blocks.

If you report one uncertainty number for a strategy, make it this confidence
interval. A Sharpe of 1.3 with a 95% CI of [0.2, 2.4] is a very different claim
from 1.3 with [1.0, 1.6], and the point estimate alone hides it completely.

---

## 8.12 A standard "return properties" report

```python
def return_report(day_pnl: pd.Series) -> str:
    m = moments(day_pnl)
    lines = [
      f"n={m['n']}  mean={m['mean']:+.4f} (se {m['se_mean']:.4f})  "
      f"sd={m['sd']:.4f}",
      f"skew={m['skew']:+.3f} (se {m['se_skew']:.3f})  "
      f"exkurt={m['kurt']:+.3f} (se {m['se_kurt']:.3f})",
      f"median={m['median']:+.4f}  IQR={m['iqr']:.4f}  "
      f"min={m['min']:+.3f}  max={m['max']:+.3f}",
      f"JB p={stats.jarque_bera(day_pnl.dropna()).pvalue:.2e}",
      f"LB(10) p={acorr_ljungbox(day_pnl.dropna(), lags=[10]).iloc[0,1]:.3f}  "
      f"LB|x|(10) p={acorr_ljungbox(day_pnl.dropna().abs(), lags=[10]).iloc[0,1]:.2e}",
      f"eff_n={effective_n(day_pnl.dropna()):.0f} of {m['n']}",
      f"VaR5={tail_stats(day_pnl)['VaR']:+.3f}  "
      f"CVaR5={tail_stats(day_pnl)['CVaR']:+.3f}  "
      f"normalVaR5={tail_stats(day_pnl)['normal_VaR']:+.3f}",
      f"top10 concentration={concentration:.1%}",
    ]
    return "\n".join(lines)
```

Run this on your strategy's daily P&L **before** you compute a single
significance test. It tells you which tests are even applicable.

---

## Checklist

- [ ] Log vs simple returns chosen deliberately and not mixed.
- [ ] Moments reported **with standard errors**, `bias=False`.
- [ ] Autocorrelation of returns **and** of |returns| checked.
- [ ] Effective sample size computed; t-stats deflated accordingly.
- [ ] Results reported in both dollars and volatility-normalised units.
- [ ] Aggregation done non-overlapping.
- [ ] Tail risk measured historically (CVaR), not from a normal.
- [ ] Risk measured at the horizon where capital accumulates (day/week/month).
- [ ] Top-10 trade concentration reported.
- [ ] Rolling Sharpe and cumulative t-stat inspected for regime structure.
- [ ] Metric uncertainty from a **block** bootstrap, not an i.i.d. one.

Next: [09 — Statistical evaluation & inference](09_statistical_evaluation.md)
