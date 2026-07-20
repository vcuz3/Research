# EXP-0019 Results Discussion

- Hypothesis: `HYP-0011` — Volatility-conditional exit-check cadence for a fixed-1-contract prop account
- Status: completed
- Builder: Claude (Opus 4.8)
- Reviewer: unassigned
- Primary metric: dollar fixed-1-contract zero-day daily net Sharpe uplift vs Null C
- Kill test: REJECT unless dollar-Sharpe uplift (cond-everybar) > 0, treatment net$ >= baseline net$, and upper-tail p <= 0.05 vs Null C

## Result versus hypothesis

REJECT on both markets. The user's thesis — in high vol, checking the stop every
bar causes whipsaw, so interval-check (15-min) when volatile and stay continuous
when calm — does NOT beat a fixed continuous stop for a fixed-1-contract account.

The investigation had two parts:

1. FIXED cadence sweep + Null C (`hyp_0011_exit_cadence.py`, artifacts
   `fixed_cadence_null_{nq,es}.txt`). Motivating screen (`scripts/exit_cadence.py`)
   found a NON-MONOTONE interior optimum at ~15 min on the dollar metric (NQ Sh
   1.14->1.29, ES 0.93->1.09) between the 30-min decision clock and the every-bar
   continuous stop. But the fixed-15 uplift over the 30-min decision baseline
   FAILED: canonical ATR-R metric NQ +0.034 p=0.29, ES +0.058 p=0.19; dollar metric
   NQ +0.113 p=0.064, ES +0.120 p=0.097 (marginal, never clears 0.05). The whole
   dollar uplift lives in vol-era weighting (rule 19): it evaporates under ATR
   normalisation. Notably the fixed-cadence null centers NEGATIVE (more checking
   hurts on noise), so the real tape's slight edge over decision is genuine but tiny
   downside-continuation — the same effect as the already-adopted NQ continuous stop.

2. CONDITIONAL cadence + Null C (`hyp_0011_cond_cadence.py`, artifacts
   `cond_{nq,es}.txt`) — the actual HYP-0011. Causal intraday-vol regime
   (intraday-to-date range vs trailing-14-session same-tod median), hi-vol->15min,
   lo-vol->every-bar. Contrast cond - everybar on the dollar metric.

## Gross, net, baseline, and null comparison

Conditional arm (dollar day-Sharpe, fixed 1 contract; common post-lb90 sample):

| arm      | NQ Sh$ | NQ net$ | ES Sh$ | ES net$ |
|----------|--------|---------|--------|---------|
| decision |  0.85  | 268,624 |  0.69  | 123,030 |
| cad15    |  0.97  | 291,312 |  0.81  | 139,504 |
| everybar |  0.96  | 265,937 |  0.69  | 111,396 |
| **cond** |  0.92  | 273,454 |  0.70  | 118,594 |

The conditional switch is DOMINATED by the fixed cadences: cond (NQ 0.92 / ES 0.70)
loses to both fixed everybar (0.96 / 0.69) and fixed cad15 (0.97 / 0.81). Blending
"15-min in high vol, continuous in low vol" is worse than picking one fixed cadence.

Null C (30 draws, cond - everybar, dollar metric):
- NQ: real uplift -0.042; null mean +0.032, sd 0.086, p=0.7419 (22/30 null >= real).
- ES: real uplift +0.017; null mean +0.082, sd 0.083, p=0.8387 (25/30 null >= real).

Diffusivity gates exact (NQ real=null=0.2500; ES real=null=0.0000).

## Regimes, sensitivity, and alternative explanations

The decisive diagnostic is the NULL-CENTER SIGN. The cond-vs-everybar null centers
POSITIVE on both markets (+0.032 NQ, +0.082 ES), and the real tape sits BELOW its
own null. This is the textbook variance-amplifier signature (EXP-0010/0012): the
conditional switch is "check LESS often in high vol" = a looser exit, and a looser
exit lifts Sharpe AT LEAST AS MUCH on a shuffled-noise tape as on the real tape,
because whipsaw reduction is a property of volatility/path geometry that the
path-preserving Null C PRESERVES (diffusivity gate holds). So the user's whipsaw
mechanism is mechanically real but it is NOT information — noise reproduces it and
then some. The real tape doing WORSE than its noise twin means the intraday timing
that survives (the NQ continuous-stop effect) actually PREFERS the every-bar checks
the conditioner removes in high vol.

Rule-19 note: on the ATR-R metric the fixed-15 dollar uplift disappears, confirming
the apparent gain is vol-era weighting. For a fixed-1-contract prop account that
cannot size down in high vol, the dollar metric is the correct objective — but even
on it the conditional overlay fails (real below null on both markets).

## Artifact and implementation risks

- `cond_regime`/`hivol_cadence`/`lovol_cadence` added default-off to core/engine2.py;
  cond_regime=None reproduces the baseline (fixed exit_check) exactly. The int-cadence
  branch in core/engine.py + engine2.py preserves the "decision"/"every_bar" strings
  bit-exact (verified: NQ decision Sh 1.14, every_bar 1.28 unchanged).
- Regime is fully causal (open->now today + strictly-prior sessions) and rule-9a
  guarded (fractional min_periods 0.7); recomputed inside every Null C draw so it
  rides the full pipeline. Consumed discovery sample — future shadow only.

## Builder interpretation

REJECT. The conditional cadence is dominated by fixed cadences and fails its Null C
decisively (real below a positively-centered null on both markets). It is a
variance/turnover lever, not alpha, and adds nothing a single fixed cadence choice
does not already give. Retain the fixed NQ continuous (every-bar) stop; on ES, fixed
cad15 is the descriptive best but was not itself Null-C-validated vs everybar and is
not adopted.

## Independent review

- Review status: pending
- Objections: pending
- Verdict: pending (builder verdict REJECT)

## Promotion decision

- `reports/FINDINGS.md`: not promoted (negative result)
- `MEMORY.md`: updated — HYP-0011 REJECT recorded under invalidated/superseded
- Shared `LEARNINGS.md`: candidate — the null-center-sign discriminator for
  conditional-vs-continuous exit cadence generalises the EXP-0010/0012 lesson, but
  hold for cross-project confirmation (GC/ES exit family) before promoting.
