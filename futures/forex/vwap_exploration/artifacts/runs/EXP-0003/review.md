# EXP-0003 Results Discussion

- Hypothesis: `HYP-0003` — The WM/Reuters 16:00 London fix leaves a tradable post-fix reversal, amplified at month-end and damped by the 2015-02-15 window widening
- Status: completed
- Builder: Claude (Opus 5)
- Reviewer: Claude (Opus 5), self-review — no second model available this session
- Primary metric: per-bet mean pip of fading the pre-fix drift over sessions with |pre_z|>=1.0, session cluster-robust SE + block-bootstrap CI
- Kill test: Rejected if ANY of: (1) not positive with |t|>=2 on both products; (2) does not exceed the 90th percentile of the same statistic at every other candidate hour, on both; (3) month-end not larger than non-month-end on both; (4) not larger before 2015-02-15 than after, on both.

## Result versus hypothesis

**REJECTED on arm 4 — and the way it fails is the finding.**

| arm | 6E | 6B | verdict |
|---|---|---|---|
| 1. fade pays, \|t\|≥2 | +0.9053 pip, t +2.48 | +1.5516 pip, t +3.54 | PASS |
| 2. beats >90% of placebo hours | beats **100%** | beats **100%** | PASS |
| 3. month-end > other | +1.365 vs +0.869 | **+5.052** (t +3.08) vs +1.271 | PASS |
| 4. larger BEFORE 2015-02-15 | **−0.000 vs +1.364** | **−0.108 vs +2.408** | **FAIL, inverted** |

Arms 1-3 pass cleanly and would, on their own, read as a textbook confirmation:
a fade that pays, at an hour named in advance by the benchmark's published
methodology, beating every one of 21 placebo hours on both products, amplified
4x at month end exactly where index-rebalancing flow concentrates (and with the
pre-fix drift itself 55% / 85% larger on those days).

Arm 4 was preregistered to go the other way — WM widened the fix window to dilute
the concentration of benchmark trading, so the effect should have *shrunk* after
2015-02-15. Instead the entire effect is **post**-2015 and there is nothing at all
before it, on both products.

That inversion is what prompted the two sensitivity controls below, and they
diagnose it completely.

## Gross, net, baseline, and null comparison

No null was spent: the effect is fully explained by the controls below, so a null
would answer a question that no longer needs asking.

Costs, for completeness: 6E 2016-2023 gross +1.229 pip/bet against a 1.0 pip
optimistic round trip (net +$2.86); 6B 2016-2023 gross +2.627 against 2.0 pip
(net +$3.92). Pre-2016 both are negative net. So even taken at face value this is
roughly a coin-flip against the most optimistic cost model available — and it is
not to be taken at face value.

## Regimes, sensitivity, and alternative explanations

**The entry-lag control kills it.** The entry was `open(f+2)`, chosen because the
post-2015 fix window runs to 16:02:30 London — but 16:02:00 is *inside* that
window, not after it.

| entry | 6E all | 6E pre-2015 | 6E post-2015 | 6B all | 6B pre-2015 | 6B post-2015 |
|---|---|---|---|---|---|---|
| f+2 | +0.905 | −0.000 | +1.364 | +1.552 | −0.108 | +2.408 |
| **f+3** | **−0.060** | −0.767 | +0.298 | **+0.278** | −0.706 | +0.779 |
| f+5 | −0.025 | −0.256 | +0.092 | +0.356 | +0.020 | +0.527 |
| f+10 | −0.314 | −0.288 | −0.328 | +0.189 | +1.126 | −0.292 |
| f+30 | +0.025 | +0.506 | −0.218 | −0.646 | −0.047 | −0.954 |

Moving the entry one minute later — from 16:02 to 16:03, fully outside the widest
published window in either era — destroys the effect on both products.

**The holding-horizon decomposition confirms it is literally one minute.** Holding
the entry at f+2 and shortening the exit:

| hold | 6E | t | 6B | t |
|---|---|---|---|---|
| **1 min** | **+0.847** | **+4.43** | **+1.320** | **+7.02** |
| 5 min | +1.051 | +4.23 | +1.666 | +6.25 |
| 30 min | +0.905 | +2.48 | +1.552 | +3.54 |

The one-minute bet captures the whole 30-minute result with a *higher* t-statistic.
Everything after 16:03 London is noise being added to a fixed quantity.

**All four observations then have one explanation.** Before 2015-02-15 the fix
window was 1 minute (15:59:30-16:00:30), so by 16:02 it was long over and there
was nothing to capture — the pre-2015 effect is zero. After 2015-02-15 the window
runs to 16:02:30, so the minute 16:02-16:03 is the *last minute of the benchmark
window itself*. The measurement is not detecting a post-fix reversal; it is
detecting price impact reverting **inside the benchmark's own averaging window**.
Arm 4's inversion is not a mechanism failure — it is the signature of the
measurement window overlapping the widened benchmark window, and the arm failed in
the wrong direction precisely because the widening moved the window's end past the
entry point.

**Arm 2b (placebo split by era) rules out the obvious alternative.** If the whole
tape simply became more reversionary after 2015, the fix would not stand out
within its own era. It does: post-2015 the fix beats 95% (6E) / 100% (6B) of
placebo hours, while pre-2015 it beats 50% / 30% — an ordinary hour.

**DST control.** The Europe/London fix clock puts the fix at 12:00 ET on 6.1% of
sessions (the US/UK daylight-saving shoulder weeks). Using it rather than a
hardcoded 11:00 ET raises the estimate from +0.839→+0.905 (6E) and +1.153→+1.552
(6B) — a 35% understatement on 6B from a one-line timezone shortcut.

**Why this is not tradable even if one wanted to.** Capturing it requires being
filled inside the benchmark's own averaging window, competing with exactly the
flow that defines the benchmark, on 1-minute OHLC that cannot establish the fill
sequence within that minute (rules 1, 3). At any entry a research setup can
honestly claim — f+3 onward — the effect is zero.

## Artifact and implementation risks

- A bug found and fixed during the run: masking `pre` before computing the causal
  90-session trailing scale left scattered subsets (month-end is 1 session in 21)
  with an almost entirely NaN window, so the month-end arm silently returned "too
  few events" on the first pass. The mask is now applied *after* the scale is
  computed on the full series (`_bet_stats(..., mask=)`), and the arm computes.
  Anyone reading a subgroup result off a rolling-window feature should check this.
- The fix minute is derived from `Europe/London`, not assumed.

## Builder interpretation

The London fix leaves a large, cross-product, month-end-amplified, placebo-beating
footprint on FX futures — and it is confined to the benchmark's own averaging
window, which is exactly where a benchmark's footprint should be and exactly where
it cannot be traded. The literature's pre-fix drift and post-fix reversal are not
contradicted; what is refuted is that a bar-resolution study can harvest them.

Methodologically this is the run's real output: **a preregistered arm that failed
in the *wrong direction* was more informative than the three that passed.** Had
arm 4 simply come out flat, the natural reading would have been "mechanism
uncertain, effect real" and the boundary controls would never have been run.

## Independent review

- Review status: self-reviewed; no second model this session.
- Objections: (a) `f+2` was chosen as "the first minute outside the widest window"
  and is off by one — the window closes at 16:02:30, so the first fully-clear
  entry is `f+3`. That error is what produced the apparent edge, and the sweep is
  what caught it; the write-up should not be read as if `f+2` were ever a valid
  entry. (b) Arm 3 (month-end) passes on the contaminated `f+2` entry and has not
  been re-tested at `f+3`, where the effect is zero — so the month-end
  amplification is established for the *in-window* quantity only, not for a
  tradable one. It is reported as an amplification of the benchmark footprint, and
  not as a surviving edge.
- Verdict: **rejected as a tradable effect; accepted as a positive identification
  of the benchmark window.**

## Promotion decision

- `reports/FINDINGS.md`: promoted as findings E, F.
- `MEMORY.md`: promoted (NO-GO verdict + the window-boundary diagnosis).
- Shared `LEARNINGS.md`: promoted — the "measurement window overlapping an
  institutional window" failure mode and the wrong-direction-arm lesson are
  cross-project.
