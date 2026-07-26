# 09 — Statistical evaluation: what to compute and how

> **Read first:** none of these tests detect lookahead, accounting errors, or
> fill artifacts. They quantify *selection and uncertainty* only. Run lesson 06's
> pre-flight checklist before any of this. In this workspace a strategy passed
> era stability, DSR = 1.000, and a frozen OOS holdout and was ~80% fake.

---

## 9.1 The inference unit

Trades on the same day are not independent. Choose your unit and be consistent:

| Unit | When |
|---|---|
| **Trade** | Only if trades are genuinely far apart in time |
| **Session/day** | Default for intraday strategies — the day is the risk unit |
| **Week/month** | When positions or exposure persist across days |
| **Block of days** | Always, for resampling |

The workspace default:

```python
def cluster_t(day_pnl: pd.Series) -> tuple[float, float]:
    """Mean and t-stat of a per-day P&L series (the day IS the risk unit)."""
    x = day_pnl.to_numpy(float); n = len(x)
    if n < 2: return (float(x.mean()) if n else 0.0), 0.0
    m = x.mean(); se = x.std(ddof=1) / np.sqrt(n)
    return m, (m / se if se > 0 else 0.0)
```

**How much this matters:** in this workspace, retrospective session weighting
turned a per-bet t of **−1.1** into **−12.4**. Same data, different estimand.
An order of magnitude.

---

## 9.2 Clustered and HAC standard errors

When you regress rather than average:

```python
import statsmodels.api as sm

X = sm.add_constant(features)
# Cluster by session
res = sm.OLS(y, X).fit(cov_type="cluster", cov_kwds={"groups": session_id})
# Or Newey-West HAC for serial correlation
res = sm.OLS(y, X).fit(cov_type="HAC", cov_kwds={"maxlags": L})
```

Choosing `L` for Newey-West: `L ≈ floor(4·(n/100)^{2/9})` is the standard
rule of thumb; for overlapping `h`-period returns use at least `h − 1`.

**Two-way clustering** (by date *and* by instrument) matters for cross-sectional
panels — use `cov_type="cluster"` with a 2-column `groups` array.

---

## 9.3 Sharpe ratio inference

### Lo's standard error (i.i.d. case)

```python
def sharpe_se_iid(sr_periodic: float, n: int) -> float:
    return np.sqrt((1 + 0.5 * sr_periodic**2) / n)
```

At `n = 252` and `SR_daily = 0.08` (≈1.27 annualised), the SE of the *daily*
Sharpe is ≈0.063 — so annualised Sharpe 1.27 has a ±2 SE band of roughly
**[0.3, 2.3]** on one year of data. One year of data tells you almost nothing.

### The non-i.i.d. version (skew/kurtosis-aware)

```python
def sharpe_se(returns: pd.Series) -> float:
    """Mertens/Opdyke SE for SR under non-normality."""
    r = returns.dropna().to_numpy(); n = len(r)
    sr = r.mean() / r.std(ddof=1)
    s  = stats.skew(r, bias=False)
    k  = stats.kurtosis(r, fisher=False, bias=False)     # NON-excess
    return float(np.sqrt((1 + 0.5*sr**2 - s*sr + (k-3)/4*sr**2) / n))
```

Negative skew (typical) **increases** the SE — the standard i.i.d. formula is
optimistic for exactly the return shape strategies usually have.

### The minimum track record length

How long must the sample be for `SR > 0` at confidence `α`?

```python
def min_track_record_length(sr, skew_, kurt_, sr_benchmark=0.0, alpha=0.05):
    z = stats.norm.ppf(1 - alpha)
    return 1 + (1 - skew_*sr + (kurt_-1)/4*sr**2) * (z/(sr - sr_benchmark))**2
```

For a daily Sharpe corresponding to annualised 1.0, this is roughly **2–3 years**
of daily data just to establish `SR > 0` at 95%. Internalise that number. Most
"validated" strategies are tested on far less.

---

## 9.4 Comparing two Sharpe ratios (the variant test)

This is what you need for "is variant B better than baseline A?". The series are
**paired and highly correlated** — an unpaired test is badly wrong.

### Ledoit–Wolf / Jobson–Korkie–Memmel test

```python
def jkm_sharpe_diff(ra: pd.Series, rb: pd.Series):
    """Test SR_b - SR_a = 0 for paired, correlated return series."""
    d = pd.concat([ra, rb], axis=1).dropna()
    a, b = d.iloc[:, 0].to_numpy(), d.iloc[:, 1].to_numpy()
    n = len(a)
    mu_a, mu_b = a.mean(), b.mean()
    va, vb = a.var(ddof=1), b.var(ddof=1)
    sa, sb = np.sqrt(va), np.sqrt(vb)
    rho = np.corrcoef(a, b)[0, 1]
    sr_a, sr_b = mu_a/sa, mu_b/sb
    theta = (1/n) * (2 - 2*rho
                     + 0.5*(sr_a**2 + sr_b**2 - 2*sr_a*sr_b*rho**2))
    diff = sr_b - sr_a
    return diff, diff/np.sqrt(theta), 2*(1 - stats.norm.cdf(abs(diff)/np.sqrt(theta)))
```

For non-normal returns, prefer the **paired block bootstrap** instead:

```python
def paired_block_bootstrap_sharpe_diff(ra, rb, block=20, n_boot=5000, seed=0):
    """Resample DATES jointly so the pairing (and correlation) is preserved."""
    rng = np.random.default_rng(seed)
    d = pd.concat([ra, rb], axis=1).dropna()
    a, b = d.iloc[:,0].to_numpy(), d.iloc[:,1].to_numpy()
    n = len(a); nb = int(np.ceil(n/block))
    out = np.empty(n_boot)
    for i in range(n_boot):
        st = rng.integers(0, n, size=nb)
        idx = (st[:,None] + np.arange(block)[None,:]).ravel()[:n] % n
        aa, bb = a[idx], b[idx]
        out[i] = bb.mean()/bb.std(ddof=1) - aa.mean()/aa.std(ddof=1)
    real = b.mean()/b.std(ddof=1) - a.mean()/a.std(ddof=1)
    return real, np.percentile(out, [2.5, 97.5]), float((out <= 0).mean())
```

**Always resample dates jointly.** Resampling the two series independently
destroys the pairing and gives you a much wider (wrong) interval.

---

## 9.5 Multiple testing — the central problem

You tried `N` configurations. The best one's t-stat is a **maximum of N**
t-stats. Under the null with `N = 50` independent trials, `E[max t] ≈ 2.6`, so a
t of 2.6 is *exactly what noise produces*.

### Bonferroni / Holm / Benjamini–Hochberg

```python
from statsmodels.stats.multitest import multipletests
rej, p_adj, _, _ = multipletests(pvals, alpha=0.05, method="holm")   # FWER
rej, p_adj, _, _ = multipletests(pvals, alpha=0.10, method="fdr_bh") # FDR
```

Use **Holm** (FWER) when a single false positive is expensive — i.e. when you
are about to deploy capital. Use **BH** (FDR) when screening many candidates and
you will validate survivors separately.

### Harvey–Liu haircut

The practical rule from the multiple-testing literature: with the number of
strategies actually tried in the field, a t-stat of **3.0** is the appropriate
threshold for a "new factor", not 2.0. Their haircut Sharpe approach shrinks the
reported Sharpe as a function of `N`:

```python
def haircut_sharpe(sr_annual, n_trials, n_years, alpha=0.05):
    """Crude Holm-style haircut: what SR survives after correcting for N trials?"""
    t_obs  = sr_annual * np.sqrt(n_years)
    p_obs  = 2*(1 - stats.norm.cdf(abs(t_obs)))
    p_adj  = min(1.0, p_obs * n_trials)             # Bonferroni
    t_adj  = stats.norm.ppf(1 - p_adj/2)
    return max(0.0, t_adj / np.sqrt(n_years)), p_adj
```

### The number that matters is the one you can't remember

`N` is not the size of the grid in your last script. It is **every
configuration you have ever looked at on this data**, including the ones you
abandoned. This is why the `IDEA_BACKLOG.md` and the run ledger exist. If you
cannot state `N`, state that you cannot, and treat the result as discovery.

---

## 9.6 Deflated Sharpe Ratio (DSR)

Bailey & López de Prado's correction for selection bias, non-normality, and
sample length simultaneously.

```python
def deflated_sharpe(sr, n, skew_, kurt_, n_trials, sr_trials_std=None):
    """
    sr    : observed SR, per-period (NOT annualised)
    n     : number of observations
    kurt_ : NON-excess kurtosis
    n_trials       : number of independent configurations tried
    sr_trials_std  : std dev of SRs across trials (best estimate if available)
    Returns P(true SR > 0) after deflation.
    """
    e = 0.5772156649                                   # Euler-Mascheroni
    if sr_trials_std is None:
        sr_trials_std = abs(sr) / 2                    # crude fallback
    # expected max SR under the null across n_trials
    z1 = stats.norm.ppf(1 - 1/n_trials)
    z2 = stats.norm.ppf(1 - 1/(n_trials*np.e))
    sr0 = sr_trials_std * ((1-e)*z1 + e*z2)
    num = (sr - sr0) * np.sqrt(n - 1)
    den = np.sqrt(1 - skew_*sr + (kurt_-1)/4*sr**2)
    return float(stats.norm.cdf(num/den))
```

Read it as: *"the probability that the true Sharpe exceeds zero, given that I
selected this configuration as the best of `n_trials`."*

**DSR > 0.95** is the usual bar. **But** — and this workspace has the receipt —
DSR = 1.000 on a strategy whose edge was an impossible fill. DSR corrects for
selection; it cannot see your counterfactual.

Sources: [Bailey & López de Prado, SSRN](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551),
[PDF](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf).

---

## 9.7 Probability of Backtest Overfitting (PBO / CSCV)

Combinatorially Symmetric Cross-Validation asks: *when I pick the best
configuration in-sample, how often does it land below median out-of-sample?*

```python
from itertools import combinations

def pbo_cscv(perf: np.ndarray, S: int = 16) -> float:
    """
    perf: (T x N) matrix of per-period performance for N configurations.
    Split time into S blocks, take all balanced train/test partitions,
    pick the IS-best config, record its OOS rank.
    Returns PBO = P(IS-best is below OOS median).
    """
    T, N = perf.shape
    blocks = np.array_split(np.arange(T), S)
    lam = []
    for tr in combinations(range(S), S//2):
        te = [b for b in range(S) if b not in tr]
        i_tr = np.concatenate([blocks[b] for b in tr])
        i_te = np.concatenate([blocks[b] for b in te])
        def sr(m):
            sd = m.std(axis=0, ddof=1)
            return np.where(sd > 0, m.mean(axis=0)/np.where(sd > 0, sd, 1), 0.0)
        best = int(np.argmax(sr(perf[i_tr])))
        oos  = sr(perf[i_te])
        rank = (oos < oos[best]).sum() / N               # relative rank in [0,1]
        lam.append(np.log(rank/(1-rank)) if 0 < rank < 1 else (-10 if rank == 0 else 10))
    lam = np.array(lam)
    return float((lam < 0).mean())
```

Interpretation:
- **PBO < 0.10** → selection is likely picking real signal.
- **PBO > 0.50** → your selection procedure is worse than random. The
  "optimisation" is fitting noise.

`S = 16` gives 12,870 partitions — expensive but tractable. PBO is one of the
few tests that evaluates your **selection procedure** rather than one result,
which is exactly what walk-forward optimisation needs.

Source: [Bailey et al., The Probability of Backtest Overfitting](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting).

---

## 9.8 White's Reality Check / Hansen's SPA

For "is the *best* of my `N` strategies better than a benchmark?", with the
correct joint distribution:

```python
def hansen_spa(losses: np.ndarray, block=20, n_boot=2000, seed=0):
    """
    losses: (T x N) matrix of BENCHMARK-minus-strategy performance
            (positive = strategy beats benchmark).
    Returns SPA p-value for H0: no strategy beats the benchmark.
    """
    rng = np.random.default_rng(seed)
    T, N = losses.shape
    mu = losses.mean(axis=0)
    sd = losses.std(axis=0, ddof=1) / np.sqrt(T)
    t_obs = np.max(mu / np.where(sd > 0, sd, np.inf))
    # recentre (Hansen's studentised, consistent recentring)
    thresh = -sd * np.sqrt(2*np.log(np.log(T)))
    mu_c = np.where(mu >= thresh, mu, 0.0)
    nb = int(np.ceil(T/block))
    boot = np.empty(n_boot)
    for b in range(n_boot):
        st = rng.integers(0, T, size=nb)
        idx = (st[:,None] + np.arange(block)[None,:]).ravel()[:T] % T
        m = losses[idx].mean(axis=0) - mu_c
        boot[b] = np.max(m / np.where(sd > 0, sd, np.inf))
    return float((boot >= t_obs).mean())
```

SPA is strictly better than White's Reality Check because the recentring stops
poor strategies in the family from inflating the critical value. Use it when you
have a genuine family of candidates and one benchmark.

---

## 9.9 Cross-validation for time series

**Never use plain `KFold` on time series.** Two additional requirements:

- **Purging** — remove training observations whose *label horizon* overlaps the
  test set.
- **Embargo** — additionally drop a buffer after the test set, because serial
  correlation leaks forward.

```python
def purged_kfold(n, n_splits=5, horizon=60, embargo=0.01):
    """Yield (train_idx, test_idx) with purge + embargo."""
    idx = np.arange(n)
    folds = np.array_split(idx, n_splits)
    emb = int(n * embargo)
    for f in folds:
        lo, hi = f[0], f[-1]
        train = np.concatenate([
            idx[: max(0, lo - horizon)],
            idx[min(n, hi + horizon + emb):],
        ])
        yield train, f
```

Without purging, a model trained on bar `t−1` and tested on bar `t` with a
60-bar label horizon has literally seen the answer.

### Walk-forward

```python
def walk_forward(dates, train_years=5, test_years=1, step_years=1):
    start = dates.min()
    while start + pd.DateOffset(years=train_years+test_years) <= dates.max():
        tr_end = start + pd.DateOffset(years=train_years)
        te_end = tr_end + pd.DateOffset(years=test_years)
        yield (dates < tr_end) & (dates >= start), (dates >= tr_end) & (dates < te_end)
        start += pd.DateOffset(years=step_years)
```

**The honest caveat, from this workspace:** walk-forward optimisation over a
parameter grid was a NO-GO here. WFO does not remove overfitting; it *relocates*
it. You are still selecting on data you have inspected, and each refit is another
trial. Report WFO results with a PBO number attached, or don't report them as
validation.

---

## 9.10 Permutation and randomisation tests (the workhorse)

Preferred over parametric tests because they make no distributional assumption
and — critically — can be made to **re-run the full pipeline** (lesson 10).

```python
def permutation_p(real_stat, null_stats, higher_is_better=True):
    """Upper-tail p with the +1 correction (never report p=0)."""
    null_stats = np.asarray(null_stats)
    k = (null_stats >= real_stat).sum() if higher_is_better else (null_stats <= real_stat).sum()
    return (k + 1) / (len(null_stats) + 1)
```

The `+1` matters: with 30 draws and 0 beating real, the honest p is `1/31 =
0.032`, not 0. This workspace reports exactly that number.

**On draw counts:** 30 full-pipeline draws gives you a minimum p of 0.032 —
enough for a 0.05 gate, not enough to distinguish 0.03 from 0.001. Use 200+
draws for cheap nulls (trade-level random drops) and 30–50 for expensive ones
(full re-run with feature rebuild).

---

## 9.11 Reporting a result honestly

A complete statistical report contains:

```
CONFIG      : <frozen config or its hash>
SAMPLE      : instrument, dates, n_days, n_trades, sample status (consumed?)
LABEL       : DISCOVERY | SEARCHED | CONFIRMATORY
FAMILY      : N configurations searched; this is the family-max / a fixed cell
PRIMARY     : <metric> = <value>  (uplift over baseline = <delta>)
INFERENCE   : day-clustered t = <t>; block-bootstrap 95% CI [lo, hi]
NULL        : <null name>, k draws, null mean +/- sd, p = (k+1)/(n+1)
NULL CENTER : positive/negative — and what that implies
MULTIPLE    : Holm/BH-adjusted p, or DSR with n_trials
CONTROLS    : matched-count random drop; sibling market; symmetric bracket;
              gross-per-trade on kept trades; cost ladder
ERA         : per-era table (gross, cost, net)
CAPACITY    : trades/year, size at which fills break
VERDICT     : GO | NO-GO | QUALIFIED | INCONCLUSIVE, and what would change it
```

If a section is missing, say it is missing. An incomplete report with declared
gaps is far more useful than a complete-looking one with silent gaps.

---

## 9.12 Decision thresholds used in this workspace

Not universal law — but calibrated by several years of results that died:

| Gate | Threshold |
|---|---|
| Sharpe uplift for adopting a variant | **≥ +0.10** daily Sharpe, **and** net R ≥ baseline |
| Sharpe uplift for a capacity/turnover lever | ≥ +0.05, labelled as a lever, not alpha |
| Null-C significance | `frac(null ≥ real) < 0.05`, **and** z ≥ 2 |
| Matched-count random-drop null | `frac(random ≥ real) < 0.05` |
| Cross-market transfer | sign must transfer to the sibling |
| Cost robustness | survives 1 tick/side; ideally 2 |
| Era consistency | ≥ 3 of 4 eras improve on both net R and drawdown |

And the standing efficiency rule:

> **Gate the expensive null on the primary metric.** If the real run does not
> clear its Sharpe/net-R gate, it is already a REJECT. Do not spend 30 Null-C
> draws to confirm a rejection.

This one rule has saved more compute here than every optimisation in lesson 03.

---

Next: [10 — Null models & negative controls](10_nulls_and_controls.md)

Sources:
- [Bailey & López de Prado — The Deflated Sharpe Ratio (SSRN)](https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2460551)
- [The Deflated Sharpe Ratio (PDF)](https://www.davidhbailey.com/dhbpapers/deflated-sharpe.pdf)
- [Bailey, Borwein, López de Prado, Zhu — The Probability of Backtest Overfitting](https://www.researchgate.net/publication/318600389_The_probability_of_backtest_overfitting)
- [Portfolio Optimization Book §8.3 — The Dangers of Backtesting](https://portfoliooptimizationbook.com/book/8.3-dangers-backtesting.html)
