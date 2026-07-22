# EXP-0029 — Laplace recency-weighted noise band (HYP-0020)

- Builder: Claude (Opus 4.8), 2026-07-22
- Command: `python -m futures.nq.noise_vwap.scripts.hyp_0020_laplace_band real {NQ|ES}`
- Evidence: `laplace_nq.txt`, `laplace_es.txt`; band `core/bands.py::noise_bands_laplace`
  (+ `laplace_weights`), tests `tests/test_bands.py::TestLaplaceBand`.
- Verdict: **REJECT — cross-market NO-GO. No Null C spent** (the real MATCHED-width
  gate fails on both NQ and ES; standing gate rule).

## What was tested

User idea: the flat lb90 mean band beats shorter lookbacks (EXP-0025) but under-weights
recent sessions. Rather than truncate history, keep a long window and tilt the trailing
per-slot average toward recent sessions with a Laplace kernel `w_k = exp(-|k-mu|/b)`
over lag `k=1..lookback`. Swept the two shape knobs the user named — center-of-mass
`mu ∈ {1,5,15,30}` and decay half-life `h ∈ {5,15,40}` sessions (`b=h/ln2`) — with the
window DERIVED (`lookback = clip(mu+5b, 90, 250)`) so slower decay uses a longer
lookback (the user's "slow decay for long lookback"). The `b→∞, lookback=90` cell
reduces to the deployed baseline EXACTLY (proved in `tests/test_bands.py`).

Only the band construction changed; engine, VWAP gate, 30-min RTH clock, every-bar
continuous stop, next-open fills and costs are the frozen baseline. All 12 cells +
baseline scored on the common post-lb250 date set (every cell defined on identical
dates = same-sample). RAW view exposes the width dial; MATCHED view rescales each cell
to the flat baseline's median width to isolate the recency-tilt SHAPE (EXP-0021 control).

## Result — both markets FAIL the +0.10 matched gate

MATCHED-width (the real test), best cell:

| market | best matched cell | dSharpe | dNetR | dGross pt/t | dTrades | verdict |
|---|---|---|---|---|---|---|
| NQ | mu5 h15 (lb114) | **−0.019** | −1.6 | +0.119 | −17 | FAIL |
| ES | mu1 h5 (lb90) | **+0.065** | +3.1 | −0.081 | −136 | FAIL (<+0.10) |

- **NQ**: *every* matched cell is worse than the flat baseline (Sharpe 1.26). The
  best is only −0.019, and the whole grid spans −0.019 → −0.219. Recency-tilting the
  band strictly degrades NQ.
- **ES**: the best matched cell clears zero (+0.065) but misses the +0.10 gate, and it
  is a **width/capacity artifact, not the mechanism**: gross pts/trade *falls* (−0.081)
  with 136 *fewer* trades (raw scale 1.082 → the raw band was narrower and got scaled
  up). It also does **not transfer** — the identical cell (mu1 h5) is one of NQ's
  *worst* matched cells (−0.117). Same-cell sign disagreement across the sibling pair
  is the cross-market kill.

## Decisive diagnostic — the residual is FLAT across slots (no reshape)

Residual `laplace_sigma / flat_sigma` by decision slot at matched width:

- NQ (mu5 h15): **1.0038 – 1.0067** across all 13 slots — flat ≈1.005.
- ES (mu1 h5): **1.0757 – 1.0832** across all 13 slots — flat ≈1.08.

In both markets the residual is essentially constant in the time-of-day slot. A Laplace
recency tilt is therefore just the flat band **uniformly rescaled**, with no
slot-dependent reshaping — the exact EXP-0021 quantile signature. (The ES ≈1.08 offset
is only median-vs-mean mismatch left by median-width-matching; it is a level scale, not
a shape, which is why it collapses to the width dial above.)

## Interpretation

Every (mu, b) cell is a linear reweighting of the same per-slot `|move|` history. The
per-slot LEVEL is a sufficient statistic for the band (EXP-0021), and the every-bar
continuous stop already supplies the current-session vol adaptivity a recency tilt was
meant to add (EXP-0025). If per-slot sigma is roughly stationary the flat mean is the
minimum-variance estimator, so re-weighting toward recent sessions only adds estimator
variance to a well-estimated quantity — which is exactly what NQ shows (uniformly worse,
maxDD up e.g. 4.7→8.2R at mu1 h5). The user's premise (lb90 is "too lagging" for recent
regime changes) is disconfirmed at the band level: the band needs only a stable long-run
level; recency adaptivity lives in the stop, not the envelope.

This is consistent with the completed recast programme (EXP-0020 cone / EXP-0021 quantile
/ EXP-0022 asymmetric) and EXP-0025 (surround/short-history): the noise band is fully
summarized by its per-slot flat symmetric level/width across *every* axis tried — time
profile, distributional shape, up/down symmetry, estimator bias/variance (pooling +
history length), and now **cross-history weighting**.

## Controls / integrity

- `b→∞, lb90` reduces to `noise_bands(df, 90)` bit-exact; `scale` linear; strict
  `min_periods=lookback` → coverage identical to the flat band at each lookback;
  causality (a date sees only strictly-prior sessions) — all proved in
  `tests/test_bands.py::TestLaplaceBand` (6 tests, pass).
- Same-sample: all cells scored on common post-lb250 dates.
- Width confound neutralized by the RAW/MATCHED split; the residual-by-slot read shows
  no reshape independent of the Sharpe numbers.
- No Null C spent — the real MATCHED gate fails on both markets (standing rule).

## Review

- Reviewer: Claude (Opus 4.8), 2026-07-22
- Decision: REJECT confirmed — cross-market NO-GO. Retain `core/session.py::noise_bands`
  (flat lb90). `noise_bands_laplace` / `laplace_weights` retained in `core/bands.py` as
  the tested recency-weighting benchmark.
- Objections: none blocking. Exact reduction + causality proved in tests; the flat
  cross-slot residual makes the reject mechanistic (a scale, not a reshape), not merely a
  failed Sharpe number.
