# ATR Counter-Bar Breakout — Findings

> **SUPERSEDED 2026-08-19:** this report was generated from a cache filtered on
> 09:30–16:00 UTC rather than New York RTH. Its NO-GO conclusion is invalid. Use
> `../vu_explore.ipynb` and see `../MEMORY.md` for the corrected status. The text
> below is retained only as an audit record of the invalidated run.

**Verdict: NO-GO on both NQ and ES.** The strategy has **no gross edge** (gross
per-trade return is negative on both instruments before any cost), so no cost
assumption, fill convention, or downstream vol-targeting rescues it. This is the
clean-negative-gross NO-GO of shared LEARNINGS #7.

## Strategy (exactly as specified)

5-minute RTH bars (09:30–16:00 ET), one session at a time, symmetric long/short.

- **Setup (prior-day info only):** daily ATR(14) from RTH true range, **lagged one
  session** (day *D* uses ATR through *D–1*, the lookahead guard). At the RTH open
  fix `up = open + 0.5·ATR`, `down = open − 0.5·ATR`; timeout = 5 bars.
- **Bar loop, in order:** (1) *exit first* — if in a position, exit when the bar
  **close** crosses back through the session open (the stop) or it is the last bar
  (EOD flat); (2) *pending entry* — once a breakout is armed, enter on the first
  **counter-move** bar (a down bar before a long, an up bar before a short — "wait
  for a pullback, don't chase"); if none within 5 bars, force the entry; (3) *detect
  breakout* — if flat, `close > up` arms a long, `close < down` arms a short.
- **Exit:** stop-at-open or EOD only — no target, no trailing stop.
- **PnL:** `dir·(exit − entry)/session_open` (return units), summed per day.

## Execution & costs

Decisions are on 5-min closes. **Headline fill = next-bar open** (workspace Rule 2;
EOD exits fill at the last bar's close). A `close`-fill ablation is reported for
completeness. Costs per trade: spread/slippage `min(0.5 bps·price, cap·tick)` per
side × 2 sides; fixed fees `$0.70 clearing + $1.00 commission` round-trip, converted
to return units at the **micro** contract point value ($2 MNQ / $5 MES) as the user
specified. Cap swept at 2 and 1 ticks/side.

## Headline results (fill = next-open, cost cap = 2 ticks/side)

### NQ (MNQ)
| metric | aggregate | pre-2023 | post-2023 |
|---|---|---|---|
| sessions | 3,834 | 2,921 | 913 |
| trades | 1,927 | 1,456 | 471 |
| hit rate (net) | 0.472 | 0.462 | 0.505 |
| mean net / trade | −3.02 bps | −3.18 bps | −2.51 bps |
| Sharpe (zero-day) | **−0.582** | −0.594 | −0.542 |
| Sharpe (trade-day) | −0.837 | −0.859 | −0.768 |
| Sharpe (vol-target) | −0.348 | −0.370 | −0.235 |
| max DD (zero-day, ret units) | −0.638 | −0.507 | −0.153 |

### ES (MES)
| metric | aggregate | pre-2023 | post-2023 |
|---|---|---|---|
| sessions | 3,834 | 2,921 | 913 |
| trades | 1,826 | 1,388 | 438 |
| hit rate (net) | 0.457 | 0.445 | 0.495 |
| mean net / trade | −3.86 bps | −4.19 bps | −2.84 bps |
| Sharpe (zero-day) | **−0.853** | −0.867 | −0.825 |
| Sharpe (trade-day) | −1.261 | −1.282 | −1.219 |
| Sharpe (vol-target) | −0.729 | −0.700 | −0.797 |
| max DD (zero-day, ret units) | −0.698 | −0.586 | −0.130 |

*Three Sharpes are reported per user memory; all are annualised ×√252. Zero-day =
all usable RTH sessions with non-trading days as 0; trade-day = trading days only;
vol-target = causal trailing-20-session vol-scaled daily series.*

## Why it's a NO-GO — the decisive read is gross

| instrument | gross / trade | gross Sharpe (zero-day) | gross hit |
|---|---|---|---|
| NQ | **−0.80 bps** | −0.154 | 0.499 |
| ES | **−1.57 bps** | −0.347 | 0.481 |

Entry-to-exit is a coin flip (gross hit ≈ 0.49–0.50) with a slightly negative mean,
i.e. the ATR breakout + counter-bar-pullback entry captures no directional
continuation into the close on either index. ~85% of exits are EOD flat (the
session-open stop rarely triggers), so this is a signal problem, not an exit-timing
one. Costs (~2.2–2.3 bps/trade) then take it from ≈0 to clearly negative.

## Sensitivity (aggregate zero-day Sharpe)

| | NQ | ES |
|---|---|---|
| next-open, cap 2t | −0.582 | −0.853 |
| next-open, cap 1t | −0.545 | −0.846 |
| close, cap 2t | −0.569 | −0.826 |
| close, cap 1t | −0.532 | −0.819 |

Negative in every cell; the fill convention and 1-vs-2-tick cap barely move it. The
post-2023 split is *less* negative but still negative on both — no regime rescue.

## Controls / integrity notes

- **Lookahead guard:** ATR is `shift(1)` at daily grain; bands are fixed from the
  09:30 open; entries/exits act only on completed-bar closes filled at the next open.
  No completed-bar OHLC is used to trade inside its own bar (Rule 2).
- **Fills feasible:** stop and breakout are close-confirmed, filled next-open; a
  next-open fill is never a stale/impossible price (Rule 1). Hand-verified one trade
  end-to-end against raw bars.
- **Rolls:** 0 RTH sessions span a contract roll on either instrument, so no bar
  crosses a roll.
- Because gross is already negative, no null model was spent (gate rule) — there is
  no positive real result to discriminate.

## Reproduce

```
python -m futures.nq.atr_breakout_explore.run next_open 2.0
python -m futures.nq.atr_breakout_explore.run close 1.0
```
Artifacts (trades, daily series, per-split reports) in `../artifacts/`.
