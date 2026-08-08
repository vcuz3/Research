# RSI/z fade — seconds-scale FILL MODEL (frozen spec)

Preregistered 2026-08-06, before the run. Question posed by the user: the minute-scale
`delay=1` (fill at open of *t+2*) assumption bakes in a full 60-second latency, which is far
too conservative — real decision+route latency is ~1.5 s. Does a fill at the **next candle
open** (`delay=0`, open of *t+1*) become defensible once we look at the true sub-second path,
and is the leftover cost just the spread the market order crosses?

## What is being measured

The engine currently prices entries at a bar **open mid** (`_rsi_stop_engine.simulate`
`entry = O[:,0]`). A real market order arrives ~1.5 s into that bar and crosses the spread.
Two optimisms separate the open-mid from a real fill:

1. **Sub-second adverse selection** — the ~1.5 s of front-loaded reversion between the minute
   boundary and the actual fill. On a reversion signal this moves price *in our favour*, so a
   real fill is worse than the open mid, and worst on the fast-reverting trades that carry the
   edge (this is the seconds-scale analogue of the freshness delay-1 collapse). **This spec
   measures this.**
2. **The spread** — the market order fills at bid/ask, not mid. Handled separately by the
   Workstream-A cost model; **NOT** re-charged here (data is mid-only, so charging it here
   would double-count).

## Data

`data/lse/fx/fx_{PAIR}_1s*.parquet` — 1-second **mid** OHLC (no bid/ask), event-sampled
(a bar exists only where the tape moved), ~111 M rows/pair, spanning 2009 → 2020-07 (EUR) …
2021-11 (NZD). Overlaps 2012–2023 on ~2,500–3,000 days/pair. The fill test therefore runs on
the **covered subsample** of our 2012-2023 trades (roughly 2012–2020); coverage per pair/era
is reported (rule 9a), and the uncovered late tail is stated, not hidden.

## Method

Signals and minute exits come unchanged from `_rsi_stop_engine` (event clock, non-overlap).
For each accepted signal *i*, entry bar = *i+1*, `T_entry` = its minute boundary (UTC).
From the 1-second tape, `px1s(T)` = last 1s close at-or-before `T` (causal, market-order fill),
valid only if a print exists within 120 s before `T` (else the fill is stale/illiquid → NaN,
counted as uncovered).

Latency grid **L ∈ {0, 1.5, 5, 15, 30, 60} s** past `T_entry`. Reported per pair, per era:

- **(A) Sub-second adverse selection** (basis-free, internal to the 1s tape):
  `asel_L = side · (px1s(T_entry+L) − px1s(T_entry)) / pip`. Positive = fill worse than the
  boundary = cost. The headline number is `asel` at **L = 1.5 s**.
- **(B) Realised gross edge vs latency**: entry = `px1s(T_entry+L)`, exit = minute
  `open(i+31)` (30-min horizon, held fixed across L). Report `mean_pips` and `mean_R`
  (R = pips / (rv_30m·1e4·open_mid)) at each L. `L=0` ≈ current delay-0; `L=60` cross-checks
  against the known delay-1-minute number.
- **(C) Case split at L = 1.5 s** (the user's mechanism): extreme-direction move
  `ext = (−side)·(px1s(T_entry+1.5) − px1s(T_entry))/pip`. **Case A** (extended ≥1 pip,
  `ext ≥ +1`, conservative fill), **Case B** (reversed ≥1 pip, `ext ≤ −1`, adverse fill),
  middle otherwise. Report fractions and mean `asel_1.5` within each.
- For the vol-gate cell also report `mean_R` under the compulsory **2.0 R stop** with the fill
  as both entry and stop anchor, at L = 0 and L = 1.5 s.

## Preregistered reading

- If `asel_1.5s` is ≈ 0 or favourable and gross `mean_R` at L = 1.5 s retains ~all of the L = 0
  edge → the delay-0 open fill is **validated**; the spread (Workstream A) is the only
  remaining charge, and delay-0 becomes the defensible primary.
- If `asel_1.5s` is materially adverse (front-loading bites) → keep a **measured seconds-scale
  latency haircut** (a per-era pip cost), replacing both the delay-0 optimism and the crude
  delay-1 full-minute conservatism.

Runs on the **base** (`zonly`, |z|≥1.5, no gate) first, then the **vol-gate cell**
(`gated`, vei_atr_z ≥ early-era 60th pct). No holdout consumed (all ≤ 2023, mostly ≤ 2020).

Reproduce: `python -u _run_rsi_fill_model.py`.
