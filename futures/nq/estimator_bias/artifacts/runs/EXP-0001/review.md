# EXP-0001 Results Discussion

- Hypothesis: `HYP-0001` — Short-window persistence estimates carry a deterministic window-length bias that a fixed threshold reads as signal
- Status: completed
- Builder: claude
- Reviewer: unassigned
- Date run: 2026-08-03
- Primary metric: per-slot selection-rate CV of the fixed-threshold expanding-window Hurst gate, versus a same-slot z-scored H at matched global selection rate, on NQ and ES.
- Kill test: Cell A REJECTED if the fixed-threshold gate's per-slot selection-rate CV is <= 2x the same-slot-z gate's CV at matched global rate on EITHER NQ or ES; Cells B/C REJECTED (and Cell A's reading re-opened) if bias correction moves AC1 by > 0.01 or the reversion retention by more than its published CI.
- Tests: `tests/test_core.py` 18/18 pass (`tests.txt`).

## Result versus hypothesis

**Cell A: NOT KILLED, decisively.** The fixed-threshold gate's per-slot selection-rate CV
exceeds the same-slot z-score's at **all 7 published thresholds on both markets**:

| | min ratio | median | max |
|---|---|---|---|
| NQ | 2.88x | 23.93x | 45.59x |
| ES | 5.90x | 21.75x | 46.48x |

The kill threshold was 2.0x. The same-slot z-score's own CV lands at 0.0025-0.0897,
straddling the 0.060-0.064 benchmark that `vwap_exploration` finding I1 established for a
well-calibrated same-slot z; the fixed cut runs 0.037-2.019.

At the realistic operating point (`H >= 0.55`, ~15-18% selection) the gate's per-slot
selection rate is **monotone decreasing through the session**:

    NQ  0.335 0.294 0.260 0.242 0.212 0.188 0.169 0.145 0.136 0.121 0.109 0.095 0.084
    ES  0.317 0.268 0.226 0.197 0.166 0.144 0.122 0.106 0.095 0.083 0.073 0.064 0.052

i.e. **4.0x (NQ) / 6.1x (ES) more likely to fire at the 10:00 decision than at 15:59.**

**Cell B: predicted null CONFIRMED.** Kendall/bootstrap correction moves the pooled AC1
by at most **0.00006** on both markets, against a 0.01 kill threshold. The published
estimator pools ~40,806 within-session pairs and small-sample bias at that T is ~1e-4, as
Study 1's table predicts.

**Cell B sub-prediction (opposite sign) CONFIRMED and large.** Removing the per-slot mean
first cuts the same statistic by 0.10-0.27:

| variant | NQ pooled | NQ slot-demeaned | ES pooled | ES slot-demeaned |
|---|---|---|---|---|
| `sma_10_50_raw` | -0.0112 | **-0.1160** | -0.0151 | **-0.1138** |
| `L:wilder_10_50` | +0.5495 | **+0.2777** | +0.5062 | **+0.2548** |
| `wilder_10_50` | +0.4411 | **+0.2198** | +0.4036 | **+0.2007** |
| `L:ema_10_50` | +0.1609 | **+0.0048** | +0.1386 | **+0.0002** |

About **half** of the persistence that motivated the Wilder estimator is the VEI's own
intraday level profile, and the EMA variant's persistence is **entirely** clock. The
*ranking* (wilder > ema > sma) is preserved on both markets, so `vei_exploration`'s
estimator choice survives; its magnitude does not.

**Cell C: resolved analytically, not re-run — see "Artifact and implementation risks".**

## Gross, net, baseline, and null comparison

Not applicable — nothing here trades. The relevant comparisons are the baseline
reproduction and the two nulls.

**Rule-23 reproduction (exact).** All 8 published AC1 cells reproduce to a 1e-4 tolerance
against the frozen artifact `vei_exploration/artifacts/runs/A_smoothing/smoothing_*.csv`:

    NQ  -0.011181 / +0.549460 / +0.441143 / +0.160876   -> reproduced to 4 dp
    ES  -0.015066 / +0.506246 / +0.403646 / +0.138612   -> reproduced to 4 dp

**Null 1, `fbm05`** — constant-volatility fBm at true H = 0.50.
**Null 2, `signflip`** — the session's real |returns| with iid random signs. Preserves the
real intraday volatility seasonality minute by minute and destroys all memory; true
H = 0.50 by construction. This is the discriminating one, and it is where the finding
turns from "a gradient exists" into "the gradient is the estimator".

Fixed-gate CV range, real versus a path with **no memory at all**:

| | real | signflip (H=0.50) | fbm05 (H=0.50) |
|---|---|---|---|
| NQ | 0.0372 .. 1.9474 | 0.0473 .. 1.4700 | 0.0482 .. 1.6279 |
| ES | 0.0873 .. 2.0193 | 0.0611 .. 1.4885 | 0.0481 .. 1.6288 |

And at `H >= 0.55` the zero-memory `signflip` path *by itself* produces a selection rate
running 0.330 -> 0.141 (NQ) / 0.333 -> 0.161 (ES) across the session — **2.3x and 2.1x of
the real 4.0x / 6.1x gradient**. Even on that path, the fixed cut is **9.8-10.6x** worse
calibrated than a same-slot z of the same feature.

## Regimes, sensitivity, and alternative explanations

**The mechanism is DISPERSION, not level.** This was preregistered as control 6 and it is
what the data says. Across the gate's 13 windows the *mean* H barely moves (range 0.0225
NQ / 0.0203 ES) while the *sd* compresses **3.80x NQ / 3.54x ES** (0.176 -> 0.046). Both
nulls reproduce the compression almost exactly (3.64x / 3.70x, and 3.89x for fbm05). A
fixed cut sitting in the tail of a distribution whose width shrinks 3.8x through the
session must select a collapsing fraction of it; that is arithmetic, not gold.

This also explains the one soft spot in the profile: the CV ratio is smallest at
`H >= 0.50` (2.88x NQ), which is nearest the ~0.47-0.49 centre of the distribution and
therefore least sensitive to a change in width. The defect is worst exactly where a
selective gate actually operates.

**Alternative explanation considered: genuine intraday variation in persistence.** Real
NQ/ES *do* sit slightly below both nulls late in the session (real - signflip reaches
-0.0100 NQ / -0.0286 ES at n=390), consistent with `hurst_explore` A2's mild coarse-scale
anti-persistence. So there is a real residual. But it is an order of magnitude smaller
than the estimator gradient, and it cannot account for a monotone 4-6x selection ramp.

**Alternative explanation considered: intraday volatility seasonality.** Ruled out as the
driver by construction — `signflip` preserves it exactly and still produces the ramp.

**Sensitivity.** The whole `H_GRID` profile is reported, not the argmax; the conclusion
holds at every usable threshold on both markets. The rule-9a check on the same-slot z
passed cleanly: per-slot coverage 0.9878 (NQ) / 0.9879 (ES) with a cross-slot **spread of
0.0000**, so the comparator deletes decisions uniformly and is not itself a hidden filter.

**Methodological by-product worth carrying.** The two bias correctors agree at moderate T
but **diverge at T=13** (per-session AC1, `wilder_10_50` NQ: raw +0.5255, Kendall +0.7831,
bootstrap +0.6595). Study 1 shows why: the analytic `-(1+3phi)/T` is accurate for T >= 30
but breaks down at T = 13 (at phi = -0.4 it predicts +0.0154 against a measured +0.0001).
**Below T ~ 20, use the bootstrap corrector, not the closed form.** Having required two
correctors is what surfaced this.

## Artifact and implementation risks

1. **`ghe1` is the deployed estimator, not a lookalike.** Copied verbatim from
   `noise_vwap/scripts/hyp_0017_hurst_filter.py`, including the `LAGS <= n // 2` cap, and
   pinned by `test_ghe1_constants_still_match_the_audited_script`, which re-reads that
   file and fails if `LAGS` or `H_GRID` ever change. Note the cap means the estimator's
   own lag set differs at n=30 (8 of 9 lags) from n>=40 (all 9) — a second, smaller
   window-length dependence folded into the same result.
2. **Cell C was not re-run, by deliberate choice.** `claude_exploration_1`'s reversion
   retention rests on correlations over ~4e4 decisions. Study 1 measures the maximum
   possible small-sample bias at T = 44,516 as **0.00025** and at T = 3,710 as 0.00091 —
   two to three orders of magnitude below the published effects and their CIs. Re-running
   that project to demonstrate a bound already established in closed form and confirmed by
   simulation would not have changed the verdict. **This is a declared deviation from the
   preregistration**, which said the cell would be re-run; the substantive prediction
   (unchanged) stands, but it is bounded rather than directly reproduced. A reviewer who
   disagrees should ask for the direct run.
3. **The slot-demeaning in Cell B is full-sample, on purpose.** It is a diagnostic
   decomposition of an already-published descriptive statistic, not a causal feature, and
   is documented as such in `core/arbias.py`. It must not be lifted into a strategy in
   that form.
4. **Session eligibility differs slightly between studies.** Study 2 uses
   `vei_exploration`'s loader (3,710 sessions); Study 3 uses `hurst_explore`'s
   complete-grid gate (3,703 NQ / 3,706 ES), because Hurst estimators require exact
   regular spacing. That is the correct gate for each and the 7-session difference cannot
   affect any conclusion here.
5. **No holdout was touched.** Every input is already-consumed exploratory data.

## Builder interpretation

The hypothesis split the world correctly and both halves landed.

Where the estimate is *reported* over a large pooled sample, small-sample bias is a
non-issue in this workspace — the audit's own predicted-null cell confirms it at 6e-5.
Anyone reaching for a bias correction on our IC/reversion statistics is wasting effort.

Where the estimate is *thresholded* and its window *varies*, it is a live defect, and the
`noise_vwap` Hurst gate is a clean instance: a fixed `H >= 0.55` cut fires 4-6x more often
at 10:00 than at 15:59, and a path with literally no memory reproduces about half of that
ramp. Since `noise_vwap` separately documents strong intraday structure — morning
super-diffusion, the :59/:29 clock as a genuine local optimum — an H gate that
preferentially fires in the morning is partly a *time-of-day* selector wearing a
persistence label.

This **qualifies but does not revive** anything. EXP-0026/0027/0028 already rejected the
Hurst gate as selection, as exit conditioning and as sizing. What changes is the standing
descriptive claim that "Hurst LEVEL is a real per-trade quality signal (beats matched
random NQ p=0.03)": that comparison was made against a *matched-count random* null, which
does not hold time of day fixed, so an unknown part of it is the morning. The claim should
now be read as **confounded with time of day and not separately established**. Re-testing
it would mean a slot-matched null or a same-slot z-scored H — both cheap, and the second
is the obvious repair if anyone ever revisits the feature.

The reusable outputs matter more than the verdict: a tested bias-correction module, the
window-length lookup table that says where to bother, the `signflip` control (real
volatility seasonality, zero memory — a better degenerate null than constant-vol fBm for
any intraday persistence question), and the confirmation that this workspace's own
selection-rate-CV diagnostic detects an *estimator*-induced clock just as well as a
*normalisation*-induced one.

Honest limitation: this is one project on a sibling pair, so NQ+ES agreement is cheap
corroboration rather than independent replication. The finding is durable in mechanism
(it is arithmetic) but its *size* on another instrument or estimator is not established.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending

## Promotion decision

- `reports/FINDINGS.md`: **yes** — sections A, B, C written.
- `MEMORY.md`: **yes** — project state, and cross-references written into
  `vei_exploration/MEMORY.md` and `noise_vwap/MEMORY.md`.
- Shared `LEARNINGS.md`: **yes, as provisional.** The mechanism is general and the
  reusable diagnostics are cross-project, but it is a single project on a correlated pair.
  The named confirming test is in the entry.
