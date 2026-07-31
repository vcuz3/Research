# VEI Exploration — Findings

Descriptive study of the **Volatility Expansion Index** (VEI = intraday
ATR(short)/ATR(long)) on NQ and ES 1-min RTH bars (2011–2026, ~3710 sessions, 30-min
decision clock). Nothing here trades — these are causal measurements of what VEI is
and what it predicts. Reading (user): VEI ≈ 1 calm; VEI < 1 consolidating after a
wider range (contraction); VEI > 1 expanding.

Companion to `futures/nq/noise_vwap` EXP-0035, where VEI as a momentum-breakout entry
gate was a NO-GO. This project asks the broader question: volatility drives every
strategy, so where does VEI actually carry information?

Status labels follow the workspace convention (`confirmed` = code+data reproducible
here, cross-market; discovery, not deployable alpha).

---

## A. Smoothing — ~~the ATR estimator dominates~~ **effective MEMORY dominates**

- Status: **CORRECTED 2026-07-26** — the original EXP-0001 headline ("the ATR estimator
  dominates") was a confounded comparison and is **withdrawn**. See "A-corrected" below,
  which supersedes it. The underlying observation (SMA(10/50) is a poor regime signal;
  Wilder(10/50) is a much better one) still holds; the *attribution* was wrong.
- Script: `scripts/s1_smoothing.py` → `artifacts/runs/A_smoothing/`

The raw ratio built from a simple rolling-mean ATR (what EXP-0035 used) is a **poor
regime signal**: across consecutive 30-min decision bars its lag-1 autocorrelation is
≈0 and it whipsaws across the VEI=1 line ~46% of the time. Swapping the ATR estimator
to **Wilder's RMA** (the textbook ATR, an EMA with α=1/n) transforms it:

| VEI(10/50) variant | AC1 (persistence) | whipsaw rate | IC vs forward 30-min vol |
|---|---|---|---|
| SMA (raw) | −0.01 | 0.46 | +0.060 |
| **Wilder RMA** | **0.55** | **0.23** | **+0.157** |
| EMA(span) | 0.16 | 0.37 | +0.065 |
| SMA + EMA(ratio, span 3/5/10) | ≈0 | ~0.45 | +0.06–0.07 |

ES identical in shape (Wilder AC1 0.51, whipsaw 0.26, IC +0.195 vs SMA +0.069).

Reads: (1) Wilder ATR nearly **triples** the forward-vol information and makes VEI a
steady, persistent regime read instead of a jittery one. (2) EMA-smoothing the *ratio*
at 1-min granularity barely helps the 30-min-decision persistence (a short EMA has
decayed by the next decision) — the win comes from smoothing *inside the ATR*, i.e. a
longer-memory estimator, not from post-smoothing the ratio. **Adopt Wilder(10/50) as
the canonical VEI.** EXP-0035 used the jumpiest, least-informative variant.

## A-corrected. It is the effective MEMORY, not the estimator form — and the shipped Wilder is mis-initialised

- Status: confirmed (NQ + ES), supersedes A's attribution — **EXP-0006 (HYP-0003)**
- Script: `scripts/s1_smoothing.py` (control cells folded in) →
  `artifacts/runs/EXP-0006/A_smoothing_smoothing_{NQ,ES}.txt`; original standalone probe
  at `scripts/s1b_estimator_controls.py`

A compared `sma(10,50)` against `wilder(10,50)` at equal *nominal* n. That is not equal
memory: SMA(n) has centre-of-mass (n−1)/2, Wilder(n) has n−1, so the Wilder cell carries
~2× the memory. The comparison moved estimator form and memory together. Running the
missing com-matched cells in both directions (same sessions, same clock, same IC
estimator):

| VEI(10/50) variant | defined | mean | AC1 | whipsaw | IC NQ | IC ES |
|---|---|---|---|---|---|---|
| SMA 10/50 (A's baseline) | 44516 | 0.973 | −0.011 | 0.456 | +0.060 | +0.069 |
| **SMA 19/99** (com-matched to Wilder) | 37099 | 0.956 | 0.330 | 0.334 | **+0.186** | **+0.188** |
| Wilder 10/50 (A's canonical) | 44516 | 0.893 | 0.549 | 0.229 | +0.157 | +0.195 |
| **Wilder 5/25** (com-matched to SMA 10/50) | 48226 | 0.937 | 0.209 | 0.356 | **+0.001** | +0.040 |
| EMA span 19/99 (α-identical to Wilder) | 37099 | 0.921 | 0.470 | 0.270 | **+0.242** | **+0.249** |
| Wilder 10/50, textbook SMA seed | 44516 | 0.917 | 0.441 | 0.245 | +0.202 | +0.207 |

Reads:

1. **Memory is the axis, not estimator form.** A plain SMA at matched com (19/99)
   recovers most of the AC1/whipsaw gain and matches-or-beats Wilder on forward-vol IC
   (+0.186 vs +0.157 NQ; +0.188 vs +0.195 ES — a wash, one market each way). The reverse
   control closes it: Wilder shortened to SMA(10/50)'s memory (5/25) collapses to IC
   **+0.001 NQ / +0.040 ES**, *worse* than the SMA it was meant to beat. Changing memory
   alone (SMA 10/50 → 19/99) roughly triples the IC on both markets. A's own `ema(10,50)`
   row (AC1 0.16, IC ≈ SMA) was already the tell and was read past.
2. **"Wilder vs EMA" was never an estimator contrast.** Wilder α=1/n *is*
   `ewm(span=2n−1)`, so `wilder(10,50)` and `ema(19,99)` are the same recursion; they
   differ only in `min_periods`.
3. **The shipped Wilder is mis-initialised, and it costs real information.**
   `ewm(adjust=False, min_periods=n)` seeds at the first observation and merely masks the
   first n−1 values; it does not seed with the first n-bar SMA as textbook Wilder ATR
   does. Two separable costs: (a) `min_periods=n` on an α=1/n recursion admits bars whose
   long ATR has had well under one e-folding of data — 7417 decisions, 17% of the series;
   dropping them (the `ema 19/99` row) lifts IC +0.157→+0.242 NQ / +0.195→+0.249 ES;
   (b) the seed itself — a textbook SMA seed lifts IC to +0.202/+0.207. The shipped
   variant is worse than **both** repairs. Because the ATR resets per session this
   recurs ~3710 times, not once.
4. **The ratio-smoothing axis was under-powered, as suspected.** EMA spans 3/5/10 on
   1-min data is a ~5-minute average against a 30-min decision clock — fully decayed by
   the next decision. It shows short minute-level smoothing is inert, not that smoothing
   VEI is inert. Given (1), the untested and interesting cell is a *decision-clock*
   (30–120 min) smoother.

**Consequence:** A's canonical-VEI decision rested on a confounded comparison plus a
defective warm-up, so Studies B–F all used the weaker of the available implementations —
the same criticism A levelled at noise_vwap EXP-0035. **The warm-up has since been
repaired (`core/vei.py`, `seed='sma'` default) and B–F re-run: see EXP-0006. The repair
was not cosmetic — Study D lost significance on NQ and has been downgraded.**

**Repaired-vs-legacy at equal sample (EXP-0006):** same 44516 decisions, forward-vol IC
+0.157→**+0.202** (NQ) / +0.195→**+0.207** (ES). Note AC1 *falls* 0.549→0.441: the legacy
series was partly autocorrelated because consecutive bars shared one contaminating seed,
so EXP-0001's "persistence" headline was itself inflated by the defect.

**~~Open lead, flagged not adopted~~ → LEAD WITHDRAWN by EXP-0008 (see §H).**
`wilder_20_100` scores far higher than everything else (IC **+0.396 NQ / +0.353 ES** at
the same 37099 decisions as the 19/99 cells, AC1 0.685, whipsaw 0.15), and IC rises
monotonically with memory across every cell. The suspicion recorded here — that
`IC_fwdvol` was rewarding "less of a ratio" — **was tested and confirmed decisively**:
`IC_fwdvol` is a near-perfect linear function of level-likeness (R² 0.992 on both
markets) and is won outright by a control with no denominator at all. Worse, it ranks
variants *opposite* to the project's primary metric, and `wilder_20_100` turns out to
have the **lowest** momentum contrast of any ratio tested. Not adopting it was correct.
**`IC_fwdvol` is retired as a selection metric.** Canonical stays Wilder(10/50), repaired.

## A-corrected (b). VEI = 1 is not a calibrated "calm" line — it is a time-of-day line

- Status: confirmed (NQ + ES) — same run

Shipped Wilder VEI has mean 0.893 (NQ) / 0.924 (ES), not ≈1. The mis-initialisation
accounts for only ~0.024 of that (0.893→0.917 with a textbook seed). The rest is
structural, and two facts show it:

- SMA VEI has no recursion seed at all and is still below 1 (mean 0.973 NQ / 0.986 ES).
- Mean VEI by decision slot (`mfo`), shipped Wilder:

```
mfo:   59    89   119   149   179   209   239   269   299   329   359   389
NQ:  0.745 0.756 0.779 0.797 0.821 0.850 0.903 0.930 0.982 0.980 1.005 1.165
ES:  0.788 0.802 0.826 0.835 0.850 0.877 0.923 0.948 0.997 0.997 1.025 1.216
```

The session-reset ATR anchors the long window on the high-vol open; the short window
walks off it first, so the ratio starts far below 1 and drifts up all day. So **1.0 is
not a constant calm threshold — it is a threshold that means something different at each
slot**, and the stated reading ("VEI ≈ 1 calm, < 1 contraction, > 1 expansion") does not
hold for this implementation. Corollaries: (i) A's *whipsaw rate* (crossings of 1.0) is
partly measuring where in the day the level sits relative to a fixed line, not regime
stability — a per-slot median line would be the honest version; (ii) the `VEI>1.10`
threshold in Studies D/E is largely a "late in the session" selector, which is exactly
what EXP-0005 measured (88.9% NQ / 87.4% ES of high-VEI decisions after 14:00).

**This does not overturn Study D.** EXP-0005 already audited the drift by correlating
*within* slot and count-weighting, and the contrast held at 106%/105% of pooled on both
markets. It also showed de-seasonalising VEI *destroys* information — so the fix is not
to normalise the drift away, it is to stop calling 1.0 "calm".

## B. Volatility forecasting — the level dominates; the ratio adds little

- Status: confirmed (NQ + ES) — EXP-0002
- Script: `scripts/s2_vol_forecast.py` → `artifacts/runs/BC_vol_forecast/`

Forecasting forward realized abs-variation (30/60 min): the current vol **level**
(trailing realized vol) is an extremely strong predictor — rank IC **+0.86**, OLS
R² **0.60**. Adding log(VEI) on top raises R² by only **+0.004** (NQ) / **+0.002**
(ES); the VEI coefficient is statistically non-zero (block-bootstrap CI excludes 0)
but economically marginal. VEI's own IC (+0.16 NQ / +0.20 ES) is real but the ratio
discards the level, which is the informative part. Honest conclusion: **for pure vol
forecasting/sizing, use the vol level; the expansion ratio adds a real but tiny sliver.**

## C. Contraction → expansion ("coiled spring") — NOT supported intraday

- Status: confirmed (NQ + ES), corrects the stated intuition at this timescale — EXP-0002,
  **re-run under the repaired feature by EXP-0006: verdict holds, one sub-claim withdrawn**
- Script: `scripts/s2_vol_forecast.py` (part C)

The user's reading is that VEI < 1 = consolidation after a wider range, i.e. a spring
that should expand. The expansion ratio (forward realized abs-var ÷ horizon-scaled
trailing abs-var) by VEI quintile says otherwise at 30–60 min. **Repaired reading
(EXP-0006, current):** the expansion ratio is essentially **independent of VEI** — flat
and non-monotone at ~0.94–0.99 across every quintile (NQ H=30: 0.958 / 0.944 / 0.952 /
0.968 / 0.960; ES: 0.988 / 0.960 / 0.967 / 0.985 / 0.977) — i.e. intraday vol decays
regardless of regime. Forward realized movement (the *level*) still rises monotonically
with VEI (persistence). Either way there is **no coiled-spring effect** intraday; the
squeeze→breakout idea, if real, likely lives at a **daily/multi-day** timescale (open
follow-up, see backlog).

> ~~*Superseded sub-claim (EXP-0002, legacy feature):* the expansion ratio is "lowest for
> low VEI (~0.90) and rises with VEI toward ~1.0", i.e. low VEI keeps decelerating.~~
> The monotone rise does not survive the warm-up repair and was itself partly the
> artefact. The NO-SPRING verdict is unaffected — it never depended on the slope.

## D. VEI as a regime SELECTOR for momentum — DOWNGRADED to qualified

- Status: **QUALIFIED / INCONCLUSIVE as of EXP-0006 (2026-07-26)** — downgraded from
  `confirmed` when the preregistered kill test fired on NQ under the repaired feature.
  Was: EXP-0003, upheld against the time-of-day confound by EXP-0005 (Study F).
  **Discovery, never validated alpha** — and EXP-0004 already showed it does not monetize.
- Script: `scripts/s3_regime_dynamics.py` → `artifacts/runs/EXP-0006/D_regime_dynamics_*`

Correlation of the trailing 30-min return with the next 30-min return, by VEI regime
(corr < 0 = mean-reverting / fade; corr > 0 = trending / momentum). **Current (repaired
feature, EXP-0006):**

| regime | NQ corr [90% CI] | ES corr [90% CI] | read |
|---|---|---|---|
| low (<0.90) | −0.008 [−0.030,+0.015] | −0.006 [−0.043,+0.031] | random walk |
| calm (0.90–1.10) | +0.020 [−0.005,+0.045] | +0.008 [−0.029,+0.042] | random walk |
| **high (>1.10)** | **+0.067 [−0.010,+0.142]** | **+0.075 [+0.003,+0.144]** | NQ inconclusive / ES trending |

> ~~*Superseded (EXP-0003, legacy feature):* high (>1.10) = +0.104 [+0.023,+0.186] NQ /
> +0.096 [+0.016,+0.171] ES, both CIs excluding zero, "confirmed cross-market".~~
> Those numbers reproduce exactly under `seed='first'` (rule 23) but were measured
> through the warm-up defect.

**What changed and what did not.** The direction and the cross-market agreement survive:
momentum continuation is ~zero in calm/contracting tapes and positive in the expanding
one, on both markets. What fails is significance and size — the repaired point estimate
is 63% (NQ) / 83% (ES) of the legacy one, and **NQ's CI now includes zero at the
preregistered cut**. Since HYP-0003's stated prior was that a better-measured feature
should give an equal or larger effect, the shrinkage is evidence *against* the finding.
It is also **threshold-sensitive**: NQ is significant at a selection-rate-matched cut
(+0.087 [+0.009,+0.144]) but not at the fixed 1.10 line — expected, given A-corrected (b)
shows 1.10 is not a calibrated level. No regime shows significant mean-reversion at
30 min.

**Read this as:** a real but weak, small-sample, cross-market-consistent tilt that is not
established at the significance level previously claimed, and that EXP-0004 already
showed does not monetize. Not a basis for anything without a future shadow sample.

Caveat vs noise_vwap EXP-0035: there, high-VEI *breakout entries* continued slightly
*worse* (a late-chase selection effect on already-extended entries). No contradiction —
D measures the unconditional tape, EXP-0035 measured continuation of an
already-extended breakout. The consistent story: generic momentum emerges in
expansion, but a breakout system that *already* requires extension does not gain by
further filtering on VEI.

## E. Momentum-in-high-VEI strategy test — mechanism confirmed, edge rejected

- Status: mechanism confirmed (NQ + ES); not deployable — EXP-0004 (HYP-0001).
  **Verdict UNCHANGED after the EXP-0006 feature repair** (see the box at the end).
- Script: `scripts/hyp_0001_momentum_vei.py` → `artifacts/runs/EXP-0004/`,
  repaired re-run at `artifacts/runs/EXP-0006/EXP-0004_momentum_{NQ,ES}.txt`

Preregistered promotion of Study D: a causal momentum rule (go with the trailing 30-min
move, fill next-open, hold 30 min, flat at close) gated on VEI regime. The **gross
dose-response confirms the mechanism** — momentum's positive gross expectancy lives
almost entirely in the high-VEI regime, on both markets:

| cell | NQ gross pt/trade | ES gross pt/trade |
|---|---|---|
| `low ≤1.10` | −0.008 (≈0/neg) | +0.008 |
| `all` | +0.054 | +0.018 |
| **`high >1.10`** | **+0.959** | **+0.375** |

Same rule, only the VEI gate differs; sign is correct (high ≫ low) and transfers to ES.
**But it does not monetize:** the preregistered `high>1.10, H=30` cell has daily Sharpe
+0.015 (NQ, t=0.06) / −0.073 (ES) — the per-trade tilt is sub-cost and daily-lumpy.
Kill-test 1 (netR>0 & Sh>0 & day_t≥2 & high>low) fails on both → matched-count random
null and path-preserving Null C not spent (standing rule). Sensitivity: net/trade rises
monotonically with T and with horizon (H=60 → NQ t≈1.7 / ES t≈1.4, still <2, post-hoc);
recent era (2023+) positive on the high cell (forward-watch only, rule 26). Conclusion:
a real, cross-market per-trade momentum signal that does not clear costs as a standalone
strategy — the recurring project pattern.

> **EXP-0006 repaired re-run — verdict unchanged.** Under the repaired warm-up the gross
> dose-response is *sharper* (NQ high gross/trade +0.96 → **+1.39** pt; low regime still
> ≈0/negative), and the primary cell improves to daily Sharpe **+0.134** (NQ, t 0.52) /
> **−0.050** (ES), or +0.232 / +0.030 at a selection-rate-matched cut. All still far below
> the preregistered `day_t ≥ 2.0` gate, so **kill-test 1 REJECTs on both markets again**
> and the matched-count random null and Null C remain **unspent**. Per HYP-0003's
> multiple-testing note these improved numbers are post-hoc on consumed history and are
> **not** evidence for the edge.

## F. Term structure and the time-of-day audit — the AUDIT holds, but D no longer clears

- Status: **partly superseded by EXP-0006.** The time-of-day audit itself is confirmed and
  slightly stronger under the repaired feature; the front-loading, VR and 13:30 results all
  replicate. But the contrast being audited lost significance on NQ (see Study D), and
  **the de-seasonalisation corollary is REVERSED** (box below). Originally EXP-0005
  (HYP-0002), descriptive.
- Script: `scripts/s4_term_structure.py` → `artifacts/runs/F_term_structure/`,
  repaired re-run at `artifacts/runs/EXP-0006/F_term_structure_*`

**The audit (the reason this study exists).** VEI here is a session-reset intraday
ATR(10)/ATR(50) whose long leg is anchored to the volatile open, so it drifts upward all
day (NQ slot mean 0.745 at 10:30 → 1.165 at 15:59). The fixed cut `VEI>1.10` therefore
fires on ~1% of morning decisions and 19–64% of late ones, and **88.9% (NQ) / 87.4% (ES)
of all high-VEI decisions sit in the 14:00-and-later slots — 31% of the clock.** No
earlier study grouped by time of day, so "momentum turns on when vol expands" and
"momentum is stronger late in the session" were completely confounded. Correlating
*inside* each of the 13 slots and only then count-weighting:

| | pooled diff (Study D style) | **within-slot diff [90% CI]** | retained |
|---|---|---|---|
| NQ | +0.1040 | **+0.1098 [+0.0251, +0.1715]** | 106% |
| ES | +0.0979 | **+0.1033 [+0.0208, +0.1681]** | 105% |

(Those are the legacy-feature numbers; they reproduce exactly under `seed='first'`.)
**Under the repaired feature (EXP-0006) the audit's own conclusion is unchanged and
slightly stronger — within-slot retains 111% (NQ) / 117% (ES) of pooled — but the
contrast itself shrinks to +0.0690 [−0.0068,+0.1339] NQ / +0.0857 [+0.0092,+0.1465] ES.**
So: **whatever Study D is, it is still not a clock effect** — but it is no longer
significant on NQ. See Study D for the downgrade.

Stable across the thin-cell threshold. Separately there *is* a real, VEI-independent
time-of-day effect: unconditional corr is ≈0 at every slot except 13:30 (+0.101 NQ /
+0.108 ES) and 15:30 (+0.078 / +0.084), agreeing across markets. **The 13:30 slot is even
more extreme under the repair** (high-regime corr +0.377 NQ, n=246 / +0.425 ES, n=269,
with rest-corr also elevated) and remains unexplained.

> **REVERSED by EXP-0006 — do not follow the instruction below.**
> ~~**De-seasonalising VEI destroys information.** At matched selection count, a causal
> same-slot percentile rank is *weaker* than the raw ratio on both markets, with a CI
> including 0 (NQ +0.069 vs raw +0.100; ES +0.068 vs +0.086). VEI's information is in its
> **absolute level**... so do not "fix" VEI's intraday drift.~~
>
> Under the repaired feature the ordering **inverts**: the causal same-slot percentile is
> now equal or better than the raw level on both markets — NQ raw +0.0682 [−0.0143,+0.1493]
> vs percentile **+0.0798 [+0.0087,+0.1482]** (the percentile is the only one of the two
> whose CI excludes 0); ES raw +0.0642 [−0.0155,+0.1423] vs percentile +0.0711
> [−0.0021,+0.1486]. Mechanism: the legacy warm-up bias was itself time-of-day dependent
> (worst early in the session, where the long ATR is least populated), which artificially
> advantaged the raw level. **The "do not de-seasonalise" instruction was an artefact of
> the bug it was measured through, and is withdrawn.**

**Term structure — the information is front-loaded (corrects Study E).** On a
composition-free constant sample, high-regime corr(past 30m, fwd H):

| H | 5 | 10 | 15 | 30 | 60 | 90 | 120 | close |
|---|---|---|---|---|---|---|---|---|
| NQ | **+0.177** | +0.168 | +0.095 | +0.161 | +0.131 | +0.070 | +0.068 | +0.029 |
| ES | **+0.170** | +0.128 | +0.073 | +0.150 | +0.150 | +0.060 | +0.054 | +0.025 |

Low/calm are flat at ≈0 at every horizon. Predictability peaks at 5–10 minutes, holds
through 30–60, and is gone by 90–120 and to-close. So EXP-0004's "the effect strengthens
with hold" is **wrong**: what improves with a longer hold is the *cost ratio* (a fixed
round trip amortised over a bigger move), not the signal. There is no basis for expecting
gains past ~60 minutes.

**Variance ratio — no regime difference.** Pooled VR(q) looks like high-VEI is much more
anti-persistent (NQ VR(30) 0.911 vs 0.959), but that is composition: a 60-min forward
window excludes the late slots where high-VEI lives. The within-slot paired difference is
≈0 at every q on both markets. All regimes are mildly anti-persistent (VR<1), matching
`hurst_explore`'s coarse-scale result. **"Momentum regime" means a drift tilt, not a
smoother forward path** — VEI predicts the alignment of the aggregate forward move with
the aggregate past move, and changes nothing about the minute-to-minute path.

**Robustness.** At matched selectivity, (10,50) with past_win=30 is the best cell on both
markets; past_win is load-bearing (a 10-min trailing return roughly kills the effect:
+0.031 NQ / +0.003 ES). The canonical parameters sit at a local optimum rather than being
an arbitrary default.

**Erratum to Study E (rule 13).** The published H=60 cell ran up to two concurrent
positions on a 30-min clock while HYP-0001 declared non-overlapping single-position bets.
Corrected to a true 1-unit book: NQ Sharpe +0.442 (t 1.70) / ES +0.526 (t 2.02); on a
proper 60-min clock +0.288 / +0.249. `core/strategy.py::simulate` now enforces non-overlap
by default. **Study E's verdict is unchanged** — the preregistered H=30 cell is untouched,
kill-test 1 still fails, nulls remain unspent — and H=60 is a post-hoc horizon on consumed
history, so the ES t=2.02 is not a pass.

## G. Did the legacy Wilder bug accidentally capture useful opening information? — mechanism yes, prediction NO

- Status: **mechanism confirmed; predictive feature rejected** (NQ + ES) — EXP-0007 /
  HYP-0004, post-hoc mechanism validation
- Script: `scripts/hyp_0004_opening_seed.py` → `artifacts/runs/EXP-0007/`

The hypothesis came from EXP-0006's puzzle: repairing Wilder reduced Study D even though
the legacy and repaired `VEI>1.10` sets overlap by 92.1%. The legacy recursion starts both
ATR legs at the first RTH bar, so it may accidentally encode whether the first minute was
quiet or shocked relative to the first 50 minutes. That mechanical story is **confirmed**:
within time-of-day slot, `legacy_vei - repaired_vei` correlates **+0.551 NQ / +0.532 ES**
with `quiet_open = -log(first-minute TR / mean first-50-minute TR)`. The bug is an
undocumented opening-anchor feature, not merely random VEI noise.

It is **not a stable predictor**. After controlling for repaired VEI, past volatility,
slot and era levels, and slot/era baseline-momentum slopes, the standardized
`past_ret × quiet_open` coefficient is:

| | coefficient [session-block 90% CI] | era-stratified re-pairing p | quietest−loudest quintile spread |
|---|---:|---:|---:|
| NQ | +0.0171 [−0.0304,+0.0210] | 0.0450 | +0.0160 |
| ES | +0.0121 [−0.0272,+0.0164] | 0.1369 | **−0.0217** |

Both CIs include zero, ES fails the claim-matched null and has the wrong-signed quintile
spread, neither market is monotone by opening-condition quintile, and era coefficients
alternate sign. The apparent positive full-sample coefficient is concentrated in the
**same single session on both markets, 2020-03-16**, whose first RTH bar has zero range.
Leaving it out flips the coefficient to −0.0153 NQ / −0.0071 ES; dropping zero-range
openings gives −0.0128 / −0.0059 (both CIs include zero), and a bounded causal
`-log1p(open_rel50)` transform also gives ≈0. NQ's isolated p=0.045 is therefore not a
robust survivor, and same-date NQ/ES leverage is not independent replication.

The spectacular consumed-history fringe reproduces — legacy-only is just 23 NQ / 40 ES
observations with corr +0.809/+0.451, repaired-only 203/228 with −0.229/−0.154 — but it
does not generalise continuously. The 2,651/3,128 observations high under **both**
versions retain a weaker +0.087/+0.086 correlation, so Study D's qualified common core is
not wholly a seed artefact. **Consequence:** do not restore the defective seed and do not
promote `quiet_open`; the legacy uplift was rare boundary selection plus one shared
extreme session. Any new opening-transition work should use an explicit causal onset /
volume feature and future data, not more transforms of this consumed screen.

---

## H. `IC_fwdvol` measures level-likeness, not ratio quality — and the LEVEL alone does not select momentum

- Status: **confirmed (NQ + ES), decisively** — EXP-0008 / HYP-0005
- Script: `scripts/s1c_selection_metric.py` → `artifacts/runs/EXP-0008/`
- Closes next action 0b **by replacement**, not by adopting the argmax.

Ten VEI variants scored on ONE common sample (n=33,389; the intersection where every
variant is defined, so the estimator is never confounded with the time of day it is
measured at). `corr_lvl` = Spearman against the vol level (`past_rv`, Study B's
baseline). Two `LEVEL:` rows are ATR(short) with **no denominator at all** — not
candidate features, but the degenerate limit, and the decisive control.

| variant | corr_lvl | IC_fwdvol | IC_partial | contrast (matched rate) |
| --- | --- | --- | --- | --- |
| `LEVEL: atr_10` (no ratio) | +0.616 / +0.655 | **+0.5745 / +0.6130** | +0.117 / +0.149 | **−0.005 [−0.062,+0.044] / +0.023 [−0.026,+0.069]** |
| `wilder_5_25` | +0.090 / +0.086 | +0.1124 / +0.1103 | **+0.069 / +0.070** | +0.093 [+0.027,+0.152] / +0.099 [+0.025,+0.167] |
| `wilder_10_50` **[canon]** | +0.259 / +0.252 | +0.2436 / +0.2367 | +0.044 / +0.047 | +0.075 [−0.013,+0.129] / +0.089 [+0.002,+0.152] |
| `wilder_20_100` | +0.450 / +0.404 | +0.3958 / +0.3530 | +0.025 / +0.025 | +0.059 [−0.028,+0.120] / +0.045 [−0.034,+0.109] |

Cross-variant regressions (NQ / ES):

| | slope on `corr_lvl` | R² |
| --- | --- | --- |
| `IC_fwdvol` | **+0.891 / +0.903** | **0.992 / 0.992** |
| `IC_partial` | +0.116 / +0.175 | 0.301 / 0.496 |
| `contrast` | **−0.216 / −0.160** | 0.838 / 0.759 |

**(a) The incumbent metric is level-likeness, to three significant figures.** R² 0.992 on
both markets, slope ≈0.9, intercept ≈0 — there is essentially no residual left for
"ratio quality". The control settles it: a feature with *zero* ratio content **wins the
`IC_fwdvol` column outright** on both markets. A metric a non-ratio wins cannot select
among ratios. The mechanism is algebraic, not empirical: as the denominator's memory
grows, ATR(long) approaches a within-session constant, and dividing by a constant is not
forming a ratio — it is rescaling ATR(short). The "better" variants were better because
they had stopped being ratios.

**(b) It is not merely uninformative, it is anti-selective.** `contrast` — the project's
primary metric — moves *against* `corr_lvl` (r −0.915 / −0.871). The two metrics rank
variants oppositely, so selecting on `IC_fwdvol` degrades the momentum-regime property.
`wilder_20_100`, the highest-scoring ratio on the incumbent metric, has the **lowest**
momentum contrast of any ratio tested, below canonical on both markets. §A-corrected's
refusal to adopt it is vindicated.

**(c) No forward-vol metric can do this job.** `IC_partial` (level partialled out of both
sides, `analysis.partial_spearman`) breaks the near-perfect fit but the pure-level
controls still top it, because `LEVEL: atr_10` is a *differently windowed* level that
carries forward-vol information `past_rv` lacks. Report `IC_partial` as a diagnostic;
do not promote it to the selection rule.

**(d) The most valuable result came from the control.** The pure vol level has a momentum
contrast of essentially **zero** (−0.005 NQ / +0.023 ES, both CIs spanning 0), while every
genuine ratio is positive (+0.06 to +0.12). **High volatility alone does NOT select the
momentum regime; the expansion RATIO does.** This is the first result in the project that
separates VEI from the level on the momentum axis rather than the vol-forecasting axis,
and it sharpens Study D's meaning — D is *not* "momentum works when vol is high".

**The two axes are now coherent and opposite.** On the **vol-forecasting** axis the ratio
is dominated by the level and nearly worthless (§B, ΔR² +0.0017). On the
**momentum-regime** axis the level is worthless and only the ratio carries anything (this
section). These are not competing measurements of one quantity — they are different
quantities, and VEI's only distinctive role is the second.

**Limits (rule 26).** This does **not** revive Study D: D remains qualified/inconclusive
after EXP-0006, its CI still crosses zero on NQ at the canonical variant, and every
contrast CI here is wide and overlapping. The `contrast` column is a ten-variant SEARCH
on consumed history; the argmax `wilder_20_50` (+0.108 / +0.118) is **not** promoted and
must not be cited as a better estimator. What is established is the *slope* — the
direction of the relationship between level-likeness and momentum-selectivity — not any
individual cell. Flagged for any future estimator work: the short-window cells
(`wilder_5_25`, `wilder_5_50`) are the least level-contaminated, so the **short** leg is
where to look, not the long one; and `sma_19_99` has `IC_partial` ≈ 0 on both markets, so
its entire forward-vol score is level content.

---

## I. The VEI threshold was a clock; the trailing same-slot z-score fixes it at no information cost

- Status: **confirmed (NQ + ES)** for the calibration result; **provisional /
  holdout-pending** for the contrast improvement — EXP-0009 / HYP-0006
- Script: `scripts/s5_slot_normalised.py` → `artifacts/runs/EXP-0009/`
- Origin: user proposal — apply the noise-area construction (a same-time-of-day
  statistic over a trailing lookback of sessions) to VEI itself rather than to
  displacement.

Four features at MATCHED selection rate on one common sample: `raw` (canonical VEI),
`rel` = VEI/mu_slot, `z` = (VEI − mu_slot)/sd_slot, `pct` (the ordinal percentile
EXP-0005/0006 tested). `mu`/`sd` come from the new `analysis.causal_slot_stats` —
strictly prior sessions at the same slot, 90-session lookback, fractional `min_obs`.

**(a) The defect, sized.** At `VEI > 1.10` the raw feature selects **1.5% of the 10:30
slot and 18.4% of the 15:30 slot** (NQ; ES 2.6% → 22.4%). Per-slot selection-rate spread
0.169 NQ / 0.198 ES, CV 0.93 / 0.88. §A-corrected (b) said the 1.10 line is a time-of-day
line; this quantifies it. Any regime label built on a fixed cut of the raw ratio was
substantially a clock.

| feature | slot-rate spread NQ / ES | CV NQ / ES |
| --- | --- | --- |
| `raw` | 0.1690 / 0.1981 | 0.933 / 0.882 |
| `rel` | 0.0293 / 0.0307 | 0.135 / 0.105 |
| **`z`** | **0.0115 / 0.0121** | **0.050 / 0.041** |
| `pct` | 0.0093 / 0.0088 | 0.039 / 0.031 |

**(b) `rel` only half-fixes it, and that is informative.** Dividing by the trailing
same-slot MEAN removes per-slot LOCATION but not per-slot SCALE, leaving `rel` ~2.5×
worse-calibrated than `z` on both markets. So **VEI's per-slot dispersion is not
proportional to its per-slot level** — the two corrections are separable and both are
needed.

**(c) De-seasonalising does NOT destroy information — settled.** `rel` retains **88.1% NQ
/ 92.5% ES** of raw's within-slot contrast, above the pre-declared 75% kill-test gate on
both markets. Together with EXP-0006 this closes the EXP-0005 claim for good: that
finding was an artefact of the warm-up bug, and the reversal now has a second,
independent, magnitude-preserving confirmation.

**(d) `z` is the only feature whose CI excludes zero on both markets in both metrics.**

| feature | within-slot NQ | within-slot ES | pooled NQ | pooled ES |
| --- | --- | --- | --- | --- |
| `raw` | +0.0748 [−0.0002, +0.1352] | +0.0781 [−0.0040, +0.1442] | +0.0647 [−0.0097, +0.1443] | +0.0633 [−0.0119, +0.1405] |
| `rel` | +0.0659 [−0.0154, +0.1277] | +0.0722 [−0.0019, +0.1368] | +0.0711 [−0.0042, +0.1452] | +0.0754 [+0.0017, +0.1556] |
| **`z`** | **+0.0959 [+0.0187, +0.1544]** | **+0.0784 [+0.0052, +0.1377]** | **+0.0930 [+0.0096, +0.1680]** | **+0.0869 [+0.0046, +0.1638]** |
| `pct` | +0.0805 [+0.0037, +0.1294] | +0.0626 [−0.0235, +0.1198] | +0.0795 [−0.0018, +0.1507] | +0.0699 [−0.0026, +0.1432] |

4 cells of 4 for `z`, 0 of 4 for `raw`. **But read the mechanism, not the headline:** on
NQ the point estimate rises (+28%) at unchanged CI width; on ES it is flat with a
slightly narrower interval. This is a **better-conditioned measurement, not a bigger
effect**, and the size of the gain does not transfer even though the significance pattern
does.

**Decision: adopt `z` as the project's regime label**, `rel` retained as the interpretable
sibling ("1.0 = normal for this time of day"). Measurement improvement only.

**(e) Limits.** Sensitivity lb {30, 90, 180} shows no cliff and no sharp optimum (180
worst on both markets); the default 90 was inherited, not selected. Rule 9a: the trailing
window costs 60 of 3710 sessions **uniformly across all 11 slots** (kept 0.9838
everywhere) — uniformity is the pass signal. CIs are wide, overlapping, and 400-draw; two
`z` ES calls sit near a CI edge, so the *pattern* is the claim, not any pairwise gap.

**(f) This does not revive Study D.** D was downgraded because NQ's CI crossed zero; under
`z` it does not, on either market or metric. That is real and cross-market-consistent —
and it is still the **fifth** measurement of D on the same consumed history, with `z`
chosen from four candidates *after* seeing D fail under the canonical feature. Rule 26
applies exactly. **`z` makes Study D worth one clean forward test; it does not
retroactively pass a test D already failed.**

---

## J. Fresh expansion plus volume separates the tape, but does not monetize

- Status: **mechanism qualified; standalone alpha rejected** — EXP-0010 / HYP-0007
- Script: `scripts/hyp_0007_onset_volume.py` → `artifacts/runs/EXP-0010/`

This was the first test built directly on EXP-0009's repaired regime label. On a
five-minute clock, an onset is the first per-session upward crossing of the causal
same-slot VEI `z >= 1.5`. Volume confirmation requires trailing five-minute volume to
be above its same-slot norm and its volume z-score to strengthen from the prior block.
The momentum rule follows the trailing 30-minute move, fills next-open, and holds 10
minutes. Every horizon uses one contiguous common clock sample.

**The pooled mechanism is clear on both markets.** At H=10, confirmed-onset aligned
return is +0.639 bp NQ [+0.023,+1.252] / +0.781 ES [+0.265,+1.260], versus -1.317
[-2.472,-0.229] / -0.958 [-1.773,-0.142] when unconfirmed. The confirmed-minus-
unconfirmed difference is **+1.956 bp [+0.592,+3.149] NQ / +1.740 [+0.752,+2.694]
ES**. The first mature-high confirmed observation is net negative on both markets, so
onset and late expansion are descriptively different. Volume mostly identifies a bad
subset, however: 79% NQ / 81% ES of onsets are “confirmed.”

**The preregistered strategy is rejected.** The primary H=10 cell has daily Sharpe
+0.050, t +0.19, netR +1.12 NQ and Sharpe -0.199, t -0.76, netR -4.53 ES. Both beat
unconfirmed onset, but neither clears the required daily t >= 2 and ES fails the
positive-performance conditions. Nulls remain unspent. The declared H=30 sensitivity
improves to Sharpe +0.527, t +2.02 NQ / +0.364, t +1.40 ES, but is not the primary,
fails the both-market gate, and cannot replace it.

**It is also era-dependent.** The primary strategy is negative on both markets in
2011–19 and positive in 2020+; the pooled mechanism difference is strongest in 2020–22
on both, but NQ and ES diverge in 2023+. Their apparent replication is highly dependent:
84% of onset dates overlap and same-date/same-slot H=10 returns correlate 0.90. Preserve
the positive recent cell for future shadow observation only.

**Read:** VEI onset and volume participation improve the description of *what kind* of
expansion is occurring. They do not establish a standalone trade. The defensible next
use is as a veto or allocation variable inside an independently validated strategy,
where incremental portfolio value can be tested against both no-VEI and absolute-vol
controls.

---

## K–L. A two-input forward-volatility core is accurate AND conditionally skilful (EXP-0011, EXP-0012)

*Builder: Codex. Summarised here because §M depends on it; lettering follows `MEMORY.md`
(K = EXP-0011, L = EXP-0012).*

The adopted forward-30-minute realised-volatility specification is deliberately small:
a **causal trailing 90-session same-slot median of the target plus `range_rv_15m`**.

- **K — EXP-0011 / HYP-0008** asked whether six extra multi-horizon volatility state
  variables add to that core. On the locked 2024-01-01..2026-07-14 out-of-sample
  interval they did, on every predeclared gate: normalized delta IC **+0.0088 NQ**
  (90% CI [0.0055, 0.0124]) and **+0.0095 ES** ([0.0064, 0.0133]), every OOS year
  positive, MAE and QLIKE both lower. **Confirmed but NOT adopted** — the gain is too
  small for six extra state variables. Multi-horizon is a shadow benchmark only.
- **L — EXP-0012 / HYP-0009** then answered the question that matters more, and answered it
  emphatically: is the core's high pooled IC just the intraday volatility curve? No.
  Within-slot IC is **0.878 (NQ) / 0.871 (ES)** against **0.418 / 0.383** for the causal
  same-slot median alone, a delta of **+0.460 [+0.4365, +0.4833]** / **+0.489
  [+0.4625, +0.5158]**, with log-MSE skill +73.6% / +74.2% and every year and all 11
  slots positive. `range_rv_15m` carries real state information at a fixed decision
  slot; the clock-composition explanation is rejected.

**Caveat carried forward** (this project's review of EXP-0011): the Part-A shuffled-target
placebo did **not** centre at zero — null mean +0.0101 NQ / +0.0042 ES against an observed
Part-A delta of +0.0192 / +0.0160 — and the placebo was never rerun on Part B. NQ's OOS
delta of +0.0088 therefore sits *inside* its own Part-A placebo band [+0.0075, +0.0127].
The multi-horizon INCREMENT is "qualified-confirmed pending the OOS placebo". Nothing in
the core specification depends on that increment, since the increment was not adopted.

**Read:** the operational forecast is the two-input core. It is accurate, and §L's
within-slot result means it is accurate in the way a decision maker needs. Whether that
converts into money is a separate question, answered in §M.

**QUALIFICATION added by §O (EXP-0015):** §L's +0.47 within-slot delta is measured against
the causal same-slot median, which is a WEAK benchmark. Against trailing 30-minute
realised volatility — the benchmark a practitioner would actually default to — the same
delta is **+0.013**, because persistence alone already scores log-MSE skill +0.69/+0.71
over seasonality. The core's advantage over persistence is a 19%/15% log-MSE reduction
plus a real call on the CHANGE (§O), not a large advantage in ranking levels. Do not
quote §L's +0.47 without §O's +0.013.

---

## M. Forecast volatility is a risk SCALE for the noise-VWAP book, not a tilt — sizing channel CLOSED (EXP-0013, HYP-0010)

The cheapest possible test of the §K–L forecast's economic value: no new strategy, one
regression on trades that already exist. Every trade of the frozen
`futures/nq/noise_vwap` book was tagged with the canonical forecast at its own decision
slot, and the **standardised edge** `net_points / forecast_points` was regressed on the
**causal trailing same-slot percentile** of the forecast (never a full-sample quantile,
so this cannot become the §I time-of-day defect).

**Preregistered kill test fired on both markets — REJECT.** On the adopted
`continuous_stop` config the slope is **−0.0047 [−0.1451, +0.1345] NQ** and **+0.0483
[−0.0822, +0.1838] ES**: flat, CIs spanning zero, and the two markets disagreeing on the
sign. Top-minus-bottom quintile difference likewise (+0.0062 / +0.0312). The `baseline`
decision-clock cell agrees.

The mechanism is visible directly in the quintile table (NQ, `continuous_stop`), and it
is the reason the REJECT is a positive statement rather than a failure:

| forecast pct | share | forecast pt | mean winner | mean loser | median | std_edge |
| --- | --- | --- | --- | --- | --- | --- |
| q1 (calmest) | 13.4% | 18.3 | +34.8 | −8.4 | −2.35 | +0.173 |
| q3 | 16.4% | 25.0 | +46.7 | −12.3 | −3.85 | +0.122 |
| q5 (most expansive) | 34.8% | 41.2 | +83.9 | −22.1 | −7.10 | +0.179 |

Everything scales together. Per-trade expectancy is **proportional** to forecast
volatility, so **sizing at `1/forecast` is the complete and optimal use of the forecast
and no tilt remains**. This is the intraday-entry-level analogue of noise_vwap EXP-0040's
day-level sizing NO-GO, and it is the fifth distinct volatility-conditioning route
rejected on that book (with EXP-0019 exit cadence, EXP-0032 adaptive stop width,
EXP-0035/0036 VEI entry gate, EXP-0040 day-level sizing).

Two by-products are worth more than the primary:

1. **The book already self-selects into high forecast-volatility slots.** 34.8% (NQ) /
   37.3% (ES) of trades land in the top forecast quintile against 20% uniform, and only
   ~12–13% in the calmest. A breakout rule defined against a same-slot noise band *is* a
   volatility filter. That is a mechanical explanation for why volatility overlays keep
   adding nothing to this family: the entry rule has already spent the information.
2. **A rank IC on this P&L points the wrong way.** `IC(forecast, net_pt)` is **−0.357 NQ
   / −0.316 ES** — large and negative — while the mean effect is flat-to-positive. With a
   74–75% loser rate a rank statistic tracks the *median* trade, and the median simply
   loses more points when volatility is higher. Read the mean/slope, never the rank IC,
   on a skewed low-hit-rate P&L.

**Denominator follow-on: do NOT switch the sizing scale.** Day-net t under size ∝ 1/scale
— forecast / trailing ATR14 / unsized — is 5.13 / 4.67 / 3.69 (NQ cont.), 5.27 / 4.60 /
3.21 (NQ base), 2.24 / 2.57 / 2.40 (ES cont.), 2.73 / 2.64 / 2.23 (ES base). Bootstrapped
differences: forecast-minus-unsized is **+1.44 [+0.42, +2.39]** and **+2.07 [+1.01, +3.13]**
on NQ but spans zero on both ES cells; forecast-minus-ATR14 spans zero on the primary
config of **both** markets. So volatility-normalised sizing beats unsized sizing on NQ
only, and the §K–L forecast is not distinguishable from the trailing ATR the project
already deploys. Accuracy over ATR did not convert into a sizing advantage.

Sub-sample cells are a sliced null and are **not** promoted: horizon-matched (hold ≤ 30m)
is significantly negative (−0.069 / −0.150) while short-only is significantly positive on
NQ (+0.397), across six sub-samples × two configs × two markets, with the long/short
split cancelling to the flat pooled result. Era signs flip (2013–19 positive, 2020–26
negative), which is further evidence of no effect. The short-side slope reproduces across
both NQ configs and is recorded as an observation for a possible future preregistered
look, not as a finding.

Rule 23: the importable `core/forward_vol.py` reproduces the EXP-0011 notebook to
|ΔIC| ≤ 1.7e-04 at **exact** row counts, and the sealed-read invariant is bit-identical
(0.000e+00) — which independently proves EXP-0011's Part-A/Part-B split did not leak.
Rule 9a: 85.5–87.1% of trades analysed with every drop accounted; per-slot coverage
uniform at 0.9822–0.9827.

**Read:** stop looking for economic value in applying this forecast to the existing
directional book. Volatility sets *where* the edge lives; it does not tell you how to
size or gate it. Evidence: `artifacts/runs/EXP-0013/`.

---

## N. Downside volatility is total volatility times one half — the recipe transfers, the SPLIT does not (EXP-0014, HYP-0011)

Two independent preregistered claims, applying the frozen §K–L recipe unchanged (only the
target and its own causal same-slot median change).

**Claim A — CONFIRMED on both markets.** Within-slot IC delta over each target's own
same-slot median:

| target | NQ | ES |
| --- | --- | --- |
| total RV (reference) | +0.4622 [+0.4403, +0.4862] | +0.4912 [+0.4688, +0.5146] |
| **downside semivariance** | **+0.4267 [+0.4054, +0.4499]** | **+0.4560 [+0.4337, +0.4791]** |
| upside semivariance | +0.4587 [+0.4377, +0.4824] | +0.4869 [+0.4658, +0.5096] |
| retention vs reference | **92.3%** | **92.8%** |

Both clear the preregistered 75% retention gate with room to spare; log-MSE skill over
the same-slot median is +0.626 / +0.648 and MAE falls 6.85 → 4.25 bp (NQ) / 5.55 → 3.36 bp
(ES), positive in all eleven tested years on both markets. The downside leg is
consistently the hardest of the three, which is the expected ordering (down-minutes are
the sparser, more jump-driven half), but the shortfall is small. **The quantity that
actually enters a stop or barrier calculation is available at no extra cost.**

**Claim B — REJECTED on both markets.** Within-slot IC delta on `fwd_down_share`:
−0.0064 [−0.0192, +0.0087] and +0.0045 [−0.0093, +0.0186] on NQ; +0.0044 [−0.0088,
+0.0199] and −0.0013 [−0.0160, +0.0139] on ES. All four span zero and the markets
disagree on which of the two declared candidates is better.

**The degenerate control is stronger evidence than the CIs.** The realised down-share has
mean 0.4950 (NQ) / 0.4942 (ES), sd 0.166 / 0.158, and per-slot means spanning only
0.4861–0.4998 / 0.4888–0.4979. Subtracting its causal trailing same-slot median
*increases* the variance — the median removes **−2.1% / −2.0%** of it. A trailing
statistic fitted to a constant-plus-noise quantity is worse than no statistic at all.

The drift control (motivated by noise_vwap EXP-0022, where a real sibling-confirmed
up/down band asymmetry merely restated drift and was harmful to act on) did not need to
work, and confirms there is no drift channel either: corr(predicted down-share, trailing
30-minute return) is −0.0004 / +0.0140, and within-slot deltas inside trailing-return
terciles are all within ±0.011.

The identity `fwd_rv_bp² == fwd_dsv_bp² + fwd_usv_bp²` is verified in-run to 2.9e-11 over
41,458 rows, so the legs provably partition the reference target.

**Read:** the same sentence now holds for the volatility FORECAST that the noise-band
programme established for the BAND — the symmetric level is a sufficient statistic and
the up/down split carries nothing. Take downside volatility from the recipe directly;
expect no information from the asymmetry. Evidence: `artifacts/runs/EXP-0014/`.

---

## O. Persistence is a far harder benchmark than seasonality — and the core is a genuine but smaller TIMING instrument (EXP-0015, HYP-0012)

§L measured the core against the causal same-slot median. This measures it against the
benchmark a practitioner would actually default to: `P` = trailing 30-minute realised
vol, built as the strict BACKWARD TWIN of the target (same estimator, same prices, window
ending at the decision bar's own open, so `log(fwd/P)` carries no scale bias — asserted
by `past_rv30_bp[p] == fwd_rv_bp[p−31]`).

**The benchmark reframing, which qualifies §L:**

| within-slot IC vs realised forward RV | NQ | ES |
| --- | --- | --- |
| model `F` | +0.8808 | +0.8740 |
| **persistence `P`** | **+0.8674** | **+0.8610** |
| seasonality `M` | +0.4186 | +0.3830 |

§L's ~+0.47 delta over the same-slot median is **+0.013** over trailing 30-minute RV.
Persistence alone scores log-MSE skill **+0.686 / +0.710** over seasonality; the model's
skill over *persistence* is **+0.187 / +0.148**. §L is not wrong — it was measured against
a weak benchmark. **The levels are nearly all persistence; the deltas are where the model
lives.** Quote both numbers or neither.

**PRIMARY — the model does call the change, and the gate holds.** Within-slot IC between
the predicted log-change `log(F/P)` and the realised log-change `log(A/P)`: **+0.3766
[+0.3690, +0.3841] NQ / +0.3901 [+0.3819, +0.3984] ES**. The preregistered
expansion-only gate — stated in advance because contraction calls after a spike are
nearly free — clears on both: **+0.2201 [+0.2050, +0.2351] / +0.2380 [+0.2240, +0.2520]**.
Against the degenerate control (the same call made by seasonality alone, +0.2403 /
+0.2518) the model's marginal value is **+0.1363 / +0.1383**. Stable across all eleven
years (0.350–0.436) and all eleven slots (0.345–0.421).

**Skill rises monotonically with the size of the disagreement** — the opposite of the
overconfidence failure the hypothesis flagged. NQ by |predicted log-change| decile:

| decile | 1 | 4 | 7 | 10 |
| --- | --- | --- | --- | --- |
| IC(pc, rc) | +0.033 | +0.145 | +0.367 | **+0.643** |
| log-MSE skill vs P | +0.001 | +0.026 | +0.190 | **+0.426** |

The model is most right exactly where it would be used.

**The honest caveat, and the reason it matters.** On expansion calls the *ranking* works
(+0.220 / +0.238) but log-MSE skill over persistence is only **+0.008 (NQ) / +0.061 (ES)**,
against **+0.300 / +0.211** on contraction calls. Nearly all of the error reduction comes
from correctly anticipating decay. The direction-of-change call on expansions transfers;
the magnitude call largely does not. The model calls an expansion 40.0% / 42.2% of the
time, and mean realised log-change on those calls is +0.054 / +0.069, so the calls are
right in sign on average.

**Read:** the core is a timing instrument, not only a calibration instrument, but a
smaller one than §L implied. Its weakest cell is also its most valuable — anticipated
expansion — which makes the scheduled-calendar channel (backlog item 13) a *targeted*
next step with a specific number to beat: expansion-call log-MSE skill over persistence
of +0.008 NQ / +0.061 ES. Evidence: `artifacts/runs/EXP-0015/`.

---

## Synthesis

VEI is not a direction predictor, and as a volatility forecaster it is dominated by the
volatility level. Effective **memory**, not estimator brand, explains Study A; use the
repaired textbook Wilder seed when Wilder is specified, but Wilder(10/50) is not proven
optimal. A fixed VEI=1 or 1.10 line is also not a universal calm/expansion boundary.

§I repairs the last of the construct's three known defects. VEI's fixed `1.10` threshold
was a time-of-day selector (1.5% of the 10:30 slot, 18.4% of 15:30); normalising against
the trailing same-slot distribution removes that entirely and costs no information —
which also settles, for good, the EXP-0005 "de-seasonalising destroys information" claim
as a warm-up-bug artefact. The canonical regime label is now the trailing same-slot
z-score. With the warm-up (EXP-0006), the selection metric (EXP-0008), and the threshold
(EXP-0009) all repaired, any future test of this feature should use it in this form.

§H settles what VEI is *for*. The two candidate roles turn out to be mutually exclusive,
and only one of them is the ratio's: at forecasting volatility the level dominates and
the ratio adds a sliver, while at selecting the momentum regime the level contributes
**nothing** (contrast ≈ 0) and only the ratio carries anything. That also retires the
metric Study A was originally selected on — `IC_fwdvol` scores level-likeness (R² 0.992)
and ranks variants opposite to the primary metric — so no estimator change should be made
on it, and the `wilder_20_100` lead is withdrawn.

The best directional lead remains a **weak, qualified momentum tilt**. EXP-0010 refines
it: fresh, volume-confirmed expansion differs sharply from unconfirmed or mature
expansion in pooled historical returns, but the frozen H=10 strategy still fails daily
risk-adjusted performance and the effect changes materially by era. Volume is therefore
a possible strategy veto/allocator, not a new standalone entry signal.

EXP-0007 closes the tempting explanation that the legacy seed was secretly a better
predictor. It did mechanically encode the opening bar, but that opening component has no
monotone, era-stable, cross-market incremental information and is load-bearing on one
shared zero-range session. The honest verified role for VEI is therefore descriptive
regime labelling and marginal risk information, not established directional alpha.

§K–M then settle the *other* half of the project — the volatility-forecasting side
— and they settle it in opposite directions, which is the cleanest result the project has
produced. The two-input core is not merely accurate in a pooled sense: at a fixed decision
slot it beats the free same-slot median by an IC delta of ~+0.47 on both markets (§L). And
it is still worth **nothing** as a tilt on the existing directional book, because that
book's expectancy is exactly proportional to it (§M). A forecast can be genuinely skilful
and still have no economic application to the strategy you happen to own.

That closes the volatility-as-overlay programme. Across the two projects, five distinct
routes have now been rejected on the noise_vwap book — entry gate, exit cadence, adaptive
stop width, day-level sizing, and now intraday entry-level sizing. §M also supplies the
mechanical reason it keeps happening: the noise-band entry rule is *itself* a volatility
filter, already placing ~35% of its trades in the top forecast quintile, so an overlay is
re-spending information the entry has spent.

§N and §O then closed two of the three directions §M pointed at, and sharpened the third.
§N: the recipe transfers to downside volatility at 92–93% of its total-RV skill, so the
decision-relevant leg is free — but the up/down SPLIT is a constant near one half plus
noise, so there is no asymmetry information anywhere. The symmetric level is a sufficient
statistic for the volatility FORECAST exactly as the noise-band programme found it to be
for the BAND. §O: measured against persistence rather than seasonality, the core's
advantage in ranking LEVELS is small (+0.013, not +0.47) but its call on the CHANGE is
real, both-market, era-stable and strongest exactly where it disagrees most.

Read §K–O together and the project's volatility-forecasting arc has a single shape: the
forecast is skilful in the way a decision maker needs (§L), worth nothing as a tilt on the
book we own (§M), free to extend to the downside leg but with no asymmetry to exploit
(§N), and mostly a restatement of persistence in levels while carrying genuine information
about changes (§O).

Remaining leads: the **scheduled economic calendar** (backlog 13) — now a targeted step
rather than a general one, because §O identifies the exact weak cell it should improve
(expansion-call log-MSE skill over persistence, +0.008 NQ / +0.061 ES); a decision-shaped
barrier/tail-probability target (backlog 15); the daily-timescale squeeze (backlog 4,
deferred by Study C and untouched); and a regime-persistence exit that holds while VEI
stays expanded (backlog 10). The standalone onset strategy, the H=60 axis, volatility
sizing/gating as an overlay, downside-asymmetry, and the disagreement-set diagnostic are
closed as leads.

See `MEMORY.md` and `experiments/IDEA_BACKLOG.md` for the next dimensions.
