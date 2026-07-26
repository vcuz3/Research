# EXP-0032 Results Discussion (Phase 1)

- Hypothesis: `HYP-0022` — a causal intraday-ATR stop buffer is a systematic
  replacement for the arbitrary 1m close-confirmation wick filter (EXP-0031).
- Status: Phase 1 completed (exploratory sweep + calibration + matched-width
  control). Phase 2 (Null C + ES) gated on this result and a user decision.
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: zero-eligible-day one-contract daily net Sharpe at 0.5 tick/side
  + fees, common 3,628-session NQ sample, vs the close-confirmed continuous stop
  (0.9226) and the k=0 first-touch anchor (0.8827).

## Construction

Exit on the first **1s** touch of `stop = max(upper, vwap) − k·ATR_N` (long;
`+` for shorts), `ATR_N` a causal rolling mean of 1-min True Range over the last
`N` completed minutes; the stop floats (recomputed each minute, no ratchet).
Entries unchanged. `k = 0` reproduces the EXP-0031 first-touch band stop
(kernel parity proved in `tests/test_atr_buffer.py`).

## Calibration — what tolerance does close-confirmation imply?

From the close-confirmed holds, the wicks it tolerates (dip below the band, close
back above) reach, in ATR_N units:

| N | tolerated-wick p50 | p90 | p95 | median ATR_N (pts) |
|---:|---:|---:|---:|---:|
| 5 | 0.30 | 0.79 | 1.02 | 2.14 |
| 14 | 0.29 | 0.81 | 1.28 | 4.27 |
| 30 | 0.32 | 0.99 | 1.30 | 4.23 |

So close-confirmation's implicit tolerance is ≈0.8–1.0 ATR at the 90th percentile
— a systematic buffer around `k ≈ 0.8` would filter most of the same wicks. Note
the monetized optimum below is **wider** (`k ≈ 1.5`), which matters (see caveats).

## Sweep (0.5 tick/side, common 3,628 sessions)

| variant | trades | gross pt/trade | worst pt | daily Sharpe | vol-tgt Sharpe | vol-tgt maxDD |
|---|---:|---:|---:|---:|---:|---:|
| close-confirmed (incumbent) | 4,209 | 3.509 | −191.8 | 0.9226 | 1.184 | −0.181 |
| k=0 first-touch (anchor) | 4,663 | 3.065 | −163.3 | 0.8827 | 1.090 | −0.244 |
| **N20 k1.5 (best)** | 3,377 | 5.030 | −237.8 | **1.0523** | **1.331** | −0.190 |
| N10 k1.5 | 3,396 | 4.877 | −224.9 | 1.0358 | 1.280 | −0.187 |
| N30 k1.5 | 3,375 | 4.851 | −212.8 | 1.0141 | 1.271 | −0.206 |
| fixed-buffer, matched width (6.375 pt) | 3,456 | 4.368 | −164.9 | 0.9675 | 1.207 | −0.269 |

`k = 1.5` is the best `k` for **every** `N` (5→30), so the peak is not a single-cell
fluke. The `k`-surface is otherwise non-monotone (e.g. N20: k0.75=0.965, k1.0=0.900,
k1.5=1.052) — a caution flag.

## Two Phase-1 questions answered

1. **Does anything beat close-confirmation?** Yes. Best `N20 k1.5` daily Sharpe
   **1.052 vs 0.923** (+0.130), vol-targeted **1.331 vs 1.184** (+0.147), with
   vol-targeted maxDD no worse (−0.190 vs −0.181).
2. **Is the vol-scaling load-bearing?** Apparently yes. At matched width/trade
   count (fixed 6.375-pt buffer, 3,456 trades ≈ the scaled cell's 3,377), the fixed
   buffer reaches only 0.9675 while the ATR-scaled cell reaches 1.0523 — a
   **+0.085 scaling uplift** over pure width. Decomposition of the +0.130:
   ≈+0.045 is just a wider stop (fixed beats close-confirmation too), ≈+0.085 is
   the volatility scaling.

## Caveats — why this is not yet a finding

This is a **looser-stop family**, the exact configuration Null C has repeatedly
exposed as a variance amplifier in this project (EXP-0010, EXP-0012, KAMA):

- Trades fall 4,663 → 3,377 and gross/trade rises 3.07 → 5.03 as `k` grows — the
  "fewer trades → higher Sharpe" signature MEMORY flags as machinery-until-proven.
- The **left tail fattens**: worst single trade −163 (k0) → −238 (N20 k1.5). The
  ATR-scaled buffer's tail is also worse than the *fixed* buffer of matched width
  (−238 vs −165) — vol-scaling widens the stop most in high vol, permitting larger
  adverse excursions. Daily/vol-targeted Sharpe partly hides this.
- The monetized optimum (`k ≈ 1.5` ≈ 6–9 pts) is **wider than the ~0.8–1.0 ATR
  that merely filters the tolerated wicks**, so part of the gain is "give winners
  more room" (trailing-stop looseness), not purely a systematic wick filter — the
  project's "looseness is load-bearing" theme, which Null C must adjudicate.

## Phase 1 gate

Phase 1 cleared the exploratory gate: the intraday-ATR buffer beat close-confirmation
on daily and vol-targeted Sharpe (best N20_k1.5 +0.130), the scaling contributed
≈+0.085 beyond matched width, the uplift held/strengthened in recent eras
(≥2024 +0.191, ≥2025 +0.155, last 252d +0.286; only CY2025 soft at −0.061), and it
transferred to ES (+0.105 vs-cc). Per the preregistered plan this warranted Phase 2.

## Phase 2 — Null C + ES: REJECT

**ES transfer (1m):** `uplift_vs_cc` NQ +0.132 → ES +0.105 (transfers);
`uplift_scaling` NQ +0.085 → ES +0.032 (same sign, weaker).

**Null C (30 draws, path-preserving return shuffle; diffusivity gate passes,
real 0.25 = null 0.25):**

| uplift | real | null center | null sd | z | frac(null≥real) |
|---|---:|---:|---:|---:|---:|
| vs close-confirmed | +0.132 | **+0.073** | 0.091 | 0.65 | 0.26 |
| **scaling vs fixed (decisive)** | +0.085 | **+0.042** | 0.096 | 0.45 | **0.40** |

Both null distributions **center positive** with the real value sitting well inside
them. The decisive `uplift_scaling` null centers at +0.042 (half the real +0.085) and
40% of null draws beat the real — the vol-scaling advantage over a matched-width fixed
buffer is **reproduced on pure noise**. This is machinery, not path structure: the
return shuffle preserves each session's range magnitude, so a vol-adaptive stop width
is mechanically better than a fixed one *regardless of whether the path carries signal*.
`uplift_vs_cc` is the plain looser-stop variance amplifier (null center +0.073, real
z=0.65). Same signature as EXP-0019 (vol-conditional cadence) and the EXP-0010/0012
looser-stop rejections: whipsaw/vol-geometry is a property Null C preserves, so noise
reproduces it and then some.

## Verdict: NO-GO

The intraday-ATR stop buffer is a **more principled, better-motivated** construction
than the arbitrary close-confirmation wick filter — it beats it in-sample (+0.130),
holds in recent eras, and transfers to ES — but the improvement does **not** survive
Null C: it is variance amplification from a looser, volatility-adaptive stop width,
which the path-preserving null reproduces (both uplifts' nulls center positive, real
inside the band). The vol-scaling carries no real intraday path information beyond a
mechanical width/vol-adaptivity dial. Retain the deployed close-confirmed continuous
stop. This closes the "systematic buffer replaces the wick mechanic" thread on
consumed history; only future/shadow data could revisit it cleanly.

Reproduce Phase 2: `python -u -m futures.nq.noise_vwap.scripts.hyp_0022_nullc real`
and `... .hyp_0022_nullc null 30`. Era check:
`python -u -m futures.nq.noise_vwap.scripts.hyp_0022_era`.

## Reproduction

- Phase 1: `python -u -m futures.nq.noise_vwap.scripts.hyp_0022_atr_buffer`
- Era: `python -u -m futures.nq.noise_vwap.scripts.hyp_0022_era`
- Phase 2: `python -u -m futures.nq.noise_vwap.scripts.hyp_0022_nullc {real|null 30}`
- Engine: `core/atr_buffer.py` (isolated kernel + 1m runner; `first_touch.py`
  untouched); `tests/test_atr_buffer.py` (3 tests). Artifacts: `sweep.csv`,
  `report.json`, `era_sharpe.csv`, `nullc_draws.csv`, `nullc_report.json`.

## Independent review

- Review status: reviewed (builder self-review, both models pending)
- Objections: none outstanding — Null C is a clean REJECT on the decisive
  scaling-vs-fixed metric (null centers positive, real inside the band).
- Verdict: NO-GO. Intraday-ATR stop buffer is better-motivated than the wick
  mechanic and beats it in-sample / recently / on ES, but the uplift is
  Null-C-machinery (looser + vol-adaptive stop width), not real path structure.
  Retain the close-confirmed continuous stop.
