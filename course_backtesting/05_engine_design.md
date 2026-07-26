# 05 — Writing the trading simulation engine

The engine is a **state machine over bars**. Its job is to answer, for every
bar: *given only what was knowable at this instant, what order would have
existed, and what price could it have received?*

Everything else — metrics, statistics, plots — is downstream of that answer
being correct.

---

## 5.1 Architecture

```
data loader        →  bars       (immutable, causal, audited)
feature builder    →  bands/ATR/VWAP/gates  (causal, audited)
        ↓
    ENGINE  ── per session ──→  trades   (date, side, entry/exit mfo & px, points, reason)
        ↓
   accounting  →  costs, sizing, per-day P&L
        ↓
    metrics    →  the numbers you report
        ↓
    nulls / statistics  →  whether you believe them
```

**Hard boundaries:**

- The engine takes **bars + features + config**, returns a **trade list**. It
  computes no metrics, applies no costs, does no sizing.
- Costs and sizing are applied downstream, so gross P&L stays auditable
  separately from net. (Rule 20: *always report gross alongside net.* If gross
  ≈ modeled cost, your conclusion is cost-model-dependent, not an edge.)
- **Experiment scripts call the engine. They never reimplement it.** Every
  reimplementation is a new place for a fill artifact to hide.

---

## 5.2 The trade record

Fix this schema early; everything downstream depends on it.

```python
dict(
  date      = session date,
  side      = +1 long / -1 short,
  entry_mfo = minutes-from-open of the FILL bar (not the signal bar),
  exit_mfo  = minutes-from-open of the EXIT FILL bar,
  entry_px  = filled price,
  exit_px   = filled price,
  points    = (exit_px - entry_px) * side,        # GROSS, before costs
  reason    = "stop" | "flip" | "eod" | "tp" | "istop" | "ladder_sl" | ...,
  tp_frac   = fraction banked early (0 if none),
)
```

Why each field earns its place:

- **`entry_mfo` is the fill bar, not the signal bar.** Storing the signal bar is
  how off-by-one fill audits become impossible later.
- **`reason`** is your most valuable diagnostic. `stop_frac` (fraction of trades
  exiting by stop) is how this workspace detected that a "better" exit was
  merely tightening the leash: stop_frac 0.64 → 0.82 with gross/trade dropping
  30%.
- **`points` is gross.** Costs are one subtraction downstream.

---

## 5.3 The information clock — the single most important design decision

Write this at the top of your engine file and never violate it:

```
Decisions are read on a bar's CLOSE.
Every fill is the NEXT bar's OPEN.
```

That is the honest default for close-based signals on OHLC bars (Rule 2). It is
what `core/engine2.py` does:

```python
def fill(i):
    """Return (price, mfo) for a fill decided at bar i. Next-open, always."""
    if fill_mode == "signal_close":
        return close[i], mfo[i]           # ABLATION ONLY — see below
    if i + 1 <= flat_i:
        return opn[i + 1], mfo[i + 1]
    return None, None                      # no bar left: the trade cannot open
```

Note the third branch: **if there is no next bar, there is no fill.** A signal
on the last bar of the session does not become a trade. Engines that silently
fill at the current close on the last bar manufacture free money at exactly the
moment the session's direction is known.

### `signal_close` is a measuring instrument, not a mode

Keep a `fill_mode="signal_close"` path — filling at the signal bar's own close —
**purely to measure the size of the fill artifact**. Run both, report both:

```
next_open   : Sharpe 1.31
signal_close: Sharpe 1.82      <- the gap IS the artifact you would have booked
```

In this workspace the same-bar fill accounted for **most of a reported
Sharpe-1.8 edge** in one project and **two-thirds of the headline** in another.
For fast clocks and event-driven entries this check is make-or-break; slow-clock
robustness does not transfer for free.

---

## 5.4 Entry mechanics

Three entry modes, in increasing order of how carefully you must audit them:

### a) Clock entry (safest)
Evaluate only at prespecified decision times.

```python
if is_decision and m in band_map:
    up, lo = band_map[m]
    if c > up and (not require_vwap or c > w):
        want = 1
    elif c < lo and (not require_vwap or c < w):
        want = -1
```

The decision clock itself must be defined precisely. From `core/session.py`:

```python
def decision_mfos(period: int, max_mfo: int) -> list[int]:
    """Decide at mfo = j*period - 1 (i.e. minute-from-open % period == 0 with the
    open counted as minute 1); exposure starts the NEXT bar."""
    return [j*period - 1 for j in range(1, max_mfo//period + 2) if j*period - 1 <= max_mfo]
```

The `-1` is the off-by-one that broke the original replication in this project.
"Every 30 minutes" is ambiguous: is the 09:59 bar or the 10:00 bar the end of
the first 30-minute block? Both are defensible; only one matches the source.
**Write it down, and test it against a known reference.**

### b) Event / threshold entry
Evaluate at every bar, trigger when price closes beyond a level by a buffer.

```python
buf = entry_buf_atr * atr          # ATR-scaled, NEVER ticks (rule 4/19)
lok = np.isfinite(up_arr) & (close > up_arr + buf) & (close > vwap)
```

Two mandatory extras here:
- The band is a step function of `mfo`; carry it forward to every bar
  explicitly, don't interpolate.
- The buffer must be **volatility-scaled**. A fixed 2-tick buffer manufactures
  a monotone "high-volatility edge" — this is a documented failure here.

### c) Delayed / confirmed entry
Arm a timer on the first qualifying close, enter `k` bars later **iff the
condition still holds**:

```python
if entry_mode == "delay":
    delay_side = np.zeros(n, dtype=int)
    pend, target = 0, -1
    for i in range(n):
        if pend != 0 and i == target:
            if (pend == 1 and lok[i]) or (pend == -1 and sok[i]):
                delay_side[i] = pend           # confirmed: fill NEXT open
            pend, target = 0, -1
        if pend == 0:
            if   lok[i]: pend, target = 1, i + entry_delay
            elif sok[i]: pend, target = -1, i + entry_delay
```

Distinguish **endpoint recheck** (above — price may wander in between) from
**persistence** (condition must hold every bar). They are different strategies
with different trade counts; conflating them is a common silent bug.

---

## 5.5 Exit mechanics

### The stop

```python
# reference level
if   stop_ref == "vwap": base = vwap[i]
elif stop_ref == "band": base = up_i if pos == 1 else lo_i
else:                    base = max(up_i, vwap[i]) if pos == 1 else min(lo_i, vwap[i])

sbuf = stop_buf_atr * atr                      # ATR-scaled loosening/tightening
stop = base - sbuf if pos == 1 else base + sbuf
hit  = (c < stop) if pos == 1 else (c > stop)
```

Note this is a **close-triggered** stop, not an intrabar-touch stop. That is a
deliberate conservative choice: a close-triggered stop with a next-open fill
cannot be over-credited, because both prices are observable and ordered. An
intrabar-touch stop on OHLC data requires you to resolve a path you cannot see —
see §5.7.

### Exit-check cadence

Whether you check the stop only at decision times or at every bar is a
**strategy parameter with large effects**, not an implementation detail:

```python
cadence = int(exit_check) if isinstance(exit_check, int) else None
check_mfos = {m for m in mfo if (m + 1) % cadence == 0} if cadence else None
check_here = (is_decision or exit_check == "every_bar"
              or (check_mfos is not None and m in check_mfos))
```

Measured in this workspace: tightening from a 30-minute check to every bar gave
NQ Sharpe 1.14→1.28 (**GO**), ES 0.93→0.92 (wash), GC 0.46→−0.06 (**inverts**).
It reliably shrinks the loser tail everywhere and drops gross/trade ~30%
everywhere; whether that is net-positive depends on the instrument's
drift-to-noise ratio. **Never transfer an exit upgrade across instruments on one
market's result.**

### Flip

```python
flip = (want == -pos) and (is_decision if entry_mode == "clock" else True)
if (hit and check_here) or flip:
    close_trade(i, "flip" if flip else "stop")
    if flip:
        px, pmfo = fill(i)
        if px is not None:
            open_pos(want, px, pmfo)
```

Decide and document: does a reversal signal close-and-reverse in one fill, or
close then wait? Both are implementable; the P&L differs. Note the exit and the
new entry share the **same** fill price here — that is correct (one bar's open),
and the cost accounting must charge the full round trip for the closed trade
plus a new entry for the opened one.

### Break-even latch

```python
fav = (c - entry_px) * pos                     # favourable close excursion
if be_atr > 0 and (be_on or fav >= be_atr * atr):
    be_on = True                                # LATCHED — never un-arms
    stop = max(stop, entry_px) if pos == 1 else min(stop, entry_px)
```

The latch matters: without `be_on`, the break-even floor would disappear when
price pulls back, which is not what a real order does.

### Ratchet trailing stop

```python
if trail_step_atr > 0:
    fav_max = max(fav_max, fav)                # peak favourable CLOSE excursion
    step = trail_step_atr * atr
    k = int(np.floor(fav_max / step))
    if fav_max >= start * atr and k >= 1:
        ratchet = entry_px + pos * (k - 1) * step
        stop = max(stop, ratchet) if pos == 1 else min(stop, ratchet)
```

Two invariants: it is driven by **close** excursion (consistent with the
decision discipline, no intrabar optimism), and it **only ever tightens**.

### Partial take-profit + runner

```python
if tp_atr > 0 and not partial_done and fav >= tp_atr * atr:
    px, _ = fill(i)                            # next open, momentum-confirmed
    if px is not None:
        banked = tp_frac * (px - entry_px) * pos
        taken_frac = tp_frac
        partial_done = True

# at exit:
runner = (exit_px - entry_px) * pos
pts = banked + (1.0 - taken_frac) * runner
```

Note this is **more conservative than an intrabar limit order** would be — the
close must confirm, then you fill at the next open. Good: you would rather
understate.

The contract sides net to one round trip (1 in, 0.5 + 0.5 out), so charging one
round-trip cost per trade row remains correct.

### The forced flat

```python
rth_idx = np.where(is_rth)[0]
flat_i = int(rth_idx[-1])                      # last RTH bar = the daily flat
...
for i in range(n):
    if i >= flat_i:
        break                                  # also stops new entries
...
if pos != 0:                                   # EOD close at the flat bar
    trades.append(dict(..., exit_px=close[flat_i], reason="eod"))
```

For an intraday strategy this must be **unconditional**. It is also why the
`fill()` helper checks `i + 1 <= flat_i`: you cannot fill at a bar past the
flat.

---

## 5.6 Costs

Keep costs **out** of the engine and apply them once, explicitly:

```python
rt_cost = 2.0 * cost_pts_per_side               # round trip, in POINTS
t["net_pts"] = t["points"] - rt_cost
```

Build `cost_pts_per_side` from the real components:

| Component | How to set it |
|---|---|
| Half-spread | 0.5 tick for a liquid index future taking liquidity; measure it, don't assume |
| Commission + exchange + clearing | your actual broker schedule, in points: `$/contract ÷ point_value` |
| Slippage | ≥ 0 extra ticks for market/stop orders; more in fast markets |
| Market impact | 0 at 1 contract; must be modelled if you claim size |

Then **stress it**. Report the metric across a cost ladder:

```python
for c in (0.0, 0.25, 0.5, 1.0, 2.0):            # ticks per side
    print(c, summarize(trades, inst, c * TICK[inst]))
```

Read it this way:
- **Dies at 1 tick/side** → not a strategy, it's a cost-model artifact. (YM in
  this workspace: gross Sharpe 0.51, dead by 1 tick.)
- **Survives 2 ticks/side** → the conclusion is robust to your cost assumptions.

And per **Rule 6**: cost stress is *not* fill validation. Validate causality,
trigger feasibility, and price availability **first**; only then stress costs.
Cost stress on an impossible fill just tells you how impossible it is.

---

## 5.7 Fill assumptions — the taxonomy

| Order type | What you may credit | What you may NOT credit |
|---|---|---|
| **Market at next open** | The next bar's `open`, exactly. | Anything better. |
| **Stop, triggered intrabar** | The first tradable price **after** the trigger. On gaps: the gap price, not the stop level. | The stop level when the bar gapped through it. |
| **Stop already crossed at placement** | It is marketable — treat as a market order at the next available price. | The stale stop price. **This is the Sharpe-2.07 killer.** |
| **Limit, price traded through by a margin** | Fill, with a volatility-scaled trade-through guard. | Fill on a mere touch. |
| **Limit, price merely touched** | Nothing, without queue evidence. | A fill. |
| **Both stop and target reachable in one bar** | The **adverse** one (default). | The favourable one. |

### The three rules that follow

**1. Assert feasibility in code, per trade.**

```python
def assert_fill_feasible(trades, bars):
    """Every credited price must have existed after the order became active."""
    b = bars.set_index(["sdate", "mfo"])
    for t in trades.itertuples():
        bar = b.loc[(t.date, t.entry_mfo)]
        assert bar.low - 1e-9 <= t.entry_px <= bar.high + 1e-9, \
            f"entry {t.entry_px} outside [{bar.low},{bar.high}] on {t.date}@{t.entry_mfo}"
        assert t.entry_mfo > t.signal_mfo, "same-bar fill on a close-based signal"
```

Run it on **every** trade of **every** run. It is cheap. It would have saved
weeks here.

**2. Resolve intrabar ambiguity adversely.**

```python
def resolve_bar(bar, side, stop, target):
    hit_stop   = bar.low <= stop  if side == 1 else bar.high >= stop
    hit_target = bar.high >= target if side == 1 else bar.low  <= target
    if hit_stop and hit_target:
        return "stop", stop          # ADVERSE default — you cannot see the order
    if hit_stop:   return "stop", stop
    if hit_target: return "target", target
    return None, None
```

The acceptable alternatives to the adverse default are: finer-resolution
reconstruction, an explicitly *validated* intrabar model, or reporting
upper/lower P&L bounds. "It probably hit the target first" is not one of them.

**3. Passive fills need queue evidence proportional to your claim.**

A print at your limit price does not prove a fill. With coarse bars, require
adverse **trade-through** and run a sensitivity test. And the guard must be
**volatility-scaled**:

```python
# BAD: manufactures a monotone high-vol "edge"
filled = bar.low < limit_price - 2 * TICK

# ACCEPTABLE HEURISTIC (still not a queue model)
filled = bar.low < limit_price - 0.1 * atr
```

Fixed-tick wick capture manufactured a fake high-volatility edge in the NQ VWAP
pullback study here.

### The finer-resolution check

If your strategy has any intrabar path dependence, re-run it identically at a
materially finer resolution. Design the engine keyed on **timestamps**, not bar
indices, so the same code runs both. In `EXP-0009` here, the 1-minute
continuous-stop result was re-run on **68.3 million 1-second bars**: daily
Sharpe 0.923 → 0.883, within the pre-declared −0.15 tolerance. That is what
"validated execution" looks like. Contrast the GC fade: 1m Sharpe +0.57 → 1s
+0.08, i.e. the whole thing was the coarse bar.

---

## 5.8 Position and portfolio accounting

**Rule 13:** daily portfolio P&L is the **sum** of position-level P&L, never
the mean of that day's trades. Averaging 61 overlapping positions per day
produced Sharpe 6.3 from a per-trade-negative strategy in this workspace.

```python
day_pnl = trades.groupby("date")["net_pts"].sum() * POINT_VALUE[inst]   # CORRECT
day_pnl = trades.groupby("date")["net_pts"].mean() * POINT_VALUE[inst]  # WRONG
```

And **Rule 12**: session weighting is invalid when it implicitly requires the
final number of signals — unknown at allocation time. Retrospective session
averaging turned per-bet t = −1.1 into t = −12.4 here. The default estimand is
the **equal-weighted per-bet effect** for equal-risk bets; report portfolio/
session results *in addition*, when capital is managed at that level.

If the strategy permits overlap, model netting, capital limits, leverage, and
aggregate exposure explicitly. If it permits only one position, **enforce
non-overlap in the engine** (as the single `pos` variable above does).

### Sizing

Keep the engine at **1 unit** and apply sizing downstream, so you can always
separate "the edge" from "the sizing policy":

```python
# constant risk: size so that the committed stop distance = a fixed fraction
risk_per_trade = 0.005 * equity
contracts = risk_per_trade / (init_stop_atr * atr * POINT_VALUE[inst])
contracts = np.floor(contracts).clip(1, max_contracts)   # integer contracts!
```

The `floor` and the cap are not details — on a small account they dominate. A
finding from here: vol-target sizing is **survival, not alpha**; it can convert
a positive-expectancy strategy into a failing one under a trailing-drawdown
constraint, and it improved nothing when the underlying edge was
volatility-independent.

---

## 5.9 The complete minimal engine

```python
def simulate_session(bars, band, decision_mfos, *,
                     fill_mode="next_open", require_vwap=True,
                     exit_check="decision", stop_ref="both",
                     tp_atr=0.0, tp_frac=0.5, be_atr=0.0) -> list[dict]:
    b = bars.sort_values("mfo").reset_index(drop=True)
    mfo, opn, close, vwap = (b[c].to_numpy() for c in ("mfo","open","close","vwap"))
    is_rth = b.is_rth.to_numpy()
    atr = float(b.atr.iloc[0]); the_date = b.sdate.iloc[0]
    n = len(b)

    flat_i = int(np.where(is_rth)[0][-1])
    band_map = {int(r.mfo): (r.upper, r.lower) for r in band.itertuples()}
    decision_set = {int(t) for t in decision_mfos}

    pos, entry_px, entry_mfo = 0, np.nan, None
    banked, taken_frac, partial_done, be_on = 0.0, 0.0, False, False
    trades = []

    def fill(i):
        if fill_mode == "signal_close": return close[i], mfo[i]
        return (opn[i+1], mfo[i+1]) if i + 1 <= flat_i else (None, None)

    def close_trade(i, reason):
        nonlocal pos, entry_px, entry_mfo
        px, pmfo = fill(i)
        if px is None: return False
        runner = (px - entry_px) * pos
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=pmfo, entry_px=entry_px, exit_px=px,
                           points=banked + (1-taken_frac)*runner,
                           reason=reason, tp_frac=taken_frac))
        pos, entry_px, entry_mfo = 0, np.nan, None
        return True

    for i in range(n):
        if i >= flat_i: break
        m, c, w = int(mfo[i]), close[i], vwap[i]
        if m not in band_map: continue            # no band -> no decision at all
        is_decision = m in decision_set

        want = 0
        if is_decision:
            up, lo = band_map[m]
            if   c > up and (not require_vwap or c > w): want = 1
            elif c < lo and (not require_vwap or c < w): want = -1

        if pos != 0:
            up_i, lo_i = band_map[m]
            base = (max(up_i, w) if pos == 1 else min(lo_i, w)) if stop_ref == "both" \
                   else (w if stop_ref == "vwap" else (up_i if pos == 1 else lo_i))
            stop = base
            fav = (c - entry_px) * pos
            if be_atr > 0 and (be_on or fav >= be_atr * atr):
                be_on = True
                stop = max(stop, entry_px) if pos == 1 else min(stop, entry_px)
            hit = (c < stop) if pos == 1 else (c > stop)
            check_here = is_decision or exit_check == "every_bar"
            flip = (want == -pos) and is_decision
            if (hit and check_here) or flip:
                if close_trade(i, "flip" if flip else "stop") and flip:
                    px, pmfo = fill(i)
                    if px is not None:
                        pos, entry_px, entry_mfo = want, px, pmfo
                        banked, taken_frac, partial_done, be_on = 0.0, 0.0, False, False
                continue
            if tp_atr > 0 and not partial_done and fav >= tp_atr * atr:
                px, _ = fill(i)
                if px is not None:
                    banked, taken_frac, partial_done = tp_frac*(px-entry_px)*pos, tp_frac, True

        if pos == 0 and want != 0 and is_decision:
            px, pmfo = fill(i)
            if px is not None:
                pos, entry_px, entry_mfo = want, px, pmfo
                banked, taken_frac, partial_done, be_on = 0.0, 0.0, False, False

    if pos != 0:                                   # forced EOD flat
        runner = (close[flat_i] - entry_px) * pos
        trades.append(dict(sdate=the_date, side=pos, entry_mfo=entry_mfo,
                           exit_mfo=int(mfo[flat_i]), entry_px=entry_px,
                           exit_px=close[flat_i],
                           points=banked + (1-taken_frac)*runner,
                           reason="eod", tp_frac=taken_frac))
    return trades
```

---

## 5.10 Engine audit tests (write these on day one)

```python
def test_no_same_bar_fill(trades):
    assert (trades.entry_mfo > trades.signal_mfo).all()

def test_fill_price_within_bar(trades, bars): ...        # §5.7

def test_flat_at_close(trades):
    assert (trades.exit_mfo <= LAST_RTH_MFO).all()

def test_no_overlap(trades):
    for _, g in trades.groupby("date"):
        g = g.sort_values("entry_mfo")
        assert (g.entry_mfo.values[1:] >= g.exit_mfo.values[:-1]).all()

def test_default_off_parity(engine, bars, bands):
    """Every new overlay must reproduce the prior baseline bit-exactly when off."""
    base = engine.run(bars, bands, **BASELINE)
    with_overlay = engine.run(bars, bands, **BASELINE, new_knob=0.0)
    pd.testing.assert_frame_equal(base, with_overlay)

def test_zero_edge_gives_zero(engine):
    """A synthetic random walk with symmetric rules must produce ~0 gross."""
    ...

def test_costs_monotone(trades):
    """Net P&L must be strictly decreasing in cost."""
    prev = np.inf
    for c in (0, 0.25, 0.5, 1.0):
        v = summarize(trades, "NQ", c)["net_pts_per_trade"]
        assert v < prev; prev = v
```

`test_default_off_parity` is the one people skip and the one that catches the
most. Every knob in `core/engine2.py` here has a documented parity assertion.

---

## Checklist

- [ ] Decisions on close, fills on next open. `signal_close` exists **only** as
      a labelled ablation, and its delta is reported.
- [ ] No fill when there is no next bar.
- [ ] Decision clock defined exactly and tested against a reference.
- [ ] All buffers/guards ATR-scaled, never fixed ticks.
- [ ] Intrabar ambiguity resolved adversely, or finer data used.
- [ ] Per-trade fill-feasibility assertion runs on every run.
- [ ] Stops close-triggered (or intrabar-touch with validated path resolution).
- [ ] Forced flat is unconditional and also blocks new entries.
- [ ] Costs applied downstream; gross and net both reported; cost ladder run.
- [ ] Day P&L is a **sum**, not a mean.
- [ ] Engine at 1 unit; sizing is a separate, downstream policy.
- [ ] Every overlay default-off with bit-exact parity proof.

Next: [06 — Lookahead, leakage & fill traps](06_lookahead_and_traps.md)
