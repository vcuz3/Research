# EXP-0035 — Volatility Expansion Index (VEI) on NQ and the noise-VWAP strategy

- Hypothesis: HYP-0025
- Builder: Claude (Opus 4.8), 2026-07-26
- Verdict: **NO-GO (both markets).** Real gate fails on NQ and ES → no Null C spent
  (standing rule). VEI carries no robust, cross-market, monetizable information for
  the Noise-Area + VWAP momentum strategy.

## Indicator

Volatility Expansion Index (user request): the ACCELERATION of intraday volatility,
`VEI = intraday ATR(short) / intraday ATR(long)` on 1-min RTH bars, causal within the
session (`core/vei.py`; rolling-mean True Range, TR uses the prior 1-min close, ATR
resets each session, strict `min_periods`). VEI > 1 = expanding vol, < 1 = contracting.
Baseline 10/50; variants (short,long) ∈ {(5,20),(10,50),(10,100),(14,50),(20,100)}.
Distinct from the RVOL *level* (EXP-0015/0016) and the daily ATR *scale*: VEI is a
dimensionless vol-of-vol / regime-change ratio.

Coverage (rule 9a): only the 09:59 decision slot (mfo 29) drops (long window not yet
populated intraday); every later decision slot is ~100% covered on both markets. The
deletion is conservative (drops signals, no leak). VEI dist NQ mean 0.973, med 0.945,
frac>1 = 0.367.

## Part 1 — predictive value on NQ (and ES): `scripts/vei_explore.py`

At the 30-min decision clock, VEI vs forward outcomes (session-block-bootstrap
Spearman IC, 90% CI):

| Question | NQ | ES |
|---|---|---|
| Signed forward return (direction) | IC ≈ 0 (0.002–0.011; quintile signed means ≈0) | IC ≈ 0 |
| \|forward return\| (magnitude) | IC +0.017…+0.025, CI excludes 0 | IC +0.014…+0.024, CI excludes 0 |
| Breakout continuation-to-close, ATR-R (10/50) | IC **−0.030** [−0.046,−0.015] | IC −0.011 [−0.026,+0.008] |

Reads:
- VEI does **not** predict direction (expected for a vol measure).
- VEI weakly predicts forward *magnitude* — ordinary vol clustering, small
  (Q1→Q5 |move| rises ~14%). Not tradable on its own.
- **The interesting bit:** at the breakout signal, VEI has a small but
  cross-variant-consistent **NEGATIVE** continuation IC on NQ (all five variants
  negative; baseline −0.030): breakouts firing out of a **low-VEI compression/coil**
  follow through better to the close than breakouts firing when vol has **already
  expanded** (a high-VEI late chase). This *inverts* the naive "expansion = impulse"
  thesis and is mechanism-plausible.
- **It does not transfer.** On ES the continuation IC is weak and insignificant
  (−0.011, CI includes 0) and the quintile Q5−Q1 is actually *positive* (+0.010,
  opposite sign). So even the descriptive per-trade signal is fragile / NQ-specific.

## Part 2 — VEI entry gate on the strategy: `scripts/hyp_0025_vei_filter.py`

Per-signal entry gate (rule 18, engine rerun via `entry_gate`; `engine2_nb` vs
`engine2` parity asserted). Keep breakouts with VEI ≥ T ("high") or ≤ T ("low");
sweep T over VEI quantiles {0.2..0.8} × 5 variants × 2 directions = 70 cells/market.
Frozen continuous-stop baseline. Primary = zero-day daily net-ATR-R Sharpe uplift,
net R co-primary.

- **NQ:** baseline trades 4209, Sharpe 1.288, netR 91.20. **Every one of the 70 cells
  has negative dSharpe.** Family-best is VEI(5/20) high, retain 0.85, dSharpe −0.013 —
  i.e. simply the cell that cuts the fewest trades; any VEI gate is pure
  exposure/turnover reduction on a positive-drift ride-to-close system. Matched-count
  random-drop null: real dSharpe −0.013 vs random mean −0.058, frac(rand≥real)=0.245 —
  a mild real per-trade tilt vs random dropping but noise-level and still net-negative.
  Real gate **REJECT** → Null C skipped.
- **ES:** baseline Sharpe 0.698, netR 51.47. Family-best VEI(5/20) high, retain 0.62,
  dSharpe **+0.066** but **netR falls −2.41**, and frac(rand≥real)=0.095 — a
  turnover/capacity lever that lifts Sharpe by cutting 38% of trades while losing net R
  and is not distinguishable from a random equal-count drop at 5%. Real gate
  **REJECT** → Null C skipped.
- **No cross-market consistency.** The direction that nudges ES Sharpe up ("high" =
  keep expanding-vol breakouts) is the *opposite* of NQ's Part-1 continuation sign
  ("low" = keep compressed breakouts better), and on NQ the "high" gate helps nothing.

## Interpretation

This is the project's recurring signature: a small, real *per-trade* effect (here the
NQ negative continuation IC) that does not monetize — it is a turnover/capacity lever,
not risk-adjusted alpha — and here it is weaker still because it does not even survive
cross-market as a descriptive signal. Fully consistent with the strategy's
volatility-INDEPENDENCE and the string of rejected selectivity screens: RVOL veto
(EXP-0016), gap veto (EXP-0024), Hurst filter/exit (EXP-0026/0027), and the ATR stop
buffer (EXP-0032). VEI adds a vol-regime axis, and the edge simply does not live on
that axis.

Retain the unconditioned continuous-stop baseline. `core/vei.py` is kept as tested,
reusable, causal feature machinery; the gate overlays are default-off (they reuse the
existing `entry_gate`, no core engine change). Thread closed on consumed history;
revisit only with future/shadow data.

## Reproduce

```
python -u -m futures.nq.noise_vwap.scripts.vei_explore NQ
python -u -m futures.nq.noise_vwap.scripts.vei_explore ES
python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real NQ
python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real ES
```

## Independent review

- Reviewer: unassigned
- Status: not-reviewed
- Open items: confirm the causal within-session ATR/VEI construction in `core/vei.py`
  and the `entry_gate` parity; confirm the family-best selection and the standing-rule
  gating of Null C.
