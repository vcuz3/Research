# FINDINGS — Run-persistence reversion (FX majors)

Current verdict: **provisional / QUALIFIED** (updated after EXP-0002). A
statistically robust short-horizon reversion signal exists in the
Frankfurt-open→NY-noon window and is **durable and cross-pair transferable**.
Its *best predictor*, however, is **pair- and era-specific**: run-length /
concentration on EURUSD/GBPUSD (and mainly in 2011–2015), but raw displacement
magnitude on AUDUSD/NZDUSD. HYP-0001's specific "concentration not magnitude"
claim is therefore **not a durable, universal law** — see EXP-0002/EXP-0003. The
single reversion signal significant in BOTH the full and recent (≥2020) era on
ALL four pairs is the **unconditional fold** (fade the run, unweighted; recent
cl-t +3.2..+4.1, signflip p=0.005, ~half full-sample amplitude). Both
conditioners — concentration and displacement magnitude — are dead post-2020 on
every pair. Intended as a conditioning signal for another strategy (fast-alpha
style), not a standalone cost-viable edge. Not holdout-validated (all history
inspected).

## Question and scope

- Signal: after a short sequence of same-direction 5m candles, does price
  mean-revert over the next 5–15 min, and is the run length a proxy for the
  move's magnitude or an independent (concentration) signal?
- Instruments: EURUSD, GBPUSD 1m clean archives 2011-07-19 → 2026-07-17,
  resampled to 5m. ~457k (EUR) / ~460k (GBP) in-window events.
- Window: 08:00 Europe/Berlin (Frankfurt open) → 12:00 America/New_York, taken
  from each bar's OWN local time (DST-correct), weekdays only.
- Reproduce: `python run_reversion_core.py; python run_persistence.py`.

## Core result (EXP-0001)

Folded 15m reversion `−sign·fwd_log_return`, session-day cluster-robust,
causal-vol-normalised predictors:

- Reversion is real and null-validated: mean fold +0.097 pip (EUR) / +0.103 pip
  (GBP), ~10σ above the signflip null, p = 0.005 (1/201 floor).
- Magnitude-proxy hypothesis REJECTED. Causal joint `y ~ dsig + signed_count`:
  count survives (EUR b=−0.068 t=−5.3; GBP b=−0.033 t=−2.6); displacement
  collapses (EUR +0.022 t=+1.7 momentum sign; GBP −0.011 t=−0.9).
- Continuous refinement: max-bar share `max|bar|/|disp|` is the best univariate
  predictor (EUR t=−4.6, GBP t=−2.4), the continuous form of count
  (corr=−0.85). Per-bar move size irrelevant (t≈0). Monotone EUR quintile: even
  grind (share≈0.47) → +0.17 pip reversion; single-bar lunge (share=1.0) →
  −0.03 pip momentum. GBP same shape, weaker.

Mechanism: grind reverts, lunge continues — HOW the move accumulated, not its
size. Consistent with the workspace "sharp = continuation, grind = reversion"
theme.

## Controls and traps handled

- Shared-close artifact (LEARNINGS §6): open==prev_close ≈ 0.9965; next-open
  entry does not separate windows, so paired 1-min-grain embargo + signflip null
  (shares decision path, destroys only direction) are the defence.
- Unit trap: FX data is `datetime64[us]`; unit-safe target construction after an
  ns divisor bug invalidated two pre-fix tables.
- Causal (trailing-vol) standardisation, not full-sample z (lookahead).
- Multiple-testing: horse race + signflip null were the pre-specified
  confirmatory tests; headline t's are discovery-inflated.

## Stability & transfer (EXP-0002)

Ran three checks. They split EXP-0001's bundled claim into (i) raw reversion
exists — survives everywhere; (ii) its driver is concentration not magnitude —
fails out-of-window.

- **Era (EUR/GBP).** Raw fold > 0 in 15/16 (EUR) and 16/16 (GBP) years — durable.
  But the concentration/count coefficient is **front-loaded and decays**: EUR
  count-t = −3.8/−3.2/−3.2/−2.3/−2.1 in 2011–2015, →≈−1 (2016–19), →noise
  (|t|<1) from 2020. Flat per-year n, so decay is real, not power. The pooled
  ~10σ / count-t=−8.3 headline is dominated by 2011–2015.
- **Time-of-day (NY hour).** Raw reversion is broad (fold>0 nearly every hour).
  The concentration effect concentrates at **NY 08h = 14h Berlin** (London/NY
  overlap): EUR count-t=−2.8, GBP −2.7. NY 01h/11h fold spikes are low-n DST
  edges, not signal.
- **Cross-pair (AUDUSD/NZDUSD).** Raw reversion TRANSFERS (fold +0.117/+0.108
  pip, signflip p=0.005). But the mechanism **inverts**: displacement/magnitude
  reverts (disp-t=−3.9/−5.7) while count is dead/wrong-signed (AUD b=+0.002
  null p=0.56; NZD b=+0.031 POSITIVE null p=0.98). Opposite of EUR/GBP.

Takeaway: the only pair- and era-universal quantity is the **unconditional
fold** (fade the run, unweighted). NEITHER conditioner is universal — displacement
magnitude loads only on AUD/NZD (pooled; not yet era-tested), concentration only
on EUR/GBP (and only 2011–2015). They are mirror images, not one base lever. On
EUR/GBP displacement is inert (univariate t=+0.6). Do not port either conditioner
across pairs; each needs its own pair×era validation.

## Era decomposition — what survives recently (EXP-0003)

FULL (2011-2026) vs RECENT (2020-2026), all four pairs. Metric: unconditional
fold + signflip null, plus the joint count/displacement horse race.

- **Only the unconditional fold survives into the recent era, on every pair.**
  RECENT: EUR +0.055 pip (cl-t +4.1), GBP +0.059 (+3.6), AUD +0.073 (+4.0),
  NZD +0.059 (+3.2) — all signflip p=0.005. ~half the full-sample amplitude
  (~0.10-0.12 pip) but clearly alive.
- **Both conditioners are dead post-2020, on every pair.** RECENT joint: count
  t = −0.4/+0.1/−0.3/+0.2; displacement t = −1.6/−1.4/−1.2/−1.4 (right sign,
  sub-threshold). The full-sample conditioner edges (concentration EUR/GBP,
  magnitude AUD/NZD) are entirely pre-2020.

**Deployable answer:** the reversion signal is the *unconditional fold* of a
same-direction 5m run in the Frankfurt→NY window — robust across all four pairs
and full+recent eras. Do NOT weight it by run-length or displacement magnitude
for live use; both refinements have no recent edge.

## Open / next

- Independent Codex replication of the three scripts.
- Future-only holdout plan (all history now inspected).
- Optional: characterise the base-fold amplitude decay (≈0.11→0.06 pip) and its
  half-life vs the reopen spread, to size its usefulness as a conditioner.

## Artifacts

- `artifacts/runs/EXP-0001/reversion_core_null.txt` — joint regression + null.
- `artifacts/runs/EXP-0001/persistence_horserace.txt` — continuous refinement.
- `artifacts/runs/EXP-0001/review.md` — full discussion.
- `artifacts/runs/EXP-0002/stability_transfer.txt` — era/time-of-day/transfer.
- `artifacts/runs/EXP-0002/review.md` — stability discussion.
- `artifacts/runs/EXP-0003/era_reversion_table.txt` — full-vs-recent per pair.
- `artifacts/runs/EXP-0003/review.md` — era-decomposition discussion.
- `experiments/hypotheses/HYP-0001.md` — pre-registered hypothesis/kill test.
