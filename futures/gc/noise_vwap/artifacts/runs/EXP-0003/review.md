# EXP-0003 — HYP-0002: VWAP-anchor × band-multiplier × lookback grid (WFO + holdout + max-stat Null-C)

Grid search over 2 VWAP anchors × 5 band vol-multipliers × 5 noise lookbacks (50
cells), scored era-neutrally (daily Sharpe on net return), tested by expanding-
window WFO and a consumed final-slice holdout, and gated by a max-statistic Null-C
over the whole search. Exit clock = decision (baseline-faithful); stop is
`max(band, vwap)` long / `min(band, vwap)` short, checked on the 30-min clock.

## Commands

```
python -m futures.gc.noise_vwap.scripts.grid_wfo grid       # grid + WFO + holdout
python -m futures.gc.noise_vwap.scripts.grid_wfo null 200    # max-stat Null-C gate
```

Fast path: `core/session.py` (load_rth_both — both anchors in one read; k-scalable
bands), `core/engine2_nb.py` (numba, bit-exact vs core.engine: 2641 trades, gross
+0.3586 pt reproduced), `core/nulls_session.py` (sdate/mfo return-shuffle, rebuilds
both anchors' VWAP; diffusivity real=null=0.1000 pt).

## Data scope

GC RTH 2011-12-09..2026-07-16, 3557 common sessions (post lb=90 warmup). IS = 2845
(→2023-08-16), holdout = 712 (2023-08-17→). Consumed history; holdout is a
robustness split, NOT sealed. Cost 0.50 tick/side + fees = 0.0725 pt/side.

## Results

### Full-sample grid — top cells vs baseline (daily Sharpe on net return)

| anchor | lb | k | Sharpe | t | net_pt | day$ | n |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| rth | 5 | 1.50 | 0.487 | 1.83 | +0.378 | +21.8 | 2050 |
| eth | 5 | 1.50 | 0.477 | 1.79 | +0.386 | +21.8 | 2008 |
| eth | 14 | 0.50 | 0.460 | 1.73 | +0.288 | +31.2 | 3856 |
| rth | 5 | 1.25 | 0.449 | 1.69 | +0.296 | +20.7 | 2491 |
| eth | 60 | 2.00 | 0.447 | 1.68 | +0.538 | +15.3 | 1009 |
| **rth** | **90** | **1.00** | **0.265** | **1.00** | **+0.214** | **+15.9** | **2641** *(baseline)* |

Best of 50 = Sharpe 0.487 at **t=1.83 (not significant, and uncorrected for the
50-cell search)**. Winners are short lookbacks (5–14). **The ETH anchor is a wash**
— rth/eth interleave throughout the ranking; anchoring VWAP to the Globex session
adds nothing. Answers the anchor question directly: the VWAP anchor is not a lever.

### Expanding WFO (5 test folds, IS 2013–2023)

| | Sharpe | t | net_pt | day$ | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| WFO-selected stream | **−0.450** | −1.38 | −0.196 | −7.7 | 926 |
| static baseline | −0.145 | −0.44 | −0.058 | −4.3 | 1749 |

Fold picks thrash (rth/lb90/k1.5 → rth/lb14/k2 → eth/lb14/k2 → rth/lb5/k1.5 →
eth/lb14/k2) and train Sharpe decays 1.80 → 0.39. The adaptively-selected config is
**negative and worse than the untuned baseline** out-of-fold — textbook overfit.

### Best-IS cell on the consumed holdout (2023–2026)

| | Sharpe | t | net_pt | day$ | n |
| --- | ---: | ---: | ---: | ---: | ---: |
| best-IS cell (eth/lb60/k2.0) | 0.686 | 1.15 | +1.373 | +45.1 | 234 |
| static baseline | **0.841** | 1.41 | +0.928 | +71.2 | 546 |

The plain baseline **beats** the grid-selected cell on the holdout. Selection does
not generalize.

### Max-statistic Null-C — STOPPED (partial, not the basis of the verdict)

The Null-C gate was stopped at 76/200 draws by direction: the real/descriptive pass
(kill condition 1) had already REJECTED the hypothesis on complete OOS evidence, so
the expensive null was unnecessary (see [[gate-nullc-on-success-metric]] — a failing
real pass is already a REJECT; run Null-C only on a positive, confirmed result).

Partial evidence (76 draws), directional only: real best-of-50 Sharpe = 0.487 vs
null best-of-50 mean 0.520 (std 0.128), z = −0.26, and 62% of noise draws produced a
best-of-50 at least as large as the real one. Consistent with the in-sample winner
being a multiple-testing artifact, but this is NOT relied on for the verdict.

## Interpretation

Three findings, all pointing the same way:

1. **No out-of-sample winner.** The in-sample best (Sharpe 0.487) is not
   significant and does not survive either OOS test: WFO selection is *negative*
   and worse than the static baseline; the holdout *prefers the untuned baseline*.
2. **The ETH VWAP anchor is inert.** RTH and ETH cells are statistically
   indistinguishable across the grid — the overnight-anchored VWAP neither helps
   nor hurts. Consistent with EXP-0002's finding that the gold edge is tied to the
   equity cash session's structure, not to alternative anchors/hours.
3. **Era instability.** The 2013–2023 decade is net-negative for both baseline and
   grid; the positive full-sample number is carried by the 2011–13 and 2023–26
   endpoints. The full-sample Sharpe is not a stationary edge.

This reproduces the NQ WFO pattern (every uplift met-or-beaten by its own noise) on
gold, and is fully consistent with the standing NO-GO.

## Kill test

Kill condition (1) fired decisively on complete evidence: **no cell beats the
baseline out-of-sample** (WFO −0.45 < baseline −0.15; holdout best-IS 0.686 <
baseline 0.841). That alone REJECTS HYP-0002; the max-stat Null-C (condition 2) was
not needed and was stopped at 76 draws (partial evidence points the same way).
**HYP-0002 REJECTED.**

## Verdict

- Reviewer: claude (builder self-review; independent review outstanding)
- Date: 2026-07-19
- Decision: **REJECTED.** No grid configuration beats the frozen baseline out-of-
  sample. Do not adopt any tuned cell. The VWAP anchor is not a lever; band-k and
  lookback tuning is overfitting.
- Objections / limits: holdout and WFO are on CONSUMED history (robustness, not
  sealed). t-stats throughout are <2. This search consumed 50 more cells of the
  history; from here only a future shadow is clean evidence.
