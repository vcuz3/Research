# Final Review — forex/noise_vwap

Date: 2026-08-01. Builder: Claude (Opus 5). Independent review: outstanding.

## Verdict

**NO-GO. Close the construct for FX.** Two registered experiments, both
preregistered with kill tests written before the run, both rejected on their own
declared gates. This is a rule-25 successful negative result.

## Research evidence vs deployable evidence

| | |
| --- | --- |
| **Research evidence** | Strong and internally consistent. The strategy loses gross on 4 pairs x 2 session definitions, in 88 of 96 cells; the exit-neutral diagnostic shows FX carries ~10x less directional information per band-width than NQ, with no reliable sign; the identical code path returns positive, significant continuation on NQ/ES, so the measurement is sound. |
| **Deployable evidence** | None, and none is claimed. No configuration in the declared family clears cost, so nothing advances to a null test, a sizing study, or a shadow period. |

Nothing here is a watchlist candidate. There is no cell whose sign is right and
whose size is merely marginal.

## What would have been concluded without the controls

Worth recording, in the style of `futures/nq/claude_exploration_1`:

1. **Without the gross gate**, the natural next move on seeing net Sharpe −0.36
   for `anchor|decision` would have been to hunt for a stop or a filter that
   "fixes" it. Reading gross first ends the investigation in one number.
2. **Without the no-anchor `band` control**, the obvious diagnosis would have
   been "FX has no volume, so the VWAP substitute is too weak" — a plausible,
   completely wrong story that would have sent the work off to build better
   volume proxies. The volume-free stop matches the published rule everywhere.
3. **Without the exit-neutral arm**, the 92% stop-out rate would have read as
   "the trailing stop is too tight for FX", and the next experiment would have
   been a stop-width sweep. Removing the exit entirely leaves the loss intact.
4. **Without the cluster-robust estimand**, EXP-0002 would have reported a
   crushing, highly significant inversion (t −16 to −27 on every row) and
   concluded that FX noise-band breaks reliably mean-revert. That is an artifact
   of an estimand that cannot be implemented causally. The corrected inference
   flipped the verdict.
5. **Without the re-executed mirror**, "just trade it the other way" would have
   looked like the answer. The inverted signal is 5–11x smaller than the spread
   and its sign is not stable across session definitions.

Four of these five would have produced a confident, wrong, publishable-looking
next step.

## Recommended next steps

Ordered by expected value, and deliberately short — the honest recommendation is
that most of the obvious follow-ups are *not* worth doing.

### 1. Do NOT continue this construct on FX (highest value)

No stop variant, band recast, session definition, cost assumption or filter
rescues a negative gross. The workspace has already exhausted the band-recast
axis on NQ (cone, quantile, asymmetric, surround, Laplace — all rejected) and
the selectivity axis (VEI, Hurst, RVOL, gap, percentile-rank — all rejected).
Re-running those on an instrument where the base signal is *negative* has no
prior.

### 2. Promote the estimand finding, and audit for it elsewhere (high value, cheap)

Finding D is the most reusable output here and it is not FX-specific: the same
per-signal vs session-averaged sign reversal appears on NQ and ES. Any statistic
in this workspace that averages per-signal outcomes within a session and then
averages sessions is suspect whenever signal count is endogenous to the outcome.
Filed to `ai_shared_memory/LEARNINGS.md` as provisional; confirm or kill by
recomputing one existing per-signal headline under both estimands in a second
project. Evaluation-only, no refit, so it cannot be re-tuning.

### 3. If FX intraday research continues, change the thesis, not the parameters

The evidence says FX majors have no exploitable intraday continuation from a
session-anchored displacement at a 30-minute decision clock. Directions with an
actual prior, none of which reuse this construct:

- **Scheduled-event windows.** FX's known intraday structure is around fixed
  events (ECB/FOMC/NFP, the 16:00 London fix, the 17:00 ET roll). A displacement
  construct anchored on an *event* rather than a session open is a different
  hypothesis, not a parameter change. Heed the `vei_exploration` warning: name
  the cell where the mechanism must fire *before* the run.
- **Cross-pair structure.** All four pairs share the USD leg. The dollar-factor
  work in `futures/nq/claude_exploration_1` found the dollar↔asset link to be
  large but almost entirely *contemporaneous* (~75x the 5-minute lagged one), so
  a lead-lag thesis here needs the reverse-direction control run first — it is
  one line and it killed that project's cleanest result.
- **Carry / rate-differential conditioning**, the one structural force in FX
  with no equity analogue. AUDUSD and NZDUSD were the two pairs showing any
  consistent (reverting) signal here, and they are the two carry pairs. Weak,
  but it is the only pattern in the data that points anywhere.

### 4. Fix the cost model before any future FX work (blocking for anything deployable)

The IBKR archive is midpoint-only, so 0.5 pip/side is an assumption, not a
measurement. It does not threaten this NO-GO (gross is negative), but no future
FX result in this workspace should be believed without bid/ask or at least a
time-of-day spread profile — particularly for anything touching the Asia hours,
where the `fxday` reversion concentrates and where the assumption is worst.

### 5. Reusable assets this project leaves behind

- `core/session.py` — DST-safe FX session construction, the TWAP anchor, causal
  noise bands with the rule-9a fractional floor, causal daily ATR in pips.
- `core/engine.py` + `core/engine_nb.py` — honest next-open engine with four
  stop references including an exit-neutral one and a re-executed mirror, plus a
  trade-level parity gate.
- `core/nulls.py` — path-preserving return shuffle, opening atom pinned,
  invariants tested. Unspent here; ready if a future FX thesis clears its
  primary metric.
- `scripts/entry_information.py` — exit-neutral entry-information diagnostic
  with cluster-robust inference and a futures reference arm, running FX and
  index futures through the same code path.
- `scripts/data_quality.py` — the rule-9a gate that found the archive defect.

## Outstanding

- Independent review of EXP-0001 and EXP-0002.
- Second-project confirmation of finding D before it moves from provisional to
  confirmed.
