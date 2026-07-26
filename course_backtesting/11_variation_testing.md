# 11 — Testing a strategy variation: is it better, or is it noise?

This is the most common thing you will do, and the easiest to get wrong. This
lesson is a procedure, in order. Follow it literally.

---

## The procedure

```
0. Freeze the baseline
1. Write the hypothesis file (BEFORE running)
2. Implement as a default-off overlay; prove bit-exact parity
3. Run on a COMMON sample
4. Read the diagnostic panel (not just Sharpe)
5. Apply the real gate  ── FAIL → REJECT, stop. Do not spend the null.
6. Apply the discriminating controls
7. Run the null (paired, family-reproducing)
8. Run the sibling market (the mechanism test)
9. Write the verdict — including NO-GO — into the run artifact
```

---

## Step 0 — Freeze the baseline

Every delta is meaningless without a fixed reference. The baseline config must
be a **committed file with a hash**, not "whatever the script does today".

```json
{ "instrument":"NQ", "session":"RTH", "lookback":90, "decision_period":30,
  "require_vwap":true, "exit_check":"every_bar", "stop_ref":"both",
  "fill_mode":"next_open", "cost_pts_per_side":0.125 }
```

**The baseline never improves.** If a variant is adopted, you create a *new*
frozen baseline with a new ID and record the transition. A baseline that drifts
upward with each accepted change makes every historical delta uncomparable.

---

## Step 1 — Write the hypothesis file first

Non-negotiable (Rule 24). Template:

```markdown
# HYP-00XX — <one-sentence testable claim>

- Status: proposed
- Created: YYYY-MM-DD
- Origin idea: <where it came from — user, paper, observation>
- Proposed mechanism: WHY this should work. A causal story about participants,
  structure, or constraints. "The backtest showed it" is NOT a mechanism.
- Exact change: the SINGLE variable that differs from the frozen baseline.
- Frozen baseline: <config path / hash>
- Primary metric: ONE number, aggregation and risk unit stated.
- Kill test: the result that REJECTS, as a threshold, decided NOW.
- Required controls: which nulls, which siblings, which diagnostics.
- Data scope: instruments, dates, and whether the sample is consumed.
- Multiple-testing note: N cells in the family; family-max reported.
- Prior: what you currently believe will happen, and why.
```

The **Prior** line is unusual and extremely valuable. Writing "strong NO-GO
prior: every selectivity filter tested here has been a rarity amplifier" before
the run is what stops a marginal result from surprising you into belief.

A real example: `futures/nq/noise_vwap/experiments/hypotheses/HYP-0017.md`.

---

## Step 2 — Implement as a default-off overlay, prove parity

```python
def run(bars, bands, ..., new_knob=0.0):     # 0.0 == OFF == prior behaviour
    ...
```

```python
def test_new_knob_parity():
    base = engine.run(bars, bands, **BASELINE)                 # before the change
    off  = engine.run(bars, bands, **BASELINE, new_knob=0.0)   # after
    pd.testing.assert_frame_equal(base, off)                   # BIT-EXACT, trade level
```

If parity fails, you have changed the baseline, and every delta you are about to
measure is contaminated. Fix this before proceeding — no exceptions.

Every knob in `core/engine2.py` in this workspace carries a documented parity
assertion. This has caught regressions repeatedly.

---

## Step 3 — Run on a common sample

```python
common = sorted(set(base_trades.date) | set(var_trades.date))
# or, more strictly, the intersection of ELIGIBLE SESSIONS
common = sorted(set(base_sessions) & set(var_sessions))
base_day = base_day.reindex(common, fill_value=0.0)
var_day  = var_day.reindex(common,  fill_value=0.0)
```

A variant with a longer warmup silently starts later and drops your worst years.
Always compare over the identical set of sessions, with zero-trade days filled.

---

## Step 4 — Read the full diagnostic panel

Never look at Sharpe alone. The panel:

```python
def compare(base, var, label=""):
    rows = []
    for name, t in (("baseline", base), (label, var)):
        s = summarize(t, INST, COST, all_days=common)
        rows.append(s)
    d = pd.DataFrame(rows)
    d.loc["delta"] = d.iloc[1] - d.iloc[0]
    return d[[
        "n_trades", "trades_per_day",
        "gross_pts_per_trade", "net_pts_per_trade",   # per-trade QUALITY
        "net_R",                                       # total EXPOSURE-weighted return
        "sharpe_net_daily", "day_net_t",
        "max_dd_R", "hit_rate", "payoff_ratio",
        "stop_frac", "mean_hold_min",                  # what the exit actually did
        "n_long", "n_short",
    ]]
```

### The four readings that decide almost everything

**1. Did per-trade quality rise or fall?**
`gross_pts_per_trade` on the **kept** trades.
- Rises → the change carries real per-trade information.
- Falls while Sharpe rises → you are selecting the *worse* trades and only
  helping via reduced exposure. **Rarity filter.**

**2. Did total net R hold?**
Sharpe can rise while total return falls, purely from cutting exposure. If
`net_R` drops materially, this is a **capacity/turnover lever**, not alpha.

Say so explicitly in the write-up. Levers are useful — for cost management,
capacity, or a size-constrained account — but they are not edges and must never
be banked as Sharpe claims.

**3. Did drawdown improve or worsen?**
A Sharpe gain with worse max DD is reshaping the return distribution, not adding
return. Report both.

**4. Did the exit mechanics change?**
`stop_frac` 0.64 → 0.82 with `mean_hold_min` falling and gross/trade down 30% =
you tightened the leash. That is variance reduction, and its null will center
positive.

---

## Step 5 — Apply the real gate. If it fails, STOP.

The gate from this workspace:

```
ADOPT if:   Δ daily Sharpe >= +0.10  AND  net R >= baseline net R
LEVER if:   Δ daily Sharpe >= +0.05  AND  gross/trade rises  AND  net R falls
            -> label as capacity/turnover lever, default OFF
REJECT if:  neither
```

> **Gate the expensive null on the primary metric.** A failing real pass is
> already a REJECT. Do not spend 30 full-pipeline null draws confirming a
> rejection.

This is the highest-ROI process rule in the course. In this workspace, of ~30
material experiments, roughly **two thirds were rejected at this step** without
ever running a null.

---

## Step 6 — The discriminating controls

Only run these if step 5 passed.

### a) Matched-count random drop (for any filter)

```python
n_keep = len(var_trades)
rand = np.array([metric(engine.run(bars, bands,
                                   entry_gate=random_subset(all_signals, n_keep, s)))
                 for s in range(200)])
print(f"frac(random >= real) = {(rand >= real).mean():.3f}")
```

`frac >= 0.05` → rarity filter. `frac > 0.5` → **anti-selection**: random
dropping beats your filter, i.e. you are systematically removing good trades.
(The overnight-gap veto here scored 0.805 — random beat it 80% of the time.)

### b) Neighbouring parameters

```python
for lb in (70, 80, 90, 100, 110):
    print(lb, metric(run(lookback=lb)))
```

A real effect has a **plateau**. A spike at exactly one value in a noisy surface
is a fitted point.

### c) Cost ladder

```python
for c in (0.0, 0.25, 0.5, 1.0, 2.0):    # ticks per side
    print(c, summarize(var_trades, INST, c*TICK)["net_R"])
```

### d) Era split

```
>= 3 of 4 eras must improve on BOTH net R and drawdown.
```
An uplift concentrated in one era on consumed data is a forward-watch candidate.

### e) Exit-geometry knife (if the change touches exits)

Re-run with a symmetric bracket or a fixed-horizon forward return. If the effect
disappears, it is exit geometry, not entry information.

### f) Long/short symmetry

If the improvement is entirely long-side on a positive-drift instrument, it is
drift.

---

## Step 7 — The null (paired, family-reproducing)

```python
real_uplift = metric(var) - metric(base)
nulls = []
for s in range(30):
    nb = null_c_returns(bars, seed=s)
    nbands = build_bands(nb)                        # REBUILD features on the null tape
    nulls.append(metric(var_cfg, nb, nbands) - metric(base_cfg, nb, nbands))
nulls = np.array(nulls)
z = (real_uplift - nulls.mean()) / nulls.std(ddof=1)
p = ((nulls >= real_uplift).sum() + 1) / (len(nulls) + 1)
print(f"real={real_uplift:+.3f}  null={nulls.mean():+.3f} +/- {nulls.std(ddof=1):.3f}  "
      f"z={z:+.2f}  p={p:.4f}  center_sign={'POS' if nulls.mean()>0 else 'NEG'}")
```

If you searched a family, the null must reproduce the **whole search** and you
compare family-max to family-max (lesson 10 §10.7).

### Reading it

| | Verdict |
|---|---|
| real ≫ null, null center **negative** | Strongest possible. Real, tied to the specific thing you changed. |
| real ≫ null, null center **≈ 0** | Real information. |
| real > null, null center **positive** | **Variance amplifier.** REJECT. |
| real inside the null band | No evidence. Post-hoc screen. |

---

## Step 8 — The sibling market

The cheapest mechanism test there is. Run the identical change on a correlated
instrument (NQ↔ES, ES↔YM, GC↔SI, EURUSD↔GBPUSD).

- **Sign transfers** → the effect is a property of the asset class / tape
  structure, and your mechanism survives.
- **Sign inverts** → your mechanism is falsified, even if the primary market's
  null passed. The effect may still be real, but it is *market-specific and
  unexplained*.

Real case: the early-flat cutoff passed its null on NQ convincingly. Its stated
mechanism (MOC imbalances, passive rebalancing, 0DTE gamma) applies **at least
as strongly to the S&P**. ES inverted. Verdict: real on NQ, mechanism falsified,
forward-watch only — do **not** attribute it to the claimed cause.

---

## Step 9 — Write the verdict

Into `artifacts/runs/EXP-XXXX/review.md`, immutable:

```markdown
# EXP-00XX — <hypothesis title>

## Verdict
REJECT / ADOPT / LEVER (default-off) / QUALIFIED (forward-shadow)

## Result
baseline: n=4209 gross=3.509pt netR=91.20 Sharpe=1.288 maxDD=4.70R
variant : n=1556 gross=4.247pt netR=39.42 Sharpe=0.694 maxDD=7.18R
delta   : Sharpe -0.594, netR -51.78, retain 37%

## Gate
FAILED (Sharpe delta -0.594 < +0.10; net R below baseline). No Null C spent.

## Decisive diagnostic
<the one reading that settled it>

## Alternative explanations considered
<what else could produce this; why you ruled them out>

## Controls run
matched-count random drop: frac(random>=real)=0.805 -> ANTI-selection
neighbouring params: monotone degradation, no plateau
sibling (ES): same sign, same magnitude -> not NQ-specific noise

## Builder / Reviewer
builder: <name>  reviewer: <name>  review status: <accepted|objections>

## Reproduce
python -m project.scripts.hyp_00XX NQ
```

**And update the ledger row and `MEMORY.md`.** Rule 25: *a NO-GO verdict is a
successful research outcome.* Preserve negative evidence, mark superseded
claims, and never leave an authoritative handoff describing a dead edge as live.

---

## Worked example: a complete rejection

From `EXP-0026` (Hurst-exponent entry filter), abbreviated:

**Hypothesis.** A breakout should continue in a persistent tape (H > 0.5) and
fail in an anti-persistent one. Gate entries on causal session-to-date Hurst.

**Result.** Family-best on **both** NQ and ES was the same un-tuned natural cell
`H ≥ 0.5`. NQ ΔSharpe **+0.058**, ES **+0.084**. Both below the +0.10 gate, and
**net R fell** on both (NQ 91.2 → 80.8).

**Gate: FAILED.** No Null C spent.

**But the positive finding was recorded:** gross pts/trade rose *monotonically*
with the threshold (NQ 3.51 → 4.59, ES 0.73 → 1.01), the chop direction was
worse everywhere (sign confirmed), and `H ≥ 0.5` **beat** a 200-draw
matched-count random-drop null on NQ (frac = 0.03). So the Hurst level **is** a
real, cross-market, mechanism-consistent per-trade quality signal — it is **not**
a rarity filter.

**It just does not monetise.** It raises per-trade quality ~30–38% while cutting
exposure ~40%. Better selection + less exposure = no risk-adjusted gain.
**Turnover/capacity lever, not alpha.**

**And the derivatives were inert:** every dH/d²H cell, both directions, both
markets, worse than baseline.

That write-up is worth more than a GO, because it closes an entire axis. Two
follow-up experiments (Hurst as exit conditioner, Hurst as sizing weight) then
also failed, and the axis was declared exhausted with evidence.

---

## The patterns that recur

After ~30 experiments in this workspace, essentially every rejection fell into
one of these:

| Pattern | Signature |
|---|---|
| **Rarity filter** | Sharpe ↑, gross/trade ↓, matched-count null reproduces it |
| **Variance amplifier** | Sharpe ↑, null centers **positive**, fewer trades |
| **Capacity/turnover lever** | gross/trade ↑, net R ↓, Sharpe flat |
| **Width/capacity dial** | "New statistic" is just the old one rescaled; residual vs baseline is **flat** across slots |
| **Drift double-count** | The feature restates something the strategy already monetises downstream; acting on it upstream mis-selects |
| **Vol-era weighting** | Effect exists in dollars, vanishes in R |
| **Anti-selection** | Random dropping **beats** the filter |
| **Exit geometry** | Effect vanishes under a symmetric bracket |
| **Coarse-bar fill artifact** | Effect vanishes at finer resolution |

Learn to recognise these from the diagnostic panel alone. It will save you
months.

---

## Checklist

- [ ] Baseline frozen, committed, hashed. Never improved in place.
- [ ] Hypothesis file written and committed **before** the run, with a prior.
- [ ] Change implemented default-off; bit-exact trade-level parity proven.
- [ ] Common sample, zero-days filled.
- [ ] Full diagnostic panel read, not just Sharpe.
- [ ] Gross/trade on kept trades read.
- [ ] Total net R and max DD read.
- [ ] Real gate applied; null NOT spent on a failing pass.
- [ ] Matched-count random-drop null run for any filter.
- [ ] Neighbouring parameters show a plateau, not a spike.
- [ ] Cost ladder and era split run.
- [ ] Null paired, features rebuilt, family search reproduced.
- [ ] Null **center sign** interpreted.
- [ ] Sibling market run as the mechanism test.
- [ ] Verdict written into an immutable run artifact, ledger, and MEMORY.md —
      including NO-GO.

Next: [12 — Institutional protocol](12_institutional_protocol.md)
