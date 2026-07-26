# EXP-0036 — Wilder-RMA VEI entry gate on noise-VWAP (revisit of EXP-0035)

- Hypothesis: HYP-0025 (re-run with the revised VEI estimator)
- Builder: Claude (Opus 4.8), 2026-07-26
- Verdict: **NO-GO (not validated), but an informative upgrade over EXP-0035.** With the
  cleaner Wilder RMA ATR the NQ `low`-VEI gate now PASSES the real gate and decisively
  beats the matched-count random-drop null (real per-trade info) — but it FAILS the
  decisive drift-preserving Null C (dSharpe frac(null≥real)=0.175) and does NOT transfer
  to ES (net R falls). A real-but-weak per-trade quality tilt, not a validated edge.

## Why this run

EXP-0035 tested VEI as a noise-VWAP entry gate using the simple rolling-mean (SMA) ATR
and was a clean NO-GO. `vei_exploration` Study A (EXP-0001) then showed the SMA ratio is
the jumpiest, least-informative VEI variant (lag-1 autocorr ≈0, whipsaws the 1.0 line
~46%), while the **Wilder RMA** ATR triples the forward-vol IC and makes VEI a persistent
regime read. This run repeats the exact EXP-0035 gate sweep with `method="wilder"`
(`core/vei.py`, backward-compatible; SMA still reproduces EXP-0035). Everything else is
identical: continuous-stop baseline, 5 (short,long) variants × 2 directions × 7 VEI
quantile thresholds, primary = zero-day daily net-ATR-R Sharpe uplift, net R co-primary,
standing-rule gating of the Null C.

## Result

Baseline (both): NQ Sharpe 1.288 / netR 91.20 / 4209 trades; ES 0.698 / 51.47 / 4326.

| market | family-best cell | retain | dSharpe | dNetR | rand-drop frac(≥real) Sh/R | real gate |
|---|---|---|---|---|---|---|
| **NQ** | VEI(5/20) `low` ≤1.003 | 0.855 | **+0.105** | +0.33 | 0.000 / 0.000 | **PASS** |
| ES | VEI(5/20) `low` ≤0.853 | 0.382 | +0.139 | **−11.99** | 0.005 / 0.025 | REJECT |

- **NQ real gate PASSES** (dSharpe≥+0.10 AND netR≥base). The passing direction is `low`
  — keep breakouts firing out of a *contracting/coiled* tape (VEI≤1.00), drop the
  highest-VEI ~15% (late chases). This matches EXP-0035's descriptive Part-C (low-VEI
  breakouts continue better on NQ), now sharpened by the better estimator.
- **Matched-count random-drop null: real beats it decisively** (frac 0.000). Dropping the
  same number of *random* breakouts centers at −0.105 Sharpe; the low-VEI selection is
  NOT a rarity/turnover filter — it selects genuinely better trades (exp net-R/trade
  0.0217→0.0254). This is the first VEI cell in the whole investigation to clear both the
  real gate and the rarity discriminator.

### The decisive test: drift-preserving Null C (NQ, 40 draws)

| metric | real | null mean | null center | z | frac(null≥real) |
|---|---|---|---|---|---|
| dSharpe (primary) | +0.1045 | −0.0006 | ≈0 (NEG) | +0.90 | **0.175** |
| dNetR | +0.33 | −1.99 | NEG | +0.28 | 0.400 |

The Null C **fails** the p≤0.05 bar (0.175). The null centers near zero (not strongly
positive), so this is not the pure "drop-trades→Sharpe-up" variance-amplifier signature
of EXP-0010/0012 — the effect is milder than that. But the real +0.10 uplift still sits
inside the null band: ~17.5% of drift-preserving return shuffles reproduce it. Since the
Null C recomputes VEI on the shuffled path, the low-VEI quality selection is largely
reproduced once order is destroyed — i.e. it is tied to vol-geometry/selection the
shuffle preserves rather than to a unique intraday timing signal (the EXP-0032
ATR-buffer lesson: a vol-adaptive selection benefit is path-geometry the null keeps).

### ES does not transfer

ES's "best" cell cuts 62% of trades and net R falls −12.0 → real gate REJECT; a
turnover/capacity lever, no deployable transfer. (Its retain 0.38 vs NQ 0.86 shows the
threshold that "helps" is not stable across markets.)

## Interpretation

The estimator matters, exactly as Study A said: swapping SMA→Wilder moved the NQ gate
from clear-fail (EXP-0035) to real-gate-pass + rarity-beating — a genuine sharpening of
a real, cross-referenced per-trade signal (low-VEI breakouts are better quality). But it
is **not validated alpha**: it fails the drift-preserving Null C on the primary metric
(p=0.175), the net-R uplift is ≈0 (pure Sharpe/variance effect), the passing cell is a
searched max barely over the gate, and it does not transfer to ES. Terminal verdict is
the same as EXP-0035 (NO-GO) but for a sharper, more honest reason: a real weak per-trade
quality tilt that does not rise to a timing edge — the recurring project pattern
(volatility-INDEPENDENCE; RVOL/gap/Hurst/ATR-buffer all landed here).

Retain the unconditioned continuous-stop baseline. `core/vei.py` now supports
`method∈{sma,wilder,ema}` (default sma; tests pass). Note for future: the NQ recent era
(2023+ recent_sharpe 0.884 on the best cell) and the low-VEI quality tilt are a
forward-watch curiosity only (rule 26), not bankable on consumed history.

## Reproduce

```
python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real NQ 30 wilder
python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter real ES 30 wilder
python -u -m futures.nq.noise_vwap.scripts.hyp_0025_vei_filter null NQ 40 wilder
```

## Independent review

- Reviewer: unassigned
- Status: not-reviewed
- Open items: confirm the Wilder ATR causality in `core/vei.py`; confirm the Null-C
  primary metric is dSharpe (the gate's primary) — reported here as frac 0.175; the
  script's stored `nullc_*` fields are on dNetR (frac 0.400). Both fail ≤0.05.
