# Require Reset Rule

This document defines the `require_reset` re-entry rule in enough detail for an independent implementation to reproduce the same behavior as the current engine.

Primary implementation references:

- [signals.py](C:/Users/Anthony%20Nguyen/Desktop/Noise-Area-Research/src/signals.py)
- [backtest.py](C:/Users/Anthony%20Nguyen/Desktop/Noise-Area-Research/src/backtest.py)
- [features.py](C:/Users/Anthony%20Nguyen/Desktop/Noise-Area-Research/src/features.py)
- [config.py](C:/Users/Anthony%20Nguyen/Desktop/Noise-Area-Research/src/config.py)

## Purpose

`require_reset` is a same-side re-entry filter.

Its purpose is:

- after a stop-out on one side
- do not allow another entry on that same side immediately
- wait until price has first returned inside the Noise Area
- only then allow a fresh same-side breakout entry

This rule does **not** block opposite-side entries.

## Where the rule applies

This rule applies only when:

- the strategy is flat
- the last stop-driven exit was on a known side
- a new entry is being considered on that same side

It does not affect:

- the initial entry of the day
- exits themselves
- opposite-side entries after a stop-out

## State variables required

An implementation must maintain these state variables:

```text
position ∈ {flat, long, short}
stopped_side ∈ {none, long, short}
reset_observed ∈ {true, false}
```

Recommended initialization:

```text
position = flat
stopped_side = none
reset_observed = true
```

Meaning:

- `position`
  - the current live position
- `stopped_side`
  - the side most recently stopped out
- `reset_observed`
  - whether price has returned inside the Noise Area since that stop-out

## Decision-clock dependency

The engine does not evaluate this continuously tick by tick.

The rule is only checked at the strategy's scheduled decision timestamps.

For run 18, those timestamps were:

- `10:00`
- `10:30`
- `11:00`
- `11:30`
- `12:00`
- `12:30`
- `13:00`
- `13:30`
- `14:00`
- `14:30`
- `15:00`
- `15:30`

in `America/New_York`.

That means a reset is only recognized when price is observed inside the Noise Area at one of those scheduled checkpoints.

## Inputs required at each decision timestamp

At each decision checkpoint, the engine must have:

- `price`
- `lower_bound`
- `upper_bound`
- `vwap`

For the current engine:

- `price` is the signal price from the prior completed bar
- `lower_bound` and `upper_bound` are the current Noise Area bounds
- `vwap` is the current session VWAP snapshot known at that decision point

## Exact reset condition

This is the exact reset rule:

```text
if lower_bound <= price <= upper_bound:
    reset_observed = true
```

This is the only event that clears the reset lock.

So in this implementation, a reset means:

- price has come back inside the Noise Area

It does **not** mean:

- price touched VWAP
- price crossed VWAP
- price reached the center of the band
- price made a new high or low

VWAP is relevant to the stop logic, not to the reset condition itself.

## Exact stop context for run 18

Run 18 used `stop_model: current_band_vwap`.

That means:

- long stop condition:
  - exit long if `price < max(upper_bound, vwap)`
- short stop condition:
  - exit short if `price > min(lower_bound, vwap)`

These stop conditions are evaluated on the same decision clock as the entries.

## State update after a long stop-out

If the strategy is currently `long` and the long exit condition is hit:

```text
position = flat
stopped_side = long
reset_observed = false
```

Interpretation:

- the engine remembers that the most recent stopped side was `long`
- another long is now blocked
- until a reset is observed

## State update after a short stop-out

If the strategy is currently `short` and the short exit condition is hit:

```text
position = flat
stopped_side = short
reset_observed = false
```

Interpretation:

- the engine remembers that the most recent stopped side was `short`
- another short is now blocked
- until a reset is observed

## Exact same-side entry permission rule

When considering a new entry on side `S`, entry is allowed only if:

```text
stopped_side != S OR reset_observed == true
```

Equivalent side-specific form:

```text
long entry allowed  if stopped_side != long  or reset_observed
short entry allowed if stopped_side != short or reset_observed
```

This is the engine's actual logic.

## Entry logic context for run 18

Run 18 uses:

- enter long if `price > upper_bound`
- enter short if `price < lower_bound`

with the extra `require_reset` permission check layered on top.

So the full same-side re-entry logic is:

- if last stopped side was `long`
  - do not allow another long while price remains outside the band
  - allow the next long only after price has first been observed back inside the band
- if last stopped side was `short`
  - do not allow another short while price remains outside the band
  - allow the next short only after price has first been observed back inside the band

## Opposite-side entries are still allowed

This rule does **not** freeze the strategy completely.

Example:

- stopped out of a long
- `stopped_side = long`
- `reset_observed = false`

In that state:

- a new long is blocked
- a new short is still allowed if the short entry condition appears

Likewise in reverse after a short stop-out.

## Sequence example: long side

Example path:

1. price is above `upper_bound`
2. strategy enters `long`
3. later, at a decision checkpoint, price falls below `max(upper_bound, vwap)`
4. strategy exits the long
5. engine sets:
   - `position = flat`
   - `stopped_side = long`
   - `reset_observed = false`
6. at the next checkpoint, price is still above `upper_bound`
   - long is still blocked
   - because price has not reset inside the Noise Area
7. later, at another checkpoint, price is inside:
   - `lower_bound <= price <= upper_bound`
   - engine sets `reset_observed = true`
8. after that, if price later breaks above `upper_bound` again:
   - long entry is allowed again

## Sequence example: short side

Example path:

1. price is below `lower_bound`
2. strategy enters `short`
3. later, at a decision checkpoint, price rises above `min(lower_bound, vwap)`
4. strategy exits the short
5. engine sets:
   - `position = flat`
   - `stopped_side = short`
   - `reset_observed = false`
6. at the next checkpoint, price is still below `lower_bound`
   - short is still blocked
7. later, price is observed inside the Noise Area
   - `reset_observed = true`
8. after that, if price later breaks below `lower_bound` again:
   - short entry is allowed again

## Difference versus `later_decision`

Under `later_decision`:

- after a stop-out, if the same-side breakout condition is still true at a later decision time
- the strategy may re-enter immediately on that later checkpoint

Under `require_reset`:

- after a stop-out, same-side re-entry is forbidden
- until price has first been observed back inside the Noise Area

This is the core distinction.

## Why the rule changes behavior

Relative to `later_decision`, `require_reset` usually:

- reduces repeated same-day re-entries
- reduces churn
- lowers cost drag
- reduces trade count

In this project, the paired comparison also showed that it improved:

- Sharpe
- CAGR
- drawdown
- expected P&L per trade

But those are empirical results, not part of the rule definition itself.

## Exact pseudocode

The following pseudocode matches the intended behavior:

```python
if lower_bound <= price <= upper_bound:
    reset_observed = True

if position == "long":
    if price < max(upper_bound, vwap):
        position = "flat"
        stopped_side = "long"
        reset_observed = False

elif position == "short":
    if price > min(lower_bound, vwap):
        position = "flat"
        stopped_side = "short"
        reset_observed = False

if position == "flat":
    long_allowed = (stopped_side != "long") or reset_observed
    short_allowed = (stopped_side != "short") or reset_observed

    if price > upper_bound and long_allowed:
        position = "long"

    elif price < lower_bound and short_allowed:
        position = "short"
```

## Important implementation note

The order of evaluation matters:

1. first recognize whether price is inside the Noise Area
2. then process stop/exit logic
3. then process entry logic

A reproducing implementation should keep the evaluation order consistent, because changing the state update order can change whether a same-timestamp reset is recognized before or after an exit decision.

## Minimal run-18 reproduction context

To reproduce the observed project behavior closely, use these settings together with `require_reset`:

- `instrument: NQ`
- `noise_lookback: 60`
- `volatility_multiplier: 1.0`
- `volatility_lookback: 14`
- `sizing_mode: volatility_target`
- `target_daily_volatility: 0.02`
- `leverage_cap: 4.0`
- `stop_model: current_band_vwap`
- `reentry_policy: require_reset`
- `same_timestamp_reversal: false`
- `price_treatment: indicative_ratio`
- `vwap_price: typical`
- `initial_capital: 1,000,000`
- `commission_per_unit_per_side: 0.85`
- `exchange_fee_per_unit_per_side: 1.40`
- `slippage_ticks_per_side: 0.25`
- `contract_multiplier: 20.0`
- `tick_size: 0.25`

## Summary

The `require_reset` rule is:

> After being stopped out on one side, do not allow another entry on that same side until price has first returned inside the Noise Area.

In this implementation, "reset" means exactly:

```text
lower_bound <= price <= upper_bound
```

and nothing else.
