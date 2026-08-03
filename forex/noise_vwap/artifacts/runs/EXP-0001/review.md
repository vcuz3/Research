# EXP-0001 — Noise-Area + TWAP port to four FX majors

- Hypothesis: `experiments/hypotheses/HYP-0001.md`
- Date: 2026-08-01
- Builder: Claude (Opus 5)
- Reviewer: pending independent review
- Status: completed — **REJECT**, on the preregistered gross gate
- Reproduce: `python -u -m forex.noise_vwap.scripts.run_grid`
- Artifacts: `grid.csv` (96 cells x 3 costs), `controls.csv`, `report.txt`,
  `summary.json`
- Engine: `core/engine_nb.py`, trade-level identical to the readable reference
  `core/engine.py` across 400 configurations (`tests/test_parity.py`)

## Result

**The port fails at the GROSS level on all four pairs, in both session
definitions, in 88 of the 96 declared cells.** This is the RTY signature — a
clean NO-GO that no exit, cost or sizing change rescues.

Primary configuration (published rule with TWAP substituted: `gate=on`,
`stop_ref=both`, `every_bar`), 0.5 pip/side:

| session | pair | trades | gross pips/trade | net pips/trade | hit | Sharpe (zero-day) | net R |
| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |
| fxday | EURUSD | 17,173 | **−0.520** | −1.520 | 0.135 | −3.380 | −303 |
| fxday | GBPUSD | 16,636 | **−0.471** | −1.471 | 0.142 | −2.304 | −224 |
| fxday | AUDUSD | 15,709 | **−0.576** | −1.576 | 0.137 | −3.664 | −338 |
| fxday | NZDUSD | 14,960 | **−0.601** | −1.601 | 0.141 | −3.980 | −335 |
| active | EURUSD | 9,182 | **−0.525** | −1.525 | 0.175 | −2.338 | −170 |
| active | GBPUSD | 8,912 | **−0.142** | −1.142 | 0.181 | −1.299 | −103 |
| active | AUDUSD | 8,453 | **−0.404** | −1.404 | 0.167 | −2.609 | −186 |
| active | NZDUSD | 8,213 | **−0.507** | −1.507 | 0.167 | −3.038 | −194 |

## Kill test (declared before the run)

| gate | fxday | active |
| --- | --- | --- |
| 1. median gross pips/trade > 0 | −0.548 → **FAIL** | −0.455 → **FAIL** |
| 2. >= 3 of 4 pairs with net Sharpe >= +0.30 | 0/4 → **FAIL** | 0/4 → **FAIL** |
| **verdict** | **REJECT** | **REJECT** |

Both gates fail on both sessions. Per the standing gate-Null-C rule, **Null C
was not spent**: a real pass that fails its primary metric is already a reject,
and a null cannot rescue a negative gross.

## Reading the declared grid

The grid is read as a slope and a cross-pair transfer, not an argmax
(LEARNINGS 2026-07-27). Across all 96 cells at 0.5 pip/side:

- gross pips/trade: min −1.162, median **−0.498**, max +0.241;
- net zero-day Sharpe: min −4.130, median −1.947, max −0.356;
- 8 of 96 cells have positive gross, all of them tiny; the single best is
  GBPUSD `active|anchor|gate=1|decision` at **+0.241 pips gross**, which is
  still only a quarter of the 1.0 pip round-trip cost and nets Sharpe −0.356.

There is no corner of the declared family that trades.

### Stop reference — the user's question

Net zero-day Sharpe / net pips per trade / trades, `gate=on`, `every_bar`:

| session | pair | `both` (band+TWAP) | `band` only | `anchor` (TWAP) only |
| --- | --- | --- | --- | --- |
| fxday | EURUSD | −3.380 / −1.520 / 17,173 | −3.240 / −1.525 / 16,677 | −1.606 / −1.546 / 9,106 |
| fxday | GBPUSD | −2.304 / −1.471 / 16,636 | −2.213 / −1.468 / 16,112 | −0.949 / −1.317 / 8,720 |
| fxday | AUDUSD | −3.664 / −1.576 / 15,709 | −3.504 / −1.617 / 15,069 | −2.075 / −1.803 / 8,564 |
| fxday | NZDUSD | −3.980 / −1.601 / 14,960 | −3.694 / −1.608 / 14,234 | −2.441 / −2.011 / 8,271 |
| active | EURUSD | −2.338 / −1.525 / 9,182 | −1.929 / −1.399 / 8,492 | −1.479 / −1.663 / 5,916 |
| active | GBPUSD | −1.299 / −1.142 / 8,912 | −1.060 / −1.032 / 8,290 | −0.627 / −0.953 / 5,746 |
| active | AUDUSD | −2.609 / −1.404 / 8,453 | −2.360 / −1.416 / 7,863 | −1.765 / −1.614 / 5,548 |
| active | NZDUSD | −3.038 / −1.507 / 8,213 | −2.741 / −1.505 / 7,599 | −2.245 / −1.883 / 5,480 |

Three things, all consistent across all eight pair/session combinations:

1. **The volume-free `band` stop costs almost nothing relative to the published
   `both` rule.** Sharpe is 0.09–0.41 *better*, net pips/trade within ±0.13, on
   ~4% fewer trades. Whatever the TWAP contributes as a stop reference is
   negligible here — which is expected, because `max(upper, twap)` only differs
   from `upper` when the anchor has crossed above the band, and by then the
   trade is already deep in trouble. **If this construct were ever worth
   trading on FX, losing the volume would not be the reason it failed.**
2. **`anchor` (the TWAP-touch exit) has the least-bad Sharpe on all eight** —
   but only because it trades ~47% less. Net pips/trade is *worse* on six of
   eight. It is a turnover lever, the pattern this workspace has now rejected
   a dozen times, and here it merely loses less slowly.
3. The ordering `anchor` > `band` > `both` on Sharpe is monotone in trade count.
   That is the signature of exposure reduction on a losing strategy, not of
   exit information.

### Entry-gate ablation

Turning the TWAP entry gate ON improves Sharpe on all eight combinations, by
+0.068 to +0.164, and cuts trades by 4–9%. The gate is doing real work as a
filter — it is the only component that helps — but it improves a loser into a
smaller loser. Net pips/trade is *lower* with the gate on in seven of eight,
so the gate removes trades that were, per trade, slightly less bad.

### Drift controls (the RTY diagnostic)

Always-long and always-short, entered at the first decision bar and held to the
session close, one trade per session:

| session | EURUSD | GBPUSD | AUDUSD | NZDUSD |
| --- | ---: | ---: | ---: | ---: |
| fxday, always-long gross pips/session | −0.226 | −0.047 | +0.569 | +0.700 |
| active, always-long gross pips/session | −1.153 | +0.430 | −0.619 | −0.256 |

Note these are algebraically mirrored by construction (always-short is the exact
negation, sharing the same fills), so the short row carries no independent
information — rule 16. What they do establish is the magnitude and consistency
of the drift: **±0.05 to ±1.15 pips per session, with the sign disagreeing
between the two session definitions for three of the four pairs.** There is no
persistent intraday drift in either direction for a breakout system to ride.

For scale, the strategy loses ~2.3–2.7 gross pips per session on `fxday`. The
loss is therefore an order of magnitude larger than the drift: this is **not**
merely "no drift to ride", the entries are actively adverse. EXP-0002 isolates
why.

### Cost sensitivity

Gross is negative on 7 of 8 primary cells, so cost is not the binding
constraint. Even at 0 cost the strategy loses on every pair in the `fxday`
session and on three of four in `active`. Reported at 0.25 / 0.50 / 1.00
pip/side in `report.txt`; the ranking never changes.

Note also that 0.5 pip/side is *optimistic* for the `fxday` session, which
trades through the Asia hours and the daily roll where real FX spreads are
several times wider. Realistic costs make the `fxday` result worse, never
better, so this does not threaten the rejection.

## Trade structure — the loss is in the entry, not the stop

| session | pair | stop-outs | hit rate | mean hold (min) |
| --- | --- | ---: | ---: | ---: |
| fxday | EURUSD | 92.2% | 0.135 | 85 |
| fxday | NZDUSD | 91.5% | 0.141 | 100 |
| active | GBPUSD | 87.5% | 0.181 | 83 |

Loosening the stop from `every_bar` to the 30-minute `decision` cadence raises
the hit rate to 0.21–0.28 and roughly doubles the hold, and gross **stays
negative** (−0.31 to −0.76 pips/trade, one cell at +0.16). So the 92% stop-out
rate is a symptom, not the cause: a directionless tape entered at a local
extreme produces stop-outs whatever the cadence.

## Alternative explanations considered

- **Bad volume substitution.** Ruled out by the `band` column: the fully
  volume-free stop performs as well as the published `both` rule on all eight
  combinations. The missing VWAP is not why this fails.
- **Wrong session definition.** Both a 24-hour FX day and a London→NY active
  window were run. They differ in level (active is less bad) but agree in sign
  on every pair.
- **Costs.** Gross is negative; see above.
- **Stop too tight.** Ruled out by the cadence comparison above and, more
  cleanly, by EXP-0002's exit-neutral arm.
- **A data defect.** `reports/DATA_QUALITY.md` audits every stage. Band coverage
  at decision slots is 1.0000 on all eight combinations, bar availability at
  decision slots is 0.9993–0.9998, and the session anchor is stable on
  98.1–100% of sessions. The one real archive defect found (IBKR chunk-boundary
  gaps at `:00–:14` of some hours) was neutralised by anchoring the FX day at
  17:15 ET and pinning the decision clock to the ET wall clock, and is asserted
  in `tests/test_core.py`.

## Builder interpretation

The Noise-Area + VWAP construct does not port to FX majors, and the reason is
not the missing volume. The workspace's cross-instrument ladder now reads:

    NQ (strong intraday drift)      -> works
    ES (weaker)                     -> works, weaker
    GC / YM (weak, costly)          -> positive gross, cost-fragile
    RTY (no intraday drift)         -> NO gross edge
    EURUSD/GBPUSD/AUDUSD/NZDUSD     -> NEGATIVE gross, all four, both sessions

FX sits at the far end. This strengthens, on a new asset class, the existing
conclusion that this strategy family's transferability is governed by the
target's own intraday drift/continuation and not by the band machinery.

## Independent review

- Reviewer: pending
- Objections: pending
- Verdict: pending
