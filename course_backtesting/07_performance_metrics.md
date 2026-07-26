# 07 — Performance metrics: definitions, formulas, code

Every metric here is given with its exact definition, the convention choices
that change the number, and code. Conventions matter more than you think — two
correct implementations of "Sharpe" can differ by 30%.

---

## 7.0 The three questions every metric set must answer

1. **How much?** — CAGR, total net R, P&L per trade, per day, per year.
2. **At what risk?** — Sharpe, Sortino, Calmar, max drawdown, tail loss.
3. **At what cost and capacity?** — gross vs net, turnover, trades/year, size
   at which it breaks.

A report that answers only (1) and (2) is incomplete. Rule 21: *an effect in R
or σ is incomplete without trades per year, dollars per unit, capital usage, and
evidence that fills and risk are realizable at the claimed size.*

---

## 7.1 The R multiple — get this right first

**R** is your risk unit: the P&L of a trade divided by the risk committed at
entry.

```python
R = (exit_px - entry_px) * side / risk_at_entry
```

`risk_at_entry` must be **frozen at entry** (Rule 14) and can be:

- the distance from fill to the initial stop (the natural choice when you have
  a hard stop), or
- a volatility scale — `k × ATR` — when the stop is a trailing/level construct
  with no fixed initial distance.

This workspace uses **`R = net_points / ATR`** because the band/VWAP stop has no
fixed entry distance. Say which you use; they are not interchangeable.

```python
trades["R_gross"] = trades.points / trades.atr
trades["R_net"]   = (trades.points - rt_cost) / trades.atr
```

**Why R and not dollars?** A fixed dollar effect is not comparable across
volatility eras. **Why also dollars?** Because a fixed *tick cost* consumes a
smaller fraction of σ as volatility rises, so σ-normalised results are
mechanically flattered in high-vol eras (Rule 19). **Report both.** A result
that exists in dollars but vanishes in R is a volatility-era-weighting artifact
— this exact pattern killed a "15-minute exit cadence" improvement here.

### Gross R, net R, expected R

```python
gross_R   = trades.R_gross.sum()          # total, before costs
net_R     = trades.R_net.sum()            # total, after costs
exp_R     = trades.R_net.mean()           # expectancy per trade, in R
exp_R_se  = trades.R_net.std(ddof=1) / np.sqrt(len(trades))
```

Sanity anchors: an intraday futures strategy with `exp_R ≈ 0.02–0.05` and a few
thousand trades is a plausible real edge. `exp_R > 0.5` on thousands of trades
means you have a bug.

**Report gross and net side by side, always.** If `gross ≈ modeled cost`, your
conclusion is cost-model-dependent, not a robust edge (Rule 20).

---

## 7.2 Expectancy, hit ratio, payoff ratio

```python
n      = len(t)
wins   = t[t.net_pts > 0]
losses = t[t.net_pts <= 0]

hit_ratio    = len(wins) / n
avg_win      = wins.net_pts.mean()
avg_loss     = losses.net_pts.mean()               # negative
payoff_ratio = abs(avg_win / avg_loss)
expectancy   = hit_ratio * avg_win + (1 - hit_ratio) * avg_loss   # == t.net_pts.mean()
profit_factor = wins.net_pts.sum() / abs(losses.net_pts.sum())
```

### The break-even identity you must always quote alongside a hit ratio

```
break_even_hit = 1 / (1 + payoff_ratio)
```

A hit ratio of 38% means nothing until you know the payoff ratio. For a fixed
2:1 bracket, break-even is 33.3%; observing 33.4% means **no edge**, regardless
of the equity curve. This is exactly how the GC VWAP fade was killed here.

```python
print(f"hit={hit_ratio:.3f}  break-even={1/(1+payoff_ratio):.3f}  "
      f"edge={hit_ratio - 1/(1+payoff_ratio):+.3f}")
```

**Trap:** a high hit ratio with a small payoff is the classic loser. A GC
direction-conditioner here had hit rate rise to 46% and still lost, because the
per-trade payoff was too small for the bracket.

---

## 7.3 The P&L series: the choice that determines everything downstream

**Rule 13:** daily P&L is the **sum** of position-level P&L, not the mean of the
day's trades.

```python
day_pnl = trades.groupby("date").net_pts.sum() * POINT_VALUE[inst]
```

### Zero-trade days: include or exclude?

This changes Sharpe substantially and there is no universally right answer —
there is only a **stated** answer.

```python
all_days = pd.date_range(start, end, freq="B")          # or your session calendar
day_pnl_zero = day_pnl.reindex(all_days, fill_value=0.0)
```

- **Include zeros** if you model the strategy as always-allocated capital. Lower
  mean, lower std, generally lower Sharpe. This is the honest choice for a
  deployed system on dedicated capital.
- **Exclude zeros** if you measure the conditional quality of active days.

This workspace reports **zero-trade-session daily Sharpe** as the primary
metric — zeros included. Pick one, state it, and never switch mid-project.

---

## 7.4 CAGR

```python
def cagr(equity: pd.Series, periods_per_year=252) -> float:
    """Compound annual growth rate from an equity curve."""
    n = len(equity)
    total = equity.iloc[-1] / equity.iloc[0]
    if total <= 0:
        return -1.0
    return total ** (periods_per_year / n) - 1
```

For a futures strategy with no natural "capital", CAGR requires you to **state
the capital base**:

```python
CAPITAL = 100_000
equity = CAPITAL + day_pnl_zero.cumsum()
print(f"CAGR = {cagr(equity):.2%} on ${CAPITAL:,} with {contracts} contract(s)")
```

A CAGR quoted without its capital base and contract count is meaningless — you
can produce any CAGR by changing the denominator. This is the single most
commonly manipulated number in strategy marketing.

Also prefer the **geometric** form above to `mean(daily_return) × 252`, which
ignores compounding drag and overstates by roughly `σ²/2`.

---

## 7.5 Sharpe ratio

```python
def sharpe(returns: pd.Series, rf=0.0, periods_per_year=252) -> float:
    ex = returns - rf / periods_per_year
    sd = ex.std(ddof=1)
    return float(ex.mean() / sd * np.sqrt(periods_per_year)) if sd > 0 else 0.0
```

### The five convention choices that change your Sharpe

1. **P&L or return?** On a futures strategy with no capital base, Sharpe on the
   *daily P&L series* is scale-free and standard. On an equity curve, use
   simple or log returns — state which.
2. **`ddof`.** Use `ddof=1` (sample). With `ddof=0` and small `n`, Sharpe is
   biased up.
3. **Risk-free rate.** For intraday strategies flat overnight, `rf = 0` is
   right — you hold no capital at risk overnight. Say so.
4. **Zero days.** §7.3.
5. **Annualisation factor.** 252 for daily. For a strategy trading a subset of
   days, still use 252 if your series is reindexed over all business days;
   using `len(traded_days)` inflates Sharpe.

### The √T annualisation is wrong under autocorrelation

`√252` assumes i.i.d. returns. With autocorrelation `ρ₁`, the correct factor is
smaller (positive ρ) or larger (negative ρ):

```python
def sharpe_annualised_ac(daily, q=252):
    """Lo (2002) autocorrelation-adjusted annualisation."""
    sr = daily.mean() / daily.std(ddof=1)
    rho = [daily.autocorr(k) for k in range(1, q)]
    adj = q / np.sqrt(q + 2*sum((q-k)*rho[k-1] for k in range(1, q)))
    return sr * adj
```

For daily strategy P&L the correction is usually small. For **monthly**
returns of a strategy with smoothed/illiquid marks it can be enormous — this is
the mechanism behind absurd hedge-fund Sharpes.

**Sanity anchors:** daily Sharpe > 3 on a simple technical strategy with real
costs = you have a bug. Realistic single-strategy intraday futures Sharpes live
in **0.8–1.5**.

---

## 7.6 Sortino ratio

Penalises only downside deviation.

```python
def sortino(returns, target=0.0, periods_per_year=252):
    ex = returns - target
    dn = ex.clip(upper=0.0)
    # Downside deviation: divide by FULL n, not by the count of negatives.
    dd = np.sqrt((dn ** 2).sum() / len(ex))
    return float(ex.mean() / dd * np.sqrt(periods_per_year)) if dd > 0 else np.nan
```

**The trap:** dividing by the number of *negative* observations instead of the
total count. That is a different (and much larger) statistic, and it is the most
common Sortino bug in circulation. Divide by full `n`.

Sortino > Sharpe means positive skew. For a "many small losses, rare big wins"
exit geometry, Sortino flatters — which is *why* you should read it alongside
the exit-geometry diagnostic (lesson 06 C4), not instead of it.

---

## 7.7 Drawdown, Calmar, MAR, Ulcer

```python
def drawdown_series(equity: pd.Series) -> pd.Series:
    return equity / equity.cummax() - 1.0            # fractional

def max_drawdown(equity) -> float:
    return float(drawdown_series(equity).min())

def calmar(equity, periods_per_year=252) -> float:
    """CAGR / |max drawdown|. Convention: over the full sample."""
    mdd = abs(max_drawdown(equity))
    return cagr(equity, periods_per_year) / mdd if mdd > 0 else np.nan
```

**Conventions:**
- **Calmar** classically uses the **trailing 36 months**. Many people use the
  full sample and call it Calmar; that is really **MAR**. State which.
- On a P&L (not equity) series, use **additive** drawdown so it's readable in R:

```python
cum = day_R.cumsum()
dd_R = cum - cum.cummax()
max_dd_R = float(dd_R.min())              # e.g. -4.70R
```

This workspace reports max drawdown **in R**, which is the right unit for
comparing strategies across eras.

### Other drawdown statistics worth reporting

```python
dd = drawdown_series(equity)
underwater_frac = float((dd < 0).mean())          # % of time in drawdown
# longest drawdown (bars from peak to recovery)
peak = equity.cummax()
grp  = (equity >= peak).cumsum()
longest = int(equity.groupby(grp).size().max())
ulcer = float(np.sqrt((dd ** 2).mean()))          # Ulcer index: depth AND duration
```

**Max drawdown is a single order statistic** — it is the most sample-dependent
number you report, with an enormous standard error. Never compare two strategies
on max DD alone; use the Ulcer index or a drawdown *distribution* from a block
bootstrap.

---

## 7.8 The complete summary function

This is the one from `core/metrics.py`, generalised:

```python
def summarize(trades, inst, cost_pts_per_side, all_days=None, label=""):
    """trades: date, side, points (GROSS), atr. Costs = 2 * per-side."""
    if trades.empty:
        return dict(label=label, n_trades=0)
    t = trades.copy()
    rt = 2.0 * cost_pts_per_side
    t["net_pts"] = t.points - rt
    t["R_net"]   = t.net_pts / t.atr
    t["R_gross"] = t.points  / t.atr
    pv = POINT_VALUE[inst]

    day_net = t.groupby("date").net_pts.sum() * pv
    day_R   = t.groupby("date").R_net.sum()
    if all_days is not None:                        # include zero-trade days
        day_net = day_net.reindex(all_days, fill_value=0.0)
        day_R   = day_R.reindex(all_days, fill_value=0.0)

    m, se = day_net.mean(), day_net.std(ddof=1) / np.sqrt(len(day_net))
    cumR  = day_R.cumsum()
    wins, losses = t[t.net_pts > 0], t[t.net_pts <= 0]
    payoff = abs(wins.net_pts.mean() / losses.net_pts.mean()) if len(losses) else np.nan

    return dict(
        label=label, inst=inst, cost_pts=cost_pts_per_side,
        # --- volume / capacity ---
        n_trades=len(t), n_days=t.date.nunique(),
        trades_per_day=len(t) / t.date.nunique(),
        trades_per_year=len(t) / (len(day_net) / 252),
        # --- effect size ---
        gross_pts_per_trade=t.points.mean(),
        net_pts_per_trade=t.net_pts.mean(),
        gross_R=t.R_gross.sum(), net_R=t.R_net.sum(),
        exp_R_per_trade=t.R_net.mean(),
        # --- quality ---
        hit_rate=(t.net_pts > 0).mean(),
        payoff_ratio=payoff,
        break_even_hit=1/(1+payoff) if payoff == payoff else np.nan,
        profit_factor=wins.net_pts.sum() / abs(losses.net_pts.sum()),
        # --- risk-adjusted (day is the risk unit) ---
        day_net_mean_usd=day_net.mean(), day_net_t=m/se if se > 0 else 0.0,
        sharpe_net_daily=day_net.mean()/day_net.std(ddof=1)*np.sqrt(252),
        sortino_net_daily=sortino(day_net),
        max_dd_R=float((cumR - cumR.cummax()).min()),
        calmar_R=(day_R.sum()/(len(day_net)/252)) /
                 abs(float((cumR - cumR.cummax()).min())),
        # --- symmetry ---
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        long_net_pts=t[t.side == 1].net_pts.mean(),
        short_net_pts=t[t.side == -1].net_pts.mean(),
        # --- exit diagnostics ---
        stop_frac=(t.reason == "stop").mean(),
        eod_frac=(t.reason == "eod").mean(),
        mean_hold_min=(t.exit_mfo - t.entry_mfo).mean(),
    )
```

The last block is not decoration. `stop_frac` and `mean_hold_min` are how you
detect that a "better exit" merely tightened the leash: in one rejected variant
here, `stop_frac` went 0.64 → 0.82, mean hold fell, and gross/trade dropped 30%
— the Sharpe gain was variance reduction, not information.

---

## 7.9 Turnover, capacity, exposure

```python
turnover_per_year = trades_per_year * 2                     # sides
time_in_market    = (t.exit_mfo - t.entry_mfo).sum() / (n_days * session_minutes)
notional_per_trade = t.entry_px.mean() * POINT_VALUE[inst] * contracts
adv_participation = contracts / median_daily_volume         # capacity proxy
```

For capacity, the honest question is: **at what size does your fill assumption
break?** If you assume next-open fills at 1 contract, that is fine to hundreds of
contracts on NQ and dishonest at 10,000. State the size at which the claim holds.

---

## 7.10 Era and regime reporting (mandatory)

```python
for lo, hi in [(2011,2015),(2016,2019),(2020,2022),(2023,2026)]:
    m = (day_net.index.year >= lo) & (day_net.index.year <= hi)
    s = day_net[m]
    print(f"{lo}-{hi}: n={len(s):4d} mean=${s.mean():+7.1f} "
          f"Sh={s.mean()/s.std(ddof=1)*np.sqrt(252):+.2f} "
          f"netR={day_R[m].sum():+7.2f}")
```

Report **gross, costs, and net by era** rather than one long-sample
normalisation (Rule 19). A fixed tick cost consumes a smaller fraction of σ as
volatility rises, so net σ-normalised results are mechanically flattered in
high-vol eras even when gross predictability is unchanged.

---

## 7.11 Metric sanity table

| Metric | Plausible for a real intraday futures edge | Suspicious |
|---|---|---|
| Daily Sharpe (net, zeros in) | 0.8 – 1.5 | > 2.5 |
| Expected net R / trade | 0.01 – 0.06 | > 0.2 |
| Hit ratio (trend system) | 0.35 – 0.45 | > 0.6 with payoff > 1 |
| Profit factor | 1.05 – 1.35 | > 2.0 |
| Max DD (R) | 4 – 10 R | < 2R over 15 years |
| Gross/net ratio | 1.1 – 1.6 | > 5 (cost-dominated) |
| Trades/year | 100 – 1000 | 5 (no power) or 100k (no capacity) |

If you land in the "suspicious" column, **go find the bug before you celebrate.**
In this workspace, every single time a metric landed there, there was a bug.

---

## 7.12 What to put in the headline line

One line, everything that matters:

```python
f"{label:<22s} n={n:>5d} ({tpd:.2f}/day) gross={gpt:+.3f}pt net={npt:+.3f}pt "
f"hit={hit:.3f} | day$net={dnm:+.1f} t={t:+.2f} Sh={sh:.2f} | "
f"L={lnp:+.3f}({nl}) S={snp:+.3f}({ns})"
```

Gross **and** net, trade count, the t-stat, Sharpe, and the long/short split — so
a reader can immediately check that the edge is not drift, not cost-dominated,
and not underpowered.

Next: [08 — Statistical properties of returns](08_return_statistics.md)
