# EXP-0002 Results Discussion

- Hypothesis: `HYP-0002` — Hurst term structure across timescale (micro vs meso)
- Status: completed (descriptive / measurement)
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned (independent review pending)
- Primary metric: control-corrected H(τ) and per-band H; 1s/1m overlap; NQ↔ES transfer
- Kill test: control-corrected H(τ) flat at 0.5, OR coarse anti-persistence vanishes after RW control

## Result versus hypothesis

Partially confirmed, and the stated prior expectation was overturned:
- Micro (1–8 s) H ≈ 0.503 — NO microstructure anti-persistence at 1s (1s OHLCV
  cannot resolve the bid-ask bounce; true-tick data would be needed).
- H(τ) declines monotonically with scale; coarse (30–180 min) H = 0.462 (NQ) /
  0.468 (ES), anti-persistent, after subtracting the RW control.
- The scale structure is real (does not vanish under control) but MILD.

## Gross, net, baseline, and null comparison

Baseline = matched-length H=0.5 random-walk control (300 draws). It reads H=0.466
at the coarse band, so ~40% of the raw coarse anti-persistence (raw 0.428) is a
finite-sample structure-function saturation artifact; ~0.04 of genuine
mean-reversion survives. Micro/meso controls sit at ≈0.50 → those bands are
artifact-free.

## Regimes, sensitivity, and alternative explanations

- Cross-frequency: 1s and 1m H(τ) agree to 0.003 in the 1–60 min overlap →
  validates the 1s curve with independent data.
- Cross-market: ES reproduces the NQ shape → structural, not machinery.
- Distinct object from the confirmed anchored-at-open morning super-diffusion
  (cone learning); that is time-of-day dispersion growth (A3 target), this is the
  stationary lag structure averaged over the day.
- Rule 9a: fill ≥ 0.90, era ≥ 2015 (228 1s sessions); forward-fill deflation of
  the τ=1–2 s points is the main residual caveat, small at high fill.

## Evidence

`a2_summary.txt`, `scale_curve.csv` (incl. RW_ctrl rows), `meta.json`.

## Reviewer verdict

Independent review (Claude, 2026-07-22) of the user's correction run EXP-0004:
ACCEPT with refinements. The moving-block bootstrap, endpoint-sensitivity, and
era-stability additions are correct and appropriately TEMPER the finding: coarse
(30-180m) anti-persistence CIs exclude 0.5 at full sample (NQ 0.462 [0.432,0.490],
ES 0.468 [0.440,0.495]) but STRADDLE 0.5 in 2023-2026 (NQ [0.443,0.502], ES
[0.463,0.520]) and for the ES 45-180m endpoint — so it is real full-sample, mild,
and NOT robust in the recent (deployment-relevant) era.

Refinements (not blocking):
1. Micro-band CI [0.501,0.506] excludes 0.5 upward, but forward-fill is a
   systematic BIAS the session bootstrap cannot see (it captures variance only),
   so that CI understates uncertainty. Verified: dropping tau=1-2s moves micro H
   0.503->0.493 in fill 0.90-0.97 sessions (fill inflation, predicted direction);
   in fill>=0.97 sessions it holds ~0.502. Read micro as ~0.50 / unresolved, not
   ">0.5". Suggest computing the micro band from tau>=3-5s or fill>=0.97 only.
2. block=5 bootstrap is well-specified for the CONTIGUOUS 1m full-history bands
   (=1 week) but not for the stratified-random 1s sample (5 consecutive rows span
   months); use block=1 (iid) for the 1s bands, or note it.
3. ~7 bands x endpoints x eras tested vs 0.5 with no family adjustment; the
   era/endpoint straddles already serve as the robustness check, but note the
   family when reading "CI excludes 0.5" as significance.
