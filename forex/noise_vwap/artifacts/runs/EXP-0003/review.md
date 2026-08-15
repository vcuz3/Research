# EXP-0003 — session-anchor sweep (HYP-0003)

- Hypothesis: `experiments/hypotheses/HYP-0003.md` (preregistered; Amendment 1
  written after the first control failure and labelled as such)
- Builder: Claude (Opus 4.8), 2026-08-11
- Reproduce:
  `python -u -m forex.noise_vwap.tests.test_anchors` (17 invariants, must pass first)
  `python -u -m forex.noise_vwap.scripts.anchor_sweep`
- Artifacts: `report.txt`, `cells.csv`, `pooled.csv`, `summary.json`
- Code: `core/anchors.py`, `core/anchor_measure.py`, `scripts/anchor_sweep.py`

## Verdict

**HYP-0003 REJECTED.** The positive control detects NQ's real anchor; no
structural FX anchor beats its placebo family at the length where the control is
valid. **The arbitrary anchor was NOT the binding constraint on the FX
Noise-Area failure.** Combined with EXP-0001 (negative gross) and EXP-0002 (no
directional information), the Noise-Area family is closed for spot FX.

## Question

EXP-0002 established that the FX failure is an *absence of directional
information*, but attributed nothing. Every subsequent NQ band study varied the
band MATHEMATICS (cone, quantile, asymmetric, surround, Laplace — all rejected)
and left the ANCHOR fixed. On NQ the anchor is the 09:30 cash open, a real
auction boundary; on spot FX the `fxday` 17:15 ET anchor was chosen for
archive-defect reasons, not economic ones. If displacement is measured from an
arbitrary timestamp the reference price is itself noise, which would suppress the
construct even on a market with tradable intraday structure.

## Design

Only the session anchor moves. 24 hourly ET anchors at `HH:15` form the placebo
family (the null distribution — LEARNINGS §1 phase sweep, where the phase is the
anchor hour); four structural FX anchors and NQ's 09:30 open are the hypotheses,
each derived from its OWN timezone with real DST (LEARNINGS §8). Primary cell,
fixed in advance: `gate=ON`, `h=60min`, `embargo=1` (fill at `open[t+2]`),
matched fire rate, per-signal mean in band half-widths with a date-clustered t.

## Results

### Positive control (the validity gate)

| Arm | Anchor | n | mean/bw | t | rank by \|t\| | frac(placebo ≥) | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| **NQ @ 390 (native)** | RTH_OPEN 09:30 | 8,676 | **+0.0369** | **+3.68** | **2/19** | **0.056** | **PASS** |
| NQ @ 1425 (forced) | RTH_OPEN 09:30 | 25,957 | +0.0062 | +1.60 | 5/25 | 0.208 | FAIL |

The control PASSES at NQ's native 390-minute RTH length: placebo |t| median 0.98,
p90 2.60. The single placebo above RTH_OPEN is `ET0915` (t=+3.96) — 15 minutes
before the same open, i.e. not an independent placebo, so RTH_OPEN is effectively
rank 1.

**The same anchor on the same instrument scores +3.68 at 390 minutes and +1.60 at
1425.** Session length, not the anchor, is what the first execution was actually
varying. This is a measured result, not an assertion, and it is why Amendment 1
was necessary.

### FX

| Arm | Anchor | n | mean/bw | t | rank | frac(placebo ≥) | verdict |
|---|---|---:|---:|---:|---:|---:|---|
| FX @ 1425 | NY_ROLL | 223,205 | −0.0106 | −3.64 | 3/28 | 0.125 | FAIL |
| FX @ 1425 | TOK_OPEN | 187,261 | −0.0087 | −3.28 | 5/28 | 0.125 | FAIL |
| FX @ 1425 | LON_OPEN | 174,860 | −0.0033 | −1.41 | 16/28 | 0.542 | FAIL |
| FX @ 1425 | LON_FIX | 174,071 | −0.0017 | −0.57 | 26/28 | 0.917 | FAIL |
| **FX @ 390** | NY_ROLL | 29,974 | −0.0398 | −2.54 | 5/28 | 0.167 | FAIL |
| FX @ 390 | LON_FIX | 22,482 | −0.0268 | −2.06 | 7/28 | 0.208 | FAIL |
| FX @ 390 | TOK_OPEN | 30,905 | −0.0238 | −1.79 | 9/28 | 0.250 | FAIL |
| FX @ 390 | LON_OPEN | 30,441 | −0.0116 | −1.23 | 20/28 | 0.667 | FAIL |

## The decisive read: every anchor is negative

**24 of 24 FX placebos are negative at 1425; 23 of 24 at 390.** Every hour of the
day shows the same mild reversion. That is a pervasive property of the spot-FX
tape, not something any anchor is organising.

The cleanest way to see it is the ratio of the best structural anchor to the
family median effect:

| Family | best structural mean/bw | placebo median mean/bw | ratio |
|---|---:|---:|---:|
| NQ @ 390 | +0.0369 | +0.0018 | **≈ 21×** |
| FX @ 390 | −0.0398 | −0.0174 | ≈ 2.3× |
| FX @ 1425 | −0.0106 | −0.0043 | ≈ 2.5× |

A real anchor stands ~21× above the typical arbitrary hour. FX's best stands
~2×, which is what a mild pervasive effect plus sampling noise looks like. The
absolute effect sizes are comparable (NQ +0.037 vs FX −0.040) — the difference is
entirely in how much the anchor *distinguishes itself from an arbitrary hour*.

Note also the SIGN: every FX effect is reversion. Even taken at face value it
would say the momentum construct points the wrong way, consistent with EXP-0002's
weak AUD/NZD reversion, not that a better anchor rescues it.

## Sensitivity that goes the other way — reported, not adopted

The preregistered criterion 3 compares against all usable placebos. If placebos
are additionally filtered to `anchor_stability >= 0.98` (the floor the structural
anchors must clear — the two largest FX placebo |t| values, `ET1515` −4.66 and
`ET1615` −5.01, sit around the 17:00 roll break at stability 0.80), then:

- FX @ 1425: NY_ROLL frac = **0.045** and TOK_OPEN frac = **0.045** — both would
  PASS criterion 3.
- FX @ 390: NY_ROLL frac = 0.167, TOK_OPEN 0.250 — still FAIL.

**This does not change the verdict, for a reason that is structural rather than a
judgement call: the only arm where the stability-filtered test would pass is
@1425, and @1425 is precisely the construction whose own positive control
FAILS.** A result cannot be read from an arm that demonstrably cannot detect a
known-real anchor. At 390, where the control passes, FX fails under every variant
of the placebo filter. The filter was also not preregistered, and adopting a
post-hoc filter that flips a verdict is the failure mode this workspace's rules
exist to prevent.

## Coverage confound (LEARNINGS §2)

NY_ROLL carries 223,205 signals at 1425 against a placebo median of 174,382
(+28%), because the 17:15 session boundary aligns with the real FX week so fewer
sessions fail the 90%-completeness filter. Across placebos `corr(n_signals, |t|)
= +0.306`, so part of NY_ROLL's larger |t| is simply more observations at equal
effect size. At 390 its n is unremarkable (29,974 vs median 30,317) and its |t|
falls to 2.54 — consistent with the coverage explanation.

## Two defects found and fixed during the run

1. **`Series.astype("int64")` returns the integer in the dtype's UNIT, and this
   project mixes units in one code path.** `forex/data/**` is stored as
   `datetime64[us]`; `futures/nq/data/**` is `datetime64[ns, UTC]`. Both hold
   exact whole-minute timestamps (verified: 0 of 5.54M EURUSD rows have a nonzero
   second or microsecond) — only the storage unit differs, so this is not a
   data-precision issue. A hard-coded `// 60_000_000_000` is therefore correct for
   the NQ control and wrong by 1000× for FX, collapsing 576,000 distinct minutes
   onto 577 colliding values. That is worse than a single-source bug because it is
   silent and instrument-dependent: the same function was right on the control and
   wrong on the subject. Fixed by dividing by a `pd.Timedelta` (exact at any
   unit); pinned by invariant tests on uniqueness and the mfo formula.
2. **Exploding cluster-t on degenerate cells.** A placebo with only a few distinct
   date clusters produced |t| = 1.4e16. Added a small-cluster guard (≥100 signals,
   ≥30 clusters) returning NaN, and — critically — made the verdict DROP NaN
   placebos explicitly with a reported count, because `NaN >= x` is False and a
   NaN placebo would otherwise count as "did not beat the real anchor" and make
   the test easier to pass (LEARNINGS §5).

## Data provenance

The canonical `forex/data/clean/*_1m_clean.parquet` were exclusively locked by
running Jupyter kernels (the `forex/exploration_6` gotcha). The run used the
archived price-only files, whose SHA-256 was verified equal to the manifest's
`spot_input_sha256` for all four pairs, with row counts, first/last timestamp,
duplicate count, ordering and gap count all matching. No volume is used anywhere
in this study.

## What this does and does not establish

- It DOES close the anchor explanation for the FX Noise-Area NO-GO, with a
  positive control proving the diagnostic can see a real anchor.
- It DOES quantify that session LENGTH / decision universe matters more than the
  anchor for the NQ construct (+3.68 → +1.60 on the same anchor).
- It does NOT test any tradable rule: this is exit-neutral forward-return
  information, no costs, no exits. Nothing here is a strategy result.
- It does NOT rule out that some *other* boundary (a scheduled release, a fixing
  auction with published flow) carries information. It rules out that a
  liquidity/value-date session boundary does.
- No Null C was spent (gate rule: the construct's real pass already failed its
  primary metric in EXP-0001).

## Independent review

- Reviewer: pending
- Status: pending
