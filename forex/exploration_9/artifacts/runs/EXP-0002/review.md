# EXP-0002 Results Discussion

- Hypothesis: `HYP-0001` — Run-length reversion is a grind-vs-lunge concentration effect, not magnitude
- Status: completed
- Builder: Claude
- Reviewer: unassigned
- Primary metric: per-year & per-NY-hour fold + count-coef cluster-t; cross-pair signflip null
- Kill test: (a) reversion mean-fold not distinguishable from the signflip null (real ≤ null p > 0.05) ⇒ KILL; (b) displacement subsumes count/max-share in the causal joint regression ⇒ the "persistence, not magnitude" claim is KILLED and it reduces to ordinary magnitude reversion.

## Result versus hypothesis

Three stability/transfer checks. They separate two distinct claims that EXP-0001
had bundled: (i) **raw short-horizon reversion exists** and (ii) **its driver is
concentration, not magnitude**. (i) survives everywhere; (ii) does NOT — it is
era-decayed on EUR/GBP and inverts on the commodity pairs. HYP-0001 is
downgraded from "accepted" to "qualified / partly falsified out-of-window."

## Gross, net, baseline, and null comparison

Signal study; comparison is the signflip null (cross-pair) and cluster-robust t
(per-year, per-hour). See `stability_transfer.txt`.

- **(1) Era stability (EUR/GBP).** Raw folded 15m reversion is durable: fold > 0
  in **15/16** years (EUR) and **16/16** (GBP). BUT the count/concentration
  coefficient — the actual HYP-0001 claim — is **front-loaded and decays**:
  EUR count-t = −3.8, −3.2, −3.2, −2.3, −2.1 in 2011–2015, fading to ≈−1 in
  2016–2019 and to noise (|t|<1, occasionally wrong-signed) from 2020 onward.
  GBP is the same shape. Per-year n (~30k) and sessions (~259) are flat across
  years, so this is decay, not a power artifact.
- **(3) Time-of-day (NY wall-clock hour).** Raw fold is positive at nearly every
  hour (one negative EUR cell at 03h), so reversion is broad, not a single-slot
  artifact. The count effect concentrates around **NY 08h (= 14h Berlin, London/
  NY overlap / US pre-open)**: EUR count-t=−2.8 (b=−0.132), GBP count-t=−2.7
  (b=−0.308). NY 01h/11h fold spikes are edge-of-window/low-n (DST boundary),
  not to be read as signal.
- **(2) Cross-pair transfer (AUDUSD, NZDUSD).** Raw reversion TRANSFERS
  (meanfold +0.117 / +0.108 pip, signflip p=0.005 both; fold>0 in 16/16 and
  13/16 years). But the mechanism **inverts**: displacement/MAGNITUDE reverts
  (AUD disp-t=−3.9, NZD disp-t=−5.7) while the count/concentration term is dead
  or wrong-signed (AUD count b=+0.002 t=+0.1, null p=0.56; NZD count b=+0.031
  t=+2.0 POSITIVE, null p=0.98). The exact opposite of EUR/GBP, where
  displacement collapsed and count survived.

## Regimes, sensitivity, and alternative explanations

- The one universal, era-stable, transferable fact is plain **short-horizon
  reversion** in this window. The "how it accumulated" (concentration) channel
  is a EUR/GBP-and-early-sample phenomenon; on antipodean pairs the reverting
  quantity is the raw displacement.
- Plausible reads: (a) the concentration signal was a real microstructure
  feature that arbitraged away / changed as EUR/GBP execution modernised
  post-2015 (algo/last-look, MiFID II 2018); (b) EUR/GBP vs AUD/NZD differ
  because the Frankfurt→NY window is the HOME/active session for EUR/GBP but an
  off-peak session for AUD/NZD (Sydney/Asia pairs), so their in-window flow
  composition differs. Not disentangled here.
- Caution: pooled EXP-0001 significance (~10σ, count-t=−8.3) is dominated by the
  2011–2015 sub-sample; do not read it as a currently-live effect.

## Artifact and implementation risks

- Same pipeline/controls as EXP-0001 (causal vol-norm, session clustering,
  µs-safe targets, signflip null). Per-year/per-hour cells use the identical
  `cell()` path; min-n guard = 500 (all reported cells clear it).
- Cross-pair G (sessions) ≈ 3.8–3.9k = full-sample NY days, consistent with the
  per-year G≈259 × ~15 years. No cluster-count anomaly.
- AUD/NZD padded-weekend-bar risk (LEARNINGS) is moot: window is weekday-only.

## Builder interpretation

The user asked for a statistically robust signal to feed another strategy. What
is robust and transferable is **short-horizon reversion in the Frankfurt→NY
window** — but its best PREDICTOR is pair-specific: concentration/run-length on
EUR/GBP (and even there mainly 2011–2015, peaking at NY 08h), raw displacement
magnitude on AUD/NZD. HYP-0001's specific "concentration not magnitude" claim is
therefore **not a durable, cross-pair law** — it is a EUR/GBP early-sample
feature. Correction to an earlier overstatement: displacement magnitude is NOT
the universal alternative — it is inert on EUR/GBP (univariate t=+0.6, joint
t=+1.7/-0.9) and loads only on AUD/NZD (pooled; not yet era-tested). The single
pair+era-universal quantity is the UNCONDITIONAL fold (fade the run, unweighted);
magnitude and concentration are mirror-image, pair-specific conditioners that
must each be validated per pair×era before use.

## Independent review

- Review status: builder-complete; independent (Codex) review recommended
- Objections: pending
- Verdict: HYP-0001 QUALIFIED — raw reversion robust/transferable; concentration
  mechanism era-decayed (EUR/GBP) and non-transferable (inverts on AUD/NZD).

## Promotion decision

- `reports/FINDINGS.md`: updated with era/time-of-day/transfer results.
- `MEMORY.md`: updated — verdict qualified; concentration is not a durable law.
- Shared `LEARNINGS.md`: candidate note — "raw short-horizon FX reversion
  transfers; its best predictor (concentration vs magnitude) is pair/era
  specific — do not port the run-length mechanism across pairs." Hold until
  independent replication.
