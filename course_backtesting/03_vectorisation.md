# 03 — Vectorisation and computational efficiency

The governing pattern, proven in `futures/nq/noise_vwap/core/engine2_nb.py`
(**16.8× speedup at bit-exact parity**):

> **Vectorise everything that is not bar-sequential. Compile the part that is.**

Feature construction, band lookup, masks, gates, and metrics are all
order-independent → pure numpy/pandas. The position state machine is inherently
sequential (each bar's action depends on the running position) → one `@njit`
kernel over flat arrays, called **once** for the entire backtest.

Do not try to vectorise the state machine. People who do end up with
`np.where` chains that silently break path dependence.

---

## 3.1 The cost model you need in your head

| Operation | Relative cost per element |
|---|---|
| numpy ufunc on float64 array | 1 |
| pandas Series ufunc | ~1.5 |
| `groupby(...).transform(vectorised)` | ~3 |
| `.rolling(n).mean()` | ~3 (it's C, and O(n) not O(n·w)) |
| `.rolling(n).apply(f, raw=True)` | ~200 |
| `.apply(f, axis=1)` | ~2000 |
| `for i, row in df.iterrows()` | ~10000 |
| numba `@njit` scalar loop | ~1.2 |

`iterrows()` and `.apply(axis=1)` should never appear in a backtest. Ever.
`.rolling().apply()` is acceptable exactly once, in a one-off diagnostic.

---

## 3.2 Rule one: never loop over rows in Python

```python
# BAD — 8 minutes on 5M bars
signals = []
for i, row in df.iterrows():
    if row.close > row.upper and row.close > row.vwap:
        signals.append(1)
    elif row.close < row.lower and row.close < row.vwap:
        signals.append(-1)
    else:
        signals.append(0)

# GOOD — 40 ms
long_ok  = (df.close > df.upper) & (df.close > df.vwap)
short_ok = (df.close < df.lower) & (df.close < df.vwap)
df["signal"] = np.select([long_ok, short_ok], [1, -1], default=0)
```

`np.select` / `np.where` are your branch replacements. Keep the conditions as
named boolean Series — they are self-documenting and reusable as diagnostics
(`long_ok.sum()` tells you signal counts for free).

---

## 3.3 Rule two: `groupby` with a vectorised function, not a lambda over rows

```python
# BAD: python function per group
df["cum_v"] = df.groupby("sdate").volume.apply(lambda s: s.cumsum())

# GOOD: pandas' native grouped cumulative
df["cum_v"] = df.groupby("sdate", sort=False).volume.cumsum()
```

Native grouped ops (`cumsum, cummax, cumcount, shift, diff, rank, transform`)
run in C. `sort=False` matters on large frames — it skips a sort of the group
keys when your data is already ordered.

The tell for a bad groupby: if the lambda takes a Series and returns a Series
of the same length, there is almost always a native equivalent.

---

## 3.4 Rule three: reshape to a matrix for cross-sectional-in-time features

This is the highest-leverage trick for intraday work. "Rolling over the same
minute-of-day across days" is awkward as a groupby and trivial as a matrix.

```python
# sessions (rows) x minute-of-open (cols)
cm = df.pivot_table(index="sdate", columns="mfo", values="close", aggfunc="last")

move  = (cm.div(cm[0], axis=0) - 1.0).abs()      # displacement from the open
sigma = move.shift(1).rolling(90, min_periods=81).mean()   # ONE call, all 390 slots

# back to long form for the engine
long = sigma.stack().rename("sigma").reset_index()
long.columns = ["sdate", "mfo", "sigma"]
```

One `.rolling()` on a `(4000 × 390)` frame replaces 390 separate rolling
computations. `.shift(1)` shifts along the **session** axis, giving causality.

The same shape is what you want for:
- intraday seasonality profiles,
- cross-sectional ranks across an instrument universe (rows=date, cols=symbol),
- event-study matrices (rows=event, cols=relative bar).

---

## 3.5 Rule four: build lookups as arrays or dicts, not repeated `.loc`

```python
# BAD — O(log n) hash/index lookup per bar, in Python
for i in range(n):
    up = band.loc[(date, mfo[i]), "upper"]

# GOOD — one dict build, O(1) scalar lookups
band_map = {int(r.mfo): (r.upper, r.lower) for r in band.itertuples()}

# BEST — merge once, work with numpy arrays
merged = bars.merge(band, on=["sdate", "mfo"], how="left")
up = merged.upper.to_numpy()
lo = merged.lower.to_numpy()
```

`.itertuples()` is ~10× faster than `.iterrows()` when you genuinely need row
iteration (namedtuples, no Series construction per row).

**Always call `.to_numpy()` before a sequential loop.** Indexing a pandas Series
in a loop pays the index-lookup and boxing cost every access; indexing a numpy
array does not. This alone is often a 20–50× difference.

---

## 3.6 Fast causal percentile rank (worked example)

The naive version from lesson 02:

```python
s.rolling(w, min_periods=w//2).apply(lambda x: (x[:-1] < x[-1]).mean(), raw=True)
```

is O(n·w) *in Python*. For `n=5e6, w=252` it will not finish. The compiled
version:

```python
from numba import njit

@njit(cache=True)
def rolling_rank(x, w):
    n = x.shape[0]
    out = np.full(n, np.nan)
    for i in range(w, n):
        c = 0; m = 0
        for j in range(i - w, i):          # strictly prior window
            v = x[j]
            if v == v:                      # not NaN
                m += 1
                if v < x[i]:
                    c += 1
        if m > 0:
            out[i] = c / m
    return out
```

Still O(n·w) but at native speed — 5M × 252 runs in a few seconds. If you need
better, use a sorted-container/Fenwick tree for O(n log w); usually you don't.

---

## 3.7 The compiled state machine

Here is the actual pattern from `core/engine2_nb.py`. Sessions are laid out
contiguously and walked via an `offsets` index, so there is **one**
Python→native call for the whole backtest, not one per day.

```python
import numpy as np, pandas as pd
from numba import njit

@njit(cache=True)
def _sim_all(offsets, flat_rel, atr_s, last_close_s,
             mfo, opn, close, vwap, is_decision, allow, ff_up, ff_lo,
             fill_mode, exit_check,
             o_sess, o_side, o_emfo, o_xmfo, o_epx, o_xpx, o_pts, o_reason):
    """One native call for the whole backtest. Returns trade count."""
    nsess = offsets.shape[0] - 1
    nt = 0
    for s in range(nsess):
        start, end = offsets[s], offsets[s + 1]
        frel = flat_rel[s]                       # local index of the forced flat
        pos = 0; entry_px = np.nan; entry_i = -1
        for j in range(end - start):
            if j >= frel:
                break
            i = start + j
            # ... entry / stop / flip logic on scalars ...
        # ... eod flat ...
    return nt


def run(bars, bands, decision_mfos, **kw) -> pd.DataFrame:
    # ---------- vectorised preprocessing (pandas) ----------
    b = bars.sort_values(["sdate", "mfo"]).reset_index(drop=True)
    b = b.merge(bands[["sdate","mfo","upper","lower"]], on=["sdate","mfo"], how="left")
    # forward-fill the band WITHIN each session (band is a step function of mfo)
    b[["ff_up","ff_lo"]] = b.groupby("sdate")[["upper","lower"]].ffill()
    b["is_decision"] = b.mfo.isin(decision_mfos).to_numpy()

    # session offsets: where each session starts in the flat arrays
    codes = b.sdate.factorize(sort=False)[0]
    starts = np.flatnonzero(np.r_[True, codes[1:] != codes[:-1]])
    offsets = np.r_[starts, len(b)].astype(np.int64)

    # ---------- one compiled call ----------
    cap = len(b)                                    # upper bound on trades
    o_side = np.empty(cap, np.int8); o_pts = np.empty(cap, np.float64)
    # ... allocate the rest ...
    nt = _sim_all(offsets, ..., o_side, ..., o_pts, ...)

    # ---------- vectorised post-processing ----------
    return pd.DataFrame({"side": o_side[:nt], "points": o_pts[:nt], ...})
```

Key design points:

- **Pre-allocate output arrays** at an upper bound (`cap`), fill, then slice
  `[:nt]`. Appending inside `@njit` requires typed lists and is much slower.
- **No strings in the kernel.** Map `"next_open"→0, "signal_close"→1` before the
  call; numba string comparison in a hot loop is slow and fragile.
- **`cache=True`** persists the compiled kernel to disk so you pay the ~2 s
  compile once, not on every script run.
- **No pandas objects cross the boundary.** Only `np.ndarray` of `float64`,
  `int64`, `int8`, `bool_`.
- **Forward-fill the band before the kernel.** That's vectorisable work; doing
  it inside the loop wastes the compilation.

---

## 3.8 Parity testing: the non-negotiable part

A fast engine you cannot trust is worthless. The rule from this workspace:

> **Parity must be trade-level (`assert_frame_equal`), never aggregate.**

Two engines can produce identical total P&L from completely different trades.
Aggregate parity is not parity.

```python
def test_parity():
    from core import engine2, engine2_nb
    bars, bands = load_fixture()
    for cfg in ALL_CONFIGS:                      # 27 configs in this workspace
        a = engine2.run(bars, bands, **cfg).sort_values(["date","entry_mfo"])
        b = engine2_nb.run(bars, bands, **cfg).sort_values(["date","entry_mfo"])
        pd.testing.assert_frame_equal(
            a.reset_index(drop=True), b.reset_index(drop=True),
            check_dtype=False, atol=1e-9,
        )
```

Sweep the **whole knob space**, not the default config. Every overlay you add
(`tp_atr`, `trail_step_atr`, `entry_gate`, `flat_before_close`, …) must be in
the parity matrix, including the off-by-default value, because:

> **Every new overlay must be default-off and prove bit-exact parity with the
> prior baseline.** Otherwise you cannot tell whether a later delta came from
> your idea or from an accidental change to the baseline.

This workspace enforces that on every single engine feature. It has caught
regressions repeatedly.

---

## 3.9 Memory

```python
# read only what you need
df = pd.read_parquet(path, columns=["ts_utc","open","high","low","close","volume"])

# downcast: 60M rows x float64 = 3.8 GB -> float32 = 1.9 GB
for c in ["open","high","low","close"]:
    df[c] = df[c].astype("float32")
```

**Caution on float32 for prices.** NQ at 25000.00 with 0.25 ticks needs ~7
significant digits; float32 has ~7.2. You are at the edge. Use float32 for
*volumes and returns*, keep **prices in float64**. A parity test comparing a
float32 and float64 engine will show you exactly where it bites.

For a 68M-row 1-second archive (as used in `EXP-0009` here), read it
**per-session** with a pyarrow row-group filter rather than loading the lot:

```python
import pyarrow.parquet as pq
pf = pq.ParquetFile(path)
for batch in pf.iter_batches(batch_size=2_000_000, columns=cols):
    process(batch.to_pandas())
```

---

## 3.10 Parameter sweeps: parallelise across configs, not inside

```python
from concurrent.futures import ProcessPoolExecutor
import functools

def one_cell(cfg, bars, bands):
    tr = engine.run(bars, bands, **cfg)
    return {**cfg, **summarize(tr)}

with ProcessPoolExecutor(max_workers=8) as ex:
    rows = list(ex.map(functools.partial(one_cell, bars=bars, bands=bands), grid))
sweep = pd.DataFrame(rows)
```

Notes:
- Load the data **once** in the parent, pass it in; each worker pickling a 3 GB
  frame will be slower than serial.
- On Windows (`spawn`), everything must be at module top level and picklable.
- The engine kernel already releases nothing (numba `nopython` holds the GIL for
  `cache=True` kernels unless `nogil=True`), so **processes**, not threads.
- Numba compiles once per process — with 8 workers you pay compilation 8×. For
  small sweeps that dominates; measure before parallelising.

---

## 3.11 Benchmark honestly

```python
import time, contextlib

@contextlib.contextmanager
def timed(label):
    t0 = time.perf_counter()
    yield
    print(f"{label}: {time.perf_counter()-t0:.2f}s")

with timed("warm"):    engine_nb.run(bars, bands, **cfg)   # discard: compilation
with timed("engine"):  engine_nb.run(bars, bands, **cfg)   # this is the number
```

Always discard the first numba call. Reporting a 2.1 s "runtime" that is 2.0 s
of compilation is how people conclude numba is slow.

---

## 3.12 What NOT to optimise

Profile before you touch anything:

```python
python -m cProfile -s cumtime -m myproject.scripts.run_baseline | head -30
```

In practice, for a typical intraday backtest:
- ~60% is **parquet I/O + the initial timezone conversion** → cache the
  processed frame to a parquet in a scratch dir and reload it.
- ~25% is **feature construction** → vectorise as above.
- ~10% is the **engine** → this is what numba fixes.
- ~5% is metrics.

Optimising a 10% component by 17× saves you 9% of runtime. Cache the data load
first.

---

## Checklist

- [ ] No `iterrows` / `.apply(axis=1)` / `.rolling().apply()` in production code.
- [ ] `.to_numpy()` before any sequential loop.
- [ ] Cross-day, same-slot features done via `pivot_table` + one `.rolling()`.
- [ ] The sequential state machine is the *only* loop, and it is compiled.
- [ ] `cache=True` on njit kernels; strings mapped to ints outside the kernel.
- [ ] Output arrays pre-allocated and sliced, not appended.
- [ ] Trade-level `assert_frame_equal` parity across the full knob matrix.
- [ ] Every new overlay is default-off and proves parity with the prior
      baseline.
- [ ] Prices float64; benchmark discards the compile call.

Next: [04 — Exploratory analysis](04_exploratory_analysis.md)
