# Findings — FX futures VWAP exploration (6E / 6B)

Last updated 2026-08-03 (EXP-0004).

Scope: CME 6E (EUR/USD) and 6B (GBP/USD) futures, Databento `GLBX.MDP3`
`ohlcv-1m` volume-ranked continuous front, CME trade dates **2010-06-07 ..
2023-12-29**. Trade dates in **2024, 2025 and 2026 are a sealed holdout** and have
never been loaded by any analysis script (`scope="explore"` is the loader
default; `scope="holdout"` must be passed explicitly and has been used only to
count withheld sessions).

Everything below is entry-information measurement: no stops, no targets, no
barriers, so no result here can be manufactured by exit geometry (rule 15).
Entry is always the open of the bar *after* the decision bar closes (rules 1, 2).

Headline: **the VWAP framing does not survive.** There is a real short-horizon
reversal on FX futures with a clean liquidity shape, but measuring it through a
session VWAP is strictly worse than measuring it with the trailing return, and
neither is within an order of magnitude of tradable. Separately, the London 4pm
fix leaves a large, month-end-amplified footprint that is confined to the
benchmark's own averaging window.

---

## A — The volume weighting in VWAP is a real operation on FX **futures**, unlike on FX **spot** (EXP-0001, confirmed)

`forex/noise_vwap` established that IBKR cash-FX bars carry no size at all
(`volume == -1` on 100% of 22.0M rows), so every "VWAP" in that project is a TWAP
wearing a VWAP's name. That could not distinguish *"volume does not help"* from
*"volume is not available"*. CME FX futures separate the two.

| | 6E | 6B |
|---|---|---|
| `R_sep` = median \|VWAP−TWAP\| / same-slot dispersion | **0.2592** | **0.2493** |
| median \|VWAP−TWAP\| | 2.6 pip | 3.9 pip |
| `corr(dev_vwap, dev_twap)` | 0.9569 | 0.9582 |
| **anchors put price on opposite sides** | **7.12%** | **7.08%** |

Both clear the pre-declared kill lines (`R_sep < 0.10` or `corr > 0.99`) by wide
margins. Separation grows 7.4-8.0x from the Asia block to `ny_pm` (as the
construction requires) and is stable across all 14 years.

Worth carrying forward: **FX futures volume is *tilted*, not *concentrated*.**
The top 30-minute slot holds 6.2% of session volume against 2.17% under a flat
profile; top four slots 22.8%; HHI only 1.60x flat. That is why `R_sep` is 0.25
and not 1.0, and it undercuts any claim that FX VWAP "is basically the overlap".

This establishes SEPARATION only. Finding B is the information arm.

Evidence: `artifacts/runs/EXP-0001/{review.md, anatomy_6E.txt, anatomy_6B.txt}`.

---

## B — Anchor displacement is a *worse* reversal signal than the trailing return that costs nothing to compute (EXP-0002, confirmed; HYP-0002 REJECTED)

Fade `|dev_z| >= 1.0`, enter `open(m+1)`, exit `close(m+30)`, per-bet mean in pips
with session cluster-robust t:

| anchor | 6E | 6B |
|---|---|---|
| `vwap` | +0.1309 (t +2.66) | +0.0476 (t **+0.72**) |
| `twap` | +0.1391 (t +2.81) | +0.0752 (t +1.14) |
| `open` (degenerate) | +0.0822 (t +1.73) | +0.0747 (t +1.15) |
| `pclose` (degenerate) | +0.0847 (t +1.67) | +0.0492 (t +0.80) |
| **`past30` — NO anchor at all** | **+0.1971 (t +3.92)** | **+0.3836 (t +5.96)** |

All four anchors are statistically indistinguishable from each other — the
degenerate `open` and `pclose` anchors land inside `vwap`'s bootstrap CI on both
products — and **all four are beaten by using no anchor**: fade the trailing
30-minute return, z-scored by the identical causal same-slot construction. 1.5x
better on 6E, **8x** better on 6B.

The partial correlation says the same thing from the other side: `dev_vwap_z`'s
raw rank IC (−0.0298 / −0.0257) roughly **halves** once `past_30` is partialled
out (−0.0146 / −0.0114), while `past_30`'s own IC (−0.0390 / −0.0365) is the
largest in the table.

**HYP-0002 kill-test arms:** sign PASS both; significance FAIL on 6B; shape PASS
both; anchor-specificity FAIL both. Rejected.

Evidence: `artifacts/runs/EXP-0002/{review.md, entryinfo_6E.txt, entryinfo_6B.txt}`.

### B1 — and it is non-tradable regardless of which version you use

| | gross/bet | optimistic round trip | net/bet |
|---|---|---|---|
| 6E 2010-2015 (tick 1.0 pip) | +0.134 pip | 2.0 pip | −1.87 pip (−$23.32) |
| 6E 2016-2023 (tick 0.5 pip) | +0.129 pip | 1.0 pip | −0.87 pip (−$10.89) |
| 6B 2010-2015 | +0.148 pip | 2.0 pip | −1.85 pip (−$11.57) |
| 6B 2016-2023 | −0.015 pip | 2.0 pip | −2.01 pip (−$12.59) |

The round trip assumes a 1-tick-wide market and a fill at the touch on both sides
— the most optimistic model available. Gross is ~8x below it in the best cell.

Rule-19 note made concrete: 6E's outright tick **halved from 0.0001 to 0.00005 in
2016**. The same gross edge went from 15x below cost to 8x below cost with no
change in predictability. A single cost number quoted across this sample is wrong
by 2x on one of the two products.

---

## C — The reversal has a real liquidity shape that survives a volatility-matched split (EXP-0002; EXP-0004 control, confirmed on 6E)

Per-bet mean by liquidity block, H=30:

| block (ET) | `vwap` 6E | `vwap` 6B | `past30` 6B |
|---|---|---|---|
| `asia` 18:00-02:59 | **+0.288** (t +5.18) | +0.115 | +0.204 |
| `ldn_am` 03:00-07:59 | +0.142 | +0.064 | +0.263 |
| `overlap` 08:00-11:59 | **−0.282** (t −1.88) | **−0.300** (t −1.81) | **+0.439** (t +2.67) |
| `ny_pm` 12:00-16:59 | +0.216 | +0.269 | **+0.700** (t +5.04) |

Anchor displacement **reverts** in the thin blocks and **continues** in the
London/NY overlap, on both products (and −0.357, t −2.20 for TWAP on 6B). That is
the shape HYP-0002 predicted from the transitory-inventory account, and it was
the one arm declared in advance as a conditional cell that had to fire.

On **6B** `past30` has the **opposite** profile — its reversion is *strongest* in
`overlap` and `ny_pm` — so on that product the two features are not
interchangeable at every hour even though `past30` dominates pooled.

> **Correction (EXP-0004).** An earlier version of this section generalised that
> sentence to "anchor displacement and short-horizon reversal have opposite
> time-of-day profiles on FX futures". That is **6B-only and does not replicate
> on 6E**, where `past30`'s block profile is near-identical to `vwap`'s
> (`asia` +0.3181, `overlap` −0.1841 raw; +0.5336 vs `vwap`'s +0.5657 after the
> volatility-matched control). The dissociation claim is narrowed to 6B.

### C1 — the volatility-matched control (EXP-0004, HYP-0004 NOT rejected)

The block split is matched on time of day only — trivially, since the blocks
*are* time-of-day windows — and LEARNINGS 2026-07-31c showed such a split can
still inherit a volatility gradient that is doing all the work. There it
collapsed a comparable contrast from +0.0496 to −0.0047. The confound is real
here and large: mean `rv_60` (mean absolute 1-minute change over the 60 minutes
ending at `close(m)`, causal, sharing no print with the entry) runs
0.86 → 1.89 pip/min across the blocks on 6E and 1.11 → 2.21 on 6B.

`asia` − `overlap` contrast for `vwap`, recomputed within quintiles of `rv_60`
on common support (harmonic weights, no extrapolation):

| | 6E | 6B |
|---|---|---|
| `C_raw` | +0.5300 | +0.3776 |
| **`C_adj`** | **+0.5657** [+0.2302, +0.8952] | **+0.2210** [−0.4120, +0.8096] |
| retained | **106.7%** | 58.5% |
| volatility ratio asia/overlap, raw → adjusted | 0.453 → **0.904** | 0.523 → **0.998** |
| effective bet count retained | 65.0% | 59.7% |

The last two rows are what make the first three readable (LEARNINGS 2026-07-31c):
the cells' volatility ratio moved most of the way to 1 while the effective sample
held up, so the split was genuinely **matched, not merely weakened**. Invariant
across 3 stratum counts, a non-overlapping volatility window (`rv_lag_60`, minutes
`(m−90, m−30]`) and a looser coverage floor: `adj/raw` spans +0.97..+1.16 on 6E
and +0.55..+0.95 on 6B, 18 declared cells each, none selected on.

**Mirror arm — and the two products disagree about which label carries it.** The
volatility contrast `q5 − q1` standardised *within* blocks:

| | raw | within-block | reading |
|---|---|---|---|
| 6E | −0.3455 | **+0.1332** | volatility dies once block is fixed → block is the operative label |
| 6B | −0.3439 | **−0.5370** | volatility *strengthens* once block is fixed → volatility is |

So both products agree the block contrast is not *caused* by volatility, and
disagree on the mechanism. On 6B it is the *volatility* label that survives
conditioning, and 6B's block contrast is underpowered. Note also the
unconditional block-free view points the other way on both — across the 43
decision slots, Spearman(mean `rv_60`, mean per-bet pip) = **−0.4305 / −0.1711** —
which is exactly why the pooled table could not settle this.

Status: **confirmed on 6E** (the block shape is not a volatility artifact);
**provisional on 6B**, where the contrast is directionally consistent but its CI
spans zero and the mirror arm favours volatility. The transitory-inventory
*mechanism* read off 6E's mirror arm is **superseded by finding H**: EXP-0005
weakened both the ET-clock and the crude block-volume accounts, so what the block
label proxies for is currently **open**. It remains non-tradable either way: `asia` is both the block
with the largest gross and the block with the widest spread, and +0.2883 pip/bet
is ~3.5x under the most optimistic post-2016 6E round trip.

Rule-9a note: `rv_60` needs both minutes of each 1-minute change, so its pairwise
coverage is roughly the square of per-minute coverage and it deleted **29.7% of
6B's `asia` decisions against 0.1% of `overlap`** — finding G on a new statistic,
selective in the worst direction (it removes the quietest decisions of the
thinnest block). Sized and shown not to matter: a 0.25 coverage floor cuts the
across-block spread 0.296 → 0.150 and moves `C_adj` by +0.03 pip.

Evidence: `artifacts/runs/EXP-0004/{review.md, volstrat_6E.txt, volstrat_6B.txt}`.

---

## D — Two measurement artifacts sized on this data, both larger here than previously recorded (EXP-0002, confirmed)

**D1. The shared-decision-bar artifact.** Entering at `close(m)` — sharing a print
with the feature — instead of `open(m+1)`:

| | naive `close(m)` | honest `open(m+1)` | retained |
|---|---|---|---|
| 6E | +0.4038 (t +6.68) | +0.1309 (t +2.66) | **32.4%** |
| 6B | +0.3793 (t +4.98) | +0.0476 (t +0.72) | **12.5%** |

LEARNINGS 2026-07-31d measured 31-56% retained at a 5-minute horizon on
NQ/ES/GC. This is a *worse* case at a **30-minute** horizon on a new asset class:
on 6B, seven-eighths of the measured reversal is the shared print. Any FX-futures
reversal quoted without this control is inflated by 3-8x.

**D2. The endogenous-signal-count estimand trap, reproduced.**

| | per-signal mean (deployable) | session-averaged | `corr(session mean, count)` |
|---|---|---|---|
| 6E | +0.1309 (t +2.66) | **+0.7769 (t +15.92)** | **−0.461** |
| 6B | +0.0476 (t **+0.72**) | **+1.0299 (t +15.06)** | **−0.474** |

Session-averaging turns 6B's null into a t≈15 blockbuster. Note the correlation is
**negative** here — sessions with *few* signals have *high* mean P&L — the
opposite sign from the FX-spot and NQ/ES cases, and it manufactures the same
spurious result. The sign of `corr(mean, count)` does not matter; its magnitude
does.

---

## E — The London 4pm fix leaves a large, month-end-amplified footprint that beats every placebo hour (EXP-0003, confirmed as a footprint, NOT as an edge)

Fade the 30-minute pre-fix drift, entry `open(f+2)`, hold 30 minutes, with the fix
minute taken from the **Europe/London** clock (it is 12:00 ET, not 11:00, on 6.1%
of sessions — the US/UK daylight-saving shoulder weeks; using the naive 11:00
understates the 6B result by 35%):

| | 6E | 6B |
|---|---|---|
| per-bet | +0.9053 (t +2.48) | +1.5516 (t +3.54) |
| vs 21 placebo hours | beats **100%** | beats **100%** |
| month-end | +1.365 | **+5.052** (t +3.08) |
| non-month-end | +0.869 | +1.271 |
| pre-fix mean \|drift\| month-end vs other | 15.3 vs 9.9 pip | 23.6 vs 12.7 pip |

Three of four preregistered arms pass cleanly, including the decisive placebo-hour
arm on both products and a 4x month-end amplification on 6B exactly where index
rebalancing concentrates. The Melvin-Prins month-end signature is visible in the
raw pre-fix drift magnitude too (+55% / +85%).

---

## F — …and the entire footprint is *inside* the benchmark's own averaging window, so it is not tradable (EXP-0003, confirmed; HYP-0003 REJECTED)

Arm 4 was preregistered to show the effect **shrinking** after WM widened the fix
window from 1 to 5 minutes on **2015-02-15**. It inverted: the whole effect is
post-2015 (6E −0.000 → +1.364; 6B −0.108 → +2.408). That inversion prompted two
boundary controls, which explain all four arms at once.

**Entry-lag sweep** (per-bet, all sessions):

| entry | 6E | 6B |
|---|---|---|
| f+2 (16:02 London) | +0.905 | +1.552 |
| **f+3 (16:03 London)** | **−0.060** | **+0.278** |
| f+5 | −0.025 | +0.356 |
| f+30 | +0.025 | −0.646 |

**Holding-horizon sweep at a fixed f+2 entry:**

| hold | 6E | 6B |
|---|---|---|
| **1 min** | **+0.847 (t +4.43)** | **+1.320 (t +7.02)** |
| 30 min | +0.905 (t +2.48) | +1.552 (t +3.54) |

The one-minute bet captures the entire 30-minute result at a *higher* t-statistic,
and moving the entry one minute later destroys it.

**The diagnosis.** Before 2015-02-15 the fix window was 1 minute
(15:59:30-16:00:30), so by 16:02 it was long over — pre-2015 effect zero. After
2015-02-15 it runs to **16:02:30**, so the minute 16:02-16:03 is the *last minute
of the benchmark window itself*. The measurement is detecting price impact
reverting **inside** the benchmark's averaging window, not after it. Arm 4 failed
in the wrong direction precisely because the widening moved the window's end
*past* the chosen entry.

Harvesting this would mean being filled inside the benchmark window, against the
flow that defines the benchmark, on 1-minute OHLC that cannot establish the fill
sequence within that minute (rules 1, 3). At any honest entry — f+3 onward — the
effect is zero. The literature's pre-fix drift and post-fix reversal are not
contradicted; what is refuted is that a bar-resolution study can harvest them.

Caveat carried from the review: the month-end amplification in finding E is
established for the *in-window* quantity only. It has not been re-tested at f+3,
where the effect is zero.

Evidence: `artifacts/runs/EXP-0003/{review.md, fix_6E.txt, fix_6B.txt}`.

---

## G — Data-quality findings that changed a construction choice (rule 9a)

Full report: `reports/DATA_QUALITY.txt` (`scripts/data_quality.py`).

Both archives are clean on the basics: 0 duplicate timestamps, 0 out-of-order
timestamps, 0 OHLC ordering violations, **0 zero-volume bars**, and ~0 bars inside
the 17:00-18:00 ET maintenance halt.

The one reportable defect is a **liquidity-driven, time-of-day-selective deletion
on 6B**, the GC lesson repeating on a new instrument. 6B's Asia-hours minute
coverage is 0.71-0.84 against 6E's 0.89-0.96. With the conventional
`lookback=60, min_periods=2/3`, the same-slot scale was undefined for **35% of
6B's 18:00 ET decisions against 1% of its London decisions** — a hidden filter
that tracks time-of-day liquidity. Moving to **`lookback=90, min_periods=1/2`**
keeps the same 45-session estimator floor and cuts the worst-hour deletion to
4.8% and the across-hour spread from 0.342 to **0.035**. That is the setting used
by every result above, and the reason is recorded in `core/vwap.py`.

Also checked and *ruled out*: the low-coverage minutes are **not** concentrated on
any minute-of-hour (top counts 9/8/8 of 355 on 6E; 12/12/12 of 662 on 6B), so
unlike the IBKR spot archives this is genuine illiquidity rather than a download
chunk-boundary artifact.

Contract economics recorded for rule 19: 6E 125,000 EUR, $12.50/pip, **tick
halved 0.0001 → 0.00005 in 2016**; 6B 62,500 GBP, $6.25/pip, tick constant.

---

## H — A third product (6J) cannot settle *why* the block shape exists, but it rules out two accounts (EXP-0005, HYP-0005 INCONCLUSIVE)

Finding C1 showed the block shape is not a volatility gradient. It could not say
what the block label is a proxy for, because 6E and 6B have the same intraday
liquidity clock (asia/overlap volume intensity **0.129 / 0.132**). 6J is a
different dose — the yen leg trades in Tokyo, so its ratio is **0.314**, 2.4x less
thin.

Risk-equalised (P&L over the decision's own same-slot displacement scale, the
equal-risk estimand of rule 12 — native units are never compared across products):

| product | `asia`−`overlap` R_adj | boot95 CI |
|---|---|---|
| 6E | +0.0589 | [+0.0178, +0.0997] |
| 6B | +0.0073 | [−0.0677, +0.0712] |
| **6J** | **−0.0038** | [−0.0331, +0.0255] |

Preregistered verdict: **arm 3, inconclusive.** `R(6J)` is −0.11× the benchmark —
the point estimate is marginally *inverted*, not merely attenuated — but its CI
contains both zero and the 0.60× gate. The kill test's benchmark was half-built
from 6B, whose own contrast is indistinguishable from zero, which halved its
power. That is a design fault, recorded as such.

**What the run did establish.** Two accounts are weakened by arms that had power:

- **H_clock (it's the ET hours) is weakened.** `R(6E) − R(6J) = +0.0627`
  **[+0.0103, +0.1107], CI excludes zero**, and the benchmark lies outside `R(6J)`'s
  interval. In the block-free view, 6E and 6B share a liquidity clock so their
  per-slot rank correlation (**+0.6458**) is the benchmark for what "the clock
  explains it" looks like; 6J reaches only **+0.2825** / **+0.4889**. (Pearson is
  flat at +0.69..+0.76 across all three pairs, so this is a rank-view finding
  only — reported both ways per LEARNINGS 2026-07-31a.)
- **H_liquidity in its crude block-volume form is also weakened.** 6J's `ny_pm`
  block has volume intensity **0.82x, identical to 6E's 0.80x and 6B's 0.82x**,
  yet carries 6J's *strongest* reversion (+0.0207, t +3.2) against their +0.0069 /
  +0.0104. Same CME volume, 2–3x the effect: **total contract volume is not the
  operative liquidity measure.**

### H1 — the pattern that fit all twelve cells, and died on four fresh products (EXP-0007, HYP-0007 REJECTED)

> **Superseded by EXP-0007.** The table below is retained as the record of what
> generated IDEA-0008. It was tested on 6A/6C/6N/6S — four products never
> previously loaded — and **rejected in the wrong direction**. See §H2.

| product | counter-ccy home | its night block | R there | `overlap` cell |
|---|---|---|---|---|
| 6E | Frankfurt/London | `asia` | +0.0522 (t +4.7) | −0.0153 (t −2.0) |
| 6B | London | `asia` | +0.0202 (t +1.2) | −0.0159 (t −2.2) |
| 6J | Tokyo | `ny_pm` | +0.0207 (t +3.2) | −0.0151 (t −1.8) |

Every product's strongest reversion sits in the block where the **counter
currency's own home market is shut** — and ET 12:00–16:59 (`ny_pm`) is Tokyo
02:00–07:00 while ET 18:00–02:59 (`asia`) is London 23:00–07:59, so these are the
same rule in different time zones. The `overlap` cell, the one block where *both*
home markets are open, is near-identical on all three.

Not tradable on 6J either: `C_adj` +0.0516 units = **$0.65/bet** against a
$12.50 round trip, ~19x under cost and worse than 6E.

Evidence: `artifacts/runs/EXP-0005/{review.md, liqclock.txt}`.

---

## H2 — the home-market account is REJECTED on fresh products (EXP-0007, HYP-0007)

IDEA-0008's prediction was preregistered from each currency's own time zone —
uniform 08:00-17:00 local, Mon-Fri, real DST, **no free parameters** — and tested
on **6A, 6C, 6N, 6S, four products never previously loaded**. 6E/6B/6J generated
the hypothesis and were excluded from the primary (rule 26).

Pooled within-product-demeaned Spearman(home-market openness, risk-equalised
reversion) across 46 decision slots. H_home predicts **negative**:

| sample | rho |
|---|---|
| consumed three — the sample that generated it | **−0.2342** |
| **fresh four — the test** | **+0.0526** (circular-shift null p = **0.710**) |

**The pattern exists only where it was found.** Both kill-test arms fail: wrong
sign, and nowhere near the null.

| product | `asia` | `ldn_am` | `overlap` | `ny_pm` | best | predicted | hit |
|---|---|---|---|---|---|---|---|
| 6E | +0.0522 | +0.0119 | −0.0153 | +0.0069 | asia | ny_pm | no |
| 6B | +0.0202 | +0.0002 | −0.0159 | +0.0104 | asia | asia | YES |
| 6J | −0.0024 | −0.0021 | −0.0151 | +0.0207 | ny_pm | overlap | no |
| **6A** | **+0.0423** | −0.0024 | −0.0046 | +0.0137 | **asia** | ldn_am | **no** |
| **6C** | +0.0259 | +0.0133 | +0.0075 | +0.0169 | asia | asia | YES |
| **6N** | −0.0040 | −0.0059 | −0.0021 | +0.0073 | ny_pm | ldn_am | no |
| **6S** | +0.0258 | +0.0147 | +0.0053 | +0.0084 | asia | ny_pm | no |

**6A is the decisive counterexample.** Sydney is *open* during `asia` (openness
0.842, second highest in the panel) and `asia` is 6A's **strongest** reversion
block. Block-level Spearman **+0.9487, exact p = 1.000** — the maximum possible
score in the wrong direction. Under H_home, 6A should have resembled 6J; it
resembles 6E.

**The argmax evidence that generated the idea was a base-rate illusion.** `asia`
is the best block for **5 of 7 products (71%)**, so "predicting `asia`" is nearly
free. Fresh argmax agreement is 1/4, and the *expected* count under the observed
marginal is **1.00 against 1 observed** — zero information. The original 3/3
should never have been read as p ≈ 1/64. **Score an argmax hit rate against the
modal-category base rate, not a uniform null.**

Volatility does not rescue it (fresh +0.0211 → +0.0055 partialled).

**What this leaves.** `asia` wins for 5 of 7 products regardless of home time
zone, which is closer to the ET-clock account. EXP-0005's finding that products
genuinely *differ* still stands — 6J and 6N are the exceptions, with negative
`asia` cells — but they do not differ as home-market hours predict. Finding C's
mechanism is **open, with the leading candidate now eliminated**.

Rule-9a note: 6N and 6S are materially thinner (bar coverage 0.758 / 0.798 vs
6E's 0.971), so they are the least powered cells. The two best-covered fresh
products, 6A and 6C, sit at opposite ends of the openness range and split 1-1.

Evidence: `artifacts/runs/EXP-0007/{review.md, homemkt.txt}`; `core/home.py`.

---

## K — the cost floor, now on seven products

Each product's **best** block, native units, against the most optimistic
post-2016 round trip (1-tick market, fill at the touch both sides):

| | 6E | 6B | 6J | 6A | 6C | 6N | 6S |
|---|---|---|---|---|---|---|---|
| net $/bet | −8.90 | −11.78 | −7.35 | −8.25 | −9.07 | −8.72 | −10.93 |

Seven of seven, $7-12 under cost per bet, in the single most favourable cell each.
The project's NO-GO is no longer a two-product result.

Rule-19 note now at full scope: **six of the seven products changed tick
mid-sample** — 6C and 6E in 2016, 6J in 2015, 6A in 2020, 6N in 2021, 6S in 2022
(all verified against the price grid, not assumed). A cost quoted in ticks across
this sample is wrong on six of seven.

---

## I — RSI(14) is a re-normalised trailing return, and its normaliser is worse than the project's (EXP-0006, HYP-0006 REJECTED)

RSI is not a new quantity. With `U−D = dp`, `U+D = |dp|` and a linear smoother,

    RSI(n) = 50 + 50 · A_n(dp) / A_n(|dp|)

exactly (verified to 3e-14 in `tests/test_core.py`) — a smoothed trailing return
over a trailing absolute-return volatility. **On this project's 30-minute decision
grid the increments `dp` ARE `past_30`**, so RSI(14) is a differently-*normalised*
sibling of finding B's incumbent.

Per-bet means at a matched ~11% selection rate, on a common sample where all four
signals and `fwd_30` are defined on identical rows:

| signal | 6E | 6B | 6J |
|---|---|---|---|
| `rsi_14` (70/30) | +0.1099 (t +1.13) | −0.0526 | −0.0173 |
| `rsi_num_14` — bare NUMERATOR | +0.1148 | −0.1515 | +0.1235 |
| **`dev_past30_z` — INCUMBENT** | **+0.2306 (t +2.03)** | **+0.2462 (t +1.54)** | **+0.0332** |
| `past_30` raw | +0.0415 | +0.4621 (t +2.98) | +0.0561 |

**The incumbent beats RSI on all three products** (kill-test arm 3, failed 3/3).
RSI also fails to beat its own bare numerator on 6E and 6J; on 6B it is "better"
only by being less negative, which is a technical pass and a substantive failure.

**The ratio is barely a ratio.** corr(RSI, its own numerator) = **+0.9732** (6E) /
+0.9693 (6J); corr(RSI, its own denominator) = **+0.0144** / +0.0908. The
denominator does almost nothing to the ranking — LEARNINGS 2026-07-27's
degenerate-numerator result on a new feature.

### I1 — why: a fixed 70/30 cut is a time-of-day selector

RSI's denominator is a *trailing window*, so it lags volatility transitions and
reaches its extremes more easily once activity picks up. The incumbent's is a
causal *same-slot* dispersion — the construction that exists to prevent exactly
this (LEARNINGS 2026-07-27).

| | 6E | 6B | 6J |
|---|---|---|---|
| per-slot selection-rate CV, RSI 70/30 | 0.3637 | 0.3331 | 0.2226 |
| per-slot selection-rate CV, incumbent | 0.0639 | 0.0600 | 0.0632 |
| **ratio** | **5.69x** | **5.55x** | **3.52x** |
| worst/best slot rate, RSI vs incumbent | 4.1x vs 1.3x | 4.0x vs 1.3x | 2.3x vs 1.3x |

The 70/30 cut fires **6.40% in `asia` against 16.07% in `overlap`** on 6E, while
the incumbent is flat near 11% everywhere. The extreme slots are `mfo` 479 (ET
01:59, deep Asia) and 989/1019 (ET 10:29/10:59, the overlap) — the prediction
written into HYP-0006 before the run.

**And it is miscalibrated in the worst possible direction for this market**:
finding C establishes that displacement *continues* in the `overlap`, so a fixed
70/30 threshold concentrates its bets in the one block where fading loses. RSI is
less a weak signal here than a badly calibrated *selector* applied to a signal the
project already selects on properly. Note 6J — the product with the flattest Asia
liquidity profile (finding H) — has the mildest miscalibration, so the defect
tracks the gradient causing it.

What RSI *does* have: its 14-period smoothing is a real extra dimension. The
partial rank IC controlling for `past_30` retains **62.6% / 51.2% / 50.9%** — the
one arm it passes on all three products.

Not tradable: 6E gross +0.1349 units against a 2.0-unit optimistic round trip
= **−$23.31/bet** pre-2016, −$11.32/bet after.

Evidence: `artifacts/runs/EXP-0006/{review.md, rsi_6E.txt, rsi_6B.txt, rsi_6J.txt}`.

---

## J — A recursive feature's gap damage is DISPLACED by its memory length (EXP-0006, extends finding G)

Finding G established that a windowed feature's coverage rule can be a hidden,
time-of-day-selective filter. A *recursive* feature is worse: a missing bar does
not cost one decision, it costs `n` more while the recursion rebuilds — and on a
30-minute grid `n=14` is about **seven hours**, so the deletion lands in a
different block from the gap that caused it.

| 6E block | missing bars | RSI coverage, `bridge` | RSI coverage, `reset` |
|---|---|---|---|
| `asia` | 5.78% | 0.9418 | **0.5773** |
| `ldn_am` | **0.25%** | 0.9975 | **0.7305** |
| `overlap` | 0.07% | 0.9993 | 0.9782 |
| `ny_pm` | 2.83% | 0.9717 | 0.9544 |

`ldn_am` has almost no gaps of its own and the second-worst coverage, because
Asia's gaps are still rebuilding when London opens. **Per-block gap counts do not
predict per-block coverage for a recursive feature.**

Fix: take increments between consecutive *available* closes within a run
(`gap_policy="bridge"`) rather than resetting. Across-block coverage spread
**0.4010 → 0.0575** on 6E and **0.7255 → 0.1835** on 6B. Generalises to any
recursive feature — EMA, Wilder ATR, Kalman filters — on a grid with holes.

---

## Status summary

| ID | Claim | Status |
|---|---|---|
| A | Volume weighting is non-degenerate on FX futures (unlike spot) | confirmed |
| B | Anchor displacement is beaten by the bare trailing return; HYP-0002 rejected | confirmed |
| B1 | Non-tradable, ~8x below the most optimistic cost floor | confirmed |
| C | Reversion in thin blocks, continuation in the overlap | **confirmed on 6E**, provisional on 6B (EXP-0004) |
| C1 | …and it is not a volatility gradient: `C_raw` +0.530 → `C_adj` +0.566 on 6E at a matched volatility ratio of 0.90 | confirmed on 6E |
| C2 | The `past30` dissociation is **6B-only**; on 6E `past30` has the same block profile as `vwap` | **corrected** (was stated as a cross-product claim) |
| D1 | Shared-print artifact worth 68% / 88% of the naive estimate | confirmed |
| D2 | Session-averaging manufactures t≈15 from a null | confirmed |
| E | London fix footprint: beats 100% of placebo hours, 4x at month-end | confirmed as a footprint |
| F | The footprint is inside the benchmark window; HYP-0003 rejected | confirmed |
| G | 6B Asia coverage forces `lookback=90, min_periods=1/2` | confirmed |
| H | 6J cannot settle *why* the block shape exists — the kill test was underpowered | **inconclusive** (EXP-0005) |
| H1 | …but H_clock and crude block-volume H_liquidity are both weakened; the mechanism behind finding C is **OPEN** | confirmed as a negative |
| H1 | The counter-currency home-market pattern (3/3 products) | **superseded** — it was a base-rate illusion, see H2 |
| H2 | …and it is REJECTED on four fresh products: generating sample −0.234, fresh +0.053 wrong-signed, 6A an outright counterexample | confirmed (HYP-0007 rejected) |
| K | Seven of seven products are $7-12 under cost per bet in their best cell; six of seven changed tick mid-sample | confirmed |
| I | RSI(14) = 50 + 50·A(dp)/A(\|dp\|); loses to the incumbent 3/3 and to its own numerator 2/3 | confirmed (HYP-0006 rejected) |
| I1 | Its fixed 70/30 cut is a time-of-day selector — per-slot CV 3.5-5.7x the incumbent's, concentrated in the block where fading loses | confirmed |
| J | A recursive feature's gap damage is displaced by its memory length; per-block gap counts don't predict per-block coverage | confirmed |

**Project verdict: NO-GO for a VWAP-based FX futures strategy on this evidence.**
The holdout (2024-2026) remains sealed and unspent — there is nothing here worth
spending it on.
