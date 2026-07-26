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

**Open lead, flagged not adopted.** `wilder_20_100` scores far higher than everything else
(IC **+0.396 NQ / +0.353 ES** at the same 37099 decisions as the 19/99 cells, AC1 0.685,
whipsaw 0.15), and IC rises monotonically with memory across every cell. Do **not** adopt
it on that basis yet: section B shows the vol LEVEL predicts forward vol at IC +0.86, so
lengthening the numerator's memory makes VEI progressively more level-like, and
`IC_fwdvol` may simply be rewarding "less of a ratio". **`IC_fwdvol` is a poor selection
metric for a ratio feature** — Study A's original metric choice is itself suspect, and a
metric that is not monotone in "how much this ratio resembles the level" is needed before
any estimator change. Canonical stays Wilder(10/50), repaired.

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

---

## Synthesis

VEI is not a direction predictor, and as a vol *forecaster* it is dominated by the vol
level. Its real, cross-market-consistent value is as a **momentum regime switch**: the
tape trends when vol expands and is a random walk otherwise. The single most important
practical correction is the **estimator** — use Wilder ATR, not rolling-mean, or VEI
is mostly noise.

Study D's momentum switch was then promoted to a preregistered strategy (E / EXP-0004):
the mechanism **confirmed** cleanly (gross dose-response high ≫ low, cross-market), but
the per-trade tilt is **too small to monetize** — daily Sharpe ≈0, sub-cost. So VEI's
honest, verified role is diagnostic/regime-labelling and (marginally) risk — not a
standalone directional edge.

Study F (EXP-0005) then stress-tested the one surviving mechanism and it held. The
obvious alternative explanation — that `VEI>1.10` is really just "it is late in the
session", since ~88% of high-VEI decisions fall after 14:00 — is **rejected on both
markets**: matching time of day leaves the contrast at 106% / 105% of its pooled size.
The regime switch is a genuine volatility property. Two corollaries change how VEI should
be used: its information lives in the **absolute level** (de-seasonalising it makes it
worse, not better), and the predictability is **front-loaded** at 5–30 minutes rather
than strengthening with hold — so Study E's H=60 lead is cost amortisation, not a longer
trend. Combined with F2 (no VR difference), the sharpest statement of what VEI does is:
*it tilts the drift of the next ~30 minutes toward the last 30 minutes' direction, and
changes nothing else about the path.*

Remaining leads, none started: the daily-timescale squeeze (backlog 4, deferred by Study
C and untouched), expansion onset vs late-chase and volume participation (backlog 8, the
"what kind of expansion" split), a regime-persistence exit that holds while VEI stays
expanded (backlog 10), and VEI as a gate on an existing momentum book rather than
standalone (backlog 3/7). The H=60 axis is now closed as a lead.

See `MEMORY.md` and `experiments/IDEA_BACKLOG.md` for the next dimensions.
