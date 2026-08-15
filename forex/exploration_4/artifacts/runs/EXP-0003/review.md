# EXP-0003 review — Stage-A addendum: same-slot normalisation

- **Pre-spec:** `experiments/hypotheses/HYP-0003.md`, frozen before the run, with all
  four decision rules written in advance.
- **Config:** `baseline_replication/configs/same_slot.json`
- **Command:** `python -u forex/exploration_4/_run_same_slot.py` (~3 min)
- **Tests:** `python -m pytest forex/exploration_4/test_stage_a.py -q -p no:cacheprovider` — 25 passed.
- **Builder:** Claude. **Reviewer:** unassigned. **Review status:** pending.
- **Numbering:** the run-book assigns EXP-0003 to Stage B; the ledger requires
  `EXP-\d{4}`, so this addendum is EXP-0003 and **Stage B becomes EXP-0004**.

---

## 1. Answers to the four pre-committed questions

**Q1 — Does the normaliser work? PASS.** Cross-hour selection-rate CV at τ=5 falls from
**0.663 → 0.119** (pass threshold 0.25). The hourly firing rate goes from a
**0.90%–8.15%** spread to **2.37%–4.08%**. Trade counts are matched to 0.8%
(111,023 vs 110,124), and the matched `k` was **picked from a fine swept grid**
(step 0.02, matched to within 1.2% on pooled rate), never interpolated — `np.interp`
clamps, and a matched-rate claim built on it would silently be an extrapolation.

**Q2 — Was the thin-hours localisation real? NO. RETRACTED.** Under the same-slot arm at
matched rate (τ=5, H=240, delay-1):

| session | n | gross R (abs σ unit) | 95% CI |
| --- | --- | --- | --- |
| off | 21,238 | 0.1896 | [0.061, 0.318] |
| asia | 33,255 | 0.2066 | [0.114, 0.299] |
| london | 27,396 | 0.0206 | [−0.116, 0.157] |

The pre-committed bar was that `off` or `asia` must exceed `london` by more than the sum
of the two cells' CI half-widths. `off − london = 0.169` against a combined half-width of
0.265; `asia − london = 0.186` against 0.228. **Neither clears.** Under the *absolute*
arm the same test passes (`off − london = 0.427` vs 0.302) — so the separation was
carried by the clock, not the market.

Precisely what is retracted: **the claim that reversion is localised in thin hours.** The
point estimates still lean that way, and I am not claiming the sessions are equal — the
separation simply is not supported once the cut fires evenly. The mechanism is visible in
the counts: normalising nearly doubles Asia (16,689 → 33,255) and cuts overlap by more
than half (37,429 → 16,808). The EXP-0002 session table was never comparing like with
like.

**Q3 — Does the grain survive? YES, and more sharply.** Same-slot, delay-1, each rung at
its own rate-matched `k`:

| τ | gross R (abs unit) | 95% CI | n |
| --- | --- | --- | --- |
| **5** | **0.1056** | **[0.045, 0.166]** | 110,124 |
| 15 | 0.0498 | [−0.011, 0.110] | 36,737 |
| 30 | −0.0040 | [−0.032, 0.024] | 21,448 |
| 60 | 0.0047 | [−0.023, 0.033] | 10,669 |
| 120 | −0.0156 | [−0.044, 0.013] | 5,138 |

τ\* = 5 is confirmed, and it is now the only rung whose CI excludes zero.

**Q4 — Does normalising destroy the information? No — it improves it.** At matched count
and in the same risk unit, `slot` beats `abs`: **0.1056 vs 0.0651 R** (+0.041), with
gross **0.383 vs 0.244 pips**. The slot arm's CI excludes zero; the absolute arm's barely
does (t = 2.08). This reproduces the LEARNINGS §1 finding that same-slot normalisation
removes the clock without removing the signal — here it removed a confound *and* sharpened
the estimate.

## 2. What this does NOT change

The cost verdict, exactly as HYP-0003 §5 pre-stated. The best cell is **0.383 gross pips**
against a modelled base round trip of **1.209 pips**, of which 0.70 is commission alone.
Renormalising a threshold changes which signals are taken; it cannot move a ~0.4-pip gross
edge past a ~1.2-pip round trip. Still short by roughly 3×.

## 3. Alternative explanations considered

- **Did the slot arm just find a different, better-selected sample?** It is matched on
  trade count (0.8%) and pooled firing rate (1.2%), and scored in the *absolute* σ risk
  unit so the two arms' R figures are directly comparable. The gain is not a units effect.
- **Is the slot arm's warm-up an advantage?** No — both arms are restricted to the common
  set of bars where *both* estimators are warmed up, so the slot estimator's ~90-session
  longer warm-up costs it rows in both arms equally.
- **Is the improvement just deeper `|z|`?** The matched `k` for slot is 2.14 vs 2.00 for
  abs, but that is a *rate*-matching adjustment, and the two arms take the same number of
  trades. Mean `|z|` at signal is carried in `surface.csv` for anyone who wants to check
  the depth distributions directly.
- **Does the achieved per-hour rate gap (4–8%) undermine the match?** No. That number
  compares an *unweighted mean of hourly rates* against a *bar-weighted pooled rate*; the
  two differ precisely because the arms distribute differently across hours, which is the
  thing being fixed. The decision-relevant match — total trade count — is 0.8%.

## 4. Departures and limitations

> **Update 2026-08-09 (Stage-A repair, Codex finding 3/4):** the "No departures" line
> below is corrected. There ARE two declared departures from the frozen HYP-0003:
> (a) **rate matching** — HYP-0003 §4 specifies a *per-hour* firing rate; `choose_matched_k`
> matches ONE *pooled* crossing rate across all hours (matched total count). Sensible, but a
> departure, now labelled as such in `verdict.json` (`Q2…matching_departure`) and the report.
> (b) **grain ranking** — the Q3 confirmation originally took each grain's *better* of
> H∈{60,240}, an undeclared two-horizon search. The primary ranking is now at the
> preregistered **fixed H\*=240** (no horizon searched); the best-of-horizon table is retained
> as a labelled robustness aux only. Neither departure changes τ\*=5's large descriptive lead.

- ~~**No departures from HYP-0003.**~~ **Corrected above.** The four decision rules are
  executed in `decide()`, not narrated, but two implementation choices depart from the frozen
  contract (pooled- vs per-hour rate matching; fixed-H\* vs best-of-horizon grain ranking).
- **One implementation change made before results were read:** the first draft matched
  rates on the coarse reporting grid, which left gaps up to 16% of target — large enough
  (≈0.01–0.02 R along the threshold curve) to contaminate Q4, whose effect is 0.041 R. It
  was replaced with a two-pass design: pass 1 counts crossings on a fine grid (step 0.02),
  pass 2 builds outcomes only at the matched `k`. Cost: one extra data pass.
- **UTC slots do not track DST**, so a slot's meaning shifts by an hour twice a year
  against London and New York local time, blending two adjacent hours' volatility for part
  of the year. Not corrected. If Stage B adopts the slot feature, a local-time slot variant
  is worth one run.
- **2024+ untouched.** Nothing here reads the sealed holdout.

## 5. Builder interpretation

The addendum did what it was for: it found that one of EXP-0002's reported findings was an
artifact of its own threshold, and it did not disturb the two that matter.

Concretely, three things for Stage B:

1. **Freeze the reference book on the same-slot z, not the all-hours z.** It is
   confound-free on the clock (CV 0.12 vs 0.66) and strictly better at matched count
   (+0.041 R). There is no longer an argument for the absolute σ.
2. **τ\* = 5 / H\* = 240 stands** and is now the only rung with a CI excluding zero.
3. **Drop the thin-hours narrative.** Do not carry "the edge lives in off-hours and Asia"
   into Stage C as a prior, and do not design a session overlay around it. The honest
   statement is that session differences are not established.

One knock-on for Stage C: axis 2 (volatility regime) was going to be partly re-measuring
the base signal's own clock selection. With the slot normaliser in the entry, that overlap
is largely gone, so a vol-regime overlay becomes a cleaner test than it would have been.

### 5a. Added for the Stage-B handoff: the cost side is now clock-dependent

Computed after the run, for `RUNBOOK.md` §4.3 — reproduce with
`python -u forex/exploration_4/_diag_intraday_sigma.py`; output
`intraday_sigma_profile.csv`.

Same-slot normalisation makes the **entry** clock-neutral, but it makes the **cost**
clock-dependent *in the sizing unit*, because `σ_slot` tracks the intraday profile while
the modelled round trip is roughly flat in pips. At τ=5, `σ_slot` runs **2.27 → 5.05 pips**
across UTC hours (2.2×), so a ~1.2-pip round trip costs **0.238 R_slot** at 13:00–14:00 UTC
but **0.529 R_slot** at 21:00 — against a flat **0.379 R_abs** everywhere.

Two consequences Stage B must handle: net must be reported in the same unit it sizes in
(a gross figure in `R_slot` against a cost in pips is not a net result), and net-of-cost
results will tilt toward busy hours **structurally** — in the opposite direction to the
finding Q2 just retracted. That gradient is mechanical and must not be read as a
discovery or built into an overlay.

## 6. Independent review checklist

1. Rerun the tests and the EXP-0003 command; confirm `verdict.json` reproduces.
2. Check the matched-`k` construction in `crossing_counts`/`choose_matched_k` — the whole
   comparison rests on it, and it is the piece I had to rebuild.
3. Check the common-sample restriction in `grain_arms` actually equalises the two arms'
   eligible rows rather than merely intersecting them loosely.
4. Judge the Q2 retraction: the rule was pre-committed, but the point estimates still lean
   the old way, so confirm you agree the CI-based bar is the right one.
5. Confirm no number here reads 2024+.
