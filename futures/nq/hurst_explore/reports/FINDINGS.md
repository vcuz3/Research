# Hurst Exploration — Findings

Reviewed synthesis across runs. Detailed evidence in `artifacts/runs/EXP-*/`.
This section studies the Hurst exponent as its own object on NQ/ES, prompted by
the noise_vwap result that intraday H is a real per-trade quality signal that did
not monetize on a drift-riding momentum breakout (selection, exit, and sizing all
NO-GO). The pivot here is to characterize H itself before asking it to trade.

Data: NQ/ES 1-minute clean (2011-08 → 2026-07, 3710 RTH sessions each); NQ
1-second Databento OHLCV (2015 → 2026, high-fill sample; ES 1s not in archive).
Estimator panel validated on synthetic fBm of known H in `tests/test_hurst.py`.

> **Review correction (EXP-0003/0004):** EXP-0003 supersedes EXP-0001's
> narrative bias correction and unmatched frequency comparison. EXP-0004 adds
> uncertainty, endpoint sensitivity, and era stability to EXP-0002. The
> corrected results below are authoritative.

---

## A1 — The measurement-error floor of an intraday Hurst estimate (EXP-0001; corrected by EXP-0003)

Status: complete (descriptive). Command:
`python -u -m futures.nq.hurst_explore.scripts.a1_measurement_floor`

**1. An intraday H at a short window is mostly noise.** Synthetic std(Ĥ) for a
driftless H=0.5 path, by window length (bars) and estimator:

| n bars | ghe1 | ghe2 | R/S | DFA |
|---|---|---|---|---|
| 30  | 0.24 | 0.22 | 0.30 | 0.17 |
| 90  | 0.15 | 0.14 | 0.10 | 0.08 |
| 390 (full 1m day) | 0.09 | 0.08 | 0.05 | 0.04 |
| 5400 (1s, 90 min) | 0.055 | 0.052 | 0.019 | 0.019 |
| 23400 (full 1s day) | 0.043 | 0.041 | 0.015 | 0.015 |

The noise_vwap Hurst work estimated session-to-date H at 30-min decision points
— windows that START near n≈30, where the sampling std is **0.17–0.30**. An H of
"0.55 vs 0.45" at that window is inside one standard error: the early-session H
it filtered on was largely noise. This is the quantitative backing for why that
signal was real-but-marginal and did not survive as alpha.

**2. Estimators are biased in known, opposite directions, but they do not all
collapse to one corrected level.** Truth-recovery (long window):
the structure function (ghe1/ghe2) is near-unbiased; DFA near-unbiased with a
small positive bias at short n; **R/S carries the classic positive small-sample
bias** (true 0.30→0.38, 0.50→0.54). On real whole-session NQ 1m the panel reads
ghe1 0.463, ghe2 0.434, R/S 0.568, DFA 0.533 — an apparent split between
"anti-persistent" (ghe) and "persistent" (R/S). EXP-0003 makes the correction
executable by inverting each estimator's simulated mean-versus-truth curve.
Corrected NQ spans **0.473–0.499** and ES **0.466–0.485**. Estimator bias
explains much, but not all, of the split; the evidence supports near-random-walk
to mildly anti-persistent levels, not a universal H=0.50.

**3. 1-second data materially sharpens the estimate** (~2–3× lower std than the
full 1m day, ~5–10× lower than the early decision points). On the same 149
eligible dates, minute-plus GHE1 is 0.490 on 1s versus 0.471 on 1m. This is a
consistency diagnostic, not independent replication or exact agreement. Use
ghe1 (or DFA for lower variance), calibrate explicitly, and treat R/S cautiously.

**Rule 9a:** 1s grid fill-rate is strongly era-dependent (mean 0.80 over a
full-history sample, min 0.26 in 2011–2014; ≥0.95 in 2023–2026). Forward-filling
a sparse session injects artificial zero-returns that deflate the sub-minute
structure function, so all 1s scale work is restricted to fill ≥ 0.90 and era
≥ 2015. Degraded Databento days (16) excluded. Exact-grid validation also
excludes 7 NQ and 4 ES sessions with missing one-minute slots; see EXP-0003
`data_quality_1m.csv`.

---

## A2 — Hurst term structure across timescale H(τ) (EXP-0002; validated by EXP-0004)

Status: complete (descriptive). Command:
`python -u -m futures.nq.hurst_explore.scripts.a2_timescale`

Translation-invariant structure function K₁(τ)=mean|logp[t+τ]−logp[t]| aggregated
over sessions; local log-log slope = H(τ). A **matched-length H=0.5 random-walk
control** subtracts the finite-sample structure-function saturation that fakes
anti-persistence as τ→N. Control-corrected bands (0.5 + raw − control):

| band | NQ | ES | note |
|---|---|---|---|
| micro 1–8 s | 0.503 | — | ~random walk |
| meso 2–30 min | 0.488 (1s) / 0.491 (1m) | 0.481 | ~random walk |
| coarse 30–180 min | 0.462 | 0.468 | anti-persistent |

EXP-0004 moving-block-bootstrap 95% intervals are **[0.432,0.490] for NQ** and
**[0.440,0.495] for ES**. Most endpoint variants remain below 0.5, but ES
45–180m includes 0.5. The 2023–2026 era also includes 0.5 for both markets
(NQ 0.474 [0.443,0.502]; ES 0.492 [0.463,0.520]). The full-sample result is
supported but mild and era-dependent.

**Headline (and it overturned the stated prior expectation):**

1. **No microstructure anti-persistence at 1s.** The prior guess — sub-minute
   bid-ask-bounce anti-persistence — is NOT visible: micro H ≈ 0.50. 1s OHLCV
   closes are too coarse to resolve the bounce; that would need true tick/trade
   data (not entitled — Databento trades ≈ $1,140 for 16y NQ).

2. **Anti-persistence GROWS with scale.** H(τ) declines monotonically from ~0.50
   (seconds) through ~0.49 (minutes) to ~0.46 (tens of minutes to hourly). The
   raw coarse read (0.43) was **~40% finite-sample saturation artifact** — the RW
   control reads 0.466 there — but ~0.04 of genuine mean-reversion survives.

3. **It is corroborated across NQ↔ES and sampling frequency.** The 1s and 1m
   H(τ) bands agree to 0.003 in the overlap, and ES reproduces the full-sample
   NQ shape. These views share market dynamics and are not independent; they
   support the description without proving a universal structural law.

4. **This is a DIFFERENT object from the confirmed morning super-diffusion
   (the cone learning).** That result is anchored-at-open dispersion GROWTH vs
   elapsed time (a time-of-day, non-stationary statistic) and is super-diffusive
   early. A2 is the translation-invariant lag persistence averaged over the whole
   day, and is mildly anti-persistent at coarse lags. They are complementary:
   morning trend from the open, mean-reversion in the stationary intraday lag
   structure dominated by the rest of the day. Disentangling them by time of day
   is A3.

---

## What this means for the promising directions (B/C)

- The "direction filter" framing is the wrong ask (A1: early-session H is noisy;
  whole-session H is near-RW to mildly anti-persistent). The full-sample evidence
  supports **mild, era-dependent coarse-scale mean-reversion**, which points at
  **B1 (H → forward dispersion/range)** and
  **C1 (a low-H / mean-reversion vehicle)** rather than at momentum selection.
- Any 1s work must stay in the fill ≥ 0.90 / era ≥ 2015 regime and bias-correct.
- Sub-minute questions are blocked by data entitlement (need true tick).

## Open / next

- A3: H by time of day (reconcile the stationary mean-reversion here with the
  anchored-at-open morning super-diffusion).
- A4: multifractality H(q) (ghe_spectrum is built and tested).
- B1: does H (or the coarse-scale exponent) forecast forward realized range?
- Independent review of corrected runs EXP-0003/0004 is still pending.
