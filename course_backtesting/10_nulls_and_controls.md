# 10 — Null models and negative controls

The single most valuable technique in this entire course:

> **Re-run the identical pipeline on data where the thing you claim to predict
> has been destroyed. A real strategy prints ≈0. A machinery artifact prints
> the same as the real tape.**

This has caught, in this workspace: an 80%-fake edge that had passed era
stability, DSR = 1.000 and a frozen OOS holdout; a +0.27R / t = 31 result built
from pure noise; and roughly eight separate "improvements" that were variance
amplifiers.

---

## 10.1 The rules a null must satisfy (Rule 17)

1. **Same pipeline.** Same feature construction, signal logic, execution, state
   transitions, costs, parameter search, and selection rule. Not the trade list
   — the **pipeline**, from raw bars forward.
2. **State precisely what it preserves and what it destroys.**
3. **Verify those claims with executable invariant tests.** A null you have not
   tested is a random number generator with a story attached.
4. **Use repeated draws**, and compare against the null *distribution*. Never
   subtract one null result.
5. **Reproduce the full candidate search** and use the distribution of the
   *selected/maximum* statistic, when selection occurred.
6. **Investigate unexpected null P&L** rather than dismissing it as machinery
   bias.

A valid null need **not** have zero gross P&L. Drift, carry, directional
exposure, or payoff features that the null deliberately preserves can legitimately
have value. **Interpret only the information the null destroyed.**

---

## 10.2 Null C — the path-preserving return shuffle

The workhorse for intraday strategies. Preserves each bar's internal geometry
and the session's net move; destroys the *order* of moves.

```python
def null_c_returns(bars: pd.DataFrame, seed: int) -> pd.DataFrame:
    """Per session: keep each bar's shape (h-o, l-o, c-o) and the inter-bar link
    (open[t] - close[t-1]) as ATOMS. Pin the opening atom, permute the rest,
    rebuild the path from the session's true first open."""
    rng = np.random.default_rng(seed)
    d = bars.sort_values(["date", "tod"]).reset_index(drop=True)
    parts = []
    for _, g in d.groupby("date", sort=False):
        n = len(g); g = g.copy()
        o, h, l, c = (g[k].to_numpy(float) for k in ("open","high","low","close"))
        dh, dl, dc = h - o, l - o, c - o
        link = np.empty(n); link[0] = 0.0; link[1:] = o[1:] - c[:-1]

        # link[0] is an ARTIFICIAL anchor, not an observed inter-bar link.
        # It must stay at index 0: if shuffled, reconstruction re-anchors the
        # first open and silently DROPS whichever real link lands there.
        perm = np.concatenate(([0], rng.permutation(np.arange(1, n))))
        dh, dl, dc, link = dh[perm], dl[perm], dc[perm], link[perm]

        o2 = np.empty(n); c2 = np.empty(n); o2[0] = o[0]
        for i in range(n):
            if i > 0:
                o2[i] = c2[i-1] + link[i]
            c2[i] = o2[i] + dc[i]
        g["open"], g["close"] = o2, c2
        g["high"], g["low"] = o2 + dh, o2 + dl
        g["volume"] = g["volume"].to_numpy()[perm]
        # rebuild cumulative VWAP on the shuffled path
        tp = (g.high + g.low + g.close) / 3.0
        v = g.volume.astype("float64").to_numpy()
        g["vwap"] = np.cumsum(tp.to_numpy()*v) / np.cumsum(v)
        g["bar_i"] = np.arange(n)
        parts.append(g)
    return pd.concat(parts, ignore_index=True)
```

**Preserves:** bar geometry, return distribution and fat tails, volumes, and
the session **net move** (a sum is permutation-invariant).
**Destroys:** the order of moves after the opening bar → intraday
autocorrelation, mean reversion, volatility clustering, seasonality.

So: everything the strategy *predicts* (intraday continuation) is destroyed; the
drift it might merely *ride* is preserved. A real timing edge must beat this;
the excess over the null is the machinery-manufactured P&L.

### The pinned-sentinel bug (learn this one)

`link[0] = 0` is a fabricated anchor, not a real inter-bar link. If you include
it in the permutation and then re-anchor the first open, you **discard whichever
real link lands at index 0**, and the reconstructed session net move changes.

This was a live defect in this workspace. The fix — pin the complete opening
atom — plus multi-seed invariant tests is now standard. Reference
implementations: `futures/nq/noise_vwap/core/nulls.py::null_c_returns` and
`futures/vwap_mean_version/core/nulls.py::null_c_returns`.

---

## 10.3 Validating the null (this step is not optional)

```python
def diffusivity(bars):
    """Median |next_open - this_close| across within-session bar steps."""
    d = bars.sort_values(["date","tod"])
    return float((d.groupby("date").open.shift(-1) - d.close).abs().dropna().median())

def test_null_invariants(real, seeds=range(5)):
    for s in seeds:
        null = null_c_returns(real, s)
        # 1. opening anchor pinned
        assert (null.groupby("date").open.first().to_numpy()
                == real.groupby("date").open.first().to_numpy()).all()
        # 2. session NET MOVE preserved
        rn = real.groupby("date").close.last() - real.groupby("date").open.first()
        nn = null.groupby("date").close.last() - null.groupby("date").open.first()
        np.testing.assert_allclose(rn.to_numpy(), nn.to_numpy(), atol=1e-9)
        # 3. complete ATOM MULTISET preserved (nothing dropped or duplicated)
        for d, g in real.groupby("date"):
            gn = null[null.date == d]
            np.testing.assert_allclose(np.sort((g.high-g.open).to_numpy()),
                                       np.sort((gn.high-gn.open).to_numpy()), atol=1e-9)
        # 4. DIFFUSIVITY GATE: path continuity statistic matches
        assert abs(diffusivity(null)/diffusivity(real) - 1) < 0.05
        # 5. volume distribution and calendar preserved
        assert null.groupby("date").volume.sum().equals(real.groupby("date").volume.sum())
```

### Why the diffusivity gate exists

**A raw bar shuffle is INVALID for any barrier/bracket strategy.** Reordering
whole bars makes price **teleport** between bars — the gap from one bar's close
to the next bar's open becomes huge. Nearby take-profits then get hit for free.

Measured here: an invalid raw-bar null printed **+0.27R at t = 31 on a strategy
built from pure noise.** It "proved" a fake edge was real by making the null
implausibly bad.

The diffusivity gate — median `|next_open − this_close|` must match the real
tape — catches this immediately.

Raw bar shuffling is acceptable **only** when the resulting path geometry is
irrelevant to the estimand: signal-only or forward-return studies with no
barrier or execution-path dependence.

### The opposite failure: destroying what the strategy is defined against

Randomise what the strategy **predicts**; preserve what it is **defined
against**. A whole-session shuffle in this workspace scrambled the *opening
range* the strategy was defined against, and nearly produced a false "your edge
is machinery" verdict — the null was testing a different strategy.

Ask, for each null: *"After this transformation, does the strategy's reference
level still mean the same thing?"* If not, the null is invalid in the other
direction.

---

## 10.4 The null catalogue

### Null A — matched-count random signal drop
**Target:** the rarity-filter hypothesis. **Cheap** (no engine re-run needed if
the filter is a pure drop; re-run if it's stateful).

```python
def matched_count_null(all_signals, n_keep, n_draws=200, seed=0):
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_draws):
        keep = set(map(tuple, rng.choice(all_signals, n_keep, replace=False)))
        out.append(metric(engine.run(bars, bands, entry_gate=keep)))
    return np.array(out)
```

**Read:** if random dropping of the same number of signals does as well as your
filter, the filter is rarity, not information.

### Null B — random sign / random entry
**Target:** whether *any* directional information exists. Weak on its own, and
beware Rule 16: multiplying realised P&L by a random sign **never retests the
fill**. It must re-run the engine with random entry directions.

### Null C — path-preserving return shuffle (§10.2)
**Target:** intraday timing/continuation information. The primary null for
intraday strategies.

### Null D — cross-instrument re-pairing
**Target:** contemporaneous cross-market information.

```python
def repair_null(a_bars, b_bars, n_draws=200, seed=0):
    """Pair instrument A's session d with instrument B's session from a DIFFERENT
    date, matched on era/calendar/regime. Destroys contemporaneous cross-info,
    preserves each leg's own dynamics."""
    rng = np.random.default_rng(seed)
    out = []
    for i in range(n_draws):
        donor = {d: rng.choice(eligible_donors(d)) for d in a_bars.date.unique()}
        out.append(metric(run_paired(a_bars, remap(b_bars, donor))))
    return np.array(out)
```

**Match or stratify donors** by era, calendar, contract and regime — otherwise
your null is testing unrelated structural changes, not the cross-information.

### Null E — sibling market (the mechanism test)
Not a randomisation but the cheapest and most decisive control. If your stated
mechanism is structural (pan-index, macro, session-driven), it makes a
falsifiable prediction about the sibling. **Run it.**

### Null F — time-shift / lag null
Shift the feature by `k` days relative to prices. Preserves the feature's own
distribution and autocorrelation, destroys its alignment with prices. Good for
cross-source (macro/sentiment/alt-data) claims.

### Null G — the adverse-execution control
Re-run with deliberately pessimistic fills (one tick worse, next-next-open,
adverse intrabar resolution). Not a statistical null but the fastest way to see
whether your result is execution-fragile.

### Null H — neighbouring parameters
If `lookback=90` works and `85` and `95` do not, you have found a spike in a
noise surface. A real effect has a **plateau**. Always report the neighbourhood.

---

## 10.5 How to read a null result — the decision table

Let `real` be your uplift and `null` the distribution of the same statistic
across draws.

| Pattern | Interpretation |
|---|---|
| `real` far above null, null centered **≈ 0** | Real information. The strongest result available. |
| `real` above null, null centered **negative** | Real, and specifically tied to what you cut — noise does *worse*. The cleanest signature. |
| `real` above null, null centered **positive** | **Variance amplification.** Your "improvement" helps noise too. Machinery, not alpha. |
| `real` **inside** the null band | No evidence. A post-hoc screen on consumed history. |
| `real` **below** the null center | Anti-selection — you are systematically removing the good trades. |

### The null's CENTER is the discriminator, not just its tail

This is the highest-value reading skill in the course, and it is under-taught
everywhere.

- **Null centers positive** → "fewer trades → higher Sharpe" machinery. Killed
  the VWAP-touch exit, the narrow exit band, the RR ladder, and the
  vol-conditional exit cadence here.
- **Null centers negative** → the effect is genuinely tied to the specific thing
  being cut. The early-flat cutoff passed on exactly this signature (real
  +0.101, null mean −0.048, p = 0.032, 0/30 draws beat real).
- **Null centers ≈ 0** on a filter → the filter is not pure rarity, and the
  uplift (if any) is real cross-information.

Worked example from this workspace: a `disagree` cross-market filter lifted
Sharpe 0.49 → 0.67. Its re-pairing null centered at ~0 — so it was **not** a
rarity filter, dropping a random 13% of trades did not reproduce it. But the
uplift was `z = 1.53, p ≈ 0.073` and was the **max over ~6 post-hoc configs on
consumed history**. Verdict: a **qualified screen** needing a future holdout, not
a validated edge. Both halves of that reading matter.

---

## 10.6 Paired draws

Always pair. Run the real and null configurations on the **same** shuffled tape,
so the difference isolates your change:

```python
real_uplift = metric(treatment(real_bars)) - metric(baseline(real_bars))
null_uplifts = []
for s in range(30):
    nb = null_c_returns(real_bars, seed=s)
    nbands = build_bands(nb)                    # REBUILD features on the null tape
    null_uplifts.append(metric(treatment(nb, nbands)) - metric(baseline(nb, nbands)))

z = (real_uplift - np.mean(null_uplifts)) / np.std(null_uplifts, ddof=1)
p = (np.sum(np.array(null_uplifts) >= real_uplift) + 1) / (len(null_uplifts) + 1)
```

**Rebuilding the features on the null tape is mandatory.** If you shuffle prices
but keep the real bands, you have tested nothing — the strategy is now trading
noise against a real reference level, which is a different (and meaningless)
experiment.

---

## 10.7 Nulls under selection

If you searched a family and are reporting the best cell, the null must
**reproduce the entire search**:

```python
real_best = max(metric(cfg) for cfg in grid)               # family-max on real data
null_bests = []
for s in range(30):
    nb = null_c_returns(real_bars, s)
    nbands = build_bands(nb)
    null_bests.append(max(metric(cfg, nb, nbands) for cfg in grid))  # SAME search
p = (np.sum(np.array(null_bests) >= real_best) + 1) / 31
```

Comparing a family-max against a single-cell null distribution is a
free significance boost of roughly `√(2·ln N)` standard deviations. With 42
cells that is ~2.7σ — enough to make any null look beaten.

---

## 10.8 Controls that are NOT valid (Rule 16)

| Fake control | Why it proves nothing |
|---|---|
| Mirrored long/short P&L on the same fills | May sum to zero **by identity** |
| Realised P&L × random sign | Never retests the fill |
| Filtering a completed trade list | The engine **state** is what your filter changes |
| A different random seed | Not a null, just a different sample |
| "It also works on SPY" (correlated proxy) | Not independent evidence |
| DSR / bootstrap / OOS holdout | Address selection & uncertainty only |

**Any control that changes what the strategy DOES must re-run the machinery.**

---

## 10.9 The standing efficiency rule

> **Gate the expensive null on the success metric.** If the real/descriptive
> pass does not first clear the primary metric (Sharpe uplift **and** net-R
> gate), it is already a REJECT. Spend no Null-C draws.

A failing real pass is a rejection. A null run on a rejection tells you nothing
you did not already know, and 30 full-pipeline draws with feature rebuilds is
often an hour of compute.

---

## 10.10 The null implementation checklist

- [ ] The null re-runs the **complete pipeline**, including feature rebuild.
- [ ] What it preserves and destroys is written down explicitly.
- [ ] Invariant tests: opening anchor, net move, atom multiset, **diffusivity**,
      volumes, calendar, pairing — passing across multiple seeds.
- [ ] Path-preserving **return** shuffle, not a raw bar shuffle, for anything
      with barrier/path dependence.
- [ ] The strategy's reference level still means the same thing after the
      transformation.
- [ ] Draws are **paired** with the real configuration.
- [ ] If a search occurred, the null reproduces the search and uses the
      family-max distribution.
- [ ] The null's **center** is reported and interpreted, not only its tail.
- [ ] Unexpected null P&L is investigated, not waved away.
- [ ] `p = (k+1)/(n+1)`, never `p = 0`.

Next: [11 — Testing a strategy variation](11_variation_testing.md)
