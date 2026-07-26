# 13 — Worked example: a complete engine from zero

A minimal but **honest** backtesting stack in ~350 lines: data → features →
engine → metrics → null → verdict. Everything the earlier lessons demand, with
nothing extra.

The strategy is a session-anchored breakout: at each 30-minute decision bar,
enter in the direction of a close beyond a same-time-of-day noise band, provided
price is on the correct side of session VWAP. Exit on a band/VWAP stop, on a
reversal, or at the session close.

Copy this into a project and replace the data loader.

---

## Layout

```
myproject/
  core/
    data.py        # loader + causal features
    engine.py      # the state machine
    metrics.py     # accounting + summary
    nulls.py       # Null C + invariant tests
  scripts/
    run_baseline.py
    run_null.py
  tests/
    test_engine.py
    test_nulls.py
```

---

## `core/data.py`

```python
"""Loader + causal features. Every feature here is strictly one-sided."""
from __future__ import annotations
import numpy as np, pandas as pd
from pathlib import Path

RTH_START, RTH_END = 9*60 + 30, 16*60          # ET minutes
TICK        = {"NQ": 0.25, "ES": 0.25}
POINT_VALUE = {"NQ": 20.0, "ES": 50.0}
MIN_BARS    = 350                               # drop half-days
BAND_MIN_FRAC = 0.9                             # rule 9a


def load(path: str | Path, inst: str) -> pd.DataFrame:
    df = pd.read_parquet(path)
    ts = pd.to_datetime(df["ts_utc"], utc=True)
    et = ts.dt.tz_convert("America/New_York")
    df = df.copy()
    df["et"]  = et.values
    df["tod"] = (et.dt.hour * 60 + et.dt.minute).values
    df = df[(df.tod >= RTH_START) & (df.tod < RTH_END)].copy()
    df["sdate"] = et.dt.normalize().dt.tz_localize(None).values[df.index - df.index[0]] \
                  if False else et[df.index].dt.normalize().dt.tz_localize(None).values
    df["mfo"] = (df.tod - RTH_START).astype(int)      # FIXED anchor, not cumcount
    df = df.sort_values("et").reset_index(drop=True)

    # drop incomplete sessions
    df = df[df.groupby("sdate").et.transform("size") >= MIN_BARS].reset_index(drop=True)

    # cumulative session VWAP (causal: resets each session, includes current bar)
    tp = (df.high + df.low + df.close) / 3.0
    v  = df.volume.astype("float64")
    df["vwap"] = ((tp*v).groupby(df.sdate).cumsum()
                  / v.groupby(df.sdate).cumsum()).to_numpy()

    # causal ATR: prior-14-session mean RTH range, in points. NOTE the shift(1).
    rng = df.groupby("sdate").high.max() - df.groupby("sdate").low.min()
    atr = rng.sort_index().shift(1).rolling(14, min_periods=14).mean()
    df["atr"] = df.sdate.map(atr).to_numpy()

    df["inst"] = inst
    return df[["et","sdate","tod","mfo","open","high","low","close","volume",
               "vwap","atr","inst"]]


def noise_bands(df: pd.DataFrame, lookback: int = 90) -> pd.DataFrame:
    """Same-time-of-day displacement band, anchored at the session open.
    sigma[d,mfo] = mean over the PRIOR `lookback` sessions of |close/open - 1|."""
    opens = df[df.mfo == 0].set_index("sdate")["open"]
    last  = df.sort_values("et").groupby("sdate").tail(1).set_index("sdate")["close"]
    dates = df.sdate.drop_duplicates().sort_values().to_numpy()
    prior_close = last.reindex(dates).shift(1)                     # causal

    cm   = df.pivot_table(index="sdate", columns="mfo", values="close",
                          aggfunc="last").reindex(dates)
    o0   = opens.reindex(dates)
    move = (cm.div(o0, axis=0) - 1.0).abs()

    mp    = int(np.ceil(BAND_MIN_FRAC * lookback))     # rule 9a: fractional min_periods
    sigma = move.shift(1).rolling(lookback, min_periods=mp).mean()   # STRICTLY PRIOR

    long = sigma.stack().rename("sigma").reset_index()
    long.columns = ["sdate","mfo","sigma"]
    long = (long.merge(o0.rename("open0"), on="sdate")
                .merge(prior_close.rename("pclose"), on="sdate")
                .dropna(subset=["open0","pclose","sigma"]))
    hi = np.maximum(long.open0, long.pclose)
    lo = np.minimum(long.open0, long.pclose)
    long["upper"] = hi * (1 + long.sigma)
    long["lower"] = lo * (1 - long.sigma)
    return long[["sdate","mfo","sigma","upper","lower"]]


def decision_mfos(period: int, max_mfo: int) -> list[int]:
    """Decide at mfo = j*period - 1; exposure starts the NEXT bar."""
    return [j*period - 1 for j in range(1, max_mfo // period + 2)
            if j*period - 1 <= max_mfo]


def data_quality(df: pd.DataFrame, bands: pd.DataFrame) -> str:
    """Rule 9a gate. Run this and READ it before interpreting anything."""
    n_sess = df.sdate.nunique()
    out = [f"rows={len(df)} sessions={n_sess} "
           f"{df.sdate.min().date()} -> {df.sdate.max().date()}"]
    per = df.groupby("sdate").size()
    out.append(f"bars/session med={per.median():.0f} min={per.min()} max={per.max()}")
    out.append(f"dup (sdate,mfo)={int(df.duplicated(['sdate','mfo']).sum())} "
               f"ts_monotonic={df.et.is_monotonic_increasing}")
    bad = int(((df.low > df[['open','close']].min(axis=1)) |
               (df.high < df[['open','close']].max(axis=1))).sum())
    out.append(f"OHLC violations={bad}")
    # THE load-bearing check: band coverage by decision slot
    dm = decision_mfos(30, int(df.mfo.max()))
    elig = df[df.mfo.isin(dm)].merge(bands, on=["sdate","mfo"], how="left")
    cov = elig.groupby("mfo").upper.apply(lambda s: s.notna().mean())
    out.append("band coverage by decision slot: "
               f"min={cov.min():.3%} max={cov.max():.3%} spread={cov.max()-cov.min():.3%}")
    if cov.max() - cov.min() > 0.05:
        out.append(f"  !! NON-UNIFORM -> hidden time-of-day filter: {cov.nsmallest(3).to_dict()}")
    return "\n".join(out)
```

---

## `core/engine.py`

```python
"""State machine. Decisions on CLOSE, fills on NEXT OPEN. No exceptions."""
from __future__ import annotations
import numpy as np, pandas as pd


def simulate_session(bars, band, decision_mfos, *,
                     fill_mode="next_open", require_vwap=True,
                     exit_check="every_bar", stop_ref="both") -> list[dict]:
    b = bars.sort_values("mfo").reset_index(drop=True)
    mfo, opn, close, vwap = (b[c].to_numpy() for c in ("mfo","open","close","vwap"))
    atr = float(b.atr.iloc[0]); the_date = b.sdate.iloc[0]
    n = len(b)
    flat_i = n - 1                                  # last RTH bar = the daily flat

    band_map = {int(r.mfo): (r.upper, r.lower) for r in band.itertuples()}
    dset = {int(t) for t in decision_mfos}

    pos, entry_px, entry_mfo, signal_mfo = 0, np.nan, None, None
    trades: list[dict] = []

    def fill(i):
        """The ONLY place a price is assigned. Next open, or nothing."""
        if fill_mode == "signal_close":              # ABLATION ONLY
            return close[i], int(mfo[i])
        return (opn[i+1], int(mfo[i+1])) if i + 1 <= flat_i else (None, None)

    def close_trade(i, reason):
        nonlocal pos, entry_px, entry_mfo, signal_mfo
        px, pmfo = fill(i)
        if px is None:
            return False
        trades.append(dict(date=the_date, side=pos, signal_mfo=signal_mfo,
                           entry_mfo=entry_mfo, exit_mfo=pmfo,
                           entry_px=entry_px, exit_px=px, atr=atr,
                           points=(px - entry_px) * pos, reason=reason))
        pos, entry_px, entry_mfo, signal_mfo = 0, np.nan, None, None
        return True

    for i in range(n):
        if i >= flat_i:
            break
        m, c, w = int(mfo[i]), close[i], vwap[i]
        if m not in band_map:                        # no band -> no decision at all
            continue
        is_dec = m in dset
        up, lo = band_map[m]

        want = 0
        if is_dec:
            if   c > up and (not require_vwap or c > w): want = 1
            elif c < lo and (not require_vwap or c < w): want = -1

        # ---- exits / flips -------------------------------------------------
        if pos != 0:
            base = (max(up, w) if pos == 1 else min(lo, w)) if stop_ref == "both" \
                   else (w if stop_ref == "vwap" else (up if pos == 1 else lo))
            hit  = (c < base) if pos == 1 else (c > base)
            check_here = is_dec or exit_check == "every_bar"
            flip = (want == -pos) and is_dec
            if (hit and check_here) or flip:
                if close_trade(i, "flip" if flip else "stop") and flip:
                    px, pmfo = fill(i)
                    if px is not None:
                        pos, entry_px, entry_mfo, signal_mfo = want, px, pmfo, m
                continue

        # ---- fresh entry ---------------------------------------------------
        if pos == 0 and want != 0 and is_dec:
            px, pmfo = fill(i)
            if px is not None:
                pos, entry_px, entry_mfo, signal_mfo = want, px, pmfo, m

    if pos != 0:                                     # unconditional EOD flat
        trades.append(dict(date=the_date, side=pos, signal_mfo=signal_mfo,
                           entry_mfo=entry_mfo, exit_mfo=int(mfo[flat_i]),
                           entry_px=entry_px, exit_px=close[flat_i], atr=atr,
                           points=(close[flat_i] - entry_px) * pos, reason="eod"))
    return trades


def run(bars, bands, decision_mfos, **kw) -> pd.DataFrame:
    by = {d: g for d, g in bands.groupby("sdate", sort=False)}
    out = []
    for d, g in bars.groupby("sdate", sort=False):
        bd = by.get(d)
        if bd is None or bd.empty:
            continue
        out.extend(simulate_session(g, bd, decision_mfos, **kw))
    return pd.DataFrame(out)
```

---

## `core/metrics.py`

```python
"""Accounting + summary. Day P&L is a SUM. Gross and net both reported."""
from __future__ import annotations
import numpy as np, pandas as pd
from .data import POINT_VALUE


def summarize(trades, inst, cost_pts_per_side, all_days=None, label="") -> dict:
    if trades.empty:
        return dict(label=label, n_trades=0)
    t  = trades.copy()
    rt = 2.0 * cost_pts_per_side                     # round trip, in points
    t["net_pts"] = t.points - rt
    t["R_net"]   = t.net_pts / t.atr
    t["R_gross"] = t.points  / t.atr
    pv = POINT_VALUE[inst]

    day_usd = t.groupby("date").net_pts.sum() * pv   # SUM, never mean (rule 13)
    day_R   = t.groupby("date").R_net.sum()
    if all_days is not None:                         # include zero-trade days
        day_usd = day_usd.reindex(all_days, fill_value=0.0)
        day_R   = day_R.reindex(all_days,  fill_value=0.0)

    sd  = day_usd.std(ddof=1)
    se  = sd / np.sqrt(len(day_usd))
    cum = day_R.cumsum()
    w, l = t[t.net_pts > 0], t[t.net_pts <= 0]
    payoff = abs(w.net_pts.mean() / l.net_pts.mean()) if len(l) and len(w) else np.nan

    return dict(
        label=label, inst=inst, cost_pts=cost_pts_per_side,
        n_trades=len(t), n_days=int(t.date.nunique()),
        trades_per_day=len(t) / t.date.nunique(),
        gross_pts_per_trade=float(t.points.mean()),
        net_pts_per_trade=float(t.net_pts.mean()),
        gross_R=float(t.R_gross.sum()), net_R=float(t.R_net.sum()),
        exp_R_per_trade=float(t.R_net.mean()),
        hit_rate=float((t.net_pts > 0).mean()),
        payoff_ratio=float(payoff),
        break_even_hit=float(1/(1+payoff)) if payoff == payoff else np.nan,
        profit_factor=float(w.net_pts.sum() / abs(l.net_pts.sum())) if len(l) else np.inf,
        day_net_mean_usd=float(day_usd.mean()),
        day_net_t=float(day_usd.mean()/se) if se > 0 else 0.0,
        sharpe_net_daily=float(day_usd.mean()/sd*np.sqrt(252)) if sd > 0 else 0.0,
        max_dd_R=float((cum - cum.cummax()).min()),
        stop_frac=float((t.reason == "stop").mean()),
        eod_frac=float((t.reason == "eod").mean()),
        mean_hold_min=float((t.exit_mfo - t.entry_mfo).mean()),
        n_long=int((t.side == 1).sum()), n_short=int((t.side == -1).sum()),
        long_net_pts=float(t[t.side==1].net_pts.mean()) if (t.side==1).any() else np.nan,
        short_net_pts=float(t[t.side==-1].net_pts.mean()) if (t.side==-1).any() else np.nan,
    )


def fmt(s: dict) -> str:
    if s.get("n_trades", 0) == 0:
        return f"{s.get('label','')}: NO TRADES"
    return (f"{s['label']:<20s} n={s['n_trades']:>5d} ({s['trades_per_day']:.2f}/d) "
            f"gross={s['gross_pts_per_trade']:+.3f}pt net={s['net_pts_per_trade']:+.3f}pt "
            f"hit={s['hit_rate']:.3f}(be {s['break_even_hit']:.3f}) "
            f"netR={s['net_R']:+.1f} | day$={s['day_net_mean_usd']:+.1f} "
            f"t={s['day_net_t']:+.2f} Sh={s['sharpe_net_daily']:.2f} "
            f"mDD={s['max_dd_R']:.2f}R | stop={s['stop_frac']:.2f} "
            f"L={s['long_net_pts']:+.3f}({s['n_long']}) "
            f"S={s['short_net_pts']:+.3f}({s['n_short']})")
```

---

## `core/nulls.py`

```python
"""Path-preserving return shuffle + the invariants that make it trustworthy."""
from __future__ import annotations
import numpy as np, pandas as pd


def null_c_returns(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["sdate","mfo"]).reset_index(drop=True)
    parts = []
    for _, g in d.groupby("sdate", sort=False):
        n = len(g); g = g.copy()
        o, h, l, c = (g[k].to_numpy(float) for k in ("open","high","low","close"))
        dh, dl, dc = h - o, l - o, c - o
        link = np.empty(n); link[0] = 0.0; link[1:] = o[1:] - c[:-1]
        # PIN the artificial opening atom at index 0 (see lesson 10 §10.2)
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]
        o2 = np.empty(n); c2 = np.empty(n); o2[0] = o[0]
        for i in range(n):
            if i > 0:
                o2[i] = c2[i-1] + link[i]
            c2[i] = o2[i] + dc[i]
        g["open"], g["close"], g["high"], g["low"] = o2, c2, o2 + dh, o2 + dl
        g["volume"] = g.volume.to_numpy()[perm]
        tp = (g.high + g.low + g.close) / 3.0
        v  = g.volume.astype("float64").to_numpy()
        g["vwap"] = np.cumsum(tp.to_numpy()*v) / np.cumsum(v)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)


def diffusivity(bars: pd.DataFrame) -> float:
    d = bars.sort_values(["sdate","mfo"])
    return float((d.groupby("sdate").open.shift(-1) - d.close).abs().dropna().median())
```

---

## `tests/test_engine.py`

```python
import numpy as np, pandas as pd, pytest
from core import data as D, engine as E, nulls as N


def test_no_same_bar_fill(trades):
    assert (trades.entry_mfo > trades.signal_mfo).all()

def test_fill_price_within_bar(trades, bars):
    b = bars.set_index(["sdate","mfo"])
    for t in trades.itertuples():
        for mfo, px in ((t.entry_mfo, t.entry_px), (t.exit_mfo, t.exit_px)):
            bar = b.loc[(t.date, mfo)]
            assert bar.low - 1e-9 <= px <= bar.high + 1e-9

def test_no_overlap(trades):
    for _, g in trades.groupby("date"):
        g = g.sort_values("entry_mfo")
        assert (g.entry_mfo.values[1:] >= g.exit_mfo.values[:-1]).all()

def test_flat_at_close(trades, last_mfo):
    assert (trades.exit_mfo <= last_mfo).all()

def test_band_is_causal(bars):
    """Truncating the future must not change any past band value."""
    full = D.noise_bands(bars, 90)
    cut_date = bars.sdate.unique()[len(bars.sdate.unique())//2]
    part = D.noise_bands(bars[bars.sdate < cut_date].copy(), 90)
    j = full.merge(part, on=["sdate","mfo"], suffixes=("_f","_p"))
    np.testing.assert_allclose(j.sigma_f, j.sigma_p, rtol=1e-12)

@pytest.mark.parametrize("seed", range(5))
def test_null_invariants(bars, seed):
    nb = N.null_c_returns(bars, seed)
    # 1. opening anchor pinned
    np.testing.assert_allclose(nb.groupby("sdate").open.first().to_numpy(),
                               bars.groupby("sdate").open.first().to_numpy())
    # 2. session net move preserved
    rn = bars.groupby("sdate").close.last() - bars.groupby("sdate").open.first()
    nn = nb.groupby("sdate").close.last()   - nb.groupby("sdate").open.first()
    np.testing.assert_allclose(rn.to_numpy(), nn.to_numpy(), atol=1e-9)
    # 3. DIFFUSIVITY GATE — the check that makes the null valid for brackets
    assert abs(N.diffusivity(nb)/N.diffusivity(bars) - 1) < 0.05

def test_costs_monotone(trades):
    from core.metrics import summarize
    prev = np.inf
    for c in (0.0, 0.25, 0.5, 1.0):
        v = summarize(trades, "NQ", c)["net_pts_per_trade"]
        assert v < prev; prev = v
```

---

## `scripts/run_baseline.py`

```python
"""python -m myproject.scripts.run_baseline NQ 90"""
import sys, numpy as np, pandas as pd
from core import data as D, engine as E
from core.metrics import summarize, fmt

inst = sys.argv[1] if len(sys.argv) > 1 else "NQ"
lb   = int(sys.argv[2]) if len(sys.argv) > 2 else 90

bars  = D.load(f"data/{inst}_1m_clean.parquet", inst)
bands = D.noise_bands(bars, lb)

print(D.data_quality(bars, bands), "\n")          # RULE 9a — read this first

dm = D.decision_mfos(30, int(bars.mfo.max()))
all_days = pd.Index(sorted(bands.sdate.unique()))
cost = 0.5 * D.TICK[inst]                          # 0.5 tick/side

# --- honest baseline + the fill-artifact ablation -------------------------
tr = E.run(bars, bands, dm, fill_mode="next_open")
print(fmt(summarize(tr, inst, cost, all_days, "next_open")))

ab = E.run(bars, bands, dm, fill_mode="signal_close")
print(fmt(summarize(ab, inst, cost, all_days, "signal_close*")))
print("   * ABLATION ONLY: the gap above IS the fill artifact you would book.\n")

# --- controls -------------------------------------------------------------
nv = E.run(bars, bands, dm, require_vwap=False)
print(fmt(summarize(nv, inst, cost, all_days, "no vwap gate")))

# naive always-long drift control: is the edge just the tape's drift?
first = bars[bars.mfo == 0].set_index("sdate").open
lastc = bars.sort_values("et").groupby("sdate").close.last()
atrs  = bars.groupby("sdate").atr.first()
drift = pd.DataFrame(dict(date=first.index, side=1, signal_mfo=-1, entry_mfo=0,
                          exit_mfo=int(bars.mfo.max()), entry_px=first.values,
                          exit_px=lastc.values, atr=atrs.values,
                          points=(lastc - first).values, reason="eod"))
print(fmt(summarize(drift, inst, cost, all_days, "naive always-long")))

# --- cost ladder ----------------------------------------------------------
print("\ncost ladder (ticks/side):")
for c in (0.0, 0.25, 0.5, 1.0, 2.0):
    s = summarize(tr, inst, c*D.TICK[inst], all_days, f"cost {c}")
    print(f"  {c:>4}  netR={s['net_R']:+7.1f}  Sh={s['sharpe_net_daily']:+.2f}  "
          f"net/trade={s['net_pts_per_trade']:+.3f}pt")

# --- era split ------------------------------------------------------------
print("\nby era:")
tr["yr"] = pd.to_datetime(tr.date).dt.year
for lo, hi in [(2011,2015),(2016,2019),(2020,2022),(2023,2026)]:
    e = tr[(tr.yr >= lo) & (tr.yr <= hi)]
    if len(e):
        print("  " + fmt(summarize(e, inst, cost, label=f"{lo}-{hi}")))
```

---

## `scripts/run_null.py`

```python
"""python -m myproject.scripts.run_null NQ 30
Gate: only run this if the real pass CLEARED its primary metric."""
import sys, numpy as np, pandas as pd
from core import data as D, engine as E, nulls as N
from core.metrics import summarize

inst   = sys.argv[1] if len(sys.argv) > 1 else "NQ"
ndraws = int(sys.argv[2]) if len(sys.argv) > 2 else 30

bars  = D.load(f"data/{inst}_1m_clean.parquet", inst)
dm    = D.decision_mfos(30, int(bars.mfo.max()))
cost  = 0.5 * D.TICK[inst]

def metric(b):
    bd = D.noise_bands(b, 90)                       # REBUILD features on this tape
    days = pd.Index(sorted(bd.sdate.unique()))
    tr = E.run(b, bd, dm)
    return summarize(tr, inst, cost, days)["net_R"] if len(tr) else 0.0

real = metric(bars)
print(f"real netR = {real:+.2f}\nrunning {ndraws} null draws...")

nulls = []
for s in range(ndraws):
    nb = N.null_c_returns(bars, seed=s)
    assert abs(N.diffusivity(nb)/N.diffusivity(bars) - 1) < 0.05, "diffusivity gate FAILED"
    v = metric(nb); nulls.append(v)
    print(f"  seed {s:>3d}: {v:+.2f}")

nulls = np.array(nulls)
z = (real - nulls.mean()) / nulls.std(ddof=1)
p = ((nulls >= real).sum() + 1) / (len(nulls) + 1)      # +1: never report p=0
cap = max(0.0, nulls.mean()) / real if real > 0 else np.nan

print(f"\nnull mean={nulls.mean():+.2f} sd={nulls.std(ddof=1):.2f}")
print(f"z={z:+.2f}  p={p:.4f}  null_center={'POSITIVE' if nulls.mean()>0 else 'NEGATIVE'}")
print(f"null capture = {cap:.1%} of real")
print("VERDICT:", "PASS" if (p < 0.05 and z >= 2) else "FAIL")
if nulls.mean() > 0:
    print("  WARNING: null centers POSITIVE -> check for variance amplification.")
```

---

## The order to run things

```powershell
pytest tests/ -q                                          # 1. invariants FIRST
python -m myproject.scripts.run_baseline NQ 90             # 2. honest baseline + ablation
#    read the data-quality block
#    read next_open vs signal_close (the fill artifact)
#    read gross vs net, and the naive always-long control
#    read the cost ladder and the era split
python -m myproject.scripts.run_null NQ 30                 # 3. ONLY if step 2 cleared
```

---

## How to read the output

```
next_open       n= 4209 (1.16/d) gross=+3.509pt net=+3.259pt hit=0.381(be 0.362)
                netR=+91.2 | day$=+30.1 t=+3.15 Sh=1.29 mDD=-4.70R | stop=0.64
                L=+4.102(2210) S=+2.334(1999)
signal_close*   n= 4209 (1.16/d) gross=+5.881pt ...  Sh=2.14
```

**The `signal_close` line is the most important one on the page.** Sharpe 1.29
→ 2.14 means 40% of the apparent performance would have been an artifact if you
had filled on the signal bar. That is the size of the trap you avoided.

Then, in order:
1. **Gross vs net** — 3.509 vs 3.259 means cost is 7% of gross. Robust.
   If they were 0.30 vs 0.05, the result would be cost-model-dependent.
2. **Hit vs break-even** — 0.381 vs 0.362 is a real 1.9pp edge over the
   bracket's algebraic break-even.
3. **Naive always-long** — if it prints Sharpe 1.2, your strategy has found
   drift, not timing.
4. **Long/short split** — +4.10 vs +2.33 is a drift tilt but both sides are
   positive, so it is not *purely* drift.
5. **Cost ladder** — must survive 1 tick/side.
6. **Era split** — must not live in one era.
7. **Null** — `z ≥ 2`, `p < 0.05`, and **check the center's sign**.

---

## What to add next, in order

1. **A `signal_mfo` column and the fill-feasibility assertion** running on every
   run (lesson 06).
2. **Costs as a config object**, not a scalar — spread, commission, slippage
   separately, so you can stress each.
3. **The numba kernel** (lesson 03) once the engine is stable — with a
   trade-level parity test against this pandas version.
4. **A sibling instrument** (ES) run through the identical code path, as your
   standing mechanism test.
5. **The ledger and hypothesis files** (lesson 12) — before your third
   experiment, not after your thirtieth.

Next: [14 — Reference card](14_reference_card.md)
